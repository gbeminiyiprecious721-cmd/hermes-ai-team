"""Product Factory: the pipeline (not the model) runs the project's unit tests in a throwaway sandbox and records the real result.
Why: the Lead Engineer has no shell (by design), so it cannot produce the passing 'verification' record the Build gate requires.
Sandbox: a COPY of the project's implementation files in /tmp, owned by 'nobody', no network (unshare -n), no new privileges,
CPU/memory/process/file-size limits and a hard timeout. Idempotent, validated (py_compile) before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "run_sandboxed_verification" not in s, "already patched"

FUNC = '''def run_sandboxed_verification(state_dir: Path, recorded_paths: list) -> Optional[dict]:
    """Run the project's own unit tests in a throwaway sandbox and return an honest verification record (or None if there are no tests).

    The Lead Engineer has no shell, so the pipeline runs the tests itself: a COPY of the implementation files, user 'nobody',
    no network, no new privileges, CPU/memory/process/file-size limits, hard timeout. The real exit code is recorded, pass or fail."""
    root = state_dir.resolve()
    rels = []
    for raw in recorded_paths or []:
        candidate = (root / str(raw)).resolve()
        try:
            rel = candidate.relative_to(root)
        except ValueError:
            continue
        if not candidate.is_file() or candidate.stat().st_size > 1_000_000:
            continue
        if rel.parts and rel.parts[0] in ("outputs", "knowledge_staging", ".claude"):
            continue
        rels.append(rel)
    tests = [r for r in rels if r.name.startswith("test_") and r.suffix == ".py"]
    if not tests:
        return None
    sandbox = tempfile.mkdtemp(prefix="pf-verify-", dir="/tmp")
    try:
        for rel in rels:
            dst = Path(sandbox) / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, dst)
        for dirpath, dirnames, filenames in os.walk(sandbox):
            os.chown(dirpath, 65534, 65534)
            for name in filenames:
                os.chown(os.path.join(dirpath, name), 65534, 65534)
        os.chmod(sandbox, 0o700)
        test_dir = tests[0].parent.as_posix() or "."
        cmd = ["python3", "-m", "unittest", "discover", "-s", test_dir, "-v"]
        wrapped = (["unshare", "-n", "--", "setpriv", "--reuid=65534", "--regid=65534", "--clear-groups", "--no-new-privs",
                    "prlimit", "--cpu=60", "--as=1073741824", "--nproc=128", "--fsize=52428800", "--", "timeout", "120"] + cmd)
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": sandbox, "PYTHONPATH": sandbox,
               "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}
        try:
            result = subprocess.run(wrapped, cwd=sandbox, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=150)
            code = result.returncode
            output = ((result.stdout or "") + "\\n" + (result.stderr or "")).strip()
        except subprocess.TimeoutExpired:
            code, output = 124, "Timed out after 150 seconds."
        except OSError as exc:
            code, output = 127, f"Sandbox could not start: {exc}"
        lines = [ln for ln in output.splitlines() if ln.strip()]
        tail = " | ".join(lines[-6:])[:900] if lines else "no output"
        record = {
            "command": "python3 -m unittest discover -s " + test_dir + " -v (run by the pipeline in a sandbox: copy of the files, user nobody, no network, 120 s / 1 GB limits)",
            "exit_code": code,
            "summary": tail,
            "run_by": "director_sandbox",
            "test_files": [t.as_posix() for t in tests],
        }
        try:
            out_dir = state_dir / "outputs"
            out_dir.mkdir(exist_ok=True)
            (out_dir / "build_verification.json").write_text(json.dumps(dict(record, full_output=output[-8000:]), indent=2), encoding="utf-8")
        except OSError:
            pass
        return record
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


'''

a = s.index("def validate_build_gate(")
# the Build gate is registered by a decorator on the line above it: insert BEFORE that decorator line, not between
NLC = chr(10)
line_start = s.rfind(NLC, 0, a) + 1
prev_start = s.rfind(NLC, 0, line_start - 1) + 1
prev_line = s[prev_start:line_start].strip()
if prev_line.startswith("@"):
    a = prev_start
s = s[:a] + FUNC + s[a:]

old = '''    verification = artifacts.get("verification")
    if not isinstance(verification, dict):
        issues.append("Build verification record is missing.")'''
new = '''    verification = artifacts.get("verification")
    worker_ran_it = isinstance(verification, dict) and verification.get("exit_code") == 0 and verification.get("command")
    if not worker_ran_it and recorded_paths:
        director_record = run_sandboxed_verification(state_dir, recorded_paths)
        if director_record is not None:
            artifacts["worker_reported_verification"] = verification
            artifacts["verification"] = verification = director_record
    if not isinstance(verification, dict):
        issues.append("Build verification record is missing.")'''
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-verifier-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: run_sandboxed_verification added and wired into validate_build_gate")
