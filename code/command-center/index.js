(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React, fetchJSON } = SDK;
  const h = React.createElement;
  const { useEffect, useState, useCallback, useRef } = SDK.hooks;
  const API = "/api/plugins/hermes-command-center";

  function cls(value) {
    return String(value || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  }

  function fmtUptime(seconds) {
    if (seconds == null) return "—";
    const d = Math.floor(seconds / 86400);
    const hr = Math.floor((seconds % 86400) / 3600);
    const min = Math.floor((seconds % 3600) / 60);
    if (d > 0) return d + "d " + hr + "h";
    if (hr > 0) return hr + "h " + min + "m";
    return min + "m";
  }

  function Pill(props) {
    return h("span", { className: "hcc-pill hcc-" + cls(props.value) }, props.label || props.value || "UNKNOWN");
  }

  function Panel(props) {
    return h("section", { className: "hcc-panel " + (props.className || "") }, [
      h("div", { className: "hcc-panel-head", key: "h" }, [
        h("h2", { key: "t" }, props.title),
        props.extra || null,
      ]),
      h("div", { className: "hcc-panel-body", key: "b" }, props.children),
    ]);
  }

  function Gauge(props) {
    const pct = Math.max(0, Math.min(100, props.value || 0));
    const r = 34, c = 2 * Math.PI * r;
    const offset = c - (pct / 100) * c;
    let color = "var(--hcc-cyan)";
    if (pct > 85) color = "var(--hcc-red)"; else if (pct > 65) color = "var(--hcc-amber)";
    return h("div", { className: "hcc-gauge" }, [
      h("svg", { key: "svg", width: 80, height: 80, viewBox: "0 0 80 80" }, [
        h("circle", { key: "t", className: "hcc-gauge-track", cx: 40, cy: 40, r: r }),
        h("circle", { key: "v", className: "hcc-gauge-value", cx: 40, cy: 40, r: r, style: { stroke: color, strokeDasharray: c, strokeDashoffset: offset } }),
      ]),
      h("div", { key: "n", className: "hcc-gauge-num" }, pct.toFixed(0) + "%"),
      h("div", { key: "l", className: "hcc-gauge-label" }, props.label),
    ]);
  }

  function AICore(props) {
    const s = props.status || {};
    const gwRunning = s.gateway && s.gateway.running;
    const platforms = s.platforms || {};
    const anyError = Object.values(platforms).some((p) => p && p.error);
    let state = "idle";
    if (!gwRunning) state = "offline"; else if (anyError) state = "error";
    return h("div", { className: "hcc-core-wrap" },
      h("div", { className: "hcc-core", "data-state": state }, [
        h("div", { className: "hcc-core-ring", key: "r1" }),
        h("div", { className: "hcc-core-ring--2", key: "r2" }),
        h("div", { className: "hcc-core-ring--3", key: "r3" }),
        h("div", { className: "hcc-core-orb", key: "orb" }),
        h("div", { className: "hcc-core-particle", key: "p1", style: { "--hcc-orbit-r": "118px", animationDuration: "9s" } }),
        h("div", { className: "hcc-core-particle", key: "p2", style: { "--hcc-orbit-r": "95px", animationDuration: "6s", animationDirection: "reverse" } }),
        h("div", { className: "hcc-core-label", key: "label" }, [
          h("strong", { key: "s" }, "HERMES"),
          h("span", { key: "sub" }, gwRunning ? state.toUpperCase() : "OFFLINE"),
        ]),
      ])
    );
  }

  const STAT_DETAILS = {
    Gateway: "The multiplexed Hermes gateway process serving Telegram, Slack and every profile from one long-running server.",
    Uptime: "Time since the current gateway process started (derived from /proc/uptime vs process start time).",
    Version: "Installed Hermes Agent version and upstream commit.",
    "Profiles served": "Profiles currently multiplexed by this gateway instance.",
    "Channels connected": "Messaging platforms with an active, authenticated connection.",
    "Memory (Honcho)": "Cross-session memory recall — persists context across chats.",
    "Obsidian vault": "Local notes vault Hermes agents can read/write via the obsidian skill.",
    Firecrawl: "Web search/scrape/extract backend for research workflows.",
  };

  function AICoreOverview(props) {
    const s = props.status || {};
    const [open, setOpen] = useState(null);
    const gw = s.gateway || {};
    const platforms = s.platforms || {};
    const connected = Object.entries(platforms).filter(([, p]) => p && p.state === "connected").map(([k]) => k);
    const rows = [
      ["Gateway", gw.running ? "Running" : "Stopped", gw.running ? "ok" : "err"],
      ["Uptime", fmtUptime(gw.uptime_seconds), "info"],
      ["Version", gw.code_version || "—", "info"],
      ["Profiles served", (gw.multiplex_profiles || []).length + " / " + ((s.profiles || []).length || (gw.multiplex_profiles || []).length), "info"],
      ["Channels connected", connected.join(", ") || "none", connected.length ? "ok" : "warn"],
      ["Memory (Honcho)", s.honcho && s.honcho.configured ? "Configured" : "Not configured", s.honcho && s.honcho.configured ? "ok" : "idle"],
      ["Obsidian vault", s.obsidian && s.obsidian.configured ? (s.obsidian.note_count != null ? s.obsidian.note_count + " notes" : "Configured") : "Not configured", s.obsidian && s.obsidian.configured ? "ok" : "idle"],
      ["Firecrawl", s.firecrawl && s.firecrawl.available ? "Available (" + s.firecrawl.mode + ")" : "Unavailable", s.firecrawl && s.firecrawl.available ? "ok" : "idle"],
    ];
    return h(Panel, { title: "AI Core Overview" }, rows.map((r, i) => h("div", { key: i }, [
      h("div", {
        className: "hcc-stat-row", key: "row",
        onClick: () => setOpen(open === i ? null : i),
      }, [
        h("span", { className: "hcc-k", key: "k" }, r[0]),
        h("span", { className: "hcc-v", key: "v" }, [h(Pill, { key: "p", value: r[1], label: r[1] }), h("span", { className: "hcc-chevron", key: "c" }, open === i ? "▾" : "▸")]),
      ]),
      open === i ? h("div", { className: "hcc-stat-detail", key: "detail" }, STAT_DETAILS[r[0]] || "") : null,
    ])));
  }

  function LiveFeed(props) {
    const events = props.events || [];
    const chip = h("span", { className: "hcc-status-chip" }, [h("span", { className: "hcc-live-dot", key: "d" }), props.live ? " LIVE · PUSH" : " POLLING"]);
    if (!events.length) return h(Panel, { title: "Live Intelligence Feed", extra: chip }, h("div", { className: "hcc-empty" }, props.live ? "Connected. Waiting for new activity…" : "No recent gateway activity in the last 2 hours."));
    return h(Panel, {
      title: "Live Intelligence Feed",
      extra: chip,
    }, h("ul", { className: "hcc-feed" }, events.map((e, i) => h("li", { key: i }, [
      h("time", { key: "t" }, ((e.timestamp || "").split("T")[1] || e.timestamp || "").replace(/(Z|[+-]\d\d:?\d\d)$/, "")),
      h("span", { className: "hcc-src", key: "s" }, e.source),
      h("span", { className: "hcc-msg", key: "m" }, e.message),
    ]))));
  }

  function ExpandableCardGrid(props) {
    const [openKey, setOpenKey] = useState(null);
    return h("div", { className: "hcc-card-grid" }, props.items.map((item) => {
      const isOpen = openKey === item.key;
      return h("div", {
        className: "hcc-card" + (isOpen ? " hcc-card-open" : ""), key: item.key,
        onClick: () => setOpenKey(isOpen ? null : item.key),
      }, [
        h("div", { className: "hcc-card-title", key: "t" }, [item.title, h("span", { className: "hcc-chevron", key: "c" }, isOpen ? "▾" : "▸")]),
        item.sub ? h("div", { className: "hcc-card-sub", key: "s" }, item.sub) : null,
        h(Pill, { key: "p", value: item.pillValue, label: item.pillLabel }),
        isOpen && item.detail ? h("div", { className: "hcc-card-detail", key: "d" }, item.detail) : null,
        isOpen && item.href ? h("a", {
          key: "link", className: "hcc-card-link", href: item.href,
          onClick: (e) => e.stopPropagation(),
        }, "Open " + item.hrefLabel + " page →") : null,
      ]);
    }));
  }


  function ModelPicker(props) {
    const row = props.row;
    const [choice, setChoice] = useState("");
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState("");
    if (!row || !row.editable) return h("div", { className: "hcc-modelpick-note" }, "Model is managed outside the dashboard for this profile.");
    const apply = async function (e) {
      e.stopPropagation();
      setBusy(true); setNote("Checking the model with a live test…");
      try { const r = await props.onApply(row.name, choice); setNote(r && r.note ? r.note : "Saved."); setChoice(""); }
      catch (err) { setNote(err && err.message ? err.message : "Could not change the model."); }
      setBusy(false);
    };
    return h("div", { className: "hcc-modelpick", onClick: (e) => e.stopPropagation() }, [
      h("label", { key: "l" }, "Change model"),
      h("div", { className: "hcc-modelpick-row", key: "r" }, [
        h("select", { key: "s", value: choice, onChange: (e) => setChoice(e.target.value), disabled: busy },
          [h("option", { key: "_", value: "" }, "Pick a verified model…")].concat(row.options.filter((o) => o !== row.model).map((o) => h("option", { key: o, value: o }, o)))),
        h("button", { key: "b", className: "hcc-modelpick-btn", disabled: busy || !choice, onClick: apply }, busy ? "Testing…" : "Apply"),
      ]),
      note ? h("div", { className: "hcc-modelpick-note", key: "n" }, note) : null,
    ]);
  }

  function HeatMap(props) {
    const hm = props.heat;
    if (!hm) return h(Panel, { title: "Activity Heat Map" }, h("div", { className: "hcc-empty" }, "Loading activity…"));
    const peak = hm.peak || 1;
    const agents = Object.keys(hm.agents || {});
    const chips = ["all"].concat(agents);
    const cell = function (n, d, hr) {
      const a = n ? Math.max(0.16, n / peak) : 0;
      return h("i", { key: hr, className: "hcc-heat-cell", title: d + " " + String(hr).padStart(2, "0") + ":00 UTC: " + n + (n === 1 ? " session" : " sessions"),
        style: { background: n ? "rgba(56,189,248," + a.toFixed(2) + ")" : "rgba(255,255,255,.04)" } });
    };
    const hourLabels = [0, 6, 12, 18, 23].map((x) => h("span", { key: x, style: { gridColumn: (x + 1) + " / span 3" } }, String(x).padStart(2, "0")));
    return h(Panel, {
      title: "Activity Heat Map · last " + hm.days + " days",
      extra: h("div", { className: "hcc-heat-filters" }, chips.map((c) => h("button", {
        key: c, "data-active": String((props.agent || "all") === c), onClick: () => props.onAgent(c === "all" ? "" : c),
      }, c === "all" ? "all" : c))),
    }, [
      h("div", { className: "hcc-heat", key: "g" }, [
        h("div", { className: "hcc-heat-row hcc-heat-hours", key: "hh" }, [h("span", { className: "hcc-heat-date", key: "e" }, ""), h("div", { className: "hcc-heat-cells hcc-heat-labels", key: "c" }, hourLabels)]),
      ].concat(hm.grid.map((r) => h("div", { className: "hcc-heat-row", key: r.date }, [
        h("span", { className: "hcc-heat-date", key: "d" }, r.date.slice(5)),
        h("div", { className: "hcc-heat-cells", key: "c" }, r.hours.map((n, hr) => cell(n, r.date, hr))),
      ])))),
      h("div", { className: "hcc-muted-note", key: "n", style: { marginTop: 8 } }, "Sessions started per hour, UTC. " + hm.total + " in this window; busiest hour = " + hm.peak + "."),
    ]);
  }

  function Profiles(props) {
    const profiles = props.profiles || [];
    return h(Panel, { title: "Active Profiles" }, h(ExpandableCardGrid, {
      items: profiles.map((p) => ({
        key: p.name, title: p.name, sub: (p.provider || "no provider") + (p.model ? " · " + p.model : ""),
        pillValue: p.served_by_multiplex ? "served" : "idle", pillLabel: p.served_by_multiplex ? "SERVED" : "IDLE",
        href: "/profiles", hrefLabel: "Profiles",
        detail: h("div", null, [
          h("div", { key: "1" }, [h("span", null, "Provider"), h("span", null, p.provider || "—")]),
          h("div", { key: "2" }, [h("span", null, "Model"), h("span", null, p.model || "—")]),
          h("div", { key: "3" }, [h("span", null, "Multiplexed"), h("span", null, p.served_by_multiplex ? "Yes" : "No")]),
          h(ModelPicker, { key: "mp", row: (props.models || []).find((x) => x.name === p.name), onApply: props.onModel }),
        ]),
      })),
    }));
  }

  function SystemMonitor(props) {
    const sys = props.system || {};
    if (!sys.available) return h(Panel, { title: "System Monitor" }, h("div", { className: "hcc-empty" }, "psutil not available on host — metrics not shown (not fabricated)."));
    return h(Panel, { title: "System Monitor" }, h("div", { className: "hcc-gauge-row" }, [
      h(Gauge, { key: "cpu", value: sys.cpu_percent, label: "CPU" }),
      h(Gauge, { key: "mem", value: sys.memory && sys.memory.percent, label: "RAM" }),
      h(Gauge, { key: "disk", value: sys.disk && sys.disk.percent, label: "Disk" }),
    ]));
  }

  function ProviderStatus(props) {
    const profiles = props.profiles || [];
    const seen = {};
    profiles.forEach((p) => { if (p.provider) { seen[p.provider] = seen[p.provider] || []; seen[p.provider].push(p.name); } });
    const entries = Object.entries(seen);
    if (!entries.length) return h(Panel, { title: "Provider / LLM Status" }, h("div", { className: "hcc-empty" }, "No providers configured."));
    return h(Panel, { title: "Provider / LLM Status" }, h(ExpandableCardGrid, {
      items: entries.map(([name, profs]) => ({
        key: name, title: name, sub: "used by " + profs.length + " profile" + (profs.length > 1 ? "s" : ""),
        pillValue: "connected", pillLabel: "CONFIGURED",
        detail: h("div", null, profs.map((p, i) => h("div", { key: i }, [h("span", null, p), h("span", null, "")]))),
      })),
    }));
  }

  function ChannelStatus(props) {
    const platforms = props.platforms || {};
    const entries = Object.entries(platforms);
    if (!entries.length) return h(Panel, { title: "Channel Status" }, h("div", { className: "hcc-empty" }, "No platforms configured."));
    return h(Panel, { title: "Channel Status" }, h(ExpandableCardGrid, {
      items: entries.map(([name, info]) => ({
        key: name, title: name, pillValue: info.state, pillLabel: (info.state || "unknown").toUpperCase(),
        href: "/channels", hrefLabel: "Channels",
        detail: h("div", null, [
          h("div", { key: "1" }, [h("span", null, "State"), h("span", null, info.state || "unknown")]),
          h("div", { key: "2" }, [h("span", null, "Error"), h("span", null, info.error || "none")]),
        ]),
      })),
    }));
  }

  function ToolsAndSkills(props) {
    const mcp = props.mcp_servers || [];
    const firecrawl = props.firecrawl || {};
    const obsidian = props.obsidian || {};
    const rows = mcp.map((m) => ({ key: m.name, title: m.name, pillValue: /enabled/.test(m.status) ? "enabled" : "unknown", pillLabel: m.status, sub: m.transport, href: "/mcp", hrefLabel: "MCP" }));
    rows.push({ key: "firecrawl", title: "Firecrawl (web)", pillValue: firecrawl.available ? "available" : "idle", pillLabel: firecrawl.available ? "AVAILABLE" : "UNAVAILABLE", sub: firecrawl.mode ? "mode: " + firecrawl.mode : "" });
    rows.push({ key: "obsidian", title: "Obsidian vault", pillValue: obsidian.configured ? "configured" : "idle", pillLabel: obsidian.configured ? "ENABLED" : "DISABLED", sub: obsidian.path });
    return h(Panel, { title: "Tools & Skills" }, h(ExpandableCardGrid, { items: rows }));
  }

  function ConfirmModal(props) {
    if (!props.open) return null;
    return h("div", { className: "hcc-modal-backdrop", onClick: props.onCancel }, h("div", { className: "hcc-modal", onClick: (e) => e.stopPropagation() }, [
      h("h3", { key: "h" }, props.title),
      h("p", { key: "p" }, props.message),
      h("div", { className: "hcc-modal-actions", key: "a" }, [
        h("button", { key: "c", onClick: props.onCancel }, "Cancel"),
        h("button", { key: "ok", className: "hcc-confirm-danger", onClick: props.onConfirm }, props.confirmLabel || "Confirm"),
      ]),
    ]));
  }

  function QuickCommands(props) {
    const [confirming, setConfirming] = useState(null);
    const [toast, setToast] = useState(null);

    const showToast = (msg, isError) => {
      setToast({ msg, isError });
      setTimeout(() => setToast(null), 3500);
    };

    const commands = [
      { key: "chat", label: "Open Hermes Chat", sub: "Start a conversation", danger: false, action: () => { window.location.pathname = "/chat"; } },
      { key: "logs", label: "Open Live Logs", sub: "View raw gateway log stream", danger: false, action: () => { window.location.pathname = "/logs"; } },
      { key: "mc", label: "Open Mission Control", sub: "Product Factory dashboard (port 9220)", danger: false, action: () => { showToast("Mission Control runs on a separate URL — http://" + window.location.hostname + ":9220"); } },
      { key: "refresh", label: "Refresh Status", sub: "Reload all panels now", danger: false, action: props.onRefresh },
      { key: "restart", label: "Restart Gateway", sub: "Reconnects Telegram/Slack — brief interruption", danger: true, action: null },
    ];

    const doRestart = async () => {
      setConfirming(null);
      try {
        await fetchJSON(API + "/restart-gateway", { method: "POST" });
        showToast("Gateway restart requested.");
      } catch (err) {
        showToast((err && err.message) || "Restart failed", true);
      }
    };

    return h(Panel, { title: "Quick Commands" }, [
      h("div", { className: "hcc-cmd-grid", key: "grid" }, commands.map((c) => h("button", {
        key: c.key, className: "hcc-cmd-btn" + (c.danger ? " hcc-cmd-danger" : ""),
        onClick: () => (c.danger ? setConfirming(c.key) : c.action()),
      }, [
        h("strong", { key: "l" }, c.label),
        h("span", { key: "s" }, c.sub),
      ]))),
      h(ConfirmModal, {
        key: "modal", open: confirming === "restart",
        title: "Restart Hermes Gateway?", message: "Telegram and Slack will briefly disconnect and reconnect. This does not affect the dashboards.",
        confirmLabel: "Restart", onCancel: () => setConfirming(null), onConfirm: doRestart,
      }),
      toast ? h("div", { key: "toast", className: "hcc-toast" + (toast.isError ? " hcc-toast-error" : "") }, toast.msg) : null,
    ]);
  }

  function fmtNum(n) {
    n = Number(n || 0);
    if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return String(n);
  }

  function Kpi(props) {
    return h("div", { className: "hcc-kpi" }, [
      h("span", { className: "hcc-kpi-v", key: "v" }, props.value),
      h("span", { className: "hcc-kpi-l", key: "l" }, props.label),
    ]);
  }

  function DayBars(props) {
    const days = props.days || [];
    if (!days.length) return h("div", { className: "hcc-empty" }, "No sessions in this window.");
    const max = Math.max.apply(null, days.map((d) => d.input_tokens + d.output_tokens)) || 1;
    return h("div", { className: "hcc-daybars" }, days.map((d) => {
      const tot = d.input_tokens + d.output_tokens;
      return h("div", { className: "hcc-daybar", key: d.date, title: d.date + ": " + fmtNum(tot) + " tokens, " + d.sessions + " sessions" }, [
        h("div", { className: "hcc-daybar-col", key: "c" }, h("div", { className: "hcc-daybar-fill", style: { height: Math.max(3, Math.round(100 * tot / max)) + "%" } })),
        h("small", { key: "l" }, d.date.slice(5)),
      ]);
    }));
  }

  function HBars(props) {
    const rows = props.rows || [];
    const max = Math.max.apply(null, rows.map((r) => r.value)) || 1;
    return h("div", { className: "hcc-hbars" }, rows.map((r) => h("div", { className: "hcc-hbar", key: r.label, title: r.title || "" }, [
      h("span", { className: "hcc-hbar-l", key: "l" }, r.label),
      h("span", { className: "hcc-hbar-t", key: "t" }, h("span", { className: "hcc-hbar-f", style: { width: Math.max(2, Math.round(100 * r.value / max)) + "%" } })),
      h("span", { className: "hcc-hbar-v", key: "v" }, r.text),
    ])));
  }

  function UsagePanel(props) {
    const u = props.usage;
    if (!u) return h(Panel, { title: "Team Usage" }, h("div", { className: "hcc-empty" }, "Loading usage…"));
    const t = u.totals || {};
    const cost = t.cost_actual_usd || t.cost_estimated_usd || 0;
    const workload = (u.per_profile || []).filter((p) => p.sessions > 0).map((p) => ({
      label: p.name, value: p.input_tokens + p.output_tokens,
      text: fmtNum(p.input_tokens + p.output_tokens) + " · " + p.sessions + " sess",
      title: p.name + ": " + p.tool_calls + " tool calls",
    }));
    const models = (u.per_model || []).map((m) => ({
      label: m.model, value: m.input_tokens + m.output_tokens,
      text: fmtNum(m.input_tokens + m.output_tokens) + (m.cost_usd ? " · $" + m.cost_usd.toFixed(2) : " · free"),
    }));
    const kb = u.kanban || {};
    return h(Panel, { title: "Team Usage · last " + u.days + " days", extra: h("span", { className: "hcc-muted-note" }, "from each profile's state.db") }, [
      h("div", { className: "hcc-kpis", key: "k" }, [
        h(Kpi, { key: "s", value: fmtNum(t.sessions), label: "Sessions" }),
        h(Kpi, { key: "i", value: fmtNum(t.input_tokens), label: "Input tokens" }),
        h(Kpi, { key: "o", value: fmtNum(t.output_tokens), label: "Output tokens" }),
        h(Kpi, { key: "c", value: "$" + cost.toFixed(2), label: t.cost_actual_usd ? "Spend (actual)" : "Spend (est.)" }),
        h(Kpi, { key: "tc", value: fmtNum(t.tool_calls), label: "Tool calls" }),
      ]),
      h("div", { className: "hcc-usage-grid", key: "g" }, [
        h("div", { key: "d" }, [h("h3", { key: "h" }, "Tokens per day"), h(DayBars, { key: "b", days: u.per_day })]),
        h("div", { key: "w" }, [h("h3", { key: "h" }, "Workload by agent"), workload.length ? h(HBars, { key: "b", rows: workload }) : h("div", { className: "hcc-empty", key: "e" }, "No agent activity.")]),
        h("div", { key: "m" }, [h("h3", { key: "h" }, "Models"), models.length ? h(HBars, { key: "b", rows: models }) : h("div", { className: "hcc-empty", key: "e" }, "No model data.")]),
        h("div", { key: "s" }, [h("h3", { key: "h" }, "Task success (Kanban)"),
          kb.available && kb.by_profile.length
            ? h("div", { className: "hcc-succ", key: "b" }, kb.by_profile.map((b) => h("div", { className: "hcc-succ-row", key: b.profile }, [
                h("span", { key: "p" }, b.profile),
                h("span", { key: "r" }, b.runs + " runs"),
                h(Pill, { key: "x", value: b.success_rate == null ? "unknown" : b.success_rate >= 80 ? "ok" : "degraded", label: b.success_rate == null ? "n/a" : b.success_rate + "%" }),
              ])))
            : h("div", { className: "hcc-empty", key: "e" }, "No Kanban runs yet."),
        ]),
      ]),
    ]);
  }

  function CommandCenter() {
    const [usage, setUsage] = useState(null);
    const [heat, setHeat] = useState(null);
    const [heatAgent, setHeatAgent] = useState("");
    const [models, setModels] = useState([]);
    const loadHeat = useCallback(async function (agent) {
      try { setHeat(await fetchJSON(API + "/heatmap?days=14&agent=" + encodeURIComponent(agent || ""))); } catch (err) { /* optional */ }
    }, []);
    const loadModels = useCallback(async function () {
      try { const m = await fetchJSON(API + "/models"); setModels(m.profiles || []); } catch (err) { /* optional */ }
    }, []);
    const changeModel = useCallback(async function (name, model) {
      const r = await fetchJSON(API + "/profiles/" + encodeURIComponent(name) + "/model", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model }),
      });
      loadModels();
      return r;
    }, [loadModels]);
    useEffect(function () { loadHeat(heatAgent); }, [heatAgent, loadHeat]);
    useEffect(function () { loadModels(); const t = setInterval(function () { loadHeat(heatAgent); }, 120000); return function () { clearInterval(t); }; }, [heatAgent, loadHeat, loadModels]);
    const [status, setStatus] = useState(null);
    const [events, setEvents] = useState([]);
    const [error, setError] = useState("");
    const [now, setNow] = useState(new Date());
    const mounted = useRef(true);

    const [live, setLive] = useState(false);
    const liveRef = useRef(false);
    const loadedEvents = useRef(false);

    const load = useCallback(async function () {
      try {
        const skipEvents = liveRef.current && loadedEvents.current;
        const [s, e] = await Promise.all([fetchJSON(API + "/status"), skipEvents ? Promise.resolve(null) : fetchJSON(API + "/events")]);
        if (!mounted.current) return;
        setStatus(s);
        if (e) { setEvents(e.events || []); loadedEvents.current = true; }
        setError("");
      } catch (err) {
        if (mounted.current) setError(err && err.message ? err.message : String(err));
      }
    }, []);

    const loadUsage = useCallback(async function () {
      try {
        const u = await fetchJSON(API + "/usage?days=7");
        if (mounted.current) setUsage(u);
      } catch (err) { /* keep last good usage */ }
    }, []);

    useEffect(function () {
      if (!window.EventSource) return undefined;
      let es = null;
      try {
        es = new EventSource(API + "/stream");
        es.onopen = function () { liveRef.current = true; setLive(true); };
        es.onmessage = function (m) {
          let ev = null;
          try { ev = JSON.parse(m.data); } catch (err) { return; }
          if (!ev || (ev.type !== "log" && ev.type !== "team")) return;
          setEvents(function (prev) {
            return [{ timestamp: ev.timestamp, level: ev.level, source: ev.source, message: ev.message }].concat(prev).slice(0, 60);
          });
        };
        es.onerror = function () { liveRef.current = false; setLive(false); };
      } catch (err) { liveRef.current = false; }
      return function () { liveRef.current = false; if (es) es.close(); };
    }, []);

    useEffect(function () {
      mounted.current = true;
      load();
      loadUsage();
      const usageTimer = setInterval(loadUsage, 60000);
      const statusTimer = setInterval(load, 6000);
      const clockTimer = setInterval(() => setNow(new Date()), 1000);
      return function () {
        mounted.current = false;
        clearInterval(statusTimer);
        clearInterval(usageTimer);
        clearInterval(clockTimer);
      };
    }, [load, loadUsage]);

    if (!status && !error) {
      return h("div", { className: "hcc-shell" }, h("div", { className: "hcc-empty" }, "Connecting to Hermes…"));
    }

    return h("div", { className: "hcc-shell" }, [
      h("div", { className: "hcc-panel hcc-topbar", key: "top" }, [
        h("div", { className: "hcc-brand", key: "b" }, [
          h("div", { className: "hcc-brand-mark", key: "m" }, "H"),
          h("div", { key: "t" }, [
            h("h1", { key: "h" }, "HERMES COMMAND CENTER"),
            h("small", { key: "s" }, "System Status: " + (status && status.gateway.running ? "OPTIMAL" : "DEGRADED")),
          ]),
        ]),
        h("div", { className: "hcc-topbar-right", key: "r" }, [
          h("span", { className: "hcc-clock", key: "c" }, now.toLocaleString()),
          h("span", { className: "hcc-status-chip", key: "chip" }, [h("span", { className: "hcc-live-dot", key: "d" }), " LIVE"]),
        ]),
      ]),
      error ? h("div", { className: "hcc-error-banner", key: "err" }, error) : null,
      h("div", { className: "hcc-grid hcc-grid-hero", key: "hero" }, [
        h(Panel, { title: "AI Core", key: "core" }, h(AICore, { status })),
        h(AICoreOverview, { key: "overview", status }),
      ]),
      h("div", { className: "hcc-grid hcc-grid-2", key: "row1" }, [
        h(LiveFeed, { key: "feed", events, live }),
        h(Profiles, { key: "profiles", profiles: status && status.profiles, models, onModel: changeModel }),
      ]),
      h("div", { className: "hcc-grid hcc-grid-3", key: "row2" }, [
        h(SystemMonitor, { key: "sys", system: status && status.system }),
        h(ProviderStatus, { key: "prov", profiles: status && status.profiles }),
        h(ChannelStatus, { key: "chan", platforms: status && status.platforms }),
      ]),
      h(UsagePanel, { key: "usage", usage }),
      h(HeatMap, { key: "heat", heat, agent: heatAgent, onAgent: setHeatAgent }),
      h(ToolsAndSkills, { key: "tools", ...(status || {}) }),
      h(QuickCommands, { key: "cmds", onRefresh: load }),
      h("div", { className: "hcc-footer", key: "foot" }, "Hermes VPS · " + (status && status.gateway.code_version || "")),
    ]);
  }


  /* ==================================================================
     JARVIS: chat + voice engine, orb, and the home page.
     Talks to Gideon (the default profile) over the host's own chat
     connection, listens with the host's local speech-to-text, speaks with
     this plugin's /jarvis/speak (free Edge voice). Every approval request is
     answered only with "approve once" or "deny", never a standing permission.
     ================================================================== */
  const J_STAGES = ["Understand", "Plan", "Execute", "Verify", "Report"];
  const J_WORDS = [["listening", "LISTENING"], ["thinking", "THINKING"], ["coordinating", "COORDINATING"], ["executing", "EXECUTING"], ["speaking", "SPEAKING"]];
  const VOICE_HINT = "[Spoken conversation through the Jarvis dashboard. Reply in one to three short plain sentences with no markdown, tables or emoji. Use the live facts below when they answer the question. Answer from what you already know whenever you can, run at most one tool, and if you still cannot find something say so in one short sentence. If the full answer is long, give a short spoken summary and say the detail is on screen.]\n\n";

  function jAgo(iso) {
    if (!iso) return "";
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 60) return s + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }

  function jIn(iso) {
    if (!iso) return "unknown";
    const s = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
    if (s <= 0) return "due now";
    if (s < 3600) return "in " + Math.max(1, Math.round(s / 60)) + " min";
    if (s < 86400) return "in " + Math.round(s / 3600) + " h";
    return "in " + Math.round(s / 86400) + " d";
  }
  function humanCron(expr) {
    const m = String(expr || "").trim().match(/^(\d{1,2}) (\d{1,2}) \* \* (\*|1-5|0,6|[0-6])$/);
    if (!m) return String(expr || "");
    const hhmm = String(m[2]).padStart(2, "0") + ":" + String(m[1]).padStart(2, "0") + " UTC";
    const dow = m[3] === "*" ? "Every day" : m[3] === "1-5" ? "Weekdays" : m[3] === "0,6" ? "Weekends" : ["Sundays", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays"][parseInt(m[3], 10)];
    return dow + " at " + hhmm;
  }

  function jChunks(text) {
    const parts = String(text || "").split(/(?<=[.!?])\s+/).filter(Boolean);
    const out = [];
    let cur = "";
    parts.forEach(function (p) {
      if ((cur + " " + p).trim().length > 240 && cur) { out.push(cur.trim()); cur = p; } else { cur = (cur + " " + p).trim(); }
    });
    if (cur) out.push(cur.trim());
    return out.slice(0, 4);
  }

  function blobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      const fr = new FileReader();
      fr.onload = function () { resolve(fr.result); };
      fr.onerror = reject;
      fr.readAsDataURL(blob);
    });
  }

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

  const JV_HERO = "data:image/webp;base64,<IMAGE_OMITTED_SEE_assets>";
  const JV_LOGO = "data:image/webp;base64,<IMAGE_OMITTED_SEE_assets>";

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

  function jWord(phase, tool) {
    if (phase === "listening") return "listening";
    if (phase === "thinking" || phase === "transcribing") return "thinking";
    if (phase === "working") return /kanban|delegat|task/i.test(tool || "") ? "coordinating" : "executing";
    if (phase === "reporting") return "thinking";
    if (phase === "speaking") return "speaking";
    return "";
  }

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

  function JarvisStage(props) {
    const jv = props.jv;
    const [text, setText] = useState("");
    const [showVoice, setShowVoice] = useState(false);
    const logRef = useRef(null);
    useEffect(function () { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [jv.messages.length, jv.phase]);
    const word = jWord(jv.phase, jv.tool);
    const status = { idle: "Standing by. Tap the mic to talk, or hold it.", listening: jv.tapRec ? "Listening… pause when you finish, or tap the mic to send." : "Listening… release to send.", arming: "Getting the microphone ready…", transcribing: "Transcribing what you said…",
      thinking: "Gideon is thinking · " + jv.elapsed + "s", working: "Working" + (jv.tool ? ": " + jv.tool : "") + " · " + jv.elapsed + "s", reporting: "Writing the answer · " + jv.elapsed + "s",
      speaking: "Speaking…", error: jv.error || "Something went wrong." }[jv.phase] || "";
    const shownErr = jv.error && jv.phase === "idle";   // an error raised while idle (blocked mic, blocked sound) must still be visible
    const statusText = shownErr ? jv.error : status;
    const statusPhase = shownErr ? "error" : jv.phase;
    const send = function () { const t = text.trim(); if (t) { jv.submit(t); setText(""); } };
    const busy = jv.phase === "thinking" || jv.phase === "working" || jv.phase === "reporting";
    const mic = { onPointerDown: function (e) { e.preventDefault(); jv.micDown(); }, onPointerUp: function () { jv.micUp(); }, onPointerCancel: function () { jv.micUp(); }, onContextMenu: function (e) { e.preventDefault(); } };
    return h("section", { className: "hcc-panel hcc-stage" }, [
      !window.isSecureContext ? h("div", { className: "hcc-note", key: "ins" }, ["You opened Jarvis over plain http, so the browser hides the microphone. ", h("a", { href: SECURE_URL, style: { color: "#fbbf24", fontWeight: 700 } }, "Open the secure https address"), " and it will work."]) : null,
      jv.diag ? h("pre", { className: "hcc-diag", key: "dg", onClick: jv.clearDiag, title: "Tap to close" }, jv.diag) : null,
      h("div", { className: "hcc-stage-main", key: "m" }, [
        h("ul", { className: "hcc-words", key: "w" }, J_WORDS.map(function (w) { return h("li", { key: w[0], "data-on": String(word === w[0]) }, w[1]); })),
        h("div", { className: "hcc-orb-wrap", key: "o", "data-phase": jv.phase }, [
          h("img", { key: "im", className: "hcc-hero-img", src: JV_HERO, alt: "Jarvis", draggable: false }),
          h(JarvisOrb, { key: "orb", phase: jv.phase, levelRef: jv.levelRef }),
          h("button", Object.assign({ key: "mic", className: "hcc-mic", "data-on": String(jv.phase === "listening"), "aria-label": "Hold to talk", title: "Hold to talk (or hold Space)" }, mic), "🎙"),
        ]),
        h("div", { className: "hcc-quote", key: "q" }, ["“ Ideas", h("br", { key: "b1" }), "Systems", h("br", { key: "b2" }), "Impact ”"]),
      ]),
      h("div", { className: "hcc-stage-status", key: "st", "data-phase": statusPhase, role: "status" }, statusText),
      h("ol", { className: "hcc-pipeline", key: "pl" }, J_STAGES.map(function (s, i) { return h("li", { key: s, "data-on": String(jv.stage === i && busy), "data-done": String(jv.stage > i || (jv.stage >= 0 && !busy && jv.phase !== "error")) }, s); })),
      jv.approval ? h("div", { className: "hcc-approval", key: "ap", role: "alertdialog" }, [
        h("strong", { key: "t" }, "Gideon needs your yes"),
        h("code", { key: "c" }, jv.approval.command),
        jv.approval.why ? h("span", { key: "w", className: "hcc-muted-note" }, jv.approval.why) : null,
        h("div", { key: "b", className: "hcc-voice-actions" }, [
          h("button", { key: "y", className: "hcc-btn2 hcc-btn2-primary", onClick: function () { jv.respondApproval("once"); } }, "Approve once"),
          h("button", { key: "n", className: "hcc-btn2", onClick: function () { jv.respondApproval("deny"); } }, "Deny"),
        ]),
      ]) : null,
      h("div", { className: "hcc-log", key: "lg", ref: logRef }, (jv.messages.length || jv.partial) ? jv.messages.map(function (m, i) {
        return h("div", { key: i, className: "hcc-msg2", "data-role": m.role }, [h("small", { key: "r" }, m.role === "user" ? "You" : m.role === "assistant" ? "Jarvis" : "System"), h("p", { key: "t" }, m.text), m.role === "assistant" ? h("button", { key: "hr", className: "hcc-hear", onClick: function () { jv.speakNow(m.text); } }, "🔊 Hear it") : null]);
      }).concat(jv.partial ? [h("div", { key: "live", className: "hcc-msg2", "data-role": "assistant" }, [h("small", { key: "r" }, "Jarvis"), h("p", { key: "t" }, jv.partial + " ▌")])] : []) : h("div", { className: "hcc-empty" }, "Say or type something. Try: “What is on my plate today?”")),
      h("div", { className: "hcc-cmdbar", key: "cb" }, [
        h("input", { key: "i", id: "jv-input", value: text, placeholder: "Speak naturally, or type here. Press / to focus.", onChange: function (e) { setText(e.target.value); },
          onKeyDown: function (e) { if (e.key === "Enter") { e.preventDefault(); send(); } e.stopPropagation(); }, disabled: busy || jv.phase === "listening" }),
        busy ? h("button", { key: "x", className: "hcc-btn2", onClick: jv.interrupt }, "Stop") : h("button", { key: "s", className: "hcc-btn2 hcc-btn2-primary", onClick: send, disabled: !text.trim() }, "Send"),
        h("button", Object.assign({ key: "m2", className: "hcc-btn2 hcc-mic-inline", title: "Hold to talk" }, mic), "🎙 Talk"),
        h("button", { key: "sp", className: "hcc-btn2", "data-on": String(jv.ttsOn), onClick: function () { if (jv.ttsOn) jv.stopAll(); jv.setTtsOn(!jv.ttsOn); }, title: "Speak replies aloud" }, jv.ttsOn ? "🔊 On" : "🔇 Off"),
        h("button", { key: "g", className: "hcc-btn2", onClick: function () { setShowVoice(!showVoice); }, title: "Voice settings" }, "⚙ Voice"),
        h("button", { key: "st", className: "hcc-btn2", onClick: function () { jv.soundTest(); }, title: "Check that this device can play sound" }, "🔈 Test sound"),
      ]),
      showVoice ? h(VoiceSettings, { key: "vs", jv: jv }) : null,
      h("div", { className: "hcc-muted-note", key: "hint" }, "Tap the mic (it stops when you pause), or hold it, or hold Space · / to type · Esc to stop · 1 to 6 for pages"),
    ]);
  }

  // ---------- home page panels ----------
  function Dot(props) { return h("i", { className: "hcc-dot", "data-s": props.s || "info" }); }

  function EnvPanel(props) {
    const rows = props.rows;
    return h(Panel, { title: "Hermes Environment" }, rows ? h("ul", { className: "hcc-env" }, rows.map(function (r) {
      return h("li", { key: r.key }, [h(Dot, { key: "d", s: r.status }), h("span", { key: "l", className: "hcc-env-l" }, r.label), h("span", { key: "v", className: "hcc-env-v" }, r.detail)]);
    })) : h("div", { className: "hcc-empty" }, "Checking…"));
  }

  function ProfilesMini(props) {
    const ps = props.profiles || [];
    return h(Panel, { title: "Multiplexed Profiles", extra: h("span", { className: "hcc-muted-note" }, ps.length + " served") }, h("ul", { className: "hcc-env" }, ps.map(function (p, i) {
      return h("li", { key: p.name }, [h("span", { key: "n", className: "hcc-env-n" }, String(i + 1).padStart(2, "0")), h("span", { key: "l", className: "hcc-env-l" }, p.name),
        h("span", { key: "v", className: "hcc-env-v" }, (p.model || "").split("/").pop()), h(Dot, { key: "d", s: p.served_by_multiplex ? "ok" : "info" })]);
    })));
  }

  function MissionCard(props) {
    const m = props.mission;
    if (!m) return h(Panel, { title: "Primary Mission" }, h("div", { className: "hcc-empty" }, "Loading…"));
    const p = m.primary;
    if (!p) return h(Panel, { title: "Primary Mission" }, h("div", { className: "hcc-empty" }, "No Product Factory project yet."));
    return h(Panel, { title: "Primary Mission", extra: h("span", { className: "hcc-status-chip" }, [h("span", { className: "hcc-live-dot", key: "d" }), m.pinned ? " PINNED" : " LATEST"]) }, [
      h("div", { className: "hcc-mission-head", key: "h" }, [h("strong", { key: "n" }, p.name), h("small", { key: "t" }, (p.type || "").replace(/_/g, " "))]),
      h("div", { className: "hcc-muted-note", key: "cm" }, "Current milestone"),
      h("div", { className: "hcc-mission-ms", key: "ms" }, [h("span", { key: "a" }, p.milestone), h("b", { key: "b" }, p.progress + "%")]),
      h("div", { className: "hcc-bar", key: "bar" }, h("i", { style: { width: p.progress + "%" } })),
      h("ul", { className: "hcc-steps", key: "s" }, (p.steps || []).map(function (s) { return h("li", { key: s.name, "data-s": s.status }, [h("i", { key: "i" }, s.status === "COMPLETE" ? "✔" : s.status === "ACTIVE" ? "◉" : "○"), s.name]); })),
      h("select", { key: "sel", className: "hcc-select", value: m.pinned ? p.id : "", onChange: function (e) { props.onPin(e.target.value); }, "aria-label": "Choose the primary mission" },
        [h("option", { key: "_", value: "" }, m.pinned ? "Follow the latest project" : "Pin a different project…")].concat((m.projects || []).map(function (x) { return h("option", { key: x.id, value: x.id }, x.name); }))),
    ]);
  }

  function SpecialistTiles(props) {
    const steps = (props.mission && props.mission.primary && props.mission.primary.steps) || [];
    const active = steps.filter(function (s) { return s.status === "ACTIVE"; }).length;
    return h(Panel, { title: "Active Specialist Agents", extra: h("span", { className: "hcc-muted-note" }, active + " working") },
      steps.length ? h("div", { className: "hcc-spec" }, steps.map(function (s) { return h("div", { key: s.name, className: "hcc-spec-t", "data-s": s.status }, [h(Dot, { key: "d", s: s.status === "COMPLETE" ? "ok" : s.status === "ACTIVE" ? "warn" : "info" }), h("span", { key: "n" }, s.name.replace(" Agent", ""))]); }))
        : h("div", { className: "hcc-empty" }, "Specialists appear when a project runs."));
  }

  function TokenMini(props) {
    const u = props.usage;
    if (!u) return h(Panel, { title: "Token Usage" }, h("div", { className: "hcc-empty" }, "Loading…"));
    const t = u.totals || {};
    const rows = (u.per_model || []).slice(0, 4).map(function (m) { return { label: m.model.split("/").pop().replace(":free", ""), value: m.input_tokens + m.output_tokens, text: fmtNum(m.input_tokens + m.output_tokens) }; });
    return h(Panel, { title: "Token Usage", extra: h("span", { className: "hcc-muted-note" }, "last " + u.days + " day") }, [
      h("div", { className: "hcc-big", key: "b" }, [fmtNum(t.input_tokens + t.output_tokens), h("small", { key: "s" }, " tokens · " + fmtNum(t.sessions) + " sessions")]),
      rows.length ? h(HBars, { key: "h", rows: rows }) : h("div", { className: "hcc-empty", key: "e" }, "No usage yet."),
    ]);
  }

  function HealthMini(props) {
    const hl = props.health;
    if (!hl) return h(Panel, { title: "System Health" }, h("div", { className: "hcc-empty" }, "Checking…"));
    const pct = hl.score, C = 2 * Math.PI * 40, off = C - (pct / 100) * C;
    const col = pct >= 90 ? "#4ade80" : pct >= 70 ? "#fbbf24" : "#fb7185";
    return h(Panel, { title: "System Health" }, h("div", { className: "hcc-health" }, [
      h("svg", { key: "g", width: 96, height: 96, viewBox: "0 0 96 96", role: "img", "aria-label": "Health " + pct + " percent" }, [
        h("circle", { key: "t", cx: 48, cy: 48, r: 40, fill: "none", stroke: "rgba(255,255,255,.08)", strokeWidth: 8 }),
        h("circle", { key: "v", cx: 48, cy: 48, r: 40, fill: "none", stroke: col, strokeWidth: 8, strokeLinecap: "round", strokeDasharray: C, strokeDashoffset: off, transform: "rotate(-90 48 48)" }),
        h("text", { key: "x", x: 48, y: 53, textAnchor: "middle", fill: "#eaf6ff", fontSize: 20, fontWeight: 800 }, pct + "%"),
      ]),
      h("ul", { key: "l", className: "hcc-env hcc-health-l" }, hl.items.map(function (i) { return h("li", { key: i.name, title: i.detail }, [h(Dot, { key: "d", s: i.ok ? "ok" : "down" }), h("span", { key: "n", className: "hcc-env-l" }, i.name), h("span", { key: "v", className: "hcc-env-v" }, i.detail)]); })),
    ]));
  }

  function TasksMini(props) {
    const t = props.tasks;
    if (!t) return h(Panel, { title: "Active Tasks" }, h("div", { className: "hcc-empty" }, "Loading…"));
    const live = (t.counts.running || 0) + (t.counts.ready || 0) + (t.counts.blocked || 0);
    return h(Panel, { title: "Active Tasks", extra: h("span", { className: "hcc-count" }, live) }, t.tasks.length ? h("ul", { className: "hcc-env" }, t.tasks.slice(0, 5).map(function (k) {
      return h("li", { key: k.id }, [h(Dot, { key: "d", s: k.status === "running" ? "warn" : k.status === "blocked" ? "down" : k.status === "done" ? "ok" : "info" }),
        h("span", { key: "l", className: "hcc-env-l" }, k.title), h("span", { key: "v", className: "hcc-env-v" }, k.agent + (k.elapsed != null ? " · " + k.elapsed + "s" : " · " + k.status))]);
    })) : h("div", { className: "hcc-empty" }, "Nothing in progress. Ask Jarvis to delegate something."));
  }

  function ToolsGrid(props) {
    const t = props.tools;
    return h(Panel, { title: "Connected Tools", extra: h("button", { className: "hcc-btn2", onClick: props.onRefresh }, "Recheck") },
      t ? h("div", { className: "hcc-tools" }, t.tiles.map(function (x) { return h("div", { key: x.key, className: "hcc-tool", "data-s": x.status, title: x.detail }, [h(Dot, { key: "d", s: x.status }), h("strong", { key: "l" }, x.label), h("small", { key: "s" }, x.kind === "live" ? "live check" : x.kind === "scope" ? "login scope" : "configured")]); }))
        : h("div", { className: "hcc-empty" }, "Checking each tool…"));
  }

  function useJarvisData() {
    const [d, setD] = useState({});
    const [events, setEvents] = useState([]);
    const [live, setLive] = useState(false);
    const alive = useRef(true);
    const get = function (key, url, opts) { return fetchJSON(url, opts).then(function (v) { if (alive.current) setD(function (p) { return Object.assign({}, p, { [key]: v }); }); }).catch(function () { /* keep last */ }); };
    const loadFast = useCallback(function () { get("env", API + "/jarvis/env"); get("health", API + "/jarvis/health"); get("mission", API + "/jarvis/mission"); get("tasks", API + "/jarvis/tasks"); get("status", API + "/status"); }, []);
    const loadTools = useCallback(function (force) { get("tools", API + "/jarvis/tools" + (force ? "?refresh=1" : "")); }, []);
    useEffect(function () {
      alive.current = true;
      loadFast(); loadTools(false); get("usage", API + "/usage?days=1");
      fetchJSON(API + "/events").then(function (e) { if (alive.current) setEvents(e.events || []); }).catch(function () { /* ignore */ });
      const a = setInterval(loadFast, 20000), b = setInterval(function () { loadTools(false); }, 300000), c = setInterval(function () { get("usage", API + "/usage?days=1"); }, 60000);
      let es = null;
      try {
        es = new EventSource(API + "/stream");
        es.onopen = function () { setLive(true); };
        es.onmessage = function (m) { let ev = null; try { ev = JSON.parse(m.data); } catch (e) { return; } if (ev && (ev.type === "log" || ev.type === "team")) { setEvents(function (p) { return [{ timestamp: ev.timestamp, level: ev.level, source: ev.source, message: ev.message }].concat(p).slice(0, 40); }); if (ev.type === "team") { loadFast(); } } };
        es.onerror = function () { setLive(false); };
      } catch (e) { /* polling only */ }
      return function () { alive.current = false; clearInterval(a); clearInterval(b); clearInterval(c); if (es) es.close(); };
    }, []);
    return { d: d, events: events, live: live, reloadTools: function () { loadTools(true); }, reloadFast: loadFast };
  }

  function JarvisPage(props) {
    const jv = props.jv;
    useEffect(function () { jv.warm(); }, []);
    const data = useJarvisData();
    const d = data.d;
    const pin = function (id) {
      fetchJSON(API + "/jarvis/mission", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: id }) }).then(function (m) { data.reloadFast(); }).catch(function () { /* ignore */ });
    };
    return h("div", { className: "hcc-shell hcc-jv" }, [
      h("div", { className: "hcc-jv-col hcc-jv-left", key: "l" }, [h(EnvPanel, { key: "e", rows: d.env && d.env.rows }), h(ProfilesMini, { key: "p", profiles: d.status && d.status.profiles })]),
      h("div", { className: "hcc-jv-col hcc-jv-center", key: "c" }, [h(JarvisStage, { key: "s", jv: jv })]),
      h("div", { className: "hcc-jv-col hcc-jv-right", key: "r" }, [h(MissionCard, { key: "m", mission: d.mission, onPin: pin }), h(SpecialistTiles, { key: "s", mission: d.mission })]),
      h("div", { className: "hcc-jv-bottom", key: "b" }, [
        h(TokenMini, { key: "t", usage: d.usage }),
        h(LiveFeed, { key: "f", events: data.events.slice(0, 8), live: data.live }),
        h(HealthMini, { key: "h", health: d.health }),
        h(TasksMini, { key: "k", tasks: d.tasks }),
        h(ToolsGrid, { key: "o", tools: d.tools, onRefresh: data.reloadTools }),
      ]),
    ]);
  }


  /* ---------------- Schedule (the host's own cron API) ---------------- */
  function ConfirmBox(props) {
    return h("div", null, [
      h("div", { className: "hcc-backdrop", key: "b", onClick: props.onNo }),
      h("div", { className: "hcc-dialog", key: "d", role: "alertdialog" }, [
        h("strong", { key: "t" }, props.title),
        h("p", { key: "p" }, props.body),
        h("div", { className: "hcc-voice-actions", key: "a" }, [
          h("button", { key: "n", className: "hcc-btn2", onClick: props.onNo }, "Cancel"),
          h("button", { key: "y", className: "hcc-btn2 " + (props.danger ? "hcc-btn2-danger" : "hcc-btn2-primary"), onClick: props.onYes }, props.yes),
        ]),
      ]),
    ]);
  }

  function SchedulePage() {
    const [jobs, setJobs] = useState(null);
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState("");
    const [confirm, setConfirm] = useState(null);
    const load = useCallback(function () {
      return fetchJSON("/api/cron/jobs").then(function (d) { setJobs(Array.isArray(d) ? d : (d.jobs || [])); }).catch(function (e) { setNote((e && e.message) || "Could not load the schedule."); });
    }, []);
    useEffect(function () { load(); const t = setInterval(load, 30000); return function () { clearInterval(t); }; }, [load]);
    const act = function (job, verb) {
      setConfirm(null); setBusy(job.id + verb); setNote("");
      const opts = verb === "delete" ? { method: "DELETE" } : { method: "POST" };
      const url = verb === "delete" ? "/api/cron/jobs/" + job.id : "/api/cron/jobs/" + job.id + "/" + verb;
      fetchJSON(url, opts).then(function () { setNote(verb === "trigger" ? "Started: " + job.name + ". It will deliver when it finishes." : verb === "delete" ? "Deleted: " + job.name : (verb === "pause" ? "Paused: " : "Resumed: ") + job.name); return load(); })
        .catch(function (e) { setNote((e && e.message) || "That did not work."); }).then(function () { setBusy(""); });
    };
    const ask = function (job, verb) {
      if (verb === "trigger") setConfirm({ job: job, verb: verb, title: "Run “" + job.name + "” now?", body: "It runs immediately and delivers to " + (job.deliver || "its usual places") + ".", yes: "Run now" });
      else if (verb === "delete") setConfirm({ job: job, verb: verb, title: "Delete “" + job.name + "”?", body: "This removes the scheduled job. A daily backup of the schedule exists, but this cannot be undone here.", yes: "Delete", danger: true });
      else act(job, verb);
    };
    return h("div", { className: "hcc-shell" }, [
      h(Panel, { key: "p", title: "Schedule", extra: h("span", { className: "hcc-muted-note" }, "the same jobs Hermes runs (times are UTC)") }, [
        note ? h("div", { className: "hcc-note", key: "n" }, note) : null,
        jobs == null ? h("div", { className: "hcc-empty", key: "l" }, "Loading the schedule…") : !jobs.length ? h("div", { className: "hcc-empty", key: "e" }, "No scheduled jobs.") : h("div", { className: "hcc-jobs", key: "j" }, jobs.map(function (j) {
          const paused = !j.enabled || j.state === "paused" || j.paused_at;
          return h("div", { key: j.id, className: "hcc-job", "data-paused": String(!!paused) }, [
            h("div", { className: "hcc-job-top", key: "t" }, [h("strong", { key: "n" }, j.name), h(Pill, { key: "s", value: paused ? "paused" : (j.last_status === "ok" || !j.last_status ? "ok" : "degraded"), label: paused ? "PAUSED" : (j.last_status || "new").toUpperCase() })]),
            h("div", { className: "hcc-job-meta", key: "m" }, [h("span", { key: "a" }, "Schedule: " + humanCron(j.schedule_display || (j.schedule && j.schedule.expr) || "")), h("span", { key: "b" }, "Next: " + (paused ? "not scheduled" : (j.next_run_at ? jIn(j.next_run_at) + " (" + String(j.next_run_at).replace("T", " ").slice(0, 16) + " UTC)" : "unknown"))),
              h("span", { key: "c" }, "Last: " + (j.last_run_at ? jAgo(j.last_run_at) : "never")), h("span", { key: "d" }, "Delivers to: " + (Array.isArray(j.deliver) ? j.deliver.join(", ") : j.deliver || "local"))]),
            j.last_error ? h("div", { className: "hcc-muted-note", key: "er" }, "Last error: " + String(j.last_error).slice(0, 140)) : null,
            h("div", { className: "hcc-voice-actions", key: "a" }, [
              h("button", { key: "r", className: "hcc-btn2 hcc-btn2-primary", disabled: !!busy, onClick: function () { ask(j, "trigger"); } }, busy === j.id + "trigger" ? "Starting…" : "Run now"),
              h("button", { key: "p", className: "hcc-btn2", disabled: !!busy, onClick: function () { ask(j, paused ? "resume" : "pause"); } }, paused ? "Resume" : "Pause"),
              h("button", { key: "d", className: "hcc-btn2", disabled: !!busy, onClick: function () { ask(j, "delete"); } }, "Delete"),
            ]),
          ]);
        })),
      ]),
      confirm ? h(ConfirmBox, { key: "c", title: confirm.title, body: confirm.body, yes: confirm.yes, danger: confirm.danger, onNo: function () { setConfirm(null); }, onYes: function () { act(confirm.job, confirm.verb); } }) : null,
    ]);
  }

  /* ---------------- Threads ---------------- */
  function ThreadsPage() {
    const [threads, setThreads] = useState(null);
    const [sel, setSel] = useState(null);
    const [msgs, setMsgs] = useState(null);
    const load = useCallback(function () { return fetchJSON(API + "/jarvis/threads").then(function (d) { setThreads(d.threads || []); }).catch(function () { setThreads([]); }); }, []);
    useEffect(function () { load(); const t = setInterval(load, 30000); return function () { clearInterval(t); }; }, [load]);
    useEffect(function () {
      if (!sel) return;
      setMsgs(null);
      fetchJSON(API + "/jarvis/threads/" + encodeURIComponent(sel.profile) + "/" + encodeURIComponent(sel.session_id)).then(function (d) { setMsgs(d.messages || []); }).catch(function () { setMsgs([]); });
    }, [sel && sel.session_id]);
    return h("div", { className: "hcc-shell hcc-threads" }, [
      h(Panel, { key: "l", title: "Threads", extra: h("span", { className: "hcc-muted-note" }, "Telegram topics and Slack, newest first") }, threads == null ? h("div", { className: "hcc-empty" }, "Loading…") : !threads.length ? h("div", { className: "hcc-empty" }, "No conversations yet.") :
        h("ul", { className: "hcc-thread-list" }, threads.map(function (t) {
          return h("li", { key: t.key, "data-on": String(!!sel && sel.key === t.key), onClick: function () { setSel(t); } }, [
            h("div", { key: "a", className: "hcc-thread-top" }, [h("strong", { key: "n" }, t.label), h("small", { key: "w" }, jAgo(t.last_activity_at))]),
            h("small", { key: "g", className: "hcc-thread-agent" }, agentTag(t.agent) + " · " + t.platform + " · " + t.sessions + " session" + (t.sessions === 1 ? "" : "s")),
            t.snippet ? h("span", { key: "s", className: "hcc-thread-snip" }, (t.last_role === "user" ? "You: " : "") + t.snippet) : null,
          ]);
        }))),
      h(Panel, { key: "r", title: sel ? sel.label : "Conversation", extra: sel ? h("button", { className: "hcc-btn2", onClick: function () { setSel(null); } }, "Close") : null },
        !sel ? h("div", { className: "hcc-empty" }, "Pick a thread to read the recent messages.") : msgs == null ? h("div", { className: "hcc-empty" }, "Loading messages…") : !msgs.length ? h("div", { className: "hcc-empty" }, "No readable messages.") :
          h("div", { className: "hcc-bubbles" }, msgs.map(function (m, i) { return h("div", { key: i, className: "hcc-bubble", "data-role": m.role }, [h("small", { key: "r" }, (m.role === "user" ? "You" : agentTag(sel.agent)) + " · " + jAgo(m.at)), h("p", { key: "t" }, m.text)]); }))),
    ]);
  }
  function agentTag(a) {
    return ({ default: "Gideon", scout: "Scout", scribe: "Scribe", socialmediaagent: "Reach", "youtube-production-agent": "Production", "product-factory": "Product Factory" })[a] || a;
  }

  /* ---------------- Comms (read-only) ---------------- */
  function CommsPage() {
    const [d, setD] = useState(null);
    const [busy, setBusy] = useState(false);
    const load = useCallback(function (force) {
      setBusy(true);
      return fetchJSON(API + "/jarvis/comms" + (force ? "?refresh=1" : "")).then(setD).catch(function () { setD({ mail_ok: false, calendar_ok: false, unread: [], events: [] }); }).then(function () { setBusy(false); });
    }, []);
    useEffect(function () { load(false); }, [load]);
    return h("div", { className: "hcc-shell hcc-comms" }, [
      h("div", { className: "hcc-panel hcc-readonly", key: "ro" }, [h("strong", { key: "a" }, "Read only. "), "Jarvis never sends, deletes or replies to mail, and never creates, moves or cancels calendar events, without your explicit yes each time. This page only reads."]),
      h(Panel, { key: "m", title: "Unread mail", extra: h("button", { className: "hcc-btn2", onClick: function () { load(true); }, disabled: busy }, busy ? "Reading…" : "Refresh") },
        !d ? h("div", { className: "hcc-empty" }, "Reading your inbox…") : !d.mail_ok ? h("div", { className: "hcc-empty" }, "Could not read Gmail right now.") : !d.unread.length ? h("div", { className: "hcc-empty" }, "Inbox zero. Nothing unread.") :
          h("ul", { className: "hcc-mail" }, d.unread.map(function (m, i) { return h("li", { key: i }, [h("div", { key: "t", className: "hcc-mail-top" }, [h("strong", { key: "f" }, m.from), h("small", { key: "d" }, String(m.date || "").slice(0, 22))]), h("div", { key: "s", className: "hcc-mail-sub" }, m.subject), h("span", { key: "n", className: "hcc-thread-snip" }, m.snippet)]); }))),
      h(Panel, { key: "c", title: "Next 48 hours" }, !d ? h("div", { className: "hcc-empty" }, "Reading your calendar…") : !d.calendar_ok ? h("div", { className: "hcc-empty" }, "Could not read the calendar right now.") : !d.events.length ? h("div", { className: "hcc-empty" }, "Nothing on the calendar.") :
        h("ul", { className: "hcc-mail" }, d.events.map(function (e, i) { return h("li", { key: i }, [h("strong", { key: "s" }, e.summary), h("small", { key: "t", className: "hcc-thread-snip" }, String(e.start || "").replace("T", " ").slice(0, 16) + (e.location ? " · " + e.location : ""))]); }))),
    ]);
  }

  /* ---------------- Docs (safe tiny markdown renderer, no innerHTML) ---------------- */
  function renderMd(src) {
    const lines = String(src || "").split("\n");
    const out = [];
    let i = 0, k = 0;
    const inline = function (t) {
      const parts = String(t).split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
      return parts.map(function (p, n) {
        if (p[0] === "`") return h("code", { key: n }, p.slice(1, -1));
        if (p.slice(0, 2) === "**") return h("strong", { key: n }, p.slice(2, -2));
        return p;
      });
    };
    while (i < lines.length) {
      const l = lines[i];
      if (l.startsWith("```")) { const buf = []; i++; while (i < lines.length && !lines[i].startsWith("```")) { buf.push(lines[i]); i++; } i++; out.push(h("pre", { key: k++, className: "hcc-doc-pre" }, buf.join("\n"))); continue; }
      if (/^#{1,3}\s/.test(l)) { const lvl = l.match(/^#+/)[0].length; out.push(h("h" + (lvl + 1), { key: k++, className: "hcc-doc-h" }, inline(l.replace(/^#+\s*/, "")))); i++; continue; }
      if (l.startsWith("|")) {
        const rows = [];
        while (i < lines.length && lines[i].startsWith("|")) { if (!/^\|\s*-/.test(lines[i])) rows.push(lines[i].split("|").slice(1, -1).map(function (c) { return c.trim(); })); i++; }
        out.push(h("div", { key: k++, className: "hcc-doc-table" }, h("table", null, h("tbody", null, rows.map(function (r, ri) { return h("tr", { key: ri }, r.map(function (c, ci) { return h(ri === 0 ? "th" : "td", { key: ci }, inline(c)); })); })))));
        continue;
      }
      if (/^\s*[-*]\s/.test(l)) { const items = []; while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; } out.push(h("ul", { key: k++, className: "hcc-doc-ul" }, items.map(function (t, n) { return h("li", { key: n }, inline(t)); }))); continue; }
      if (!l.trim()) { i++; continue; }
      const para = [l]; i++;
      while (i < lines.length && lines[i].trim() && !/^(#|\||```|\s*[-*]\s)/.test(lines[i])) { para.push(lines[i]); i++; }
      out.push(h("p", { key: k++, className: "hcc-doc-p" }, inline(para.join(" "))));
    }
    return out;
  }
  function DocsPage() {
    const [d, setD] = useState(null);
    useEffect(function () { fetchJSON(API + "/jarvis/docs").then(setD).catch(function () { setD({ content: "Could not load the runbook.", title: "Runbook" }); }); }, []);
    return h("div", { className: "hcc-shell" }, h(Panel, { title: d ? d.title : "Docs", extra: d && d.updated_at ? h("span", { className: "hcc-muted-note" }, "updated " + jAgo(d.updated_at)) : null },
      d ? h("div", { className: "hcc-doc" }, renderMd(d.content)) : h("div", { className: "hcc-empty" }, "Loading…")));
  }

  /* ---------------- app shell: page nav, shortcuts, one shared Jarvis ---------------- */
  const CC_PAGES = [["jarvis", "Jarvis"], ["infrastructure", "Infrastructure"], ["schedule", "Schedule"], ["threads", "Threads"], ["comms", "Comms"], ["docs", "Docs"]];
  function ccPageFromHash() {
    const m = (window.location.hash || "").match(/^#\/?([a-z]+)/);
    return m && CC_PAGES.some(function (p) { return p[0] === m[1]; }) ? m[1] : "infrastructure";
  }

  function CCApp() {
    const [page, setPage] = useState(ccPageFromHash());
    const jv = useJarvis();
    const jvRef = useRef(jv); jvRef.current = jv;
    const pageRef = useRef(page); pageRef.current = page;
    useEffect(function () {
      const onHash = function () { setPage(ccPageFromHash()); window.scrollTo(0, 0); };
      window.addEventListener("hashchange", onHash);
      return function () { window.removeEventListener("hashchange", onHash); };
    }, []);
    useEffect(function () {
      let spaceDown = false;
      const typing = function (e) { const t = e.target; return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable); };
      const down = function (e) {
        if (e.ctrlKey || e.metaKey || e.altKey || typing(e)) return;
        if (e.key === "Escape") { jvRef.current.stopAll(); return; }
        if (pageRef.current === "jarvis" && e.code === "Space" && !e.repeat) { e.preventDefault(); spaceDown = true; jvRef.current.micDown(); return; }
        if (e.key === "/" && pageRef.current === "jarvis") { const el = document.getElementById("jv-input"); if (el) { e.preventDefault(); el.focus(); } return; }
        const n = parseInt(e.key, 10);
        if (n >= 1 && n <= CC_PAGES.length) { window.location.hash = "#/" + CC_PAGES[n - 1][0]; }
      };
      const up = function (e) { if (e.code === "Space" && spaceDown) { spaceDown = false; jvRef.current.micUp(); } };
      window.addEventListener("keydown", down); window.addEventListener("keyup", up);
      return function () { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
    }, []);
    const mc = window.location.protocol + "//" + window.location.hostname + ":8443/";
    const body = page === "jarvis" ? h(JarvisPage, { jv: jv }) : page === "schedule" ? h(SchedulePage) : page === "threads" ? h(ThreadsPage) : page === "comms" ? h(CommsPage) : page === "docs" ? h(DocsPage) : h(CommandCenter);
    return h("div", null, [
      h("nav", { className: "hcc-appnav", key: "nav", "aria-label": "Command Center pages" }, [
        h("div", { className: "hcc-appnav-in", key: "in" }, [h("span", { key: "brand", className: "hcc-brand" }, [h("img", { key: "lg", src: JV_LOGO, alt: "", className: "hcc-brand-logo" }), h("span", { key: "tx", className: "hcc-brand-text" }, [h("b", { key: "b" }, "JARVIS"), h("small", { key: "s" }, "Hermes Mission Control")])])].concat(CC_PAGES.map(function (p, i) { return h("button", { key: p[0], "data-active": String(page === p[0]), onClick: function () { window.location.hash = "#/" + p[0]; }, title: "Press " + (i + 1) }, p[1]); })
          .concat([h("a", { key: "mc", className: "hcc-appnav-link", href: mc }, "Mission Control ↗")]))),
      ]),
      body,
    ]);
  }

  window.__HERMES_PLUGINS__.register("hermes-command-center", CCApp);
})();
