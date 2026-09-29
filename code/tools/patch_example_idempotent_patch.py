"""Adds body language, live screens, holograms, beams, motes, radar pings, entrance + hover animation to the 3D office (Mission Control),
and makes the Overview's Specialist Network fill its panel. Source: live/pf_index.js.pre-office-anim (created on first run)."""
import os
import shutil

NL = chr(10)
D = os.environ.get("WORKDIR", ".")   # folder holding live/, vendor/, refimg/
L = os.path.join(D, "live")
src = os.path.join(L, "pf_index.js")
bak = src + ".pre-office-anim"
if not os.path.exists(bak):
    shutil.copy(src, bak)
s = open(bak, encoding="utf-8").read()


def rep(old, new):
    global s
    assert s.count(old) == 1, ("anchor count %d: " % s.count(old)) + old[:80]
    s = s.replace(old, new, 1)


# ---- makeAgent: canvas screen, arms, keyboard, holograms, burst ring ----
rep("      const screenMat = mat({ color: 0x050b14, emissive: col(color), emissiveIntensity: 0.05, roughness: 0.4 });",
    '      const scr = document.createElement("canvas"); scr.width = 160; scr.height = 96;' + NL +
    "      const scrTex = new THREE.CanvasTexture(scr); if (THREE.SRGBColorSpace) scrTex.colorSpace = THREE.SRGBColorSpace; disposables.push(scrTex);" + NL +
    "      const screenMat = mat({ color: 0x050b14, emissive: 0xffffff, emissiveMap: scrTex, emissiveIntensity: 0.6, roughness: 0.4 });")
rep("      chair.position.set(0, 0.55, 0); g.add(chair);",
    "      chair.position.set(0, 0.55, 0); g.add(chair);" + NL +
    "      const makeArm = function (side) {" + NL +
    "        const piv = new THREE.Group(); piv.position.set(side * 0.43, 1.55, 0);" + NL +
    "        const m = new THREE.Mesh(geo(new THREE.CapsuleGeometry(0.09, 0.66, 3, 8)), bodyMat); m.position.y = -0.4; piv.add(m); g.add(piv); return piv;" + NL +
    "      };" + NL +
    "      const armL = makeArm(-1), armR = makeArm(1);" + NL +
    "      const kb = new THREE.Mesh(geo(new THREE.BoxGeometry(big ? 0.9 : 0.7, 0.03, 0.28)), mat({ color: 0x0d1b2c, emissive: col(color), emissiveIntensity: 0.18, roughness: 0.5 }));" + NL +
    "      kb.position.set(0, 0.985, 1.02); g.add(kb);" + NL +
    "      const holo = new THREE.Group(); holo.position.set(0, 2.75, 0); g.add(holo);" + NL +
    "      const hBasic = function (hex) { return basic({ color: col(hex), transparent: true, opacity: 0.95 }); };" + NL +
    "      const hs = new THREE.Group(); [0, 1, 2].forEach(function (i) { const o = new THREE.Mesh(geo(new THREE.SphereGeometry(0.08, 10, 8)), hBasic(STATE_META.working.color)); const an = i / 3 * Math.PI * 2; o.position.set(Math.cos(an) * 0.5, 0, Math.sin(an) * 0.5); hs.add(o); }); holo.add(hs);" + NL +
    "      const ha = new THREE.Group(); const bar = new THREE.Mesh(geo(new THREE.BoxGeometry(0.11, 0.34, 0.11)), hBasic(STATE_META.blocked.color)); bar.position.y = 0.12; ha.add(bar);" + NL +
    "      const dotA = new THREE.Mesh(geo(new THREE.SphereGeometry(0.075, 10, 8)), hBasic(STATE_META.blocked.color)); dotA.position.y = -0.16; ha.add(dotA); holo.add(ha);" + NL +
    "      const hq = new THREE.Group(); [-1, 0, 1].forEach(function (i) { const o = new THREE.Mesh(geo(new THREE.SphereGeometry(0.07, 10, 8)), hBasic(STATE_META.queued.color)); o.position.x = i * 0.24; hq.add(o); }); holo.add(hq);" + NL +
    "      const hd = new THREE.Mesh(geo(new THREE.RingGeometry(0.28, 0.33, 36)), basic({ color: col(STATE_META.recent.color), transparent: true, opacity: 0.8, side: THREE.DoubleSide })); hd.rotation.x = -Math.PI / 2; holo.add(hd);" + NL +
    "      hs.visible = ha.visible = hq.visible = hd.visible = false;" + NL +
    "      const burst = new THREE.Mesh(geo(new THREE.RingGeometry(0.9, 1.0, 44)), basic({ color: 0xfbbf24, transparent: true, opacity: 0, side: THREE.DoubleSide }));" + NL +
    "      burst.rotation.x = -Math.PI / 2; burst.position.set(0, 0.06, 0.6); g.add(burst);")
