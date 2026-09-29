# 05 - Dashboards as Hermes plugins (Command Center + Mission Control)

## Why two dashboards
The owner already had a ChatGPT-built pair (a general Command Center and a Product Factory Mission Control). The rebuild kept both, with the same names and purposes:
- **Command Center** (default profile, port 9119): the operator's console, now with Jarvis.
- **Mission Control** (profile `product-factory`, port 9220, `--isolated`): the team's board, network, office, library.
Rule from the owner: never create a third disconnected dashboard; extend the two.

## Plugin anatomy
```
<home>/plugins/<name>/dashboard/
   manifest.json          # {"name","label","description","icon","version","tab":{"path":"/command-center","position":"after:chat"},
                          #  "entry":"dist/index.js","css":"dist/style.css","api":"plugin_api.py"}
   plugin_api.py          # FastAPI `router`, mounted at /api/plugins/<name>/ when the dashboard process STARTS
   dist/index.js          # plain IIFE, no build step
   dist/style.css
   dist/three.module.min.js   # (Mission Control only) vendored three.js, loaded on demand
```
- Product Factory's plugin lives under `~/.hermes/profiles/product-factory/plugins/...` because its dashboard runs with `--profile product-factory --isolated`.
- **Restart the dashboard after any `plugin_api.py` change.** JS/CSS are served from disk (behind the dashboard login) - a browser refresh is enough, but clear the cache when in doubt.
- Static files and APIs sit behind the dashboard's basic-auth login (302 to `/login` unauthenticated, 401 for API calls) - use that as your post-deploy test.

## Front-end contract (no bundler)
```js
(function () {
  const SDK = window.__HERMES_PLUGIN_SDK__;      // { React, hooks:{useState,useEffect,useRef,useCallback,useMemo}, fetchJSON, buildWsUrl, ... }
  const h = SDK.React.createElement;
  const API = "/api/plugins/<name>";
  function App() { ... }
  window.__HERMES_PLUGINS__.register("<name>", App);
})();
```
- `fetchJSON(url, opts)` handles auth cookies; `await buildWsUrl("/api/ws")` returns a wss URL with a short-lived auth ticket.
- Use `React.createElement` (`h`) directly. Long files are fine; keep helpers at the top.
- Hash routing (`#/overview`, `#/office`, ...) so pages are linkable and the back button works.

## Command Center pages
Jarvis (default landing), Infrastructure (the original view: environment, multiplexed profiles with model dropdown, tokens, usage heat map, live feed, health, tasks, tools), Schedule (cron: run now, pause, resume, delete with confirmation), Threads (Telegram topics and Slack from each profile's `state.db`), Comms (read-only Gmail unread COUNT and calendar), Docs (runbook viewer with a safe markdown renderer).
Keys: hold Space to talk, `/` type, Esc stop, 1-6 pages. Mission Control has a gold "Jarvis" button; Command Center links back with "Mission Control".

## Mission Control pages
Overview (mission header, Specialist Network graph that fills its panel, role status donut, mission timeline, gates), Office (3D), Tasks (board + actions), Library (Obsidian drafts search), Activity, Artifacts. A project switcher lets the owner pick any Product Factory project, not just the current one.

## API patterns worth copying (see `code/*/plugin_api.py`)
- **Read-only data endpoints** that shell out to the official CLI or read files (`hermes kanban list --json`, journal, cron API) with short timeouts.
- **Stale-while-revalidate cache** `_swr(key, ttl, fn)` for slow sources (Gmail counter took 0.6 s cold; first `/jarvis/brief` 10 s -> 2.5 s cold, 2 ms warm).
- **Allowlist + audit log** for every write (model change, task create/unblock/reassign, pin project).
- **Secret scrubbing** (`_scrub_text`) before returning any text that could contain a token.
- **Health score** from weighted checks: services 40, channels 20, resources 20, backups 10, recent errors 10.
- **SSE** endpoint `/stream` with a generator that yields only when a fingerprint changes.

## Design system decisions (from owner feedback)
Dark navy base, cyan and violet accents, amber for "working", green only for "done/ok" (the owner disliked an all-green look). Every panel interactive: click a node/row -> drawer with details. Layout must fit phone width with no horizontal scroll (verified at 375 px on every page).
Overview polish (2026-09-21): graph SVG uses `viewBox` with `width:100%; height:auto; max-width:700px`, panel body `display:flex; align-items:center`, panel height stretches to match the neighbouring column.

## Deploy loop
1. Back up (`hermes_backup.py custom`).
2. `scp` files to the plugin folder.
3. `systemctl --user restart <dashboard unit>` only if the API changed.
4. Check: units active, journal has no errors, unauthenticated request -> 302/401, bundle contains a marker string (`grep -c animateAgent dist/index.js`).
5. Update the runbook.
