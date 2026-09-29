  function VoiceSettings(props) {
    const jv = props.jv;
    const [voices, setVoices] = useState([]);
    const [jvoices, setJvoices] = useState([]);
    const [cfg, setCfg] = useState(null);
    const [note, setNote] = useState("");
    useEffect(function () {
      fetchJSON(API + "/jarvis/voices").then(function (d) { setVoices(d.voices || []); setJvoices(d.jarvis_voices || []); setCfg(d.settings); }).catch(function () { setNote("Could not load voices."); });
    }, []);
    if (!cfg) return h("div", { className: "hcc-voice-pop" }, note || "Loading voices…");
    const engine = cfg.engine === "edge" ? "edge" : "jarvis";
    const num = function (s, unit) { return parseInt(String(s).replace(unit, ""), 10) || 0; };
    const set = function (k, v) { setCfg(Object.assign({}, cfg, { [k]: v })); };
    const fmt = function (n, unit) { return (n >= 0 ? "+" : "") + n + unit; };
    const save = function () {
      fetchJSON(API + "/jarvis/settings", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice: cfg.voice, rate: cfg.rate, pitch: cfg.pitch, speed: cfg.speed, engine: engine, jarvis_voice: cfg.jarvis_voice }) })
        .then(function () { setNote("Saved."); if (jv) jv.resetSession(); }).catch(function (e) { setNote((e && e.message) || "Could not save."); });
    };
    const preview = function () {
      setNote("Preparing a sample…");
      const t0 = Date.now();
      fetchJSON(API + "/jarvis/speak", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "Good day, Precious. This is how I will sound.", voice: cfg.voice, rate: cfg.rate, pitch: cfg.pitch, engine: engine, jarvis_voice: cfg.jarvis_voice }) })
        .then(function (d) {
          setNote("Playing (" + ((Date.now() - t0) / 1000).toFixed(1) + " s to prepare" + (d.engine === "edge" && engine === "jarvis" ? ", using the cloud voice because the Jarvis voice was busy" : "") + ")");
          return jv.playSample(d.data_url);
        }).then(function () { setNote(""); }).catch(function (e) { setNote((e && e.message) || "Preview failed."); });
    };
    return h("div", { className: "hcc-voice-pop" }, [
      h("label", { key: "le" }, "Voice engine"),
      h("select", { key: "se", value: engine, onChange: function (e) { set("engine", e.target.value); } }, [
        h("option", { key: "j", value: "jarvis" }, "Jarvis voice: made on this server, private (recommended)"),
        h("option", { key: "e", value: "edge" }, "Cloud voices: Microsoft Edge, starts about 2 s sooner"),
      ]),
      engine === "jarvis" ? h("label", { key: "l1" }, "Character") : h("label", { key: "l1" }, "Voice (free Edge neural voices)"),
      engine === "jarvis"
        ? h("select", { key: "s", value: cfg.jarvis_voice || "jarvis", onChange: function (e) { set("jarvis_voice", e.target.value); } },
          jvoices.map(function (v) { return h("option", { key: v.id, value: v.id }, v.label); }))
        : h("select", { key: "s", value: cfg.voice, onChange: function (e) { set("voice", e.target.value); } },
          voices.map(function (v) { return h("option", { key: v.name, value: v.name }, v.name.replace("Neural", "") + " · " + v.gender + " · " + v.locale); })),
      h("label", { key: "lf" }, "Reply speed"),
      h("select", { key: "sf", value: cfg.speed || "balanced", onChange: function (e) { set("speed", e.target.value); } }, [
        h("option", { key: "f", value: "fastest" }, "Fastest: about 4 seconds, but a small model that can slip on details"),
        h("option", { key: "p", value: "premium" }, "Premium: ChatGPT subscription, about 5 seconds, steadiest" + (cfg.premium_ok === false ? " (ChatGPT login needed, using Balanced)" : "")),
        h("option", { key: "b", value: "balanced" }, "Balanced: free model, about 8 seconds, reliable on facts"),
        h("option", { key: "o", value: "original" }, "Original: Gideon's own model, about 25 seconds"),
      ]),
      engine === "edge" ? h("label", { key: "l2" }, "Voice speed " + cfg.rate) : null,
      engine === "edge" ? h("input", { key: "r", type: "range", min: -30, max: 30, value: num(cfg.rate, "%"), onChange: function (e) { set("rate", fmt(parseInt(e.target.value, 10), "%")); } }) : null,
      engine === "edge" ? h("label", { key: "l3" }, "Pitch " + cfg.pitch) : null,
      engine === "edge" ? h("input", { key: "p", type: "range", min: -30, max: 30, value: num(cfg.pitch, "Hz"), onChange: function (e) { set("pitch", fmt(parseInt(e.target.value, 10), "Hz")); } }) : null,
      h("div", { key: "b", className: "hcc-voice-actions" }, [
        h("button", { key: "pv", className: "hcc-btn2", onClick: preview }, "Preview"),
        h("button", { key: "sv", className: "hcc-btn2 hcc-btn2-primary", onClick: save }, "Save as Jarvis's voice"),
      ]),
      cfg.speed === "premium" ? h("div", { key: "pn", className: "hcc-muted-note" }, "Premium sends your questions (with counts-only live facts, never mail or event contents) to OpenAI through your ChatGPT subscription and uses part of its usage allowance.") : null,
      h("div", { key: "n", className: "hcc-muted-note" }, note || (engine === "jarvis"
        ? "Speech is generated on your own server and nothing is sent to a third party. If it is ever busy, Jarvis falls back to a cloud voice so it never goes silent."
        : "Text is sent to Microsoft's free speech service to make the audio. Nothing is stored.")),
    ]);
  }

