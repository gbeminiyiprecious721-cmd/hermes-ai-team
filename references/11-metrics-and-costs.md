# 11 - Metrics, benchmarks and costs (measured on this server)

## Server
2 vCPU AMD EPYC 9354P (AVX-512, VNNI), 7.7 GB RAM (about 2.3 GB used with everything running, 5.5 GB available), 96 GB disk (19% used), load average ~0.1 idle.
Backups ~255 MB for 7+7+4 generations. Voice service ~0.75 GB RAM when warm (MemoryMax 1500M).

## Jarvis reply speed (same prompt the page sends: voice hint + live facts + question; zero tool calls)
| Mode / model | Correct of 5 | Median | Worst |
|---|---|---|---|
| Fastest - nemotron-3-nano-omni (free) | 4/5 | 3.6 s | - |
| **Balanced - nemotron-3-super-120b (free), default** | **5/5** | **8.0 s** | 10.7 s |
| nex-n2.5-pro (free) | 5/5 | 8.3 s | - |
| Original - Gideon's Solar | lookups wrong or timed out | ~25 s | 41 s to first word (before streaming) |
Latest end-to-end: "How many tasks are on the board and how healthy is the system?" -> first speech 5.1 s after Send, correct answer.
`/jarvis/brief`: 10 s first call -> 2.5 s cold -> 2 ms warm (stale-while-revalidate).

## Voice generation (Kokoro on 2 vCPU)
| Model | Real-time factor | Note |
|---|---|---|
| fp32 (325 MB) | ~0.5 (2.8-3.9 s for 5.7 s of speech) | used |
| int8 (92 MB) | ~1.4 | slower on this CPU; deleted |
Edge cloud voice: ~0.7 s to prepare, free, text goes to Microsoft. First sentence with the local voice adds ~2 s.

## GPT models through the ChatGPT subscription (measured 2026-09-21, provider `openai-codex`)
gpt-5.6-luna median 4.9 s, gpt-5.6-terra 4.7 s, gpt-5.5 4.6 s (first word ~3.5-3.9 s), all answering the 5 status questions correctly from the live facts with zero tool calls. Now used for Jarvis Premium mode (active) and as Gideon's first fallback; see 14.

## Quality checks
Round-trip every voice through the local whisper: "Good evening, Precious ... at eight." came back verbatim; numbers survive ("2,906 unread emails").

## Costs
- Hosting: the VPS plan (the owner's existing Hostinger plan); Tailscale free tier; Telegram/Slack free.
- Models: specialists and Jarvis run on **free** OpenRouter/Nous models. Only Gideon's fallback (`openai/gpt-4o-mini` via OpenRouter) can cost money; a spend rule caps behaviour but is guidance only.
- Voice: free (Kokoro local, Edge fallback). Paid ElevenLabs was explicitly declined.
- Optional upgrades: a faster paid model for Jarvis (consistent 2-4 s and reliable tool use); a larger VPS for a snappier local voice; off-server encrypted backups.

## Dashboard sizes
Command Center bundle ~150 KB (incl. two embedded images), Mission Control ~100 KB + three.js 0.160 (vendored). No build step.
