import json, os, subprocess, sys, time, urllib.request, urllib.error

PY = "/usr/local/lib/hermes-agent/venv/bin/python"
DIR = "/root/.hermes/staging/jarvistest"
srv = subprocess.Popen([PY, DIR + "/serve.py", DIR + "/cc_api.py", DIR + "/static", "9920"], stdout=open(DIR + "/srv.log", "w"), stderr=subprocess.STDOUT)
B = "http://127.0.0.1:9920"
P = B + "/api/plugins/hermes-command-center"


def call(method, url, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode()), round(time.time() - t, 1)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode()), round(time.time() - t, 1)
        except Exception:
            return e.code, {}, round(time.time() - t, 1)


try:
    for _ in range(60):
        try:
            urllib.request.urlopen(P + "/jarvis/settings", timeout=2); break
        except Exception:
            time.sleep(0.5)
    print(open(DIR + "/srv.log").read().strip()[:300])

    st, d, dt = call("GET", P + "/jarvis/env")
    print("env: %s %.1fs" % (st, dt), [(r["label"], r["status"], r["detail"][:34]) for r in d["rows"]])
    st, d, dt = call("GET", P + "/jarvis/tools")
    print("tools: %s %.1fs" % (st, dt), [(t["label"], t["status"]) for t in d["tiles"]])
    st, d, dt = call("GET", P + "/jarvis/health")
    print("health: %s score=%s" % (st, d["score"]), [(i["name"], i["ok"], i["detail"][:40]) for i in d["items"]])
    st, d, dt = call("GET", P + "/jarvis/mission")
    pm = d["primary"] or {}
    print("mission: %s primary=%r progress=%s%% steps=%d projects=%d" % (st, pm.get("name"), pm.get("progress"), len(pm.get("steps", [])), len(d["projects"])))
    st, d, dt = call("GET", P + "/jarvis/voices")
    print("voices: %s n=%d has RyanNeural=%s current=%s" % (st, len(d["voices"]), any(v["name"] == "en-GB-RyanNeural" for v in d["voices"]), d["settings"]["voice"]))
    st, d, dt = call("GET", P + "/jarvis/threads")
    print("threads: %s n=%d" % (st, len(d["threads"])), [(t["label"], t["agent"], t["sessions"]) for t in d["threads"][:8]])
    if d["threads"]:
        t0 = d["threads"][0]
        st2, d2, _ = call("GET", P + "/jarvis/threads/%s/%s" % (t0["profile"], t0["session_id"]))
        print("thread messages:", st2, len(d2.get("messages", [])), "roles:", sorted({m["role"] for m in d2.get("messages", [])}))
    st, d, dt = call("GET", P + "/jarvis/comms")
    print("comms: %s %.1fs mail_ok=%s calendar_ok=%s unread=%d events=%d read_only=%s" % (st, dt, d["mail_ok"], d["calendar_ok"], len(d["unread"]), len(d["events"]), d["read_only"]))
    st, d, dt = call("GET", P + "/jarvis/docs")
    print("docs: %s %d chars" % (st, len(d["content"])))

    print("--- voice")
    sentence = "Good afternoon. All systems are running normally, and your morning briefing is ready."
    st, d, dt = call("POST", P + "/jarvis/speak", {"text": "🧭 Gideon: **Good afternoon.** All systems are running normally, and your morning briefing is ready."})
    print("speak: %s %.1fs voice=%s chars=%s audio=%s" % (st, dt, d.get("voice"), d.get("chars"), (len(d.get("data_url", "")) * 3 // 4 // 1024) if d.get("data_url") else None), "KB")
    if st == 200:
        st2, t, dt2 = call("POST", B + "/api/audio/transcribe", {"data_url": d["data_url"], "mime_type": "audio/mpeg"}, timeout=120)
        print("transcribe (host, local whisper): %s %.1fs -> %r" % (st2, dt2, t.get("transcript") or t))
    print("bad voice:", call("POST", P + "/jarvis/speak", {"text": "hi", "voice": "../etc"})[0], "| bad rate:", call("POST", P + "/jarvis/speak", {"text": "hi", "rate": "fast"})[0])
    print("settings roundtrip:", call("POST", P + "/jarvis/settings", {"tts_enabled": True})[0])

    print("--- host cron api")
    st, d, dt = call("GET", B + "/api/cron/jobs")
    jobs = d if isinstance(d, list) else d.get("jobs", d)
    print("cron jobs:", st, len(jobs) if hasattr(jobs, "__len__") else jobs, [j.get("name") for j in (jobs if isinstance(jobs, list) else [])][:4])
finally:
    srv.terminate()
