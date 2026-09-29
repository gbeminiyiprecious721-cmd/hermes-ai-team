# 07 - The 3D Office (Mission Control, page #/office)

## Rule: real state only
Nothing moves for show. Every agent's look comes from data:
- **Team agents** (Gideon + 5) from the Kanban board: `working` (a running task), `blocked`, `queued`, `recent` (finished in the last 15 min), `idle`.
- **The 11 Product Factory specialists** from the project state: ACTIVE -> working, COMPLETE -> recent, PENDING -> queued, SKIPPED -> not needed.
- Gideon shows "coordinating N" whenever anyone else has running/queued work.
- A **packet** (glowing orb) flies from the delegator to the assignee when a task appears, back green when done, back red when blocked - only for real changes after the first load (never replay history).

## Stack and constraints
three.js 0.160 vendored as `dist/three.module.min.js`, imported on demand with `import(base + "three.module.min.js")` (`window.__PFMC_ASSET_BASE__` lets tests point at a local copy).
`WebGLRenderer({ antialias, alpha, powerPreference: "low-power" })`, pixel ratio capped at 2, custom orbit camera (drag rotate, wheel/pinch zoom, tilt buttons), labels are DOM elements projected each frame, tap picks an agent (raycast) and opens a card.
Two platforms: **Command Floor** (Gideon centre, five agents around) and **Product Factory** (Director centre, 11 specialists on a ring). Wide screens: side by side; narrow screens: stacked vertically with a wider FOV.

## Animation set (2026-09-21)
Per agent (`animateAgent`, all eased with a per-frame approach so state changes never snap):
- **working**: arms type alternately, head tilts to the screen and sways, body micro-bob, ring spins.
- **blocked**: right arm raised and waving, head shaking, red "!" hologram, flashing red screen.
- **queued**: head looks around, a finger taps, three blue dots bounce above the head.
- **recent**: relaxed nod and a green expanding ring; a **cheer** (both arms up, jump) when a packet lands.
- **idle**: slow head scan, arms sway. **skipped**: still and dim.
- **Screens** are `CanvasTexture`s drawn by state (scrolling code lines for working, QUEUED dots, BLOCKED triangle, DONE tick, scanline for idle); redrawn every ~90 ms only while animated.
- **Beams**: amber curved lines with three travelling dots from the coordinator to every working agent.
- **Ambience**: 150 drifting light motes (additive points), a radar ping ring on each platform, breathing platform rims, entrance animation (agents rise with ease-out-back, staggered), hover highlight (mouse only), gentle camera drift (toggle button), arrival burst rings.
- Source: `code/mission-control/office_animation_source.js` (the helper block) and `index.js` (`buildOffice`).

## Performance notes
17 agents, 16 pooled beams, 150 points, a handful of 160x96 canvas textures updated at ~11 fps only for working/blocked/queued. Redraw is skipped when the tab is hidden. All geometries/materials/textures are pushed to a `disposables` list and released in `cleanup`.

## Testing without the live system
`harness_pf.html` with fixtures and `?demo` (forces a mix of running/blocked/ready states) plus `?live` (fake SSE emitter); `window.__PFMC_DEBUG.packets` exposes packets. Compare two screenshots seconds apart to prove motion (beam dots moved, ring expanded, screen lines scrolled, camera drifted).
The two `404`s for `/stream` in the static harness are expected (no SSE server there).

## Visual language
State colours: working amber, blocked rose, queued sky, just-finished green, idle slate, not-needed dark slate. Team colours per agent (Gideon cyan, Scout orange, Scribe violet, Reach magenta, Production red, Product Factory teal).
