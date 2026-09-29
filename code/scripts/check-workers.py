import importlib.util, yaml, os, sys
PF="/root/.hermes/profiles/product-factory"
os.chdir(PF+"/skills/hermes-director"); sys.path.insert(0, os.getcwd())
spec=importlib.util.spec_from_file_location("director","director.py"); d=importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
pol=yaml.safe_load(open(PF+"/policies/routing_policy.yaml"))
for w in ("claude_code","codex","nemotron","nous","gemini"):
    r=d.get_worker_availability(w, pol, force=True)
    print(f"{w:12s} {str(r.get('status')):14s} {str(r.get('reason'))[:100]}")
