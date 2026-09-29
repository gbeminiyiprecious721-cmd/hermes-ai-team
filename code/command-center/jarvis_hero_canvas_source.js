  // ---------- the hero: the JARVIS portrait with live rings and a waveform that follow the state ----------
  function JarvisOrb(props) {
    const ref = useRef(null);
    const live = useRef({ phase: props.phase });
    live.current.phase = props.phase;
    useEffect(function () {
      const c = ref.current;
      if (!c) return undefined;
      const ctx = c.getContext("2d");
      const wrap = c.parentElement;
      let raf = 0;
      const t0 = performance.now();
      const size = function () { const r = c.getBoundingClientRect(); const d = Math.min(2, window.devicePixelRatio || 1); c.width = Math.max(10, r.width * d); c.height = Math.max(10, r.height * d); };
      size();
      const ro = new ResizeObserver(size); ro.observe(c);
      const PAL = { idle: ["#38bdf8", "#fbbf24"], listening: ["#7dd3fc", "#38bdf8"], transcribing: ["#8b7cf6", "#38bdf8"], thinking: ["#8b7cf6", "#c4b5fd"], working: ["#fbbf24", "#f59e0b"],
        reporting: ["#fbbf24", "#38bdf8"], speaking: ["#e0f2fe", "#fbbf24"], error: ["#fb7185", "#f43f5e"] };
      let smooth = 0;
      const draw = function (now) {
        raf = requestAnimationFrame(draw);
        if (document.hidden) return;
        const w = c.width, h = c.height, s = w / 520, t = (now - t0) / 1000;
        const ph = live.current.phase, pal = PAL[ph] || PAL.idle, raw = Math.min(1, props.levelRef.current || 0);
        smooth += (raw - smooth) * 0.35;
        const lvl = smooth;
        const busy = ph === "thinking" || ph === "working" || ph === "transcribing" || ph === "reporting";
        wrap.style.setProperty("--lvl", lvl.toFixed(3));
        ctx.clearRect(0, 0, w, h);
        const cx = 260 * s, cy = 210 * s, R = 200 * s;
        ctx.save();
        ctx.beginPath(); ctx.rect(0, 0, w, 322 * s); ctx.clip();          // rings only above the shoulders
        ctx.globalCompositeOperation = "lighter";
        // soft halo that breathes with the voice
        const g = ctx.createRadialGradient(cx, cy, R * 0.7, cx, cy, R * 1.25);
        g.addColorStop(0, "transparent"); g.addColorStop(0.72, pal[0] + Math.round(18 + lvl * 60).toString(16).padStart(2, "0")); g.addColorStop(1, "transparent");
        ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
        // waveform bars around the top arc
        const N = 96;
        for (let i = 0; i < N; i++) {
          const a = (i / N) * Math.PI * 2 - Math.PI / 2;
          const wave = busy ? 0.3 + 0.3 * Math.sin(i * 0.45 - t * 4.2) : (0.2 + 0.8 * Math.abs(Math.sin(i * 0.7 + t * 2.3)) * (0.18 + lvl * 1.1));
          const len = R * (0.02 + wave * (busy ? 0.08 : 0.16 * (0.2 + lvl)));
          const r1 = R * 1.04, r2 = r1 + len;
          ctx.strokeStyle = i % 6 === 0 ? pal[1] : pal[0];
          ctx.globalAlpha = 0.8; ctx.lineWidth = Math.max(1.4, 2.2 * s);
          ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1); ctx.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2); ctx.stroke();
        }
        ctx.globalAlpha = 1;
        const ring = function (rad, dash, speed, color, lw) {
          ctx.save(); ctx.translate(cx, cy); ctx.rotate(t * speed); ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.setLineDash(dash);
          ctx.beginPath(); ctx.arc(0, 0, rad, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
        };
        ring(R * 1.2, [R * 0.30, R * 0.14], busy ? 0.9 : 0.16, pal[1] + "cc", Math.max(1.5, 2.4 * s));
        ring(R * 1.3, [R * 0.02, R * 0.07], busy ? -0.7 : -0.12, pal[0] + "99", Math.max(1, 1.6 * s));
        if (busy) {   // a sweeping scanner arc while it works
          ctx.strokeStyle = pal[1]; ctx.lineWidth = Math.max(2, 3 * s); ctx.globalAlpha = 0.85;
          const a0 = t * 2.2 - Math.PI / 2;
          ctx.beginPath(); ctx.arc(cx, cy, R * 1.12, a0, a0 + 0.9); ctx.stroke(); ctx.globalAlpha = 1;
        }
        ctx.restore();
        // the horizontal waveform either side of the mic, like the reference
        const by = 347 * s;
        ctx.save(); ctx.globalCompositeOperation = "lighter";
        for (let side = -1; side <= 1; side += 2) {
          for (let i = 0; i < 26; i++) {
            const x = cx + side * (44 * s + i * 5.6 * s);
            const fall = 1 - i / 30;
            const amp = (busy ? 0.25 + 0.2 * Math.sin(i * 0.6 - t * 5) : 0.08 + Math.abs(Math.sin(i * 0.9 + t * 3.1)) * (0.15 + lvl * 1.4)) * fall;
            const hh = Math.max(2 * s, amp * 42 * s);
            ctx.fillStyle = i % 5 === 0 ? pal[1] : pal[0]; ctx.globalAlpha = 0.85 * fall + 0.1;
            ctx.fillRect(x - 1.3 * s, by - hh, 2.6 * s, hh * 2);
          }
        }
        ctx.restore();
      };
      raf = requestAnimationFrame(draw);
      return function () { cancelAnimationFrame(raf); ro.disconnect(); };
    }, []);
    return h("canvas", { ref: ref, className: "hcc-orb-canvas", "aria-label": "Jarvis status: " + props.phase });
  }

