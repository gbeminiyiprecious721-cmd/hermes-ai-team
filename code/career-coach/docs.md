# Data Science Career Coach

Internal profile: `data-science-career-coach` · Display name: **AI Career Coach**

## Voice architecture (2026-09-24)

**Live Conversation (built, real, local):** "Start Live Conversation" opens the mic once via `getUserMedia`, runs an energy-threshold VAD (Web Audio `AnalyserNode`, RMS of the time-domain signal — no external library) to detect speech start/end, records each utterance with `MediaRecorder`, uploads it to `POST /voice/transcribe` (real faster-whisper via `tools/transcription_tools.py` — the same backend this Hermes install uses elsewhere), auto-sends the transcript through the existing `/chat/send` (no manual Send click), auto-plays the real KittenTTS reply, and loops back to listening when it ends. Barge-in is real: if the VAD detects speech while the coach's audio is playing, playback stops immediately and a new utterance capture starts. All cleaned up (tracks stopped, AudioContext closed, rAF cancelled) on End Session, End Live Conversation, or component unmount.

**OpenAI Realtime provider: not implemented, and here's exactly why and what it needs.** No `OPENAI_API_KEY` exists anywhere in this install (checked both the global and profile `.env`) — per the owner's own stated fallback rule, that means realtime mode is simply unavailable right now, not a build gap. To add it later:
1. `OPENAI_API_KEY` server-side only (`.env`), never sent to the browser.
2. A new `POST /voice/realtime/session` dashboard endpoint that calls OpenAI's session-creation endpoint server-side and returns only a short-lived ephemeral client token to the browser (current OpenAI Realtime docs should be re-checked at implementation time — this session did not fetch external web docs).
3. Browser-side WebRTC: exchange SDP offer/answer with OpenAI using the ephemeral token, attach the mic stream directly to the peer connection (bypassing the local VAD entirely — OpenAI's realtime endpoint does its own turn detection).
4. Configurable via `OPENAI_REALTIME_MODEL` / `OPENAI_VOICE` env vars, not hardcoded.
5. Cost controls: idle timeout + hard max session duration + explicit termination on End Session/page unload — the local path already has no per-minute cost, so this only matters once realtime is added.
The current `send()`/VAD/state-machine code in `index.js` is written so a second provider could plug in at the "capture audio → get transcript → get reply → play audio" seams without touching the chat/persistence layer — but there is no unused `VoiceProvider`/`OpenAIRealtimeVoiceProvider` class sitting in the codebase today, on purpose: an uninstantiable class for a provider with no credentials would be dead code, not real architecture.

**Avatar:** still the real photo in a video-tile with state-reactive border color (blue=listening, amber=thinking/transcribing, green=speaking) — genuinely wired to the same voice/lesson state machine, not decorative. No talking/lip-synced avatar; that needs a paid provider decision, not attempted without the owner's explicit go-ahead per the standing "never subscribe on my behalf" rule.

**Real latency numbers (2026-09-24, on Claude Opus 5.5 via the now-active Nous subscription):** text-only turns ~5.95s, remarkably consistent across samples. Voice-on turns (coach also calls its TTS tool) 17.7s–30.1s, scaling with reply length — this gap is architectural: the current `/chat/send` is one opaque CLI subprocess call bundling reasoning + any TTS tool call with no intermediate signal, confirmed by checking the CLI itself (`hermes -z` has no `--stream` flag). Real streaming would mean calling Hermes's agent loop as a library instead of shelling out — a genuine rearchitecture, not attempted this round. This is *the* concrete case for Deepgram/Cartesia below: they don't fix Hermes's own reasoning time, but streaming TTS (start speaking the first sentence while the rest is still generating) would hide most of the voice-mode overhead the numbers above show.

### Deepgram Streaming STT — not implemented, no `DEEPGRAM_API_KEY`

What it needs: a WebSocket connection to Deepgram's streaming endpoint, opened server-side (the key must never reach the browser) with the browser's mic audio relayed through — either the dashboard backend proxies raw PCM frames over its own WebSocket to the browser, or (simpler, matching how `/voice/transcribe` already works) a short-lived scoped token is minted server-side and handed to the browser to connect directly, if Deepgram's current API supports that pattern (verify at implementation time — this session did not fetch live Deepgram docs). Deepgram returns interim + final transcripts as JSON messages over the same socket; "final" replaces the current local VAD's job of deciding an utterance is complete, and would let the local energy-threshold VAD retire entirely for that path (Deepgram does real endpointing). Config: `DEEPGRAM_API_KEY` (server-side), a `Speech Recognition` setting choosing `Deepgram Streaming` vs `Local Whisper`, with local kept as the always-available fallback exactly as it is today.

### Cartesia Sonic Streaming TTS — not implemented, no `CARTESIA_API_KEY`

What it needs: as Hermes's reply text becomes available, split it into sentence-sized chunks (a simple sentence-boundary buffer — flush on `.`/`?`/`!` followed by whitespace, with a max-length safety flush so one very long unpunctuated clause doesn't stall playback) and stream each chunk to Cartesia's streaming synthesis endpoint as soon as it's ready, playing the returned audio chunks as they arrive rather than waiting for the whole reply. This only pays off once Hermes's own response is itself streamed (see the architecture gap above) — chunking a reply that only exists in full after a single blocking subprocess call doesn't save anything over what KittenTTS already does today. Config: `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`, `CARTESIA_MODEL`, all server-side. A `Preview Voice` action is just: synthesize a short fixed sample sentence with the selected voice ID and play it — doesn't touch coach memory or personality, exactly as required.

