# 12 - MVP course blueprint: "Build your own AI operations team"

Working title options: *Your AI Operations Team in a Weekend* / *Hermes on a VPS: from zero to a private AI team* / *Run an AI Chief of Staff*.
This note turns the build into a teachable product. Everything a student sees was verified on a real system (see 09, 10, 11).

## Promise, audience, prerequisites
- **Promise:** by the end you own a private, secured AI team: a Telegram front door, specialist agents, a task board, live dashboards you can open on your phone, and (optional) a voice assistant, with backups and a runbook.
- **Audience:** founders, consultants, analysts and operators who can copy-paste commands and follow a checklist; developers who want a working reference. Not for people who need a no-code hosted product.
- **Prerequisites:** a VPS (Ubuntu, 2 vCPU / 8 GB is comfortable), a Telegram account, a Tailscale account, an OpenRouter account (free models are enough), a computer with a terminal. Claude Code (or any coding assistant) as the co-pilot is assumed; the course teaches how to drive it safely.
- **Time:** MVP path about 8-10 hours of guided work; advanced modules another 6-8.

## MVP scope vs later (recommendation)
| Tier | Modules | Why |
|---|---|---|
| **MVP (sell first)** | 1-7 | delivers the promise end to end: secure server, Telegram team, delegation, dashboard basics, chat-first Jarvis, backups and runbook |
| Pro add-on | 8 (3D office, local custom voice, Obsidian hand-off) | high wow factor, more moving parts; keep out of the MVP so the base is reliable |
| Integrations pack | 9 (Google Workspace, Notion/Linear/Netlify, Firecrawl) | OAuth on a headless server is the #1 support burden |
| Clinic | 10 (migration + troubleshooting) | turn the pitfalls table into a live Q&A or a paid audit |
Cut for MVP: Kokoro voice, 3D office, model dropdown, usage heat map. Keep: one dashboard page with tasks + health, Telegram routing, Kanban, Jarvis as text chat with optional Edge voice.

## Module map (each: outcome - lessons - lab - deliverable - check)
### Module 0 - Orientation (30 min)
Outcome: know what is being built and the safety rules. Lessons: the finished system tour (Telegram, Mission Control, 3D office, Jarvis), the 8 principles from SKILL.md, the cost model (11). Deliverable: a filled "project sheet" (names, topics, budget, what you will and will not let agents do).

### Module 1 - Server and private access (60-90 min)
Lessons: what a VPS is, SSH keys, user-level systemd + lingering, Tailscale, why loopback + Serve, https for microphone. Lab: create the server, SSH by key, install Tailscale, publish a test page over `tailscale serve`. Deliverable: phone opens `https://<machine>.<tailnet>.ts.net`. Check: public IP shows nothing but SSH. Failure to expect: `Invalid Host header`, Tailscale not connected on the phone.

### Module 2 - Install Hermes, first agent, Telegram (60-90 min)
Lessons: Hermes layout (`/usr/local/lib/hermes-agent`, `~/.hermes`), `.env` and mode 600, BotFather, allowed users, gateway as a user service. Lab: install, `hermes model`, create the bot, run `hermes-gateway.service`, say hello. Deliverable: the bot answers from the server. Check: `journalctl` shows "Connected to Telegram (polling mode)". Failure: getUpdates conflict (one poller per token).

### Module 3 - Build the team (90 min)
Lessons: profiles, multiplexed gateway, only `default` owns platform tokens, Telegram topics -> `profile_routes`, SOUL.md anatomy (identity, tags, style, delegation, stop-and-ask), free model choice and fallbacks. Lab: create Scout and Scribe, two topics, routes, SOULs, tag rule. Deliverable: each topic answers with its own tag. Check: message every topic. Failure: "could not connect to the AI model service" (provider not logged in).

### Module 4 - Delegation with Kanban (60-90 min)
Lessons: the board, dispatcher limits, Gideon rule "create tasks, do not do the work", blocked/unblock, Factory Floor feed. Lab: Scout researches -> Scribe writes, watch it in Telegram. Deliverable: three tasks done and a Factory Floor topic. Check: `hermes kanban list`.

