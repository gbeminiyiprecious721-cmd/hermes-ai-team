# 13 - Rebuild checklist (ordered, with checks)

Tick each box only when its check passes. Commands run on the server as root unless noted.

## A. Server and private access
- [ ] Create the VPS (Ubuntu). Add your SSH public key; test `ssh root@<ip>`.
- [ ] `loginctl enable-linger root` (user services survive logout).
- [ ] Install Tailscale, `tailscale up`, authorise; note `tailscale ip -4` and the machine name.
- [ ] Phone and PC: Tailscale app connected. Check: `tailscale status` lists them.

## B. Hermes and the first agent
- [ ] Install Hermes (see its docs) so `hermes --version` works; home `/root/.hermes`.
- [ ] `hermes model` (provider login) and a test message from the CLI.
- [ ] Telegram: BotFather token -> `/root/.hermes/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`), `chmod 600`.
- [ ] Gateway as a user service; `hermes gateway restart`. Check: journal shows "Connected to Telegram (polling mode)", no `Conflict`.
- [ ] Only ONE machine polls this token (disable any old install).

## C. The team
- [ ] `hermes profile create <name>` for scout, scribe, socialmediaagent, youtube-production-agent, product-factory (secondary profiles get NO Telegram/Slack tokens).
- [ ] Telegram group with topics; note chat id and each topic's thread id.
- [ ] `gateway.profile_routes` entries (03). Restart the gateway.
- [ ] SOUL.md per profile from `code/souls/` (identity, tag, team map, rules, stop-and-ask). grep for `[` placeholders.
- [ ] Models: OpenRouter free for specialists (+ free fallback). Check: each topic answers with its tag.

## D. Delegation
- [ ] `kanban:` limits in config (max_in_progress 2, per profile 1). Gideon SOUL delegation rule.
- [ ] Test chain: Gideon -> Scout -> Scribe. Check: `hermes kanban list` shows done; outputs exist.
- [ ] Factory Floor topic + `hermes-factory-floor` unit (mask/set chat id and thread id in the script).
- [ ] Vault: create `/srv/hermes/obsidian/<Vault>` (dirs 700, files 600), `hermes config set OBSIDIAN_VAULT_PATH ...`, `hermes-library-export` unit. Check: a finished task creates a draft in `00-Inbox/Agent-Outputs/`.

## E. Dashboards
- [ ] Dashboard auth env (username, password HASH, persistent secret) in `.env`, mode 600. Never `--insecure`.
- [ ] Units run dashboards on `--host 127.0.0.1` (Command Center 9119; Mission Control `--profile product-factory dashboard --isolated` 9220).
- [ ] `tailscale serve --bg --https=443 http://127.0.0.1:9119` and `--https=8443 http://127.0.0.1:9220`; set `dashboard.public_url` in each dashboard's config.
- [ ] Copy plugins from `code/command-center` and `code/mission-control` into the plugin folders (05), restart both dashboards.
- [ ] Checks: `curl -sk -o /dev/null -w '%{http_code}' https://<machine>.<tailnet>.ts.net/` -> 302; API without login -> 401; pages fit 375 px.

## F. Jarvis (optional, MVP = text chat)
- [ ] Command Center Jarvis page works over https; chat streams; approvals show Once/Deny only.
- [ ] Speech in: local whisper via the host audio route (https only). Speech out: Edge first.
- [ ] Pro: voice service (`code/jarvis-voice`): venv from the Hermes venv Python, `pip install kokoro-onnx soundfile numpy`, download `kokoro-v1.0.onnx` (fp32) and `voices-v1.0.bin` from the kokoro-onnx `model-files-v1.0` release, unit `hermes-jarvis-voice`, `curl 127.0.0.1:9931/health`.
- [ ] Phone: run **Test sound**; hear beep and voice.
- [ ] Benchmark speed modes with `code/tools/speed_exp2.py`; keep Balanced as default.

## G. Integrations (as needed, each with its own OAuth session)
- [ ] `hermes mcp login notion|linear|netlify` per profile; `hermes mcp test <name>`.
- [ ] Google Workspace: Cloud project, six APIs, Desktop OAuth client, test user, setup script, paste the redirect URL; live check each service.
- [ ] Product Factory workers: `npm install -g @anthropic-ai/claude-code @openai/codex`, sign in (`claude auth login`, `codex login --device-auth`), run `check-workers.sh` (expect both AVAILABLE), fix `routing_policy.yaml` paths, then prove each with one tiny call using the director's exact flags (see 14).
- [ ] Run one full local project through `director.py` end to end (a small CLI tool is a good first test) and confirm it reaches `COMPLETED` - this exercises Lead Engineer, QA, Security and Release for real, not just a smoke call.
- [ ] Slack app; `auth.test`. Firecrawl key in env (never printed). Honcho status.

## H. Operations
- [ ] `hermes_backup.py` + `hermes-backup.timer` (03:30 UTC). Run once, `sha256sum -c SHA256SUMS`, rehearse a restore.
- [ ] Off-server copy: install `Pull-HermesBackup.ps1` (see 08) and schedule it; run once and confirm the checksum lines in `pull.log`. Write `SECRETS-INVENTORY.md` (names only).
- [ ] Health score 100; journal errors 0 in 24 h; disk under 85%.
- [ ] Spend rule and approvals in Gideon's SOUL. Remove any temporary SSH key.
- [ ] Reboot test (08): everything comes back without touching it.

## I. Handover
- [ ] RUNBOOK.md current (services, URLs, topic ids, backups/restore, known caveats).
- [ ] The owner has: both https links, where the password lives (password manager), what each topic is for, and how to ask for help.
