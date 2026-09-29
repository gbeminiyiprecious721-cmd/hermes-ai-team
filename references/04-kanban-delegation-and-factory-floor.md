# 04 - Kanban delegation, Factory Floor and the Obsidian hand-off

## The flow
```
Owner (Telegram / Jarvis / Mission Control)
   -> Gideon creates a task:  hermes kanban create "<title>" --assignee scout
   -> gateway dispatcher starts the assignee (max_in_progress 2, max_in_progress_per_profile 1)
   -> specialist works, saves outputs, marks done (or blocked with a reason)
   -> Factory Floor script posts one line per event to Telegram topic 247
   -> library_export writes a DRAFT note per finished task into the vault 00-Inbox/Agent-Outputs/<Agent>/
   -> Mission Control (Tasks, Library, Office) and Command Center (Jarvis brief) read the same board
```
Config (`config.yaml`):
```yaml
kanban:
  review_dispatch: true
  max_in_progress: 2
  max_in_progress_per_profile: 1
```
Board file: `/root/.hermes/kanban.db` (SQLite). CLI: `hermes kanban create "<title>" --assignee <profile> [--body ...] [--priority N] [--parent <id>] [--json]`, then `list`, `unblock`, `reassign`, `archive`.

## Gideon's delegation rule (in his SOUL)
Anything a specialist should do becomes a task; Gideon replies with the task id and who has it, then reports when it is done.
Verified chain: Scout researches -> Scribe writes a note from Scout's output (Firecrawl blog post test), all three tasks done and visible everywhere.

## Factory Floor (`code/scripts/factory_floor.py`, unit `hermes-factory-floor`)
- Polls every 5 s: the Kanban DB (all agents) and the Product Factory project state files (the 11 internal specialists).
- Posts with the Bot API `sendMessage` (does **not** conflict with the gateway's polling - only `getUpdates` does).
- Batches up to 12 lines per message, `disable_notification`, cursor file so restarts never repost history.
- Token read from `.env`, never printed. Topic id and chat id are constants at the top.
- Skip rule for test tasks (titles starting `Test:`, `Feed test`, ...) lives in the exporter, not the feed.

## Library export (`code/scripts/library_export.py`, unit `hermes-library-export`)
- One note per finished task, written once, never overwritten; text deliverables embedded (cap 60 KB), obvious secrets masked.
- Follows the vault's AGENT-WORKFLOW rules: only `00-Inbox`, marked as draft, never touches curated notes or `.obsidian`.
- Waits a few seconds after "done" so files are complete.
- **The vault it writes to is the server copy** - see 02 (not synced to the PC vault).

## Mission Control actions (Tasks page)
Create task (assignee list, priority), unblock (with a reason), reassign, open the task drawer (attachments preview, comments/history).
API: `POST /kanban/tasks`, `/kanban/{id}/unblock`, `/kanban/{id}/reassign`; every action goes through the `hermes kanban` CLI with an allowlisted assignee list and is written to `dashboard-actions.log`.
Pattern (reuse it): validate against an allowlist -> call the official CLI -> log who/what/when -> return the fresh state -> push an SSE `kanban` event so every open page refreshes.

## Live updates
Mission Control `/stream` (Server-Sent Events) emits `changed`, `kanban`, `library`, `activity`; pages fall back to 30 s polling when connected and 8 s when not. Command Center has its own `/stream` (journal + Kanban).
The 3D Office reads the same data and spawns a packet whenever a real task appears, finishes or blocks (07).

## Gotchas
- A task that "does nothing": the assignee profile is on a provider it is not logged into; check `hermes kanban list` and the gateway journal.
- Do not run a second Kanban writer; the dispatcher inside the gateway is the only starter.
- Give tasks an assignee (`default` becomes "Gideon coordinating" in the office).
