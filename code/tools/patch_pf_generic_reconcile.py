"""Product Factory: reconcile files_changed for the Lead Engineer regardless of which worker completed it (run on the server)."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_pf_le_snapshot" not in s, "already patched"

old = '''    for index, worker in enumerate(chain):
        availability = get_worker_availability(worker, policy)'''
new = '''    _pf_le_snapshot = _project_snapshot(state_dir) if specialist == "Lead Engineer" else {}
    for index, worker in enumerate(chain):
        availability = get_worker_availability(worker, policy)'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

old2 = '''    output_dir = state_dir / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{specialist.lower().replace('/', '_').replace(' ', '_')}.json"
    _write_json_file(output_file, result)'''
new2 = '''    if specialist == "Lead Engineer" and result.get("status") == "SUCCESS":
        _reconcile_files_changed(result, state_dir, _pf_le_snapshot)

    output_dir = state_dir / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{specialist.lower().replace('/', '_').replace(' ', '_')}.json"
    _write_json_file(output_file, result)'''
assert s.count(old2) == 1
s = s.replace(old2, new2, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-generic-reconcile-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: files_changed reconciled for Lead Engineer regardless of worker")
