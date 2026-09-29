"""Product Factory: Claude Code needs more turns to REWORK many files, and failures must show Claude's real message (run on the server).
- --max-turns 10 -> 30, timeout 600 -> 900 s (inside _invoke_claude_code_once only)
- non-zero exit: include the JSON result (subtype / result / errors) from stdout, not only the (empty) stderr, so quota, max-turns and
  auth problems are distinguishable and quota problems are recognised by the existing failure classifier.
Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
a = s.index("def _invoke_claude_code_once(")
b = s.find("\ndef ", a + 10)
b = len(s) if b < 0 else b + 1
fn = s[a:b]
assert '"--max-turns", "30"' not in fn, "already patched"

reps = [
    ('"--max-turns", "10",', '"--max-turns", "30",'),
    ("timeout=600,", "timeout=900,"),
    ('errors=["Claude Code invocation timed out after 600 seconds."]', 'errors=["Claude Code invocation timed out after 900 seconds."]'),
    ('''            stderr = result.stderr[:500] if result.stderr else ""
            return canonical(''',
     '''            stderr = result.stderr[:500] if result.stderr else ""
            detail = ""
            try:
                payload = json.loads(result.stdout or "{}")
                if isinstance(payload, dict):
                    detail = " | ".join(str(payload.get(k))[:300] for k in ("subtype", "result", "errors") if payload.get(k))
            except ValueError:
                detail = (result.stdout or "")[:300]
            if detail:
                stderr = (stderr + " claude_output: " + detail)[:900]
            return canonical('''),
]
for old, new in reps:
    assert fn.count(old) == 1, (fn.count(old), old[:70])
    fn = fn.replace(old, new, 1)
s = s[:a] + fn + s[b:]
shutil.copy(p, "/root/backups/manual-changes/director.py.before-claude-limits-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: max-turns 30, timeout 900 s, failures now include Claude's own message")
