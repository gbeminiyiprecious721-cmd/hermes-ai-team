# 01 - Architecture and stack

## Big picture
```
 Phone / PC (Tailscale app on)                 Telegram group "Product Factory" (topics)
        |  https (tailnet only)                          |  Bot API long-polling
        v                                                v
 Tailscale Serve  443 -> 127.0.0.1:9119   +--------- hermes-gateway.service (ONE process, multiplexed) ---------+
                  8443 -> 127.0.0.1:9220  |  profiles: default(Gideon) scout scribe socialmediaagent            |
        |                                 |            youtube-production-agent product-factory                |
        v                                 |            geminiworker openrouterworker                           |
 hermes-dashboard (Command Center)        |  Kanban dispatcher, cron ticker, Telegram + Slack adapters          |
 hermes-dashboard-product-factory (MC)    +----------------------------------------------------------------------+
        |                                          |                     |
        | plugin APIs (FastAPI routers)            | kanban.db, state.db  | MCP: Notion, Linear, Netlify (OAuth)
        v                                          v                     v
 /api/plugins/<name>/...  + host routers   /root/.hermes (config, SOULs, profiles, skills, memories)
 (/api/ws chat, /api/audio/transcribe,
  /api/cron)                                Honcho memory (OAuth), Firecrawl, Google Workspace skill (OAuth)
        |
 hermes-jarvis-voice (127.0.0.1:9931, Kokoro) ; hermes-factory-floor ; hermes-library-export ; hermes-backup.timer
```

## Components and where they live
| Piece | Path / unit | Notes |
|---|---|---|
| Hermes install | `/usr/local/lib/hermes-agent` | venv Python 3.11; `hermes` CLI |
| Home | `/root/.hermes` | `config.yaml`, `SOUL.md`, `.env` (600), `profiles/<name>/`, `skills/`, `plugins/`, `kanban.db`, `cron/jobs.json` |
| Gateway | `hermes-gateway.service` | multiplex mode: serves every profile from one process; only `default` owns Telegram/Slack tokens |
| Dashboards | `hermes-dashboard`, `hermes-dashboard-product-factory` | `--host 127.0.0.1`; MC runs `--profile product-factory dashboard --isolated` |
| Plugins | `~/.hermes/plugins/hermes-command-center`, `~/.hermes/profiles/product-factory/plugins/product-factory-mission-control` | each has `dashboard/manifest.json`, `plugin_api.py`, `dist/index.js`, `dist/style.css` |
| Voice | `hermes-jarvis-voice` + `/root/jarvis-voice/` | own venv, Kokoro ONNX, ffmpeg |
| Feeds | `hermes-factory-floor`, `hermes-library-export` | small Python scripts in `~/.hermes/scripts` |
| Backups | `hermes-backup.timer` 03:30 UTC | `/root/backups/{custom,data,secrets}` |
| Vault | `/srv/hermes/obsidian/Precious-AI-Vault` | separate from the PC vault; **not synced** |

## Design decisions and why
- **Multiplexed gateway** (not one gateway per profile): one Telegram token, one process to watch, cheap. Cost: profile secret scoping - only `default` carries platform tokens; every other profile is reached through `profile_routes`.
- **User-level systemd + lingering**: services survive logout and reboot without root units.
- **Dashboards as plugins**: extend the host dashboard (auth, websocket chat, audio, cron already exist) instead of writing a third app. Plugin APIs mount at process start, so restart the dashboard after API edits.
- **Loopback + Tailscale Serve**: https for free (needed for microphone), tailnet-only, and nothing to firewall.
- **Kanban as the single source of truth for delegation**: Gideon never "does the work"; he creates tasks for specialists, and every surface (Telegram feed, Mission Control, 3D office, Obsidian export) reads the same board.
- **Free OpenRouter/Nous models for specialists, guarded fallbacks**: see 03 and 11.
- **Obsidian as curated memory, Honcho + session search as operational memory**: agents write drafts to `00-Inbox` only.

## Versions and environment facts (verified 2026-09-21)
Hermes Agent v0.21.3 (2026.9.14) - Ubuntu 26.04.1 LTS - Tailscale 1.102.4 - system Python 3.14 (no venv/ensurepip; use the Hermes venv's Python to create other venvs) - onnxruntime 1.30 / kokoro-onnx 0.6.1 - three.js 0.160 vendored.

## Ports
`9119` Command Center (loopback), `9220` Mission Control (loopback), `9931` voice service (loopback), `22` SSH (public), `443/8443` Tailscale Serve (tailnet). Nothing else is exposed.
