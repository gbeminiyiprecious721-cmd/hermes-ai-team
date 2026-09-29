#!/usr/bin/env python3
"""Saves each finished Kanban task as a draft note in the Obsidian vault inbox.

Follows the vault's AGENT-WORKFLOW rules: routine agent writes go to 00-Inbox, are
marked as drafts, never touch curated notes or .obsidian, and are never deleted or
overwritten here. One note per task, written once. Text deliverables are embedded in
the note; obvious secrets are masked.
"""
import json, os, re, sqlite3, sys, time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/root/.hermes")
KANBAN_DB = HOME / "kanban.db"
STATE = HOME / "library-export" / "exported.json"
POLL = 15
SETTLE_SECONDS = 8
MAX_EMBED = 60_000
TEXT_TYPES = (".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml", ".html")
AGENT = {"default": "Gideon", "scout": "Scout", "scribe": "Scribe", "socialmediaagent": "Reach",
         "youtube-production-agent": "Production", "product-factory": "Product Factory"}
# my own smoke-test tasks: not deliverables
SKIP_TITLE = re.compile(r"^(Test:|Feed test|SSE test|Dashboard test|Push test|Live test|--help)", re.I)
SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|xox[abp]-[A-Za-z0-9\-]{10,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b)")


def log(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def vault() -> Path:
    v = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not v:
        for line in (HOME / ".env").read_text().splitlines():
            if line.startswith("OBSIDIAN_VAULT_PATH="):
                v = line.split("=", 1)[1].strip().strip("\"'")
    p = Path(v or "/srv/hermes/obsidian/Precious-AI-Vault")
    if not (p / "AGENT-WORKFLOW.md").is_file():
        raise SystemExit("vault not found at " + str(p))
    return p


OUT = vault() / "00-Inbox" / "Agent-Outputs"


def scrub(t):
    return SECRET.sub("[REDACTED]", t or "")


def slug(title):
    s = re.sub(r"[^A-Za-z0-9 \-]+", "", title or "task").strip()
    s = re.sub(r"\s+", " ", s)[:60].strip()
    return s or "task"


def iso(e):
    return datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if e else ""


def yq(s):
    return json.dumps(s, ensure_ascii=False)  # valid YAML double-quoted scalar


def load():
    try:
        return set(json.loads(STATE.read_text()))
    except Exception:
        return set()


def save(ids):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(ids)))
    tmp.replace(STATE)


def write_note(con, t, overwrite=False):
    who = AGENT.get(t["assignee"] or "default", t["assignee"] or "Unassigned")
    runs = con.execute("select summary from task_runs where task_id=? and summary is not null and summary != '' order by id desc limit 1", (t["id"],)).fetchall()
    summary = runs[0]["summary"] if runs else (t["result"] or "")
    atts = [dict(r) for r in con.execute("select filename, stored_path, size from task_attachments where task_id=? order by id", (t["id"],)).fetchall()]
    # workers sometimes drop files into the task folder without registering them: include those too
    folder_of_files = HOME / "kanban" / "attachments" / t["id"]
    if folder_of_files.is_dir():
        known = {a["filename"] for a in atts}
        for f in sorted(folder_of_files.iterdir()):
            if f.is_file() and f.name not in known:
                atts.append({"filename": f.name, "stored_path": str(f), "size": f.stat().st_size})
    date = (iso(t["completed_at"]) or iso(t["created_at"]))[:10]
    folder = OUT / who
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{date} {slug(t['title'])} ({t['id']}).md"
    if path.exists() and not overwrite:
        return path, False
    parts = [
        "---",
        "type: agent-output", "status: draft", "source: hermes-kanban",
        f"task: {t['id']}", f"agent: {yq(who)}", f"title: {yq(t['title'])}",
        f"created: {iso(t['created_at'])}", f"completed: {iso(t['completed_at'])}",
        "---", "",
        f"# {t['title']}", "",
        f"> Draft from **{who}** via Hermes Kanban task `{t['id']}`. Not reviewed. "
        "Per AGENT-WORKFLOW, promote into a curated note only with your approval.", "",
    ]
    if (t["body"] or "").strip():
        parts += ["## Request", "", scrub(t["body"]).strip(), ""]
    if summary.strip():
        parts += ["## Result", "", scrub(summary).strip(), ""]
    base = (HOME / "kanban").resolve()
    for a in atts:
        parts += [f"## Deliverable: {a['filename']}", ""]
        fp = Path(a["stored_path"]).resolve()
        try:
            fp.relative_to(base)
            ok = fp.is_file() and a["filename"].lower().endswith(TEXT_TYPES)
        except ValueError:
            ok = False
        if not ok:
            parts += [f"_({a['filename']}, {a['size']} bytes: not embedded, open the task in Mission Control.)_", ""]
            continue
        text = scrub(fp.read_text(encoding="utf-8", errors="replace"))
        cut = len(text) > MAX_EMBED
        text = text[:MAX_EMBED]
        if a["filename"].lower().endswith(".md"):
            parts += [text.strip(), ""]
        else:
            parts += ["~~~~", text.strip(), "~~~~", ""]
        if cut:
            parts += ["_(truncated at 60 KB)_", ""]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(parts), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path, True


def main():
    log(f"library exporter started, output: {OUT}")
    done = load()
    # one-off: LIBRARY_REWRITE=t_abc,t_def regenerates those notes (only ever used on drafts this script wrote)
    rewrite = {x for x in os.environ.get("LIBRARY_REWRITE", "").split(",") if x}
    once = "--once" in sys.argv
    while True:
        try:
            if KANBAN_DB.exists():
                con = sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True, timeout=5)
                con.row_factory = sqlite3.Row
                try:
                    rows = con.execute("select * from tasks where status='done' and completed_at is not null and completed_at <= ?",
                                       (time.time() - SETTLE_SECONDS,)).fetchall()
                    changed = False
                    for t in rows:
                        if t["id"] in done and t["id"] not in rewrite:
                            continue
                        if SKIP_TITLE.match(t["title"] or ""):
                            done.add(t["id"]); changed = True; continue
                        path, created = write_note(con, t, overwrite=t["id"] in rewrite)
                        done.add(t["id"]); changed = True
                        if created:
                            log(f"saved {t['id']} -> {path.relative_to(OUT)}")
                    if changed:
                        save(done)
                finally:
                    con.close()
        except Exception as e:
            log(f"error: {type(e).__name__}: {str(e)[:160]}")
        if once:
            return
        time.sleep(POLL)


if __name__ == "__main__":
    main()
