"""Product Factory: attach the pipeline's REAL sandbox test record to the Lead Engineer result (run on the server).
The evidence check reads the stored result, so the record must live in result["artifacts"]["verification"]; the worker's own claim is kept
as artifacts["worker_reported_verification"]. Replaces the wrapper installed by patch_pf_repair.py. Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_attach_director_verification" not in s, "already patched"
a = s.index("def invoke_claude_code(")
b = s.index("def _invoke_claude_code_once(")

WRAPPER = '''def _attach_director_verification(result: dict, record: dict) -> None:
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
    result = _invoke_claude_code_once(prompt, state_dir, specialist)
    if specialist != "Lead Engineer":
        return result
    for round_no in (0, 1, 2):
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
            + "\\n\\nREPAIR ROUND " + str(round_no + 1) + " of 2. The pipeline ran your project's unit tests in a sandbox and they FAILED "
            + "(exit code " + str(record.get("exit_code")) + "). Real output (last part):\\n" + str(detail)[-4000:]
            + "\\n\\nFix the implementation, or a test that is wrong, using your Read/Edit/Write tools. Keep every file inside the project folder. "
            + "Then return the same JSON object again with files_changed listing every project file. Do NOT claim the tests passed: "
            + "you cannot run them, the pipeline will run them again."
        )
        result = _invoke_claude_code_once(repair, state_dir, specialist)
    return result


'''
s = s[:a] + WRAPPER + s[b:]
shutil.copy(p, "/root/backups/manual-changes/director.py.before-repair2-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: director verification record is attached to the Lead Engineer result after every attempt")
