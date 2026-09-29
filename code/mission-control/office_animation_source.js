    // ---- animation: live screens, beams, particles, per-state body language ----
    const easeOutBack = function (x) { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
    const approach = function (obj, key, target, k) { obj[key] += (target - obj[key]) * k; };

    function drawScreen(a, t) {
      const c = a.scr, x = a.sctx, w = c.width, h = c.height, s = a.state, hex = "#" + new THREE.Color(a.color).getHexString();
      x.globalAlpha = 1;
      x.fillStyle = s === "skipped" ? "#03070d" : "#060d18"; x.fillRect(0, 0, w, h);
      x.textAlign = "center"; x.textBaseline = "middle";
      if (s === "working") {
        x.fillStyle = "rgba(255,255,255,.10)"; x.fillRect(0, 0, w, 11);
        x.fillStyle = "#fbbf24"; x.fillRect(6, 3, 6, 5); x.fillStyle = hex; x.fillRect(16, 3, 6, 5);
        const step = 13, off = (t * 16) % step, base = Math.floor(t * 16 / step);
        for (let i = -1; i < 7; i++) {
          const seed = ((base + i + a.seed) * 9301 + 49297) % 233280, r = seed / 233280;
          const y = 18 + i * step - off, indent = Math.floor(r * 3) * 12, len = 26 + r * (w - 70);
          x.fillStyle = i % 3 === 0 ? "#fbbf24" : i % 3 === 1 ? hex : "#8fb4d4"; x.globalAlpha = 0.9;
          x.fillRect(10 + indent, y, len, 6);
        }
        x.globalAlpha = 1;
        if (Math.floor(t * 2.5) % 2 === 0) { x.fillStyle = "#ffffff"; x.fillRect(w - 20, h - 16, 7, 11); }
      } else if (s === "queued") {
        x.fillStyle = "#38bdf8"; x.font = "bold 15px sans-serif"; x.fillText("QUEUED", w / 2, h / 2 - 16);
        for (let i = 0; i < 3; i++) { x.globalAlpha = 0.35 + 0.65 * Math.max(0, Math.sin(t * 4 - i * 0.9)); x.beginPath(); x.arc(w / 2 - 18 + i * 18, h / 2 + 14, 5, 0, 6.283); x.fill(); }
        x.globalAlpha = 1;
      } else if (s === "blocked") {
        const on = Math.floor(t * 3) % 2 === 0;
        x.fillStyle = on ? "#2a0a12" : "#060d18"; x.fillRect(0, 0, w, h);
        x.fillStyle = "#fb7185"; x.beginPath(); x.moveTo(w / 2, 14); x.lineTo(w / 2 + 34, h - 22); x.lineTo(w / 2 - 34, h - 22); x.closePath(); x.fill();
        x.fillStyle = "#060d18"; x.font = "bold 38px sans-serif"; x.fillText("!", w / 2, h / 2 + 8);
        x.fillStyle = "#fb7185"; x.font = "bold 12px sans-serif"; x.fillText("BLOCKED", w / 2, h - 10);
      } else if (s === "recent") {
        x.strokeStyle = "#4ade80"; x.lineWidth = 9; x.lineCap = "round"; x.lineJoin = "round";
        x.beginPath(); x.moveTo(w / 2 - 30, h / 2 - 2); x.lineTo(w / 2 - 8, h / 2 + 20); x.lineTo(w / 2 + 34, h / 2 - 24); x.stroke();
        x.fillStyle = "#4ade80"; x.font = "bold 12px sans-serif"; x.fillText("DONE", w / 2, h - 10);
      } else if (s === "idle") {
        const y = ((t * 18) % (h + 20)) - 10;
        x.fillStyle = "rgba(56,189,248,.16)"; x.fillRect(0, y, w, 5);
        x.fillStyle = "#3b5670"; x.font = "bold 12px sans-serif"; x.fillText("STANDING BY", w / 2, h / 2);
      }
      a.scrTex.needsUpdate = true;
      a.lastDraw = t;
    }

    // beams from the coordinator to whoever is working, with data dots travelling along them
    const beams = [];
    const BEAM_N = 18;
    ZONES.forEach(function (z) {
      const centre = Object.keys(agents).map(function (k) { return agents[k]; }).filter(function (q) { return q.zone === z && q.ox === 0 && q.oz === 0; })[0];
      Object.keys(agents).forEach(function (id) {
        const q = agents[id];
        if (q.zone !== z || q === centre) return;
        const pos = new Float32Array((BEAM_N + 1) * 3);
        const bg = new THREE.BufferGeometry(); bg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
        const bm = new THREE.LineBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.55 });
        const line = new THREE.Line(bg, bm); line.frustumCulled = false; line.visible = false; scene.add(line);
        disposables.push(bg, bm);
        const dm = new THREE.MeshBasicMaterial({ color: 0xfff1b8, transparent: true, opacity: 0.95 }); disposables.push(dm);
        const dots = [0, 1, 2].map(function () { const d = new THREE.Mesh(geo(new THREE.SphereGeometry(0.11, 8, 6)), dm); d.visible = false; scene.add(d); return d; });
        beams.push({ from: centre, to: q, line: line, pos: pos, dots: dots, seed: Math.random() });
      });
    });
    const bp = new THREE.Vector3(), bq = new THREE.Vector3();
    function beamPoint(A, B, u, out) {
      bp.copy(A.headWorld); bp.y -= 0.9; bq.copy(B.headWorld); bq.y -= 0.9;
      out.lerpVectors(bp, bq, u); out.y += Math.sin(Math.PI * u) * 2.4;
      return out;
    }
    const tmpV = new THREE.Vector3();
    function updateBeams(t) {
      beams.forEach(function (b) {
        const on = b.to.state === "working" && b.from && b.from.state !== "skipped";
        b.line.visible = on;
        b.dots.forEach(function (d) { d.visible = on; });
        if (!on) return;
        for (let i = 0; i <= BEAM_N; i++) { beamPoint(b.from, b.to, i / BEAM_N, tmpV); b.pos[i * 3] = tmpV.x; b.pos[i * 3 + 1] = tmpV.y; b.pos[i * 3 + 2] = tmpV.z; }
        b.line.geometry.attributes.position.needsUpdate = true;
        b.line.material.opacity = 0.4 + 0.2 * Math.sin(t * 3 + b.seed * 6);
        b.dots.forEach(function (d, i) {
          const u = ((t * 0.55 + i / 3 + b.seed) % 1);
          beamPoint(b.from, b.to, u, d.position);
          d.scale.setScalar(0.7 + 0.5 * Math.sin(Math.PI * u));
        });
      });
    }

    // drifting motes of light
    const MOTES = 150;
    const motePos = new Float32Array(MOTES * 3), moteSpeed = new Float32Array(MOTES);
    for (let i = 0; i < MOTES; i++) { motePos[i * 3] = (Math.random() - 0.5) * 60; motePos[i * 3 + 1] = Math.random() * 16; motePos[i * 3 + 2] = (Math.random() - 0.5) * 44; moteSpeed[i] = 0.25 + Math.random() * 0.5; }
    const moteGeo = new THREE.BufferGeometry(); moteGeo.setAttribute("position", new THREE.BufferAttribute(motePos, 3));
    const moteMat = new THREE.PointsMaterial({ color: 0x7dd3fc, size: 0.16, transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending });
    disposables.push(moteGeo, moteMat);
    const motes = new THREE.Points(moteGeo, moteMat); motes.frustumCulled = false; scene.add(motes);

    let bornBase = null, sweep = 0;
    function animateAgent(a, t, dt) {
      const s = a.state, p = a.phase, k = Math.min(1, dt * 7);
      if (bornBase === null) bornBase = t;
      const born = Math.min(1, Math.max(0, (t - (bornBase + a.idx * 0.07)) / 0.9));
      approach(a, "hoverK", a.hover ? 1 : 0, Math.min(1, dt * 10));
      a.group.scale.setScalar(Math.max(0.001, easeOutBack(born)) * (1 + a.hoverK * 0.07));
      a.group.visible = born > 0;
      const pulse = a.flashUntil && a.flashUntil > t;
      let by = 1.15, hy = 0, hx = 0, lx = 0.02, rx = 0.02, lz = -0.12, rz = 0.12;
      if (s === "working") {
        by = 1.15 + Math.sin(t * 7 + p) * 0.03; hy = Math.sin(t * 2 + p) * 0.22; hx = 0.18 + Math.sin(t * 3 + p) * 0.05;
        lx = -1.05 + Math.sin(t * 15 + p) * 0.15; rx = -1.05 + Math.sin(t * 15 + p + 2.4) * 0.15; lz = 0.12; rz = -0.12;
      } else if (s === "blocked") {
        by = 1.15; hy = Math.sin(t * 9) * 0.35; rx = -2.8 + Math.sin(t * 7) * 0.25; rz = -0.3 + Math.sin(t * 7) * 0.2; lx = -0.35;
      } else if (s === "queued") {
        hy = Math.sin(t * 1.4 + p) * 0.55; by = 1.15 + Math.sin(t * 2 + p) * 0.012;
        rx = -0.9 + Math.abs(Math.sin(t * 6 + p)) * 0.28; rz = -0.1; lx = -0.15;
      } else if (s === "recent") {
        hy = Math.sin(t * 0.9 + p) * 0.2; hx = Math.sin(t * 1.6 + p) * 0.06;
        rx = -0.25 + Math.sin(t * 1.5 + p) * 0.05; lx = Math.sin(t * 1.5 + p + 1) * 0.05;
      } else if (s === "skipped") {
        hy = 0; by = 1.14;
      } else {
        hy = Math.sin(t * 0.45 + p) * 0.5; hx = Math.sin(t * 0.3 + p) * 0.06; by = 1.15 + Math.sin(t * 1.4 + p) * 0.012;
        lx = Math.sin(t * 1.1 + p) * 0.05; rx = Math.sin(t * 1.1 + p + 1.5) * 0.05;
      }
      if (pulse && s !== "blocked") {   // something just landed on this desk: cheer
        const j = Math.abs(Math.sin((a.flashUntil - t) * 6));
        lx = -2.7 + Math.sin(t * 12) * 0.18; rx = -2.7 + Math.sin(t * 12 + 1) * 0.18; lz = -0.35; rz = 0.35; by = 1.15 + j * 0.13;
      }
      approach(a.body.position, "y", by, k); approach(a.head.rotation, "y", hy, k); approach(a.head.rotation, "x", hx, k);
      approach(a.armL.rotation, "x", lx, k); approach(a.armR.rotation, "x", rx, k); approach(a.armL.rotation, "z", lz, k); approach(a.armR.rotation, "z", rz, k);
      a.head.position.y = 1.95 + (a.body.position.y - 1.15);
      a.ring.rotation.z += dt * (s === "working" ? 1.6 : s === "blocked" ? 0.4 : 0.15);
      a.ring.scale.setScalar(pulse ? 1 + 0.3 * Math.abs(Math.sin((a.flashUntil - t) * 7)) : 1);
      // screen
      const period = s === "working" || s === "blocked" || s === "queued" ? 0.09 : s === "idle" ? 0.2 : 99;
      if (a.needsDraw || t - a.lastDraw > period) { drawScreen(a, t); a.needsDraw = false; }
      a.screenMat.emissiveIntensity = s === "skipped" ? 0.12 : s === "idle" ? 0.6 : 1;
      // holograms above the head
      a.holo.position.y = 2.75 + Math.sin(t * 2 + p) * 0.06;
      a.hs.visible = s === "working"; a.ha.visible = s === "blocked"; a.hq.visible = s === "queued"; a.hd.visible = s === "recent";
      if (a.hs.visible) { a.hs.rotation.y = t * 2.4; a.hs.rotation.z = Math.sin(t * 1.3) * 0.25; }
      if (a.ha.visible) { a.ha.rotation.y = t * 2; a.ha.scale.setScalar(1 + 0.25 * Math.abs(Math.sin(t * 6))); }
      if (a.hq.visible) a.hq.children.forEach(function (d, i) { d.position.y = Math.max(0, Math.sin(t * 5 - i * 0.8)) * 0.22; });
      if (a.hd.visible) { const u = (t * 0.5 + p) % 1; a.hd.scale.setScalar(0.5 + u * 1.3); a.hd.material.opacity = (1 - u) * 0.85; }
      // arrival burst on the floor
      if (a.burstAt && t - a.burstAt < 1.0) { const u = (t - a.burstAt); a.burst.scale.setScalar(0.6 + u * 2.4); a.burst.material.opacity = (1 - u) * 0.9; }
      else if (a.burst.material.opacity) a.burst.material.opacity = 0;
    }

    function ambient(t, dt) {
      for (let i = 0; i < MOTES; i++) {
        let y = motePos[i * 3 + 1] + moteSpeed[i] * dt;
        if (y > 16) y = 0;
        motePos[i * 3 + 1] = y;
        motePos[i * 3] += Math.sin(t * 0.3 + i) * dt * 0.15;
      }
      moteGeo.attributes.position.needsUpdate = true;
      ZONES.forEach(function (z, zi) {
        z.rim.material.opacity = 0.72 + 0.16 * Math.sin(t * 1.6 + zi);
        const u = ((t + zi * 1.7) % 4.5) / 4.5;
        z.ping.scale.setScalar(0.15 + u * 0.9); z.ping.material.opacity = (1 - u) * 0.5;
      });
      updateBeams(t);
      if (drift && !userMoved) {
        view.theta = home.theta + Math.sin(t * 0.17) * 0.17;
        view.phi = home.phi + Math.sin(t * 0.12 + 1) * 0.03;
      }
      if (hoverPt && (tick % 4) === 0) {
        const r = el.getBoundingClientRect();
        ndc.set(((hoverPt.x - r.left) / r.width) * 2 - 1, -((hoverPt.y - r.top) / r.height) * 2 + 1);
        ray.setFromCamera(ndc, camera);
        const hit = ray.intersectObjects(pickables, false)[0];
        hoveredId = hit ? hit.object.userData.agentId : null;
        el.style.cursor = hoveredId ? "pointer" : "";
      } else if (!hoverPt && hoveredId) { hoveredId = null; el.style.cursor = ""; }
      Object.keys(agents).forEach(function (id) { agents[id].hover = id === hoveredId; });
    }

