"""Product Factory: repair loop for the Lead Engineer (run on the server).
After Claude Code writes the implementation, the pipeline runs the project's tests in the sandbox. If they fail, Claude gets the REAL failure
output and up to 2 repair rounds; the Build gate then re-runs the tests independently. Idempotent, validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_invoke_claude_code_once" not in s, "already patched"
assert "def run_sandboxed_verification" in s, "apply the verifier patch first"

a = s.index("def invoke_claude_code(")
prev = s[max(0, a - 80):a]
assert "@" not in prev.splitlines()[-1] if prev.splitlines() else True

WRAPPER = '''def invoke_claude_code(prompt: str, state_dir: Path, specialist: str) -> dict:
    """Claude Code call with a bounded repair loop for the Lead Engineer.

    Claude has no shell, so the pipeline runs the project's tests in a sandbox. On failure Claude receives the real output and
    up to 2 repair rounds; the Build gate re-runs the tests independently afterwards. Other specialists are single calls."""
    result = _invoke_claude_code_once(prompt, state_dir, specialist)
    if specialist != "Lead Engineer":
        return result
    for round_no in (1, 2):
        try:
            artifacts = _extract_artifacts(result)
        except Exception:
            return result
        files = artifacts.get("files_changed") if isinstance(artifacts, dict) else None
        if result.get("status") != "SUCCESS" or not isinstance(files, list) or not files:
            return result
        record = run_sandboxed_verification(state_dir, files)
        if record is None or record.get("exit_code") == 0:
            return result
        try:
            detail = json.loads((state_dir / "outputs" / "build_verification.json").read_text(encoding="utf-8")).get("full_output", "")
        except (OSError, ValueError):
            detail = record.get("summary", "")
        repair = (
            prompt
            + "\\n\\nREPAIR ROUND " + str(round_no) + " of 2. The pipeline ran your project's unit tests in a sandbox and they FAILED "
            + "(exit code " + str(record.get("exit_code")) + "). Real output (last part):\\n" + str(detail)[-4000:]
            + "\\n\\nFix the implementation, or a test that is wrong, using your Read/Edit/Write tools. Keep every file inside the project folder. "
            + "Then return the same JSON object again with files_changed listing every project file. Do NOT claim the tests passed: "
            + "you cannot run them, the pipeline will run them again."
        )
        result = _invoke_claude_code_once(repair, state_dir, specialist)
    return result


'''

s = s[:a] + WRAPPER + s[a:].replace("def invoke_claude_code(", "def _invoke_claude_code_once(", 1)
# the timeout message inside the single-call function still said 180 s
s = s.replace('errors=["Claude Code invocation timed out after 180 seconds."]', 'errors=["Claude Code invocation timed out after 600 seconds."]', 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-repair-loop-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: invoke_claude_code now wraps _invoke_claude_code_once with a 2-round repair loop")
