# Hermes AI Team

A self-hosted, multi-agent "AI operations team" built on top of
[Hermes Agent](https://github.com/) running on a private VPS: one gateway,
several specialist agent profiles reachable from Telegram/Slack, a shared
Kanban task board for delegation between agents, two custom web dashboards,
and a voice assistant.

This repo is the **custom code, configuration templates and documentation**
for that system — not a copy of the Hermes framework itself (that's a
separate third-party project this system is built on top of), and not the
live runtime state (sessions, logs, memories, caches) of the deployed
server, which stays private.

## What's actually in here

- **`code/mission-control/`** — a custom dashboard plugin (Python API +
  JS/CSS frontend) for monitoring specialist agents and task delegation on
  the "product-factory" profile.
- **`code/career-coach/`** — a conversational AI Data Science/career coach
  plugin: a FastAPI-style backend (`plugin_api.py`) with endpoints for
  profile, roadmap, goals, jobs, interviews and live chat, a SQLite schema
  (`coach_db.py`), and a real-time voice loop (browser mic capture,
  energy-based voice-activity detection, local Whisper speech-to-text,
  KittenTTS replies, barge-in interruption). See `code/career-coach/docs.md`
  for an explicit "what's real vs. not yet built" note written during
  development.
- **`code/command-center/`** — the general team dashboard plugin (Kanban
  board, voice settings, animated "office" visualisation).
- **`code/jarvis-voice/`** — the voice-assistant server.
- **`code/souls/`** — the persona/standing-instructions file (`SOUL.md`) for
  each agent profile (default, product-factory, scout, scribe,
  social-media agent, YouTube production agent). These are guidance for the
  AI, not enforced permissions.
- **`code/systemd/`** — the systemd unit files used to run the gateway,
  dashboards, voice assistant and backups as services on the VPS.
- **`code/scripts/`** — operational scripts: backup/restore, a safe-update
  wrapper, a secrets inventory (**names only, no values** — see
  `code/scripts/SECRETS-INVENTORY.md`), and small patches applied during
  development.
- **`code/tools/`** — supporting scripts used while building and testing the
  system (build harness, Jarvis test/serve scripts, patch scripts).
- **`references/`** — 14 written references documenting the architecture,
  the Telegram/profile team design, Kanban delegation, the dashboard plugin
  system, the voice assistant, backups/security, a testing method, known
  pitfalls, measured metrics/costs, and a rebuild checklist. These were
  written directly from the working system, not from memory.
- **`profiles/youtube-production-agent/`** — the fullest example of a
  specialist agent's actual working code: a YouTube content-production
  pipeline (ideate → outline → script → metadata → thumbnails) built on the
  Claude Agent SDK, with a Streamlit dashboard and a human-in-the-loop
  approval state machine (see that folder's own contents for detail).

## What's deliberately left out

- The Hermes framework/runtime itself (third-party).
- Any real credentials, tokens or API keys. Every config file here uses
  placeholders or environment-variable references; see
  `code/scripts/SECRETS-INVENTORY.md` for exactly which variables exist and
  where to regenerate them if you're rebuilding this yourself.
- Live runtime state: session transcripts, logs, cached audio/images,
  personal memories, and backups. None of that is code — it's operational
  data from a live personal system.

## Status

This is a real, running personal system, not a demo. Some pieces (e.g. the
career coach's avatar/streaming-voice roadmap) are explicitly documented as
not yet built where that's the case — see the relevant file's own notes
rather than assuming everything described is finished.
