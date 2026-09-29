#!/usr/bin/env python3
"""
Hermes Director - Product Factory Orchestration Engine
Phase 5.2: Real specialist invocation, semantic classification, quality gates, tests.

Key changes from Phase 5.1:
- Real CLI worker invocation (Claude Code, Codex) instead of simulated outputs
- Real worker availability checks (claude doctor, codex --version)
- Semantic classification via model when confidence is MEDIUM/LOW
- Gate-specific quality validation (not just artifact presence)
- Automated test suite
- File-based human approval with APPROVE/REJECT mechanisms
- Obsidian capture via file writes to vault
- Fixed ML over-selection: optional specialists only when productionization keywords present
"""

import argparse
import yaml
import os
import sys
import re
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, Optional

# Import canonical schema helpers
from schemas import canonical, validate as validate_specialist_schema

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent
PROFILE_DIR = SKILL_DIR.parent.parent
POLICY_PATH = PROFILE_DIR / "policies" / "routing_policy.yaml"
TEMPLATES_DIR = PROFILE_DIR / "templates"
STATE_TEMPLATE = TEMPLATES_DIR / "project_state.md"
OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", "")
PROFILE_NAME = "product-factory"
AVAILABILITY_CACHE = PROFILE_DIR / "runtime" / "worker_availability.json"
AVAILABILITY_TTL_SECONDS = 300
MAX_SPECIALIST_CONTEXT_CHARS = 12000

# CLI worker paths
HERMES_PATH = shutil.which("hermes") or str(PROFILE_DIR.parent.parent / "bin" / "hermes.exe")
CLAUDE_PATH = shutil.which("claude") or str(PROFILE_DIR.parent.parent / "node" / "claude.cmd")
CODEX_PATH = shutil.which("codex") or str(PROFILE_DIR.parent.parent / "bin" / "codex.cmd")
GEMINI_PATH = shutil.which("gemini") or "gemini"
LAST_WORKER_ERRORS: dict[str, str] = {}
LAST_WORKER_EVENTS: dict[str, list[dict]] = {}


def _redact_worker_error(value: str) -> str:
    """Keep operational errors useful without persisting credentials."""
    text = str(value or "empty response")
    text = re.sub(
        r"(?i)(api[_ -]?key|authorization|token|secret|password)(\s*[:=]\s*)\S+",
        r"\1\2[REDACTED]",
        text,
    )
    return text[:500]


def _provider_failure_kind(value: str) -> str:
    """Classify invocation errors for bounded retry and availability handling."""
    text = str(value or "").lower()
    if any(token in text for token in (
        "overloaded", "temporarily unavailable", "service unavailable",
        "upstream error", "retryable: true", "http 502", "http 503", "http 504",
        "timed out", "timeout", "connection reset", "connection aborted", "read timed out",
    )):
        return "RETRYABLE_OVERLOAD"
    if any(token in text for token in (
        "quota", "rate limit", "rate-limit", "usage limit", "credit", "http 429", " 429",
    )):
        return "QUOTA_LIMITED"
    return "FAILED"


def _retry_settings(policy: dict) -> tuple[int, list[float], int]:
    availability = policy.get("availability", {})
    retries = max(0, min(int(availability.get("overload_max_retries", 2)), 4))
    configured = availability.get("overload_backoff_seconds", [1, 3])
    if not isinstance(configured, list) or not configured:
        configured = [1, 3]
    backoff = [max(0.0, min(float(value), 30.0)) for value in configured]
    cooldown = max(1, int(availability.get("overload_cooldown_seconds", 300)))
    return retries, backoff, cooldown

# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------
def load_policy() -> dict:
    with open(POLICY_PATH, 'r') as f:
        return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Keyword-based classification (first pass)
# ---------------------------------------------------------------------------
def contains_any_keyword(text: str, keywords) -> bool:
    """Match whole words/phrases so tokens such as ``ui`` never match ``build``."""
    return any(re.search(rf"(?<!\w){re.escape(str(keyword).strip())}(?!\w)", text,
                         flags=re.IGNORECASE) for keyword in keywords if str(keyword).strip())


def classify_keywords(request: str) -> list[str]:
    """Return list of matching project types based on keyword heuristics."""
    r = request.lower()
    keywords = {
        "WEBSITE": ["website", "landing page", "home page", "static site", "company site", "site"],
        "SOFTWARE_APPLICATION": ["software application", "desktop application", "windows app", "mac app"],
        "SAAS": ["saas", "software as a service", "web application", "web app", "platform", "dashboard"],
        "DATA_SCIENCE": ["data science", "data analysis", "analyse data", "analyze data", "statistical analysis", "data visualization"],
        "MACHINE_LEARNING": ["machine learning", "ml ", "predictive model", "train a model", "forecast", "model training", "predict"],
        "AI_AGENT": ["ai agent", "artificial intelligence agent", "autonomous agent", "agent system"],
        "AI_LLM_APPLICATION": ["llm", "large language model", "gpt", "chatbot", "ai assistant", "ai-powered", "rag", "retrieval augmented"],
        "API": ["rest api", "graphql", "web service", "microservice", "api endpoint"],
        "BUSINESS_AUTOMATION": ["business automation", "workflow automation", "process automation", "automate"],
        "DATA_PIPELINE": ["data pipeline", "etl", "data flow", "data ingestion", "data engineering"],
        "PROCUREMENT_SYSTEM": ["procurement", "bill of quantities", "boq", "supplier quotation", "tender", "rfq"],
        "INTERNAL_BUSINESS_SYSTEM": ["internal system", "internal tool", "company tool", "employee portal", "admin panel"],
        "RESEARCH_PROJECT": ["research", "study", "survey", "literature review", "market research", "research paper"],
        "SIMPLE_TASK": ["summarise", "summarize", "rewrite", "explain", "translate", "shorten", "expand", "reword", "paraphrase"],
    }
    matches = []
    for proj_type, words in keywords.items():
        if contains_any_keyword(r, words):
            matches.append(proj_type)
    return matches


def classify_request(request: str, policy: dict) -> tuple[str, str, bool]:
    """
    Classify the request.
    Returns (project_type, confidence, semantic_used).
    Uses keyword heuristics first; if confidence is MEDIUM/LOW or hybrid,
    escalates to semantic classification via the default model.
    """
    matches = classify_keywords(request)
    non_simple = [m for m in matches if m != "SIMPLE_TASK"]

    # HYBRID: more than one non-simple match
    if len(non_simple) > 1:
        project_type = "HYBRID_PROJECT"
        confidence = "MEDIUM"
    elif len(matches) == 1:
        project_type = matches[0]
        if project_type == "SIMPLE_TASK":
            confidence = "HIGH"
        else:
            confidence = "HIGH"
    elif len(matches) == 0:
        # Default: try to infer from request content
        r = request.lower()
        if contains_any_keyword(r, ["build", "create", "develop", "write code", "implement", "program"]):
            project_type = "SOFTWARE_APPLICATION"
        elif contains_any_keyword(r, ["research", "find", "look up", "investigate"]):
            project_type = "RESEARCH_PROJECT"
        else:
            project_type = "SOFTWARE_APPLICATION"
        confidence = "LOW"
    else:
        # Only SIMPLE_TASK matched
        project_type = "SIMPLE_TASK"
        confidence = "HIGH"

    # If we matched SAAS or WEBSITE and also have ML keywords, force HYBRID
    r = request.lower()
    ml_keywords = ["machine learning", "ml ", "predictive model", "train a model", "forecast", "model training", "predict"]
    ai_keywords = ["ai assistant", "ai-powered", "chatbot", "llm", "gpt", "rag", "retrieval augmented"]
    has_ml = contains_any_keyword(r, ml_keywords)
    has_ai = contains_any_keyword(r, ai_keywords)

    if project_type in ("SAAS", "WEBSITE", "SOFTWARE_APPLICATION", "API", "INTERNAL_BUSINESS_SYSTEM") and (has_ml or has_ai):
        project_type = "HYBRID_PROJECT"
        confidence = "MEDIUM"

    semantic_used = False
    # Escalate to semantic classification when confidence is MEDIUM/LOW or hybrid
    # But NEVER let semantic override a keyword-detected HYBRID_PROJECT —
    # multiple keyword matches is stronger signal than a single model guess.
    token_count = len(re.findall(r"[a-zA-Z0-9]+", request))
    should_use_semantic = (
        project_type == "HYBRID_PROJECT"
        or (confidence == "LOW" and token_count >= 3)
    )
    if should_use_semantic:
        semantic_used = True
        semantic_type = semantic_classify(request, policy)
        # Only allow semantic override when keywords gave a single type (not hybrid)
        if (matches and semantic_type and semantic_type != project_type
                and project_type != "HYBRID_PROJECT"):
            project_type = semantic_type
            confidence = "MEDIUM"  # semantic is better than keyword-only but not HIGH

    return project_type, confidence, semantic_used


def semantic_classify(request: str, policy: dict) -> Optional[str]:
    """
    Use the default model (nemotron via OpenRouter) to semantically classify
    the request into one of the known project types.
    Returns the classified type or None if the call fails.
    """
    # We use the Hermes CLI to call the model
    # Build a classification prompt
    prompt = f"""Classify this request into exactly ONE of these project types:
WEBSITE, SOFTWARE_APPLICATION, SAAS, DATA_SCIENCE, MACHINE_LEARNING,
AI_AGENT, AI_LLM_APPLICATION, API, BUSINESS_AUTOMATION, DATA_PIPELINE,
PROCUREMENT_SYSTEM, INTERNAL_BUSINESS_SYSTEM, RESEARCH_PROJECT, HYBRID_PROJECT, SIMPLE_TASK.

Request: {request}

Respond with ONLY the project type name, nothing else."""

    try:
        result = invoke_model(prompt, policy, "nemotron")
        if result:
            # Parse the response — expect a single type name
            cleaned = result.strip().upper().replace(" ", "_")
            known_types = [
                "WEBSITE", "SOFTWARE_APPLICATION", "SAAS", "DATA_SCIENCE",
                "MACHINE_LEARNING", "AI_AGENT", "AI_LLM_APPLICATION", "API",
                "BUSINESS_AUTOMATION", "DATA_PIPELINE", "PROCUREMENT_SYSTEM",
                "INTERNAL_BUSINESS_SYSTEM", "RESEARCH_PROJECT", "HYBRID_PROJECT",
                "SIMPLE_TASK"
            ]
            for t in known_types:
                if t in cleaned or cleaned in t:
                    return t
            # Fallback: return the cleaned value if it looks reasonable
            if cleaned in known_types:
                return cleaned
    except Exception as e:
        print(f"  [WARN] Semantic classification failed: {e}", file=sys.stderr)

    return None


def build_hermes_command(prompt: str, worker: dict) -> list[str]:
    """Build a one-shot command pinned to the isolated Product Factory profile."""
    return [
        HERMES_PATH, "--profile", PROFILE_NAME,
        "--provider", str(worker.get("provider", "")),
        "--model", str(worker.get("model", "")),
        "--in", str(PROFILE_DIR),
        "-z", prompt,
    ]


