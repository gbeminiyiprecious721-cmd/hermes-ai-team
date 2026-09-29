"""Profile-local Product Factory Mission Control dashboard API.

The API is a projection over canonical Product Factory files. It owns no
database, performs no orchestration, and never reports metered usage unless a
trusted runtime source actually supplies it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ROLE_NAMES = [
    ("Hermes Director", "Hermes Director"),
    ("Product Agent", "Product"),
    ("Research Agent", "Research"),
    ("Architecture Agent", "Architecture"),
    ("Lead Engineer", "Lead Engineer / Claude Code"),
    ("Data/ML Engineer", "Data/ML Engineer"),
    ("QA Agent", "QA / Codex"),
    ("Security Agent", "Security"),
    ("UI/UX Agent", "UI/UX"),
    ("ML/AI Evaluation Agent", "ML/AI Evaluation & MLOps"),
    ("Release/DevOps Agent", "Release/DevOps"),
]
SAFE_WORKER_FIELDS = {"status", "reason", "checked_at", "expires_epoch"}
SAFE_POLICY_FIELDS = {"provider", "model", "type", "cost"}
SENSITIVE_KEY = re.compile(r"(api.?key|token|secret|credential|password|authorization)", re.I)
ARTIFACT_SUFFIXES = {".json", ".md", ".txt", ".csv"}
MAX_ARTIFACT_BYTES = 1_000_000


class ApprovalDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]


def _profile_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def _projects_root() -> Path:
    return _profile_home() / "runtime" / "projects"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _project_dir(project_id: str) -> Path:
    if not project_id or Path(project_id).name != project_id:
        raise HTTPException(status_code=400, detail="Invalid project id.")
    root = _projects_root().resolve()
    target = (root / project_id).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project id.") from exc
    if not (target / "state.json").is_file():
        raise HTTPException(status_code=404, detail="Product Factory project not found.")
    return target


def _state_files() -> list[Path]:
    root = _projects_root()
    if not root.is_dir():
        return []
    return [path for path in root.glob("*/state.json") if path.is_file()]


def _updated_key(path: Path) -> tuple[str, float]:
    state = _read_json(path, {})
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return str(state.get("updated_at", "")), modified


def _load_policy() -> dict:
    try:
        value = yaml.safe_load(
            (_profile_home() / "policies" / "routing_policy.yaml").read_text(encoding="utf-8")
        )
        return value if isinstance(value, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _selected_specialists(state: dict) -> list[str]:
    explicit = state.get("selected_specialists")
    if isinstance(explicit, list):
        return [str(value) for value in explicit]
    ordered = []
    candidates = (
        list(state.get("specialists_completed", []))
        + ([state.get("specialist_in_progress")] if state.get("specialist_in_progress") else [])
        + list(state.get("pending_specialists", []))
    )
    for specialist in candidates:
        if specialist and specialist not in ordered:
            ordered.append(str(specialist))
    return ordered


def _skipped_specialists(state: dict, selected: list[str]) -> list[dict]:
    explicit = state.get("skipped_specialists")
    if isinstance(explicit, list):
        return explicit
    project_type = state.get("project_type", "project")
    return [
        {
            "specialist": canonical,
            "reason": f"Not selected by the {project_type} routing plan.",
        }
        for canonical, _label in ROLE_NAMES[1:]
        if canonical not in selected
    ]


def _roles(state: dict, selected: list[str], skipped: list[dict], policy: dict) -> list[dict]:
    completed = set(state.get("specialists_completed", []))
    current = state.get("specialist_in_progress")
    pending = set(state.get("pending_specialists", []))
    skip_reasons = {item.get("specialist"): item.get("reason") for item in skipped}
    worker_used = state.get("worker_used", {})
    fallback_used = state.get("fallback_used", {})
    execution = state.get("specialist_execution", {})
    route = policy.get("routing", {})
    route_keys = {
        "Hermes Director": "hermes_director", "Product Agent": "product_agent",
        "Research Agent": "research_agent", "Architecture Agent": "architecture_agent",
        "Lead Engineer": "lead_engineer", "Data/ML Engineer": "data_ml_engineer",
        "QA Agent": "qa_agent", "Security Agent": "security_agent",
        "UI/UX Agent": "ui_ux_agent", "ML/AI Evaluation Agent": "ml_ai_evaluation_agent",
        "Release/DevOps Agent": "release_devops_agent",
    }
    rows = []
    for canonical, label in ROLE_NAMES:
        if canonical == "Hermes Director":
            status = "ACTIVE" if state.get("current_phase") not in {"COMPLETED", "REJECTED"} else "COMPLETE"
            reason = "Owns routing and gate enforcement."
            execution_status = execution.get(canonical, {}).get(
                "status", "ORCHESTRATING" if status == "ACTIVE" else "NOT_RECORDED"
            )
        elif canonical == current:
            status, reason = "ACTIVE", None
            execution_status = execution.get(canonical, {}).get("status", "IN_PROGRESS")
        elif canonical in completed:
            status, reason = "COMPLETE", None
            execution_status = execution.get(canonical, {}).get("status", "NOT_RECORDED")
        elif canonical in pending or canonical in selected:
            status, reason = "PENDING", None
            execution_status = execution.get(canonical, {}).get("status", "NOT_RUN")
        else:
            status, reason = "SKIPPED", skip_reasons.get(canonical)
            execution_status = execution.get(canonical, {}).get("status", "NOT_RUN")
        execution_detail = execution.get(canonical, {}) if isinstance(execution, dict) else {}
        rows.append({
            "name": canonical,
            "label": label,
            "status": status,
            "reason": reason,
            "worker_used": worker_used.get(canonical) or execution_detail.get("worker"),
            "fallback_used": bool(fallback_used.get(canonical, False)),
            "execution_status": execution_status,
            "execution_evidence": execution_detail.get("evidence"),
            "route": _redact(route.get(route_keys[canonical], {})),
        })
    return rows


def _workers(policy: dict) -> list[dict]:
    availability = _read_json(_profile_home() / "runtime" / "worker_availability.json", {})
    available_workers = availability.get("workers", {}) if isinstance(availability, dict) else {}
    rows = []
    for name, definition in policy.get("workers", {}).items():
        runtime = available_workers.get(name, {})
        safe_runtime = {key: runtime.get(key) for key in SAFE_WORKER_FIELDS if key in runtime}
        safe_definition = {key: definition.get(key) for key in SAFE_POLICY_FIELDS if key in definition}
        rows.append({"name": name, **safe_definition, **safe_runtime})
    return rows


def _gates(state: dict) -> list[dict]:
    results = state.get("gate_status", {})
    return [
        {
            "name": gate,
            "status": results.get(gate, {}).get("status", "PENDING"),
            "reason": results.get(gate, {}).get("reason", "Awaiting evidence."),
        }
        for gate in state.get("required_gates", [])
    ]


def _artifacts(project: Path) -> list[dict]:
    rows = []
    roots = [project / "outputs", project / "knowledge_staging"]
    roots.extend(project / name for name in ("README.md", "PRD.md", "ARCHITECTURE.md", "implementation_plan.md", "DELIVERY_CONTRACT.md"))
    candidates = []
    for root in roots:
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
        elif root.is_file():
            candidates.append(root)
    for path in sorted(set(candidates)):
        if path.suffix.lower() not in ARTIFACT_SUFFIXES:
            continue
        relative = path.relative_to(project).as_posix()
        rows.append({
            "id": relative,
            "name": path.name,
            "group": relative.split("/", 1)[0] if "/" in relative else "project",
            "size": path.stat().st_size,
        })
    return rows


def _fallback_events(project: Path, state: dict) -> list[dict]:
    events = []
    for output in sorted((project / "outputs").glob("*.json")) if (project / "outputs").is_dir() else []:
        payload = _read_json(output, {})
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        attempts = metadata.get("attempts", [])
        if metadata.get("fallback_used") or len(attempts) > 1:
            events.append({
                "specialist": payload.get("specialist"),
                "worker": payload.get("worker"),
                "attempts": _redact(attempts),
                "fallback_used": bool(metadata.get("fallback_used")),
                "timestamp": metadata.get("timestamp"),
            })
    if events:
        return events
    return [
        {"specialist": specialist, "worker": state.get("worker_used", {}).get(specialist), "fallback_used": True}
        for specialist, used in state.get("fallback_used", {}).items() if used
    ]


def build_snapshot(project: Path) -> dict:
    state = _read_json(project / "state.json", {})
    if not state:
        raise HTTPException(status_code=500, detail="Project state is unreadable.")
    policy = _load_policy()
    selected = _selected_specialists(state)
    skipped = _skipped_specialists(state, selected)
    approval = state.get("approval", {})
    approval_status = approval.get("status", "NOT_REQUIRED")
    if approval_status == "REJECTED":
        approval_status = "DENIED"
    gates = _gates(state)
    gate_pass = bool(gates) and all(gate["status"] == "PASS" for gate in gates)
    phase = state.get("current_phase", "UNKNOWN")
    controlled_ready = gate_pass and (
        phase == "COMPLETED" or approval_status == "APPROVED"
    )
    workers = _workers(policy)
    return {
        "profile": "product-factory",
        "project_id": project.name,
        "project": state.get("project_name", project.name),
        "project_type": state.get("project_type", "UNKNOWN"),
        "phase": phase,
        "milestone": state.get("current_milestone") or phase.replace("_", " ").title(),
        "current_specialist": state.get("specialist_in_progress"),
        "active_worker": state.get("active_worker") or state.get("worker_used", {}).get(state.get("specialist_in_progress")),
        "selected_specialists": selected,
        "skipped_specialists": skipped,
        "roles": _roles(state, selected, skipped, policy),
        "workers": workers,
        "fallback_events": _fallback_events(project, state),
        "gates": gates,
        "approval": {
            "required": bool(approval.get("required", False)),
            "status": approval_status,
            "points": approval.get("points", []),
            "decided_at": approval.get("decided_at"),
        },
        "blocker": state.get("blocked_reason") or (state.get("blockers") or [None])[0],
        "blockers": state.get("blockers", []),
        "last_verified_action": state.get("last_verified_action"),
        "next_action": state.get("next_action"),
        "activity": _redact(state.get("activity", [])),
        "artifacts": _artifacts(project),
        "staged_artifacts": state.get("staged_artifacts", []),
        "release_readiness": {
            "controlled": "READY" if controlled_ready else "NOT_READY",
            "production": "BLOCKED",
            "global_activation": "DISABLED",
        },
        "provider_usage": [
            {
                "worker": worker["name"],
                "configured_cost": worker.get("cost"),
                "availability": worker.get("status", "UNKNOWN"),
                "metered_usage": None,
                "note": "Metered usage is not available from a reliable local source.",
            }
            for worker in workers
        ],
        "updated_at": state.get("updated_at"),
        "source_of_truth": {
            "state": "state.json",
            "outputs": "outputs/*.json",
            "staged_knowledge": "knowledge_staging/*",
            "workers": "runtime/worker_availability.json",
            "routing": "policies/routing_policy.yaml",
            "duplicate_database": False,
        },
    }


def _load_director():
    module_name = "hermes_product_factory_director"
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = _profile_home() / "skills" / "hermes-director" / "director.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Product Factory director could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@router.get("/projects")
def list_projects():
    rows = []
    for state_file in sorted(_state_files(), key=_updated_key, reverse=True):
        state = _read_json(state_file, {})
        rows.append({
            "project_id": state_file.parent.name,
            "project": state.get("project_name", state_file.parent.name),
            "project_type": state.get("project_type", "UNKNOWN"),
            "phase": state.get("current_phase", "UNKNOWN"),
            "updated_at": state.get("updated_at"),
        })
    return {"projects": rows}


@router.get("/snapshot")
def latest_snapshot():
    files = sorted(_state_files(), key=_updated_key, reverse=True)
    if not files:
        return {"project": None, "profile": "product-factory", "message": "No controlled project has run yet."}
    return build_snapshot(files[0].parent)


@router.get("/projects/{project_id}")
def project_snapshot(project_id: str):
    return build_snapshot(_project_dir(project_id))


@router.get("/projects/{project_id}/artifacts/{artifact_path:path}")
def inspect_artifact(project_id: str, artifact_path: str):
    project = _project_dir(project_id)
    target = (project / artifact_path).resolve()
    try:
        target.relative_to(project.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path.") from exc
    if not target.is_file() or target.suffix.lower() not in ARTIFACT_SUFFIXES:
        raise HTTPException(status_code=404, detail="Inspectable artifact not found.")
    if target.stat().st_size > MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail="Artifact is too large to inspect in the dashboard.")
    if target.suffix.lower() == ".json":
        return {"path": artifact_path, "kind": "json", "content": _redact(_read_json(target, {}))}
    return {"path": artifact_path, "kind": "text", "content": target.read_text(encoding="utf-8", errors="replace")}


@router.post("/projects/{project_id}/approval")
def decide_approval(project_id: str, payload: ApprovalDecision):
    project = _project_dir(project_id)
    state = _read_json(project / "state.json", {})
    approval = state.get("approval", {})
    if not approval.get("required") or approval.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="This project has no pending approval point.")
    if state.get("current_phase") != "AWAITING_HUMAN_APPROVAL":
        raise HTTPException(status_code=409, detail="Approval is only accepted at the canonical approval phase.")
    director = _load_director()
    director.record_approval(project, approved=payload.decision == "APPROVE")
    return build_snapshot(project)


# ---------------------------------------------------------------------------
# Server-sent events: pushes a "changed" signal (and each new activity entry)
# the moment a project's state.json is written, so the page reloads instantly
# instead of waiting for its polling timer. Polling remains as the fallback.
# ---------------------------------------------------------------------------
import asyncio
import time as _time

from fastapi.responses import StreamingResponse


def _project_marks() -> dict:
    marks = {}
    for f in _state_files():
        try:
            st = f.stat()
            marks[f.parent.name] = (st.st_mtime_ns, st.st_size)
        except OSError:
            pass
    return marks


def _kanban_mark():
    """mtime of the shared Kanban database and its WAL: changes whenever a task changes."""
    home = _profile_home()
    root = home.parent.parent if home.parent.name == "profiles" else home
    marks = []
    for name in ("kanban.db", "kanban.db-wal"):
        try:
            marks.append((root / name).stat().st_mtime_ns)
        except OSError:
            marks.append(0)
    return tuple(marks)


def _activity_counts() -> dict:
    return {f.parent.name: len(_read_json(f, {}).get("activity", []) or []) for f in _state_files()}


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@router.get("/stream")
async def stream():
    async def gen():
        yield "retry: 3000\n\n"
        yield _sse({"type": "hello"})
        marks = await asyncio.to_thread(_project_marks)
        counts = await asyncio.to_thread(_activity_counts)
        last_kanban = await asyncio.to_thread(_kanban_mark)
        last_lib = await asyncio.to_thread(_library_mark)
        idle = 0
        while True:
            await asyncio.sleep(1)
            now = await asyncio.to_thread(_project_marks)
            for pid, mark in now.items():
                if marks.get(pid) == mark:
                    continue
                marks[pid] = mark
                state = _read_json(_projects_root() / pid / "state.json", {})
                activity = state.get("activity", []) or []
                start = counts.get(pid, 0)
                if start > len(activity):  # file was rewritten shorter
                    start = 0
                for entry in activity[start:][-20:]:
                    yield _sse({"type": "activity", "project_id": pid, "entry": _redact(entry)})
                counts[pid] = len(activity)
                yield _sse({"type": "changed", "project_id": pid, "phase": state.get("current_phase"),
                            "updated_at": state.get("updated_at")})
                idle = 0
            kmark = await asyncio.to_thread(_kanban_mark)
            if kmark != last_kanban:
                last_kanban = kmark
                idle = 0
                yield _sse({"type": "kanban"})
            lmark = await asyncio.to_thread(_library_mark)
            if lmark != last_lib:
                last_lib = lmark
                idle = 0
                yield _sse({"type": "library"})
            idle += 1
            if idle >= 15:
                idle = 0
                yield ": ping\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# ---------------------------------------------------------------------------
# Team task board: read-only view of the shared Hermes Kanban board (the one
# Gideon creates tasks on). The database lives in the ROOT Hermes home, one level
# above this profile. Nothing here writes to it.
# ---------------------------------------------------------------------------
import sqlite3

_SECRET_TEXT = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|xox[abp]-[A-Za-z0-9\-]{10,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b)")
_KANBAN_ORDER = ["triage", "todo", "ready", "running", "review", "blocked", "done"]
_TEXT_TYPES = (".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml", ".html")


def _kanban_root() -> Path:
    home = _profile_home()
    return home.parent.parent if home.parent.name == "profiles" else home


def _kanban_ro():
    db = _kanban_root() / "kanban.db"
    if not db.is_file():
        raise HTTPException(status_code=404, detail="No Kanban board found.")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    return con


def _scrub(text, limit=None):
    if text is None:
        return None
    s = _SECRET_TEXT.sub("[REDACTED]", str(text))
    return s[:limit] if limit else s


def _ts(epoch):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if epoch else None


@router.get("/kanban")
def kanban_board(limit: int = 80):
    limit = max(1, min(int(limit), 200))
    con = _kanban_ro()
    try:
        rows = con.execute(
            "select t.id, t.title, t.assignee, t.status, t.priority, t.created_by, t.created_at, t.started_at, "
            "t.completed_at, t.consecutive_failures, t.last_failure_error, t.block_kind, "
            "(select summary from task_runs r where r.task_id = t.id order by r.id desc limit 1) last_summary, "
            "(select count(*) from task_attachments a where a.task_id = t.id) attachments, "
            "(select group_concat(parent_id) from task_links l where l.child_id = t.id) parents "
            "from tasks t where t.status != 'archived' order by t.created_at desc limit ?", (limit,)).fetchall()
    finally:
        con.close()
    tasks, by_status, by_assignee = [], {}, {}
    for r in rows:
        status = (r["status"] or "unknown").lower()
        by_status[status] = by_status.get(status, 0) + 1
        who = r["assignee"] or "unassigned"
        by_assignee[who] = by_assignee.get(who, 0) + 1
        tasks.append({
            "id": r["id"], "title": _scrub(r["title"], 140), "assignee": who, "status": status,
            "priority": r["priority"], "created_by": r["created_by"],
            "created_at": _ts(r["created_at"]), "started_at": _ts(r["started_at"]), "completed_at": _ts(r["completed_at"]),
            "failures": r["consecutive_failures"] or 0, "last_error": _scrub(r["last_failure_error"], 200),
            "block_kind": r["block_kind"], "summary": _scrub(r["last_summary"], 220),
            "attachments": r["attachments"], "parents": (r["parents"] or "").split(",") if r["parents"] else [],
        })
    columns = [s for s in _KANBAN_ORDER if s in by_status] + sorted(s for s in by_status if s not in _KANBAN_ORDER)
    return {"tasks": tasks, "columns": columns, "by_status": by_status, "by_assignee": by_assignee}


@router.get("/kanban/{task_id}")
def kanban_task(task_id: str):
    con = _kanban_ro()
    try:
        t = con.execute("select * from tasks where id = ?", (task_id,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="Task not found.")
        runs = con.execute("select id, profile, status, outcome, started_at, ended_at, summary, error from task_runs where task_id = ? order by id", (task_id,)).fetchall()
        events = con.execute("select kind, payload, created_at from task_events where task_id = ? order by id desc limit 30", (task_id,)).fetchall()
        comments = con.execute("select author, body, created_at from task_comments where task_id = ? order by id", (task_id,)).fetchall()
        atts = con.execute("select id, filename, content_type, size, uploaded_by, created_at from task_attachments where task_id = ? order by id", (task_id,)).fetchall()
    finally:
        con.close()
    return {
        "id": t["id"], "title": _scrub(t["title"], 200), "assignee": t["assignee"] or "unassigned", "status": t["status"],
        "body": _scrub(t["body"], 4000), "result": _scrub(t["result"], 4000), "created_by": t["created_by"],
        "created_at": _ts(t["created_at"]), "started_at": _ts(t["started_at"]), "completed_at": _ts(t["completed_at"]),
        "failures": t["consecutive_failures"] or 0, "last_error": _scrub(t["last_failure_error"], 400),
        "runs": [{"id": r["id"], "profile": r["profile"], "status": r["status"], "outcome": r["outcome"],
                  "started_at": _ts(r["started_at"]), "ended_at": _ts(r["ended_at"]),
                  "summary": _scrub(r["summary"], 1500), "error": _scrub(r["error"], 400)} for r in runs],
        "events": [{"kind": e["kind"], "at": _ts(e["created_at"])} for e in events if e["kind"] not in ("heartbeat",)],
        "comments": [{"author": c["author"], "body": _scrub(c["body"], 1500), "at": _ts(c["created_at"])} for c in comments],
        "attachments": [{"id": a["id"], "filename": a["filename"], "size": a["size"], "type": a["content_type"],
                         "by": a["uploaded_by"], "at": _ts(a["created_at"])} for a in atts],
    }


@router.get("/kanban/{task_id}/attachments/{attachment_id}")
def kanban_attachment(task_id: str, attachment_id: int):
    con = _kanban_ro()
    try:
        a = con.execute("select filename, stored_path, size from task_attachments where id = ? and task_id = ?", (attachment_id, task_id)).fetchone()
    finally:
        con.close()
    if not a:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    base = (_kanban_root() / "kanban").resolve()
    target = Path(a["stored_path"]).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Attachment is outside the Kanban store.")
    if not target.is_file() or not a["filename"].lower().endswith(_TEXT_TYPES):
        return {"filename": a["filename"], "size": a["size"], "preview": None, "note": "No text preview for this file type."}
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"filename": a["filename"], "size": a["size"], "truncated": len(text) > 20000, "preview": _scrub(text[:20000])}


# ---------------------------------------------------------------------------
# Task board actions: create / unblock / reassign. These run Hermes' own
# `hermes kanban ...` commands (argument list, no shell) so every rule of the
# board still applies; nothing here writes to kanban.db directly. Requests are
# JSON-only, behind the dashboard login.
# ---------------------------------------------------------------------------
import subprocess
import sys as _sys

from pydantic import BaseModel, Field

_TASK_ID = re.compile(r"^t_[0-9a-f]{6,32}$")
_TEAM = ["default", "scout", "scribe", "socialmediaagent", "youtube-production-agent", "product-factory"]


def _team_profiles() -> list:
    root = _kanban_root()
    return [n for n in _TEAM if ((root if n == "default" else root / "profiles" / n) / "config.yaml").is_file()]


def _run_kanban(args: list, timeout: int = 25) -> str:
    env = dict(os.environ)
    env["HERMES_HOME"] = str(_kanban_root())
    try:
        p = subprocess.run([_sys.executable, "-m", "hermes_cli.main", "kanban", *args],
                           capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="The Kanban command timed out.")
    if p.returncode != 0:
        msg = _scrub(((p.stderr or "") + (p.stdout or "")).strip())
        raise HTTPException(status_code=400, detail=(msg or "The Kanban command failed.")[-400:])
    return p.stdout or ""


def _task_status(task_id: str) -> str:
    if not _TASK_ID.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid task id.")
    con = _kanban_ro()
    try:
        row = con.execute("select status from tasks where id = ?", (task_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found.")
    return (row["status"] or "").lower()


class NewTask(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    body: str = Field(default="", max_length=4000)
    assignee: str = Field(min_length=1, max_length=64)


class UnblockTask(BaseModel):
    reason: str = Field(default="", max_length=300)


class ReassignTask(BaseModel):
    profile: str = Field(min_length=1, max_length=64)


@router.get("/kanban-meta")
def kanban_meta():
    return {"assignees": _team_profiles()}


@router.post("/kanban/tasks")
def kanban_create(payload: NewTask):
    title = " ".join(payload.title.split())
    if not title:
        raise HTTPException(status_code=422, detail="A title is required.")
    if payload.assignee not in _team_profiles():
        raise HTTPException(status_code=400, detail="Unknown assignee.")
    args = ["create", "--assignee", payload.assignee, "--created-by", "dashboard"]
    if payload.body.strip():
        args += ["--body", payload.body.strip()]
    args += ["--", title]
    out = _run_kanban(args)
    m = re.search(r"\bt_[0-9a-f]{6,32}\b", out)
    if not m:
        raise HTTPException(status_code=500, detail="Task was created but its id could not be read.")
    return {"ok": True, "task": kanban_task(m.group(0))}


@router.post("/kanban/{task_id}/unblock")
def kanban_unblock(task_id: str, payload: UnblockTask):
    status = _task_status(task_id)
    if status != "blocked":
        raise HTTPException(status_code=409, detail=f"Only blocked tasks can be unblocked (this one is {status}).")
    reason = " ".join(payload.reason.split()) or "Unblocked from Mission Control"
    _run_kanban(["unblock", "--reason", reason, task_id])
    return {"ok": True, "task": kanban_task(task_id)}


@router.post("/kanban/{task_id}/reassign")
def kanban_reassign(task_id: str, payload: ReassignTask):
    status = _task_status(task_id)
    if status in ("done", "archived"):
        raise HTTPException(status_code=409, detail=f"A {status} task cannot be reassigned. Create a new task instead.")
    if payload.profile != "none" and payload.profile not in _team_profiles():
        raise HTTPException(status_code=400, detail="Unknown assignee.")
    args = ["reassign"]
    if status == "running":
        args.append("--reclaim")
    args += ["--reason", "Reassigned from Mission Control", task_id, payload.profile]
    _run_kanban(args)
    return {"ok": True, "task": kanban_task(task_id)}


# ---------------------------------------------------------------------------
# Content library: read-only view of the agent output drafts the exporter saves
# into the Obsidian vault at 00-Inbox/Agent-Outputs. Only that folder is ever
# read; the rest of the vault is not exposed here.
# ---------------------------------------------------------------------------
_LIB_MAX_NOTE = 200_000


def _vault_root() -> Path:
    v = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not v:
        try:
            for line in (_kanban_root() / ".env").read_text(encoding="utf-8").splitlines():
                if line.startswith("OBSIDIAN_VAULT_PATH="):
                    v = line.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            pass
    return Path(v or "/srv/hermes/obsidian/Precious-AI-Vault")


def _lib_dir() -> Path:
    return _vault_root() / "00-Inbox" / "Agent-Outputs"


def _split_front(text: str):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        k, _, val = line.partition(":")
        if k.strip():
            fm[k.strip()] = val.strip().strip('"')
    return fm, text[end + 4:].lstrip("\n")


def _library_mark():
    d = _lib_dir()
    if not d.is_dir():
        return (0, 0)
    n, newest = 0, 0
    for f in d.rglob("*.md"):
        n += 1
        try:
            newest = max(newest, f.stat().st_mtime_ns)
        except OSError:
            pass
    return (n, newest)


@router.get("/library")
def library(q: str = "", agent: str = ""):
    d = _lib_dir()
    if not d.is_dir():
        return {"available": False, "items": [], "agents": {}, "total": 0}
    needle = q.strip().lower()
    items, agents = [], {}
    for f in d.rglob("*.md"):
        try:
            if f.stat().st_size > 2_000_000:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, body = _split_front(text)
        who = fm.get("agent") or f.parent.name
        agents[who] = agents.get(who, 0) + 1
        if agent and who.lower() != agent.lower():
            continue
        title = fm.get("title") or f.stem
        if needle and needle not in (title + " " + who + " " + body).lower():
            continue
        snippet = ""
        m = re.search(r"^## Result\s*\n+(.+?)(?:\n\n|\Z)", body, re.S | re.M)
        if m:
            snippet = " ".join(m.group(1).split())[:200]
        items.append({
            "path": str(f.relative_to(d)).replace("\\", "/"), "title": _scrub(title, 160), "agent": who,
            "task": fm.get("task"), "status": fm.get("status"), "created": fm.get("created"),
            "completed": fm.get("completed") or fm.get("created"), "size": len(text.encode("utf-8")),
            "snippet": _scrub(snippet, 200),
        })
    items.sort(key=lambda x: x.get("completed") or "", reverse=True)
    return {"available": True, "items": items[:300], "agents": agents, "total": sum(agents.values())}


@router.get("/library/note")
def library_note(path: str):
    d = _lib_dir().resolve()
    target = (d / path).resolve()
    try:
        target.relative_to(d)
    except ValueError:
        raise HTTPException(status_code=403, detail="Outside the agent outputs folder.")
    if target.suffix.lower() != ".md" or not target.is_file():
        raise HTTPException(status_code=404, detail="Note not found.")
    text = target.read_text(encoding="utf-8", errors="replace")
    fm, body = _split_front(text[:_LIB_MAX_NOTE])
    return {"path": path, "frontmatter": fm, "content": _scrub(body), "truncated": len(text) > _LIB_MAX_NOTE,
            "vault_path": "00-Inbox/Agent-Outputs/" + path}
