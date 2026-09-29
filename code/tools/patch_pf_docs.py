"""Product Factory: fill the generated PRD / ARCHITECTURE / implementation_plan documents from the specialists' real output (run on the server),
and make the 'rework exhausted' blocker list what QA still reports. Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "fill_project_documents" not in s, "already patched"

HELPERS = '''# ---- documents: fill the template placeholders from what the specialists actually produced ----
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
        return "\\n".join(f"- {k}: {_doc_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "\\n".join("- " + (item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)) for item in value)
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
        text = re.sub(r"\\{[a-z_]+\\}", _NOT_SPECIFIED, text)
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
    text = text.replace("{list_of_gates}", "\\n".join("- " + str(g) for g in quality_gates) or _NOT_SPECIFIED)
    text = text.replace("{approval_points}", "\\n".join("- " + str(a) for a in approval_points) or "None required for this project.")
    text = text.replace("{knowledge_to_capture}", "Staged under knowledge_staging/ (never written to a real vault without approval).")
    path.write_text(text, encoding="utf-8")


'''

a = s.index("MAX_QA_REWORK_ROUNDS = 2")
s = s[:a] + HELPERS + s[a:]

# hook 1: after a specialist passes its gate
old = '''        state["specialists_completed"].append(specialist)
        state["pending_specialists"] = specialists[index + 1:]'''
new = '''        fill_project_documents(state_dir, specialist, result)
        state["specialists_completed"].append(specialist)
        state["pending_specialists"] = specialists[index + 1:]'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

# hook 2: before the specialist loop (covers resumed projects whose documents were never filled)
old = '''    for index, specialist in enumerate(specialists):
        if specialist in state["specialists_completed"]:
            continue'''
new = '''    refill_documents_from_outputs(state_dir)
    for index, specialist in enumerate(specialists):
        if specialist in state["specialists_completed"]:
            continue'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

# hook 3: plan document filled before finalization
old = "    unresolved_gates = [gate for gate in quality_gates"
assert s.count(old) == 1
s = s.replace(old, "    fill_plan_document(state_dir, quality_gates, approval_points)\n" + old, 1)

# hook 4: when the rework budget is used up, say exactly what QA still reports
old = "    return result, aggregate\n\n\n"
assert s.count(old) == 1, s.count(old)
new = '''    if aggregate.get("status") != "PASS" and state.get("rework_rounds"):
        try:
            remaining = _extract_artifacts(result).get("bugs_found") or []
        except Exception:
            remaining = []
        summary = "; ".join(f"{b.get('id', '?')} ({b.get('severity', '?')}): {b.get('summary', '')}" for b in remaining if isinstance(b, dict))[:900]
        aggregate = dict(aggregate)
        aggregate["reason"] = (str(aggregate.get("reason", "")) + f" After {len(state['rework_rounds'])} rework round(s) QA still reports: "
                               + (summary or "see outputs/qa_agent.json") + ". Needs a human decision.")
    return result, aggregate


'''
s = s.replace(old, new, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-docs-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: documents are filled from specialist output; rework-exhausted blocker lists QA's remaining findings")
