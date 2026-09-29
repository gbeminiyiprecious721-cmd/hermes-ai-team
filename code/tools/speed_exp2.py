"""Same prompt the Jarvis page sends (voice hint + live facts + question), across the three speed modes."""
import json, os, select, subprocess, sys, time, urllib.request

PY = "/usr/local/lib/hermes-agent/venv/bin/python"
BRIEF = json.loads(urllib.request.urlopen("http://127.0.0.1:9920/api/plugins/hermes-command-center/jarvis/brief", timeout=20).read().decode())["text"]
HINT = ("[Spoken conversation through the Jarvis dashboard. Reply in one to three short plain sentences with no markdown, tables or emoji. "
        "Use the live facts below when they answer the question. Answer from what you already know whenever you can, run at most one tool, "
        "and if you still cannot find something say so in one short sentence. If the full answer is long, give a short spoken summary and say the detail is on screen.]\n\n")
QUESTIONS = [
    ("How many unread emails are in my inbox?", ["2906", "2,906"]),
    ("What time does my morning briefing run?", ["08:00", "8:00", "8 am", "8 a.m", "eight"]),
    ("How many tasks are on the board, and what state are they in?", ["3", "three"]),
    ("When does the topic news digest run next?", ["18:00", "6 pm", "6:00", "weekday", "2 h", "two hours"]),
    ("How healthy is the system?", ["100"]),
]
MODES = {
    "fastest (nano)": {"provider": "openrouter", "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "reasoning_effort": "low"},
    "balanced (nemotron-super)": {"provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free", "reasoning_effort": "low"},
    "nex-n2.5-pro": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-pro:free", "reasoning_effort": "low"},
}
env = dict(os.environ, HERMES_HOME="/root/.hermes", PYTHONUNBUFFERED="1")
p = subprocess.Popen([PY, "-m", "tui_gateway.entry"], cwd="/usr/local/lib/hermes-agent", env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
nid = [1]
frames = []


def send(method, params):
    i = nid[0]; nid[0] += 1
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n"); p.stdin.flush()
    return i


def pump(timeout):
    r, _, _ = select.select([p.stdout], [], [], timeout)
    if not r:
        return None
    line = p.stdout.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except Exception:
        return None


def wait(pred, timeout):
    end = time.time() + timeout
    while time.time() < end:
        m = pump(0.3)
        if m and pred(m):
            return m
        if m:
            frames.append((time.time(), m))
    return None


wait(lambda m: m.get("method") == "event" and m["params"].get("type") == "gateway.ready", 60)
only = sys.argv[1] if len(sys.argv) > 1 else None
for name, extra in MODES.items():
    if only and only not in name:
        continue
    rid = send("session.create", dict({"cols": 100, "hidden": True, "title": "speedtest2"}, **extra))
    resp = wait(lambda m: m.get("id") == rid, 90)
    sid = resp["result"]["session_id"]
    ok = 0; times = []; lines = []
    for q, needles in QUESTIONS:
        frames.clear()
        t0 = time.time()
        send("prompt.submit", {"session_id": sid, "text": HINT + BRIEF + "\n\n" + q})
        done = wait(lambda m: m.get("method") == "event" and m["params"].get("type") in ("message.complete", "error"), 100)
        dt = time.time() - t0
        tools = sum(1 for _, f in frames if f.get("method") == "event" and f["params"].get("type") == "tool.start")
        txt = ((done or {}).get("params", {}).get("payload", {}) or {}).get("text", "") if done else ""
        good = any(n.lower() in txt.lower() for n in needles)
        ok += good; times.append(dt)
        lines.append(f"   {'OK ' if good else 'BAD'} {dt:5.1f}s tools={tools} | {q[:44]:44s} -> {txt.replace(chr(10), ' ')[:90]}")
    print(f"{name}: correct {ok}/{len(QUESTIONS)}, median {sorted(times)[len(times)//2]:.1f}s, worst {max(times):.1f}s", flush=True)
    print("\n".join(lines), flush=True)
    send("session.close", {"session_id": sid})
p.terminate()