rep("body: body, bodyMat: bodyMat, head: head,",
    "body: body, bodyMat: bodyMat, head: head, armL: armL, armR: armR, scr: scr, sctx: scr.getContext(\"2d\"), scrTex: scrTex, holo: holo, hs: hs, ha: ha, hq: hq, hd: hd, burst: burst," + NL +
    "                  idx: agentCount++, seed: agentCount * 7, hoverK: 0, hover: false, lastDraw: -9, needsDraw: true, burstAt: 0,")
rep("    const agents = {};   // id -> { group, screen, ring, body, head, phase, state, label, kind }",
    "    let agentCount = 0;" + NL + "    const agents = {};   // id -> { group, screen, ring, body, head, phase, state, label, kind }")

# ---- zones: radar ping ring ----
rep("rim.rotation.x = -Math.PI / 2; rim.position.set(z.cx, 0.32, z.cz); scene.add(rim); z.rim = rim;",
    "rim.rotation.x = -Math.PI / 2; rim.position.set(z.cx, 0.32, z.cz); scene.add(rim); z.rim = rim;" + NL +
    "      const ping = new THREE.Mesh(geo(new THREE.RingGeometry(z.r - 0.5, z.r, 72)), basic({ color: z.color, transparent: true, opacity: 0, side: THREE.DoubleSide }));" + NL +
    "      ping.rotation.x = -Math.PI / 2; ping.position.set(z.cx, 0.34, z.cz); scene.add(ping); z.ping = ping;")
rep("ZONES.forEach(function (z) { z.plat.position.set(z.cx, 0.15, z.cz); z.rim.position.set(z.cx, 0.32, z.cz); });",
    "ZONES.forEach(function (z) { z.plat.position.set(z.cx, 0.15, z.cz); z.rim.position.set(z.cx, 0.32, z.cz); z.ping.position.set(z.cx, 0.34, z.cz); });")

# ---- state look: the screen now draws its own colours ----
a = s.index('      a.screenMat.emissive.copy(state === "working"')
b = s.index(NL, a)
s = s[:a] + "      a.needsDraw = true;" + s[b:]

# ---- camera state + hover ----
rep("    let userMoved = false;" + NL + "    function placeCamera() {", "    let userMoved = false;" + NL + "    let drift = true;" + NL + "    let hoverPt = null, hoveredId = null;" + NL + "    function placeCamera() {")
rep("      spin: function (d) { userMoved = true; view.theta += d; },", "      spin: function (d) { userMoved = true; view.theta += d; }," + NL + "      drift: function () { drift = !drift; if (!drift) userMoved = true; else { userMoved = false; } return drift; },")
rep("    const pts = new Map();", "    const pts = new Map();" + NL +
    '    el.addEventListener("pointermove", function (e) { if (e.pointerType === "mouse" && pts.size === 0) hoverPt = { x: e.clientX, y: e.clientY }; });' + NL +
    '    el.addEventListener("pointerleave", function () { hoverPt = null; });')

# ---- the animation helpers go right before the loop section ----
rep("    // ---- sizing + loop ----", open(os.path.join(D, "office_anim_extras.js"), encoding="utf-8").read() + "    // ---- sizing + loop ----")

