# 02 - Migration, integrations and hardening

The build started as a **migration from a Windows PC to a VPS** (Hermes had been running on Windows) and then grew. This note is the
order that worked, with the traps. Do not repeat the traps.

## Phase A - decommission the old host FIRST
Symptom: Telegram logs `Conflict: terminated by other getUpdates request` every ~40 s, on a clean single-instance VPS gateway.
Root cause: the Windows install still ran a standalone gateway for one profile (a Startup-folder `.vbs` relaunched it at every login)
and its `.env` still held the live bot token. Two long-pollers with one token evict each other.
Fix: kill the Windows process tree, **move** (not delete) the Startup launchers to a `_disabled_by_migration` folder, keep the Windows install as a disabled fallback,
restart the VPS gateway once and watch two poll cycles with `journalctl --user -u hermes-gateway --since "2 min ago" | grep -i conflict`.
Rule: after a migration, search every `.env` and profile for the shared token; only `default` keeps it.
Also check: `getWebhookInfo` shows no webhook (a webhook also blocks polling).

## Phase B - integrations that need a human in the loop (OAuth on a headless server)
An agent cannot click "Allow" for you. Patterns that worked:
| Integration | Method | Gotcha |
|---|---|---|
| Nous Portal | `hermes model` -> device-code / browser login | the login page redirects to `http://127.0.0.1:<port>/callback` on the *browser's* machine, which refuses to connect. Either forward that port over SSH (`ssh -L <port>:127.0.0.1:<port>`) or complete it where the callback can reach the server; success page: "Authorization Successful" |
| Notion / Linear / Netlify MCP | `hermes mcp login <name>` (OAuth) | each profile has its own connection; log in per profile that needs it. `hermes mcp test <name>` proves it; `hermes mcp list` shows enabled state |
| Google Workspace skill | Google Cloud project, enable Gmail, Calendar, Drive, Sheets, Docs, People APIs; **Desktop** OAuth client JSON; add your account as a test user; run the skill's `scripts/setup.py` | the final redirect goes to `http://localhost:1/?code=...` which fails to load. That is expected: copy the whole failed URL and paste it to the setup script - the `code` is in it |
| Slack | app + bot token, Socket Mode app token in the default profile `.env` | verify with `auth.test`; no duplicate Windows-side gateway |
| Honcho memory | `hermes honcho status`; OAuth token refreshes on next use | shows "token expired" until used - harmless |
| Firecrawl | official integration; key in the env, never printed | stop at the credential step and ask the owner |

Everything interactive must run in an interactive SSH session, not piped, or OAuth fails with a "non-interactive/background context" error.

## Phase C - fix what the migration exposed (not caused)
- A Gemini credential showing `auth failed (403)`: it was a stale cooldown marker; `hermes auth reset gemini` cleared it.
- A cron job (Morning briefing) hard-failed because the Google skill had no token: detach the skill from the job until OAuth exists, then re-attach.
- A vault path pointing at a Windows folder: comment it out (after backing up each config as `*.bak-<stamp>-<reason>`), then set it properly once the vault exists on the VPS.

## Phase D - secure remote access (Tailscale)
1. Install Tailscale, `tailscale up`, authorise (URL), note the IPv4 and hostname.
2. Dashboard auth: basic auth via `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `..._PASSWORD_HASH` (store the hash only) and a persistent `..._SECRET` so sessions survive restarts. `.env` mode 600. **Never `--insecure`.**
3. Bind to the tailnet IP first (unit waits for it with `wait_for_tailscale_ip.sh`), verify: unauthenticated request -> 302 to `/login`; public IP on the port -> refused.
4. **HTTPS matters**: browsers hide the microphone on plain http, and iOS Safari lacks MediaRecorder. Use `tailscale serve --bg --https=443 http://127.0.0.1:9119` and `--https=8443 ... 9220`, then set `dashboard.public_url: https://<machine>.<tailnet>.ts.net` in each dashboard's config (otherwise the login answers "Invalid Host header").
5. Final hardening (2026-09-21): bind both dashboards to `127.0.0.1` and point Serve at loopback, closing the plain-http tailnet ports. Verify unauthenticated calls still return 302/401 after the change (a loopback bind must not skip login).
6. Never put a generated password in chat or a note; give it once, tell the owner to store it in a password manager.

## Phase E - Obsidian vault on the server
Target `/srv/hermes/obsidian/Precious-AI-Vault` with `HOME.md` directly inside (no nested duplicate). Preserve `.obsidian`. Dirs 700, files 600 (client data).
Set with `hermes config set OBSIDIAN_VAULT_PATH ...` for each profile that uses it (writes `.env`, purges stale `config.yaml` copies), restart the gateway, run a read/write/delete test on a scratch note.
**The server vault and the PC vault are independent copies.** Agent exports land on the server first. Since 2026-09-21 the PC's daily pull script copies new files from the server's `00-Inbox/Agent-Outputs` into the PC vault's `00-Inbox/Agent-Outputs` (tar over SSH with keep-old-files, so nothing is ever overwritten). It is one-way and inbox-only, matching the vault's AGENT-WORKFLOW rules; edits made on the PC do not flow back. For true two-way sync use Syncthing or git - a separate decision.

## Phase F - keep the safety net
Take a backup before every risky step; keep every config edit reversible (`*.bak-*`); keep the old install disabled but present until the new one has run cleanly for a while.
