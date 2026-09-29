"""Product Factory: fix a pre-existing schema mismatch in the Testing gate (run on the server, unrelated to the Claude/Codex fixes).
The QA prompt asks for test_results as ONE object {command, exit_code, passed, failed}, but a genuine independent QA naturally runs
several checks (the project's own tests plus its own independent probes) and both Claude Code and Codex correctly returned a LIST of
run records - which the gate validator (written for a single dict) then rejected even when every run passed with exit_code 0.
Fix: accept either shape; a list passes only if every entry ran (has a command) and exited 0 with no reported failures.
Also clarifies the prompt so future runs are not guessing the shape. Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_testing_gate_passed" not in s, "already patched"

old_fn = '''    elif gate_name == "Testing":
        test_results = artifacts.get("test_results")
        if (not isinstance(test_results, dict)
                or test_results.get("exit_code") != 0
                or test_results.get("failed", 0) != 0):
            issues.append("Passing executable test results are missing.")'''
new_fn = '''    elif gate_name == "Testing":
        if not _testing_gate_passed(artifacts.get("test_results")):
            issues.append("Passing executable test results are missing.")'''
assert s.count(old_fn) == 1
s = s.replace(old_fn, new_fn, 1)

HELPER = '''def _testing_gate_passed(test_results) -> bool:
    """True if test_results shows real, passing, executed test runs. Accepts either the documented single
    {command, exit_code, passed, failed} object or a LIST of such runs (a genuine independent QA naturally runs
    more than one check: the project's own suite plus its own probes)."""
    def run_ok(run) -> bool:
        if not isinstance(run, dict) or not run.get("command"):
            return False
        if run.get("exit_code") != 0:
            return False
        failed = run.get("failed")
        if isinstance(failed, list) and failed:
            return False
        if isinstance(failed, (int, float)) and failed not in (0, 0.0):
            return False
        return True

    if isinstance(test_results, dict):
        return run_ok(test_results)
    if isinstance(test_results, list) and test_results:
        return all(run_ok(r) for r in test_results)
    return False


'''
a = s.index('def _validate_gate_evidence(gate_name: str, artifacts: dict) -> list[str]:')
s = s[:a] + HELPER + s[a:]

old_prompt = '"Also include test_results ({command, exit_code, passed, failed}), independent_review=true, and evidence from executed checks.",'
new_prompt = ('"Also include test_results: a LIST of the checks you actually ran, each {command, exit_code, passed, failed} - '
              "one entry per command (the project's own test suite AND your own independent checks). Every entry needs "
              'exit_code 0 and an empty/zero failed for the gate to pass. Also independent_review=true, and evidence from executed checks.",')
assert s.count(old_prompt) == 1
s = s.replace(old_prompt, new_prompt, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-testing-gate-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: Testing gate accepts a list of passing test runs, not only a single object")