# ---- the frame: replace the old per-agent block ----
a = s.index("      Object.keys(agents).forEach(function (id) {" + NL + "        const a = agents[id], s = a.state, p = a.phase;")
end_marker = "        project(a.headWorld, a.label);" + NL + "      });" + NL
b = s.index(end_marker, a) + len(end_marker)
s = s[:a] + "      ambient(t, dt);" + NL + "      Object.keys(agents).forEach(function (id) { const a = agents[id]; animateAgent(a, t, dt); project(a.headWorld, a.label); });" + NL + s[b:]
rep("if (u >= 1) { pk.b.flashUntil = t + 0.9;", "if (u >= 1) { pk.b.flashUntil = t + 0.9; pk.b.burstAt = t;")
rep('ctl("⟲", "Reset view", () => apiRef.current.reset()),', 'ctl("⟲", "Reset view", () => apiRef.current.reset()), ctl("◌", "Gentle camera drift on or off", () => apiRef.current.drift()),')

# ---- overview: the Specialist Network fills its panel, centred ----
a = s.index('    return h("div", { className: "pfmc-graph-tight" }, [')
b = s.index("  function AgentDrawer(props) {")
seg = s[a:b]
seg = seg.replace('h("svg", { key: "svg", viewBox: "50 10 420 420", width: "100%", height: "360", role: "img", style: { maxWidth: 420, display: "block", margin: "0 auto" } }, [',
                  'h("svg", { key: "svg", viewBox: "38 6 444 434", role: "img", className: "pfmc-graph-svg" }, [', 1)
seg = seg.replace('h("p", { key: "hint", style: { textAlign: "center", fontSize: 10.5, color: "var(--pfmc-muted)", margin: "-6px 0 0" } }, "Click any specialist for details · dot color = status, ring color = role"),',
                  'h("div", { key: "hint", className: "pfmc-graph-legend" }, [' + NL +
                  '        h("span", { key: "h" }, "Click a specialist for details · ring colour = role"),' + NL +
                  '        h("span", { key: "l", className: "pfmc-graph-key" }, [["COMPLETE", "Complete"], ["ACTIVE", "Active"], ["PENDING", "Pending"], ["SKIPPED", "Skipped"]].map(function (x) {' + NL +
                  '          return h("span", { key: x[0] }, [h("i", { key: "i", style: { background: STATUS_COLOR[x[0]] } }), x[1]]);' + NL +
                  "        }))," + NL + "      ]),", 1)
assert "pfmc-graph-svg" in seg and "pfmc-graph-legend" in seg
s = s[:a] + seg + s[b:]
rep('h(Panel, { title: "Specialist Network", key: "graph" }, h(AgentGraph, {', 'h(Panel, { title: "Specialist Network", key: "graph", className: "pfmc-panel-fill" }, h(AgentGraph, {')
rep('return h("div", { className: "pfmc-graph-tight" }, [', 'return h("div", { className: "pfmc-graph-tight pfmc-graph-fill" }, [')
open(src, "w", encoding="utf-8").write(s)

# ---- css ----
cp = os.path.join(L, "pf_style.css")
bakc = cp + ".pre-office-anim"
if not os.path.exists(bakc):
    shutil.copy(cp, bakc)
c = open(bakc, encoding="utf-8").read()
c += NL + """
/* ---- overview: the specialist network fills and centres in its panel ---- */
.pfmc-grid-graph { align-items: stretch; }
.pfmc-panel-fill { display: flex; flex-direction: column; }
.pfmc-panel-fill > .pfmc-panel-body { flex: 1; display: flex; align-items: center; justify-content: center; padding: 12px 16px 16px; }
.pfmc-graph-fill { width: 100%; margin: 0 !important; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; }
.pfmc-graph-svg { display: block; width: 100%; height: auto; max-width: 700px; max-height: 72vh; margin: 0 auto; }
.pfmc-graph-legend { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px 18px; font-size: 11px; color: var(--pfmc-muted); text-align: center; }
.pfmc-graph-key { display: inline-flex; flex-wrap: wrap; gap: 6px 14px; justify-content: center; }
.pfmc-graph-key span { display: inline-flex; align-items: center; gap: 6px; }
.pfmc-graph-key i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
"""
open(cp, "w", encoding="utf-8").write(c)
print("office animation + overview patched")
