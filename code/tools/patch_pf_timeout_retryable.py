"""Product Factory: a model call that simply timed out was being classified the same as a hard failure (run on the server).
_provider_failure_kind() only recognised "overloaded"/"service unavailable"/HTTP 502-504 etc. as RETRYABLE_OVERLOAD. A plain
"Model invocation timed out after 120 seconds." fell through to FAILED, which invoke_specialist then caches as a hard
UNAVAILABLE for overload_cooldown_seconds (default 300s) - so an immediate retry (e.g. a --resume right after) does not even
attempt the model again, it just replays the cached failure. A timeout is clearly transient. Fix: classify it as
RETRYABLE_OVERLOAD, matching the design that already exists for exactly this case (TEMPORARILY_UNAVAILABLE is never cached,
so the very next call retries for real). Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert '"timed out"' not in s, "already patched"

old = '''    if any(token in text for token in (
        "overloaded", "temporarily unavailable", "service unavailable",
        "upstream error", "retryable: true", "http 502", "http 503", "http 504",
    )):
        return "RETRYABLE_OVERLOAD"'''
new = '''    if any(token in text for token in (
        "overloaded", "temporarily unavailable", "service unavailable",
        "upstream error", "retryable: true", "http 502", "http 503", "http 504",
        "timed out", "timeout", "connection reset", "connection aborted", "read timed out",
    )):
        return "RETRYABLE_OVERLOAD"'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-timeout-retryable-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: a model timeout is now RETRYABLE_OVERLOAD, so it is never cached as a hard UNAVAILABLE")
