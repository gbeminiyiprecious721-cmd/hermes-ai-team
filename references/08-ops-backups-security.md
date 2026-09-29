# 08 - Operations, backups and security

## Services (systemd --user, lingering on)
`hermes-gateway`, `hermes-dashboard`, `hermes-dashboard-product-factory`, `hermes-factory-floor`, `hermes-library-export`, `hermes-jarvis-voice`, `hermes-backup.timer` (+ `hermes-backup.service`). Unit files are in `code/systemd/`.
`Restart=always` on long-runners. The gateway has a drop-in `hermes-gateway.service.d/quiet-nous.conf` (see "Log noise" below).
Check: `systemctl --user is-active <units>`; logs: `journalctl --user -u <unit> -n 50`; restart the gateway with `hermes gateway restart`.

## Backups (`code/scripts/hermes_backup.py`, timer 03:30 UTC)
| Tier | Contents | Where it may go |
|---|---|---|
| `custom` | code and config: plugins, scripts, SOULs, configs, systemd units, runbook, cron jobs, voice server; **secret-scanned** (regex for sk-, xox, ghp_, AIza, Telegram tokens; anything matching is skipped) | safe to copy off the server; copied to the PC daily |
| `data` | SQLite `.backup` snapshots (sessions, kanban), memories, vault | private; copied to the PC's local disk (not OneDrive) daily |
| `secrets` | `.env`, `auth.json`, OAuth tokens | root-only 600/700, same disk: protects against mistakes, **not against losing the server** |
Retention 7/7/4. `SHA256SUMS` per tier. Restore rehearsal was run (extract, compare, restore a dashboard, restore a DB with the gateway stopped).
**Off-server copy (done 2026-09-21):** a PC script `Pull-HermesBackup.ps1` (scheduled task "Hermes VPS backup pull", daily 09:15, runs on next start if the PC was off) copies the newest `custom` and `data` archives to `C:\...\Hermes-VPS-Backups\{custom,data}` (local disk, not OneDrive), verifies each against `SHA256SUMS`, keeps 7, and logs to `pull.log`. The `secrets` tier is **deliberately not copied**; `SECRETS-INVENTORY.md` lists every variable and login by name so they can be re-issued. The script uses the assistant's SSH key: if that key is revoked, create a new key (ideally restricted to read-only backup access) and edit `$Key`.
Manual rollback copies (`*.before-<change>`) live in `/root/backups/manual-changes/` with a README.

## Runbook
`/root/.hermes/RUNBOOK.md` (copy on the PC). Update it in the same step as every change - it is the handover document and the course's source of truth.

## Access and secrets checklist
- Dashboards: loopback only, Tailscale Serve https, basic auth with hashed password and persistent signing secret, `.env` mode 600, never `--insecure`.
- SSH key for the assistant was a **temporary** key; remove its line from `/root/.ssh/authorized_keys` when the build is finished.
- No secret is ever echoed into chat, notes, or the `custom` backup. If a password was shown once in chat, rotate it.
- Google token has write scopes; "read only" is enforced by page design + SOUL. Reduce scopes if that is not acceptable.
- Approvals: Jarvis offers only "Approve once" / "Deny".
- Spend rule in Gideon's SOUL: ask above 2 GBP per action / 5 GBP per day; recurring or new paid services always ask.
- Obsidian rules (AGENT-WORKFLOW.md in the vault): agents write drafts to `00-Inbox` only; never overwrite curated notes, move/delete files, or touch `.obsidian`.

## Health score (Command Center)
Services 40 (all units incl. voice), Channels 20 (Telegram + Slack connected), Resources 20 (disk and memory under 85%), Backups 10 (under 36 h), Recent errors 10 (no gateway ERROR in 30 min).

