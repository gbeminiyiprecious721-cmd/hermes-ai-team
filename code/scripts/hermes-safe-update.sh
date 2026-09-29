#!/bin/bash
# hermes-safe-update.sh - update Hermes with a backup, a rollback copy, smoke tests and automatic rollback.
#
#   hermes-safe-update.sh check        read-only: current vs available, plan, disk, what would restart
#   hermes-safe-update.sh update       do the update (asks nothing; run it only after you have read `check`)
#   hermes-safe-update.sh rollback     put the previous install back and restart everything
#
# Assumptions (edit the block below for your server): git install in $INSTALL, systemd USER units, dashboards bound to loopback.
set -u
export PATH="$PATH:/usr/local/bin:/root/.local/bin"
INSTALL=/usr/local/lib/hermes-agent
SAFE=/root/backups/manual-changes
UNITS_STOP_FIRST="hermes-dashboard hermes-dashboard-product-factory"      # stopped so the updater cannot relaunch them outside systemd
UNITS_ALL="hermes-gateway hermes-dashboard hermes-dashboard-product-factory hermes-factory-floor hermes-library-export hermes-jarvis-voice"
PUBLIC_URL="${PUBLIC_URL:-}"                                                # e.g. https://<machine>.<tailnet>.ts.net  (for the https smoke test)
BACKUP_SCRIPT=/root/.hermes/scripts/hermes_backup.py
STAMP=$(date +%Y%m%d-%H%M%S)
COPY="$INSTALL.pre-update"
LOG=/root/hermes-update-$STAMP.log

say() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
active() { systemctl --user is-active "$1" >/dev/null 2>&1; }

smoke() {   # returns non-zero if anything is wrong
  local bad=0
  for u in $UNITS_ALL; do active "$u" || { say "FAIL unit not active: $u"; bad=1; }; done
  hermes --version >/dev/null 2>&1 || { say "FAIL hermes --version"; bad=1; }
  hermes kanban list >/dev/null 2>&1 || { say "FAIL hermes kanban list"; bad=1; }
  hermes cron list >/dev/null 2>&1 || { say "FAIL hermes cron list"; bad=1; }
  python3 - <<'PY' || bad=1
import json,sys
try:
    d=json.load(open("/root/.hermes/gateway_state.json"))
    bad=[k for k,v in d.get("platforms",{}).items() if v.get("state")!="connected"]
    if bad: print("FAIL platforms not connected:",bad); sys.exit(1)
    print("platforms connected:",list(d.get("platforms",{})))
except Exception as e:
    print("FAIL gateway_state:",e); sys.exit(1)
PY
  if [ -n "$PUBLIC_URL" ]; then
    c=$(curl -sk -o /dev/null -w '%{http_code}' "$PUBLIC_URL/"); [ "$c" = 302 ] || { say "FAIL https root returned $c (want 302)"; bad=1; }
  fi
  local errs; errs=$(journalctl --user -u hermes-gateway --since "-3 min" -p err --no-pager -q | wc -l)
  [ "$errs" -eq 0 ] || { say "FAIL $errs gateway errors in the last 3 min"; bad=1; }
  return $bad
}

case "${1:-check}" in
  check)
    say "current: $(hermes --version | head -1)"
    hermes update --check 2>&1 | tail -3 | tee -a "$LOG"
    hermes update --plan 2>&1 | tail -20 | tee -a "$LOG"
    say "disk free: $(df -h / | tail -1 | awk '{print $4}') ; rollback copy needs $(du -sh "$INSTALL" | cut -f1)"
    say "running kanban tasks: $(hermes kanban list 2>&1 | grep -c -i running) (update only when 0)"
    ;;
  update)
    running=$(hermes kanban list 2>&1 | grep -c -i running)
    [ "$running" -eq 0 ] || { say "ABORT: $running kanban task(s) running; try later"; exit 1; }
    say "1/7 backup"; python3 "$BACKUP_SCRIPT" 2>&1 | tail -3 | tee -a "$LOG"
    say "2/7 snapshot configs + rollback copy of the install"
    mkdir -p "$SAFE/pre-update-$STAMP"; cp /root/.hermes/config.yaml "$SAFE/pre-update-$STAMP/config.default.yaml"
    for p in /root/.hermes/profiles/*/; do cp "$p/config.yaml" "$SAFE/pre-update-$STAMP/config.$(basename "$p").yaml" 2>/dev/null; done
    git -C "$INSTALL" rev-parse HEAD > "$SAFE/pre-update-$STAMP/commit.txt"
    rm -rf "$COPY"; cp -a "$INSTALL" "$COPY" || { say "ABORT: could not copy install (disk?)"; exit 1; }
    say "3/7 stop dashboards"; for u in $UNITS_STOP_FIRST; do systemctl --user stop "$u"; done
    say "4/7 hermes update"
    if ! hermes update --yes >> "$LOG" 2>&1; then say "update command failed -> rollback"; "$0" rollback; exit 1; fi
    say "5/7 restart"; for u in $UNITS_STOP_FIRST; do systemctl --user start "$u"; done
    hermes gateway restart >> "$LOG" 2>&1; sleep 45
    say "6/7 smoke tests"
    if smoke; then say "7/7 OK: $(hermes --version | head -1). Rollback copy kept at $COPY (delete after a few days: rm -rf $COPY)"; else say "smoke tests FAILED -> rollback"; "$0" rollback; exit 1; fi
    ;;
  rollback)
    [ -d "$COPY" ] || { say "no rollback copy at $COPY"; exit 1; }
    say "rolling back"
    for u in $UNITS_ALL; do systemctl --user stop "$u" 2>/dev/null; done
    rm -rf "$INSTALL.failed"; mv "$INSTALL" "$INSTALL.failed"; mv "$COPY" "$INSTALL"
    for u in $UNITS_ALL; do systemctl --user start "$u" 2>/dev/null; done
    sleep 45; say "rolled back to $(hermes --version | head -1); failed install kept at $INSTALL.failed"
    smoke && say "smoke tests pass after rollback" || say "WARNING: smoke tests still failing after rollback - investigate"
    say "note: if the update migrated the databases, restore state from the newest data backup (see runbook)"
    ;;
  *) echo "usage: $0 check|update|rollback"; exit 2;;
esac
