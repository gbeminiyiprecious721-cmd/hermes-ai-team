---
name: hermes-ai-team-build
description: Complete blueprint and reference for the self-hosted "AI operations team" built on Hermes Agent (v0.21.3) on a Hostinger VPS - one multiplexed gateway, Telegram topics routed to specialist profiles, Kanban delegation, two dashboards (Command Center + Mission Control) served over Tailscale https, the Jarvis voice assistant with a local custom voice, an animated 3D office, Obsidian hand-off, backups and a runbook. Use when asked to rebuild, extend, debug, document or TEACH this system, including drafting the MVP course, lesson plans, workshop material or a step-by-step build guide from it.
---

# Hermes AI Team Build (2026-09-21 snapshot)

A working, secured, phone-friendly "operations team" that a non-engineer can run: one Telegram bot fronting eight
Hermes profiles, a shared Kanban board, live dashboards, a voice assistant ("Jarvis") and nightly backups. Everything here
was built and verified on a real server; the numbers, fixes and failures in the references are measured, not guessed.

## What exists (the finished system)
| Layer | What it is | Reference |
|---|---|---|
| Host | Hostinger VPS, Ubuntu 26.04, 2 vCPU (AMD EPYC), 8 GB RAM, 96 GB disk. Hermes v0.21.3 in `/usr/local/lib/hermes-agent` (Python 3.11 venv), home `/root/.hermes`, systemd **user** services with lingering | 01 |
| Access | Tailscale only. Dashboards listen on 127.0.0.1, Tailscale Serve gives https (443 and 8443), login required, no Funnel, no public ports except SSH | 02, 08 |
| Team | One Telegram bot, one gateway, 8 profiles. Topics routed to profiles by `gateway.profile_routes`. Gideon (default) is Chief of Staff; Scout, Scribe, Reach, Production, Product Factory are specialists | 03 |
| Work flow | Shared Kanban DB, dispatcher inside the gateway (max 2 running, 1 per profile), Factory Floor feed in Telegram, finished tasks exported as drafts to the Obsidian inbox | 04 |
| Dashboards | Command Center (Jarvis, Infrastructure, Schedule, Threads, Comms, Docs) and Mission Control (Overview, 3D Office, Tasks, Library, Activity, Artifacts) as Hermes dashboard plugins | 05 |
| Jarvis | Voice + chat assistant: local speech-to-text, streaming replies, sentence-by-sentence speech, custom-blended local voice (Kokoro) with Edge fallback, live-facts prompt, speed modes | 06 |
| 3D Office | three.js scene driven by real Kanban + project state: agents type, wave when blocked, cheer, beams and packets between them | 07 |
| Operations | Three-tier backups with restore rehearsal, health score, runbook, spend and approval rules | 08 |

## Non-negotiable principles (learned the hard way)
1. **Inspect before you change; back up before you deploy.** Every deploy in this build was preceded by a backup and followed by an unauthenticated 401/302 check.
2. **Real state only.** Dashboards show data read from the system (Kanban, cron, journal, project files). No fake demo numbers in production views.
3. **One owner per secret.** Only the `default` profile holds the Telegram and Slack tokens; two pollers with one token fight forever (see 02, 10).
4. **Guidance is not enforcement.** SOUL.md rules steer models; they do not stop a tool call. Use permissions, allowlists, approvals and read-only scopes for real limits.
5. **Free models are a design constraint.** Latency varies wildly and tool use is unreliable; put the facts in the prompt instead of hoping the model looks them up (06, 11).
6. **Secure by topology, not by hope.** Bind to loopback, publish only through Tailscale Serve, keep `.env` at mode 600, never print credentials in chat.
7. **Test the way it will be used** - real endpoints, phone width, synthetic microphone, round trips (09).
8. **Write the runbook as you go.** The runbook is the product handover.

## How to use this skill
- To **rebuild**: follow `references/13-rebuild-checklist.md` in order; use `code/` as the starting files.
- To **debug**: read `references/10-pitfalls-and-fixes.md` first; most failures already happened once.
- To **extend** (a new specialist, a new dashboard page, a new voice): 03, 05, 06 have the patterns and the exact files to touch.
- To **teach** (MVP course): `references/12-mvp-course-blueprint.md` maps the build to modules, labs, deliverables and scope cuts.
- Numbers and benchmarks: `references/11-metrics-and-costs.md`.
- **Open design questions and decisions to make next** (GPT subscription use, vault sync, backup key, course launch): `references/14-open-design-questions.md`.

## Where things are
- `references/` - 14 numbered notes (this index + the detail).
- `code/` - the real files: dashboard plugins (Python API + JS + CSS), Jarvis voice service, scripts, systemd units, SOUL templates. No secrets; the Telegram group id and tailnet name are masked.
- `assets/` - the JARVIS portrait and gold logo crops used by the Jarvis page.

## Quick commands (on the server)
```
systemctl --user is-active hermes-gateway hermes-dashboard hermes-dashboard-product-factory hermes-factory-floor hermes-library-export hermes-jarvis-voice
hermes gateway restart                       # not "reload"
hermes kanban list                           # board
hermes cron list                             # scheduled jobs
hermes mcp test <server>                     # OAuth MCP health
tailscale serve status                       # what is published
python3 /root/.hermes/scripts/hermes_backup.py [custom|data|secrets]
journalctl --user -u <unit> -n 50
```

## Scope note
This is a snapshot of one person's system (Precious, Chief of Staff pattern). Names, chat ids, hostnames and the vault path are examples; replace them.
Hermes' free-model lineup, the Kokoro model files and the Tailscale/Hostinger UIs change - re-check versions before teaching from it.
