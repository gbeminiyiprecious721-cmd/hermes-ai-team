# Hermes VPS - what to re-create if the server is lost (names only, no values)

The `secrets` backup tier stays on the server on purpose: copying credentials off the server unencrypted would be worse than the risk it covers.
If the server is ever lost, everything below can be re-issued. Store the new values in a password manager, not in a note or chat.

## Environment variables (files: `/root/.hermes/.env` and `/root/.hermes/profiles/<name>/.env`, mode 600)
| Variable | Where | How to get it again |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | default only | BotFather -> your bot -> revoke/regenerate token |
| `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL`, `TELEGRAM_HOME_CHANNEL_THREAD_ID` | most profiles | your Telegram user id / group id / topic id (ids, not secrets) |
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_ALLOWED_USERS` | default | Slack app settings (OAuth + Socket Mode app token) |
| `OPENROUTER_API_KEY` | every profile | openrouter.ai keys |
| `ANTHROPIC_API_KEY` | every profile | console.anthropic.com keys (only if you use it) |
| `OBSIDIAN_VAULT_PATH` | default, workers, product-factory, scout, scribe | `hermes config set OBSIDIAN_VAULT_PATH /srv/hermes/obsidian/Precious-AI-Vault` |
| `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `..._PASSWORD_HASH`, `..._SECRET` | default, product-factory (also present in scout and scribe, unused there) | choose a new password, store its hash; new random signing secret |

## Logins that must be redone interactively (OAuth / device flows)
Nous Portal (`hermes model`); Notion, Linear, Netlify MCP (`hermes mcp login <name>`, per profile that uses them); Higgsfield MCP (Production);
Claude Code (`claude auth login`, Claude Pro) and Codex (`codex login --device-auth`, ChatGPT), both on the server; Google Workspace (Desktop OAuth client + `setup.py`, paste the redirect URL); Honcho (refreshes on first use); Tailscale (`tailscale up`); Firecrawl key.

## What the backups DO contain
`custom` (code, config, SOULs, units, cron jobs, runbook) and `data` (sessions, kanban, memories, vault) - both copied here by `Pull-HermesBackup.ps1`.
Restore steps: see `RUNBOOK.md` (section "Restore").
