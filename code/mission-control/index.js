(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React, fetchJSON } = SDK;
  const h = React.createElement;
  const { useCallback, useEffect, useState, useRef } = SDK.hooks;
  const API = "/api/plugins/product-factory-mission-control";

  const ROLE_ORDER = [
    "Hermes Director", "Product Agent", "Research Agent", "Architecture Agent",
    "Lead Engineer", "Data/ML Engineer", "QA Agent", "Security Agent",
    "UI/UX Agent", "ML/AI Evaluation Agent", "Release/DevOps Agent",
  ];
  /* Fixed per-role identity color (who) — distinct from status color (what state),
     matching the multi-hue per-agent card style rather than one uniform hue. */
  const ROLE_COLOR = {
    "Hermes Director": "#38bdf8", "Product Agent": "#fb923c", "Research Agent": "#fb7185",
    "Architecture Agent": "#a78bfa", "Lead Engineer": "#2dd4bf", "Data/ML Engineer": "#fbbf24",
    "QA Agent": "#4ade80", "Security Agent": "#f87171", "UI/UX Agent": "#e879f9",
    "ML/AI Evaluation Agent": "#818cf8", "Release/DevOps Agent": "#0ea5e9",
  };
  const STATUS_COLOR = { COMPLETE: "#4ade80", ACTIVE: "#fbbf24", PENDING: "#5b7285", SKIPPED: "rgba(91,114,133,.4)" };
  /* Short labels that actually fit inside a ~68px node circle — the full label
     (e.g. "Lead Engineer", "ML/AI Evaluation Agent") is still used in the
     timeline, drawer, and native tooltip. */
  const SHORT_LABEL = {
    "Hermes Director": "HERMES", "Product Agent": "PRODUCT", "Research Agent": "RESEARCH",
    "Architecture Agent": "ARCH", "Lead Engineer": "LEAD ENG", "Data/ML Engineer": "DATA/ML",
    "QA Agent": "QA", "Security Agent": "SECURITY", "UI/UX Agent": "UI/UX",
    "ML/AI Evaluation Agent": "ML EVAL", "Release/DevOps Agent": "DEVOPS",
  };

  function cls(value) { return String(value || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-"); }
  function Pill(props) { return h("span", { className: "pfmc-pill pfmc-" + cls(props.value) }, props.value || "UNKNOWN"); }
  function Panel(props) {
    return h("section", { className: "pfmc-panel " + (props.className || "") }, [
      h("div", { className: "pfmc-panel-head", key: "h" }, [h("h2", { key: "t" }, props.title), props.extra || null]),
      h("div", { className: "pfmc-panel-body", key: "b" }, props.children),
    ]);
  }
  function Empty(props) { return h("div", { className: "pfmc-empty" }, props.children); }

  function AgentGraph(props) {
    const roles = props.roles || [];
    const byName = {};
    roles.forEach((r) => { byName[r.name] = r; });
    const specialists = ROLE_ORDER.slice(1);
    const cx = 260, cy = 220, rOuter = 165, rNode = 34, rDirector = 44;
    const nodes = specialists.map((name, i) => {
      const angle = (i / specialists.length) * Math.PI * 2 - Math.PI / 2;
      return { name, x: cx + rOuter * Math.cos(angle), y: cy + rOuter * Math.sin(angle) };
    });
    const director = byName["Hermes Director"] || {};
    const activeName = props.currentSpecialist;
    const selected = props.selected;
    const onSelect = props.onSelect;

    function statusBadge(status, ringR, duration) {
      const c = STATUS_COLOR[status] || STATUS_COLOR.PENDING;
      // Orbits around the node's local origin (0,0) at a fixed radius — a small
      // moving indicator sweeping the ring, not a static corner dot.
      return h("g", { key: "badge", className: "pfmc-status-orbit", style: { animationDuration: duration } },
        h("circle", { cx: ringR, cy: 0, r: 6, fill: c, stroke: "#030910", strokeWidth: 2 }));
    }

    return h("div", { className: "pfmc-graph-tight pfmc-graph-fill" }, [
      h("svg", { key: "svg", viewBox: "38 6 444 434", role: "img", className: "pfmc-graph-svg" }, [
        h("g", { key: "edges" }, nodes.map((n, i) => {
          const role = byName[n.name] || {};
          const isActive = n.name === activeName;
          const idColor = ROLE_COLOR[n.name] || "#38bdf8";
          return h("line", {
            key: "e" + i, x1: cx, y1: cy, x2: n.x, y2: n.y,
            className: "pfmc-edge" + (isActive ? " pfmc-edge-active" : ""),
            style: { stroke: idColor, opacity: role.status === "SKIPPED" ? .25 : .65 },
          });
        })),
        h("g", { key: "packets" }, nodes.filter((n) => n.name === activeName).map((n, i) =>
          h("circle", { key: "pk" + i, r: 5, fill: ROLE_COLOR[n.name], className: "pfmc-node-packet", cx: (cx + n.x) / 2, cy: (cy + n.y) / 2 })
        )),
        h("g", {
          key: "director", className: "pfmc-graph-node" + (selected === "Hermes Director" ? " pfmc-node-selected" : ""),
          style: { color: ROLE_COLOR["Hermes Director"], cursor: "pointer", pointerEvents: "all" },
          onClick: () => onSelect("Hermes Director"),
        }, [
          h("title", { key: "tt" }, "Hermes Director — " + (director.status || "UNKNOWN") + ". Click for details."),
          h("circle", { key: "c", cx, cy, r: rDirector, className: "pfmc-node-ring", style: { stroke: "currentColor" }, fill: "rgba(56,189,248,.1)" }),
          h("text", { key: "t1", x: cx, y: cy - 3, style: { fontWeight: 800, fontSize: 12, fill: "#fff" } }, "HERMES"),
          h("text", { key: "t2", x: cx, y: cy + 12, className: "pfmc-node-sub" }, "DIRECTOR"),
          h("g", { key: "badgewrap", transform: "translate(" + cx + "," + cy + ")" }, statusBadge(director.status, rDirector - 4, "5s")),
        ]),
        h("g", { key: "nodes" }, nodes.map((n, i) => {
          const role = byName[n.name] || {};
          const idColor = ROLE_COLOR[n.name] || "#38bdf8";
          const fullLabel = (role.label || n.name);
          const short = SHORT_LABEL[n.name] || fullLabel.split(" ")[0].toUpperCase();
          const isActive = n.name === activeName;
          return h("g", {
            key: "n" + i, className: "pfmc-graph-node" + (selected === n.name ? " pfmc-node-selected" : "") + (isActive ? " pfmc-node-active" : ""),
            style: { color: idColor, opacity: role.status === "SKIPPED" ? .55 : 1, cursor: "pointer", pointerEvents: "all" },
            transform: "translate(" + n.x + "," + n.y + ")",
            onClick: () => onSelect(n.name),
          }, [
            h("title", { key: "tt" }, fullLabel + " — " + (role.status || "PENDING") + (role.reason ? " (" + role.reason + ")" : "") + (role.worker_used ? ". Worker: " + role.worker_used : "") + ". Click for details."),
            h("circle", { key: "c", r: rNode, className: "pfmc-node-ring", style: { stroke: "currentColor" }, fill: "rgba(255,255,255,.03)" }),
            h("text", Object.assign({ key: "t1", y: 4, style: { fontWeight: 800, fontSize: 11, fill: "#f4fbff", letterSpacing: ".01em" } }, short.length > 5 ? { textLength: Math.min(52, short.length * 7.4), lengthAdjust: "spacingAndGlyphs" } : {}), short),
            statusBadge(role.status, rNode - 3, (3 + (i % 4)) + "s"),
          ]);
        })),
      ]),
      h("div", { key: "hint", className: "pfmc-graph-legend" }, [
        h("span", { key: "h" }, "Click a specialist for details · ring colour = role"),
        h("span", { key: "l", className: "pfmc-graph-key" }, [["COMPLETE", "Complete"], ["ACTIVE", "Active"], ["PENDING", "Pending"], ["SKIPPED", "Skipped"]].map(function (x) {
          return h("span", { key: x[0] }, [h("i", { key: "i", style: { background: STATUS_COLOR[x[0]] } }), x[1]]);
        })),
      ]),
    ]);
  }

  function AgentDrawer(props) {
    const role = props.role;
    if (!role) return null;
    const rows = [
      ["Status", role.status], ["Reason", role.reason || "—"],
      ["Worker used", role.worker_used || "—"], ["Fallback used", role.fallback_used ? "Yes" : "No"],
      ["Execution status", role.execution_status || "—"], ["Evidence", role.execution_evidence || "—"],
      ["Primary route", (role.route && role.route.primary) || "—"], ["Fallback route", (role.route && role.route.fallback) || "—"],
    ];
    return h("div", null, [
      h("div", { className: "pfmc-drawer-backdrop", key: "bd", onClick: props.onClose }),
      h("div", { className: "pfmc-drawer", key: "d" }, [
        h("div", { className: "pfmc-drawer-head", key: "h" }, [
          h("h3", { key: "t" }, role.label || role.name),
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: props.onClose }, "✕"),
        ]),
        h("div", { className: "pfmc-drawer-body", key: "b" }, [
          h("div", { className: "pfmc-drawer-section", key: "s1" }, [
            h("h4", { key: "h" }, "Agent"),
            ...rows.map((r, i) => h("div", { className: "pfmc-drawer-row", key: i }, [
              h("span", { className: "pfmc-dk", key: "k" }, r[0]), h("span", { className: "pfmc-dv", key: "v" }, r[1]),
            ])),
          ]),
        ]),
      ]),
    ]);
  }

  function MissionHeader(props) {
    const d = props.data || {};
    const roles = d.roles || [];
    const total = roles.length || 1;
    const done = roles.filter((r) => r.status === "COMPLETE" || r.status === "SKIPPED").length;
    const pct = Math.round((done / total) * 100);
    const hasActiveAgent = !!d.current_specialist;
    const items = [
      ["Phase", d.phase || "Unavailable", null],
      ["Milestone", d.milestone || "Unavailable", null],
      ["Progress", pct + "%", null],
      ["Current Agent", hasActiveAgent ? d.current_specialist : "No active agent", hasActiveAgent ? d.current_specialist : null],
      ["Worker", d.active_worker || "None", d.active_worker ? "__worker__" : null],
    ];
    return h("div", { className: "pfmc-panel pfmc-header" }, [
      h("div", { key: "left" }, [
        h("p", { className: "pfmc-kicker", key: "k" }, "PRODUCT FACTORY MISSION CONTROL"),
        h("h1", { key: "h" }, d.project || "No active project"),
        h("div", { className: "pfmc-progress-track", key: "pt", style: { width: "100%", maxWidth: 320 } }, h("div", { className: "pfmc-progress-fill", style: { width: pct + "%" } })),
      ]),
      h("div", { className: "pfmc-header-meta", key: "meta" }, items.map(([label, value, action], i) => h("div", {
        className: "pfmc-meta-item" + (action ? " pfmc-meta-clickable" : ""), key: i,
        onClick: action ? () => (action === "__worker__" ? props.onSelectWorker(d) : props.onSelectRole(action)) : undefined,
      }, [
        h("span", { key: "l" }, label), h("strong", { key: "v" }, value),
      ]))),
    ]);
  }

  function WorkerDrawer(props) {
    const d = props.data;
    if (!d) return null;
    const role = (d.roles || []).find((r) => r.name === d.current_specialist) || {};
    const rows = [
      ["Worker / runtime", d.active_worker || "Unavailable"],
      ["Executing for", d.current_specialist || "Unavailable"],
      ["Fallback used", role.fallback_used ? "Yes" : "No"],
      ["Execution status", role.execution_status || "Unavailable"],
      ["Primary route", (role.route && role.route.primary) || "Unavailable"],
      ["Fallback route", (role.route && role.route.fallback) || "Unavailable"],
    ];
    return h("div", null, [
      h("div", { className: "pfmc-drawer-backdrop", key: "bd", onClick: props.onClose }),
      h("div", { className: "pfmc-drawer", key: "d" }, [
        h("div", { className: "pfmc-drawer-head", key: "h" }, [
          h("h3", { key: "t" }, "Worker Runtime"),
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: props.onClose }, "✕"),
        ]),
        h("div", { className: "pfmc-drawer-body", key: "b" }, h("div", { className: "pfmc-drawer-section" }, [
          h("h4", { key: "h" }, "Runtime"),
          ...rows.map((r, i) => h("div", { className: "pfmc-drawer-row", key: i }, [
            h("span", { className: "pfmc-dk", key: "k" }, r[0]), h("span", { className: "pfmc-dv", key: "v" }, r[1]),
          ])),
        ])),
      ]),
    ]);
  }

  function ProjectSwitcher(props) {
    const [open, setOpen] = useState(false);
    const current = props.projects.find((p) => p.project_id === props.value);
    return h("div", { className: "pfmc-switcher" }, [
      h("span", { className: "pfmc-switcher-label", key: "l" }, "ACTIVE PROJECT"),
      h("div", { className: "pfmc-switcher-control", key: "c" }, [
        h("button", { key: "btn", className: "pfmc-switcher-btn", onClick: () => setOpen((o) => !o) }, [
          h("span", { key: "name", className: "pfmc-switcher-name" }, (current && current.project) || "Select project"),
          h(Pill, { key: "status", value: (current && current.phase) || "unknown" }),
          h("span", { key: "chev", className: "pfmc-switcher-chevron" }, open ? "▴" : "▾"),
        ]),
        open ? h("div", { key: "menu", className: "pfmc-switcher-menu" }, props.projects.map((p) => h("div", {
          key: p.project_id, className: "pfmc-switcher-item" + (p.project_id === props.value ? " pfmc-switcher-item-active" : ""),
          onClick: () => { props.onChange(p.project_id); setOpen(false); },
        }, [
          h("span", { key: "n", className: "pfmc-switcher-item-name" }, p.project),
          h(Pill, { key: "s", value: p.phase }),
        ]))) : null,
      ]),
    ]);
  }

  function StatusDonut(props) {
    const roles = props.roles || [];
    const counts = { COMPLETE: 0, ACTIVE: 0, PENDING: 0, SKIPPED: 0 };
    roles.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
    const total = roles.length || 1;
    const r = 54, circumference = 2 * Math.PI * r;
    let offset = 0;
    const segments = Object.entries(counts).filter(([, n]) => n > 0).map(([status, n]) => {
      const frac = n / total;
      const seg = h("circle", {
        key: status, cx: 70, cy: 70, r, fill: "none", stroke: STATUS_COLOR[status],
        strokeWidth: 16, strokeDasharray: (frac * circumference) + " " + circumference,
        strokeDashoffset: -offset, transform: "rotate(-90 70 70)",
      });
      offset += frac * circumference;
      return seg;
    });
    return h("div", { className: "pfmc-donut-wrap" }, [
      h("svg", { key: "svg", viewBox: "0 0 140 140", width: 140, height: 140 }, [
        h("circle", { key: "track", cx: 70, cy: 70, r, fill: "none", stroke: "rgba(255,255,255,.06)", strokeWidth: 16 }),
        ...segments,
        h("text", { key: "n", x: 70, y: 66, textAnchor: "middle", style: { fill: "#fff", fontSize: 20, fontWeight: 800 } }, total),
        h("text", { key: "l", x: 70, y: 82, textAnchor: "middle", style: { fill: "var(--pfmc-muted)", fontSize: 9, letterSpacing: "0.1em" } }, "ROLES"),
      ]),
      h("div", { className: "pfmc-donut-legend", key: "legend" }, Object.entries(counts).filter(([, n]) => n > 0).map(([status, n]) => h("div", {
        key: status, className: "pfmc-donut-legend-row" + (props.activeFilter === status ? " pfmc-donut-legend-active" : ""),
        onClick: () => props.onFilter(props.activeFilter === status ? null : status),
      }, [
        h("span", { key: "dot", className: "pfmc-donut-dot", style: { background: STATUS_COLOR[status] } }),
        h("span", { key: "l" }, status), h("strong", { key: "n" }, n),
      ]))),
    ]);
  }

  function Timeline(props) {
    const roles = props.roles || [];
    let order = ROLE_ORDER.filter((n) => roles.some((r) => r.name === n));
    const byName = {}; roles.forEach((r) => { byName[r.name] = r; });
    if (props.statusFilter) order = order.filter((n) => (byName[n] || {}).status === props.statusFilter);
    return h(Panel, {
      title: "Mission Timeline",
      extra: props.statusFilter ? h("button", { onClick: () => props.onFilter(null), style: { fontSize: 10.5, padding: "4px 9px", minHeight: "auto" } }, "Clear filter: " + props.statusFilter + " ✕") : null,
    }, order.length ? h("div", { className: "pfmc-timeline2" },
      order.map((name) => {
        const r = byName[name] || {};
        const pct = r.status === "COMPLETE" ? 100 : r.status === "ACTIVE" ? 55 : r.status === "SKIPPED" ? 100 : 0;
        const color = STATUS_COLOR[r.status] || STATUS_COLOR.PENDING;
        return h("div", { className: "pfmc-tl-row", key: name, onClick: () => props.onSelect(name), title: r.reason || "" }, [
          h("span", { key: "n" }, r.label || name),
          h("div", { className: "pfmc-tl-track", key: "t" }, h("div", { className: "pfmc-tl-fill", style: { width: pct + "%", background: color } })),
          h(Pill, { key: "p", value: r.status || "PENDING" }),
        ]);
      })
    ) : h(Empty, null, "No roles match this filter."));
  }

  function Gates(props) {
    const [open, setOpen] = useState({});
    const gates = props.gates || [];
    if (!gates.length) return h(Panel, { title: "Quality Gates" }, h(Empty, null, "No gates recorded for this project."));
    return h(Panel, { title: "Quality Gates" }, h("div", { className: "pfmc-gate-grid" },
      gates.map((g, i) => h("div", {
        key: i, className: "pfmc-gate" + (open[i] ? " pfmc-open" : ""),
        onClick: () => setOpen((o) => ({ ...o, [i]: !o[i] })),
      }, [
        h("div", { className: "pfmc-gate-name", key: "n" }, g.name),
        h(Pill, { key: "p", value: g.status }),
        h("div", { className: "pfmc-gate-reason", key: "r" }, g.reason),
      ]))
    ));
  }

  function ActivityStream(props) {
    const [filter, setFilter] = useState("all");
    const activity = props.activity || [];
    const filters = ["all", "hermes", "agents", "errors", "warnings"];
    const filtered = activity.filter((e) => {
      if (filter === "all") return true;
      const ev = (e.event || "").toLowerCase();
      if (filter === "errors") return ev.includes("fail") || ev.includes("error") || ev.includes("reject");
      if (filter === "warnings") return ev.includes("remediation") || ev.includes("fallback") || ev.includes("retry");
      if (filter === "hermes") return !e.specialist;
      if (filter === "agents") return !!e.specialist;
      return true;
    });
    return h(Panel, {
      title: "Live Activity Stream" + (props.push ? "  ● PUSH" : "  ○ polling"),
      extra: h("div", { className: "pfmc-stream-filters" }, filters.map((f) => h("button", {
        key: f, "data-active": String(f === filter), onClick: () => setFilter(f),
      }, f))),
    }, filtered.length ? h("ul", { className: "pfmc-stream" }, filtered.slice().reverse().map((e, i) => h("li", { key: i }, [
      h("time", { key: "t" }, (e.timestamp || "").replace("T", " ").slice(0, 19)),
      h("span", { className: "pfmc-ev", key: "ev" }, (e.specialist ? e.specialist + " · " : "Hermes · ") + e.event),
      e.detail ? h("span", { className: "pfmc-detail", key: "d" }, e.detail) : null,
    ]))) : h(Empty, null, "No activity matches this filter."));
  }

  function Artifacts(props) {
    const artifacts = props.artifacts || [];
    if (!artifacts.length) return h(Panel, { title: "Artifacts" }, h(Empty, null, "No inspectable artifacts yet."));
    return h(Panel, { title: "Artifacts" }, h("div", { className: "pfmc-artifacts2" },
      artifacts.map((a) => h("button", { key: a.id, onClick: () => props.onOpen(a.id) }, [
        h("strong", { key: "n" }, a.name), h("span", { key: "g" }, a.group + " · " + (a.size / 1024).toFixed(1) + " KB"),
      ]))
    ));
  }


  const AGENT_LABEL = { default: "Gideon", scout: "Scout", scribe: "Scribe", socialmediaagent: "Reach",
    "youtube-production-agent": "Production", "product-factory": "Product Factory", unassigned: "Unassigned" };
  const TASK_COLOR = { ready: "#38bdf8", running: "#fbbf24", blocked: "#fb7185", done: "#4ade80", review: "#8b7cf6", triage: "#5b7285", todo: "#5b7285" };

  function agentLabel(name) { return AGENT_LABEL[name] || name; }

  const TEAM_ORDER = ["default", "scout", "scribe", "socialmediaagent", "youtube-production-agent", "product-factory"];
  const RISK_NOTE = {
    "product-factory": "Product Factory can run commands and change files on the server.",
    socialmediaagent: "Reach is instructed to ask you before posting anything, but that is guidance, not a hard block.",
    "youtube-production-agent": "Production is instructed to ask you before any paid generation, but that is guidance, not a hard block.",
    default: "Gideon has the full toolset, including the terminal.",
  };

  function NewTaskDialog(props) {
    const [title, setTitle] = useState("");
    const [body, setBody] = useState("");
    const [assignee, setAssignee] = useState(props.assignees.indexOf("scout") >= 0 ? "scout" : props.assignees[0]);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const submit = async function () {
      if (!title.trim()) { setErr("Give the task a title."); return; }
      setBusy(true); setErr("");
      try {
        await props.onCreate({ title: title.trim(), body: body.trim(), assignee });
        props.onClose();
      } catch (e) { setErr(e && e.message ? e.message : "Could not create the task."); setBusy(false); }
    };
    return h("div", null, [
      h("div", { className: "pfmc-drawer-backdrop", key: "bd", onClick: props.onClose }),
      h("div", { className: "pfmc-modal", key: "m" }, [
        h("div", { className: "pfmc-drawer-head", key: "h" }, [
          h("h3", { key: "t" }, "New task"),
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: props.onClose }, "✕"),
        ]),
        h("div", { className: "pfmc-form", key: "f" }, [
          h("label", { key: "l1" }, "Title"),
          h("input", { key: "i1", value: title, maxLength: 140, placeholder: "What should be done?", onChange: (e) => setTitle(e.target.value) }),
          h("label", { key: "l2" }, "Details (the agent sees only this, so include the goal, context and what the result should contain)"),
          h("textarea", { key: "i2", rows: 6, value: body, maxLength: 4000, onChange: (e) => setBody(e.target.value) }),
          h("label", { key: "l3" }, "Assign to"),
          h("select", { key: "i3", value: assignee, onChange: (e) => setAssignee(e.target.value) },
            props.assignees.map((a) => h("option", { key: a, value: a }, agentLabel(a)))),
          RISK_NOTE[assignee] ? h("div", { className: "pfmc-warn", key: "w" }, RISK_NOTE[assignee]) : null,
          err ? h("div", { className: "pfmc-form-err", key: "e" }, err) : null,
          h("div", { className: "pfmc-form-actions", key: "a" }, [
            h("button", { className: "pfmc-btn", key: "c", onClick: props.onClose, disabled: busy }, "Cancel"),
            h("button", { className: "pfmc-btn pfmc-btn-primary", key: "s", onClick: submit, disabled: busy }, busy ? "Creating…" : "Create task"),
          ]),
        ]),
      ]),
    ]);
  }

  function ago(iso) {
    if (!iso) return "";
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (s < 60) return s + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }


  function fmtDate(iso) { return iso ? iso.replace("T", " ").replace("Z", "").slice(0, 16) : ""; }

  function LibraryPanel(props) {
    const lib = props.lib;
    const agents = lib && lib.agents ? Object.keys(lib.agents) : [];
    const chips = ["all"].concat(TEAM_ORDER.map(agentLabel).filter((n) => agents.indexOf(n) >= 0), agents.filter((n) => TEAM_ORDER.map(agentLabel).indexOf(n) < 0));
    const head = h("div", { className: "pfmc-stream-filters", key: "f" }, chips.map((c) => h("button", {
      key: c, "data-active": String((props.agent || "all") === c), onClick: () => props.onAgent(c === "all" ? "" : c),
    }, c === "all" ? "all" : c + " " + (lib.agents[c] || 0))));
    if (!lib) return h(Panel, { title: "Content Library" }, h(Empty, null, "Loading the library…"));
    if (!lib.available) return h(Panel, { title: "Content Library" }, h(Empty, null, "The Obsidian vault folder for agent outputs isn't available on this server yet."));
    return h(Panel, { title: "Content Library" + (props.push ? "  ● PUSH" : ""), extra: chips.length > 1 ? head : null }, [
      h("input", { key: "q", className: "pfmc-search", value: props.query, placeholder: "Search titles and content…", onChange: (e) => props.onQuery(e.target.value) }),
      lib.items.length ? h("div", { className: "pfmc-lib", key: "l" }, lib.items.map((it) => h("button", { className: "pfmc-lib-row", key: it.path, onClick: () => props.onOpen(it.path) }, [
        h("div", { className: "pfmc-lib-top", key: "t" }, [h("strong", { key: "s" }, it.title), h("span", { className: "pfmc-lib-agent", key: "a" }, it.agent)]),
        it.snippet ? h("span", { className: "pfmc-tb-sum", key: "sn" }, it.snippet) : null,
        h("span", { className: "pfmc-tb-meta", key: "m" }, fmtDate(it.completed) + " · " + (it.size / 1024).toFixed(1) + " KB" + (it.status ? " · " + it.status : "")),
      ]))) : h(Empty, { key: "e" }, props.query || props.agent ? "Nothing matches." : "No saved outputs yet. Finished tasks appear here automatically."),
    ]);
  }

  function NoteDrawer(props) {
    const n = props.note;
    const [copied, setCopied] = useState(false);
    useEffect(function () { setCopied(false); }, [n && n.path]);
    if (!n) return null;
    const copy = function () {
      try { navigator.clipboard.writeText(n.content).then(() => setCopied(true)); } catch (err) { setCopied(false); }
    };
    const fm = n.frontmatter || {};
    return h("div", null, [
      h("div", { className: "pfmc-drawer-backdrop", key: "bd", onClick: props.onClose }),
      h("div", { className: "pfmc-drawer pfmc-drawer-wide", key: "d" }, [
        h("div", { className: "pfmc-drawer-head", key: "h" }, [
          h("h3", { key: "t" }, fm.title || n.path),
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: props.onClose }, "✕"),
        ]),
        h("div", { className: "pfmc-drawer-body", key: "b" }, [
          h("div", { className: "pfmc-drawer-section", key: "m" }, [
            h("div", { className: "pfmc-drawer-row", key: "1" }, [h("span", { className: "pfmc-dk", key: "k" }, "By"), h("span", { className: "pfmc-dv", key: "v" }, fm.agent || "—")]),
            h("div", { className: "pfmc-drawer-row", key: "2" }, [h("span", { className: "pfmc-dk", key: "k" }, "Status"), h("span", { className: "pfmc-dv", key: "v" }, fm.status || "—")]),
            h("div", { className: "pfmc-drawer-row", key: "3" }, [h("span", { className: "pfmc-dk", key: "k" }, "Vault path"), h("span", { className: "pfmc-dv", key: "v" }, n.vault_path)]),
            fm.task ? h("div", { className: "pfmc-drawer-row", key: "4" }, [h("span", { className: "pfmc-dk", key: "k" }, "Task"), h("span", { className: "pfmc-dv", key: "v" }, fm.task)]) : null,
          ]),
          h("div", { className: "pfmc-form-actions", key: "a", style: { justifyContent: "flex-start", margin: "0 0 8px" } },
            h("button", { className: "pfmc-btn", onClick: copy }, copied ? "Copied" : "Copy text")),
          h("pre", { className: "pfmc-pre pfmc-pre-tall", key: "c" }, n.content + (n.truncated ? "\n\n…(truncated)" : "")),
        ]),
      ]),
    ]);
  }

  function TaskBoard(props) {
    const board = props.board;
    const [who, setWho] = useState("all");
    if (!board) return h(Panel, { title: "Team Task Board" }, h(Empty, null, "Loading the Kanban board…"));
    if (!board.tasks.length) return h(Panel, { title: "Team Task Board", extra: h("button", { className: "pfmc-newtask", onClick: props.onNew }, "+ New task") }, h(Empty, null, "No tasks yet. Create one here or ask Gideon in Telegram."));
    const seen = Object.keys(board.by_assignee).filter((a) => TEAM_ORDER.indexOf(a) < 0);
    const people = ["all"].concat(TEAM_ORDER, seen);
    const tasks = board.tasks.filter((t) => who === "all" || t.assignee === who);
    return h(Panel, {
      title: "Team Task Board" + (props.push ? "  ● PUSH" : ""),
      extra: h("div", { className: "pfmc-stream-filters" }, [h("button", { key: "new", className: "pfmc-newtask", onClick: props.onNew }, "+ New task")].concat(people.map((p) => h("button", {
        key: p, "data-active": String(p === who), onClick: () => setWho(p),
      }, p === "all" ? "all" : agentLabel(p) + (board.by_assignee[p] ? " " + board.by_assignee[p] : ""))))),
    }, h("div", { className: "pfmc-tb" }, board.columns.map((col) => {
      const items = tasks.filter((t) => t.status === col);
      return h("div", { className: "pfmc-tb-col", key: col }, [
        h("div", { className: "pfmc-tb-head", key: "h", style: { color: TASK_COLOR[col] || "#7590a3" } }, [
          h("span", { key: "n" }, col), h("span", { className: "pfmc-tb-n", key: "c" }, items.length),
        ]),
        h("div", { className: "pfmc-tb-list", key: "l" }, items.length ? items.map((t) => h("button", {
          className: "pfmc-tb-card", key: t.id, onClick: () => props.onOpen(t.id),
          style: { borderLeftColor: TASK_COLOR[t.status] || "#5b7285" },
        }, [
          h("strong", { key: "t" }, t.title),
          h("span", { className: "pfmc-tb-meta", key: "m" }, agentLabel(t.assignee) + " · " + ago(t.completed_at || t.started_at || t.created_at)),
          t.summary ? h("span", { className: "pfmc-tb-sum", key: "s" }, t.summary) : null,
          (t.attachments || t.failures) ? h("span", { className: "pfmc-tb-meta", key: "a" },
            (t.attachments ? t.attachments + " file" + (t.attachments > 1 ? "s" : "") : "") + (t.failures ? "  ⚠ " + t.failures + " failed" : "")) : null,
        ])) : h("div", { className: "pfmc-tb-empty", key: "e" }, "empty")),
      ]);
    })));
  }

  function TaskDrawer(props) {
    const t = props.task;
    const [preview, setPreview] = useState(null);
    const [reason, setReason] = useState("");
    const [target, setTarget] = useState("");
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState("");
    useEffect(function () { setPreview(null); setReason(""); setTarget(""); setNote(""); }, [t && t.id]);
    if (!t) return null;
    const act = async function (fn) {
      setBusy(true); setNote("");
      try { await fn(); setNote("Done."); } catch (e) { setNote(e && e.message ? e.message : "That did not work."); }
      setBusy(false);
    };
    const openFile = async function (a) {
      try {
        setPreview({ filename: a.filename, loading: true });
        const r = await fetchJSON(API + "/kanban/" + encodeURIComponent(t.id) + "/attachments/" + a.id);
        setPreview(r);
      } catch (err) { setPreview({ filename: a.filename, preview: null, note: err && err.message ? err.message : "Could not load." }); }
    };
    const row = function (k, v, i) { return h("div", { className: "pfmc-drawer-row", key: i }, [h("span", { className: "pfmc-dk", key: "k" }, k), h("span", { className: "pfmc-dv", key: "v" }, v || "—")]); };
    const latest = (t.runs || []).slice(-1)[0];
    const others = (props.assignees || []).filter((a) => a !== t.assignee);
    const finished = t.status === "done" || t.status === "archived";
    const actions = h("div", { className: "pfmc-drawer-section", key: "sa" }, [
      h("h4", { key: "h" }, "Actions"),
      finished ? h("div", { className: "pfmc-tb-meta", key: "f" }, "Finished tasks can't be changed. Create a new task to follow up.") : null,
      t.status === "blocked" ? h("div", { className: "pfmc-act", key: "u" }, [
        h("input", { key: "i", value: reason, maxLength: 300, placeholder: "Why is it OK to continue? (optional)", onChange: (e) => setReason(e.target.value) }),
        h("button", { className: "pfmc-btn pfmc-btn-primary", key: "b", disabled: busy, onClick: () => act(() => props.onUnblock(t.id, reason)) }, "Unblock"),
      ]) : null,
      !finished ? h("div", { className: "pfmc-act", key: "r" }, [
        h("select", { key: "s", value: target, onChange: (e) => setTarget(e.target.value) },
          [h("option", { key: "_", value: "" }, "Reassign to…")].concat(others.map((a) => h("option", { key: a, value: a }, agentLabel(a))))),
        h("button", { className: "pfmc-btn", key: "b", disabled: busy || !target, onClick: () => act(() => props.onReassign(t.id, target)) }, t.status === "running" ? "Stop and reassign" : "Reassign"),
      ]) : null,
      !finished && target && RISK_NOTE[target] ? h("div", { className: "pfmc-warn", key: "w" }, RISK_NOTE[target]) : null,
      note ? h("div", { className: "pfmc-tb-meta", key: "n" }, note) : null,
    ]);
    return h("div", null, [
      h("div", { className: "pfmc-drawer-backdrop", key: "bd", onClick: props.onClose }),
      h("div", { className: "pfmc-drawer pfmc-drawer-wide", key: "d" }, [
        h("div", { className: "pfmc-drawer-head", key: "h" }, [
          h("h3", { key: "t" }, t.title),
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: props.onClose }, "✕"),
        ]),
        h("div", { className: "pfmc-drawer-body", key: "b" }, [
          h("div", { className: "pfmc-drawer-section", key: "s1" }, [
            h("h4", { key: "h" }, "Task"),
            row("Status", t.status, 1), row("Assigned to", agentLabel(t.assignee), 2), row("Created by", t.created_by, 3),
            row("Created", (t.created_at || "").replace("T", " ").replace("Z", " UTC"), 4),
            row("Finished", (t.completed_at || "").replace("T", " ").replace("Z", " UTC"), 5),
            t.failures ? row("Failed attempts", String(t.failures), 6) : null,
            t.last_error ? row("Last error", t.last_error, 7) : null,
          ]),
          actions,
          t.body ? h("div", { className: "pfmc-drawer-section", key: "s2" }, [h("h4", { key: "h" }, "Request"), h("pre", { className: "pfmc-pre", key: "p" }, t.body)]) : null,
          latest && latest.summary ? h("div", { className: "pfmc-drawer-section", key: "s3" }, [h("h4", { key: "h" }, "Result"), h("pre", { className: "pfmc-pre", key: "p" }, latest.summary)]) : null,
          (t.attachments || []).length ? h("div", { className: "pfmc-drawer-section", key: "s4" }, [
            h("h4", { key: "h" }, "Files"),
            ...t.attachments.map((a) => h("button", { className: "pfmc-file", key: a.id, onClick: () => openFile(a) }, a.filename + "  ·  " + (a.size / 1024).toFixed(1) + " KB")),
            preview ? h("pre", { className: "pfmc-pre", key: "pv" }, preview.loading ? "Loading…" : (preview.preview != null ? preview.preview + (preview.truncated ? "\n…(truncated)" : "") : (preview.note || "No preview."))) : null,
          ]) : null,
          (t.runs || []).length ? h("div", { className: "pfmc-drawer-section", key: "s5" }, [h("h4", { key: "h" }, "Runs"),
            ...t.runs.map((r) => row("Run " + r.id + " · " + agentLabel(r.profile), (r.outcome || r.status) + (r.ended_at ? " · " + ago(r.ended_at) : ""), "r" + r.id))]) : null,
          (t.events || []).length ? h("div", { className: "pfmc-drawer-section", key: "s6" }, [h("h4", { key: "h" }, "Timeline"),
            ...t.events.slice().reverse().map((e, i) => row(e.kind, (e.at || "").replace("T", " ").replace("Z", ""), "e" + i))]) : null,
        ]),
      ]),
    ]);
  }







  /* ---------------- 3D office ----------------
     Real state only: team agents from the Kanban board, specialists from the project state.
     three.js is shipped with this plugin (dist/three.module.min.js) and loaded only when the
     Office page is opened. */
  const TEAM_COLOR = {
    default: "#38bdf8", scout: "#fb923c", scribe: "#a78bfa",
    socialmediaagent: "#e879f9", "youtube-production-agent": "#f87171", "product-factory": "#2dd4bf",
  };
  const STATE_META = {
    working: { color: "#fbbf24", label: "Working" },
    blocked: { color: "#fb7185", label: "Blocked" },
    queued: { color: "#38bdf8", label: "Queued" },
    recent: { color: "#4ade80", label: "Just finished" },
    idle: { color: "#5b7285", label: "Idle" },
    skipped: { color: "#3b4b5c", label: "Not needed" },
  };
  let threePromise = null;
  function loadThree() {
    if (!threePromise) {
      const base = window.__PFMC_ASSET_BASE__ || "/dashboard-plugins/product-factory-mission-control/dist/";
      threePromise = import(base + "three.module.min.js").catch(function (e) { threePromise = null; throw e; });
    }
    return threePromise;
  }

  function deriveTeam(board) {
    const out = {};
    TEAM_ORDER.forEach(function (id) { out[id] = { id: id, running: 0, blocked: 0, queued: 0, done: 0, last: null, state: "idle" }; });
    ((board && board.tasks) || []).forEach(function (t) {
      const s = out[t.assignee];
      if (!s) return;
      if (t.status === "running") s.running++;
      else if (t.status === "blocked") s.blocked++;
      else if (t.status === "done") { s.done++; if (!s.last || (t.completed_at || "") > (s.last.at || "")) s.last = { title: t.title, at: t.completed_at }; }
      else s.queued++;
    });
    TEAM_ORDER.forEach(function (id) {
      const s = out[id];
      const recent = s.last && s.last.at && (Date.now() - new Date(s.last.at).getTime()) < 15 * 60 * 1000;
      s.state = s.running ? "working" : s.blocked ? "blocked" : s.queued ? "queued" : recent ? "recent" : "idle";
    });
    // Gideon delegates: while anyone else has tasks running or queued he is coordinating them
    let inflight = 0;
    TEAM_ORDER.forEach(function (id) { if (id !== "default") inflight += out[id].running + out[id].queued; });
    out.default.coordinating = inflight;
    if (inflight && (out.default.state === "idle" || out.default.state === "recent")) out.default.state = "working";
    return out;
  }

  function deriveRoles(roles) {
    const out = {};
    (roles || []).forEach(function (r) {
      out[r.name] = { id: r.name, role: r, state: r.status === "ACTIVE" ? "working" : r.status === "COMPLETE" ? "recent" : r.status === "PENDING" ? "queued" : "skipped" };
    });
    return out;
  }

  function buildOffice(THREE, mount, labelsEl, dataRef, onPick, apiRef) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);
    renderer.domElement.className = "pfmc-office-canvas";
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x030910, 46, 100);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.5, 200);
    scene.add(new THREE.HemisphereLight(0xa8dcff, 0x0a1220, 1.05));
    const sun = new THREE.DirectionalLight(0xffffff, 0.85);
    sun.position.set(12, 24, 10);
    scene.add(sun);

    const disposables = [];
    const mat = function (opts) { const m = new THREE.MeshStandardMaterial(opts); disposables.push(m); return m; };
    const geo = function (g) { disposables.push(g); return g; };
    const basic = function (opts) { const m = new THREE.MeshBasicMaterial(opts); disposables.push(m); return m; };

    // ground + two platforms
    const ground = new THREE.Mesh(geo(new THREE.CircleGeometry(70, 64)), mat({ color: 0x050d18, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2; scene.add(ground);
    const grid = new THREE.GridHelper(100, 50, 0x123049, 0x0b1a2b);
    grid.position.y = 0.02; disposables.push(grid.geometry, grid.material); scene.add(grid);
    const ZONES = [
      { key: "team", cx: -11, cz: 0, r: 9.6, color: 0x38bdf8, title: "COMMAND FLOOR" },
      { key: "pf", cx: 11, cz: 0, r: 10.6, color: 0x8b7cf6, title: "PRODUCT FACTORY" },
    ];
    ZONES.forEach(function (z) {
      const plat = new THREE.Mesh(geo(new THREE.CylinderGeometry(z.r, z.r, 0.3, 56)), mat({ color: 0x0a1727, roughness: 0.85 }));
      plat.position.set(z.cx, 0.15, z.cz); scene.add(plat); z.plat = plat;
      const rim = new THREE.Mesh(geo(new THREE.RingGeometry(z.r - 0.12, z.r + 0.08, 72)), basic({ color: z.color, transparent: true, opacity: 0.85, side: THREE.DoubleSide }));
      rim.rotation.x = -Math.PI / 2; rim.position.set(z.cx, 0.32, z.cz); scene.add(rim); z.rim = rim;
      const ping = new THREE.Mesh(geo(new THREE.RingGeometry(z.r - 0.5, z.r, 72)), basic({ color: z.color, transparent: true, opacity: 0, side: THREE.DoubleSide }));
      ping.rotation.x = -Math.PI / 2; ping.position.set(z.cx, 0.34, z.cz); scene.add(ping); z.ping = ping;
    });

    let agentCount = 0;
    const agents = {};   // id -> { group, screen, ring, body, head, phase, state, label, kind }
    const pickables = [];
    const col = function (hex) { return new THREE.Color(hex); };

    function makeAgent(id, kind, color, zone, ox, oz, big) {
      const cx = zone.cx + ox, cz = zone.cz + oz;
      const g = new THREE.Group();
      g.position.set(cx, 0.3, cz);
      const w = big ? 2.8 : 2.1;
      const deskMat = mat({ color: 0x172d46, roughness: 0.65, metalness: 0.15 });
      const top = new THREE.Mesh(geo(new THREE.BoxGeometry(w, 0.12, 1.1)), deskMat);
      top.position.set(0, 0.9, 1.15); g.add(top);
      [-1, 1].forEach(function (s) {
        const leg = new THREE.Mesh(geo(new THREE.BoxGeometry(0.12, 0.9, 0.9)), deskMat);
        leg.position.set(s * (w / 2 - 0.14), 0.45, 1.15); g.add(leg);
      });
      const scr = document.createElement("canvas"); scr.width = 160; scr.height = 96;
      const scrTex = new THREE.CanvasTexture(scr); if (THREE.SRGBColorSpace) scrTex.colorSpace = THREE.SRGBColorSpace; disposables.push(scrTex);
      const screenMat = mat({ color: 0x050b14, emissive: 0xffffff, emissiveMap: scrTex, emissiveIntensity: 0.6, roughness: 0.4 });
      const screen = new THREE.Mesh(geo(new THREE.BoxGeometry(big ? 1.5 : 1.1, 0.7, 0.06)), screenMat);
      screen.position.set(0, 1.5, 1.35); g.add(screen);
      const stand = new THREE.Mesh(geo(new THREE.BoxGeometry(0.1, 0.3, 0.1)), deskMat);
      stand.position.set(0, 1.12, 1.35); g.add(stand);
      const bodyMat = mat({ color: col(color), roughness: 0.55, emissive: col(color), emissiveIntensity: 0.1 });
      const body = new THREE.Mesh(geo(new THREE.CapsuleGeometry(0.33, 0.55, 4, 12)), bodyMat);
      body.position.set(0, 1.15, 0); g.add(body);
      const head = new THREE.Mesh(geo(new THREE.SphereGeometry(0.27, 18, 14)), mat({ color: 0xe6eef7, roughness: 0.6 }));
      head.position.set(0, 1.95, 0); g.add(head);
      const chair = new THREE.Mesh(geo(new THREE.CylinderGeometry(0.4, 0.4, 0.1, 20)), deskMat);
      chair.position.set(0, 0.55, 0); g.add(chair);
      const makeArm = function (side) {
        const piv = new THREE.Group(); piv.position.set(side * 0.43, 1.55, 0);
        const m = new THREE.Mesh(geo(new THREE.CapsuleGeometry(0.09, 0.66, 3, 8)), bodyMat); m.position.y = -0.4; piv.add(m); g.add(piv); return piv;
      };
      const armL = makeArm(-1), armR = makeArm(1);
      const kb = new THREE.Mesh(geo(new THREE.BoxGeometry(big ? 0.9 : 0.7, 0.03, 0.28)), mat({ color: 0x0d1b2c, emissive: col(color), emissiveIntensity: 0.18, roughness: 0.5 }));
      kb.position.set(0, 0.985, 1.02); g.add(kb);
      const holo = new THREE.Group(); holo.position.set(0, 2.75, 0); g.add(holo);
      const hBasic = function (hex) { return basic({ color: col(hex), transparent: true, opacity: 0.95 }); };
      const hs = new THREE.Group(); [0, 1, 2].forEach(function (i) { const o = new THREE.Mesh(geo(new THREE.SphereGeometry(0.08, 10, 8)), hBasic(STATE_META.working.color)); const an = i / 3 * Math.PI * 2; o.position.set(Math.cos(an) * 0.5, 0, Math.sin(an) * 0.5); hs.add(o); }); holo.add(hs);
      const ha = new THREE.Group(); const bar = new THREE.Mesh(geo(new THREE.BoxGeometry(0.11, 0.34, 0.11)), hBasic(STATE_META.blocked.color)); bar.position.y = 0.12; ha.add(bar);
      const dotA = new THREE.Mesh(geo(new THREE.SphereGeometry(0.075, 10, 8)), hBasic(STATE_META.blocked.color)); dotA.position.y = -0.16; ha.add(dotA); holo.add(ha);
      const hq = new THREE.Group(); [-1, 0, 1].forEach(function (i) { const o = new THREE.Mesh(geo(new THREE.SphereGeometry(0.07, 10, 8)), hBasic(STATE_META.queued.color)); o.position.x = i * 0.24; hq.add(o); }); holo.add(hq);
      const hd = new THREE.Mesh(geo(new THREE.RingGeometry(0.28, 0.33, 36)), basic({ color: col(STATE_META.recent.color), transparent: true, opacity: 0.8, side: THREE.DoubleSide })); hd.rotation.x = -Math.PI / 2; holo.add(hd);
      hs.visible = ha.visible = hq.visible = hd.visible = false;
      const burst = new THREE.Mesh(geo(new THREE.RingGeometry(0.9, 1.0, 44)), basic({ color: 0xfbbf24, transparent: true, opacity: 0, side: THREE.DoubleSide }));
      burst.rotation.x = -Math.PI / 2; burst.position.set(0, 0.06, 0.6); g.add(burst);
      const ringMat = basic({ color: col(STATE_META.idle.color), transparent: true, opacity: 0.85, side: THREE.DoubleSide });
      const ring = new THREE.Mesh(geo(new THREE.RingGeometry(1.0, 1.16, 44)), ringMat);
      ring.rotation.x = -Math.PI / 2; ring.position.set(0, 0.04, 0.6); g.add(ring);
      // face the centre of this zone (local +z points at it), yaw only so nothing ever tilts
      g.rotation.y = (ox === 0 && oz === 0) ? Math.PI : Math.atan2(-ox, -oz);
      scene.add(g);
      const label = document.createElement("div");
      label.className = "pfmc-olabel";
      labelsEl.appendChild(label);
      const a = { id: id, kind: kind, group: g, screen: screen, screenMat: screenMat, ring: ring, ringMat: ringMat, body: body, bodyMat: bodyMat, head: head, armL: armL, armR: armR, scr: scr, sctx: scr.getContext("2d"), scrTex: scrTex, holo: holo, hs: hs, ha: ha, hq: hq, hd: hd, burst: burst,
                  idx: agentCount++, seed: agentCount * 7, hoverK: 0, hover: false, lastDraw: -9, needsDraw: true, burstAt: 0,
                  phase: Math.random() * 6.28, state: "idle", label: label, headWorld: new THREE.Vector3(cx, 3.1, cz), color: color, zone: zone, ox: ox, oz: oz };
      g.traverse(function (o) { if (o.isMesh) { o.userData.agentId = id; pickables.push(o); } });
      agents[id] = a;
      return a;
    }

    // Command Floor: Gideon at the centre, the five agents around him
    const teamZone = ZONES[0];
    makeAgent("default", "team", TEAM_COLOR.default, teamZone, 0, 0, true);
    const others = TEAM_ORDER.filter(function (i) { return i !== "default"; });
    others.forEach(function (id, i) {
      const ang = (i / others.length) * Math.PI * 2 + Math.PI / 2;
      makeAgent(id, "team", TEAM_COLOR[id], teamZone, Math.cos(ang) * 6.2, Math.sin(ang) * 6.2, false);
    });
    // Product Factory: the Director at the centre, the specialists on a ring
    const pfZone = ZONES[1];
    makeAgent("Hermes Director", "role", ROLE_COLOR["Hermes Director"], pfZone, 0, 0, true);
    const specs = ROLE_ORDER.slice(1);
    specs.forEach(function (name, i) {
      const ang = (i / specs.length) * Math.PI * 2 - Math.PI / 2;
      makeAgent(name, "role", ROLE_COLOR[name] || "#38bdf8", pfZone, Math.cos(ang) * 7.4, Math.sin(ang) * 7.4, false);
    });
    // zone titles as labels
    const zoneLabels = ZONES.map(function (z) {
      const el = document.createElement("div");
      el.className = "pfmc-ozone"; el.textContent = z.title; labelsEl.appendChild(el);
      return { el: el, pos: new THREE.Vector3(z.cx, 0.5, z.cz - z.r - 1.2) };
    });

    // ---- camera (custom orbit: drag to rotate, wheel / pinch to zoom) ----
    const target = new THREE.Vector3(0, 1.2, 0);
    const view = { theta: 0.0, phi: 1.02, radius: 36 };
    let home = { theta: 0.0, phi: 1.02, radius: 36 };
    let userMoved = false;
    let drift = true;
    let hoverPt = null, hoveredId = null;
    function placeCamera() {
      const sp = Math.sin(view.phi), cp = Math.cos(view.phi);
      camera.position.set(target.x + view.radius * sp * Math.sin(view.theta), target.y + view.radius * cp, target.z + view.radius * sp * Math.cos(view.theta));
      camera.lookAt(target);
    }
    apiRef.current = {
      reset: function () { userMoved = false; view.theta = home.theta; view.phi = home.phi; view.radius = home.radius; },
      zoom: function (f) { userMoved = true; view.radius = Math.max(14, Math.min(64, view.radius * f)); },
      tilt: function (d) { userMoved = true; view.phi = Math.max(0.3, Math.min(1.42, view.phi + d)); },
      spin: function (d) { userMoved = true; view.theta += d; },
      drift: function () { drift = !drift; if (!drift) userMoved = true; else { userMoved = false; } return drift; },
    };
    const el = renderer.domElement;
    const pts = new Map();
    el.addEventListener("pointermove", function (e) { if (e.pointerType === "mouse" && pts.size === 0) hoverPt = { x: e.clientX, y: e.clientY }; });
    el.addEventListener("pointerleave", function () { hoverPt = null; });
    let downAt = null, moved = 0, pinch0 = 0;
    el.addEventListener("pointerdown", function (e) {
      el.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      downAt = { x: e.clientX, y: e.clientY }; moved = 0;
      if (pts.size === 2) { const p = Array.from(pts.values()); pinch0 = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y); }
    });
    el.addEventListener("pointermove", function (e) {
      const prev = pts.get(e.pointerId);
      if (!prev) return;
      const cur = { x: e.clientX, y: e.clientY };
      if (pts.size === 1) {
        const dx = cur.x - prev.x, dy = cur.y - prev.y;
        moved += Math.abs(dx) + Math.abs(dy);
        if (moved > 8) userMoved = true;
        view.theta -= dx * 0.008;
        if (e.pointerType !== "touch") view.phi = Math.max(0.3, Math.min(1.42, view.phi - dy * 0.006));
      } else if (pts.size === 2) {
        pts.set(e.pointerId, cur);
        const p = Array.from(pts.values());
        const d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
        if (pinch0 > 0) { view.radius = Math.max(14, Math.min(64, view.radius * (pinch0 / d))); }
        pinch0 = d; moved += 10;
      }
      pts.set(e.pointerId, cur);
    });
    function up(e) {
      const wasTap = pts.size === 1 && downAt && moved < 8;
      pts.delete(e.pointerId);
      if (wasTap) pick(e.clientX, e.clientY);
      downAt = null;
    }
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", function (e) { pts.delete(e.pointerId); });
    el.addEventListener("wheel", function (e) { e.preventDefault(); userMoved = true; view.radius = Math.max(14, Math.min(64, view.radius * (1 + e.deltaY * 0.001))); }, { passive: false });

    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    function pick(cx, cy) {
      const r = el.getBoundingClientRect();
      ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(pickables, false)[0];
      onPick(hit ? hit.object.userData.agentId : null);
    }

    // ---- state -> look ----
    const sc = new THREE.Color();
    function applyState(a, state) {
      a.state = state;
      const meta = STATE_META[state] || STATE_META.idle;
      a.ringMat.color.set(meta.color);
      a.ringMat.opacity = state === "idle" || state === "skipped" ? 0.35 : 0.9;
      sc.set(state === "idle" || state === "skipped" ? a.color : meta.color);
      a.needsDraw = true;
      a.label.style.borderColor = meta.color;
      a.label.dataset.state = state;
    }

    // ---- task packets: an orb flies from the delegator to whoever is tasked, and back when done ----
    const packets = [];
    const packetGeo = geo(new THREE.SphereGeometry(0.28, 14, 10));
    const fromV = new THREE.Vector3(), toV = new THREE.Vector3();
    function spawnPacket(fromId, toId, color) {
      const A = agents[fromId], B = agents[toId];
      if (!A || !B || A === B || packets.length >= 8) return;
      const m = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.95 });
      const mesh = new THREE.Mesh(packetGeo, m);
      mesh.position.copy(A.headWorld);
      scene.add(mesh);
      packets.push({ mesh: mesh, mat: m, a: A, b: B, t0: clock.elapsedTime, dur: 1.4 });
    }
    if (window.__PFMC_DEBUG) window.__PFMC_DEBUG.packets = packets;
    const seenTasks = {}, seenRoles = {};
    let primedTasks = false, primedRoles = false;

    let lastKey = "";
    let lastWide = null;
    function syncData() {
      const d = dataRef.current;
      const team = deriveTeam(d.board), roles = deriveRoles(d.roles);
      // what just happened? (only real changes after the first load, never the history)
      const tasks = (d.board && d.board.tasks) || [];
      if (d.board && primedTasks) {
        tasks.forEach(function (tk) {
          const prev = seenTasks[tk.id];
          if (prev === undefined) {
            if (tk.status !== "done" && tk.assignee !== "default") spawnPacket("default", tk.assignee, "#fbbf24");
          } else if (prev !== tk.status) {
            if (tk.status === "done") spawnPacket(tk.assignee, "default", "#4ade80");
            else if (tk.status === "blocked") spawnPacket(tk.assignee, "default", "#fb7185");
            else if (tk.status === "running" && agents[tk.assignee]) agents[tk.assignee].flashUntil = clock.elapsedTime + 1.2;
          }
        });
      }
      if (d.board) { tasks.forEach(function (tk) { seenTasks[tk.id] = tk.status; }); primedTasks = true; }
      if (d.roles && d.roles.length) {
        if (primedRoles) {
          Object.keys(roles).forEach(function (n) {
            const st = roles[n].state, pv = seenRoles[n];
            if (pv !== undefined && pv !== st && n !== "Hermes Director") {
              if (st === "working") spawnPacket("Hermes Director", n, "#fbbf24");
              else if (pv === "working" && st === "recent") spawnPacket(n, "Hermes Director", "#4ade80");
            }
          });
        }
        Object.keys(roles).forEach(function (n) { seenRoles[n] = roles[n].state; });
        primedRoles = true;
      }
      const key = JSON.stringify([Object.values(team).map(function (s) { return s.state + s.running + s.blocked + s.queued; }), Object.values(roles).map(function (r) { return r.state; }), d.currentSpecialist]);
      if (key === lastKey && lastWide === (mount.clientWidth >= 520)) return;
      lastWide = mount.clientWidth >= 520;
      lastKey = key;
      Object.keys(agents).forEach(function (id) {
        const a = agents[id];
        if (a.kind === "team") {
          const s = team[id]; applyState(a, s ? s.state : "idle");
          const wide = mount.clientWidth >= 520;
          a.label.textContent = agentLabel(id) + (wide && s && s.running ? "  ·  " + s.running + " running" : wide && s && s.queued ? "  ·  " + s.queued + " queued" : wide && id === "default" && s && s.coordinating ? "  ·  coordinating " + s.coordinating : "");
        } else {
          const r = roles[id]; applyState(a, r ? r.state : "skipped");
          a.label.textContent = id === "Hermes Director" ? "DIRECTOR" : (SHORT_LABEL[id] || id);
        }
      });
    }

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

    // ---- sizing + loop ----
    let layoutVertical = null;
    function applyLayout(vertical) {
      ZONES[0].cx = vertical ? 0 : -11; ZONES[0].cz = vertical ? -12 : 0;
      ZONES[1].cx = vertical ? 0 : 11; ZONES[1].cz = vertical ? 12.5 : 0;
      ZONES.forEach(function (z) { z.plat.position.set(z.cx, 0.15, z.cz); z.rim.position.set(z.cx, 0.32, z.cz); z.ping.position.set(z.cx, 0.34, z.cz); });
      Object.keys(agents).forEach(function (id) {
        const a = agents[id];
        a.group.position.set(a.zone.cx + a.ox, 0.3, a.zone.cz + a.oz);
        a.headWorld.set(a.zone.cx + a.ox, 3.1, a.zone.cz + a.oz);
      });
      zoneLabels.forEach(function (zl, i) { zl.pos.set(ZONES[i].cx, 0.5, ZONES[i].cz - ZONES[i].r - 1.2); });
      target.set(0, 1.2, vertical ? 0.5 : 0);
      home = vertical ? { theta: 0.0, phi: 0.5, radius: 52 } : { theta: 0.0, phi: 1.02, radius: 36 };
      view.theta = home.theta; view.phi = home.phi; view.radius = home.radius;
    }
    function resize() {
      const w = mount.clientWidth, h = mount.clientHeight || 400;
      const vertical = w < h * 0.95;
      if (vertical !== layoutVertical) { layoutVertical = vertical; applyLayout(vertical); }
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.fov = w < 520 ? 58 : 42;   // wider view on phones so both rooms fit
      camera.updateProjectionMatrix();
      if (!layoutVertical) {   // wide screens: fit the two side-by-side rooms to the window width
        const t = Math.tan((camera.fov / 2) * Math.PI / 180);
        home.radius = Math.max(26, Math.min(62, 23 / (t * (w / h)) * 1.12));
        if (!userMoved) view.radius = home.radius;
      }
    }
    const ro = new ResizeObserver(resize); ro.observe(mount); resize();
    const clock = new THREE.Clock();
    let raf = 0, alive = true, tick = 0;
    const v = new THREE.Vector3();
    function project(pos, elx, hideIfBehind) {
      v.copy(pos).project(camera);
      const w = mount.clientWidth, h = mount.clientHeight;
      const behind = v.z > 1;
      elx.style.display = behind ? "none" : "block";
      elx.style.transform = "translate(" + ((v.x * 0.5 + 0.5) * w).toFixed(1) + "px," + ((-v.y * 0.5 + 0.5) * h).toFixed(1) + "px) translate(-50%,-100%)";
    }
    function frame() {
      if (!alive) return;
      raf = requestAnimationFrame(frame);
      if (document.hidden) return;
      const dt = Math.min(clock.getDelta(), 0.1), t = clock.elapsedTime;
      if ((tick++ % 30) === 0) syncData();
      ambient(t, dt);
      Object.keys(agents).forEach(function (id) { const a = agents[id]; animateAgent(a, t, dt); project(a.headWorld, a.label); });
      for (let i = packets.length - 1; i >= 0; i--) {
        const pk = packets[i], u = (t - pk.t0) / pk.dur;
        if (u >= 1) { pk.b.flashUntil = t + 0.9; pk.b.burstAt = t; scene.remove(pk.mesh); pk.mat.dispose(); packets.splice(i, 1); continue; }
        fromV.copy(pk.a.headWorld); toV.copy(pk.b.headWorld);
        pk.mesh.position.lerpVectors(fromV, toV, u);
        pk.mesh.position.y += Math.sin(Math.PI * u) * 3.2;
        pk.mesh.scale.setScalar(0.8 + 0.5 * Math.sin(Math.PI * u));
      }
      zoneLabels.forEach(function (z) { project(z.pos, z.el); });
      placeCamera();
      renderer.render(scene, camera);
    }
    placeCamera(); syncData(); frame();

    return function cleanup() {
      alive = false; cancelAnimationFrame(raf); ro.disconnect();
      packets.forEach(function (pk) { try { pk.mat.dispose(); } catch (e) { /* ignore */ } });
      disposables.forEach(function (d) { try { d.dispose(); } catch (e) { /* ignore */ } });
      renderer.dispose();
      try { renderer.forceContextLoss(); } catch (e) { /* ignore */ }
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      while (labelsEl.firstChild) labelsEl.removeChild(labelsEl.firstChild);
    };
  }

  function OfficePage(props) {
    const mountRef = useRef(null);
    const labelsRef = useRef(null);
    const dataRef = useRef(props);
    dataRef.current = props;
    const apiRef = useRef({});
    const [sel, setSel] = useState(null);
    const [err, setErr] = useState("");
    const [ready, setReady] = useState(false);
    useEffect(function () {
      let disposed = false;
      let cleanup = function () {};
      loadThree().then(function (THREE) {
        if (disposed || !mountRef.current) return;
        try { cleanup = buildOffice(THREE, mountRef.current, labelsRef.current, dataRef, function (id) { setSel(id); }, apiRef); setReady(true); }
        catch (e) { setErr("This browser could not start the 3D view (WebGL is needed)."); }
      }).catch(function () { if (!disposed) setErr("Could not load the 3D library."); });
      return function () { disposed = true; cleanup(); };
    }, []);

    const team = deriveTeam(props.board);
    const roles = deriveRoles(props.roles);
    const rows = TEAM_ORDER.map(function (id) { return { id: id, label: agentLabel(id), state: team[id].state, extra: id === "default" && team[id].coordinating ? "coordinating " + team[id].coordinating : team[id].running ? team[id].running + " running" : team[id].queued ? team[id].queued + " queued" : team[id].done + " done" }; })
      .concat(ROLE_ORDER.map(function (n) { const r = roles[n]; return { id: n, label: SHORT_LABEL[n] || n, state: r ? r.state : "skipped", extra: r && r.role.worker_used ? r.role.worker_used : "" , role: true }; }));
    let card = null;
    if (sel) {
      const isTeam = TEAM_ORDER.indexOf(sel) >= 0;
      if (isTeam) {
        const s = team[sel];
        card = h("div", { className: "pfmc-ocard" }, [
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: () => setSel(null) }, "✕"),
          h("strong", { key: "n" }, agentLabel(sel)),
          h("span", { key: "s", className: "pfmc-ostate", style: { color: STATE_META[s.state].color } }, STATE_META[s.state].label),
          sel === "default" && s.coordinating ? h("span", { key: "co", className: "pfmc-tb-meta" }, "Coordinating " + s.coordinating + " task" + (s.coordinating > 1 ? "s" : "") + " in flight") : null,
          h("span", { key: "c", className: "pfmc-tb-meta" }, s.running + " running · " + s.queued + " queued · " + s.blocked + " blocked · " + s.done + " done"),
          s.last ? h("span", { key: "l", className: "pfmc-tb-meta" }, "Last finished: " + s.last.title + " (" + ago(s.last.at) + ")") : null,
          h("button", { key: "b", className: "pfmc-btn", onClick: () => props.onGo("tasks") }, "Open task board"),
        ]);
      } else if (roles[sel]) {
        const r = roles[sel];
        card = h("div", { className: "pfmc-ocard" }, [
          h("button", { className: "pfmc-drawer-close", key: "x", onClick: () => setSel(null) }, "✕"),
          h("strong", { key: "n" }, r.role.label || sel),
          h("span", { key: "s", className: "pfmc-ostate", style: { color: STATE_META[r.state].color } }, STATE_META[r.state].label + " · " + r.role.status),
          h("span", { key: "w", className: "pfmc-tb-meta" }, r.role.worker_used ? "Worker: " + r.role.worker_used : (r.role.reason || "No worker recorded")),
          h("button", { key: "b", className: "pfmc-btn", onClick: () => props.onSelectRole(sel) }, "Open details"),
        ]);
      }
    }
    const ctl = function (label, title, fn) { return h("button", { className: "pfmc-octl", title: title, "aria-label": title, onClick: fn }, label); };
    return h(Panel, { title: "3D Office" + (props.push ? "  ● PUSH" : ""), extra: h("span", { className: "pfmc-tb-meta" }, "drag to rotate · scroll or pinch to zoom · tap an agent") }, [
      h("div", { className: "pfmc-office", key: "o" }, [
        h("div", { className: "pfmc-office-mount", ref: mountRef, key: "m" }),
        h("div", { className: "pfmc-olabels", ref: labelsRef, key: "l" }),
        !ready && !err ? h("div", { className: "pfmc-office-msg", key: "ld" }, "Loading the office…") : null,
        err ? h("div", { className: "pfmc-office-msg", key: "er" }, err) : null,
        ready ? h("div", { className: "pfmc-octls", key: "c" }, [
          ctl("＋", "Zoom in", () => apiRef.current.zoom(0.85)), ctl("－", "Zoom out", () => apiRef.current.zoom(1.18)),
          ctl("▲", "Tilt up", () => apiRef.current.tilt(-0.12)), ctl("▼", "Tilt down", () => apiRef.current.tilt(0.12)),
          ctl("⟲", "Reset view", () => apiRef.current.reset()), ctl("◌", "Gentle camera drift on or off", () => apiRef.current.drift()),
        ]) : null,
        card,
      ]),
      h("div", { className: "pfmc-olegend", key: "lg" }, Object.keys(STATE_META).map(function (k) {
        return h("span", { key: k }, [h("i", { key: "i", style: { background: STATE_META[k].color } }), STATE_META[k].label]);
      })),
      h("div", { className: "pfmc-orows", key: "rows" }, rows.map(function (r) {
        return h("button", { key: r.id, className: "pfmc-orow", onClick: () => setSel(r.id), title: r.label }, [
          h("i", { key: "d", style: { background: STATE_META[r.state].color } }), h("span", { key: "n" }, r.label), h("small", { key: "e" }, r.extra),
        ]);
      })),
    ]);
  }

  const PAGES = [["overview", "Overview"], ["office", "Office"], ["tasks", "Tasks"], ["library", "Library"], ["activity", "Activity"], ["artifacts", "Artifacts"]];

  function pageFromHash() {
    const m = (window.location.hash || "").match(/^#\/?([a-z]+)/);
    return m && PAGES.some((p) => p[0] === m[1]) ? m[1] : "overview";
  }

  function PageNav(props) {
    // "Jarvis" lives in Command Center (Gideon's dashboard, on the same host without the :8443 port)
    const jarvisUrl = window.location.protocol + "//" + window.location.hostname + "/#/jarvis";
    return h("nav", { className: "pfmc-nav", "aria-label": "Mission Control pages" }, PAGES.map((pg) => h("button", {
      key: pg[0], "data-active": String(props.page === pg[0]), onClick: () => props.onGo(pg[0]),
    }, [pg[1], props.counts[pg[0]] != null ? h("span", { className: "pfmc-nav-n", key: "n" }, props.counts[pg[0]]) : null]))
      .concat([h("a", { key: "jarvis", className: "pfmc-nav-jarvis", href: jarvisUrl, title: "Open Jarvis: talk to Gideon, voice control, schedule" }, "Jarvis ↗")]));
  }

  function MissionControl() {
    const [projects, setProjects] = useState([]);
    const [projectId, setProjectId] = useState("");
    const [data, setData] = useState(null);
    const [artifact, setArtifact] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(true);
    const [selectedRole, setSelectedRole] = useState(null);
    const [showWorker, setShowWorker] = useState(false);
    const [statusFilter, setStatusFilter] = useState(null);

    const load = useCallback(async function (requestedId) {
      try {
        const catalog = await fetchJSON(API + "/projects");
        setProjects(catalog.projects || []);
        const chosen = requestedId || projectId || (catalog.projects[0] && catalog.projects[0].project_id);
        const snapshot = chosen ? await fetchJSON(API + "/projects/" + encodeURIComponent(chosen)) : await fetchJSON(API + "/snapshot");
        setData(snapshot);
        if (snapshot && snapshot.project_id) setProjectId(snapshot.project_id);
        setError("");
      } catch (err) {
        setError(err && err.message ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }, [projectId]);

    const [push, setPush] = useState(false);
    const [page, setPage] = useState(pageFromHash());
    useEffect(function () {
      const onHash = function () { setPage(pageFromHash()); window.scrollTo(0, 0); };
      window.addEventListener("hashchange", onHash);
      return function () { window.removeEventListener("hashchange", onHash); };
    }, []);
    const go = useCallback(function (pg) { window.location.hash = "#/" + pg; }, []);
    const [board, setBoard] = useState(null);
    const [taskDetail, setTaskDetail] = useState(null);
    const loadBoard = useCallback(async function () {
      try { setBoard(await fetchJSON(API + "/kanban")); } catch (err) { /* board is optional */ }
    }, []);
    const boardRef = useRef(loadBoard);
    boardRef.current = loadBoard;
    const [showNew, setShowNew] = useState(false);
    const [lib, setLib] = useState(null);
    const [libQuery, setLibQuery] = useState("");
    const [libAgent, setLibAgent] = useState("");
    const [note, setNote] = useState(null);
    const libArgs = useRef({ q: "", agent: "" });
    libArgs.current = { q: libQuery, agent: libAgent };
    const loadLib = useCallback(async function () {
      try {
        const a = libArgs.current;
        setLib(await fetchJSON(API + "/library?q=" + encodeURIComponent(a.q) + "&agent=" + encodeURIComponent(a.agent)));
      } catch (err) { /* library is optional */ }
    }, []);
    const libRef = useRef(loadLib);
    libRef.current = loadLib;
    useEffect(function () {
      const t = setTimeout(loadLib, libQuery ? 300 : 0);
      return () => clearTimeout(t);
    }, [libQuery, libAgent, loadLib]);
    const openNote = useCallback(async function (path) {
      try { setNote(await fetchJSON(API + "/library/note?path=" + encodeURIComponent(path))); } catch (err) { setError(err && err.message ? err.message : String(err)); }
    }, []);
    const [assignees, setAssignees] = useState(TEAM_ORDER);
    useEffect(function () {
      fetchJSON(API + "/kanban-meta").then((m) => { if (m && m.assignees && m.assignees.length) setAssignees(m.assignees); }).catch(() => {});
    }, []);
    const post = useCallback(async function (path, body) {
      const r = await fetchJSON(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
      if (r && r.task) setTaskDetail(r.task);
      boardRef.current();
      return r;
    }, []);
    const openTask = useCallback(async function (id) {
      try { setTaskDetail(await fetchJSON(API + "/kanban/" + encodeURIComponent(id))); } catch (err) { setError(err && err.message ? err.message : String(err)); }
    }, []);
    const loadRef = useRef(load);
    loadRef.current = load;

    useEffect(function () { load(); }, [load]);
    useEffect(function () { loadBoard(); }, [loadBoard]);

    // Polling is the fallback: slow when the push stream is connected, fast when it is not.
    useEffect(function () {
      const t = setInterval(() => { loadRef.current(); boardRef.current(); libRef.current(); }, push ? 30000 : 8000);
      return () => clearInterval(t);
    }, [push]);

    useEffect(function () {
      if (!window.EventSource) return undefined;
      let es = null;
      let timer = null;
      try {
        es = new EventSource(API + "/stream");
        es.onopen = function () { setPush(true); };
        es.onmessage = function (m) {
          let ev = null;
          try { ev = JSON.parse(m.data); } catch (err) { return; }
          if (ev && ev.type === "kanban") { boardRef.current(); return; }
          if (ev && ev.type === "library") { libRef.current(); return; }
          if (ev && (ev.type === "changed" || ev.type === "activity")) {
            clearTimeout(timer);
            timer = setTimeout(function () { loadRef.current(); }, 250);
          }
        };
        es.onerror = function () { setPush(false); };
      } catch (err) { setPush(false); }
      return function () { clearTimeout(timer); if (es) es.close(); };
    }, []);

    const openArtifact = useCallback(async function (path) {
      try {
        const result = await fetchJSON(API + "/projects/" + encodeURIComponent(projectId) + "/artifacts/" + encodeURIComponent(path));
        setArtifact(result);
      } catch (err) {
        setError(err && err.message ? err.message : String(err));
      }
    }, [projectId]);

    const decide = useCallback(async function (decision) {
      try {
        await fetchJSON(API + "/projects/" + encodeURIComponent(projectId) + "/approval", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }),
        });
        load(projectId);
      } catch (err) {
        setError(err && err.message ? err.message : String(err));
      }
    }, [projectId, load]);

    if (loading) return h("div", { className: "pfmc-shell" }, h(Empty, null, "Loading Product Factory state…"));
    if (!data || !data.project) return h("div", { className: "pfmc-shell" }, h(Empty, null, (data && data.message) || "No controlled project has run yet."));

    return h("div", { className: "pfmc-shell" }, [
      error ? h("div", { className: "pfmc-error", key: "err" }, error) : null,
      projects.length > 1 ? h(ProjectSwitcher, {
        key: "sel", value: projectId, projects,
        onChange: (id) => { setProjectId(id); load(id); },
      }) : null,
      h(MissionHeader, { key: "header", data, onSelectRole: setSelectedRole, onSelectWorker: () => setShowWorker(true) }),
      h(PageNav, { key: "nav", page, onGo: go, counts: { tasks: board ? board.tasks.length : null, library: lib && lib.available ? lib.total : null, artifacts: (data.artifacts || []).length, activity: (data.activity || []).length } }),
      page === "overview" ? h("div", { key: "ov" }, [
      h("div", { className: "pfmc-grid pfmc-grid-graph", key: "graph-row" }, [
        h(Panel, { title: "Specialist Network", key: "graph", className: "pfmc-panel-fill" }, h(AgentGraph, {
          roles: data.roles, currentSpecialist: data.current_specialist,
          selected: selectedRole, onSelect: setSelectedRole,
        })),
        h("div", { key: "side", style: { display: "flex", flexDirection: "column", gap: 14 } }, [
          h(Panel, { title: "Role Status Breakdown", key: "donut" }, h(StatusDonut, { roles: data.roles, activeFilter: statusFilter, onFilter: setStatusFilter })),
          h(Timeline, { key: "timeline", roles: data.roles, onSelect: setSelectedRole, statusFilter, onFilter: setStatusFilter }),
        ]),
      ]),
        h(Gates, { key: "gates", gates: data.gates }),
      ]) : null,
      page === "office" ? h(OfficePage, { key: "office", board, roles: data.roles, currentSpecialist: data.current_specialist, push, onGo: go, onSelectRole: setSelectedRole }) : null,
      page === "tasks" ? h(TaskBoard, { key: "taskboard", board, push, onOpen: openTask, onNew: () => setShowNew(true) }) : null,
      page === "library" ? h(LibraryPanel, { key: "library", lib, push, query: libQuery, agent: libAgent, onQuery: setLibQuery, onAgent: setLibAgent, onOpen: openNote }) : null,
      page === "activity" ? h(ActivityStream, { key: "stream", activity: data.activity, push }) : null,
      page === "artifacts" ? h(Artifacts, { key: "artifacts", artifacts: data.artifacts, onOpen: openArtifact }) : null,
      data.approval && data.approval.required && data.approval.status === "PENDING"
        ? h(Panel, { key: "approval", title: "Approval Required" }, [
            h("p", { key: "p" }, data.blocker || "This project is waiting on human approval to proceed."),
            h("div", { className: "pfmc-approval-actions", key: "a" }, [
              h("button", { key: "approve", className: "pfmc-approve", onClick: () => decide("APPROVE") }, "Approve"),
              h("button", { key: "reject", className: "pfmc-reject", onClick: () => decide("REJECT") }, "Reject"),
            ]),
          ])
        : null,
      artifact && page === "artifacts" ? h(Panel, { key: "inspector", title: "Artifact: " + artifact.path, className: "pfmc-inspector" },
          h("pre", null, artifact.kind === "json" ? JSON.stringify(artifact.content, null, 2) : artifact.content)) : null,
      h("div", { className: "pfmc-footer", key: "foot" }, "Product Factory · " + (data.updated_at || "")),
      selectedRole ? h(AgentDrawer, {
        key: "drawer",
        role: (data.roles || []).find((r) => r.name === selectedRole),
        onClose: () => setSelectedRole(null),
      }) : null,
      taskDetail ? h(TaskDrawer, {
        key: "taskDrawer", task: taskDetail, assignees, onClose: () => setTaskDetail(null),
        onUnblock: (id, reason) => post("/kanban/" + encodeURIComponent(id) + "/unblock", { reason }),
        onReassign: (id, profile) => post("/kanban/" + encodeURIComponent(id) + "/reassign", { profile }),
      }) : null,
      note ? h(NoteDrawer, { key: "noteDrawer", note, onClose: () => setNote(null) }) : null,
      showNew ? h(NewTaskDialog, { key: "newTask", assignees, onClose: () => setShowNew(false), onCreate: (t) => post("/kanban/tasks", t) }) : null,
      showWorker ? h(WorkerDrawer, { key: "workerDrawer", data, onClose: () => setShowWorker(false) }) : null,
    ]);
  }

  window.__HERMES_PLUGINS__.register("product-factory-mission-control", MissionControl);
})();
