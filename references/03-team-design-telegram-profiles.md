# 03 - Team design: Telegram topics -> profiles, SOULs, models

## The team
| Topic (Telegram) | thread id | Profile | Tag | Job |
|---|---|---|---|---|
| General | 1 (no route = default) | `default` | Gideon | Chief of Staff and Product Factory Director; talks to Precious, delegates to everyone |
| Builder | 147 | `product-factory` | Product Factory | builds products through 11 internal specialist roles (Product, Research, Architecture, Lead Engineer, Data/ML, QA, Security, UI/UX, ML Eval, DevOps, Release) |
| Reach | 152 | `socialmediaagent` | Reach | social content |
| Production | 155 | `youtube-production-agent` | Production | video/script production |
| Scout | 158 | `scout` | Scout | research |
| Scribe | 206 | `scribe` | Scribe | writing and documentation |
| Factory Floor | 247 | read-only feed | none | one line per task/specialist event |

Also present but unrouted: `geminiworker`, `openrouterworker`.

## Routing config (in `~/.hermes/config.yaml`)
```yaml
gateway:
  profile_routes:
    - name: telegram-pf-group-scout        # any label
      platform: telegram
      chat_id: "-100XXXXXXXXXX"            # the group
      thread_id: "158"                     # the topic
      profile: scout
      enabled: true
```
One entry per topic. Only the `default` profile has `TELEGRAM_BOT_TOKEN`/`SLACK_*` in its `.env`.
Every reply is posted by the same bot name ("Admin Manager"), so each SOUL forces a **tag** at the start of replies (`Scout:` ...) - the reader knows who answered.

## SOUL design (guidance, not enforcement)
Each profile has a `SOUL.md`. The pattern (see `code/souls/`):
1. **Identity block**: who you are, who you serve, your tag, one-line role.
2. **Team map**: who else exists and what to ask them. Gideon knows everyone; specialists know Gideon.
3. **Style rules**: plain language, no dashes as decoration, no unexplained jargon, short answers first.
4. **Delegation rules** (Gideon): create Kanban tasks for anything a specialist should do; do not do specialist work yourself; report results back in the topic.
5. **Worker rules** (specialists): take one task, do it, save output, mark done; if blocked say why in one line.
6. **Stop-and-ask list**: spend limits, new subscriptions, destructive actions, external publishing, agreements.
7. **Mail/calendar/personal data rules**: read-only unless the owner says yes each time.
A SOUL never replaces a permission. Product Factory and Gideon still have terminal access.

### Spend rule now in Gideon's SOUL
Ask first above 2 GBP in one action or 5 GBP in a day; under the limits proceed but report what was spent and why; anything recurring or a new paid service always needs a yes.
(An unfilled "[SET A THRESHOLD]" placeholder sat in the file for days - grep SOULs for `[` placeholders before shipping.)

## Models (2026-09)
- Specialists: `nvidia/nemotron-3-super-120b-a12b:free` on OpenRouter, fallback `nex-agi/nex-n2.5-pro:free` (free).
- Gideon (from 2026-09-22): **`gpt-5.6-terra` via the ChatGPT subscription (`openai-codex`)** as primary; fallbacks are free only (`nex-agi/nex-n2.5-pro:free`, `nvidia/nemotron-3-super-120b-a12b:free`, then Solar via Nous). The paid `openai/gpt-4o-mini` fallback was removed on 2026-09-21 to prevent silent spend. Trade-off: if the ChatGPT allowance or login fails he drops to free models (slower, less reliable) instead of paying.
- The two unrouted workers `geminiworker` (Gemini) and `openrouterworker` (`openai/gpt-5.6-luna`) use paid models by design and only run when a task is assigned to them.
- Jarvis conversations use a **per-session override** (never a config write): fastest = nemotron-3-nano-omni, balanced = nemotron-3-super (default), original = Gideon's own model.
- The dashboard's model dropdown only offers an allowlist of verified free models and live-probes a tool call (3 tries) before switching; every change is written to `dashboard-actions.log`.
### Product Factory workers (Claude Code and Codex)
Product Factory does not run its Lead Engineer on a Hermes model: `policies/routing_policy.yaml` routes Lead Engineer, Data/ML implementation and several reviews to **Claude Code** (CLI, `claude -p`) with **Codex** (CLI, `codex exec`) as fallback, and independent QA to **Codex**; the other roles use free models (nemotron, nous, gemini). Both CLIs need a subscription sign-in on the machine that runs them. Check with `/root/.hermes/scripts/check-workers.sh` (installed and signed in, no quota used). A moved install keeps the old machine's paths and cached status - re-check after any migration. Since 2026-09-22 the director runs Claude Code with file tools only (inside the project folder), runs the project's tests itself in a no-network sandbox and lets Claude repair failures for up to 2 rounds, and runs Codex QA in a throwaway copy of the project; a `GATE_WAIVERS.json` mechanism lets a named, reasoned known limitation pass a gate without hiding the real result; and a plain model timeout is treated as retryable instead of being cached as a hard failure. A full project (`csv-quote-compare-smoke`) reached `COMPLETED` end to end - all 6 specialists, all 7 gates, Security and Release both genuinely exercised for the first time. See 14 for the full account.

Lessons: a profile on a provider it is not logged in to answers "could not connect to the AI model service" (Reach/Production did this until moved to OpenRouter); a Gemini profile with a bad key and paid fallback silently costs money.

## Onboarding message pattern
Each topic got an introduction reply: who I am, what I do, what to send me, who I hand off to. Test by messaging each topic and checking the tag, the model, and that Gideon can delegate Scout -> Scribe in one chain (Kanban).

## What the owner needs to know (plain language)
"The bot name is always Admin Manager. The tag at the start of the message tells you which teammate answered. Anything big goes on the board; watch it in Mission Control or in the Factory Floor topic."
