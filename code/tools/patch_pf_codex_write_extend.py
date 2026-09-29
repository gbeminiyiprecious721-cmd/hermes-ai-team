"""Product Factory: extend the Lead Engineer's Codex-fallback write-access fix to Data/ML Engineer and ML/AI Evaluation Agent (run on the server).
routing_policy.yaml routes both of these to codex as an implementation_fallback/evaluation_fallback, exactly like Lead Engineer's
fallback - so without this they would hit the SAME bug already proven and fixed for Lead Engineer: Codex could describe an
implementation but never actually save it, because the code only special-cased the literal string "Lead Engineer". This has never
been exercised by a real run (no Data/ML or AI_AGENT project has been tested), so it is a proactive fix based on an already-proven
bug pattern, not a speculative change - only the fallback path is affected, so it has zero effect while Claude Code succeeds (the
normal case). Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert 'if specialist in ("Lead Engineer", "Data/ML Engineer"' not in s, "already patched"

old = '''    if specialist == "Lead Engineer":
        return _invoke_codex_once(prompt, state_dir, specialist, sandbox="workspace-write", extra_config=[_PF_NO_NETWORK_CFG])
    return _invoke_codex_once(prompt, state_dir, specialist)'''
new = '''    if specialist in ("Lead Engineer", "Data/ML Engineer", "ML/AI Evaluation Agent"):
        return _invoke_codex_once(prompt, state_dir, specialist, sandbox="workspace-write", extra_config=[_PF_NO_NETWORK_CFG])
    return _invoke_codex_once(prompt, state_dir, specialist)'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

old_doc = '''    - Lead Engineer (fallback from Claude Code): writes directly into the real project, writable but no network, so a fallback can actually
      deliver the implementation instead of only describing one that never gets recorded.
    - Everything else: read-only sandbox in the real project (unchanged)."""'''
new_doc = '''    - Lead Engineer, Data/ML Engineer, ML/AI Evaluation Agent (fallback from Claude Code): writes directly into the real project,
      writable but no network, so a fallback can actually deliver the implementation instead of only describing one that never
      gets recorded. All three route Claude Code first and Codex only as their fallback in routing_policy.yaml.
    - Everything else: read-only sandbox in the real project (unchanged)."""'''
assert s.count(old_doc) == 1
s = s.replace(old_doc, new_doc, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-codex-write-extend-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: Codex-as-fallback write access now also covers Data/ML Engineer and ML/AI Evaluation Agent")
