# code/ - the real files

No secrets. The Telegram group id is masked (`-100XXXXXXXXXX`) and the tailnet name is a placeholder (`<your-machine>.<your-tailnet>.ts.net`).
The Command Center bundle has its two embedded images replaced by `<IMAGE_OMITTED_SEE_assets>` (see `../assets/`).
Three.js (`three.module.min.js`, 0.160) is not included: download it from the three.js releases and place it in Mission Control's `dist/`.

| Path | What |
|---|---|
| `command-center/plugin_api.py` | Command Center API: usage, heatmap, models (+ model change with probe), stream (SSE), Jarvis endpoints (env, tools, health, mission, voices, speak, settings, threads, comms, docs, tasks, brief), speed models, Kokoro/Edge speak |
| `command-center/index.js`, `style.css`, `manifest.json` | the dashboard UI (Jarvis, Infrastructure, Schedule, Threads, Comms, Docs) |
| `command-center/jarvis_hook_source.js` | `useJarvis()`: WebSocket JSON-RPC, WAV recorder, streaming TTS queue, unlock/playback, sound test |
| `command-center/jarvis_hero_canvas_source.js` | the canvas rings + waveform over the portrait |
| `command-center/voice_settings_source.js` | engine / character / reply-speed panel |
| `mission-control/plugin_api.py` | Mission Control API: projects, roles, kanban (+ create/unblock/reassign), library, SSE stream, artifacts, approvals |
| `mission-control/index.js`, `style.css`, `manifest.json` | Overview, Office (3D), Tasks, Library, Activity, Artifacts |
| `mission-control/office_animation_source.js` | the animation helper block (screens, beams, motes, body language) |
| `jarvis-voice/server.py` | Kokoro voice service (blends, ffmpeg chain, cache) |
| `scripts/` | `factory_floor.py`, `library_export.py`, `hermes_backup.py`, `wait_for_tailscale_ip.sh`, `quiet_nous_sitecustomize.py`, `Pull-HermesBackup.ps1` (Windows: off-server backup + vault draft pull; edit the paths and key at the top), `SECRETS-INVENTORY.md` (names only) |
| `systemd/` | all unit files + the gateway drop-in |
| `souls/` | SOUL.md for Gideon and the five specialists |
| `tools/` | test harness pieces: `serve_jarvis.py` (throwaway real-endpoint server), `build_harness_real.py`, `speed_exp2.py` (latency/accuracy benchmark), `test_jarvis_api.py`, `patch_example_idempotent_patch.py` (anchor-checked patch pattern). Set `WORKDIR` to the folder that holds `live/`, `vendor/`, `refimg/`. |

Deploy locations on the server: plugins under `/root/.hermes/plugins/hermes-command-center/dashboard/` and `/root/.hermes/profiles/product-factory/plugins/product-factory-mission-control/dashboard/`, scripts in `/root/.hermes/scripts/`, units in `~/.config/systemd/user/`, voice service in `/root/jarvis-voice/`.