### HeyGen LiveAvatar — not implemented, no `HEYGEN_API_KEY`, and no `AVATAR_ID`

**Owner action required, not invented:** create a custom LiveAvatar in the HeyGen dashboard from `profiles/data-science-career-coach/assets/coach-reference.jpg` (or a short video if HeyGen's current quality bar needs one — check their current requirements when you get there), then give me the resulting `AVATAR_ID`. I have not submitted your photo anywhere or created a placeholder ID.

Once both exist, the integration point is a `HeyGenLiveAvatarProvider` behind the same seams `send()` already has (`initialize → createSession → connectStream → setState → speak → interrupt → stopSpeech → endSession → destroy`), replacing the static photo-frame with HeyGen's video stream when configured and falling back to the photo when not. Open architectural question to resolve at implementation time (do not guess): whether HeyGen's LiveAvatar accepts text directly (and does its own TTS) or expects pre-generated audio — these are different integrations, and if HeyGen does its own speech synthesis, that's a real conflict with Cartesia that needs a decision (probably: HeyGen owns voice+face together when active, Cartesia/KittenTTS only apply when no avatar is configured), not two competing audio streams running at once.

### Provider settings panel — not built yet

The real version of this needs to actually probe each provider (credential present + a lightweight reachability check) before showing anything but "Not configured" — never show a provider as available just because it's coded, matching everything else in this project's honesty rule. Reasonable shape once there's more than one working option per category: `GET /voice/providers` returning `{stt: [...], tts: [...], avatar: [...]}` each with `{id, label, status: "connected"|"not_configured"|"error"}`, driving a settings panel that lets the owner pick per category and persists the choice (another small `coach_db` table, same pattern as `notes`). Not built this round — there's exactly one working option per category today (Local Whisper, KittenTTS, static photo), so a picker UI would have nothing real to pick between yet.

## Full redesign brief (owner reference, saved 2026-09-24 — not yet implemented)

The owner supplied a full "finish the dashboard" brief — button-by-button audit, coach visual states, teaching workspace with tabs, Your Turn/Quiz interactive modes, design system tokens, empty/loading/error states, animations, and a full testing/reporting checklist. Saved verbatim at `live-coach-redesign-brief.md` (same folder) per the owner's instruction to save it before building. Nothing in it has been implemented yet — read that file in full before resuming this work.

## Target structure (owner reference, saved 2026-09-24 — not yet fully implemented)

The owner supplied this wireframe as the structure the Live Coach dashboard should follow. Saved verbatim for reference; no implementation changes were made when this was captured.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ HERMES   Data Science Career Coach   ● Online   🔔  ⚙️  Precious            │
├──────────────┬──────────────────────────────────────┬────────────────────────┤
│              │                                      │                        │
│ Dashboard    │       LIVE HUMAN AI COACH            │ TODAY'S PLAN           │
│              │                                      │                        │
│ Live Coach ● │   ┌──────────────────────────────┐   │ ● Python OOP     30m  │
│              │   │                              │   │ ○ Coding         30m  │
│ Learning Hub │   │    REAL COACH FACE           │   │ ○ Project        45m  │
│              │   │                              │   │ ○ Career         20m  │
│ Practice     │   │   Speaking / Listening       │   │ ○ Interview      20m  │
│              │   │                              │   │                        │
│ Projects     │   └──────────────────────────────┘   ├────────────────────────┤
│              │                                      │ LEARNING PROGRESS      │
│ Career       │ 🎤  🔊  Transcript  ● LIVE  24:18   │ Python          60%    │
│              │                                      │ SQL      Not assessed  │
│ Interviews   ├──────────────────────────────────────┤ ML              40%    │
│              │                                      │ AI Eng.   Not assessed │
│ Progress     │ TODAY'S LESSON                       ├────────────────────────┤
│              │                                      │ CAREER GOAL            │
│ Goals        │ Python OOP                           │                        │
│              │ Getters, Setters & Deleters          │ Data Scientist /       │
│ Schedule     │                                      │ AI Engineer            │
│              │ ① Explain → ② Code → ③ Your Turn    │                        │
│ Analytics    │ → ④ Quiz → ⑤ Summary                ├────────────────────────┤
│              │                                      │ RECENT ACTIVITY        │
│ Settings     ├──────────────────────────────────────┤                        │
│              │                                      │ ✓ Python exercise      │
│              │ ┌──────────────┐ ┌─────────────────┐ │ ✓ Mock interview       │
│              │ │ LIVE CODE    │ │ KEY POINTS      │ │ ✓ Project update       │
│              │ │              │ │                 │ │                        │
│              │ │ School(...)  │ │ Getter = read   │ │                        │
│              │ │              │ │ Setter = change │ │                        │
│              │ └──────────────┘ └─────────────────┘ │                        │
│              │                                      │                        │
│              ├──────────────────────────────────────┤                        │
│              │ 💬 Ask your coach...            ➤   │                        │
│              │                                      │                        │
│              │ Explain Again | Simplify | Quiz Me  │                        │
│              └──────────────────────────────────────┴────────────────────────┘
```

Differences from the current baseline below, noted for when work resumes:
- Nav splits `Practice` and `Projects` into two separate items, and `Career` and `Interviews` into two separate items (baseline currently combines each pair). Adds `Schedule`, `Analytics`, `Settings` — none have backing data yet, so baseline deliberately left them out; would need real data/functionality behind them before adding as more than dead links.
- Top bar shows a notification bell, settings gear, and the owner's name next to online status — baseline's top bar is the host Command Center's own header, not something this plugin controls.
- Session controls order/placement: mic, speaker, Transcript label, ● LIVE + timer, all in one row under the coach — baseline has the state badge overlaid top-left on the coach stage instead, and controls below the avatar.
- Panel labelled "LIVE CODE" (baseline: "CODE").

## Dashboard structure (current baseline, 2026-09-24)

This is the reference structure for the dashboard as it exists right now — a snapshot to build from, not a plan. Frontend: `/root/.hermes/plugins/data-science-career-coach-hub/dashboard/dist/index.js` (+ `style.css`). Everything below is live and backend-wired unless marked otherwise.

**App shell** — two-column grid: a left sidebar nav (`SideNav`) + a main content area (`.dscc-main`). Sidebar collapses to a hamburger-triggered drawer with a scrim below 860px. Nav items (icon + label), each a real page with real backing data — no items were added for sections without data (e.g. no fake "Settings"/"Agents"/"Schedule" entries):

1. 🎥 **Live Coach** (`live`) — default landing tab, described below
2. 🏠 **Dashboard** (`dashboard`) — Today's Plan / Learning Progress / Career Roadmap (top 3 phases) / Recent Activity, 2×2 grid
3. 🗺️ **Learning Hub** (`roadmap`) — full 8-phase curriculum roadmap
4. 📊 **My Progress** (`progress`) — Learning Progress bars + Career Skill Matrix
5. 🛠️ **Practice & Projects** (`projects`) — portfolio project cards
6. 💼 **Jobs** (`jobs`) — tracked job applications
7. 🎤 **Interview Prep** (`interviews`) — Interview Analytics panel (avg scores across dimensions + frequently-missed concepts) + Interview History cards
8. 🎯 **Goals & Plans** (`goals`) — goal cards

**Live Coach page** (`LiveCoachPage`) — 2-column layout: center column + a 300px right rail (stacks under the center below 1180px).

*Center column, top to bottom:*
- `dscc-coach-stage` — a 16:9 card, the dominant visual element:
  - `CoachStateBadge` top-left: real derived state (`idle`/`thinking`/`explain_concept`/`live_coding`/`your_turn`/`quiz`/`summary`/`interview`) — `thinking` is real client-local send state, the rest come from polling `/live/stage` (a real signal the coach sets itself via the `coach_set_lesson_stage` tool; never guessed)
  - `Avatar` (large): real portrait if uploaded (`GET /avatar/portrait`), else an SVG person-outline placeholder — never the old bare "AI" text
  - `dscc-coach-controls`: 🎙️ mic (honestly disabled, tooltip explains why), 🔈/🔊 speaker (real — toggles whether the coach also speaks its reply via TTS), 📝 transcript show/hide toggle, ⏹️ End Session (sends a real closing message asking the coach to wrap up and set stage to idle)
- `StageTracker` — the 5-step Explain Concept → Live Coding → Your Turn → Quiz → Summary tracker (or a single "interview in progress" pill), only rendered when `/live/stage` has a real, non-stale signal
- `TeachingArea` — Code / Key Points side-by-side panels, populated by regex-extracting a fenced code block and bullet lines out of the coach's own latest reply (real content, not generated separately)
- `dscc-live-transcript` — chat bubbles with avatar/name/timestamp per message; toggled by the 📝 control
- 8 quick-action buttons (Explain Again, Simplify This, Give an Example, Ask Me a Question, Quiz Me, Show Code, Next Topic, Mock Interview) — each sends a real prompt through the same chat pipeline
- Input row (text input + Send)

*Right rail:* `TodayPanel`, `ProgressPanel`, `CareerGoalPanel`, `ActivityPanel` — the same real panels used elsewhere, refreshed every 20s.

**Backend endpoints** (`plugin_api.py`, all real, no mocked data): `/profile /today /progress /roadmap /sessions /projects /jobs /interviews /interviews/analytics /goals /activity /avatar/status /avatar/portrait /live/stage /chat/send /chat/audio/<file>`.

**Known placeholders, not gaps:** coach portrait is a generic SVG until `assets/coach-reference.jpg` is uploaded; mic input is visibly disabled (no STT wired yet); chat text renders as plain text (no markdown styling yet).

## Architecture

Extends the existing Hermes install — no separate app, no new database engine (SQLite, matching `kanban.db`/`state.db`).

- **Profile**: `/root/.hermes/profiles/data-science-career-coach/` — created via `hermes profile create` (not cloned; fresh profile, custom SOUL.md).
- **Personality**: `/root/.hermes/profiles/data-science-career-coach/SOUL.md` — coach persona, the 9 core modes (`/today /learn /practice /quiz /career /interview /review /project /jobs`), the Socratic teaching rule, memory discipline, spaced-revision rule.
- **Storage**: `/root/.hermes/profiles/data-science-career-coach/coach.db` (SQLite). Single shared module `coach_db.py` in the same directory — the one code path both the dashboard API and any future agent-side tool must use, so there's no risk of the two-path drift bug found and fixed elsewhere in this install's kanban code this session. Tables: `learning_topics`, `sessions`, `career_profile`, `skills_matrix`, `projects`, `jobs`, `interviews`, `goals`, `roadmap_phases` (seeded with the 8-phase curriculum from the spec), `activity_log`.
- **Dashboard**: a new Command Center tab, "AI Career Coach", at `/root/.hermes/plugins/data-science-career-coach-hub/dashboard/` (manifest.json + plugin_api.py + dist/index.js + dist/style.css), mounted the same way the existing Mission Control plugin is. Enabled via `plugins.enabled` in `/root/.hermes/config.yaml` (a real security gate in this Hermes version — user dashboard plugins don't auto-execute).
- Reachable at `https://hermes-vps.tailed9e28.ts.net` → **AI Career Coach** tab (Command Center, port 9119).

## What's actually live vs. not yet wired

**Live and verified (each tested against real data, not just the model's self-report):**
- Profile boots and responds in character; 12 agent tools let it read *and write* `coach.db` during a live session (lessons, topics, interviews, projects, jobs, goals, career profile, skills, lesson-stage signal, interview analytics).
- Dashboard renders real data end-to-end across all 8 pages.
- Live Coach page: real chat (`/chat/send` runs the actual CLI, not a stub), real 5-stage lesson tracker, real code/key-points extraction, real voice playback (KittenTTS — neutts was tried first but has a broken upstream dependency chain, documented in RUNBOOK.md).
- Telegram: a dedicated "AI Career Coach" topic exists in the Hermes supergroup, routed via `gateway.profile_routes` in `config.yaml`. Outbound delivery confirmed; inbound (a real message from the owner in that topic) not yet confirmed.

**Not yet wired:**
- Real-time avatar (talking video) — Phase 2/3, needs a paid vendor decision, not started.
- Speech-to-text (mic input) — visibly disabled with a stated reason rather than faked.
- Slack routing — Telegram only so far.
- Chat markdown rendering (currently plain text with `white-space: pre-wrap`).
- A separate, fully immersive Mock Interview screen (role/type selectors, live per-question progress) — mock interviews currently run through the same Live Coach chat; results appear for real afterward on Interview Prep, not as a live in-session gauge (deliberately, to avoid fabricating a signal that doesn't exist).

## How to use it now

- **Dashboard**: open the AI Career Coach tab at `https://hermes-vps.tailed9e28.ts.net`.
- **Chat directly**: `hermes --profile data-science-career-coach chat` (or via the dashboard's Chat page once the profile is selected in the sidebar).
- **One-shot**: `hermes --profile data-science-career-coach -z "your message"`.

## Backups

Every file this build touched has a timestamped backup in `/root/backups/manual-changes/`:
`config.yaml.before-career-coach-*`, `career_coach_SOUL.md.new`, `data-science-career-coach.SOUL.md.default-*`.

## Troubleshooting

- Dashboard tab missing → check `plugins.enabled` in `/root/.hermes/config.yaml` includes `data-science-career-coach-hub`, then restart the dashboard on port 9119.
- Dashboard shows stale/no data → confirm `coach.db` exists at `/root/.hermes/profiles/data-science-career-coach/coach.db` (run `python coach_db.py` in that directory to (re)initialise; it's idempotent).
- Profile responds as Gideon instead of the coach → you must pass `--profile data-science-career-coach` explicitly; just `cd`-ing into the profile directory is not enough.

## No new environment variables

This profile has no dedicated API keys (`.env` is effectively empty) — it inherits the shared provider keys already configured for the other profiles via the multiplexed gateway, same as `scout`/`scribe`/etc.
