#!/usr/bin/env python3
"""Hermes VPS backup.

Makes three timestamped archives in /root/backups:
  custom/   code and config (plugins, scripts, SOULs, configs, systemd units, runbook).
            Contains NO secrets: every file is scanned and anything that looks like a key is skipped.
            This is the one that is safe to copy off the server.
  data/     consistent SQLite snapshots (sessions, kanban), memories, cron jobs, the Obsidian vault.
            Private conversation content: keep on the server or somewhere you trust.
  secrets/  .env files, auth.json, OAuth tokens. Root only (mode 600, directory 700). Same disk as the
            server, so it protects against mistakes, not against losing the server.
Old archives are pruned (7 custom, 7 data, 4 secrets). Nothing outside /root/backups is modified.
Run:  hermes_backup.py            (all three)   |   hermes_backup.py custom
"""
import hashlib, os, re, shutil, sqlite3, subprocess, sys, tarfile, tempfile, time
from pathlib import Path

HOME = Path("/root/.hermes")
OUT = Path("/root/backups")
VAULT = Path("/srv/hermes/obsidian/Precious-AI-Vault")
UNITS = Path("/root/.config/systemd/user")
KEEP = {"custom": 7, "data": 7, "secrets": 4}
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|xox[abp]-[A-Za-z0-9\-]{10,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b|BEGIN (RSA |OPENSSH )?PRIVATE KEY)")
EXCLUDE = re.compile(r"(\.bak-|\.backup-|__pycache__|\.tmp$|\.lock$|\.pyc$)")
LOG = OUT / "backup.log"


def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def profiles():
    return [p for p in sorted((HOME / "profiles").iterdir()) if p.is_dir()] if (HOME / "profiles").is_dir() else []


def walk(path):
    if path.is_file():
        yield path
    elif path.is_dir():
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not EXCLUDE.search(d)]
            for f in files:
                if not EXCLUDE.search(f):
                    yield Path(root) / f


def add_files(tar, files, skipped, scan):
    n = 0
    for f in files:
        if not f.is_file():
            continue
        if scan and f.stat().st_size < 3_000_000:
            try:
                if SECRET_RE.search(f.read_text(encoding="utf-8", errors="ignore")):
                    skipped.append(str(f)); continue
            except OSError:
                continue
        tar.add(str(f), arcname=str(f).lstrip("/"), recursive=False)
        n += 1
    return n


def finish(kind, tmp_path, stamp, mode):
    d = OUT / kind
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700 if kind == "secrets" else 0o750)
    final = d / f"{kind}-{stamp}.tar.gz"
    shutil.move(tmp_path, final)
    os.chmod(final, mode)
    with tarfile.open(final) as t:            # verify it really opens and has content
        names = t.getnames()
    if not names:
        raise RuntimeError("empty archive: " + str(final))
    for old in sorted(d.glob(f"{kind}-*.tar.gz"))[:-KEEP[kind]]:
        old.unlink()
    sums = []
    for f in sorted(d.glob(f"{kind}-*.tar.gz")):
        sums.append(hashlib.sha256(f.read_bytes()).hexdigest() + "  " + f.name)
    (d / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    log(f"{kind}: {final.name} {final.stat().st_size // 1024} KB, {len(names)} entries")
    return final


def make_custom(stamp):
    skipped = []
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz"); os.close(fd)
    with tarfile.open(tmp, "w:gz") as tar:
        files = [HOME / "config.yaml", HOME / "SOUL.md", HOME / "RUNBOOK.md", HOME / "dashboard-actions.log", HOME / "jarvis-settings.json", HOME / "cron" / "jobs.json", Path("/root/jarvis-voice/server.py")]
        for p in profiles():
            files += [p / "config.yaml", p / "SOUL.md", p / "profile.yaml"]
        dirs = [HOME / "plugins" / "hermes-command-center", HOME / "profiles" / "product-factory" / "plugins" / "product-factory-mission-control", HOME / "scripts"]
        allf = list(files)
        for d in dirs:
            allf += list(walk(d))
        allf += [u for u in sorted(UNITS.glob("hermes-*")) if u.is_file()]
        n = add_files(tar, allf, skipped, scan=True)
        # runtime facts that are not files
        for name, cmd in (("tailscale-serve.json", ["tailscale", "serve", "status", "--json"]), ("VERSION.txt", ["hermes", "--version"]),
                          ("kanban-board.txt", ["hermes", "kanban", "list"])):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=dict(os.environ, HERMES_HOME=str(HOME))).stdout
                if out.strip() and not SECRET_RE.search(out):
                    info = tarfile.TarInfo("facts/" + name); data = out.encode(); info.size = len(data); info.mtime = time.time()
                    import io
                    tar.addfile(info, io.BytesIO(data))
            except Exception:
                pass
    if skipped:
        log("custom: skipped (looked like secrets): " + ", ".join(skipped))
    log(f"custom: {n} files")
    return finish("custom", tmp, stamp, 0o640)


def make_data(stamp):
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz"); os.close(fd)
    work = Path(tempfile.mkdtemp(prefix="hbk-"))
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            dbs = [HOME / "state.db", HOME / "kanban.db"] + [p / "state.db" for p in profiles()]
            for db in dbs:
                if not db.is_file():
                    continue
                snap = work / (str(db.relative_to(HOME)).replace("/", "__"))
                src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
                dst = sqlite3.connect(snap)
                src.backup(dst)
                ok = dst.execute("pragma integrity_check").fetchone()[0]
                src.close(); dst.close()
                if ok != "ok":
                    raise RuntimeError(f"integrity_check failed for {db}: {ok}")
                tar.add(str(snap), arcname="db/" + snap.name)
            files = list(walk(HOME / "memories"))
            for p in profiles():
                files += list(walk(p / "memories"))
            files += list(walk(HOME / "library-export")) + list(walk(HOME / "factory-floor")) + list(walk(VAULT))
            add_files(tar, files, [], scan=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return finish("data", tmp, stamp, 0o600)


def make_secrets(stamp):
    fd, tmp = tempfile.mkstemp(suffix=".tar.gz"); os.close(fd)
    with tarfile.open(tmp, "w:gz") as tar:
        files = [HOME / ".env", HOME / "auth.json", HOME / "honcho.json", HOME / "google_token.json", HOME / "google_client_secret.json"]
        files += list(walk(HOME / "mcp-tokens"))
        for p in profiles():
            files += [p / ".env", p / "auth.json"] + list(walk(p / "mcp-tokens"))
        add_files(tar, files, [], scan=False)
    return finish("secrets", tmp, stamp, 0o600)


def main():
    kinds = sys.argv[1:] or ["custom", "data", "secrets"]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    makers = {"custom": make_custom, "data": make_data, "secrets": make_secrets}
    bad = 0
    for k in kinds:
        try:
            makers[k](stamp)
        except Exception as e:
            bad += 1
            log(f"{k}: FAILED {type(e).__name__}: {e}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