## Log noise (2026-09-21) and how it was handled
- **Nous warning** `nous: NOUS_INFERENCE_BASE_URL unreadable - no profile secret scope on a multiplexed call`: ~220 per day, from scheduled background tasks (hourly and every 15 min) that resolve the Nous provider without a profile scope. Harmless here because no routing override is set (default routing is what we want). Hermes exposes no config switch, so a **logging filter** (`code/scripts/quiet_nous_sitecustomize.py`, loaded via `PYTHONPATH` in the gateway unit's drop-in) hides only that message, and switches itself off if an override env var is ever set. It survives `hermes update` because no Hermes file was edited.
- **Netlify MCP keepalive** warnings: 8 in one 25-minute window, none since; `hermes mcp test netlify` connected and found 9 tools; the OAuth token refreshes itself. It was a server blip, not a configuration fault. Re-test with `hermes mcp test netlify`; if it recurs, run `hermes mcp reauth netlify`.
- Other benign lines: Telegram "sticky path failed, re-walking IPs" (transient network).
- **Higgsfield MCP warning** (`website_repo_access: suspicious description content - code execution reference`): Hermes' own scanner flagging one third-party tool description (it mentions sandbox checkout/push). Production does not need repo access, so the tool is excluded in that profile: `mcp_servers.higgsfield.tools.exclude: [website_repo_access]`. Warning gone after restart and after a full reboot; the server's other tools are unaffected. Glob patterns work too (`tools.include` is a whitelist and wins over `exclude`).

## Known caveats
SOULs are guidance; `hermes update` strips YAML comments and plugins load at start; free models rate-limit; agent drafts now flow one way to the PC vault (see 04 and 02) but the two vaults are otherwise independent; system Python 3.14 has no venv support (use the Hermes venv's Python for new venvs).

## Reboot test - PASSED 2026-09-21
`systemctl reboot`; SSH answered in ~55 s; 40 s later: all 7 units active without intervention, Tailscale up and `serve status` intact (443/8443 -> loopback), https 302 on both dashboards and 401 on unauthenticated API calls, only loopback listeners for 9119/9220/9931, Telegram and Slack `connected`, voice `/health` ok, zero journal errors since boot, zero Nous or Higgsfield warnings, backup timer scheduled, live call to Gideon answered. Preconditions that made it work: lingering on, every unit `enabled`, `tailscaled` enabled, Serve config persisted by Tailscale. Repeat this test after any change to units or networking.


## Updating Hermes without complications (procedure + script)
Hermes is a **git install** (`/usr/local/lib/hermes-agent`). Read-only first: `hermes update --check` (current vs available) and `hermes update --plan` (which services restart and how).
Findings from the first real attempt (2026-09-21, v0.21.3 -> v0.21.4 / tag v2026.9.21, release notes: no documented breaking changes):
- The "N commits behind" number can be misleading (a shallow fetch made history look unrelated); trust the version/tag and the release notes.
- `hermes update --plan` shows the dashboards as **manual-serve** processes: the updater would stop and relaunch them itself, outside systemd, which fights `Restart=always`. **Stop the dashboard units first**, update, then start them.
- `updates.pre_update_backup: true` makes Hermes snapshot state itself; still take your own backup and a full **rollback copy of the install directory** (2.4 GB, 22 s) - rollback is then a directory swap.
- Use `--yes` only after reading the plan; it auto-accepts config-migration and stash prompts.
Script: `code/scripts/hermes-safe-update.sh` with three modes: `check` (read-only), `update` (refuses if tasks are running; backup, configs snapshot, rollback copy, stop dashboards, `hermes update --yes`, restart, 45 s wait, smoke tests, automatic rollback on any failure), `rollback`. Smoke tests: every unit active, `hermes --version`, kanban and cron CLIs respond, Telegram + Slack `connected`, https root returns 302, no gateway errors in 3 minutes. After success keep the rollback copy a few days, then delete it.
**Result (2026-09-21):** after the owner said go, `hermes-safe-update.sh update` took the install from v0.21.3 to v0.21.4 in about 6 minutes and passed its smoke tests first time. Extra checks that were worth doing because they cover the custom parts: parsed-YAML diff of all 8 profile configs before vs after (0 changed keys - routes, fallbacks, public_url, MCP excludes intact), the logging filter still hiding the Nous warning, Jarvis chat end to end through the real websocket (first spoken word 5.4 s), local voice, speech-to-text round trip, cron API, and the kanban `--json` fields Mission Control reads. Keep the script's rollback copy a few quiet days, then delete it.
Note for an AI assistant driving this: applying an upstream update with auto-accept is a consequential action; get the owner's explicit yes after showing `check` output. (In the reference build the first unattended attempt was blocked by the tool's safety classifier; it ran only after the owner approved.)
