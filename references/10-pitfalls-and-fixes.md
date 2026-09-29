# 10 - Pitfalls and fixes (every one of these happened)

## Migration and platform
| Symptom | Cause | Fix |
|---|---|---|
| Telegram `Conflict: terminated by other getUpdates` every ~40 s | old Windows gateway still polling the same token (Startup `.vbs`) | kill it, move the launchers aside, one poller per token |
| Product Factory/Reach/Production reply "could not connect to the AI model service" | profile's provider not logged in (Nous per profile) | move to OpenRouter free or log that profile in |
| Scout: Gemini 403 and a paid fallback | bad key + fallback costing money | switch to a free OpenRouter model, remove the paid fallback |
| Dashboard login: `Invalid Host header` on https | dashboard only knew its bound host | `dashboard.public_url` in that dashboard's own config |
| Hermes `hermes gateway reload` does nothing useful | wrong verb | `hermes gateway restart` |
| Google OAuth ends on a dead `localhost:1` page | expected for headless setup | paste the failed URL (contains `code=`) to the setup script |
| `python3 -m venv` fails on the server | system Python 3.14 has no ensurepip | create venvs with the Hermes venv's Python |
| OAuth CLI fails in a script | non-interactive context | run in an interactive SSH session |

## Dashboards
| Symptom | Cause | Fix |
|---|---|---|
| New API route 404 after deploy | plugin API mounts at process start | restart the dashboard |
| Expanded card rows squashed | old CSS `.card-detail div{display:flex}` leaking | scoped override |
| Progress bars/labels overflow on phones | fixed widths, no `box-sizing` | fluid widths; test at 375 px |
| Graph small in a tall panel | fixed height SVG | `viewBox` + `width:100%;height:auto`, flex-centre the panel body |
| "Next: 0s ago" for future cron times | naive humaniser | `jIn()` for future, `jAgo()` for past, `humanCron` for schedules |
| Model change refused, left a profile on the wrong model | flaky single-shot live probe | 3 probe retries, and the revert path forces restore |
| Invisible mic error while idle | error only shown in busy states | show `error` in the status line in red |

## Jarvis
| Symptom | Cause | Fix |
|---|---|---|
| 25-41 s replies | slow model, no streaming, speech after full reply | model override + live facts + sentence streaming + pre-warm (06) |
| "Zero unread emails" / invented briefing time | free model bad at tool lookups | give facts in the prompt |
| Safari "browser can't record audio here" | plain http page (insecure context) and/or no MediaRecorder | https address; Web Audio WAV recorder; specific messages and banner |
| First words garbled in a synthetic test | stream warm-up artefact of the test rig | "arming" state before "Listening" |
| Reply shows as text but silent on the phone | autoplay policy + Web Audio path suspended after mic | shared unlocked audio element, no Web Audio routing on touch, Hear it button, Test sound diagnostic |
| Local voice too slow | int8 ONNX slower than fp32 on this CPU (RTF 1.4 vs 0.5) | benchmark both; use fp32 |
| Speech cut / markdown read aloud | raw text sent to TTS | `_speakable` strips markdown, links, emoji, tags |

## Ops
| Symptom | Cause | Fix |
|---|---|---|
| Backups not taken before a deploy | `pkill -f` matched and killed its own shell | kill by PID; verify the backup exists before deploying |
| Self-matching `pgrep`/`ps grep` false "stray process" | grep matches its own command | check listeners with `ss -ltnp` |
| Heredoc/quoting corrupts patch scripts | shell quoting of `'`, `\n`, curly quotes | write files with the file tool; `NL = chr(10)`; marker slicing |
| Test sessions clutter history | tests create real sessions | title tests clearly; prune only what you can identify |
| "1 job failed" on a cron that found nothing new | model explained instead of replying exactly `[SILENT]` | prompt: "reply with exactly [SILENT] and nothing else" |
| Unfilled placeholder in a SOUL | template text shipped | grep SOULs for `[` before shipping |
| Hermes warns `suspicious description content` for a third-party MCP tool | built-in scanner; the tool (repo checkout/push) is not needed | exclude that tool in the profile: `mcp_servers.<name>.tools.exclude` |
| Lead Engineer / QA silently on free models after migration | routing policy pointed at Windows CLI paths plus a stale AVAILABLE cache; the CLIs never existed on the server; the availability check only ran `--version` | install the CLIs, fix paths, make the check require sign-in, refresh the cache, sign in (03, 14) |
| Product Factory Lead Engineer blocked: "Implementation file does not exist" although Claude Code ran | the director runs `claude -p` with `--max-turns 1`, `--permission-mode dontAsk` and no allowed tools, so every file write is denied (`permission_denials` in the JSON output) and it stops with `error_max_turns`; the step then falls back to a free model that writes no files and the gate correctly blocks | give Claude Code write access limited to the project folder (project-level `.claude/settings.json` allowing Read/Write/Edit/Glob/Grep only) and allow several turns; diagnose with the saved prompt file and the JSON `permission_denials` |
| Build gate: "Build verification did not pass" / "Successful build verification evidence is missing" although files exist | the worker cannot run tests (no shell) and reports `exit_code: null`; the evidence check reads a copy of the artifacts | pipeline-run sandboxed tests stored in the result itself (14) |
| Gate says "Implemented code artifact has no existing in-project file" | the model's own `files_changed` list is missing or wrong | derive the file list from the filesystem (14) |
| QA (Codex) cannot run tests: "No usable temporary directory found" | read-only sandbox has no writable temp | run QA in a throwaway copy with `workspace-write` (14) |
| Codex as a fallback "fails" a specialist that needs to write files | the read-only sandbox is the default for every specialist except the one you scoped write access to | give a fallback worker `--sandbox workspace-write` (with `network_access=false`) wherever it is expected to deliver files |
| A gate rejects evidence a worker clearly produced correctly | the gate validator was written for one shape (e.g. a single object) but the real, honest output is a list (e.g. several test runs) | accept both shapes in the validator; tell the model the expected shape explicitly in the prompt; unit-test the validator with both shapes before trusting it |
| Patch to a decorated function broke gate registration ("'dict' object has no attribute 'resolve'") | new function inserted between the decorator and the function it decorates | insert above the decorator line; test import and a dry call before running the pipeline |
| A YAML edit broke a config file | new text was written before it was validated; values containing a colon and space need quotes | parse the new text with a YAML loader BEFORE writing, quote such strings, keep a backup |
| Paid model quietly used as fallback | `fallback_providers` still listed a paid model | list free models only; audit every profile's `model` and `fallback_providers` |

## Things that look like bugs but are not
Honcho "token expired" until first use; `hermes update` nag (24 commits behind) is cosmetic; Nous "no profile secret scope" warnings (08); static-harness `/stream` 404s.
