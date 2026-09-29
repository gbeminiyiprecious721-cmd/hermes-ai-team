# 06 - Jarvis: the voice + chat assistant

Inspired by a public "JARVIS Mission Control" tutorial and a reference image (helmeted figure in a glowing earth ring, waveform under the mic,
"Ideas, Systems, Impact"). Rule: **fit it into the existing dashboard as another page**, do not replace anything.

## Pipeline
```
tap mic -> Web Audio capture (ScriptProcessor) -> 16 kHz mono WAV -> POST /api/audio/transcribe (host, local faster-whisper)
  -> WebSocket /api/ws (JSON-RPC to tui_gateway): session.create -> prompt.submit
  -> events: message.start, thinking.delta, tool.start/complete, message.delta, message.complete, approval events
  -> sentence chunker -> POST /api/plugins/hermes-command-center/jarvis/speak -> mp3 (data URL) -> one shared <audio> element
```
`session.create` params used: `cols, title, model, provider, reasoning_effort, profile` (the model override is per session; **never** write config).
Approvals: the page offers only "Approve once" or "Deny" (never "always"). `session.interrupt` powers Stop.

## Why speed was the whole game
Gideon's Solar model: 25-40 s a reply, nothing on screen, speech only after the full reply -> unusable. What fixed it (measured):
| Change | Effect |
|---|---|
| Per-session model override: balanced = nemotron-3-super, fastest = nemotron-3-nano | replies ~8 s / ~4 s vs ~25 s |
| **Live facts block** prefixed to each question (`/jarvis/brief`: task counts, running tasks, schedule in plain words, health, Gmail unread COUNT, calendar event COUNT - never contents) | free models were bad at tool lookups (said "zero unread", invented times); with facts: correct with **zero tool calls** |
| Stream text as it arrives + speak each sentence as soon as it is complete | first word ~15 s -> ~5 s after Send |
| Pre-build the session on page open (`warm()`), shared session promise | no cold start on the first question |
| "One moment." filler after 5 s | perceived latency |
| Stale-while-revalidate for the brief | 10 s -> 2.5 s cold, 2 ms warm |
Bench with facts and no tools: Fastest 4/5 correct median 3.6 s; **Balanced 5/5 median 8.0 s (default)**; nex-n2.5-pro 5/5 median 8.3 s. A fast wrong answer is worse than a right one 4 s later.

## Speech in (microphone)
- Browsers expose the mic only on **https** (or localhost). iOS Safari has no MediaRecorder for this use, so record with Web Audio and encode WAV yourself (`encodeWav` in the hook source).
- UX: tap once, it stops when you pause (silence detection); or hold; or tap again to send. An "arming" state ("Getting the microphone ready...") avoids clipping the first words.
- Specific error messages (permission denied, no mic, http page) beat a generic "can't record".

## Speech out
- Default engine `jarvis`: **Kokoro** (open-source neural TTS, ONNX, runs on the server, private). `code/jarvis-voice/server.py` on 127.0.0.1:9931.
  - Voices are weighted blends of Kokoro styles; the signature is `bm_george 0.55 + bm_fable 0.30 + bm_lewis 0.15`, 3.5% deeper (asetrate/atempo), light EQ, faint echo, compressor, limiter via ffmpeg. Seven presets (Jarvis, George, Lewis, Fable, Daniel, Onyx, Emma).
  - Speed on 2 vCPU: fp32 model RTF ~0.5 (5 s sentence in 2-4 s); the int8 model was **slower** (RTF ~1.4) on this CPU - always benchmark quantised models.
  - LRU cache of 60 phrases, pre-warmed "One moment." etc.; one lock so two requests never fight for the CPUs.
- Fallback engine `edge`: free Microsoft Edge neural voices (`edge-tts`), text goes to Microsoft, starts ~2 s sooner.
- API falls back to Edge automatically if the local voice is busy or down, so Jarvis never goes silent.
- `_speakable` strips markdown, links, emoji, agent tags before synthesis.

## Phones: why "I can't hear it" happened and the fix
1. Phones only allow sound that a tap unlocked. Use **one shared `Audio` element**, unlocked with a silent WAV inside the tap (mic tap or Send), then swap `src` per sentence.
2. Do not route the element through Web Audio on touch devices: after the mic was used the AudioContext can be suspended/interrupted, and iOS silences Web Audio with the ring switch. Route only on desktop (for the orb meter); on phones animate the orb from a simulated level.
3. Give the user a **"Hear it" button** under each answer and a **"Test sound"** diagnostic (local beep, then a real sentence, printing play() results, position, duration, secure-context flag). That diagnostic is what located the problem in one round.
4. If it is still silent: check media volume (not ringer), Bluetooth routing, iPhone silent switch.

## The hero (image-following UI)
The reference portrait was cropped from the owner's screenshot (`assets/jarvis-hero.webp`, `jarvis-logo.webp`) and embedded as data URLs.
- `<img>` with `mix-blend-mode: screen` and a radial+linear mask so its dark background dissolves into the panel.
- A canvas overlay draws state-coloured waveform bars around the ring, rotating dashed rings, a scanner arc while busy, and the horizontal waveform beside the mic (`code/command-center/jarvis_hero_canvas_source.js`).
- Audio level drives a CSS variable `--lvl` that brightens and scales the portrait while speaking.
- Nav shows the gold wing logo + "JARVIS / Hermes Mission Control".

## Settings and privacy
`/root/.hermes/jarvis-settings.json`: `voice, rate, pitch, tts_enabled, primary_project, speed, engine, jarvis_voice`.
Comms are read-only by page design and SOUL, **not** by token scope (the Google token has write scopes) - say so in any course material.

## Known limits
Free models are variable (worst replies 11-16 s); Fastest can slip on details; the first question in the first seconds after page load can be slower; real-microphone behaviour on a specific phone cannot be proven from a desktop harness - ask the owner to run the Test sound button.
