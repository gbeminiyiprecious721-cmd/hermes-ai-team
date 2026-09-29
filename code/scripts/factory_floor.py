#!/usr/bin/env python3
"""Factory Floor feed: posts one line per team event to a Telegram topic.

Sources (read-only): the Kanban board (all agents) and the Product Factory project state
files (the 11 specialists). Sends with the Bot API sendMessage, which does not conflict
with the gateway's polling. The bot token is read from .env and never printed.
"""
import json, os, sqlite3, sys, time, urllib.request, urllib.error
from pathlib import Path

HOME = Path("/root/.hermes")
CHAT_ID = "-100XXXXXXXXXX"
THREAD_ID = 247
POLL_SECONDS = 5
MAX_LINES_PER_MESSAGE = 12
STATE_FILE = HOME / "factory-floor" / "cursor.json"
KANBAN_DB = HOME / "kanban.db"
PF_PROJECTS = HOME / "profiles" / "product-factory" / "runtime" / "projects"

AGENT = {
    "default": "🧭 Gideon",
    "scout": "🔎 Scout",
    "scribe": "✍️ Scribe",
    "socialmediaagent": "📣 Reach",
    "youtube-production-agent": "🎬 Production",
    "product-factory": "🏗 Product Factory",
}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def token():
    for line in (HOME / ".env").read_text().splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("TELEGRAM_BOT_TOKEN not found")


TOKEN = token()


def send(text):
    data = json.dumps({
        "chat_id": CHAT_ID, "message_thread_id": THREAD_ID, "text": text,
        "disable_notification": True, "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data,
        headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status == 200
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = json.loads(e.read().decode()).get("description", "")
            except Exception:
                pass
            if e.code == 429:
                time.sleep(5 * (attempt + 1)); continue
            log(f"send failed: HTTP {e.code} {body}")  # never log the URL (it holds the token)
            return False
        except Exception as e:
            log(f"send failed: {type(e).__name__}")
            time.sleep(2)
    return False


def clip(s, n=140):
    s = " ".join(str(s or "").split()).replace("—", ":").replace("–", "-")
    return s if len(s) <= n else s[: n - 1] + "…"


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return None


def save_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st))
    tmp.replace(STATE_FILE)


def kanban_lines(last_id):
    lines, max_id = [], last_id
    if not KANBAN_DB.exists():
        return lines, max_id
    con = sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True, timeout=5)
    try:
        rows = con.execute(
            "select e.id, e.kind, e.payload, t.id, t.title, t.assignee from task_events e "
            "join tasks t on t.id = e.task_id where e.id > ? order by e.id", (last_id,)).fetchall()
    finally:
        con.close()
    for eid, kind, payload, tid, title, assignee in rows:
        max_id = max(max_id, eid)
        who = AGENT.get(assignee or "default", assignee or "unassigned")
        t = clip(title, 90)
        if kind == "created":
            lines.append(f"📋 New task for {who}: {t} ({tid})")
        elif kind == "spawned":
            lines.append(f"▶️ {who} started: {t}")
        elif kind == "completed":
            lines.append(f"✅ {who} finished: {t}")
        elif kind == "blocked":
            reason = ""
            try:
                reason = json.loads(payload or "{}").get("reason", "")
            except Exception:
                pass
            lines.append(f"⛔ {who} blocked: {t}" + (f" ({clip(reason, 80)})" if reason else ""))
        elif kind in ("crashed", "timed_out", "spawn_failed", "gave_up", "failed"):
            lines.append(f"⚠️ {who} problem ({kind}): {t}")
    return lines, max_id


PF_ICON = {"STARTED": "▶️", "COMPLETED": "✅", "BLOCKED": "⛔", "FAILED": "⚠️", "PASSED": "✅",
           "FINALIZED": "🏁", "APPROVAL": "🛂"}


def pf_events():
    out = []
    if not PF_PROJECTS.is_dir():
        return out
    for sf in PF_PROJECTS.glob("*/state.json"):
        try:
            st = json.loads(sf.read_text())
        except Exception:
            continue
        for e in st.get("activity", []) or []:
            key = f"{sf.parent.name}|{e.get('timestamp')}|{e.get('event')}"
            out.append((e.get("timestamp") or "", key, sf.parent.name, e))
    out.sort(key=lambda x: x[0])
    return out


def pf_line(project, e):
    ev = str(e.get("event", ""))
    icon = "🏗"
    for k, v in PF_ICON.items():
        if k in ev:
            icon = v; break
    who = e.get("specialist") or e.get("worker") or "Product Factory"
    return f"{icon} 🏗 {clip(who, 40)} ({clip(project, 32)}): {clip(e.get('detail') or ev, 130)}"


def main():
    st = load_state()
    first = st is None
    if first:  # start from "now": do not replay history
        last_id = 0
        try:
            con = sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True, timeout=5)
            last_id = con.execute("select coalesce(max(id),0) from task_events").fetchone()[0]
            con.close()
        except Exception:
            pass
        st = {"kanban_last_id": last_id, "pf_seen": [k for _, k, _, _ in pf_events()]}
        save_state(st)
        send("🟢 Factory Floor is live. I post one line here when an agent or a Product Factory specialist starts, finishes, gets blocked or hits a problem.")
        log("initialised")
    seen = set(st["pf_seen"])
    log("running")
    while True:
        try:
            lines, new_last = kanban_lines(st["kanban_last_id"])
            new_pf = []
            for _, key, proj, e in pf_events():
                if key not in seen:
                    seen.add(key); new_pf.append(pf_line(proj, e))
            lines += new_pf
            for i in range(0, len(lines), MAX_LINES_PER_MESSAGE):
                if not send("\n".join(lines[i:i + MAX_LINES_PER_MESSAGE])):
                    raise RuntimeError("send failed, will retry")
                time.sleep(1.2)
            st["kanban_last_id"] = new_last
            st["pf_seen"] = sorted(seen)[-5000:]
            if lines:
                save_state(st)
        except Exception as e:
            log(f"loop error: {type(e).__name__}: {str(e)[:120]}")
            seen = set(load_state()["pf_seen"]) if load_state() else seen
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
