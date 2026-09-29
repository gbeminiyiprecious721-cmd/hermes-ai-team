"""Product Factory: Codex QA works in a throwaway COPY of the project (run on the server).
Before: codex exec --sandbox read-only in the real project -> tests that need a temp directory cannot run ("No usable temporary directory").
After : QA Agent gets a scratch copy under /tmp with --sandbox workspace-write (writes only inside the copy, no network); the copy is deleted afterwards;
        the real project is never writable by QA. Other Codex uses are unchanged. Timeout 180 -> 420 s. Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_invoke_codex_once" not in s, "already patched"

a = s.index("def invoke_codex(")
b = s.find("\ndef ", a + 10)
b = len(s) if b < 0 else b + 1
fn = s[a:b]

reps = [
    ("def invoke_codex(prompt: str, state_dir: Path, specialist: str) -> dict:",
     "def _invoke_codex_once(prompt: str, state_dir: Path, specialist: str, work_dir: Optional[Path] = None, sandbox: str = \"read-only\") -> dict:"),
    ('    result_file = state_dir / "codex_last_message.json"\n',
     '    result_file = state_dir / "codex_last_message.json"\n    work_dir = work_dir or state_dir\n'),
    ('"--sandbox", "read-only",', '"--sandbox", sandbox,'),
    ('"-C", str(state_dir), "-o", str(result_file), "-"],', '"-C", str(work_dir), "-o", str(result_file), "-"],'),
    ("            timeout=180,\n            cwd=str(state_dir)\n        )", "            timeout=420,\n            cwd=str(work_dir)\n        )"),
]
for old, new in reps:
    assert fn.count(old) == 1, (fn.count(old), old[:60])
    fn = fn.replace(old, new, 1)

WRAPPER = '''def invoke_codex(prompt: str, state_dir: Path, specialist: str) -> dict:
    """Codex call. QA works in a throwaway copy of the project (writable scratch, no network) so its tests can create temp files;
    the real project stays untouched. Other specialists keep the read-only sandbox in the real project."""
    if specialist != "QA Agent":
        return _invoke_codex_once(prompt, state_dir, specialist)
    scratch = Path(tempfile.mkdtemp(prefix="pf-qa-", dir="/tmp"))
    try:
        work = scratch / "project"
        shutil.copytree(state_dir, work, ignore=shutil.ignore_patterns("knowledge_staging", ".claude", "__pycache__", "*.pyc"))
        return _invoke_codex_once(prompt, state_dir, specialist, work_dir=work, sandbox="workspace-write")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


'''
s = s[:a] + WRAPPER + fn + s[b:]
shutil.copy(p, "/root/backups/manual-changes/director.py.before-qa-scratch-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: QA Agent runs Codex in a scratch copy with workspace-write")
