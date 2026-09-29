  const SECURE_URL = "https://<your-machine>.<your-tailnet>.ts.net/#/jarvis";

  // Records with the Web Audio API and writes a 16 kHz mono WAV. This works in every browser that can open the
  // microphone, including Safari versions without MediaRecorder.
  function encodeWav(chunks, srcRate, dstRate) {
    let len = 0;
    chunks.forEach(function (c) { len += c.length; });
    const all = new Float32Array(len);
    let o = 0;
    chunks.forEach(function (c) { all.set(c, o); o += c.length; });
    const ratio = srcRate / dstRate;
    const n = Math.floor(all.length / ratio);
    const pcm = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      const a = Math.floor(i * ratio), b = Math.min(all.length, Math.floor((i + 1) * ratio));
      let s = 0;
      for (let j = a; j < b; j++) s += all[j];
      const v = Math.max(-1, Math.min(1, s / Math.max(1, b - a)));
      pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
    const buf = new ArrayBuffer(44 + n * 2);
    const dv = new DataView(buf);
    const wr = function (off, str) { for (let i = 0; i < str.length; i++) dv.setUint8(off + i, str.charCodeAt(i)); };
    wr(0, "RIFF"); dv.setUint32(4, 36 + n * 2, true); wr(8, "WAVE"); wr(12, "fmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
    dv.setUint32(24, dstRate, true); dv.setUint32(28, dstRate * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); wr(36, "data"); dv.setUint32(40, n * 2, true);
    new Int16Array(buf, 44).set(pcm);
    return new Blob([buf], { type: "audio/wav" });
  }

  function useJarvis() {
    const [phase, setPhase] = useState("idle");
    const [stage, setStage] = useState(-1);
    const [tool, setTool] = useState("");
    const [messages, setMessages] = useState([]);
    const [partial, setPartial] = useState("");
    const [error, setError] = useState("");
    const [approval, setApproval] = useState(null);
    const [elapsed, setElapsed] = useState(0);
    const [ttsOn, setTtsOn] = useState(true);
    const [tapRec, setTapRec] = useState(false);
    const [diag, setDiag] = useState("");
    const levelRef = useRef(0);
    const R = useRef({ ws: null, pending: {}, nextId: 1, sid: null, sessP: null, settings: null, turnStart: 0, ctx: null, micAn: null, playAn: null, micStream: null, rec: null,
      audio: null, audioDone: null, filler: null, speakGen: 0, ttsOn: true, active: false, buf: "", spokenIdx: 0, spokenChars: 0, q: [], playing: false, mounted: true, meter: 0,
      downAt: 0, upAt: 0 });
    useEffect(function () { R.current.ttsOn = ttsOn; }, [ttsOn]);

    const say = function (role, text) { setMessages(function (m) { return m.concat([{ role: role, text: text, at: new Date().toISOString() }]).slice(-40); }); };

    // ---------- audio plumbing (the level meter drives the orb) ----------
    const getCtx = function () {
      const r = R.current;
      if (!r.ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        r.ctx = new AC();
        r.micAn = r.ctx.createAnalyser(); r.micAn.fftSize = 512;
        r.playAn = r.ctx.createAnalyser(); r.playAn.fftSize = 512; r.playAn.connect(r.ctx.destination);
      }
      if (r.ctx.state === "suspended") r.ctx.resume();
      return r;
    };
    useEffect(function () {
      const r = R.current;
      r.mounted = true;
      const buf = new Uint8Array(256);
      const tick = function () {
        r.meter = requestAnimationFrame(tick);
        if (r.audio && !r.routed) { levelRef.current = 0.3 + 0.22 * Math.abs(Math.sin(Date.now() / 140)); return; }
        const an = r.audio ? r.playAn : (r.micStream ? r.micAn : null);
        if (!an) { levelRef.current *= 0.85; return; }
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
        levelRef.current = Math.min(1, Math.sqrt(sum / buf.length) * 3.2);
      };
      tick();
      return function () {
        r.mounted = false;
        cancelAnimationFrame(r.meter); r.meter = 0;
        try { if (r.ws) r.ws.close(); } catch (e) { /* ignore */ }
        try { if (r.audio) r.audio.pause(); } catch (e) { /* ignore */ }
        if (r.micStream) r.micStream.getTracks().forEach(function (t) { t.stop(); });
        try { if (r.ctx) r.ctx.close(); } catch (e) { /* ignore */ }
      };
    }, []);
    useEffect(function () {
      if (!(phase === "thinking" || phase === "working" || phase === "reporting")) return undefined;
      const t = setInterval(function () { setElapsed(Math.round((Date.now() - R.current.turnStart) / 1000)); }, 500);
      return function () { clearInterval(t); };
    }, [phase]);

    // ---------- chat connection ----------
    const getSettings = function () {
      const r = R.current;
      if (r.settings) return Promise.resolve(r.settings);
      return fetchJSON(API + "/jarvis/settings").then(function (s) { r.settings = s; return s; }).catch(function () { return { speed: "original" }; });
    };
    const ensureWs = function () {
      const r = R.current;
      if (r.ws && r.ws.readyState === 1) return Promise.resolve(r.ws);
      return Promise.resolve(SDK.buildWsUrl ? SDK.buildWsUrl("/api/ws") : null).then(function (url) {
        if (!url) throw new Error("This dashboard version has no chat connection for plugins.");
        return new Promise(function (resolve, reject) {
          const ws = new WebSocket(url);
          let opened = false;
          ws.onopen = function () { opened = true; r.ws = ws; r.sid = null; r.sessP = null; resolve(ws); };
          ws.onmessage = function (ev) { let f = null; try { f = JSON.parse(ev.data); } catch (e) { return; } onFrame(f); };
          ws.onerror = function () { if (!opened) reject(new Error("Could not open the chat connection.")); };
          ws.onclose = function () {
            r.ws = null; r.sid = null; r.sessP = null;
            if (r.active && r.mounted) { r.active = false; setPhase("error"); setError("The chat connection dropped. Try again."); }
          };
        });
      });
    };
    const rpc = function (method, params) {
      return ensureWs().then(function (ws) {
        return new Promise(function (resolve, reject) {
          const id = R.current.nextId++;
          R.current.pending[id] = { resolve: resolve, reject: reject };
          ws.send(JSON.stringify({ jsonrpc: "2.0", id: id, method: method, params: params || {} }));
          setTimeout(function () { if (R.current.pending[id]) { delete R.current.pending[id]; reject(new Error("No answer from the chat connection.")); } }, 90000);
        });
      });
    };
    // One shared promise, so pre-building the session on page open and the first message never create two sessions.
    const ensureSession = function () {
      const r = R.current;
      if (r.sessP) return r.sessP;
      r.sessP = getSettings().then(function (s) {
        const params = { cols: 100, title: "Jarvis" };
        let mode = s && s.speed;
        if (mode === "premium" && s.premium_ok === false) mode = "balanced";   // ChatGPT login missing: quietly use the free model
        const m = s && s.speed_models && s.speed_models[mode];   // per-session model, never a config change
        if (m) Object.assign(params, m);
        return rpc("session.create", params);
      }).then(function (res) { r.sid = res.session_id; return r.sid; }).catch(function (e) { r.sessP = null; throw e; });
      return r.sessP;
    };
    const warm = function () {
      if (R.current.active) return;
      fetchJSON(API + "/jarvis/brief").catch(function () { /* just warms the server-side cache */ });
      ensureSession().catch(function () { /* the first message will report any problem */ });
    };
    const resetSession = function () {
      const r = R.current;
      r.settings = null;
      const old = r.sid;
      r.sid = null; r.sessP = null;
      if (old && r.ws && r.ws.readyState === 1) rpc("session.close", { session_id: old }).catch(function () { /* ignore */ });
      warm();
    };

    // ---------- speaking: each sentence is voiced as soon as it is written ----------
    const stopSpeaking = function () {
      const r = R.current;
      r.speakGen++; r.q = [];
      if (r.audio) { try { r.audio.pause(); } catch (e) { /* ignore */ } r.audio = null; }
      if (r.audioDone) { const d = r.audioDone; r.audioDone = null; d(); }
    };
    const fetchAudio = function (text) {
      return fetchJSON(API + "/jarvis/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text }) }).then(function (d) { return d.data_url; });
    };
    // Phones only allow sound that a tap has unlocked. One shared element is unlocked on the tap, then reused for every sentence.
    const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
    const unlockAudio = function () {
      const r = R.current;
      if (!r.el) {
        r.el = new Audio();
        r.el.setAttribute("playsinline", ""); r.el.preload = "auto";
        const touch = (navigator.maxTouchPoints || 0) > 0;
        if (!touch) {   // desktop: route through the analyser so the orb follows the voice
          try { const c = getCtx(); c.ctx.createMediaElementSource(r.el).connect(c.playAn); r.routed = true; } catch (e) { r.routed = false; }
        }
      }
      if (!r.unlocked) {
        try { r.el.src = SILENT; const pr = r.el.play(); if (pr && pr.then) pr.then(function () { r.unlocked = true; r.el.pause(); }).catch(function () { /* retried on the next tap */ }); } catch (e) { /* ignore */ }
      }
      return r.el;
    };
    const playUrl = function (url) {
      return new Promise(function (resolve) {
        const r = R.current;
        const a = unlockAudio();
        r.audio = a; r.audioDone = resolve;
        const end = function () { a.onended = null; a.onerror = null; if (r.audio === a) r.audio = null; if (r.audioDone === resolve) r.audioDone = null; resolve(); };
        a.onended = end; a.onerror = end;
        a.src = url;
        const pr = a.play();
        if (pr && pr.catch) pr.catch(function () { end(); r.blocked = true; setError("Your phone blocked the sound. Tap Hear it under the answer."); });
      });
    };
    // Speak a chosen message from a tap (works even where automatic sound is blocked).
    const speakNow = function (text) {
      const r = R.current;
      unlockAudio();
      stopSpeaking();
      r.blocked = false; setError("");
      r.spokenChars = 0;
      const t = String(text || "").trim();
      if (t) enqueueSpeech(t.length > 900 ? t.slice(0, 900) : t);
    };
    // Step-by-step sound check for phones: a local beep first (does this phone play sound at all?), then a real spoken sentence (does the server voice arrive and play?).
    const makeTone = function () {
      const rate = 8000, n = Math.floor(rate * 0.7), bytes = new Uint8Array(44 + n * 2), dv = new DataView(bytes.buffer);
      const w = function (o, str) { for (let i = 0; i < str.length; i++) dv.setUint8(o + i, str.charCodeAt(i)); };
      w(0, "RIFF"); dv.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
      dv.setUint32(24, rate, true); dv.setUint32(28, rate * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); w(36, "data"); dv.setUint32(40, n * 2, true);
      for (let i = 0; i < n; i++) { const env = Math.min(1, i / 300, (n - i) / 300); dv.setInt16(44 + i * 2, Math.round(Math.sin(2 * Math.PI * 660 * i / rate) * 0.7 * env * 32767), true); }
      let bin = ""; for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      return "data:audio/wav;base64," + btoa(bin);
    };
    const soundTest = function () {
      const r = R.current;
      const out = [];
      const show = function (l) { out.push(l); setDiag(out.join("\n")); };
      const el = unlockAudio();
      const sleep = function (ms) { return new Promise(function (res) { setTimeout(res, ms); }); };
      const attempt = function (label, src) {
        return new Promise(function (resolve) {
          try { el.onended = null; el.onerror = null; el.pause(); } catch (e) { /* ignore */ }
          el.muted = false; el.volume = 1;
          el.src = src;
          let pr;
          try { pr = el.play(); } catch (e) { show(label + ": play() threw " + e.name + ": " + e.message); resolve(false); return; }
          const done = function (ok, why) {
            const t = el.currentTime || 0;
            show(label + ": " + (ok ? "playing" : "FAILED") + " (" + why + "; position " + t.toFixed(2) + "s, length " + (isFinite(el.duration) ? el.duration.toFixed(2) : "?") + "s" + (el.error ? ", media error " + el.error.code : "") + ")");
            resolve(ok);
          };
          (pr && pr.then ? pr : Promise.resolve()).then(function () { return sleep(500); }).then(function () { done(el.currentTime > 0.05 || el.ended, "phone accepted it"); })
            .catch(function (e) { done(false, "blocked: " + (e && e.name) + " " + ((e && e.message) || "")); });
        });
      };
      show("Sound check (build 3). Secure page: " + (window.isSecureContext ? "yes" : "NO") + ", touch: " + (navigator.maxTouchPoints || 0) + ", browser: " + navigator.userAgent.replace(/^Mozilla\/5\.0 /, "").slice(0, 70));
      show("Step 1 of 2: a short beep from this page. Listen now.");
      attempt("Beep", makeTone()).then(function () { return sleep(900); }).then(function () {
        show("Step 2 of 2: fetching a spoken sentence from the server...");
        const t0 = Date.now();
        return fetchAudio("Sound check. If you can hear this, Jarvis can speak on this phone.").then(function (url) {
          show("Voice audio arrived in " + ((Date.now() - t0) / 1000).toFixed(1) + " s (" + Math.round(url.length * 0.75 / 1024) + " KB, " + url.slice(5, url.indexOf(";")) + ").");
          return attempt("Voice", url);
        });
      }).then(function () { show("Done. Tell me: did you hear the beep, and did you hear the voice?"); })
        .catch(function (e) { show("Voice audio could not be fetched: " + ((e && e.message) || e)); });
    };
    const pump = function () {
      const r = R.current;
      if (r.playing) return;
      r.playing = true;
      (async function () {
        try {
          while (r.q.length) {
            const item = r.q.shift();
            if (item.gen !== r.speakGen) continue;
            let url = null;
            try { url = await item.p; } catch (e) { setError((e && e.message) || "Speech failed."); continue; }
            if (item.gen !== r.speakGen) continue;
            setPhase("speaking");
            await playUrl(url);
          }
        } finally { r.playing = false; }
        if (r.q.length) { pump(); return; }
        setPhase(r.active ? "reporting" : "idle");
      })();
    };
    const enqueueSpeech = function (text) {
      const r = R.current;
      const p = fetchAudio(text);
      p.catch(function () { /* reported when it is awaited */ });
      r.spokenChars += text.length;
      r.q.push({ gen: r.speakGen, p: p });
      pump();
    };
    const feedSpeech = function (final) {
      const r = R.current;
      if (!r.ttsOn) return;
      const text = r.buf;
      while (r.spokenChars < 700) {
        const re = /[.!?](?=\s)/g;
        re.lastIndex = r.spokenIdx;
        let m, cut = -1;
        while ((m = re.exec(text)) !== null) { if (m.index + 1 - r.spokenIdx >= 14) { cut = m.index + 1; break; } }
        if (cut < 0) break;
        const s = text.slice(r.spokenIdx, cut).trim();
        r.spokenIdx = cut;
        if (s) enqueueSpeech(s);
      }
      if (final) {
        const rest = text.slice(r.spokenIdx).trim();
        r.spokenIdx = text.length;
        if (rest && r.spokenChars < 900) enqueueSpeech(rest);
      }
    };

    const finishTurn = function (finalText) {
      const r = R.current;
      clearTimeout(r.filler);
      r.active = false;
      setStage(4); setTool(""); setPartial("");
      const clean = String(finalText || r.buf || "").trim();
      say("assistant", clean || "(no reply)");
      if (r.ttsOn && clean) {
        if (!r.buf) r.buf = clean;
        feedSpeech(true);
        if (!r.playing && !r.q.length) setPhase("idle");
      } else setPhase("idle");
    };

    function onFrame(f) {
      const r = R.current;
      if (f.id != null && r.pending[f.id]) {
        const p = r.pending[f.id]; delete r.pending[f.id];
        if (f.error) p.reject(new Error(f.error.message || "Request failed")); else p.resolve(f.result);
        return;
      }
      if (f.method !== "event" || !f.params) return;
      const type = f.params.type, pl = f.params.payload || {};
      if (f.params.session_id && r.sid && f.params.session_id !== r.sid) return;
      if (Array.isArray(pl.choices) && (type || "").indexOf("approval") >= 0) {
        setApproval({ command: String(pl.command || pl.description || "an action"), request_id: pl.request_id || pl.id || null, why: pl.reason || pl.description || "" });
        return;
      }
      if (!r.active) return;
      if (type === "message.start") { setPhase("thinking"); setStage(0); }
      else if (type === "thinking.delta" || type === "reasoning.delta") { if (!r.playing) setPhase("thinking"); setStage(1); }
      else if (type === "tool.start" || type === "tool.generating") { const nm = String(pl.name || pl.tool || pl.tool_name || "tool"); setTool(nm); if (!r.playing) setPhase("working"); setStage(2); }
      else if (type === "tool.complete") { setStage(3); }
      else if (type === "message.delta") { clearTimeout(r.filler); r.buf += String(pl.text || ""); setPartial(r.buf); if (!r.playing) setPhase("reporting"); setStage(4); feedSpeech(false); }
      else if (type === "message.complete") { finishTurn(pl.text); }
      else if (type === "error") { r.active = false; setPhase("error"); setError(String(pl.message || pl.error || "Something went wrong.")); }
    }

    const submit = function (text) {
      unlockAudio();
      const t = String(text || "").trim();
      if (!t) return;
      const r = R.current;
      if (r.active) return;
      setError(""); setApproval(null);
      say("user", t);
      stopSpeaking();
      r.active = true; r.buf = ""; r.spokenIdx = 0; r.spokenChars = 0; r.turnStart = Date.now();
      setElapsed(0); setPartial(""); setPhase("thinking"); setStage(0);
      // Live facts (counts and schedule only) ride along, so status questions are answered without slow tool lookups.
      const briefP = Promise.race([fetchJSON(API + "/jarvis/brief").then(function (b) { return b && b.text ? b.text + String.fromCharCode(10, 10) : ""; }), new Promise(function (res) { setTimeout(function () { res(""); }, 2500); })]).catch(function () { return ""; });
      clearTimeout(r.filler);
      r.filler = setTimeout(function () { if (r.active && !r.buf && r.ttsOn && !r.playing) enqueueSpeech("One moment."); }, 5000);
      Promise.all([ensureSession(), briefP]).then(function (v) {
        return rpc("prompt.submit", { session_id: v[0], text: (r.ttsOn ? VOICE_HINT : "") + v[1] + t });
      }).catch(function (e) { clearTimeout(r.filler); r.active = false; setPhase("error"); setError(e && e.message ? e.message : "Could not reach Gideon."); });
    };

    const interrupt = function () {
      const r = R.current;
      clearTimeout(r.filler);
      if (r.sid && r.ws && r.ws.readyState === 1) { rpc("session.interrupt", { session_id: r.sid }).catch(function () { /* ignore */ }); }
      r.active = false; r.buf = "";
      setPartial(""); setPhase("idle"); setTool(""); setStage(-1);
    };

    const respondApproval = function (choice) {
      const a = approval;
      setApproval(null);
      const r = R.current;
      if (!r.sid) return;
      rpc("approval.respond", { session_id: r.sid, choice: choice === "once" ? "once" : "deny", request_id: a && a.request_id }).catch(function () { /* ignore */ });
      say("system", choice === "once" ? "Approved once: " + (a ? a.command : "") : "Denied: " + (a ? a.command : ""));
    };

    // ---------- listening ----------
    const stopListening = function (discard) {
      const r = R.current, rec = r.rec;
      if (!rec) return;
      r.rec = null; setTapRec(false);
      try { rec.proc.onaudioprocess = null; rec.proc.disconnect(); rec.src.disconnect(); } catch (e) { /* ignore */ }
      rec.stream.getTracks().forEach(function (t) { t.stop(); });
      r.micStream = null;
      const total = rec.chunks.reduce(function (n, c) { return n + c.length; }, 0);
      if (discard || Date.now() - rec.start < 500 || total < rec.rate * 0.4) { setPhase("idle"); return; }
      setPhase("transcribing");
      blobToDataUrl(encodeWav(rec.chunks, rec.rate, 16000)).then(function (dataUrl) {
        return fetchJSON("/api/audio/transcribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_url: dataUrl, mime_type: "audio/wav" }) });
      }).then(function (d) {
        const t = (d && d.transcript || "").trim();
        if (!t) { setPhase("idle"); setError("I did not catch that. Try again a little closer to the microphone."); return; }
        submit(t);
      }).catch(function (e) { setPhase("error"); setError((e && e.message) || "Transcription failed."); });
    };
    const startListening = function () {
      const r = R.current;
      if (r.rec || r.active) return;
      if (!window.isSecureContext) { setError("The microphone only works on the secure address. Open " + SECURE_URL); return; }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { setError("This browser does not let web pages use the microphone. Update it, or type instead."); return; }
      if (!(window.AudioContext || window.webkitAudioContext)) { setError("This browser has no audio engine for recording. Type instead."); return; }
      stopSpeaking();
      let ctx;
      try { ctx = getCtx().ctx; } catch (e) { setError("Audio could not start in this browser."); return; }
      navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } }).then(function (stream) {
        if (ctx.state === "suspended") ctx.resume();
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(4096, 1, 1);
        // If the finger was already lifted while the permission prompt was open, behave as tap-to-talk.
        const rec = { stream: stream, src: src, proc: proc, chunks: [], rate: ctx.sampleRate, start: Date.now(), heard: false, quietSince: 0, tap: r.upAt >= r.downAt };
        proc.onaudioprocess = function (e) {
          const d = e.inputBuffer.getChannelData(0);
          if (!rec.live) { rec.live = true; setPhase("listening"); }   // only say Listening once sound is really flowing
          rec.chunks.push(new Float32Array(d));
          let s = 0;
          for (let i = 0; i < d.length; i++) s += d[i] * d[i];
          const rms = Math.sqrt(s / d.length), now = Date.now();
          if (rms > 0.015) { rec.heard = true; rec.quietSince = 0; }
          else if (rec.heard && rec.tap) { if (!rec.quietSince) rec.quietSince = now; else if (now - rec.quietSince > 1400) stopListening(false); }
          if (now - rec.start > 45000) stopListening(false);
        };
        src.connect(r.micAn); src.connect(proc); proc.connect(ctx.destination);
        r.rec = rec; r.micStream = stream;
        setTapRec(rec.tap); setError(""); setPhase("arming");
      }).catch(function (err) {
        setPhase("idle");
        setError(err && err.name === "NotAllowedError" ? "Microphone permission was denied. Allow it for this site in your browser settings, then try again." : "Could not start the microphone (" + ((err && err.name) || "error") + ").");
      });
    };
    // Hold the button to talk, or tap it once and pause when you finish (it stops itself), or tap again to send.
    const micDown = function () {
      const r = R.current;
      r.downAt = Date.now();
      unlockAudio();
      if (r.rec && r.rec.tap) { stopListening(false); return; }
      startListening();
    };
    const micUp = function () {
      const r = R.current;
      r.upAt = Date.now();
      if (!r.rec) return;
      if (r.rec.tap) return;
      if (Date.now() - r.downAt < 350) { r.rec.tap = true; setTapRec(true); } else stopListening(false);
    };

    const stopAll = function () {
      stopSpeaking();
      const r = R.current;
      if (r.rec) stopListening(true);
      if (r.active) interrupt(); else setPhase("idle");
    };

    return { phase: phase, stage: stage, tool: tool, messages: messages, partial: partial, error: error, approval: approval, elapsed: elapsed, ttsOn: ttsOn, setTtsOn: setTtsOn, tapRec: tapRec,
      levelRef: levelRef, submit: submit, interrupt: interrupt, respondApproval: respondApproval, micDown: micDown, micUp: micUp, stopAll: stopAll, warm: warm, resetSession: resetSession,
      clearError: function () { setError(""); }, diag: diag, clearDiag: function () { setDiag(""); }, playSample: function (url) { unlockAudio(); stopSpeaking(); return playUrl(url); }, soundTest: soundTest, speakNow: speakNow, unlockAudio: unlockAudio };
  }

