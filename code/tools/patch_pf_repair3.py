"""Product Factory: record the files Claude Code REALLY wrote (from the filesystem), not the list it reports (run on the server).
Adds a snapshot/diff around each Claude call for the Lead Engineer; artifacts["files_changed"] becomes the observed set
(changed files + existing files it claimed + all project .py files); the model's own list is kept as worker_reported_files_changed.
Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_reconcile_files_changed" not in s, "already patched"

HELPERS = '''_PF_EXCLUDE_DIRS = {"outputs", "knowledge_staging", ".claude", "__pycache__", ".git"}
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


'''

a = s.index("def _attach_director_verification(")
s = s[:a] + HELPERS + s[a:]

old1 = '''    result = _invoke_claude_code_once(prompt, state_dir, specialist)
    if specialist != "Lead Engineer":
        return result
    for round_no in (0, 1, 2):'''
new1 = '''    before = _project_snapshot(state_dir) if specialist == "Lead Engineer" else {}
    result = _invoke_claude_code_once(prompt, state_dir, specialist)
    if specialist != "Lead Engineer":
        return result
    for round_no in (0, 1, 2):
        if result.get("status") == "SUCCESS":
            _reconcile_files_changed(result, state_dir, before)'''
assert s.count(old1) == 1
s = s.replace(old1, new1, 1)

old2 = '''        result = _invoke_claude_code_once(repair, state_dir, specialist)
    return result'''
new2 = '''        before = _project_snapshot(state_dir)
        result = _invoke_claude_code_once(repair, state_dir, specialist)
    return result'''
assert s.count(old2) == 1
s = s.replace(old2, new2, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-repair3-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: files_changed now comes from the filesystem")