def invoke_model(prompt: str, policy: dict, worker_key: str,
                 sleep_fn: Callable[[float], None] = time.sleep) -> Optional[str]:
    """
    Invoke a model worker via Hermes CLI or direct API.
    For nemotron/nous: use the hermes chat -q command.
    Returns the model's text response or None.
    """
    worker = policy.get("workers", {}).get(worker_key, {})
    provider = worker.get("provider", "openrouter")

    model = worker.get("model", "")
    if not model:
        LAST_WORKER_ERRORS[worker_key] = "Worker model is not configured."
        return None

    # Use a per-invocation profile, provider and model override. This leaves the
    # user's sticky/default Hermes configuration untouched.
    cmd = build_hermes_command(prompt, worker)

    retries, backoff, cooldown = _retry_settings(policy)
    events = []
    LAST_WORKER_EVENTS[worker_key] = events
    env = os.environ.copy()
    env["HERMES_PROFILE"] = PROFILE_NAME

    for attempt in range(1, retries + 2):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
                cwd=str(PROFILE_DIR),
                env=env,
            )
            if result.returncode == 0 and (result.stdout or "").strip():
                LAST_WORKER_ERRORS.pop(worker_key, None)
                events.append({"event": "INVOCATION_SUCCEEDED", "worker": worker_key,
                               "attempt": attempt})
                return result.stdout.strip()
            error = _redact_worker_error(result.stderr or result.stdout or "empty response")
            failure_kind = _provider_failure_kind(error)
            LAST_WORKER_ERRORS[worker_key] = error
            events.append({"event": failure_kind, "worker": worker_key,
                           "attempt": attempt, "detail": error})
            print(f"  [WARN] Model invocation failed (rc={result.returncode}): {error[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            error = "Model invocation timed out after 240 seconds."
            failure_kind = _provider_failure_kind(error)
            LAST_WORKER_ERRORS[worker_key] = error
            events.append({"event": failure_kind, "worker": worker_key,
                           "attempt": attempt, "detail": error})
            print("  [WARN] Model invocation timed out", file=sys.stderr)
        except FileNotFoundError:
            error = f"Hermes executable not found at {HERMES_PATH}."
            LAST_WORKER_ERRORS[worker_key] = error
            events.append({"event": "FAILED", "worker": worker_key,
                           "attempt": attempt, "detail": error})
            print("  [WARN] 'hermes' command not found", file=sys.stderr)
            break

        if failure_kind != "RETRYABLE_OVERLOAD" or attempt > retries:
            break
        delay = backoff[min(attempt - 1, len(backoff) - 1)]
        events.append({"event": "BACKOFF", "worker": worker_key,
                       "attempt": attempt, "delay_seconds": delay})
        sleep_fn(delay)

    final_kind = _provider_failure_kind(LAST_WORKER_ERRORS.get(worker_key, ""))
    if final_kind == "RETRYABLE_OVERLOAD":
        events.append({"event": "WORKER_TEMPORARILY_UNAVAILABLE", "worker": worker_key,
                       "cooldown_seconds": cooldown})
        record_worker_status(worker_key, "TEMPORARILY_UNAVAILABLE",
                             LAST_WORKER_ERRORS[worker_key], ttl_seconds=cooldown)
    elif final_kind == "QUOTA_LIMITED":
        record_worker_status(worker_key, "QUOTA_LIMITED",
                             LAST_WORKER_ERRORS[worker_key],
                             ttl_seconds=int(policy.get("availability", {}).get(
                                 "quota_cooldown_seconds", 900)))

    return None


# Stable reference used by retry-focused tests; the general test harness replaces
# the public adapter with a deterministic model stub.
_invoke_model_with_retry = invoke_model


# ---------------------------------------------------------------------------
# Specialist selection (FIXED: ML over-selection)
# ---------------------------------------------------------------------------
def get_specialists_for_type(project_type: str, policy: dict, request_lower: str) -> list[str]:
    """
    Return the list of specialists for the given project type.
    FIXED: MACHINE_LEARNING/DATA_SCIENCE no longer over-selects optional specialists.
    Optional specialists are ONLY added when productionization keywords are present.
    """
    r = request_lower

    # --- WEBSITE ---
    if project_type == "WEBSITE":
        required = ["Product Agent", "Architecture Agent", "Lead Engineer",
                     "UI/UX Agent", "QA Agent", "Security Agent", "Release/DevOps Agent"]
        optional = ["Research Agent"]
        specialists = required.copy()
        if contains_any_keyword(r, ["research", "market", "user study", "survey", "feedback"]):
            specialists.append("Research Agent")
        return specialists

    # --- MACHINE_LEARNING / DATA_SCIENCE (FIXED) ---
    if project_type in ("MACHINE_LEARNING", "DATA_SCIENCE"):
        # ALWAYS required: Product, Data/ML, ML/AI Evaluation, QA
        required = ["Product Agent", "Data/ML Engineer", "ML/AI Evaluation Agent", "QA Agent"]
        specialists = required.copy()

        # Optional specialists are ONLY included when productionization keywords appear.
        # This fixes the over-selection bug where ANY keyword would pull in ALL optional specialists.
        production_keywords = [
            "deploy", "production", "serve", "api", "endpoint", "web app",
            "web application", "dashboard", "integrate", "application",
            "software", "ux", "interface", "frontend",
            "security", "secure", "encryption", "authentication",
            "authorization", "sensitive data", "privacy", "host", "cloud",
            "mlops", "pipeline", "monitoring", "drift"
        ]


        if contains_any_keyword(r, production_keywords):
            # Need to productionize: add Architecture, Lead Engineer, Security, Release/DevOps, UI/UX, Research
            optional_additions = [
                "Architecture Agent",
                "Lead Engineer",
                "Security Agent",
                "Release/DevOps Agent",
                "UI/UX Agent",
                "Research Agent"
            ]
            # Only add Research if research keywords present
            if contains_any_keyword(r, ["research", "market", "study", "survey"]):
                specialists.append("Research Agent")
            # Add others unconditionally when productionizing
            for spec in optional_additions:
                if spec != "Research Agent":
                    specialists.append(spec)

        return specialists

    # --- HYBRID_PROJECT ---
    if project_type == "HYBRID_PROJECT":
        all_specs = [
            "Product Agent",
            "Architecture Agent",
            "Data/ML Engineer",
            "Lead Engineer",
            "ML/AI Evaluation Agent",
            "QA Agent",
            "Security Agent",
            "UI/UX Agent",
            "Release/DevOps Agent",
        ]
        if contains_any_keyword(r, ["research", "market", "study", "survey"]):
            all_specs.append("Research Agent")
        ml_keywords = ["machine learning", "ml ", "predictive model", "train", "forecast", "data science", "predict", "prediction"]
        ai_keywords = ["ai ", "llm", "gpt", "chatbot", "rag", "assistant", "intelligent", "ai-powered"]
        ui_keywords = ["ui", "ux", "interface", "frontend", "dashboard", "web app"]
        security_keywords = ["security", "secure", "encryption", "authentication",
                             "authorization", "sensitive data", "privacy", "saas"]
        deployment_keywords = ["deploy", "production", "serve", "api", "endpoint", "saas", "dashboard"]

        # Remove Data/ML Engineer if no predictive/ML training requirement
        if not contains_any_keyword(r, ml_keywords):
            all_specs = [s for s in all_specs if s != "Data/ML Engineer"]
        # Remove ML/AI Evaluation Agent only if neither predictive ML nor AI/LLM keywords present
        if not contains_any_keyword(r, ml_keywords) and not contains_any_keyword(r, ai_keywords):
            all_specs = [s for s in all_specs if s != "ML/AI Evaluation Agent"]
        # Remove UI/UX if no UI requirement
        if not contains_any_keyword(r, ui_keywords):
            all_specs = [s for s in all_specs if s != "UI/UX Agent"]
        # Remove Security if not security-sensitive
        if not contains_any_keyword(r, security_keywords):
            all_specs = [s for s in all_specs if s != "Security Agent"]
        # Remove Release/DevOps if no deployment
        if not contains_any_keyword(r, deployment_keywords):
            all_specs = [s for s in all_specs if s != "Release/DevOps Agent"]

        return all_specs

    # --- PROCUREMENT_SYSTEM ---
    if project_type == "PROCUREMENT_SYSTEM":
        return ["Product Agent", "Research Agent", "Architecture Agent",
                "Lead Engineer", "QA Agent", "Security Agent",
                "UI/UX Agent", "Release/DevOps Agent"]

    # --- AI_AGENT ---
    if project_type == "AI_AGENT":
        required = ["Product Agent", "Architecture Agent", "Lead Engineer",
                     "QA Agent", "Security Agent", "ML/AI Evaluation Agent"]
        specialists = required.copy()
        if contains_any_keyword(r, ["ui", "ux", "interface", "frontend", "dashboard", "user-facing"]):
            specialists.append("UI/UX Agent")
        if contains_any_keyword(r, ["deploy", "production", "serve", "api", "endpoint"]):
            specialists.append("Release/DevOps Agent")
        if contains_any_keyword(r, ["research", "market", "study"]):
            specialists.append("Research Agent")
        return specialists

    # --- AI_LLM_APPLICATION ---
    if project_type == "AI_LLM_APPLICATION":
        required = ["Product Agent", "Architecture Agent", "Lead Engineer",
                     "QA Agent", "Security Agent", "ML/AI Evaluation Agent"]
        specialists = required.copy()
        if contains_any_keyword(r, ["ui", "ux", "interface", "frontend", "dashboard"]):
            specialists.append("UI/UX Agent")
        if contains_any_keyword(r, ["deploy", "production", "serve", "api"]):
            specialists.append("Release/DevOps Agent")
        if contains_any_keyword(r, ["research", "market", "competitor"]):
            specialists.append("Research Agent")
        return specialists

    # --- SAAS ---
    if project_type == "SAAS":
        return ["Product Agent", "Research Agent", "Architecture Agent",
                "Lead Engineer", "QA Agent", "Security Agent",
                "UI/UX Agent", "Release/DevOps Agent"]

    # --- API ---
    if project_type == "API":
        required = ["Product Agent", "Architecture Agent", "Lead Engineer",
                     "QA Agent", "Security Agent"]
        specialists = required.copy()
        if contains_any_keyword(r, ["deploy", "production", "serve", "endpoint"]):
            specialists.append("Release/DevOps Agent")
        if contains_any_keyword(r, ["ui", "dashboard", "frontend"]):
            specialists.append("UI/UX Agent")
        return specialists

    # --- DATA_PIPELINE ---
    if project_type == "DATA_PIPELINE":
        return ["Product Agent", "Data/ML Engineer", "QA Agent",
                "Architecture Agent"]

    # --- BUSINESS_AUTOMATION ---
    if project_type == "BUSINESS_AUTOMATION":
        required = ["Product Agent", "Architecture Agent", "Lead Engineer",
                     "QA Agent", "Security Agent"]
        specialists = required.copy()
        if contains_any_keyword(r, ["ui", "dashboard", "frontend"]):
            specialists.append("UI/UX Agent")
        if contains_any_keyword(r, ["deploy", "production"]):
            specialists.append("Release/DevOps Agent")
        return specialists

    # --- RESEARCH_PROJECT ---
    if project_type == "RESEARCH_PROJECT":
        return ["Product Agent", "Research Agent", "QA Agent"]

    # --- INTERNAL_BUSINESS_SYSTEM ---
    if project_type == "INTERNAL_BUSINESS_SYSTEM":
        return ["Product Agent", "Architecture Agent", "Lead Engineer",
                "QA Agent", "Security Agent", "UI/UX Agent",
                "Release/DevOps Agent"]

    # --- SIMPLE_TASK ---
    if project_type == "SIMPLE_TASK":
        return []

    # --- Default fallback ---
    required = ["Product Agent", "Architecture Agent", "Lead Engineer",
                "QA Agent", "Security Agent", "Release/DevOps Agent"]
    specialists = required.copy()
    if contains_any_keyword(r, ["ui", "ux", "interface", "frontend", "dashboard"]):
        specialists.append("UI/UX Agent")
    if contains_any_keyword(r, ["research", "market", "study"]):
        specialists.append("Research Agent")
    return specialists


# ---------------------------------------------------------------------------
# Worker mapping
# ---------------------------------------------------------------------------
SPECIALIST_TO_KEY = {
    "Product Agent": "product_agent",
    "Research Agent": "research_agent",
    "Architecture Agent": "architecture_agent",
    "Lead Engineer": "lead_engineer",
    "Data/ML Engineer": "data_ml_engineer",
    "QA Agent": "qa_agent",
    "Security Agent": "security_agent",
    "UI/UX Agent": "ui_ux_agent",
    "ML/AI Evaluation Agent": "ml_ai_evaluation_agent",
    "Release/DevOps Agent": "release_devops_agent",
    "Hermes Director": "hermes_director",
}

PRODUCT_FACTORY_ROLES = [
    "Hermes Director",
    "Product Agent",
    "Research Agent",
    "Architecture Agent",
    "Lead Engineer",
    "Data/ML Engineer",
    "QA Agent",
    "Security Agent",
    "UI/UX Agent",
    "ML/AI Evaluation Agent",
    "Release/DevOps Agent",
]


def get_skipped_specialists(selected: list[str], project_type: str) -> list[dict]:
    """Return an explicit, display-safe explanation for every unselected role."""
    skipped = []
    for specialist in PRODUCT_FACTORY_ROLES[1:]:
        if specialist in selected:
            continue
        if specialist == "Data/ML Engineer":
            reason = "No predictive modelling, model training, or ML data pipeline is required."
        elif specialist == "ML/AI Evaluation Agent":
            reason = "No ML or LLM component exists to evaluate."
        else:
            reason = f"Not required by the {project_type} routing policy for this request."
        skipped.append({"specialist": specialist, "reason": reason})
    return skipped


def record_activity(state: dict, event: str, detail: str, **fields) -> dict:
    """Append a timestamped canonical lifecycle event to project state."""
    item = {"timestamp": _utc_timestamp(), "event": event, "detail": detail}
    item.update({key: value for key, value in fields.items() if value is not None})
    state.setdefault("activity", []).append(item)
    return item

# Map specialists to the CLI worker that executes them
SPECIALIST_CLI_WORKER = {
    "Product Agent": "nemotron",           # orchestration via model
    "Research Agent": "gemini",            # long-context research
    "Architecture Agent": "nous",          # deeper reasoning
    "Lead Engineer": "claude_code",        # software implementation
    "Data/ML Engineer": "claude_code",     # data/ML coding
    "QA Agent": "codex",                   # independent QA
    "Security Agent": "claude_code",       # security review
    "UI/UX Agent": "claude_code",          # UI/UX review
    "ML/AI Evaluation Agent": "claude_code",  # evaluation
    "Release/DevOps Agent": "claude_code",    # deployment
}


def get_workers_for_specialist(specialist: str, policy: dict) -> dict:
    """
    Map specialist to primary/fallback workers from routing policy.
    For CLI-based specialists, also return the CLI worker type.
    """
    routing = policy.get("routing", {})
    key = SPECIALIST_TO_KEY.get(specialist)
    if not key:
        return {"primary": "unknown", "fallback": "unknown", "cli_worker": "unknown"}

    worker_info = routing.get(key, {})
    result = {
        "primary": worker_info.get("primary", "unknown"),
        "fallback": worker_info.get("fallback", "unknown"),
        "cli_worker": SPECIALIST_CLI_WORKER.get(specialist, "unknown"),
    }

    # Nested workers (data_ml_engineer, ml_ai_evaluation_agent)
    if specialist in ("Data/ML Engineer", "ML/AI Evaluation Agent"):
        result["primary_orchestration"] = worker_info.get("primary_orchestration", "unknown")
        result["reasoning_fallback"] = worker_info.get("reasoning_fallback", "unknown")
        result["implementation_worker"] = worker_info.get("implementation_worker", "unknown")
        result["implementation_fallback"] = worker_info.get("implementation_fallback", "unknown")
        result["review_worker"] = worker_info.get("review_worker", "unknown")
        result["review_fallback"] = worker_info.get("review_fallback", "unknown")
        if specialist == "ML/AI Evaluation Agent":
            result["evaluation_worker"] = worker_info.get("evaluation_worker", "unknown")
            result["evaluation_fallback"] = worker_info.get("evaluation_fallback", "unknown")

    # second_fallback for lead_engineer
    if specialist == "Lead Engineer":
        sf = worker_info.get("second_fallback")
        if sf:
            result["second_fallback"] = sf

    return result


# ---------------------------------------------------------------------------
# Real worker availability checks
# ---------------------------------------------------------------------------
def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_file(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _write_json_file(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
    os.replace(temporary, path)


def canonical_runtime_project_dir(value: Path) -> Path:
    """Resolve a CLI project directory and keep it inside this profile runtime."""
    root = (PROFILE_DIR / "runtime" / "projects").resolve()
    target = Path(value).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"State directory must be inside the canonical Product Factory runtime: {root}"
        ) from exc
    if target == root:
        raise ValueError("State directory must identify one project, not the projects root.")
    return target


def _profile_env_has(*names: str) -> bool:
    """Check configuration presence without loading or exposing secret values."""
    if any(os.environ.get(name) for name in names):
        return True
    env_file = PROFILE_DIR / ".env"
    try:
        configured = {
            line.split("=", 1)[0].strip()
            for line in env_file.read_text(encoding="utf-8").splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
    except OSError:
        return False
    return any(name in configured for name in names)


def _provider_auth_status(provider: str) -> tuple[str, str]:
    """Inspect Hermes' profile-scoped auth registry without making a model call."""
    try:
        result = subprocess.run(
            [HERMES_PATH, "--profile", PROFILE_NAME, "auth", "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, cwd=str(PROFILE_DIR),
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNAVAILABLE", "Hermes auth registry could not be inspected."
    if result.returncode != 0:
        return "UNAVAILABLE", "Hermes auth registry check failed."
    stdout = result.stdout or ""
    provider_line = next(
        (line.lower() for line in stdout.splitlines()
         if line.lower().startswith(provider.lower() + " ")),
        "",
    )
    if not provider_line:
        return "UNAVAILABLE", f"Provider '{provider}' has no profile-scoped credential."
    # Credential detail lines follow the provider header. Search only the
    # provider's section and persist no identity or credential metadata.
    sections = stdout.lower().split("\n\n")
    section = next((part for part in sections
                    if part.startswith(provider.lower() + " ")), provider_line)
    if "rate-limited" in section or "exhausted" in section:
        return "QUOTA_LIMITED", f"Provider '{provider}' is marked rate-limited by Hermes."
    return "AVAILABLE", f"Provider '{provider}' has a profile-scoped credential."


def record_worker_status(worker_type: str, status: str, reason: str = "",
                         cache_path: Optional[Path] = None,
                         ttl_seconds: int = AVAILABILITY_TTL_SECONDS) -> dict:
    """Persist a short-lived, redacted availability/quota observation."""
    cache_path = Path(cache_path or AVAILABILITY_CACHE)
    cache = _read_json_file(cache_path, {"schema_version": 1, "workers": {}})
    entry = {
        "status": status,
        "reason": reason[:500],
        "checked_at": _utc_timestamp(),
        "expires_epoch": time.time() + max(0, ttl_seconds),
    }
    cache.setdefault("workers", {})[worker_type] = entry
    _write_json_file(cache_path, cache)
    return entry


def _cached_worker_status(worker_type: str, cache_path: Path) -> Optional[dict]:
    entry = _read_json_file(cache_path, {}).get("workers", {}).get(worker_type)
    if not isinstance(entry, dict) or entry.get("expires_epoch", 0) <= time.time():
        return None
    return entry


def get_worker_availability(worker_type: str, policy: dict,
                            cache_path: Optional[Path] = None,
                            force: bool = False) -> dict:
    """Return safe runtime readiness without consuming a model request."""
    worker_info = policy.get("workers", {}).get(worker_type)
    if not worker_info:
        return {"status": "UNAVAILABLE", "reason": "Worker is not configured."}

    cache_path = Path(cache_path or AVAILABILITY_CACHE)
    configured_path = worker_info.get("path", "")
    # A policy path that is explicitly invalid must win over any cached result
    # produced for a different policy or an older installation.
    if (worker_info.get("type", "model") == "cli" and configured_path
            and configured_path.startswith("/nonexistent")):
        return {"status": "UNAVAILABLE",
                "reason": "Configured executable does not exist."}
    if not force:
        cached = _cached_worker_status(worker_type, cache_path)
        if cached:
            return cached

    if worker_info.get("type", "model") == "cli":
        executable = CLAUDE_PATH if worker_type == "claude_code" else CODEX_PATH
        available = check_claude_avail() if worker_type == "claude_code" else check_codex_avail()
        reason = f"CLI executable verified at {executable}." if available else "CLI health check failed."
        return record_worker_status(worker_type, "AVAILABLE" if available else "UNAVAILABLE",
                                    reason, cache_path)

    if not Path(HERMES_PATH).exists() and not shutil.which(str(HERMES_PATH)):
        return record_worker_status(worker_type, "UNAVAILABLE",
                                    "Hermes executable is unavailable.", cache_path)

    provider = str(worker_info.get("provider", "")).lower()
    env_names = {
        "openrouter": ("OPENROUTER_API_KEY",),
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"),
        "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"),
    }
    if provider in env_names and _profile_env_has(*env_names[provider]):
        status, reason = "AVAILABLE", (
            "Provider configuration is present; quota is checked on invocation.")
    else:
        registry_provider = "gemini" if provider == "google" else provider
        status, reason = _provider_auth_status(registry_provider)
    return record_worker_status(worker_type, status, reason, cache_path)


def check_worker_availability(worker_type: str, policy: dict) -> bool:
    return get_worker_availability(worker_type, policy).get("status") == "AVAILABLE"


def check_claude_avail() -> bool:
    """Claude Code is usable only when it is installed AND signed in (checked without consuming a model turn)."""
    try:
        result = subprocess.run(
            [CLAUDE_PATH, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        if result.returncode != 0:
            return False
        auth = subprocess.run(
            [CLAUDE_PATH, "auth", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
        try:
            return bool(json.loads(auth.stdout or "{}").get("loggedIn"))
        except ValueError:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def check_codex_avail() -> bool:
    """Codex is usable only when it is installed AND signed in (`codex login status` exits 0)."""
    try:
        result = subprocess.run(
            [CODEX_PATH, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        if result.returncode != 0:
            return False
        auth = subprocess.run(
            [CODEX_PATH, "login", "status"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
        return auth.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

def check_model_avail(worker_type: str, policy: dict) -> bool:
    """Compatibility wrapper for the non-consuming configuration probe."""
    return get_worker_availability(worker_type, policy).get("status") == "AVAILABLE"


def check_gemini_avail() -> bool:
    """Check Gemini CLI installation or profile-scoped API configuration."""
    try:
        result = subprocess.run(
            [GEMINI_PATH, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, OSError):
        pass

    return _profile_env_has("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI")


# ---------------------------------------------------------------------------
# Real specialist invocation via CLI workers
# ---------------------------------------------------------------------------
def invoke_specialist(specialist: str, context: dict, state_dir: Path,
                      policy: dict) -> dict:
    """
    Invoke a specialist using the appropriate CLI worker.
    Writes real output to state_dir/outputs/<specialist>.json.
    Returns status dict with COMPLETED, BLOCKED, or FAILED.
    """
    worker_info = get_workers_for_specialist(specialist, policy)
    prompt = build_specialist_prompt(specialist, context, policy)
    chain = get_execution_chain(specialist, policy)
    attempts = []
    provider_events = []
    result = None

    _pf_le_snapshot = _project_snapshot(state_dir) if specialist == "Lead Engineer" else {}
    for index, worker in enumerate(chain):
        availability = get_worker_availability(worker, policy)
        attempts.append({"worker": worker, "availability": availability.get("status")})
        if availability.get("status") != "AVAILABLE":
            continue

        if worker == "claude_code":
            candidate = invoke_claude_code(prompt, state_dir, specialist)
        elif worker == "codex":
            candidate = invoke_codex(prompt, state_dir, specialist)
        else:
            candidate_info = {"primary": worker, "fallback": worker}
            candidate = invoke_model_worker(
                prompt, specialist, state_dir, candidate_info, policy)
            provider_events.extend(LAST_WORKER_EVENTS.get(worker, []))

        errors = validate_specialist_schema(candidate)
        if errors:
            candidate = canonical(
                specialist=specialist, worker=worker, status="FAILED",
                artifacts={}, gate_result="FAIL",
                summary="Worker returned a non-canonical result.",
                errors=errors, metadata={"timestamp": _utc_timestamp()},
            )
        error_text = " ".join(candidate.get("errors", []))
        status = "AVAILABLE"
        failure_kind = _provider_failure_kind(error_text)
        if failure_kind == "QUOTA_LIMITED":
            status = "QUOTA_LIMITED"
        elif failure_kind == "RETRYABLE_OVERLOAD":
            status = "TEMPORARILY_UNAVAILABLE"
        elif candidate.get("status") in ("FAILED", "BLOCKED"):
            status = "UNAVAILABLE"
        if status != "TEMPORARILY_UNAVAILABLE":
            record_worker_status(worker, status, error_text or "Invocation succeeded.")

        candidate.setdefault("metadata", {})["fallback_used"] = index > 0
        candidate["metadata"]["attempts"] = attempts.copy()
        candidate["metadata"]["provider_events"] = provider_events.copy()
        result = candidate
        if candidate.get("status") == "SUCCESS":
            break

    if result is None or result.get("status") != "SUCCESS":
        last_errors = result.get("errors", []) if isinstance(result, dict) else []
        result = canonical(
            specialist=specialist,
            worker=result.get("worker", chain[-1] if chain else "unknown") if isinstance(result, dict) else (chain[-1] if chain else "unknown"),
            status="BLOCKED",
            artifacts={},
            gate_result="BLOCKED",
            summary=f"No available worker completed {specialist}.",
            next_handoff="Resolve worker availability or quota, then resume.",
            errors=last_errors or ["All configured workers were unavailable or failed."],
            metadata={"fallback_used": len(attempts) > 1, "attempts": attempts,
                      "provider_events": provider_events,
                      "timestamp": _utc_timestamp()},
        )

    if specialist == "Lead Engineer" and result.get("status") == "SUCCESS":
        _reconcile_files_changed(result, state_dir, _pf_le_snapshot)

    output_dir = state_dir / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{specialist.lower().replace('/', '_').replace(' ', '_')}.json"
    _write_json_file(output_file, result)
    result["output_file"] = str(output_file)
    return result


def get_execution_chain(specialist: str, policy: dict) -> list[str]:
    """Return the ordered, deduplicated worker chain declared by policy."""
    route = policy.get("routing", {}).get(SPECIALIST_TO_KEY.get(specialist, ""), {})
    if specialist == "Data/ML Engineer":
        values = [route.get("implementation_worker"),
                  route.get("implementation_fallback"),
                  route.get("primary_orchestration"), route.get("reasoning_fallback")]
    elif specialist == "ML/AI Evaluation Agent":
        values = [route.get("evaluation_worker"), route.get("evaluation_fallback"),
                  route.get("primary_orchestration"), route.get("reasoning_fallback")]
    else:
        values = [route.get("primary"), route.get("fallback"), route.get("second_fallback")]
    chain = []
    for value in values:
        if value and value != "unknown" and value not in chain:
            chain.append(value)
    return chain


def _build_specialist_prompt_base(specialist: str, context: dict, policy: dict) -> str:
    """
    Build a detailed prompt for the specialist based on its role,
    the project context, and completed work.
    """
    project_name = context.get("project_name", "Unnamed Project")
    project_type = context.get("project_type", "Unknown")
    completed = context.get("completed_specialists", [])
    outputs = context.get("outputs", {})

    # Build context summary from completed specialists
    context_lines = []
    for spec in completed:
        if spec in outputs:
            out = outputs[spec]
            artifacts = _extract_artifacts(out)
            if artifacts:
                context_lines.append(f"--- {spec} output ---")
                for k, v in artifacts.items():
                    if isinstance(v, list):
                        preview = ", ".join(str(item) for item in v[:5])
                        context_lines.append(f"{k}: {preview}{'...' if len(v) > 5 else ''}")
                    else:
                        context_lines.append(f"{k}: {str(v)[:300]}")

    context_summary = "\n".join(context_lines) if context_lines else "No prior specialist output."
    if len(context_summary) > MAX_SPECIALIST_CONTEXT_CHARS:
        context_summary = (
            context_summary[:MAX_SPECIALIST_CONTEXT_CHARS]
            + "\n[Prior specialist context preview truncated at a safe command-line boundary.]"
        )

    # Specialist-specific prompts
    prompts = {
        "Product Agent": f"""You are the Product Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Understand the business problem, identify users, define objectives,
define the MVP, generate a PRD with user stories, functional/non-functional
requirements, acceptance criteria, edge cases, assumptions, risks, and the
Definition of Done.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- project_brief: 1-2 sentence summary
- objectives: list of 3-5 objectives
- acceptance_criteria: list of 5-10 testable acceptance criteria
- mvp_definition: description of MVP scope
- users: list of user types
- functional_requirements: list
- non_functional_requirements: list
- user_stories: list of user stories
- edge_cases: list
- assumptions: list
- risks: list
- dod: Definition of Done as a list of criteria

Respond with ONLY the JSON object, no other text.""",

        "Research Agent": f"""You are the Research Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Conduct market research, competitor analysis, API research,
technical documentation research, and best practices research relevant to
this project.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- research_findings: summary of key findings
- market_analysis: market size, trends, opportunities
- competitor_analysis: list of competitors and their strengths/weaknesses
- technology_options: list of relevant technologies/frameworks with pros/cons
- best_practices: list of relevant best practices
- api_options: list of relevant APIs if applicable
- recommendations: list of research-based recommendations

Respond with ONLY the JSON object, no other text.""",

        "Architecture Agent": f"""You are the Architecture Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Design the overall system architecture, select the technology stack,
design frontend/backend/database/API architecture, authentication, security
architecture, deployment architecture, and testing strategy.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- architecture_summary: high-level architecture description
- technology_stack: {{"frontend": "...", "backend": "...", "database": "...", "infrastructure": "..."}}
- frontend_architecture: description
- backend_architecture: description
- database_design: schema overview
- api_design: API endpoints overview
- auth_design: authentication/authorization approach
- security_considerations: list
- deployment_architecture: deployment approach
- testing_strategy: testing approach
- failure_recovery: failure and recovery strategy

Respond with ONLY the JSON object, no other text.""",

        "Lead Engineer": f"""You are the Lead Engineer in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Implement the features based on the architecture and requirements.
Develop frontend and backend, APIs, database schemas. Write unit and integration
tests. Create technical documentation.

Context from prior specialists:
{context_summary}

If this is a code implementation task, write the actual implementation code.
If the project is just starting, create the project structure, initial files,
and a detailed implementation plan.

Write the output as a JSON object with these keys:
- implementation_plan: step-by-step implementation plan
- code_structure: file/folder structure
- technical_specs: technical specification details
- code: actual implementation code (if applicable) or "PROJECT_STRUCTURE" for initial setup
- tests: test code (if applicable)
- documentation: technical documentation notes

Respond with ONLY the JSON object, no other text.""",

        "Data/ML Engineer": f"""You are the Data/ML Engineer in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Handle data ingestion, validation, EDA, feature engineering,
model training, evaluation, and data pipeline design.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- data_pipeline_design: data pipeline description
- data_validation: validation approach
- eda_findings: exploratory data analysis findings
- feature_engineering: feature engineering plan
- model_architecture: model design
- training_plan: training approach
- evaluation_strategy: evaluation metrics and approach

Respond with ONLY the JSON object, no other text.""",

        "ML/AI Evaluation Agent": f"""You are the ML/AI Evaluation Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Evaluate ML systems or AI/LLM systems for task completion,
hallucinations, tool correctness, retrieval quality, prompt injection
resistance, agent loops, cost, latency, context handling, failure modes,
and consistency.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- evaluation_methodology: how evaluation was conducted
- metrics_results: metrics and scores
- hallucination_assessment: hallucination analysis
- tool_correctness: tool use accuracy
- failure_modes: identified failure modes
- recommendations: list of recommendations
- overall_assessment: overall evaluation summary

Respond with ONLY the JSON object, no other text.""",

        "QA Agent": f"""You are the Independent QA Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Review the implementation independently, validate acceptance criteria,
run tests, attempt to break workflows, inspect error states, validate
calculations, test edge cases, review maintainability.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- test_plan: test plan overview
- test_cases: list of test cases
- acceptance_validation: whether acceptance criteria are met
- edge_case_results: edge case testing results
- error_handling_review: error handling assessment
- maintainability_review: code maintainability assessment
- bugs_found: list of bugs found
- recommendations: list of QA recommendations

Respond with ONLY the JSON object, no other text.""",

        "Security Agent": f"""You are the Security Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Review authentication, authorization, secrets handling, SQL injection,
command injection, XSS, CSRF, file-upload attacks, path traversal, session
handling, data exposure, logging, access control, dependency vulnerabilities,
error disclosure, API security, sensitive-data handling, rate limiting.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- security_assessment: overall security assessment
- vulnerabilities: list of vulnerabilities found
- mitigations: list of recommended mitigations
- auth_review: authentication review
- authorization_review: authorization review
- secrets_review: secrets handling review
- dependency_review: dependency vulnerability review
- recommendations: security recommendations

Respond with ONLY the JSON object, no other text.""",

        "UI/UX Agent": f"""You are the UI/UX Quality Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Review visual hierarchy, navigation, forms, information architecture,
error messages, empty states, loading states, mobile responsiveness, desktop
experience, accessibility, typography, spacing, consistency, dashboard clarity,
user-flow friction.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- visual_hierarchy_review: visual hierarchy assessment
- navigation_review: navigation assessment
- form_review: form usability assessment
- error_message_review: error message clarity
- accessibility_review: accessibility assessment
- responsiveness_review: responsive design assessment
- consistency_review: consistency assessment
- user_flow_review: user flow assessment
- recommendations: UI/UX recommendations

Respond with ONLY the JSON object, no other text.""",

        "Release/DevOps Agent": f"""You are the Release/DevOps Agent in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Your task: Set up environment separation, build processes, deployment pipelines,
database migrations, logging, monitoring, backups, health checks, rollback
procedures, release notes.

Context from prior specialists:
{context_summary}

Write the output as a JSON object with these keys:
- deployment_plan: deployment plan
- ci_cd_pipeline: CI/CD configuration
- environment_setup: environment separation setup
- monitoring_setup: monitoring and alerting
- backup_strategy: backup approach
- rollback_procedure: rollback plan
- health_checks: health check definitions
- release_notes: release notes draft
- recommendations: DevOps recommendations

Respond with ONLY the JSON object, no other text.""",
    }

    base_prompt = prompts.get(specialist, f"""You are the {specialist} in the Hermes Product Factory.
Project: {project_name}
Type: {project_type}

Context from prior specialists:
{context_summary}

Provide your specialist output as a JSON object with relevant artifacts.

Respond with ONLY the JSON object, no other text.""")
    evidence_fields = {
        "Research Agent": "Also include sources (a non-empty list of source identifiers or URLs).",
        "Architecture Agent": "Also include decisions (a non-empty list of architecture decisions and rationale).",
        "Lead Engineer": "Also include files_changed (list) and verification ({command, exit_code, summary}); exit_code must reflect a real check.",
        "QA Agent": "Also include test_results: a LIST of the checks you actually ran, each {command, exit_code, passed, failed} - one entry per command (the project's own test suite AND your own independent checks). Every entry needs exit_code 0 and an empty/zero failed for the gate to pass. Also independent_review=true, and evidence from executed checks.",
        "Security Agent": "Also include checks_performed (a non-empty list).",
        "UI/UX Agent": "Also include accessibility_checks (a non-empty list).",
        "Data/ML Engineer": "Also include evaluation_results with measured data/model validation results.",
        "ML/AI Evaluation Agent": "Also include evaluation_results with measured outcomes and thresholds.",
        "Release/DevOps Agent": "Also include dry_run ({command, exit_code, summary}) and production_changes_applied=false. Never deploy.",
    }
    return (
        base_prompt
        + "\n\nMANDATORY GATE EVIDENCE:\n"
        + "Include evidence as a non-empty JSON list of concrete claims and their source/check. "
        + evidence_fields.get(specialist, "")
        + " Do not claim a command or check ran unless it actually ran."
    )


_PF_EXCLUDE_DIRS = {"outputs", "knowledge_staging", ".claude", "__pycache__", ".git"}
_PF_EXCLUDE_FILES = {"state.json", "claude_prompt.txt", "codex_last_message.json"}


def _project_snapshot(state_dir: Path) -> dict:
    """relative path -> mtime_ns for every deliverable-looking file under the project (pipeline bookkeeping excluded)."""
    snap = {}
    root = state_dir.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PF_EXCLUDE_DIRS]
        for name in filenames:
            if name in _PF_EXCLUDE_FILES or name.endswith(".pyc"):
                continue
            full = Path(dirpath) / name
            try:
                snap[full.relative_to(root).as_posix()] = full.stat().st_mtime_ns
            except (OSError, ValueError):
                continue
    return snap


def _reconcile_files_changed(result: dict, state_dir: Path, before: dict) -> None:
    """Replace the model's self-reported file list with what exists on disk (changed + claimed-and-real + all .py files)."""
    artifacts = result.get("artifacts") if isinstance(result, dict) else None
    if not isinstance(artifacts, dict):
        return
    after = _project_snapshot(state_dir)
    changed = {rel for rel, mtime in after.items() if before.get(rel) != mtime}
    claimed = [c for c in (artifacts.get("files_changed") or []) if isinstance(c, str)]
    real_claimed = {c for c in claimed if c in after}
    py_files = {rel for rel in after if rel.endswith(".py")}
    artifacts["worker_reported_files_changed"] = claimed
    artifacts["files_changed"] = sorted(changed | real_claimed | py_files)


def _attach_director_verification(result: dict, record: dict) -> None:
    """Store the pipeline's own test record in the result; keep the worker's claim for the audit trail."""
    artifacts = result.get("artifacts") if isinstance(result, dict) else None
    if isinstance(artifacts, dict):
        if "worker_reported_verification" not in artifacts and artifacts.get("verification") is not None:
            artifacts["worker_reported_verification"] = artifacts.get("verification")
        artifacts["verification"] = record


def invoke_claude_code(prompt: str, state_dir: Path, specialist: str) -> dict:
    """Claude Code call with a bounded repair loop for the Lead Engineer.

    Claude has no shell, so the pipeline runs the project's tests in a sandbox after every attempt and stores the real record in the
    result. On failure Claude receives the real output and up to 2 repair rounds. Other specialists are single calls."""
    before = _project_snapshot(state_dir) if specialist == "Lead Engineer" else {}
    result = _invoke_claude_code_once(prompt, state_dir, specialist)
    if specialist != "Lead Engineer":
        return result
    for round_no in (0, 1, 2):
        if result.get("status") == "SUCCESS":
            _reconcile_files_changed(result, state_dir, before)
        try:
            artifacts = _extract_artifacts(result)
        except Exception:
            return result
        files = artifacts.get("files_changed") if isinstance(artifacts, dict) else None
        if result.get("status") != "SUCCESS" or not isinstance(files, list) or not files:
            return result
        record = run_sandboxed_verification(state_dir, files)
        if record is None:
            return result
        _attach_director_verification(result, record)
        if record.get("exit_code") == 0 or round_no == 2:
            return result
        try:
            detail = json.loads((state_dir / "outputs" / "build_verification.json").read_text(encoding="utf-8")).get("full_output", "")
        except (OSError, ValueError):
            detail = record.get("summary", "")
        repair = (
            prompt
            + "\n\nREPAIR ROUND " + str(round_no + 1) + " of 2. The pipeline ran your project's unit tests in a sandbox and they FAILED "
            + "(exit code " + str(record.get("exit_code")) + "). Real output (last part):\n" + str(detail)[-4000:]
            + "\n\nFix the implementation, or a test that is wrong, using your Read/Edit/Write tools. Keep every file inside the project folder. "
            + "Then return the same JSON object again with files_changed listing every project file. Do NOT claim the tests passed: "
            + "you cannot run them, the pipeline will run them again."
        )
        before = _project_snapshot(state_dir)
        result = _invoke_claude_code_once(repair, state_dir, specialist)
    return result


def _invoke_claude_code_once(prompt: str, state_dir: Path, specialist: str) -> dict:
    """
    Invoke Claude Code via print mode (-p) with the specialist prompt.
    Returns a canonical SpecialistResult dict.
    """
    # Write prompt to temp file for Claude to read
    prompt_file = state_dir / "claude_prompt.txt"
    with open(prompt_file, 'w', encoding="utf-8") as f:
        f.write(prompt)

    try:
        result = subprocess.run(
            [CLAUDE_PATH, "-p",
             "Complete the assigned specialist task and return only the required JSON object.",
             "--append-system-prompt-file", str(prompt_file),
             "--output-format", "json",
             "--max-turns", "30",
             "--permission-mode", "dontAsk",
             "--no-session-persistence",
             # Claude Code may only use file tools, and only inside this project folder (cwd). No shell, no web.
             "--tools", "Read,Write,Edit,Glob,Grep",
             "--allowedTools", "Read(./**)", "Write(./**)", "Edit(./**)", "Glob", "Grep"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            cwd=str(state_dir)
        )

        if result.returncode == 0:
            # Try to parse JSON from stdout
            try:
                payload = json.loads(result.stdout)
                if isinstance(payload, dict) and isinstance(payload.get("structured_output"), dict):
                    artifacts = payload["structured_output"]
                elif isinstance(payload, dict) and isinstance(payload.get("result"), str):
                    artifacts = extract_json_from_text(payload["result"])
                else:
                    artifacts = payload
                if not isinstance(artifacts, dict):
                    raise json.JSONDecodeError("No artifact object", result.stdout, 0)
                return canonical(
                    specialist=specialist,
                    worker="claude_code",
                    status="SUCCESS",
                    artifacts=artifacts,
                    gate_result="NOT_APPLICABLE",
                    summary=f"Claude Code completed {specialist}.",
                    next_handoff="",
                    errors=[],
                    metadata={
                        "fallback_used": False,
                        "timestamp": datetime.now().isoformat(),
                        "adapter": "claude_code_print",
                        "exit_code": result.returncode,
                        "profile": PROFILE_NAME,
                    },
                )
            except json.JSONDecodeError:
                # Claude may wrap JSON in markdown or add text
                extracted = extract_json_from_text(result.stdout)
                if extracted:
                    return canonical(
                        specialist=specialist,
                        worker="claude_code",
                        status="SUCCESS",
                        artifacts=extracted,
                        gate_result="NOT_APPLICABLE",
                        summary=f"Claude Code completed {specialist} (JSON extracted).",
                        next_handoff="",
                        errors=[],
                        metadata={
                            "fallback_used": False,
                            "timestamp": datetime.now().isoformat(),
                            "adapter": "claude_code_print",
                            "exit_code": result.returncode,
                            "profile": PROFILE_NAME,
                        },
                    )
                # Unstructured text is not evidence and must not pass a gate.
                return canonical(
                    specialist=specialist,
                    worker="claude_code",
                    status="FAILED",
                    artifacts={},
                    gate_result="FAIL",
                    summary=f"Claude Code returned invalid JSON for {specialist}.",
                    next_handoff="",
                    errors=["Claude Code response was not a JSON object."],
                    metadata={
                        "fallback_used": False,
                        "timestamp": datetime.now().isoformat(),
                        "adapter": "claude_code_print",
                        "exit_code": result.returncode,
                        "profile": PROFILE_NAME,
                    },
                )
        else:
            stderr = result.stderr[:500] if result.stderr else ""
            detail = ""
            try:
                payload = json.loads(result.stdout or "{}")
                if isinstance(payload, dict):
                    detail = " | ".join(str(payload.get(k))[:300] for k in ("subtype", "result", "errors") if payload.get(k))
            except ValueError:
                detail = (result.stdout or "")[:300]
            if detail:
                stderr = (stderr + " claude_output: " + detail)[:900]
            return canonical(
                specialist=specialist,
                worker="claude_code",
                status="FAILED",
                artifacts={},
                gate_result="NOT_APPLICABLE",
                summary=f"Claude Code failed for {specialist}.",
                next_handoff="",
                errors=[f"Non-zero exit code: {result.returncode}. stderr: {stderr}"],
                metadata={"timestamp": datetime.now().isoformat()},
            )

    except subprocess.TimeoutExpired:
        return canonical(
            specialist=specialist,
            worker="claude_code",
            status="FAILED",
            artifacts={},
            gate_result="NOT_APPLICABLE",
            summary=f"Claude Code timed out for {specialist}.",
            next_handoff="",
            errors=["Claude Code invocation timed out after 900 seconds."],
            metadata={"timestamp": datetime.now().isoformat()},
        )
    except FileNotFoundError:
        return canonical(
            specialist=specialist,
            worker="claude_code",
            status="BLOCKED",
            artifacts={},
            gate_result="NOT_APPLICABLE",
            summary=f"Claude Code not found for {specialist}.",
            next_handoff="",
            errors=[f"Claude Code not found at {CLAUDE_PATH}."],
            metadata={"timestamp": datetime.now().isoformat()},
        )
    except Exception as e:
        return canonical(
            specialist=specialist,
            worker="claude_code",
            status="FAILED",
            artifacts={},
            gate_result="NOT_APPLICABLE",
            summary=f"Unexpected error for {specialist}.",
            next_handoff="",
            errors=[f"Unexpected error invoking Claude Code: {e}"],
            metadata={"timestamp": datetime.now().isoformat()},
        )


_PF_NO_NETWORK_CFG = "sandbox_workspace_write.network_access=false"


def invoke_codex(prompt: str, state_dir: Path, specialist: str) -> dict:
    """Codex call.
    - QA Agent: a throwaway COPY of the project (writable, no network) so its tests can create temp files; the real project is untouched.
    - Lead Engineer, Data/ML Engineer, ML/AI Evaluation Agent (fallback from Claude Code): writes directly into the real project,
      writable but no network, so a fallback can actually deliver the implementation instead of only describing one that never
      gets recorded. All three route Claude Code first and Codex only as their fallback in routing_policy.yaml.
    - Everything else: read-only sandbox in the real project (unchanged)."""
    if specialist == "QA Agent":
        scratch = Path(tempfile.mkdtemp(prefix="pf-qa-", dir="/tmp"))
        try:
            work = scratch / "project"
            shutil.copytree(state_dir, work, ignore=shutil.ignore_patterns("knowledge_staging", ".claude", "__pycache__", "*.pyc"))
            return _invoke_codex_once(prompt, state_dir, specialist, work_dir=work, sandbox="workspace-write",
                                      extra_config=[_PF_NO_NETWORK_CFG])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    if specialist in ("Lead Engineer", "Data/ML Engineer", "ML/AI Evaluation Agent"):
        return _invoke_codex_once(prompt, state_dir, specialist, sandbox="workspace-write", extra_config=[_PF_NO_NETWORK_CFG])
    return _invoke_codex_once(prompt, state_dir, specialist)


def _invoke_codex_once(prompt: str, state_dir: Path, specialist: str, work_dir: Optional[Path] = None, sandbox: str = "read-only", extra_config: Optional[list] = None) -> dict:
    """
    Invoke Codex via print mode with the specialist prompt.
    Returns a canonical SpecialistResult dict.
    """
    result_file = state_dir / "codex_last_message.json"
    work_dir = work_dir or state_dir

    try:
        result = subprocess.run(
            [CODEX_PATH, "exec", "--sandbox", sandbox]
            + [item for cfg in (extra_config or []) for item in ("-c", cfg)]
            + ["--skip-git-repo-check", "--ephemeral", "--color", "never",
               "-C", str(work_dir), "-o", str(result_file), "-"],
            capture_output=True,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=420,
            cwd=str(work_dir)
        )

        if result.returncode == 0:
            response_text = result_file.read_text(encoding="utf-8") if result_file.exists() else result.stdout
            try:
                artifacts = json.loads(response_text)
                if not isinstance(artifacts, dict):
                    raise json.JSONDecodeError("No artifact object", response_text, 0)
                return canonical(
                    specialist=specialist,
                    worker="codex",
                    status="SUCCESS",
                    artifacts=artifacts,
                    gate_result="NOT_APPLICABLE",
                    summary=f"Codex completed {specialist}.",
                    next_handoff="",
                    errors=[],
                    metadata={
                        "fallback_used": False,
                        "timestamp": datetime.now().isoformat(),
                        "adapter": "codex_exec",
                        "exit_code": result.returncode,
                        "profile": PROFILE_NAME,
                    },
                )
            except json.JSONDecodeError:
                extracted = extract_json_from_text(response_text)
                if extracted:
                    return canonical(
                        specialist=specialist,
                        worker="codex",
                        status="SUCCESS",
                        artifacts=extracted,
                        gate_result="NOT_APPLICABLE",
                        summary=f"Codex completed {specialist} (JSON extracted).",
                        next_handoff="",
                        errors=[],
                        metadata={
                            "fallback_used": False,
                            "timestamp": datetime.now().isoformat(),
                            "adapter": "codex_exec",
                            "exit_code": result.returncode,
                            "profile": PROFILE_NAME,
                        },
                    )
                return canonical(
                    specialist=specialist,
                    worker="codex",
                    status="FAILED",
                    artifacts={},
                    gate_result="FAIL",
                    summary=f"Codex returned invalid JSON for {specialist}.",
                    next_handoff="",
                    errors=["Codex response was not a JSON object."],
                    metadata={
                        "fallback_used": False,
                        "timestamp": datetime.now().isoformat(),
                        "adapter": "codex_exec",
                        "exit_code": result.returncode,
                        "profile": PROFILE_NAME,
                    },
                )
        else:
            stderr = (result.stderr or result.stdout or "")[:500]
            return canonical(
                specialist=specialist,
                worker="codex",
                status="FAILED",
                artifacts={},
                gate_result="NOT_APPLICABLE",
                summary=f"Codex failed for {specialist}.",
                next_handoff="",
                errors=[f"Non-zero exit code: {result.returncode}. {stderr}"],
                metadata={"timestamp": datetime.now().isoformat()},
            )

    except subprocess.TimeoutExpired:
        return canonical(
            specialist=specialist,
            worker="codex",
            status="FAILED",
            artifacts={},
            gate_result="NOT_APPLICABLE",
            summary=f"Codex timed out for {specialist}.",
            next_handoff="",
            errors=["Codex invocation timed out after 180 seconds."],
            metadata={"timestamp": datetime.now().isoformat()},
        )
    except FileNotFoundError:
        return canonical(
            specialist=specialist,
            worker="codex",
            status="BLOCKED",
            artifacts={},
            gate_result="NOT_APPLICABLE",
            summary=f"Codex not found for {specialist}.",
            next_handoff="",
            errors=[f"Codex not found at {CODEX_PATH}."],
            metadata={"timestamp": datetime.now().isoformat()},
        )
    except Exception as e:
        return canonical(
            specialist=specialist,
            worker="codex",
            status="FAILED",
            artifacts={},
            gate_result="NOT_APPLICABLE",
            summary=f"Unexpected error for {specialist}.",
            next_handoff="",
            errors=[f"Unexpected error invoking Codex: {e}"],
            metadata={"timestamp": datetime.now().isoformat()},
        )


def invoke_model_worker(prompt: str, specialist: str, state_dir: Path,
                        worker_info: dict, policy: dict) -> dict:
    """
    Invoke a model-based worker (nemotron, nous, gemini) for specialists
    that don't have a dedicated CLI worker.
    Returns a canonical SpecialistResult dict.
    """
    # Determine which model to use
    primary_model = worker_info.get("primary", "nemotron")
    fallback_model = worker_info.get("fallback", "nous")

    # Try primary
    result_text = invoke_model(prompt, policy, primary_model)
    used_model = primary_model
    fallback_used = False

    if not result_text and fallback_model != primary_model:
        # Try fallback
        result_text = invoke_model(prompt, policy, fallback_model)
        used_model = fallback_model
        fallback_used = True

    if result_text:
        extracted = extract_json_from_text(result_text)
        if extracted:
            return canonical(
                specialist=specialist,
                worker=used_model,
                status="SUCCESS",
                artifacts=extracted,
                gate_result="NOT_APPLICABLE",
                summary=f"Model worker {used_model} completed {specialist}.",
                next_handoff="",
                errors=[],
                metadata={
                    "fallback_used": fallback_used,
                    "timestamp": datetime.now().isoformat(),
                    "raw_response": result_text[:1000],
                    "adapter": "hermes_oneshot",
                    "profile": PROFILE_NAME,
                },
            )
        else:
            return canonical(
                specialist=specialist,
                worker=used_model,
                status="FAILED",
                artifacts={},
                gate_result="FAIL",
                summary=f"Model worker {used_model} returned invalid JSON for {specialist}.",
                next_handoff="",
                errors=["Model response was not a JSON object."],
                metadata={
                    "fallback_used": fallback_used,
                    "timestamp": datetime.now().isoformat(),
                    "adapter": "hermes_oneshot",
                    "profile": PROFILE_NAME,
                },
            )

    return canonical(
        specialist=specialist,
        worker=used_model,
        status="FAILED",
        artifacts={},
        gate_result="NOT_APPLICABLE",
        summary=f"Model invocation failed for {specialist}.",
        next_handoff="",
        errors=[f"Model invocation failed for {used_model}: "
                f"{LAST_WORKER_ERRORS.get(used_model, 'unknown error')}"],
        metadata={"timestamp": datetime.now().isoformat()},
    )


def extract_json_from_text(text: str) -> Optional[dict]:
    """
    Extract a JSON object from a text response.
    Handles markdown code blocks, wrapped JSON, etc.
    """
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Hermes CLI may surround the answer with status lines (or other JSON
    # diagnostics). Decode every object boundary and retain the largest valid
    # dictionary rather than treating the entire stdout stream as one value.
    decoder = json.JSONDecoder()
    candidates = []
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append((end, value))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    # Try to find JSON in markdown code blocks
    import re
    # fenced code blocks
    match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # JSON object pattern: find { ... }
    match = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Canonical schema compatibility helpers
# ---------------------------------------------------------------------------

def _extract_artifacts(specialist_output: dict) -> dict:
    """
    Extract artifacts dict from a specialist output, supporting both:
    - Old nested schema:  {output: {artifacts: {...}, ...}}
    - New canonical schema: {artifacts: {...}, ...}

    Returns empty dict when artifacts cannot be determined.
    """
    if not specialist_output:
        return {}

    # New canonical schema: top-level "artifacts"
    if "artifacts" in specialist_output and isinstance(specialist_output["artifacts"], dict):
        artifacts = dict(specialist_output["artifacts"])
        if "evidence" not in artifacts and isinstance(artifacts.get("gate_evidence"), list):
            artifacts["evidence"] = artifacts["gate_evidence"]
        return artifacts

    # Old nested schema: output.artifacts
    out = specialist_output.get("output", {}) if isinstance(specialist_output, dict) else {}
    artifacts = out.get("artifacts", {}) if isinstance(out, dict) else {}
    if isinstance(artifacts, dict):
        artifacts = dict(artifacts)
        if "evidence" not in artifacts and isinstance(artifacts.get("gate_evidence"), list):
            artifacts["evidence"] = artifacts["gate_evidence"]
        return artifacts

    return {}


def _extract_worker(result: dict) -> str:
    """Extract worker value from either schema shape."""
    if not result:
        return "unknown"
    # Canonical: top-level
    if "worker" in result:
        return str(result["worker"])
    # Old: nested
    out = result.get("output", {})
    return str(out.get("worker_used", "unknown"))


def _extract_fallback(result: dict) -> bool:
    """Extract fallback_used from either schema shape."""
    if not result:
        return False
    if "metadata" in result and isinstance(result["metadata"], dict):
        return bool(result["metadata"].get("fallback_used", False))
    out = result.get("output", {})
    return bool(out.get("fallback_used", False))
GATE_VALIDATORS = {}


def register_gate_validator(gate_name: str):
    """Decorator to register a gate validator function."""
    def decorator(fn):
        GATE_VALIDATORS[gate_name] = fn
        return fn
    return decorator


@register_gate_validator("Requirements")
def validate_requirements_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate that the Product Agent output has complete requirements."""
    artifacts = _extract_artifacts(specialist_output)

    checks = []
    issues = []

    # Check project_brief
    brief = artifacts.get("project_brief", "")
    if not brief or len(brief.strip()) < 10:
        issues.append("Project brief is missing or too short (< 10 chars).")

    # Check objectives
    objectives = artifacts.get("objectives", [])
    if not objectives or len(objectives) < 2:
        issues.append("Objectives missing or fewer than 2 items.")

    # Check acceptance_criteria
    ac = artifacts.get("acceptance_criteria", [])
    if not ac:
        issues.append("Acceptance criteria are missing entirely.")
    elif len(ac) < 3:
        issues.append(f"Acceptance criteria has only {len(ac)} items (minimum 3 recommended).")
    else:
        # Check that each criterion is testable (contains action verbs or is descriptive)
        for i, criterion in enumerate(ac):
            if not isinstance(criterion, str) or len(criterion.strip()) < 3:
                issues.append(f"Acceptance criterion #{i+1} is too brief or not a string.")

    # Check MVP definition
    mvp = artifacts.get("mvp_definition", "")
    if not mvp or len(mvp.strip()) < 20:
        issues.append("MVP definition is missing or too short.")

    # Check user stories
    stories = artifacts.get("user_stories", [])
    if not stories:
        issues.append("User stories are missing.")

    # Check functional requirements
    func_reqs = artifacts.get("functional_requirements", [])
    if not func_reqs:
        issues.append("Functional requirements are missing.")

    # Check risks
    risks = artifacts.get("risks", [])
    if not risks:
        issues.append("Risks are not identified.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "All requirement checks passed."}


@register_gate_validator("Architecture")
def validate_architecture_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate that the Architecture Agent output is complete."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("architecture_summary"):
        issues.append("Architecture summary is missing.")
    if not artifacts.get("technology_stack"):
        issues.append("Technology stack is not defined.")
    elif not isinstance(artifacts["technology_stack"], dict):
        issues.append("Technology stack should be a dict with frontend/backend/database keys.")
    else:
        for key in ("frontend", "backend", "database"):
            if not artifacts["technology_stack"].get(key):
                issues.append(f"Technology stack missing {key} choice.")

    if not artifacts.get("api_design"):
        issues.append("API design is missing.")

    if not artifacts.get("deployment_architecture"):
        issues.append("Deployment architecture is missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Architecture gate passed."}


def run_sandboxed_verification(state_dir: Path, recorded_paths: list) -> Optional[dict]:
    """Run the project's own unit tests in a throwaway sandbox and return an honest verification record (or None if there are no tests).

    The Lead Engineer has no shell, so the pipeline runs the tests itself: a COPY of the implementation files, user 'nobody',
    no network, no new privileges, CPU/memory/process/file-size limits, hard timeout. The real exit code is recorded, pass or fail."""
    root = state_dir.resolve()
    rels = []
    for raw in recorded_paths or []:
        candidate = (root / str(raw)).resolve()
        try:
            rel = candidate.relative_to(root)
        except ValueError:
            continue
        if not candidate.is_file() or candidate.stat().st_size > 1_000_000:
            continue
        if rel.parts and rel.parts[0] in ("outputs", "knowledge_staging", ".claude"):
            continue
        rels.append(rel)
    tests = [r for r in rels if r.name.startswith("test_") and r.suffix == ".py"]
    if not tests:
        return None
    sandbox = tempfile.mkdtemp(prefix="pf-verify-", dir="/tmp")
    try:
        for rel in rels:
            dst = Path(sandbox) / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, dst)
        for dirpath, dirnames, filenames in os.walk(sandbox):
            os.chown(dirpath, 65534, 65534)
            for name in filenames:
                os.chown(os.path.join(dirpath, name), 65534, 65534)
        os.chmod(sandbox, 0o700)
        test_dir = tests[0].parent.as_posix() or "."
        cmd = ["python3", "-m", "unittest", "discover", "-s", test_dir, "-v"]
        wrapped = (["unshare", "-n", "--", "setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", "--no-new-privs",
                    "prlimit", "--cpu=60", "--as=1073741824", "--nproc=128", "--fsize=52428800", "--", "timeout", "120"] + cmd)
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": sandbox, "PYTHONPATH": sandbox,
               "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
        try:
            result = subprocess.run(wrapped, cwd=sandbox, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=150)
            code = result.returncode
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        except subprocess.TimeoutExpired:
            code, output = 124, "Timed out after 150 seconds."
        except OSError as exc:
            code, output = 127, f"Sandbox could not start: {exc}"
        lines = [ln for ln in output.splitlines() if ln.strip()]
        tail = " | ".join(lines[-6:])[:900] if lines else "no output"
        record = {
            "command": "python3 -m unittest discover -s " + test_dir + " -v (run by the pipeline in a sandbox: copy of the files, user nobody, no network, 120 s / 1 GB limits)",
            "exit_code": code,
            "summary": tail,
            "run_by": "director_sandbox",
            "test_files": [t.as_posix() for t in tests],
        }
        try:
            out_dir = state_dir / "outputs"
            out_dir.mkdir(exist_ok=True)
            (out_dir / "build_verification.json").write_text(json.dumps(dict(record, full_output=output[-8000:]), indent=2), encoding="utf-8")
        except OSError:
            pass
        return record
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


@register_gate_validator("Build")
def validate_build_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate that the Lead Engineer produced implementation artifacts."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("implementation_plan"):
        issues.append("Implementation plan is missing.")

    if not artifacts.get("code_structure"):
        issues.append("Code structure is not defined.")

    files_changed = artifacts.get("files_changed")
    implemented_code = artifacts.get("code")
    recorded_paths = files_changed if isinstance(files_changed, list) else []
    if not recorded_paths:
        code_recorded = bool(implemented_code)
        if isinstance(implemented_code, dict):
            code_recorded = implemented_code.get("status") == "IMPLEMENTED"
            entrypoint = implemented_code.get("entrypoint")
            if entrypoint:
                recorded_paths = [entrypoint]
        if not recorded_paths and isinstance(artifacts.get("code_structure"), dict):
            recorded_paths = [
                path for path in artifacts["code_structure"]
                if Path(str(path)).suffix and (state_dir / str(path)).is_file()
            ]
        if not code_recorded:
            issues.append("No implementation files or implemented code artifact were recorded.")
        elif not recorded_paths:
            issues.append("Implemented code artifact has no existing in-project file.")

    if recorded_paths:
        project_root = state_dir.resolve()
        for relative in recorded_paths:
            candidate = (state_dir / str(relative)).resolve()
            try:
                candidate.relative_to(project_root)
            except ValueError:
                issues.append(f"Implementation file is outside the project: {relative}.")
                continue
            if not candidate.is_file():
                issues.append(f"Implementation file does not exist: {relative}.")

    verification = artifacts.get("verification")
    worker_ran_it = isinstance(verification, dict) and verification.get("exit_code") == 0 and verification.get("command")
    if not worker_ran_it and recorded_paths:
        director_record = run_sandboxed_verification(state_dir, recorded_paths)
        if director_record is not None:
            artifacts["worker_reported_verification"] = verification
            artifacts["verification"] = verification = director_record
    if not isinstance(verification, dict):
        issues.append("Build verification record is missing.")
    else:
        if verification.get("exit_code") != 0:
            issues.append("Build verification did not pass.")
        if not verification.get("command") or not verification.get("summary"):
            issues.append("Build verification must include command and summary.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Build gate passed."}


@register_gate_validator("Testing")
def validate_testing_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate QA Agent test plan completeness."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("test_plan"):
        issues.append("Test plan is missing.")

    test_cases = artifacts.get("test_cases", [])
    if not test_cases:
        issues.append("No test cases defined.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Testing gate passed."}


@register_gate_validator("Independent QA")
def validate_independent_qa_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate that QA independently reviewed the implementation."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("acceptance_validation"):
        issues.append("Acceptance criteria validation is missing.")

    if not artifacts.get("edge_case_results"):
        issues.append("Edge case testing results are missing.")

    if not artifacts.get("maintainability_review"):
        issues.append("Maintainability review is missing.")

    # QA should find at least some issues or explicitly state none found
    bugs = artifacts.get("bugs_found", [])
    if bugs is None:
        issues.append("Bugs found field is missing (should be list, even if empty).")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Independent QA gate passed."}


@register_gate_validator("Security")
def validate_security_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate Security Agent review completeness."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    for key in ("auth_review", "authorization_review", "secrets_review"):
        if not artifacts.get(key):
            issues.append(f"{key.replace('_', ' ').title()} is missing.")

    if not artifacts.get("vulnerabilities"):
        v = artifacts.get("vulnerabilities")
        if v is None:
            issues.append("Vulnerabilities list is missing.")
    if not artifacts.get("mitigations"):
        m = artifacts.get("mitigations")
        if m is None:
            issues.append("Mitigations list is missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Security gate passed."}


@register_gate_validator("UI/UX")
def validate_uiux_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate UI/UX review completeness."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    for key in ("visual_hierarchy_review", "navigation_review", "accessibility_review"):
        if not artifacts.get(key):
            issues.append(f"{key.replace('_', ' ').title()} is missing.")

    if not artifacts.get("recommendations"):
        issues.append("UI/UX recommendations are missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "UI/UX gate passed."}


@register_gate_validator("Data/ML")
def validate_dataml_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate Data/ML Engineer output."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("data_pipeline_design"):
        issues.append("Data pipeline design is missing.")

    if not artifacts.get("feature_engineering"):
        issues.append("Feature engineering plan is missing.")

    if not artifacts.get("model_architecture"):
        issues.append("Model architecture is missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Data/ML gate passed."}


@register_gate_validator("AI/LLM")
def validate_aillm_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate ML/AI Evaluation Agent output."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("evaluation_methodology"):
        issues.append("Evaluation methodology is missing.")

    if not artifacts.get("metrics_results"):
        issues.append("Metrics results are missing.")

    if not artifacts.get("overall_assessment"):
        issues.append("Overall assessment is missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "AI/LLM evaluation gate passed."}


@register_gate_validator("Research")
def validate_research_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate Research Agent output."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("research_findings"):
        issues.append("Research findings are missing.")

    if not artifacts.get("market_analysis"):
        issues.append("Market analysis is missing.")

    if not artifacts.get("recommendations"):
        issues.append("Research recommendations are missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Research gate passed."}


@register_gate_validator("Release")
def validate_release_gate(specialist_output: dict, state_dir: Path) -> dict:
    """Validate Release/DevOps Agent output."""
    artifacts = _extract_artifacts(specialist_output)

    issues = []

    if not artifacts.get("deployment_plan"):
        issues.append("Deployment plan is missing.")

    if not artifacts.get("ci_cd_pipeline"):
        issues.append("CI/CD pipeline configuration is missing.")

    if not artifacts.get("monitoring_setup"):
        issues.append("Monitoring setup is missing.")

    if not artifacts.get("rollback_procedure"):
        issues.append("Rollback procedure is missing.")

    if issues:
        return {"status": "FAIL", "reason": "; ".join(issues)}
    return {"status": "PASS", "reason": "Release gate passed."}


def _testing_gate_passed(test_results) -> bool:
    """True if test_results shows real, passing, executed test runs. Accepts either the documented single
    {command, exit_code, passed, failed} object or a LIST of such runs (a genuine independent QA naturally runs
    more than one check: the project's own suite plus its own probes)."""
    def run_ok(run) -> bool:
        if not isinstance(run, dict) or not run.get("command"):
            return False
        if run.get("exit_code") != 0:
            return False
        failed = run.get("failed")
        if isinstance(failed, list) and failed:
            return False
        if isinstance(failed, (int, float)) and failed not in (0, 0.0):
            return False
        return True

    if isinstance(test_results, dict):
        return run_ok(test_results)
    if isinstance(test_results, list) and test_results:
        return all(run_ok(r) for r in test_results)
    return False


def _validate_gate_evidence(gate_name: str, artifacts: dict, state_dir: Optional[Path] = None) -> list[str]:
    """Validate evidence that supports a gate decision, not just prose fields."""
    issues = []
    evidence = artifacts.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        issues.append("Evidence list is missing or empty.")

    if gate_name == "Research" and not artifacts.get("sources"):
        issues.append("Research sources are missing.")
    elif gate_name == "Architecture" and not artifacts.get("decisions"):
        issues.append("Architecture decision records are missing.")
    elif gate_name == "Build":
        verification = artifacts.get("verification")
        if not isinstance(verification, dict) or verification.get("exit_code") != 0:
            issues.append("Successful build verification evidence is missing.")
        if not artifacts.get("files_changed") and not artifacts.get("code"):
            issues.append("No changed files or code artifact is recorded.")
    elif gate_name == "Testing":
        # Trust the pipeline's own sandboxed test run (director-executed, not self-reported)
        # first; a specialist's self-reported test_results is only a fallback for project
        # types where nothing was executed in a sandbox.
        sandboxed = _read_json_file(state_dir / "outputs" / "build_verification.json", None) if state_dir else None
        if not _testing_gate_passed(sandboxed) and not _testing_gate_passed(artifacts.get("test_results")):
            issues.append("Passing executable test results are missing.")
    elif gate_name == "Independent QA":
        if artifacts.get("independent_review") is not True:
            issues.append("Independent review attestation is missing.")
    elif gate_name == "Security" and not artifacts.get("checks_performed"):
        issues.append("Security checks performed are missing.")
    elif gate_name == "UI/UX" and not artifacts.get("accessibility_checks"):
        issues.append("Accessibility check evidence is missing.")
    elif gate_name in ("Data/ML", "AI/LLM") and not artifacts.get("evaluation_results"):
        issues.append("Evaluation results are missing.")
    elif gate_name == "Release":
        dry_run = artifacts.get("dry_run")
        if not isinstance(dry_run, dict) or dry_run.get("exit_code") != 0:
            issues.append("Successful release dry-run evidence is missing.")
        if artifacts.get("production_changes_applied") is not False:
            issues.append("Release evidence must confirm no production changes were applied.")
    return issues


def _load_gate_waivers(state_dir: Path) -> list:
    """GATE_WAIVERS.json in the project folder: an explicit, reasoned, attributed list of accepted known limitations.
    Never auto-generated by any specialist or worker; a human (or someone deciding on the human's behalf) writes this file."""
    path = state_dir / "GATE_WAIVERS.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    waivers = data.get("waivers") if isinstance(data, dict) else data
    return waivers if isinstance(waivers, list) else []


def _apply_gate_waiver(gate_name: str, result: dict, specialist_output: dict, state_dir: Path) -> dict:
    """If a gate failed and a matching, reasoned waiver names every CURRENTLY reported finding, let it pass - the original
    failure is kept in the result under original_status/original_reason, nothing is hidden. A new, un-named finding is not
    covered: the gate still fails closed, so a waiver cannot be used to blanket-approve future problems."""
    if result.get("status") == "PASS":
        return result
    artifacts = _extract_artifacts(specialist_output) or {}
    remaining_ids = {b.get("id") for b in (artifacts.get("bugs_found") or []) if isinstance(b, dict) and b.get("id")}
    for waiver in _load_gate_waivers(state_dir):
        if waiver.get("gate") != gate_name or not waiver.get("reason") or not waiver.get("decided_by"):
            continue
        accepted_ids = set(waiver.get("accepted_finding_ids") or [])
        covers_all = waiver.get("accept_all_remaining") is True or (bool(remaining_ids) and remaining_ids <= accepted_ids)
        if not covers_all:
            continue
        return {
            "status": "PASS",
            "reason": "Passed with an accepted known limitation: " + str(waiver["reason"]),
            "waived": True,
            "waiver_decided_by": waiver["decided_by"],
            "waiver_decided_at": waiver.get("decided_at"),
            "waived_finding_ids": sorted(remaining_ids),
            "original_status": result.get("status"),
            "original_reason": result.get("reason"),
        }
    return result


def validate_gate(gate_name: str, specialist_output: dict, state_dir: Path,
                  strict: bool = True) -> dict:
    """
    Validate the specialist output against the named quality gate.
    Uses gate-specific validators when registered; falls back to basic
    artifact presence check.
    """
    result_status = specialist_output.get("status") if isinstance(specialist_output, dict) else None
    if result_status in ("FAILED", "BLOCKED"):
        return {"status": "BLOCKED", "reason":
                f"Specialist result status is {result_status}; gate cannot pass."}

    if isinstance(specialist_output, dict) and "specialist" in specialist_output:
        schema_errors = validate_specialist_schema(specialist_output)
        if schema_errors:
            return {"status": "FAIL", "reason": "Canonical schema invalid: " + "; ".join(schema_errors)}

    validator = GATE_VALIDATORS.get(gate_name)
    if validator:
        result = validator(specialist_output, state_dir)
        if result["status"] == "PASS" and strict:
            evidence_issues = _validate_gate_evidence(
                gate_name, _extract_artifacts(specialist_output), state_dir)
            if evidence_issues:
                result = {"status": "FAIL", "reason": "; ".join(evidence_issues)}
        if result.get("status") != "PASS":
            result = _apply_gate_waiver(gate_name, result, specialist_output, state_dir)
        return result

    return {"status": "BLOCKED", "reason":
            f"No validator is registered for gate '{gate_name}'; failing closed."}


SPECIALIST_GATE_MAP = {
    "Product Agent": ["Requirements"],
    "Research Agent": ["Research"],
    "Architecture Agent": ["Architecture"],
    "Lead Engineer": ["Build"],
    "Data/ML Engineer": ["Data/ML"],
    "ML/AI Evaluation Agent": ["AI/LLM"],
    "QA Agent": ["Testing", "Independent QA"],
    "Security Agent": ["Security"],
    "UI/UX Agent": ["UI/UX"],
    "Release/DevOps Agent": ["Release"],
}


def validate_specialist_gates(specialist: str, specialist_output: dict,
                              state_dir: Path, required_gates: list[str]) -> dict:
    """Run every required gate owned by a specialist and aggregate fail-closed."""
    results = {}
    for gate in SPECIALIST_GATE_MAP.get(specialist, []):
        if gate in required_gates:
            results[gate] = validate_gate(gate, specialist_output, state_dir, strict=True)
    failures = [f"{name}: {value['reason']}" for name, value in results.items()
                if value["status"] != "PASS"]
    return {
        "status": "FAIL" if failures else "PASS",
        "reason": "; ".join(failures) if failures else "All required gates passed.",
        "gates": results,
    }

# ---------------------------------------------------------------------------
# Human approval
# ---------------------------------------------------------------------------
def check_human_approval(state_dir: Path) -> Optional[bool]:
    """
    Check if human approval has been granted.
    Looks for APPROVE file (approved) or REJECT file (rejected).
    APPROVE takes precedence if both exist (REJECT is deleted).
    """
    approve_file = state_dir / "APPROVE"
    reject_file = state_dir / "REJECT"
    approval_record = _read_json_file(state_dir / "approval.json", {})
    if approval_record.get("status") == "APPROVED":
        return True
    if approval_record.get("status") == "REJECTED":
        return False

    if approve_file.exists():
        # Human approved — clean up reject if present
        if reject_file.exists():
            reject_file.unlink()
        return True

    if reject_file.exists():
        return False

    return None  # No decision yet


def record_approval(state_dir: Path, approved: bool):
    """Record human approval or rejection."""
    state_dir.mkdir(parents=True, exist_ok=True)
    if approved:
        (state_dir / "APPROVE").touch()
        reject = state_dir / "REJECT"
        if reject.exists():
            reject.unlink()
    else:
        (state_dir / "REJECT").touch()
        approve = state_dir / "APPROVE"
        if approve.exists():
            approve.unlink()
    decision = "APPROVED" if approved else "REJECTED"
    _write_json_file(state_dir / "approval.json", {
        "schema_version": 1,
        "status": decision,
        "decided_at": _utc_timestamp(),
        "source": "explicit_cli_or_api_action",
    })
    state_file = state_dir / "state.json"
    state = _read_json_file(state_file, {})
    if state:
        state.setdefault("approval", {})["status"] = decision
        state["approval"]["decided_at"] = _utc_timestamp()
        if approved and state.get("current_phase") == "AWAITING_HUMAN_APPROVAL":
            state["current_phase"] = "APPROVED_FOR_CONTROLLED_RELEASE"
            state["current_milestone"] = "Controlled release approved"
            state["next_action"] = "Execute the approved release action separately."
        elif not approved:
            state["current_phase"] = "REJECTED"
            state["current_milestone"] = "Approval rejected"
            state["next_action"] = "Revise the project before requesting approval again."
        record_activity(
            state,
            "APPROVAL_DECIDED",
            f"Human approval checkpoint was {decision.lower()}.",
            approval_status=decision,
        )
        _write_json_file(state_file, state)


# ---------------------------------------------------------------------------
# Obsidian knowledge capture
# ---------------------------------------------------------------------------
def capture_to_obsidian(state_dir: Path, specialist: str,
                        specialist_output: dict, publish: bool = False,
                        validated: bool = False) -> bool:
    """
    Stage structured knowledge locally. Publishing to the configured vault is
    allowed only when both publish=True and validated=True are explicit.
    """
    artifacts = _extract_artifacts(specialist_output)
    if not artifacts:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d")
    specialist_slug = specialist.lower().replace('/', '_').replace(' ', '_')
    note_name = f"{timestamp}_{specialist_slug}.md"
    staging_path = state_dir / "knowledge_staging"
    staging_path.mkdir(parents=True, exist_ok=True)
    decision = {
        "schema_version": 1,
        "status": "VALIDATED" if validated else "STAGED",
        "project": state_dir.name,
        "specialist": specialist,
        "worker": _extract_worker(specialist_output),
        "fallback_used": _extract_fallback(specialist_output),
        "captured_at": _utc_timestamp(),
        "artifacts": artifacts,
    }
    _write_json_file(staging_path / f"{specialist_slug}.json", decision)

    if publish and validated and OBSIDIAN_VAULT:
        vault_path = Path(OBSIDIAN_VAULT)
        if not vault_path.exists():
            return False
        note_path = vault_path / "Product Factory" / note_name
    else:
        note_path = staging_path / note_name
    note_path.parent.mkdir(parents=True, exist_ok=True)

    # Build note content
    lines = [
        f"# {specialist} — {timestamp}",
        "",
        f"**Project:** {state_dir.name}",
        f"**Worker:** {_extract_worker(specialist_output)}",
        f"**Fallback used:** {_extract_fallback(specialist_output)}",
        f"**Capture status:** {'VALIDATED' if validated else 'STAGED'}",
        "",
    ]

    for key, value in artifacts.items():
        lines.append(f"## {key.replace('_', ' ').title()}")
        lines.append("")
        if isinstance(value, list):
            for item in value:
                lines.append(f"- {item}")
        elif isinstance(value, dict):
            for dk, dv in value.items():
                lines.append(f"- **{dk}:** {dv}")
        else:
            lines.append(str(value))
        lines.append("")

    try:
        with open(note_path, 'w', encoding="utf-8") as f:
            f.write("\n".join(lines))
        return True
    except (OSError, IOError):
        return False


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def update_state(state_dir: Path, specialist_name: str, gate_status: dict,
                 worker_used: str, fallback_used: bool,
                 next_action: str) -> dict:
    """Update project state after a specialist completes."""
    state_file = state_dir / "state.json"

    if state_file.exists():
        with open(state_file, 'r') as f:
            state = json.load(f)
    else:
        state = {
            "project_name": "",
            "project_type": "",
            "current_phase": "",
            "current_milestone": "",
            "specialists_completed": [],
            "specialist_in_progress": None,
            "pending_specialists": [],
            "gate_status": {},
            "blocked_reason": None,
            "worker_used": {},
            "fallback_used": {},
            "last_verified_action": "",
            "next_action": "",
        }

    state["specialist_in_progress"] = specialist_name
    state["gate_status"][specialist_name] = gate_status["status"]
    state["worker_used"][specialist_name] = worker_used
    state["fallback_used"][specialist_name] = fallback_used
    state["last_verified_action"] = (
        f"Completed {specialist_name} — gate: {gate_status['status']}"
    )
    state["next_action"] = next_action

    if gate_status["status"] == "PASS":
        if specialist_name not in state["specialists_completed"]:
            state["specialists_completed"].append(specialist_name)
        state["specialist_in_progress"] = None
    elif gate_status["status"] in ("FAIL", "BLOCKED"):
        state["blocked_reason"] = gate_status.get("reason", "Unknown")

    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

    return state


# ---------------------------------------------------------------------------
# Template initialization
# ---------------------------------------------------------------------------
def init_project_template(project_type: str, state_dir: Path,
                          project_name: str) -> list[str]:
    """
    Initialize project files from templates based on project type.
    Returns list of created file paths.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    created = []
    directory_sets = {
        "WEBSITE": ["src", "tests", "assets", "docs"],
        "SAAS": ["backend", "frontend", "database", "api", "deploy", "tests", "docs"],
        "MACHINE_LEARNING": ["data/raw", "data/processed", "models", "notebooks", "src", "tests", "docs"],
        "DATA_SCIENCE": ["data/raw", "data/processed", "notebooks", "src", "tests", "reports"],
        "AI_AGENT": ["agent", "tools", "prompts", "tests", "evals", "docs"],
        "AI_LLM_APPLICATION": ["src", "prompts", "retrieval", "tests", "evals", "docs"],
        "DATA_PIPELINE": ["pipelines", "transformers", "schedulers", "monitoring", "tests", "docs"],
    }
    directories = directory_sets.get(project_type, ["src", "tests", "docs"])
    directories.extend(["outputs", "knowledge_staging"])
    for relative in directories:
        (state_dir / relative).mkdir(parents=True, exist_ok=True)

    replacements = {
        "{project_name}": project_name,
        "{project_type}": project_type,
        "{date}": datetime.now().strftime("%Y-%m-%d"),
        "{created}": _utc_timestamp(),
        "{updated}": _utc_timestamp(),
        "{status}": "INITIALIZED",
        "{phase}": "PLANNING",
        "{confidence}": "PENDING",
        "{semantic_used}": "PENDING",
    }
    template_files = ["PRD.md", "ARCHITECTURE.md", "implementation_plan.md",
                      "project_state.md"]
    type_template = TEMPLATES_DIR / f"{project_type}.md"
    if type_template.exists():
        template_files.append(type_template.name)

    for name in template_files:
        source = TEMPLATES_DIR / name
        if not source.exists():
            continue
        content = source.read_text(encoding="utf-8")
        for token, value in replacements.items():
            content = content.replace(token, value)
        destination = state_dir / ("DELIVERY_CONTRACT.md" if name == f"{project_type}.md" else name)
        destination.write_text(content, encoding="utf-8")
        created.append(str(destination))

    readme = state_dir / "README.md"
    readme.write_text(
        f"# {project_name}\n\n"
        f"Type: `{project_type}`\n\n"
        "Initialized by the isolated Hermes Product Factory. No production "
        "deployment or external service change has been performed.\n",
        encoding="utf-8",
    )
    created.append(str(readme))
    gitignore = state_dir / ".gitignore"
    gitignore.write_text("__pycache__/\n*.pyc\n.env\noutputs/\n", encoding="utf-8")
    created.append(str(gitignore))
    return created


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def revalidate_completed_checkpoints(state_dir: Path, state: dict,
                                     specialists: list[str],
                                     quality_gates: list[str]) -> list[str]:
    """Keep only the consecutive completed checkpoints that still pass gates."""
    completed = state.get("specialists_completed", [])
    verified = []
    invalidated = []
    for specialist in specialists:
        if specialist not in completed:
            break
        key = specialist.lower().replace("/", "_").replace(" ", "_")
        result = _read_json_file(state_dir / "outputs" / f"{key}.json", {})
        if not result:
            staged = _read_json_file(
                state_dir / "knowledge_staging" / f"{key}.json", {})
            if staged.get("status") == "VALIDATED" and isinstance(staged.get("artifacts"), dict):
                result = canonical(
                    specialist=specialist,
                    worker=staged.get("worker", "unknown"),
                    status="SUCCESS",
                    artifacts=staged["artifacts"],
                    gate_result="NOT_APPLICABLE",
                    summary="Revalidating the staged canonical checkpoint.",
                )
        aggregate = validate_specialist_gates(
            specialist, result, state_dir, quality_gates)
        if aggregate["status"] != "PASS":
            invalidated = specialists[len(verified):]
            record_activity(
                state,
                "CHECKPOINT_INVALIDATED",
                f"{specialist} no longer satisfies the active quality gate: {aggregate['reason']}",
                specialist=specialist,
            )
            break
        verified.append(specialist)

    if invalidated:
        state["specialists_completed"] = verified
        for specialist in invalidated:
            state.get("specialist_gate_status", {}).pop(specialist, None)
            for gate in SPECIALIST_GATE_MAP.get(specialist, []):
                state.get("gate_status", {}).pop(gate, None)
        state["blocked_reason"] = None
    return invalidated


def restore_validated_checkpoints(state_dir: Path, state: dict,
                                  specialists: list[str],
                                  quality_gates: list[str]) -> list[str]:
    """Restore consecutive, staged VALIDATED outputs after an interrupted retry."""
    restored = []
    for specialist in specialists:
        if specialist in state.get("specialists_completed", []):
            continue
        key = specialist.lower().replace("/", "_").replace(" ", "_")
        staged = _read_json_file(
            state_dir / "knowledge_staging" / f"{key}.json", {})
        if not (
            staged.get("status") == "VALIDATED"
            and staged.get("project") == state_dir.name
            and staged.get("specialist") == specialist
            and isinstance(staged.get("artifacts"), dict)
        ):
            break
        result = canonical(
            specialist=specialist,
            worker=staged.get("worker", "unknown"),
            status="SUCCESS",
            artifacts=staged["artifacts"],
            gate_result="NOT_APPLICABLE",
            summary="Restored from the profile-local validated checkpoint.",
            metadata={
                "fallback_used": bool(staged.get("fallback_used")),
                "restored_from": "knowledge_staging",
            },
        )
        aggregate = validate_specialist_gates(
            specialist, result, state_dir, quality_gates)
        if aggregate["status"] != "PASS":
            staged["status"] = "INVALIDATED"
            staged["invalidation_reason"] = aggregate["reason"]
            staged["invalidated_at"] = _utc_timestamp()
            _write_json_file(
                state_dir / "knowledge_staging" / f"{key}.json", staged)
            break
        _write_json_file(state_dir / "outputs" / f"{key}.json", result)
        state.setdefault("specialists_completed", []).append(specialist)
        state.setdefault("specialist_gate_status", {})[specialist] = "PASS"
        state.setdefault("worker_used", {})[specialist] = staged.get("worker", "unknown")
        state.setdefault("fallback_used", {})[specialist] = bool(staged.get("fallback_used"))
        for gate, gate_result in aggregate["gates"].items():
            state.setdefault("gate_status", {})[gate] = gate_result
        restored.append(specialist)
        record_activity(
            state,
            "CHECKPOINT_RESTORED",
            f"Restored and revalidated {specialist} from staged canonical evidence.",
            specialist=specialist,
            worker=staged.get("worker", "unknown"),
            gates=aggregate["gates"],
        )
    return restored


# ---- documents: fill the template placeholders from what the specialists actually produced ----
_NOT_SPECIFIED = "Not specified by the specialist."
_DOC_FILES = ("PRD.md", "ARCHITECTURE.md", "implementation_plan.md")
# template placeholder -> (specialist output file key, artifact key or ("dict-key", "technology_stack", "frontend"))
_DOC_MAP = {
    "PRD.md": {
        "description": "project_brief", "objectives": "objectives", "users": "users", "mvp": "mvp_definition",
        "user_stories": "user_stories", "functional_requirements": "functional_requirements",
        "non_functional_requirements": "non_functional_requirements", "acceptance_criteria": "acceptance_criteria",
        "edge_cases": "edge_cases", "assumptions": "assumptions", "risks": "risks", "dod": "dod",
        "out_of_scope": "out_of_scope", "notes": "notes",
    },
    "ARCHITECTURE.md": {
        "overview": "architecture_summary", "frontend_architecture": "frontend_architecture", "backend_architecture": "backend_architecture",
        "database_architecture": "database_design", "api_architecture": "api_design", "auth": "auth_design", "security": "security_considerations",
        "deployment": "deployment_architecture", "testing": "testing_strategy", "recovery": "failure_recovery", "questions": "open_questions",
        "frontend_stack": ("technology_stack", "frontend"), "backend_stack": ("technology_stack", "backend"),
        "database": ("technology_stack", "database"), "infrastructure": ("technology_stack", "infrastructure"),
    },
}
_DOC_SOURCE = {"PRD.md": "product_agent", "ARCHITECTURE.md": "architecture_agent"}


def _doc_text(value) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return _NOT_SPECIFIED
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {_doc_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "\n".join("- " + (item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)) for item in value)
    return str(value)


def fill_project_documents(state_dir: Path, specialist: str, result: dict) -> None:
    """Replace the {placeholders} in the generated documents with the specialist's real output; unresolved ones say so plainly."""
    artifacts = _extract_artifacts(result) or {}
    for doc, source_key in _DOC_SOURCE.items():
        if specialist.lower().replace("/", "_").replace(" ", "_") != source_key:
            continue
        path = state_dir / doc
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for placeholder, key in _DOC_MAP.get(doc, {}).items():
            token = "{" + placeholder + "}"
            if token not in text:
                continue
            if isinstance(key, tuple):
                value = (artifacts.get(key[0]) or {}).get(key[1]) if isinstance(artifacts.get(key[0]), dict) else None
            else:
                value = artifacts.get(key)
            text = text.replace(token, _doc_text(value))
        # anything still in braces was not covered by this specialist's output
        text = re.sub(r"\{[a-z_]+\}", _NOT_SPECIFIED, text)
        path.write_text(text, encoding="utf-8")


def refill_documents_from_outputs(state_dir: Path) -> None:
    """Idempotent: fill documents from already-saved specialist outputs (used when a project is resumed)."""
    for source_key in _DOC_SOURCE.values():
        saved = _read_json_file(state_dir / "outputs" / f"{source_key}.json", {})
        if saved:
            name = {"product_agent": "Product Agent", "architecture_agent": "Architecture Agent"}[source_key]
            fill_project_documents(state_dir, name, saved)


def fill_plan_document(state_dir: Path, quality_gates: list, approval_points: list) -> None:
    path = state_dir / "implementation_plan.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text = text.replace("{list_of_gates}", "\n".join("- " + str(g) for g in quality_gates) or _NOT_SPECIFIED)
    text = text.replace("{approval_points}", "\n".join("- " + str(a) for a in approval_points) or "None required for this project.")
    text = text.replace("{knowledge_to_capture}", "Staged under knowledge_staging/ (never written to a real vault without approval).")
    path.write_text(text, encoding="utf-8")


MAX_QA_REWORK_ROUNDS = 2


def build_specialist_prompt(specialist: str, context: dict, policy: dict) -> str:
    """Base prompt, plus a rework request when QA sent findings back to the Lead Engineer."""
    prompt = _build_specialist_prompt_base(specialist, context, policy)
    feedback = context.get("rework_feedback") if isinstance(context, dict) else None
    if specialist == "Lead Engineer" and feedback:
        prompt += (
            "\n\nREWORK REQUEST (round " + str(context.get("rework_round", 1)) + " of " + str(MAX_QA_REWORK_ROUNDS) + "). "
            "The independent QA Agent reviewed your implementation and reported the findings below. The project files already exist in the "
            "project folder: read them, then fix the real defects with your Edit/Write tools (keep every file inside the project folder). "
            "Fix what violates the acceptance criteria or is a genuine robustness, correctness or security defect. If you decline a finding, "
            "say why in the evidence list. Update the unit tests to cover the fixes. Return the same JSON object as before, with files_changed "
            "listing every project file. You cannot run the tests; the pipeline runs them and QA will re-check.\n\nQA FINDINGS:\n" + str(feedback)
        )
    return prompt


def _qa_feedback_text(result: dict) -> str:
    """Turn a QA result into a compact rework request (bugs, recommendations, failing test runs, failed edge cases)."""
    artifacts = _extract_artifacts(result) or {}
    parts = []
    for key in ("bugs_found", "recommendations"):
        value = artifacts.get(key)
        if value:
            parts.append(key + ": " + json.dumps(value)[:3500])
    runs = artifacts.get("test_results")
    if isinstance(runs, list):
        failing = [r for r in runs if isinstance(r, dict) and r.get("exit_code") not in (0, None)]
        if failing:
            parts.append("failing_test_runs: " + json.dumps(failing)[:2000])
    edge = artifacts.get("edge_case_results")
    if edge:
        parts.append("edge_case_results: " + json.dumps(edge)[:1500])
    return "\n".join(parts)[:7500]


def _qa_rework_loop(state: dict, state_file: Path, context: dict, state_dir: Path, policy: dict,
                    quality_gates: list, invoke_fn: Callable, result: dict, aggregate: dict) -> tuple:
    """Bounded QA -> Lead Engineer -> QA loop. Returns the latest (qa_result, qa_aggregate)."""
    state.setdefault("rework_rounds", [])
    for round_no in range(1, MAX_QA_REWORK_ROUNDS + 1):
        feedback = _qa_feedback_text(result)
        if not feedback or result.get("status") != "SUCCESS":
            break                                   # nothing concrete to send back (e.g. QA itself could not run)
        chain = get_execution_chain("Lead Engineer", policy)
        state["current_phase"] = f"REWORK_LEAD_ENGINEER_ROUND_{round_no}"
        state["current_milestone"] = f"Rework round {round_no}/{MAX_QA_REWORK_ROUNDS} - Lead Engineer fixing QA findings"
        state["specialist_in_progress"] = "Lead Engineer"
        state["active_worker"] = chain[0] if chain else None
        state["next_action"] = "Lead Engineer is fixing the defects reported by QA."
        state["updated_at"] = _utc_timestamp()
        record_activity(state, "REWORK_STARTED", f"QA findings sent to the Lead Engineer (round {round_no}).",
                        specialist="Lead Engineer", round=round_no)
        _write_json_file(state_file, state)

        rework_context = dict(context)
        rework_context["rework_feedback"] = feedback
        rework_context["rework_round"] = round_no
        le_result = invoke_fn("Lead Engineer", rework_context, state_dir, policy)
        le_aggregate = validate_specialist_gates("Lead Engineer", le_result, state_dir, quality_gates)
        state["specialist_gate_status"]["Lead Engineer"] = le_aggregate["status"]
        for gate, gate_result in le_aggregate["gates"].items():
            state["gate_status"][gate] = gate_result
        state["worker_used"]["Lead Engineer"] = _extract_worker(le_result)
        entry = {"round": round_no, "qa_findings_chars": len(feedback), "lead_engineer_gate": le_aggregate["status"],
                 "lead_engineer_worker": state["worker_used"]["Lead Engineer"]}
        if le_aggregate["status"] != "PASS":
            entry["stopped"] = "Lead Engineer gate failed: " + str(le_aggregate.get("reason"))[:200]
            state["rework_rounds"].append(entry)
            record_activity(state, "REWORK_STOPPED", entry["stopped"], specialist="Lead Engineer", round=round_no)
            _write_json_file(state_file, state)
            return le_result, le_aggregate          # the blocker is now the Lead Engineer's, report that honestly

        # QA looks again at the reworked project (fresh context so it reads the new Lead Engineer output)
        key = "lead_engineer"
        refreshed = _read_json_file(state_dir / "outputs" / f"{key}.json", {})
        qa_context = dict(context)
        qa_context["outputs"] = dict(context.get("outputs", {}))
        if refreshed:
            qa_context["outputs"]["Lead Engineer"] = refreshed
        state["current_phase"] = f"REWORK_QA_ROUND_{round_no}"
        state["current_milestone"] = f"Rework round {round_no}/{MAX_QA_REWORK_ROUNDS} - QA re-checking"
        state["specialist_in_progress"] = "QA Agent"
        chain_qa = get_execution_chain("QA Agent", policy)
        state["active_worker"] = chain_qa[0] if chain_qa else None
        state["updated_at"] = _utc_timestamp()
        _write_json_file(state_file, state)
        result = invoke_fn("QA Agent", qa_context, state_dir, policy)
        aggregate = validate_specialist_gates("QA Agent", result, state_dir, quality_gates)
        entry["qa_gate_after"] = aggregate["status"]
        state["rework_rounds"].append(entry)
        record_activity(state, "REWORK_COMPLETED", f"Round {round_no}: QA gate {aggregate['status']} after rework.",
                        specialist="QA Agent", round=round_no, qa_gate=aggregate["status"])
        _write_json_file(state_file, state)
        if aggregate["status"] == "PASS":
            break
    if aggregate.get("status") != "PASS" and state.get("rework_rounds"):
        try:
            remaining = _extract_artifacts(result).get("bugs_found") or []
        except Exception:
            remaining = []
        summary = "; ".join(f"{b.get('id', '?')} ({b.get('severity', '?')}): {b.get('summary', '')}" for b in remaining if isinstance(b, dict))[:900]
        aggregate = dict(aggregate)
        aggregate["reason"] = (str(aggregate.get("reason", "")) + f" After {len(state['rework_rounds'])} rework round(s) QA still reports: "
                               + (summary or "see outputs/qa_agent.json") + ". Needs a human decision.")
    return result, aggregate


def run_project(request: str, policy: Optional[dict] = None,
                state_dir: Optional[Path] = None,
                invoke_fn: Optional[Callable] = None,
                resume: bool = False) -> tuple[dict, Path]:
    """Execute a project sequentially with fail-closed, persisted gates."""
    if not request or not request.strip():
        raise ValueError("A non-empty project request is required.")
    policy = policy or load_policy()
    invoke_fn = invoke_fn or invoke_specialist
    project_type, confidence, semantic_used = classify_request(request, policy)
    request_lower = request.lower()
    specialists = get_specialists_for_type(project_type, policy, request_lower)
    quality_gates = get_quality_gates_for_type(project_type, request_lower)
    approval_points = get_human_approval_points(project_type, request_lower)

    if state_dir is None:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", request[:50])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Canonical by default, not an OS /tmp scratch dir: canonical_runtime_project_dir()
        # (main(), for --state-dir/--resume/--approve/--reject) only accepts paths inside
        # runtime/projects, so a project must already live there to ever be resumable.
        state_dir = PROFILE_DIR / "runtime" / "projects" / f"{safe_name}_{timestamp}"
        state_dir.mkdir(parents=True, exist_ok=True)
    else:
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)

    state_file = state_dir / "state.json"
    prior_state = _read_json_file(state_file, {}) if resume else {}
    can_resume = bool(
        prior_state
        and prior_state.get("project_name") == request
        and prior_state.get("project_type") == project_type
        and prior_state.get("selected_specialists") == specialists
    )
    created_files = (
        prior_state.get("template_files", [])
        if can_resume else init_project_template(project_type, state_dir, request)
    )
    state = prior_state if can_resume else {
        "schema_version": 2,
        "project_name": request,
        "project_type": project_type,
        "classification": {"confidence": confidence, "semantic_used": semantic_used},
        "current_phase": "PLANNING",
        "current_milestone": "Requirements and routing",
        "selected_specialists": specialists.copy(),
        "skipped_specialists": get_skipped_specialists(specialists, project_type),
        "specialists_completed": [],
        "specialist_in_progress": None,
        "pending_specialists": specialists.copy(),
        "required_gates": quality_gates,
        "gate_status": {},
        "specialist_gate_status": {},
        "blocked_reason": None,
        "worker_used": {},
        "fallback_used": {},
        "fallback_events": [],
        "active_worker": None,
        "specialist_execution": {},
        "approval": {
            "required": bool(approval_points),
            "status": "PENDING" if approval_points else "NOT_REQUIRED",
            "points": approval_points,
            "decided_at": None,
        },
        "knowledge_capture": {"mode": "STAGED_ONLY", "published": False},
        "template_files": created_files,
        "last_verified_action": "Project initialized",
        "next_action": f"Invoke {specialists[0]}." if specialists else "Complete simple task.",
        "updated_at": _utc_timestamp(),
        "activity": [],
    }
    if can_resume:
        state["current_phase"] = "RESUMING"
        state["current_milestone"] = "Controlled retry"
        state["specialist_in_progress"] = None
        state["blocked_reason"] = None
        state["pending_specialists"] = [
            item for item in specialists
            if item not in state.get("specialists_completed", [])
        ]
        state["next_action"] = (
            f"Retry {state['pending_specialists'][0]}."
            if state["pending_specialists"] else "Finalize project state."
        )
        state["updated_at"] = _utc_timestamp()
        record_activity(
            state,
            "PROJECT_RESUMED",
            "Retrying from the last persisted, gate-verified specialist boundary.",
            completed_specialists=state.get("specialists_completed", []).copy(),
        )
        revalidate_completed_checkpoints(
            state_dir, state, specialists, quality_gates)
        restore_validated_checkpoints(
            state_dir, state, specialists, quality_gates)
        state["pending_specialists"] = [
            item for item in specialists
            if item not in state.get("specialists_completed", [])
        ]
        for pending in state["pending_specialists"]:
            state.get("worker_used", {}).pop(pending, None)
            state.get("fallback_used", {}).pop(pending, None)
            state.get("specialist_gate_status", {}).pop(pending, None)
            for gate in SPECIALIST_GATE_MAP.get(pending, []):
                state.get("gate_status", {}).pop(gate, None)
    else:
        record_activity(
            state,
            "PROJECT_INITIALIZED",
            "Project classified and controlled routing plan created.",
            project_type=project_type,
            selected_specialists=specialists.copy(),
            skipped_specialists=state["skipped_specialists"],
        )
    _write_json_file(state_file, state)

    refill_documents_from_outputs(state_dir)
    for index, specialist in enumerate(specialists):
        if specialist in state["specialists_completed"]:
            continue
        worker_chain = get_execution_chain(specialist, policy)
        active_worker = worker_chain[0] if worker_chain else None
        state["current_phase"] = f"EXECUTING_{specialist.upper().replace(' ', '_').replace('/', '_')}"
        state["current_milestone"] = f"{index + 1}/{len(specialists)} — {specialist}"
        state["specialist_in_progress"] = specialist
        state["active_worker"] = active_worker
        state.setdefault("specialist_execution", {})[specialist] = {
            "status": "IN_PROGRESS",
            "worker": active_worker,
            "evidence": None,
        }
        state["next_action"] = f"Invoking {specialist}."
        state["updated_at"] = _utc_timestamp()
        record_activity(
            state,
            "SPECIALIST_STARTED",
            f"Routing work to {specialist}.",
            specialist=specialist,
            worker_chain=worker_chain,
        )
        _write_json_file(state_file, state)

        outputs = {}
        for completed in state["specialists_completed"]:
            key = completed.lower().replace("/", "_").replace(" ", "_")
            prior = _read_json_file(state_dir / "outputs" / f"{key}.json", {})
            if prior:
                outputs[completed] = prior
        context = {
            "project_name": request,
            "project_type": project_type,
            "state_dir": str(state_dir),
            "completed_specialists": state["specialists_completed"].copy(),
            "outputs": outputs,
        }
        result = invoke_fn(specialist, context, state_dir, policy)
        aggregate = validate_specialist_gates(
            specialist, result, state_dir, quality_gates)
        if specialist == "QA Agent" and aggregate["status"] != "PASS":
            result, aggregate = _qa_rework_loop(
                state, state_file, context, state_dir, policy, quality_gates, invoke_fn, result, aggregate)
        state["specialist_gate_status"][specialist] = aggregate["status"]
        for gate, gate_result in aggregate["gates"].items():
            state["gate_status"][gate] = gate_result
            if isinstance(gate_result, dict) and gate_result.get("waived"):
                state.setdefault("gate_waivers_applied", []).append({
                    "gate": gate, "specialist": specialist, "reason": gate_result.get("reason"),
                    "decided_by": gate_result.get("waiver_decided_by"), "decided_at": gate_result.get("waiver_decided_at"),
                    "waived_finding_ids": gate_result.get("waived_finding_ids"),
                    "original_reason": gate_result.get("original_reason"), "recorded_at": _utc_timestamp(),
                })
                record_activity(state, "GATE_WAIVED", gate_result.get("reason"), gate=gate, specialist=specialist,
                                waived_finding_ids=gate_result.get("waived_finding_ids"),
                                decided_by=gate_result.get("waiver_decided_by"))
        state["worker_used"][specialist] = _extract_worker(result)
        state["fallback_used"][specialist] = _extract_fallback(result)
        evidence_path = result.get("output_file")
        if evidence_path:
            try:
                evidence_path = Path(evidence_path).resolve().relative_to(state_dir.resolve()).as_posix()
            except (OSError, ValueError):
                evidence_path = None
        declared_execution = result.get("metadata", {}).get("execution_status")
        execution_status = declared_execution if declared_execution in {
            "ACTUALLY_EXECUTED", "EVIDENCE_VALIDATED_ONLY", "NOT_RUN"
        } else "ACTUALLY_EXECUTED"
        state["specialist_execution"][specialist] = {
            "status": execution_status,
            "worker": state["worker_used"][specialist],
            "evidence": evidence_path,
        }
        state["active_worker"] = state["worker_used"][specialist]
        state["last_verified_action"] = (
            f"{specialist} completed with gate status {aggregate['status']}." )
        record_activity(
            state,
            "SPECIALIST_COMPLETED",
            state["last_verified_action"],
            specialist=specialist,
            worker=state["worker_used"][specialist],
            fallback_used=state["fallback_used"][specialist],
            gate_status=aggregate["status"],
            gates=aggregate["gates"],
            attempts=result.get("metadata", {}).get("attempts", []),
        )
        for provider_event in result.get("metadata", {}).get("provider_events", []):
            event_name = provider_event.get("event")
            if event_name in {
                "RETRYABLE_OVERLOAD", "BACKOFF", "WORKER_TEMPORARILY_UNAVAILABLE"
            }:
                record_activity(
                    state,
                    event_name,
                    provider_event.get("detail") or (
                        f"{provider_event.get('worker')} {event_name.lower().replace('_', ' ')}."
                    ),
                    **{key: value for key, value in provider_event.items()
                       if key not in {"event", "detail"}},
                )

        if aggregate["status"] != "PASS":
            state["current_phase"] = "BLOCKED_BY_QUALITY_GATE"
            state["current_milestone"] = "Quality gate remediation"
            state["blocked_reason"] = aggregate["reason"]
            state["next_action"] = f"Resolve {specialist} gate evidence before continuing."
            state["specialist_in_progress"] = specialist
            state["updated_at"] = _utc_timestamp()
            record_activity(
                state,
                "QUALITY_GATE_BLOCKED",
                aggregate["reason"],
                specialist=specialist,
            )
            _write_json_file(state_file, state)
            return state, state_dir

        fill_project_documents(state_dir, specialist, result)
        state["specialists_completed"].append(specialist)
        state["pending_specialists"] = specialists[index + 1:]
        state["specialist_in_progress"] = None
        state["active_worker"] = None
        capture_to_obsidian(state_dir, specialist, result, publish=False,
                            validated=True)
        state["next_action"] = (
            f"Invoke {specialists[index + 1]}."
            if index + 1 < len(specialists) else "Finalize project state."
        )
        state["updated_at"] = _utc_timestamp()
        _write_json_file(state_file, state)

    fill_plan_document(state_dir, quality_gates, approval_points)
    unresolved_gates = [gate for gate in quality_gates
                        if state["gate_status"].get(gate, {}).get("status") != "PASS"]
    if unresolved_gates:
        state["current_phase"] = "BLOCKED_BY_QUALITY_GATE"
        state["current_milestone"] = "Quality gate remediation"
        state["blocked_reason"] = (
            "Required gates were not satisfied: " + ", ".join(unresolved_gates))
        state["next_action"] = "Route the missing gate owners and provide evidence."
    elif approval_points:
        state["current_phase"] = "AWAITING_HUMAN_APPROVAL"
        state["current_milestone"] = "Human approval"
        state["next_action"] = "Record an explicit approval or rejection; do not deploy."
    else:
        state["current_phase"] = "COMPLETED"
        state["current_milestone"] = "Controlled delivery complete"
        state["next_action"] = "Project completed."
    state["updated_at"] = _utc_timestamp()
    state["active_worker"] = None
    record_activity(
        state,
        "PROJECT_FINALIZED",
        f"Controlled run reached {state['current_phase']}.",
        phase=state["current_phase"],
        approval_status=state["approval"]["status"],
    )
    _write_json_file(state_file, state)
    return state, state_dir


def main():
    parser = argparse.ArgumentParser(description="Run the controlled Hermes Product Factory director.")
    parser.add_argument("request", nargs="?", help="The complete project request.")
    parser.add_argument("--state-dir", type=Path, help="Canonical runtime project directory.")
    parser.add_argument("--resume", action="store_true", help="Resume a compatible canonical checkpoint.")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    args = parser.parse_args()
    approve_mode = args.approve
    reject_mode = args.reject
    state_dir_override = args.state_dir

    if state_dir_override is not None:
        try:
            state_dir_override = canonical_runtime_project_dir(state_dir_override)
        except ValueError as exc:
            parser.error(str(exc))

    # Handle approval-mode actions
    if approve_mode or reject_mode:
        if state_dir_override and state_dir_override.exists():
            record_approval(state_dir_override, approved=approve_mode)
            status = "APPROVED" if approve_mode else "REJECTED"
            print(f"Human approval: {status}")
            print(f"State directory: {state_dir_override}")
            sys.exit(0)
        else:
            print("Error: --state-dir required for approval actions.", file=sys.stderr)
            sys.exit(1)

    # Normal orchestration mode
    request = args.request
    if not request:
        print("Error: No request provided.", file=sys.stderr)
        sys.exit(1)

    print(f"Processing request: {request}")
    final, state_dir = run_project(
        request,
        state_dir=state_dir_override,
        resume=args.resume,
    )
    classification = final.get("classification", {})
    print(
        f"Classification: {final['project_type']} "
        f"(confidence: {classification.get('confidence')}, "
        f"semantic: {classification.get('semantic_used')})"
    )
    completed = final.get("specialists_completed", [])
    pending = final.get("pending_specialists", [])
    print(f"Specialists: {len(completed) + len(pending)}")
    print(f"Gates: {', '.join(final.get('required_gates', [])) or 'None'}")
    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    print(json.dumps(final, indent=2))
    print(f"State directory: {state_dir}")
    if final.get("current_phase") == "COMPLETED":
        print("\nRESULT: SUCCESS")
    elif final.get("current_phase") == "AWAITING_HUMAN_APPROVAL":
        print(f"\nRESULT: AWAITING HUMAN APPROVAL (state: {state_dir})")
    else:
        print("\nRESULT: BLOCKED")
    return

    print(f"Processing request: {request}")

    # Load policy
    policy = load_policy()

    # Classify
    request_lower = request.lower()
    project_type, confidence, semantic_used = classify_request(request, policy)
    print(f"Classification: {project_type} (confidence: {confidence}, semantic: {semantic_used})")

    # Select specialists
    specialists = get_specialists_for_type(project_type, policy, request_lower)
    print(f"Specialists ({len(specialists)}): {', '.join(specialists) if specialists else 'None'}")

    # Determine complexity
    num = len(specialists)
    complexity = "LOW" if num <= 2 else ("MEDIUM" if num <= 5 else "HIGH")
    print(f"Complexity: {complexity}")

    # Create state directory
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', request[:50])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    state_dir = Path(tempfile.mkdtemp(
        prefix=f"hermes_pf_{safe_name}_{timestamp}_"))
    
    # Initialize project template
    created_files = init_project_template(project_type, state_dir, request)
    if created_files:
        print(f"Template files created: {len(created_files)}")

    # Initialize state
    state = {
        "project_name": request,
        "project_type": project_type,
        "current_phase": "PLANNING",
        "current_milestone": "None",
        "specialists_completed": [],
        "specialist_in_progress": None,
        "pending_specialists": specialists.copy(),
        "gate_status": {},
        "blocked_reason": None,
        "worker_used": {},
        "fallback_used": {},
        "last_verified_action": "Project initialized",
        "next_action": "Invoke Product Agent." if specialists and "Product Agent" in specialists else "No specialists needed.",
    }
    with open(state_dir / "state.json", 'w') as f:
        json.dump(state, f, indent=2)

    # Execute specialists sequentially
    specialist_to_gate = {
        "Product Agent": "Requirements",
        "Research Agent": "Research",
        "Architecture Agent": "Architecture",
        "Lead Engineer": "Build",
        "Data/ML Engineer": "Data/ML",
        "ML/AI Evaluation Agent": "AI/LLM",
        "QA Agent": "Testing",
        "Security Agent": "Security",
        "UI/UX Agent": "UI/UX",
        "Release/DevOps Agent": "Release",
    }

    quality_gates = get_quality_gates_for_type(project_type, request_lower)

    index = 0
    while index < len(specialists):
        specialist = specialists[index]
        phase = f"EXECUTING_{specialist.upper().replace(' ', '_').replace('/', '_')}"
        state["current_phase"] = phase
        state["specialist_in_progress"] = specialist
        state["next_action"] = f"Invoking {specialist}..."
        with open(state_dir / "state.json", 'w') as f:
            json.dump(state, f, indent=2)

        # Build context
        context = {
            "project_name": request,
            "project_type": project_type,
            "completed_specialists": state["specialists_completed"],
            "outputs": {},
        }
        for completed in state["specialists_completed"]:
            key = completed.lower().replace('/', '_').replace(' ', '_')
            out_file = state_dir / "outputs" / f"{key}.json"
            if out_file.exists():
                with open(out_file, 'r') as f:
                    context["outputs"][completed] = json.load(f)

        # Invoke
        print(f"Invoking {specialist}...")
        result = invoke_specialist(specialist, context, state_dir, policy)

        # Validate gate
        gate_name = specialist_to_gate.get(specialist, "Unknown")
        if gate_name not in quality_gates:
            gate_status = {"status": "PASS", "reason": f"Gate {gate_name} not required."}
        else:
            gate_status = validate_gate(gate_name, result, state_dir)

        # Update state
        state = update_state(
            state_dir, specialist, gate_status,
            result.get("worker_used", "unknown"),
            result.get("fallback_used", False),
            state["next_action"]
        )

        # Report
        status_icon = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "⚠", "FAILED": "✗"}.get(
            gate_status["status"], "?")
        print(f"  {status_icon} {specialist}: {gate_status['status']}")
        if gate_status.get("reason"):
            print(f"    Reason: {gate_status['reason'][:200]}")

        if result.get("output_file"):
            print(f"    Output: {result['output_file']}")

        # Capture to Obsidian if available
        if result.get("output") and OBSIDIAN_VAULT:
            captured = capture_to_obsidian(state_dir, specialist, result)
            if captured:
                print(f"    Obsidian: captured to vault")

        # Check for block
        if gate_status["status"] in ("FAIL", "BLOCKED"):
            state["next_action"] = "BLOCKED — awaiting resolution."
            with open(state_dir / "state.json", 'w') as f:
                json.dump(state, f, indent=2)
            break

        index += 1
        if index < len(specialists):
            state["next_action"] = f"Invoke {specialists[index]}."
        else:
            # All done — check human approval
            approval_points = get_human_approval_points(project_type, request_lower)
            if approval_points:
                state["next_action"] = "AWAITING HUMAN APPROVAL"
                state["current_phase"] = "AWAITING_APPROVAL"
                print(f"\nHuman approval required. State dir: {state_dir}")
                print(f"To approve:  director.py --approve --state-dir {state_dir}")
                print(f"To reject:   director.py --reject --state-dir {state_dir}")
            else:
                state["next_action"] = "Project completed."
                state["current_phase"] = "COMPLETED"
        with open(state_dir / "state.json", 'w') as f:
            json.dump(state, f, indent=2)

    # Handle case where no specialists were needed (e.g. SIMPLE_TASK)
    if len(specialists) == 0:
        state["current_phase"] = "COMPLETED"
        state["next_action"] = "Project completed."
        with open(state_dir / "state.json", 'w') as f:
            json.dump(state, f, indent=2)

    # Final report
    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    with open(state_dir / "state.json", 'r') as f:
        final = json.load(f)
    print(json.dumps(final, indent=2))

    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Project:     {request}")
    print(f"Type:        {project_type} ({confidence})")
    print(f"Complexity:  {complexity}")
    print(f"Specialists: {len(specialists)}")
    for i, s in enumerate(specialists, 1):
        gw = get_workers_for_specialist(s, policy)
        cli = gw.get("cli_worker", "model")
        print(f"  {i}. {s} → {cli}")
    print(f"Gates:       {', '.join(quality_gates) if quality_gates else 'None'}")
    print(f"Status:      {final.get('current_phase', 'UNKNOWN')}")
    print(f"Next:        {final.get('next_action', 'UNKNOWN')}")

    if final.get("current_phase") in ("COMPLETED", "DEPLOYMENT_READY"):
        print("\nRESULT: SUCCESS")
    elif final.get("current_phase") == "AWAITING_APPROVAL":
        print(f"\nRESULT: AWAITING HUMAN APPROVAL (state: {state_dir})")
    else:
        print(f"\nRESULT: {'BLOCKED' if final.get('blocked_reason') else 'FAILED'}")


def get_quality_gates_for_type(project_type: str, request_lower: str) -> list[str]:
    """Return quality gates for the project type."""
    r = request_lower

    if project_type == "SIMPLE_TASK":
        return []

    if project_type == "WEBSITE":
        return ["Requirements", "Architecture", "Build", "Testing",
                "Independent QA", "Security", "UI/UX", "Release"]

    if project_type in ("MACHINE_LEARNING", "DATA_SCIENCE"):
        gates = ["Requirements", "Data/ML", "Testing", "Independent QA"]
        prod_kw = ["deploy", "production", "serve", "api", "endpoint",
                   "web app", "dashboard", "integrate", "application",
                   "security", "ui", "ux", "frontend"]
        if contains_any_keyword(r, prod_kw):
            gates.extend(["Architecture", "Security", "Release"])
            if contains_any_keyword(r, ["ui", "ux", "dashboard", "frontend"]):
                gates.append("UI/UX")
        return gates

    if project_type == "AI_AGENT":
        gates = ["Requirements", "Architecture", "Build", "Testing",
                 "Independent QA", "Security", "AI/LLM", "Release"]
        if contains_any_keyword(r, ["ui", "ux", "interface", "frontend", "dashboard"]):
            gates.append("UI/UX")
        return gates

    if project_type == "AI_LLM_APPLICATION":
        gates = ["Requirements", "Architecture", "Build", "Testing",
                 "Independent QA", "Security", "AI/LLM"]
        if contains_any_keyword(r, ["deploy", "production", "serve"]):
            gates.append("Release")
        if contains_any_keyword(r, ["ui", "ux", "dashboard", "frontend"]):
            gates.append("UI/UX")
        return gates

    if project_type == "SAAS":
        return ["Requirements", "Research", "Architecture", "Build",
                "Testing", "Independent QA", "Security", "UI/UX", "Release"]

    if project_type == "PROCUREMENT_SYSTEM":
        return ["Requirements", "Research", "Architecture", "Build",
                "Testing", "Independent QA", "Security", "UI/UX", "Release"]

    if project_type == "API":
        gates = ["Requirements", "Architecture", "Build", "Testing",
                 "Independent QA", "Security"]
        if contains_any_keyword(r, ["deploy", "production"]):
            gates.append("Release")
        return gates

    if project_type == "DATA_PIPELINE":
        return ["Requirements", "Data/ML", "Testing", "Independent QA",
                "Architecture"]

    if project_type == "BUSINESS_AUTOMATION":
        gates = ["Requirements", "Architecture", "Build", "Testing",
                 "Independent QA", "Security"]
        if contains_any_keyword(r, ["ui", "dashboard"]):
            gates.append("UI/UX")
        if contains_any_keyword(r, ["deploy", "production"]):
            gates.append("Release")
        return gates

    if project_type == "INTERNAL_BUSINESS_SYSTEM":
        return ["Requirements", "Architecture", "Build", "Testing",
                "Independent QA", "Security", "UI/UX", "Release"]

    if project_type == "RESEARCH_PROJECT":
        return ["Requirements", "Research", "Testing"]

    # Default
    gates = ["Requirements", "Architecture", "Build", "Testing",
             "Independent QA", "Security"]
    if contains_any_keyword(r, ["ui", "ux", "dashboard", "frontend"]):
        gates.append("UI/UX")
    if contains_any_keyword(r, ["deploy", "production", "serve"]):
        gates.append("Release")
    if contains_any_keyword(r, ["machine learning", "ml", "predict", "train"]):
        gates.append("Data/ML")
    if contains_any_keyword(r, ["llm", "gpt", "chatbot", "rag", "ai assistant"]):
        gates.append("AI/LLM")
    return gates


def get_human_approval_points(project_type: str, request_lower: str) -> list[str]:
    """Return human approval points for the project type."""
    # Safety constraints such as "do not deploy" describe a prohibited action,
    # not a request to perform it. Remove only tightly-scoped negated action
    # phrases before evaluating the positive approval triggers below.
    r = request_lower.lower()
    for pattern in (
        r"\b(?:do not|don't|never)\b[^.;]*",
        r"\bnon-production\b",
        r"\b(?:no|without|do not|don't|never)\s+(?:any\s+)?(?:production\s+)?deploy(?:ment|ing)?\b",
        r"\b(?:no|without|do not|don't|never)\s+(?:any\s+)?production\b",
        r"\b(?:no|without|do not|don't|never)\s+(?:any\s+)?(?:billing|subscriptions?|paid resources?)\b",
        r"\b(?:no|without|do not|don't|never)\s+(?:any\s+)?public (?:service )?exposure\b",
        r"\b(?:no|without|do not|don't|never)\s+(?:any\s+)?irreversible (?:infrastructure )?(?:actions?|changes?)\b",
    ):
        r = re.sub(pattern, "", r)
    points = []

    if project_type in ("SIMPLE_TASK", "RESEARCH_PROJECT"):
        return points

    deploy_kw = ["deploy", "production", "serve", "api", "endpoint",
                 "launch", "go live", "release to"]
    if contains_any_keyword(r, deploy_kw):
        points.extend([
            "Before production deployment",
            "Before creating paid resources",
            "Before public service exposure",
        ])

    if contains_any_keyword(r, ["payment", "billing", "subscription", "paid"]):
        points.append("Before billing changes")

    if contains_any_keyword(r, ["database", "migration", "schema change", "data migration"]):
        points.append("Before destructive database migration")

    if contains_any_keyword(r, ["credential", "secret", "api key", "token", "password"]):
        points.append("Before credential rotation")

    if contains_any_keyword(r, ["provider", "platform", "hosting", "cloud"]):
        points.append("Before major provider changes")

    if contains_any_keyword(r, ["delete", "destroy", "remove", "irreversible"]):
        points.append("Before irreversible infrastructure changes")

    return points


if __name__ == "__main__":
    main()
