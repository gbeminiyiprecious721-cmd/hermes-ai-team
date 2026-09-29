"""Product Factory: when Codex is the Lead Engineer's FALLBACK it must actually be able to write the project's files (run on the server).
Before: Lead Engineer falling back to Codex used the default read-only sandbox -> Codex could describe an implementation but write nothing ->
Build gate correctly failed with "No implementation files were recorded", making Claude Code's earlier failure look like a Codex failure too.
After: Codex for Lead Engineer writes directly into the real project folder with --sandbox workspace-write and network disabled
(-c sandbox_workspace_write.network_access=false); QA keeps its own disposable-copy behaviour, unchanged. Validated before replacing the file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "network_access=false" not in s, "already patched"

old_sig = 'def _invoke_codex_once(prompt: str, state_dir: Path, specialist: str, work_dir: Optional[Path] = None, sandbox: str = "read-only") -> dict:'
new_sig = 'def _invoke_codex_once(prompt: str, state_dir: Path, specialist: str, work_dir: Optional[Path] = None, sandbox: str = "read-only", extra_config: Optional[list] = None) -> dict:'
assert s.count(old_sig) == 1
s = s.replace(old_sig, new_sig, 1)

old_cmd = '''            [CODEX_PATH, "exec", "--sandbox", sandbox,
             "--skip-git-repo-check", "--ephemeral", "--color", "never",
             "-C", str(work_dir), "-o", str(result_file), "-"],'''
new_cmd = '''            [CODEX_PATH, "exec", "--sandbox", sandbox]
            + [item for cfg in (extra_config or []) for item in ("-c", cfg)]
            + ["--skip-git-repo-check", "--ephemeral", "--color", "never",
               "-C", str(work_dir), "-o", str(result_file), "-"],'''
assert s.count(old_cmd) == 1
s = s.replace(old_cmd, new_cmd, 1)

old_wrap = '''def invoke_codex(prompt: str, state_dir: Path, specialist: str) -> dict:
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
        shutil.rmtree(scratch, ignore_errors=True)'''
new_wrap = '''_PF_NO_NETWORK_CFG = "sandbox_workspace_write.network_access=false"


def invoke_codex(prompt: str, state_dir: Path, specialist: str) -> dict:
    """Codex call.
    - QA Agent: a throwaway COPY of the project (writable, no network) so its tests can create temp files; the real project is untouched.
    - Lead Engineer (fallback from Claude Code): writes directly into the real project, writable but no network, so a fallback can actually
      deliver the implementation instead of only describing one that never gets recorded.
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
    if specialist == "Lead Engineer":
        return _invoke_codex_once(prompt, state_dir, specialist, sandbox="workspace-write", extra_config=[_PF_NO_NETWORK_CFG])
    return _invoke_codex_once(prompt, state_dir, specialist)'''
assert s.count(old_wrap) == 1
s = s.replace(old_wrap, new_wrap, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-codex-write-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: Codex as Lead Engineer's fallback now writes into the real project, no network")
