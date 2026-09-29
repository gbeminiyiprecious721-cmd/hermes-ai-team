# 09 - How everything was tested (reusable method)

The assistant could not see the live dashboards (they are behind a login on a private network) and could not hear audio or use a phone.
So it built a **test harness that runs the real code against the real server** and was explicit about what it could not prove.

## The throwaway real-endpoint server
`serve_jarvis.py` (kept in the working notes; ~40 lines): a FastAPI app **on the VPS, bound to 127.0.0.1:9920, no auth**, that
1. loads the plugin's `plugin_api.py` router at `/api/plugins/<name>`,
2. mounts the host's own routers (`hermes_cli.web_routers.audio`, `.cron`),
3. exposes `/api/ws` by calling `tui_gateway.ws.handle_ws`,
4. serves the test page from a static folder.
Reach it with `ssh -f -N -L 9920:127.0.0.1:9920 root@<vps>`; open `http://localhost:9920/...` in a browser pane.
Afterward: kill by PID (not `pkill -f`, which killed its own shell once), delete the folder, confirm nothing listens on 9920.

## The local page
A single HTML file that inlines vendored React + ReactDOM, the plugin CSS/JS, and a small fake `window.__HERMES_PLUGIN_SDK__` (`fetchJSON` straight to the real endpoints, `buildWsUrl` to `ws://localhost`). Flags: `?desktop` (force `maxTouchPoints=0`), `?insecure` (force `isSecureContext=false`), `?demo` (fixture states), `?live` (fake SSE).
Fixture-only variants exist for Mission Control (`harness_pf.html`) so layout work is fast.

## What was checked, and how
| Claim | Evidence |
|---|---|
| Chat works end to end | typed prompt -> real Gideon reply -> status went Thinking -> Coordinating -> Speaking; 10.6 s of audio |
| Speech recognition | synthetic microphone: play real speech into the recorder, transcript exactly matched; also TTS -> local whisper round trip on every new voice ("2,906 unread" survived the effects chain) |
| Speed | timers around Send -> first speech; benchmark script over 5 status questions x 3 models with the same prompt the page sends |
| Accuracy | needle strings per question ("2906", "08:00", ...) |
| Layout | resize to 375x812, `document.documentElement.scrollWidth === innerWidth`, screenshots of every page |
| Animation | two screenshots seconds apart differ (beam dots, ping ring, screen lines, camera) |
| Deploy | file hash equality local vs server before editing; after deploy: units active, journal errors 0, unauthenticated 302/401, marker string present in the bundle |
| Security change | after binding to loopback: unauthenticated API 401 on loopback and via https; old tailnet-IP port refused |
| Backups | archive entry counts, `sha256sum -c`, restore rehearsal |

## What could NOT be verified (say so out loud)
Real phone microphone on iOS/Android, audible voice quality, the live login-protected dashboards from the owner's device. Ask the owner to run the Test sound button, open both dashboards and report; add a diagnostic button rather than guessing.

## Habits that saved time
- Write patch scripts with the file-write tool, not shell heredocs (apostrophes, `\n` and curly quotes corrupt them); marker-based slicing instead of exact multi-line matches.
- Keep a `.pre-<change>` copy of every file the patch reads, and make patches idempotent (assert the anchor count is exactly 1).
- Temporary `launch.json` entries for local servers, restored to the original after each test.
- Verify a listener with `ss -ltnp`, not `pgrep | grep` (which matches itself).
- Time-box rabbit holes: for a harmless warning, prove it is harmless, then add the smallest reversible fix.