### Module 5 - See the work: dashboards (2 h)
Lessons: Hermes dashboard plugins (manifest, API router, IIFE bundle), auth model, `public_url`, real-state-only rule, SSE. Lab: a "Team board" page (tasks + health + create/unblock/reassign with allowlist and audit log). Deliverable: Mission Control-lite. Check: 302/401 unauthenticated, works at 375 px. Failure: API route 404 (restart the dashboard).

### Module 6 - Talk to it: Jarvis (2-3 h)
Lessons: WebSocket chat protocol, streaming, sentence-by-sentence speech, the **live facts** trick, per-session model override, latency budget, https + Web Audio recording, phone audio unlock, "Hear it" and Test sound diagnostics. Lab (MVP): text chat with streaming + optional Edge voice. Lab (stretch): microphone with local whisper. Deliverable: a question answered aloud in under 10 s. Check: benchmark script from `code/tools/speed_exp2.py`.

### Module 7 - Run it like a product (90 min)
Lessons: three-tier backups + secret scan + restore rehearsal, runbook habit, health score, approvals, spend rules, access model (loopback + Serve), removing temporary SSH keys, reboot test. Lab: schedule backups, restore a dashboard from an archive, do a reboot test. Deliverable: RUNBOOK.md and a passing checklist.

### Module 8 (Pro) - Wow layer (3-4 h)
3D Office (state from real data, animation set), the JARVIS hero (blend-mode image + canvas overlay), local custom voice with Kokoro (benchmark fp32 vs int8, blends, ffmpeg chain, fallback), Obsidian hand-off with vault governance.
### Module 9 (Integrations) - OAuth on a headless server (2 h)
Nous device login, MCP OAuth per profile, Google Workspace desktop-client flow and the dead `localhost` redirect trick, Slack, Firecrawl (never print keys), read-only enforcement honesty (token scope vs page design).
### Module 10 (Clinic) - Migration and troubleshooting
Migrating from a PC (decommission first), the pitfalls table live-debug, reading logs, filtering harmless warnings without editing vendor code.

### Bonus case study: the rework loop
The reference build's own Lead Engineer/QA rework loop (14) is a strong worked example for an advanced lesson: a bounded repair loop, sandboxed pipeline-run tests instead of trusting a model's self-report, and a gate that correctly refuses to rubber-stamp remaining edge cases. Use `csv-quote-compare-smoke`'s real rework history as course material.

## Capstone
"Weekly digest team": Scout gathers, Scribe writes, Gideon reports to Telegram, a draft lands in the Obsidian inbox, Mission Control shows it, a cron job runs it on schedule, backup exists, runbook updated.

## Teaching method (what made this build work)
1. **Prompt like an operator:** inspect first, back up before editing, never expose secrets, verify with evidence, report root cause and every change. (Template below.)
2. **Build - verify - document** in every lesson; the runbook is the graded artefact.
3. **Show failures on purpose:** each module has one planted, realistic failure from 10-pitfalls.
4. **Say what was not verified.**

### Claude Code prompt template (from the owner's own best prompts)
```
You are working on my Hermes VPS. Current confirmed state: <bullets>.
Task: <one outcome>.
Rules: inspect before changing; back up every file before editing (*.bak-<stamp>-<reason>); do not expose secrets or tokens;
do not touch <protected things>; restart only what is required; verify with real checks (not assumptions);
finish with: root cause, every change made, what is running now, what you could not verify.
```

## Assets to capture for the sales page and lessons
Screens: Jarvis hero (idle/speaking), Mission Control Overview (network filling its panel), 3D Office with beams and a blocked agent, Tasks board with unblock/reassign, Telegram topics with tags, Factory Floor feed, health score 100, backup listing, `tailscale serve status`. Short clips: sentence-by-sentence speech, packet flying to an agent, phone opening the https link.

## Risks to disclose to students
Free models vary in speed and accuracy; SOUL rules are guidance; OAuth scopes may be broader than the UI implies; a single VPS is a single point of failure until backups leave the server; third-party UIs (Hostinger, Tailscale, Telegram) change.

## Open decisions before launch
Name and price (not set here), whether to ship `code/` as a starter repo, licence for the JARVIS artwork (the portrait was cropped from a user-supplied image - use your own artwork or a licensed one in anything you sell), whether to include a hosted "done-for-you" tier, and a support policy for OAuth issues.
