(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React, fetchJSON, authedFetch } = SDK;
  const h = React.createElement;
  const { useCallback, useEffect, useState, useRef } = SDK.hooks;
  const API = "/api/plugins/data-science-career-coach-hub";

  const LEVEL_LABEL = {
    not_assessed: "Not assessed", learning: "Learning", developing: "Developing",
    demonstrated: "Demonstrated", interview_ready: "Interview ready",
  };
  const LEVEL_PCT = { not_assessed: 0, learning: 25, developing: 50, demonstrated: 75, interview_ready: 100 };
  const CATEGORY_ICON = {
    Python: "🐍", SQL: "🗄️", "Data Analysis": "📈", Statistics: "📐", "Machine Learning": "🤖",
    "AI Engineering": "🧠", Projects: "🛠️", "Interview Preparation": "🎤", "Career Preparation": "🎯",
  };
  const ACTIVITY_ICON = {
    session: "✅", topic_update: "📘", interview: "🎤", project: "🛠️", job: "💼",
    goal: "🎯", career_update: "🧭", skill_update: "📊", note: "📝",
  };
  const KP_ICONS = ["📗", "✏️", "🗑️", "🧬", "🔑", "💡"];

  function fmtDate(ts) {
    if (!ts) return "-";
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  }
  function fmtElapsed(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + String(s).padStart(2, "0");
  }
  function fmtTime(ts) {
    return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  function Panel(props) {
    return h("section", { className: "dscc-panel " + (props.className || "") }, [
      h("div", { className: "dscc-panel-head", key: "h" }, [
        h("h2", { key: "t" }, props.title),
        props.extra || null,
      ]),
      h("div", { className: "dscc-panel-body", key: "b" }, props.children),
    ]);
  }

  function Empty(props) { return h("div", { className: "dscc-empty" }, props.children); }

  function Bar(props) {
    const pct = props.pct == null ? null : Math.max(0, Math.min(100, props.pct));
    return h("div", { className: "dscc-bar-row" }, [
      h("span", { className: "dscc-bar-label", key: "l" }, props.label),
      h("div", { className: "dscc-bar-track", key: "t" },
        pct == null ? null : h("div", { className: "dscc-bar-fill", style: { width: pct + "%" } })),
      h("span", { className: "dscc-bar-pct", key: "p" }, pct == null ? "Not assessed" : pct + "%"),
    ]);
  }

  function Toast(props) {
    if (!props.toast) return null;
    return h("div", { className: "dscc-toast dscc-toast-" + props.toast.type }, props.toast.message);
  }

  // Real pages only - no nav entries for sections with no backing data ("dead controls").
  // Added "analytics" this round now that /stats gives it real numbers; still no
  // "Settings" entry - there is nothing real to configure there yet.
  const NAV_ITEMS = [
    ["live", "🎥", "Live Coach"], ["dashboard", "🏠", "Dashboard"], ["roadmap", "🗺️", "Learning Hub"],
    ["progress", "📊", "My Progress"], ["projects", "🛠️", "Practice & Projects"], ["jobs", "💼", "Jobs"],
    ["interviews", "🎤", "Interview Prep"], ["goals", "🎯", "Goals & Plans"], ["analytics", "📈", "Analytics"],
  ];

  function SideNav(props) {
    return h("nav", { className: "dscc-sidenav" + (props.open ? " open" : "") }, [
      h("div", { className: "dscc-sidenav-brand", key: "brand" }, [
        h("span", { className: "dscc-sidenav-logo", key: "l" }, "🎓"),
        h("span", { key: "t" }, "Career Coach"),
      ]),
      h("div", { className: "dscc-sidenav-items", key: "items" }, NAV_ITEMS.map(([key, icon, label]) =>
        h("button", {
          key, className: "dscc-sidenav-item" + (props.page === key ? " active" : ""),
          onClick: () => { props.onGo(key); props.onClose && props.onClose(); },
        }, [h("span", { className: "dscc-sidenav-icon", key: "i" }, icon), h("span", { key: "t" }, label)])
      )),
    ]);
  }

  function Avatar(props) {
    // Real portrait when uploaded (profiles/data-science-career-coach/assets/coach-reference.jpg),
    // else an SVG placeholder - never a fabricated "listening/speaking" state baked into the
    // image; real state is shown separately (CoachStateBadge), driven only by real signals.
    const [hasPortrait, setHasPortrait] = useState(null);
    useEffect(() => {
      fetchJSON(API + "/avatar/status").then((r) => setHasPortrait(!!r.has_portrait)).catch(() => setHasPortrait(false));
    }, []);
    const cls = "dscc-avatar dscc-avatar-breathing" + (props.large ? " dscc-avatar-lg" : "");
    if (hasPortrait) {
      return h("img", { className: cls, src: API + "/avatar/portrait", alt: "Coach portrait" });
    }
    return h("div", { className: cls + " dscc-avatar-placeholder" },
      h("svg", { viewBox: "0 0 24 24", width: props.large ? 56 : 24, height: props.large ? 56 : 24, fill: "none", stroke: "currentColor", strokeWidth: 1.6 },
        h("path", { d: "M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-4.2 0-7.5 2.3-7.5 5v1.5h15V19c0-2.7-3.3-5-7.5-5Z" })));
  }

  function Header(props) {
    const career = (props.profile && props.profile.career) || {};
    return h("div", { className: "dscc-header" }, [
      h(Avatar, { key: "av" }),
      h("div", { className: "dscc-header-text", key: "t" }, [
        h("h1", { key: "h" }, "Precious AI Data Science & Career Coach"),
        h("p", { key: "p" }, "Your personal Data Science lecturer, productivity coach and career guide."),
        career.career_goal ? h("p", { key: "g", className: "dscc-goal" }, "Goal: " + career.career_goal) : null,
      ]),
      h("span", { className: "dscc-status-pill", key: "s" }, "Online"),
    ]);
  }

  function TodayPanel(props) {
    const t = props.today || {};
    const revisions = t.due_revisions || [];
    const inProgress = t.in_progress_topics || [];
    const goals = t.active_goals || [];
    const suggestion = t.suggested_next_topic;
    const onSelect = props.onSelect;
    const row = (icon, pillCls, pillLabel, label, key) => h("div", {
      className: "dscc-plan-item" + (onSelect ? " clickable" : ""), key,
      onClick: onSelect ? () => onSelect(label) : undefined,
    }, [
      h("span", { className: "dscc-plan-icon", key: "ic" }, icon),
      h("span", { className: "dscc-pill dscc-pill-" + pillCls, key: "p" }, pillLabel),
      h("span", { key: "t" }, label),
      onSelect ? h("span", { className: "dscc-plan-chevron", key: "c" }, "›") : null,
    ]);
    if (!revisions.length && !inProgress.length && !goals.length && !suggestion) {
      return h(Panel, { title: "Today's Plan" }, [
        h(Empty, { key: "e" }, "No plan generated yet."),
        props.onGenerate ? h("button", { key: "g", className: "dscc-quick-btn", onClick: props.onGenerate }, "Generate Today's Plan") : null,
      ]);
    }
    return h(Panel, { title: "Today's Plan", extra: h("span", { className: "dscc-panel-date" }, new Date().toLocaleDateString(undefined, { weekday: "short", day: "2-digit", month: "short" })) }, [
      suggestion ? row("▶", "new", "Next up", suggestion.topic + " (" + suggestion.phase + ")", "sugg") : null,
      revisions.length ? h("div", { key: "rev" }, [
        h("h3", { className: "dscc-subhead", key: "h" }, "Due for revision"),
        ...revisions.map((r) => row("🔁", "revise", "Revise", r.topic_name, r.topic_id)),
      ]) : null,
      inProgress.length ? h("div", { key: "prog" }, [
        h("h3", { className: "dscc-subhead", key: "h" }, "In progress"),
        ...inProgress.map((r) => row("📘", "progress", r.status, r.topic_name, r.topic_id)),
      ]) : null,
      goals.length ? h("div", { key: "goals" }, [
        h("h3", { className: "dscc-subhead", key: "h" }, "Active goals"),
        ...goals.map((g) => row("🎯", "goal", g.kind, g.description, g.id)),
      ]) : null,
    ]);
  }

  function ProgressPanel(props) {
    const cats = props.progress ? props.progress.categories : {};
    const entries = Object.keys(cats || {});
    return h(Panel, {
      title: "Learning Progress",
      extra: props.onViewDetails ? h("a", { className: "dscc-view-link", onClick: props.onViewDetails }, "View Details →") : null,
    }, entries.length
      ? entries.map((k) => h("div", { className: "dscc-progress-row", key: k }, [
          h("span", { className: "dscc-cat-icon", key: "i" }, CATEGORY_ICON[k] || "•"),
          h(Bar, { key: "b", label: k, pct: cats[k] }),
        ]))
      : h(Empty, null, "No progress recorded yet."));
  }

  function EditGoalModal(props) {
    const career = props.initial || {};
    let initRoles = career.target_roles;
    if (typeof initRoles === "string") { try { initRoles = JSON.parse(initRoles); } catch (e) { initRoles = []; } }
    const [goalText, setGoalText] = useState(career.career_goal || "");
    const [rolesText, setRolesText] = useState((initRoles || []).join(", "));
    const [saving, setSaving] = useState(false);

    const save = () => {
      setSaving(true);
      fetchJSON(API + "/career", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          career_goal: goalText.trim() || null,
          target_roles: rolesText.split(",").map((s) => s.trim()).filter(Boolean),
        }),
      }).then(() => {
        props.showToast("Career goal updated", "success");
        props.onSaved();
        props.onClose();
      }).catch((e) => props.showToast("Could not save goal: " + String((e && e.message) || e), "error"))
        .finally(() => setSaving(false));
    };

    return h("div", { className: "dscc-modal-backdrop", onClick: props.onClose }, [
      h("div", { className: "dscc-modal", key: "m", onClick: (e) => e.stopPropagation() }, [
        h("h3", { key: "t" }, "Set Career Goal"),
        h("label", { className: "dscc-modal-label", key: "l1" }, "Career goal / summary"),
        h("textarea", {
          key: "i1", className: "dscc-modal-textarea", value: goalText, rows: 3,
          placeholder: "e.g. Become a Machine Learning Engineer within 12 months",
          onChange: (e) => setGoalText(e.target.value),
        }),
        h("label", { className: "dscc-modal-label", key: "l2" }, "Target roles (comma-separated)"),
        h("input", {
          key: "i2", className: "dscc-modal-input", value: rolesText,
          placeholder: "e.g. Data Scientist, AI Engineer",
          onChange: (e) => setRolesText(e.target.value),
        }),
        h("div", { className: "dscc-modal-actions", key: "a" }, [
          h("button", { key: "c", className: "dscc-quick-btn", onClick: props.onClose }, "Cancel"),
          h("button", { key: "s", className: "dscc-live-send", disabled: saving, onClick: save }, saving ? "Saving…" : "Save Goal"),
        ]),
      ]),
    ]);
  }

  function CareerGoalPanel(props) {
    const [editing, setEditing] = useState(false);
    const career = (props.profile && props.profile.career) || {};
    let roles = career.target_roles;
    if (typeof roles === "string") { try { roles = JSON.parse(roles); } catch (e) { roles = []; } }
    const hasGoal = !!(career.career_goal || (roles && roles.length));
    return h(Panel, {
      title: "Career Goal",
      extra: h("a", { className: "dscc-view-link", onClick: () => setEditing(true) }, hasGoal ? "Edit Goal" : "Set Goal"),
    }, [
      hasGoal ? h("div", { className: "dscc-goal-card", key: "card" }, [
        h("span", { className: "dscc-goal-icon", key: "i" }, "🎯"),
        h("div", { key: "t" }, [
          career.career_goal ? h("div", { className: "dscc-goal-role", key: "r" }, career.career_goal) : null,
          roles && roles.length ? h("div", { className: "dscc-goal-tags", key: "tags" },
            roles.map((r, i) => h("span", { className: "dscc-pill dscc-pill-goal", key: i }, r))) : null,
        ]),
      ]) : h(Empty, { key: "e" }, "No career goal set yet."),
      editing ? h(EditGoalModal, {
        key: "modal", initial: career, onClose: () => setEditing(false),
        onSaved: props.onGoalUpdated, showToast: props.showToast,
      }) : null,
    ]);
  }

  function RoadmapPanel(props) {
    const phases = props.roadmap || [];
    return h(Panel, { title: "Career Roadmap" }, phases.length
      ? phases.map((p) => h("div", { className: "dscc-roadmap-item", key: p.phase_id }, [
          h("span", { className: "dscc-phase-num", key: "n" }, p.order_index),
          h("div", { key: "b" }, [
            h("div", { className: "dscc-phase-name", key: "t" }, p.phase_name),
            h("div", { className: "dscc-phase-items", key: "i" }, p.items.join(" · ")),
          ]),
        ]))
      : h(Empty, null, "Roadmap not initialised."));
  }

  function ActivityPanel(props) {
    const [expanded, setExpanded] = useState(false);
    const items = props.activity || [];
    const shown = expanded ? items : items.slice(0, 5);
    return h(Panel, {
      title: "Recent Activity",
      extra: items.length > 5 ? h("a", { className: "dscc-view-link", onClick: () => setExpanded((v) => !v) }, expanded ? "Show less" : "View All →") : null,
    }, shown.length
      ? shown.map((a) => h("div", { className: "dscc-activity-row", key: a.id }, [
          h("span", { className: "dscc-activity-icon", key: "i" }, ACTIVITY_ICON[a.kind] || "•"),
          h("div", { key: "t" }, [
            h("div", { className: "dscc-activity-summary", key: "s" }, a.summary),
            h("div", { className: "dscc-activity-time-v2", key: "tm" }, fmtDate(a.created_at)),
          ]),
        ]))
      : h(Empty, null, "No activity yet."));
  }

  function SkillsPanel(props) {
    const skills = props.progress ? props.progress.skills : [];
    return h(Panel, { title: "Career Skill Matrix" }, (skills && skills.length)
      // not_assessed must render as "Not assessed" text, not a fabricated "0%" -
      // Bar only does that when pct is null, so map not_assessed to null explicitly.
      ? skills.map((s) => h(Bar, { key: s.skill_name, label: s.skill_name, pct: s.level === "not_assessed" ? null : LEVEL_PCT[s.level] }))
      : h(Empty, null, "No skills assessed yet."));
  }

  function StatsPanel(props) {
    const s = props.stats;
    if (!s) return null;
    const items = [
      ["⏱️", s.total_learning_hours + "h", "Learning hours"],
      ["✅", s.topics_completed + " / " + s.total_topics, "Topics completed"],
      ["🔥", s.current_streak_days + " day" + (s.current_streak_days === 1 ? "" : "s"), "Current streak"],
      ["🎤", s.interview_sessions, "Interview sessions"],
      ["🛠️", s.projects, "Projects"],
      ["📅", s.revision_queue, "Due for revision"],
    ];
    return h(Panel, { title: "My Progress — Overview" },
      h("div", { className: "dscc-stats-grid" }, items.map(([icon, value, label], i) =>
        h("div", { className: "dscc-stat-card", key: i }, [
          h("span", { className: "dscc-stat-icon", key: "i" }, icon),
          h("div", { className: "dscc-stat-value", key: "v" }, value),
          h("div", { className: "dscc-stat-label", key: "l" }, label),
        ]))));
  }

  function ProjectsPage(props) {
    const items = props.projects || [];
    return h(Panel, { title: "Portfolio Projects" }, items.length
      ? items.map((p) => h("div", { className: "dscc-card", key: p.id }, [
          h("h3", { key: "t" }, p.title),
          h("p", { key: "d" }, p.description || "No description yet."),
          h("div", { className: "dscc-card-meta", key: "m" }, [
            h("span", { className: "dscc-pill", key: "s" }, p.status),
            p.repo_url ? h("a", { key: "r", href: p.repo_url, target: "_blank", rel: "noreferrer" }, "Repo") : null,
          ]),
        ]))
      : h(Empty, null, "No projects tracked yet. Ask the coach to help you plan one via /project."));
  }

  function JobsPage(props) {
    const items = props.jobs || [];
    return h(Panel, { title: "Job Applications" }, items.length
      ? items.map((j) => h("div", { className: "dscc-card", key: j.id }, [
          h("h3", { key: "t" }, j.role + " @ " + j.company),
          h("div", { className: "dscc-card-meta", key: "m" }, h("span", { className: "dscc-pill", key: "s" }, j.status)),
          j.next_action ? h("p", { key: "n" }, "Next: " + j.next_action) : null,
        ]))
      : h(Empty, null, "No jobs tracked yet. Paste a job description to the coach via /jobs to start."));
  }

  const SCORE_DIM_LABEL = {
    technical_accuracy: "Technical accuracy", clarity: "Clarity", structure: "Structure",
    communication: "Communication", confidence: "Confidence", completeness: "Completeness",
  };

  function InterviewAnalyticsPanel(props) {
    const a = props.analytics;
    if (!a || !a.total_interviews) {
      return h(Panel, { title: "Interview Analytics" }, h(Empty, null, "No completed mock interviews yet — analytics build up once you've done a few."));
    }
    const dims = Object.keys(SCORE_DIM_LABEL).filter((d) => a.averages[d] != null);
    return h(Panel, { title: "Interview Analytics — " + a.total_interviews + " interview" + (a.total_interviews === 1 ? "" : "s") }, [
      dims.length ? h("div", { key: "avg" }, [
        h("h3", { className: "dscc-subhead", key: "h" }, "Average scores"),
        ...dims.map((d) => h(Bar, { key: d, label: SCORE_DIM_LABEL[d], pct: a.averages[d] })),
      ]) : null,
      a.frequently_missed_concepts.length ? h("div", { key: "miss" }, [
        h("h3", { className: "dscc-subhead", key: "h" }, "Frequently missed concepts"),
        ...a.frequently_missed_concepts.map((c) => h("div", { className: "dscc-plan-item", key: c.concept }, [
          h("span", { className: "dscc-pill dscc-pill-revise", key: "p" }, "×" + c.count),
          h("span", { key: "t" }, c.concept),
        ])),
      ]) : null,
    ]);
  }

  function InterviewsPage(props) {
    const items = props.interviews || [];
    return h("div", null, [
      h(InterviewAnalyticsPanel, { key: "analytics", analytics: props.analytics }),
      h(Panel, { title: "Interview History", key: "history" }, items.length
        ? items.map((iv) => h("div", { className: "dscc-card", key: iv.id }, [
            h("h3", { key: "t" }, iv.interview_type + " — " + iv.role),
            h("div", { className: "dscc-card-meta", key: "m" }, [
              h("span", { className: "dscc-pill", key: "d" }, iv.difficulty),
              h("span", { key: "dt" }, fmtDate(iv.created_at)),
            ]),
            iv.feedback ? h("p", { key: "f" }, iv.feedback) : null,
          ]))
        : h(Empty, null, "No mock interviews yet. Say \"mock interview me\" or use /interview to start one.")),
    ]);
  }

  function GoalsPage(props) {
    const items = props.goals || [];
    return h(Panel, { title: "Goals & Plans" }, items.length
      ? items.map((g) => h("div", { className: "dscc-card", key: g.id }, [
          h("h3", { key: "t" }, g.kind),
          h("p", { key: "d" }, g.description),
          h("span", { className: "dscc-pill", key: "s" }, g.status),
        ]))
      : h(Empty, null, "No goals set yet."));
  }

  function AnalyticsPage(props) {
    return h("div", null, [
      h(StatsPanel, { key: "stats", stats: props.stats }),
      h(InterviewAnalyticsPanel, { key: "iv", analytics: props.analytics }),
      h(ProgressPanel, { key: "prog", progress: props.progress }),
    ]);
  }

  const QUICK_ACTIONS = [
    ["🔁", "Explain Again", "Please explain that again, a bit more simply."],
    ["✨", "Simplify This", "Can you simplify that further, with a simpler analogy?"],
    ["💡", "Give an Example", "Can you give me a concrete example?"],
    ["❓", "Ask Me a Question", "Ask me a question to check my understanding."],
    ["📝", "Quiz Me", "Quiz me on what we've covered so far."],
    ["💻", "Show Code", "Show me the code example for this again."],
    ["➡️", "Next Topic", "I'm ready — what's next?"],
    ["🎤", "Mock Interview", "Let's start a mock interview for a role I'm targeting."],
  ];

  const LESSON_STAGES = [
    ["explain_concept", "Explain Concept", "We're here now"], ["live_coding", "Live Coding", "See it in action"],
    ["your_turn", "Your Turn", "Try it yourself"], ["quiz", "Quiz", "Check your understanding"],
    ["summary", "Summary", "Key takeaways"],
  ];

  const STAGE_STATE_LABEL = {
    explain_concept: "Explaining", live_coding: "Live Coding", your_turn: "Waiting on you",
    quiz: "Quizzing", summary: "Summarising", interview: "Interviewing",
  };

  function deriveCoachState(sending, paused, liveState) {
    if (paused) return { key: "paused", label: "Paused" };
    if (sending) return { key: "thinking", label: "Thinking…" };
    if (liveState && liveState.stage && liveState.stage !== "idle") {
      return { key: liveState.stage, label: STAGE_STATE_LABEL[liveState.stage] || liveState.stage };
    }
    return { key: "idle", label: "Ready" };
  }

  function CoachStateBadge(props) {
    const s = props.state;
    return h("span", { className: "dscc-coach-state dscc-coach-state-" + s.key + (props.corner ? " corner" : "") }, [
      h("span", { className: "dscc-coach-state-dot", key: "d" }),
      h("span", { key: "t" }, s.label),
    ]);
  }

  function LessonPanel(props) {
    const s = props.liveState;
    if (!s || !s.stage || s.stage === "idle") {
      return h(Panel, { title: "Today's Lesson" }, h(Empty, null, "No lesson in progress yet — start one from the chat below, or pick a topic from the Learning Hub."));
    }
    if (s.stage === "interview") {
      return h(Panel, { title: "Today's Lesson", extra: h("span", { className: "dscc-pill dscc-pill-progress" }, "Interview") },
        h("div", { className: "dscc-lesson-head" }, [
          h("span", { className: "dscc-lesson-icon", key: "i" }, "🎤"),
          h("div", { className: "dscc-lesson-title", key: "t" }, "Mock interview in progress" + (s.topic_name ? " — " + s.topic_name : "")),
        ]));
    }
    const currentIdx = LESSON_STAGES.findIndex(([key]) => key === s.stage);
    return h(Panel, { title: "Today's Lesson", extra: h("span", { className: "dscc-pill dscc-pill-progress" }, "In Progress") }, [
      h("div", { className: "dscc-lesson-head", key: "head" }, [
        h("span", { className: "dscc-lesson-icon", key: "i" }, "🐍"),
        h("div", { className: "dscc-lesson-title", key: "t" }, s.topic_name || "Current topic"),
        h("span", { className: "dscc-lesson-fraction", key: "f" }, (currentIdx + 1) + "/5"),
      ]),
      h("div", { className: "dscc-lesson-progress-track", key: "track" },
        h("div", { className: "dscc-lesson-progress-fill", style: { width: ((currentIdx + 1) / 5 * 100) + "%" } })),
      h("div", { className: "dscc-stage-row-v2", key: "stages" }, LESSON_STAGES.map(([key, label, sub], i) =>
        h("div", { className: "dscc-stage-step-v2" + (i === currentIdx ? " current" : i < currentIdx ? " done" : ""), key }, [
          h("span", { className: "dscc-stage-num", key: "n" }, i < currentIdx ? "✓" : i + 1),
          h("span", { className: "dscc-stage-label", key: "l" }, label),
          i === currentIdx ? h("span", { className: "dscc-stage-sub", key: "s" }, sub) : null,
        ]))),
    ]);
  }

  // Pull a fenced code block (+ language) and bullet-style lines out of the coach's own
  // latest reply - real content the coach actually wrote, not invented lesson data.
  function extractTeachingContent(text) {
    if (!text) return { code: null, language: null, points: [] };
    const codeMatch = text.match(/```([a-zA-Z]*)\n?([\s\S]*?)```/);
    const code = codeMatch ? codeMatch[2].trim() : null;
    const language = codeMatch && codeMatch[1] ? codeMatch[1] : null;
    const withoutCode = text.replace(/```[\s\S]*?```/g, "");
    const points = withoutCode.split("\n")
      .map((l) => l.trim())
      .filter((l) => /^([-*•]|\d+[.)])\s+/.test(l))
      .map((l) => l.replace(/^([-*•]|\d+[.)])\s+/, ""))
      .slice(0, 6);
    return { code, language, points };
  }

  function TeachingArea(props) {
    const { code, language, points } = extractTeachingContent(props.lastCoachText);
    const [codeExpanded, setCodeExpanded] = useState(false);
    const [running, setRunning] = useState(false);
    if (!code && !points.length) return null;

    const copyCode = () => {
      if (!code || !navigator.clipboard) return;
      navigator.clipboard.writeText(code)
        .then(() => props.showToast("Code copied to clipboard", "success"))
        .catch(() => props.showToast("Could not copy code", "error"));
    };
    const runCode = () => {
      if (!code || running) return;
      setRunning(true);
      props.onRunCode(code).finally(() => setRunning(false));
    };
    const saveNotes = () => {
      fetchJSON(API + "/notes", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: points.join("\n"), topic_name: props.topicName || null }),
      }).then(() => props.showToast("Notes saved", "success"))
        .catch((e) => props.showToast("Could not save notes: " + String((e && e.message) || e), "error"));
    };

    return h("div", { className: "dscc-teach-grid" + (codeExpanded ? " code-expanded" : "") }, [
      h(Panel, {
        title: "Live Code Example", key: "code", className: "dscc-teach-panel",
        extra: h("div", { className: "dscc-teach-panel-actions" }, [
          language ? h("span", { className: "dscc-lang-badge", key: "lang" }, language) : null,
          code ? h("button", { key: "copy", className: "dscc-icon-btn", onClick: copyCode, title: "Copy code" }, "📋") : null,
          code ? h("button", { key: "exp", className: "dscc-icon-btn", onClick: () => setCodeExpanded((v) => !v), title: codeExpanded ? "Collapse" : "Expand" }, codeExpanded ? "⤡" : "⤢") : null,
        ]),
      }, [
        code ? h("pre", { className: "dscc-code-block", key: "pre" }, code) : h(Empty, { key: "e" }, "No code in this reply."),
        code ? h("button", {
          className: "dscc-run-btn", key: "run", disabled: running, onClick: runCode,
          title: "Sends the code to the coach for a step-by-step AI trace-through (no sandboxed execution wired yet)",
        }, running ? "Tracing…" : "▶ Trace Code") : null,
      ]),
      h(Panel, {
        title: "Key Points", key: "points", className: "dscc-teach-panel",
        extra: points.length ? h("button", { className: "dscc-icon-btn-text", onClick: saveNotes }, "💾 Save Notes") : null,
      }, points.length
        ? h("ul", { className: "dscc-keypoints-list" }, points.map((p, i) => h("li", { key: i }, [
            h("span", { className: "dscc-kp-icon", key: "ic" }, KP_ICONS[i % KP_ICONS.length]),
            h("span", { key: "t" }, p),
          ])))
        : h(Empty, null, "No key points captured from this reply.")),
    ]);
  }

  function MessageBubble(props) {
    const m = props.msg;
    return h("div", { className: "dscc-msg-row dscc-msg-row-" + m.role }, [
      m.role === "coach" ? h(Avatar, { key: "av" }) : null,
      h("div", { className: "dscc-msg-col", key: "col" }, [
        h("div", { className: "dscc-msg-meta", key: "meta" }, [
          h("span", { className: "dscc-msg-name", key: "n" }, m.role === "coach" ? "AI Career Coach" : "You"),
          h("span", { className: "dscc-msg-time", key: "t" }, fmtTime(m.ts)),
        ]),
        h("div", { className: "dscc-bubble dscc-bubble-" + m.role, key: "b" }, [
          m.text,
          m.interviewScore ? h(InlineScoreCard, { key: "score", score: m.interviewScore }) : null,
        ]),
      ]),
    ]);
  }

  function InlineScoreCard(props) {
    const s = props.score;
    const dims = Object.keys(SCORE_DIM_LABEL).filter((d) => s.scores && s.scores[d] != null);
    if (!dims.length) return null;
    return h("div", { className: "dscc-inline-score" }, [
      h("div", { className: "dscc-subhead", key: "h" }, "Interview scored"),
      ...dims.map((d) => h(Bar, { key: d, label: SCORE_DIM_LABEL[d], pct: s.scores[d] })),
    ]);
  }

  // Live Conversation voice pipeline: real Deepgram streaming STT (server relay,
  // see plugin_api.py's /voice/deepgram/stream), real Cartesia streaming TTS,
  // and an optional LiveAvatar (HeyGen) video avatar in LITE/Avatar-Only mode.
  // VAD/turn-taking is Deepgram's own (SpeechStarted for barge-in, speech_final
  // for end-of-utterance) - no client-side energy VAD needed anymore.
  const DG_SAMPLE_RATE = 16000;
  // LiveAvatar's own documented requirement for LITE-mode lip-sync audio is
  // PCM16 24kHz mono - Cartesia is asked to synthesize at exactly that rate so
  // the same bytes can be played locally AND fed to the avatar with zero
  // client-side resampling.
  const CARTESIA_SAMPLE_RATE = 24000;
  const SIMLI_SAMPLE_RATE = 16000;

  const VOICE_STATE_LABEL = {
    listening: "Listening…", transcribing: "Transcribing…", thinking: "Thinking…",
    speaking: "Speaking…", reconnecting: "Reconnecting…",
    provider_unavailable: "Voice provider unavailable", error: "Voice error",
  };
  const AVATAR_STATUS_LABEL = {
    connecting: "Avatar connecting…", connected: "Avatar live",
    reconnecting: "Reconnecting avatar…", unavailable: "Static fallback — voice continues",
  };
  // HeyGen LiveAvatar's Free tier caps a session at roughly 2 minutes - refresh
  // proactively well before that so the video never actually goes blank, and
  // still detect+recover reactively (track/room/ws events) for anything that
  // disconnects earlier than expected.
  const AVATAR_PROACTIVE_REFRESH_MS = 100000;
  const AVATAR_HEALTH_CHECK_MS = 4000;
  const AVATAR_MAX_RECONNECT_ATTEMPTS = 4;
  const AVATAR_SPEAK_END_TIMEOUT_MS = 6000;

  function floatTo16BitPCM(float32Array) {
    const out = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  // Simple averaging downsampler (mic AudioContext is usually 48kHz; Deepgram
  // wants 16kHz linear16) - adequate for speech, no external resampler needed.
  function downsampleTo16k(float32Array, inputSampleRate) {
    if (inputSampleRate === DG_SAMPLE_RATE) return float32Array;
    const ratio = inputSampleRate / DG_SAMPLE_RATE;
    const newLength = Math.round(float32Array.length / ratio);
    const result = new Float32Array(newLength);
    let offsetResult = 0, offsetBuffer = 0;
    while (offsetResult < newLength) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < float32Array.length; i++) { accum += float32Array[i]; count++; }
      result[offsetResult] = count ? accum / count : 0;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }

  function base64ToInt16(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Int16Array(bytes.buffer);
  }

  function mintWsTicket() {
    return (authedFetch ? authedFetch("/api/auth/ws-ticket", { method: "POST" }) : fetch("/api/auth/ws-ticket", { method: "POST", credentials: "same-origin" }))
      .then((r) => r.json()).then((d) => d.ticket);
  }

  // LiveKit's browser SDK has no build step in this plugin, so it's loaded
  // from a CDN on first use (real HeyGen LiveAvatar sessions are delivered
  // over a LiveKit WebRTC room) - loaded once, reused for every session.
  let _liveKitSdkPromise = null;
  function loadLiveKitSdk() {
    if (window.LivekitClient) return Promise.resolve(window.LivekitClient);
    if (_liveKitSdkPromise) return _liveKitSdkPromise;
    _liveKitSdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js";
      script.onload = () => resolve(window.LivekitClient);
      script.onerror = () => reject(new Error("Failed to load LiveKit SDK"));
      document.head.appendChild(script);
    });
    return _liveKitSdkPromise;
  }

  // Simli's official simli-client package is real-bundled with esbuild
  // (see simli-build/) and served from this plugin's own dist/vendor/ - not
  // a CDN, per its CommonJS-only distribution having no working CDN/ESM
  // bundle path (confirmed: a CDN UMD fetch and jsDelivr's ESM auto-bundler
  // both failed for this package).
  let _simliSdkPromise = null;
  function loadSimliSdk() {
    if (window.SimliClientBundle) return Promise.resolve(window.SimliClientBundle);
    if (_simliSdkPromise) return _simliSdkPromise;
    _simliSdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/dashboard-plugins/data-science-career-coach-hub/dist/vendor/simli-client.bundle.js";
      script.onload = () => resolve(window.SimliClientBundle);
      script.onerror = () => reject(new Error("Failed to load Simli SDK bundle"));
      document.head.appendChild(script);
    });
    return _simliSdkPromise;
  }

  function LiveCoachPage(props) {
    const [messages, setMessages] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    const [input, setInput] = useState("");
    const [sending, setSending] = useState(false);
    const [paused, setPaused] = useState(false);
    const [error, setError] = useState(null);
    const [startedAt, setStartedAt] = useState(null);
    const [elapsed, setElapsed] = useState(0);
    const [liveState, setLiveState] = useState(null);
    const [voiceOn, setVoiceOn] = useState(false);
    const [transcriptOpen, setTranscriptOpen] = useState(true);
    const [fullscreen, setFullscreen] = useState(false);
    const [prevInterviewCount, setPrevInterviewCount] = useState(null);
    // One-shot record/transcribe/review-before-send (typed-fallback friendly).
    const [recording, setRecording] = useState(false);
    const [transcribing, setTranscribing] = useState(false);
    const mediaRecorderRef = useRef(null);
    // Continuous "Start Live Conversation" mode: real turn-taking, no manual Send.
    // STT = Deepgram (server relay), TTS = Cartesia (streaming), video = LiveAvatar
    // (optional, best-effort - voice conversation never depends on it working).
    const [liveConvo, setLiveConvo] = useState(false);
    const [voiceMode, setVoiceMode] = useState("idle"); // idle|listening|transcribing|thinking|speaking|reconnecting|provider_unavailable|error
    const [interimText, setInterimText] = useState("");
    const [avatarStatus, setAvatarStatus] = useState("idle"); // idle|connecting|connected|reconnecting|unavailable
    // Live diagnostic panel - real values only, updated at every actual
    // provider transition (never silently switched, per explicit requirement).
    const [providerState, setProviderState] = useState({ stt: "-", llm: "-", tts: "-", avatar: "-" });
    const liveConvoRef = useRef(false);
    const voiceModeRef = useRef("idle");
    const streamRef = useRef(null);
    const timingRef = useRef({});
    const transcriptRef = useRef(null);
    const audioRef = useRef(null);
    const sessionIdRef = useRef(null);
    const liveIdRef = useRef(null);
    // Deepgram mic-capture pipeline
    const dgSocketRef = useRef(null);
    const dgAudioCtxRef = useRef(null);
    const dgProcessorRef = useRef(null);
    const dgReconnectingRef = useRef(false);
    // Cartesia: one persistent WS per Live Conversation session (not per turn -
    // reconnecting every turn was the real cause of intermittent TTS failures).
    // Each turn gets its own context_id and a monotonic turnId; barge-in just
    // bumps turnId so any in-flight chunks from an interrupted turn are
    // silently dropped rather than requiring a socket teardown.
    const cartesiaSocketRef = useRef(null);
    const cartesiaPlaybackCtxRef = useRef(null);
    const cartesiaNextStartRef = useRef(0);
    const cartesiaActiveSourcesRef = useRef([]);
    const cartesiaTurnIdRef = useRef(0);
    const cartesiaContextMapRef = useRef(new Map());
    // Avatar: Simli (primary) -> LiveAvatar/HeyGen (fallback) -> static photo.
    // avatarProviderRef tracks which one is actually active ("simli"|"heygen"|null)
    // so shared code (Cartesia audio routing, barge-in) dispatches correctly.
    const avatarProviderRef = useRef(null);
    const simliClientRef = useRef(null);
    const simliAudioRef = useRef(null);
    // LiveAvatar/HeyGen (LiveKit room for video + a plain WS for LITE-mode commands)
    const avatarRoomRef = useRef(null);
    const avatarWsRef = useRef(null);
    const avatarSessionIdRef = useRef(null);
    const avatarReadyRef = useRef(false);
    const avatarVideoRef = useRef(null);
    const avatarHealthTimerRef = useRef(null);
    const avatarProactiveTimerRef = useRef(null);
    const avatarReconnectAttemptsRef = useRef(0);
    const avatarSpeakEndSafetyRef = useRef(null);

    const setMode = useCallback((m) => { voiceModeRef.current = m; setVoiceMode(m); }, []);
    useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

    useEffect(() => {
      if (paused) return;
      const t = setInterval(() => {
        if (startedAt) setElapsed(Math.floor((Date.now() - startedAt) / 1000));
      }, 1000);
      return () => clearInterval(t);
    }, [startedAt, paused]);

    useEffect(() => {
      const poll = () => fetchJSON(API + "/live/stage").then(setLiveState).catch(() => {});
      poll();
      const t = setInterval(poll, 4000);
      return () => clearInterval(t);
    }, []);

    useEffect(() => {
      if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }, [messages, sending]);

    const logLatency = useCallback(() => {
      const t = timingRef.current;
      const line = [];
      if (t.speechEnd && t.transcriptFinal) line.push("speechEnd→transcript " + (t.transcriptFinal - t.speechEnd) + "ms");
      if (t.transcriptFinal && t.chatResponseReceived) line.push("transcript→coachText " + (t.chatResponseReceived - t.transcriptFinal) + "ms");
      if (t.chatRequestStart && t.chatResponseReceived) line.push("request→response " + (t.chatResponseReceived - t.chatRequestStart) + "ms");
      if (t.chatResponseReceived && t.firstAudio) line.push("coachText→firstAudio " + (t.firstAudio - t.chatResponseReceived) + "ms");
      if (t.avatarConnectStart && t.avatarConnected) line.push("avatarConnect " + (t.avatarConnected - t.avatarConnectStart) + "ms");
      if (t.speechEnd && t.audioPlaybackStart) line.push("speechEnd→firstAudio(legacy) " + (t.audioPlaybackStart - t.speechEnd) + "ms");
      if (t.speechEnd && t.firstAudio) line.push("TOTAL speechEnd→audible " + (t.firstAudio - t.speechEnd) + "ms");
      if (line.length) console.debug("[dscc-voice-latency] " + line.join(" · "));
    }, []);

    const send = useCallback((text, opts) => {
      const trimmed = (text || "").trim();
      if (!trimmed || sending || paused) return Promise.resolve();
      const voiceTurn = !!(opts && opts.voiceTurn);
      const skipUserMessage = !!(opts && opts.skipUserMessage);
      if (!startedAt) setStartedAt(Date.now());
      if (!skipUserMessage) setMessages((m) => [...m, { role: "user", text: trimmed, ts: Date.now() }]);
      setInput("");
      setSending(true);
      setError(null);
      if (voiceTurn || liveConvoRef.current) setMode("thinking");
      timingRef.current.chatRequestStart = Date.now();
      const priorInterviewCount = prevInterviewCount;
      const useVoice = voiceOn || liveConvoRef.current;
      return fetchJSON(API + "/chat/send", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, session_id: sessionId, voice: useVoice }),
      }).then((r) => {
        timingRef.current.chatResponseReceived = Date.now();
        setSessionId(r.session_id);
        const newMsg = { role: "coach", text: r.reply, ts: Date.now() };
        setMessages((m) => [...m, newMsg]);
        // This is the whole-response, non-streaming path - used for typed
        // chat/quick actions always, and as Live Conversation's last-resort
        // fallback if the streaming turn (Deepgram->Coach->Cartesia) itself
        // fails outright, so a reply is still heard rather than silence.
        if ((voiceTurn || liveConvoRef.current) && r.audio_file && audioRef.current) {
          if (liveConvoRef.current) setProviderState((p) => ({ ...p, tts: "kittentts_fallback" }));
          audioRef.current.src = API + "/chat/audio/" + encodeURIComponent(r.audio_file);
          setMode("speaking");
          timingRef.current.audioPlaybackStart = Date.now();
          logLatency();
          audioRef.current.play().catch(() => { setMode(liveConvoRef.current ? "listening" : "idle"); });
        } else {
          setMode(liveConvoRef.current ? "listening" : "idle");
        }
        // Real-derived inline score card: only shown if the coach actually recorded
        // a new interview during this turn (checked against real analytics count).
        fetchJSON(API + "/interviews/analytics").then((a) => {
          if (priorInterviewCount != null && a.total_interviews > priorInterviewCount) {
            const latest = a.trend[a.trend.length - 1];
            setMessages((m) => m.map((msg) => msg === newMsg ? { ...msg, interviewScore: latest } : msg));
          }
          setPrevInterviewCount(a.total_interviews);
        }).catch(() => {});
      }).catch((e) => {
        setError(String((e && e.message) || e));
        if (liveConvoRef.current) setMode("listening"); else setMode("idle");
      }).finally(() => setSending(false));
    }, [sessionId, sending, paused, voiceOn, prevInterviewCount, startedAt, logLatency]);

    useEffect(() => {
      fetchJSON(API + "/interviews/analytics").then((a) => setPrevInterviewCount(a.total_interviews)).catch(() => {});
    }, []);

    const runCode = useCallback((code) => send(
      "Trace through this code step by step and tell me exactly what it outputs (no sandboxed execution is wired yet, so please reason through it):\n\n```\n" + code + "\n```"
    ), [send]);

    // Real local speech-to-text (faster-whisper, the same backend this Hermes
    // install uses elsewhere) - not a fake mic button. Record -> upload -> real
    // transcript -> fills the input for review before sending.
    const transcribeBlob = useCallback((blob) => {
      setTranscribing(true);
      const form = new FormData();
      form.append("audio", blob, "recording.webm");
      (authedFetch ? authedFetch(API + "/voice/transcribe", { method: "POST", body: form }) : fetch(API + "/voice/transcribe", { method: "POST", body: form }))
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) throw new Error(data.detail || "Transcription failed.");
          if (data.transcript) setInput((prev) => (prev ? prev + " " : "") + data.transcript);
          else setError("Didn't catch any speech in that recording — try again.");
        })
        .catch((e) => setError(String((e && e.message) || e)))
        .finally(() => setTranscribing(false));
    }, []);

    const toggleRecording = useCallback(async () => {
      if (recording) {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") mediaRecorderRef.current.stop();
        setRecording(false);
        return;
      }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setError("Microphone recording isn't supported in this browser.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];
        const mr = new MediaRecorder(stream);
        mr.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
        mr.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          transcribeBlob(new Blob(chunks, { type: mr.mimeType || "audio/webm" }));
        };
        mr.start();
        mediaRecorderRef.current = mr;
        setRecording(true);
        setError(null);
      } catch (e) {
        setError("Microphone access was blocked or unavailable.");
      }
    }, [recording, transcribeBlob]);

    // ---- Continuous "Start Live Conversation" mode -----------------------------
    // Real turn-taking driven by Deepgram's own server-side VAD/endpointing
    // (SpeechStarted for barge-in, speech_final for end-of-utterance) - the mic
    // stream is pumped continuously to a server-side Deepgram relay (the
    // permanent DEEPGRAM_API_KEY never reaches the browser). Replies are spoken
    // with Cartesia streaming TTS and, when connected, lip-synced by LiveAvatar;
    // both are independent, best-effort layers - STT/Coach/lesson logic never
    // depends on either succeeding.

    // ---- Cartesia streaming TTS: one persistent WS per Live Conversation -----
    // session (not per turn - reconnecting every turn was the real cause of
    // the intermittent "falls back to KittenTTS" symptom found in real-browser
    // testing). Each turn gets its own context_id + monotonic turnId; barge-in
    // just bumps turnId so late chunks from an interrupted turn are dropped
    // rather than requiring a socket teardown/reconnect.

    function getCartesiaPlaybackCtx() {
      if (!cartesiaPlaybackCtxRef.current) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        cartesiaPlaybackCtxRef.current = new AudioCtx();
      }
      return cartesiaPlaybackCtxRef.current;
    }

    // sampleRate is per-call, not fixed: Simli requires PCM16 24kHz->16kHz
    // for lip-sync while local fallback/HeyGen use 24kHz, and a single
    // turn's audio is always requested at one consistent rate (see
    // beginCartesiaTurn) - createBuffer handles playback at whatever rate
    // the AudioContext itself is actually running at, so this needs no
    // context-level rate pinning.
    const playPCM = useCallback((int16Array, sampleRate) => {
      const ctx = getCartesiaPlaybackCtx();
      const float32 = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) float32[i] = int16Array[i] / 0x8000;
      const buffer = ctx.createBuffer(1, float32.length, sampleRate);
      buffer.getChannelData(0).set(float32);
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      const startAt = Math.max(ctx.currentTime, cartesiaNextStartRef.current);
      src.start(startAt);
      cartesiaNextStartRef.current = startAt + buffer.duration;
      cartesiaActiveSourcesRef.current.push(src);
      src.onended = () => { cartesiaActiveSourcesRef.current = cartesiaActiveSourcesRef.current.filter((s) => s !== src); };
    }, []);

    const stopCartesiaPlayback = useCallback(() => {
      cartesiaActiveSourcesRef.current.forEach((s) => { try { s.stop(); } catch (e) {} });
      cartesiaActiveSourcesRef.current = [];
      const ctx = cartesiaPlaybackCtxRef.current;
      cartesiaNextStartRef.current = ctx ? ctx.currentTime : 0;
    }, []);

    // Dispatchers: which avatar provider (if any) is actually live decides
    // how audio/barge-in reach it. Simli has no "seal an utterance" concept
    // (agent.speak_end is a HeyGen-specific LITE-mode command) - it just
    // renders whatever audio is streamed to it, so Simli always returns
    // false from sealAvatarUtterance and the caller falls through to the
    // same duration-based "done speaking" timeout used for local playback.
    const feedAvatarAudio = useCallback((base64Chunk) => {
      if (!avatarReadyRef.current) return false;
      if (avatarProviderRef.current === "simli") {
        if (!simliClientRef.current) return false;
        const int16 = base64ToInt16(base64Chunk);
        const uint8 = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength);
        try { simliClientRef.current.sendAudioData(uint8); return true; } catch (e) { return false; }
      }
      if (avatarProviderRef.current === "heygen") {
        if (!avatarWsRef.current || avatarWsRef.current.readyState !== WebSocket.OPEN) return false;
        avatarWsRef.current.send(JSON.stringify({ type: "agent.speak", event_id: "spk-" + Date.now() + "-" + Math.random().toString(36).slice(2), audio: base64Chunk }));
        return true;
      }
      return false;
    }, []);

    const sealAvatarUtterance = useCallback(() => {
      if (avatarReadyRef.current && avatarProviderRef.current === "heygen" && avatarWsRef.current && avatarWsRef.current.readyState === WebSocket.OPEN) {
        avatarWsRef.current.send(JSON.stringify({ type: "agent.speak_end" }));
        return true;
      }
      return false;
    }, []);

    const interruptAvatar = useCallback(() => {
      if (!avatarReadyRef.current) return;
      if (avatarProviderRef.current === "simli" && simliClientRef.current) {
        try { simliClientRef.current.ClearBuffer(); } catch (e) {}
      } else if (avatarProviderRef.current === "heygen" && avatarWsRef.current && avatarWsRef.current.readyState === WebSocket.OPEN) {
        avatarWsRef.current.send(JSON.stringify({ type: "agent.interrupt" }));
      }
    }, []);

    // Simli's own real requirement (PCM16 mono) is 16kHz, not the 24kHz
    // HeyGen/local-playback path uses - decided once per turn based on
    // whichever avatar is actually active right now.
    function activeCartesiaSampleRate() {
      return avatarProviderRef.current === "simli" ? SIMLI_SAMPLE_RATE : CARTESIA_SAMPLE_RATE;
    }

    const handleCartesiaMessage = useCallback((ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
      const entry = msg.context_id && cartesiaContextMapRef.current.get(msg.context_id);
      if (!entry) return;
      const isCurrentTurn = entry.turnId === cartesiaTurnIdRef.current;
      if (msg.type === "chunk" && msg.data) {
        if (!entry.firstAudioSeen) { entry.firstAudioSeen = true; entry.onFirstAudio && entry.onFirstAudio(); }
        if (!isCurrentTurn) return; // interrupted by barge-in - drop silently, don't play stale audio
        // Per-chunk, freshly-checked routing (not decided once for the whole
        // turn): this is what makes an avatar failure mid-utterance recover
        // instead of dropping audio - once fallen back to local playback for
        // this turn, stay there (avoid flip-flopping mid-sentence).
        if (!entry.fellBack && avatarReadyRef.current && feedAvatarAudio(msg.data)) {
          entry.usedAvatar = true;
        } else {
          entry.fellBack = true;
          setProviderState((p) => (p.tts === "cartesia" ? p : { ...p, tts: "cartesia" }));
          playPCM(base64ToInt16(msg.data), entry.sampleRate);
        }
      } else if (msg.type === "done") {
        cartesiaContextMapRef.current.delete(msg.context_id);
        if (isCurrentTurn) entry.resolve(entry);
      } else if (msg.type === "error") {
        cartesiaContextMapRef.current.delete(msg.context_id);
        if (isCurrentTurn) entry.reject(new Error(msg.error || "cartesia_error"));
      }
    }, [feedAvatarAudio, playPCM]);
    const handleCartesiaMessageRef = useRef(handleCartesiaMessage);
    handleCartesiaMessageRef.current = handleCartesiaMessage;

    const ensureCartesiaSocket = useCallback(() => {
      const existing = cartesiaSocketRef.current;
      if (existing && existing.readyState === WebSocket.OPEN) return Promise.resolve(existing);
      return fetchJSON(API + "/voice/cartesia/token", { method: "POST" }).then((tokenInfo) => new Promise((resolve, reject) => {
        const wsUrl = "wss://api.cartesia.ai/tts/websocket?cartesia_version=2026-08-14&access_token=" + encodeURIComponent(tokenInfo.token);
        const ws = new WebSocket(wsUrl);
        ws.__tokenInfo = tokenInfo;
        ws.onopen = () => { cartesiaSocketRef.current = ws; resolve(ws); };
        ws.onmessage = (ev) => handleCartesiaMessageRef.current(ev);
        ws.onerror = () => reject(new Error("cartesia_ws_error"));
        ws.onclose = () => { if (cartesiaSocketRef.current === ws) cartesiaSocketRef.current = null; };
      }));
    }, []);

    const beginCartesiaTurn = useCallback((onFirstAudio) => {
      const turnId = ++cartesiaTurnIdRef.current;
      const contextId = "turn-" + turnId + "-" + Date.now();
      const sampleRate = activeCartesiaSampleRate();
      return ensureCartesiaSocket().then((ws) => {
        const entry = { turnId, usedAvatar: false, fellBack: false, firstAudioSeen: false, onFirstAudio, sampleRate };
        const donePromise = new Promise((resolve, reject) => { entry.resolve = resolve; entry.reject = reject; });
        cartesiaContextMapRef.current.set(contextId, entry);
        return { ws, contextId, turnId, entry, donePromise, tokenInfo: ws.__tokenInfo, sampleRate };
      });
    }, [ensureCartesiaSocket]);

    function sendSentenceToCartesia(turnCtx, sentence, isLast) {
      turnCtx.ws.send(JSON.stringify({
        model_id: turnCtx.tokenInfo.model_id, transcript: sentence,
        voice: { mode: "id", id: turnCtx.tokenInfo.voice_id }, language: "en",
        context_id: turnCtx.contextId,
        output_format: { container: "raw", encoding: "pcm_s16le", sample_rate: turnCtx.sampleRate },
        continue: !isLast,
      }));
    }

    // ---- Avatar: Simli (primary) -> LiveAvatar/HeyGen (fallback) -> static ---
    // Robustness against session limits (HeyGen Free's ~2min cap; either
    // provider's own connection failures): proactive refresh, reactive
    // detection via provider-specific events plus a periodic health poll,
    // and automatic reconnect/fallthrough - the UI must never keep showing
    // an avatar as live once its video track is actually gone (avatarReadyRef
    // is the single source of truth Cartesia routing checks, and every path
    // below that loses the avatar sets it false in the same tick as the
    // status badge). Avatar failure NEVER touches STT/LLM/TTS provider state.

    const clearAvatarTimers = useCallback(() => {
      if (avatarHealthTimerRef.current) { clearInterval(avatarHealthTimerRef.current); avatarHealthTimerRef.current = null; }
      if (avatarProactiveTimerRef.current) { clearTimeout(avatarProactiveTimerRef.current); avatarProactiveTimerRef.current = null; }
    }, []);

    const teardownAvatarConnection = useCallback(() => {
      if (simliClientRef.current) { try { simliClientRef.current.stop(); } catch (e) {} simliClientRef.current = null; }
      if (avatarWsRef.current) { try { avatarWsRef.current.onclose = null; avatarWsRef.current.close(); } catch (e) {} avatarWsRef.current = null; }
      if (avatarRoomRef.current) { try { avatarRoomRef.current.disconnect(); } catch (e) {} avatarRoomRef.current = null; }
      avatarReadyRef.current = false;
      avatarProviderRef.current = null;
    }, []);

    const disconnectAvatar = useCallback((reason) => {
      clearAvatarTimers();
      teardownAvatarConnection();
      if (avatarSessionIdRef.current) {
        const sid = avatarSessionIdRef.current;
        avatarSessionIdRef.current = null;
        fetch(API + "/voice/liveavatar/session/" + encodeURIComponent(sid) + "/stop", { method: "POST", credentials: "same-origin" }).catch(() => {});
      }
      setAvatarStatus(reason || "idle");
      setProviderState((p) => ({ ...p, avatar: reason === "idle" ? "-" : (AVATAR_STATUS_LABEL[reason] || reason || "-") }));
    }, [clearAvatarTimers, teardownAvatarConnection]);

    const markAvatarLost = useCallback((logReason) => {
      // Logs the actual reason (track/room/ws event) rather than just going
      // silent - the honest-reporting standard this whole project holds to.
      console.debug("[dscc-avatar] lost:", logReason);
      const lostProvider = avatarProviderRef.current;
      teardownAvatarConnection();
      if (liveConvoRef.current) {
        setAvatarStatus("reconnecting");
        setProviderState((p) => ({ ...p, avatar: "Reconnecting…" }));
        reconnectAvatarRef.current && reconnectAvatarRef.current(logReason, lostProvider);
      }
    }, [teardownAvatarConnection]);

    const connectSimliAvatar = useCallback(async ({ isReconnect } = {}) => {
      const SDK = await loadSimliSdk();
      const session = await fetchJSON(API + "/voice/simli/session", { method: "POST" });
      const videoEl = avatarVideoRef.current, audioEl = simliAudioRef.current;
      if (!videoEl || !audioEl) throw new Error("simli_no_media_elements");
      const oldClient = simliClientRef.current;
      const client = new SDK.SimliClient(session.session_token, videoEl, audioEl, session.ice_servers || null);
      await new Promise((resolve, reject) => {
        let settled = false;
        const timeout = setTimeout(() => { if (!settled) { settled = true; reject(new Error("simli_connect_timeout")); } }, 20000);
        client.on("failed", (e) => { if (!settled) { settled = true; clearTimeout(timeout); reject(new Error("simli_failed: " + (e && (e.message || JSON.stringify(e))))); } });
        client.on("disconnected", () => { if (settled) markAvatarLost("simli_disconnected"); });
        client.start().then(() => { if (!settled) { settled = true; clearTimeout(timeout); resolve(); } }).catch((e) => { if (!settled) { settled = true; clearTimeout(timeout); reject(e); } });
      });
      simliClientRef.current = client;
      avatarProviderRef.current = "simli";
      avatarReadyRef.current = true;
      timingRef.current.avatarConnected = Date.now();
      if (oldClient && oldClient !== client) { try { oldClient.stop(); } catch (e) {} }

      avatarReconnectAttemptsRef.current = 0;
      setAvatarStatus("connected");
      setProviderState((p) => ({ ...p, avatar: "Simli Live" }));

      if (avatarHealthTimerRef.current) clearInterval(avatarHealthTimerRef.current);
      avatarHealthTimerRef.current = setInterval(() => {
        const track = videoEl.srcObject && videoEl.srcObject.getVideoTracks && videoEl.srcObject.getVideoTracks()[0];
        const healthy = !!track && track.readyState === "live";
        if (!healthy && avatarReadyRef.current && avatarProviderRef.current === "simli") markAvatarLost("simli_health_check_failed");
      }, AVATAR_HEALTH_CHECK_MS);

      if (avatarProactiveTimerRef.current) clearTimeout(avatarProactiveTimerRef.current);
      avatarProactiveTimerRef.current = setTimeout(() => {
        if (liveConvoRef.current && avatarProviderRef.current === "simli") connectSimliAvatarRef.current({ isReconnect: true }).catch(() => markAvatarLost("simli_proactive_refresh_failed"));
      }, AVATAR_PROACTIVE_REFRESH_MS);
      return true;
    }, [markAvatarLost]);
    const connectSimliAvatarRef = useRef(connectSimliAvatar);
    connectSimliAvatarRef.current = connectSimliAvatar;

    const connectHeyGenAvatar = useCallback(async ({ isReconnect } = {}) => {
      timingRef.current.avatarConnectStart = Date.now();
      const oldRoom = avatarRoomRef.current, oldWs = avatarWsRef.current;
      const LK = await loadLiveKitSdk();
      const session = await fetchJSON(API + "/voice/liveavatar/session", { method: "POST" });
      avatarSessionIdRef.current = session.session_id;
      const room = new LK.Room();
      room.on(LK.RoomEvent.TrackSubscribed, (track) => {
        if (avatarVideoRef.current && (track.kind === "video" || track.kind === "audio")) track.attach(avatarVideoRef.current);
      });
      room.on(LK.RoomEvent.TrackUnsubscribed, (track) => { if (track.kind === "video") markAvatarLost("track_unsubscribed"); });
      room.on(LK.RoomEvent.TrackMuted, (pub) => { if (pub.kind === "video") markAvatarLost("track_muted"); });
      room.on(LK.RoomEvent.Disconnected, (reason) => markAvatarLost("room_disconnected:" + reason));
      await room.connect(session.livekit_url, session.livekit_client_token);
      avatarRoomRef.current = room;

      const ws = new WebSocket(session.ws_url);
      await new Promise((resolve, reject) => {
        let settled = false;
        const timeout = setTimeout(() => { if (!settled) { settled = true; reject(new Error("avatar_ws_timeout")); } }, 15000);
        ws.onmessage = (ev) => {
          let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
          if (msg.type === "session.state_updated") {
            if (msg.state === "connected" && !settled) {
              settled = true; clearTimeout(timeout);
              avatarReadyRef.current = true;
              timingRef.current.avatarConnected = Date.now();
              resolve();
            } else if (msg.state === "disconnected") {
              markAvatarLost("session.state_updated:disconnected");
            }
          } else if (msg.type === "agent.speak_ended" || msg.type === "agent.speak_interrupted") {
            if (avatarSpeakEndSafetyRef.current) { clearTimeout(avatarSpeakEndSafetyRef.current); avatarSpeakEndSafetyRef.current = null; }
            if (liveConvoRef.current) setMode("listening");
          } else if (msg.type === "error") {
            console.debug("[dscc-avatar] error event:", msg.error);
          }
        };
        ws.onerror = () => { if (!settled) { settled = true; clearTimeout(timeout); reject(new Error("avatar_ws_error")); } };
        ws.onclose = (ev) => { if (!settled) { settled = true; clearTimeout(timeout); reject(new Error("avatar_ws_closed")); } else { markAvatarLost("ws_close:" + ev.code + ":" + ev.reason); } };
      });
      avatarWsRef.current = ws;
      avatarProviderRef.current = "heygen";
      avatarReconnectAttemptsRef.current = 0;

      // The old connection (if this was a reconnect) is only torn down
      // AFTER the new one is confirmed live, so the video never has a gap.
      if (oldWs) { try { oldWs.onclose = null; oldWs.close(); } catch (e) {} }
      if (oldRoom) { try { oldRoom.disconnect(); } catch (e) {} }

      setAvatarStatus("connected");
      setProviderState((p) => ({ ...p, avatar: "LiveAvatar" }));

      if (avatarHealthTimerRef.current) clearInterval(avatarHealthTimerRef.current);
      avatarHealthTimerRef.current = setInterval(() => {
        const room2 = avatarRoomRef.current;
        const healthy = !!room2 && room2.state === "connected" && avatarWsRef.current && avatarWsRef.current.readyState === WebSocket.OPEN;
        if (!healthy && avatarReadyRef.current && avatarProviderRef.current === "heygen") markAvatarLost("health_check_failed");
      }, AVATAR_HEALTH_CHECK_MS);

      if (avatarProactiveTimerRef.current) clearTimeout(avatarProactiveTimerRef.current);
      avatarProactiveTimerRef.current = setTimeout(() => {
        if (liveConvoRef.current && avatarProviderRef.current === "heygen") connectHeyGenAvatarRef.current({ isReconnect: true }).catch(() => markAvatarLost("heygen_proactive_refresh_failed"));
      }, AVATAR_PROACTIVE_REFRESH_MS);
      return true;
    }, [markAvatarLost]);
    const connectHeyGenAvatarRef = useRef(connectHeyGenAvatar);
    connectHeyGenAvatarRef.current = connectHeyGenAvatar;

    // Top-level orchestrator: Simli first (if configured), HeyGen next, then
    // static image + voice-only. Real status is read from /voice/providers
    // (never inferred/guessed), so a missing SIMLI_FACE_ID reports as
    // "not configured" - never confused with a genuine connection failure.
    const connectAvatar = useCallback(async ({ isReconnect, skipSimli } = {}) => {
      setAvatarStatus(isReconnect ? "reconnecting" : "connecting");
      setProviderState((p) => ({ ...p, avatar: isReconnect ? "Reconnecting…" : "Connecting…" }));
      let providers = null;
      try { providers = await fetchJSON(API + "/voice/providers"); } catch (e) {}
      const avatarList = (providers && providers.avatar) || [];
      const simliEntry = avatarList.find((p) => p.id === "simli");
      const heygenEntry = avatarList.find((p) => p.id === "liveavatar");

      if (!skipSimli && simliEntry && simliEntry.status === "connected") {
        try {
          await connectSimliAvatarRef.current({ isReconnect });
          return true;
        } catch (e) {
          console.debug("[dscc-avatar] Simli failed, falling back to HeyGen:", e);
        }
      }
      if (heygenEntry && heygenEntry.status === "connected") {
        try {
          await connectHeyGenAvatarRef.current({ isReconnect });
          return true;
        } catch (e) {
          console.debug("[dscc-avatar] HeyGen also failed, static fallback:", e);
        }
      }
      teardownAvatarConnection();
      setAvatarStatus("unavailable");
      setProviderState((p) => ({ ...p, avatar: "Static fallback" }));
      return false;
    }, [teardownAvatarConnection]);
    const connectAvatarRef = useRef(connectAvatar);
    connectAvatarRef.current = connectAvatar;

    const reconnectAvatarRef = useRef(null);
    reconnectAvatarRef.current = (reason, lostProvider) => {
      avatarReconnectAttemptsRef.current += 1;
      if (avatarReconnectAttemptsRef.current > AVATAR_MAX_RECONNECT_ATTEMPTS) {
        setAvatarStatus("unavailable");
        setProviderState((p) => ({ ...p, avatar: "Static fallback" }));
        return;
      }
      if (lostProvider === "simli") {
        // Required hierarchy: a Simli failure goes straight to HeyGen, not
        // a Simli retry loop.
        connectHeyGenAvatarRef.current({ isReconnect: true }).catch(() => {
          setAvatarStatus("unavailable");
          setProviderState((p) => ({ ...p, avatar: "Static fallback" }));
        });
      } else {
        connectAvatarRef.current({ isReconnect: true, skipSimli: true });
      }
    };

    // ---- Turn orchestration: streaming Coach text -> Cartesia (+ avatar) -----
    // Deepgram speech_final -> POST /chat/send/stream (real per-token
    // streaming) -> as soon as a sentence boundary completes, that sentence is
    // sent to Cartesia immediately (not after the full reply is done) -> each
    // audio chunk is routed to the avatar or local playback, decided fresh
    // per chunk so an avatar failure never silences Cartesia.

    const sendLiveTurn = useCallback((transcript) => {
      const trimmed = (transcript || "").trim();
      if (!trimmed) return;
      setMessages((m) => [...m, { role: "user", text: trimmed, ts: Date.now() }]);
      if (!startedAt) setStartedAt(Date.now());
      setMode("thinking");
      setProviderState((p) => ({ ...p, tts: "cartesia" }));
      timingRef.current.chatRequestStart = Date.now();
      timingRef.current.firstLLMToken = null;
      timingRef.current.firstAudio = null;

      let fullText = "";
      let sentenceBuffer = "";
      let pendingSentence = null;
      let turnCtx = null;
      let sendQueue = Promise.resolve();

      function enqueueSend(text, isLast) {
        sendQueue = sendQueue.then(() => {
          if (!turnCtx) {
            return beginCartesiaTurn(() => {
              if (!timingRef.current.firstAudio) { timingRef.current.firstAudio = Date.now(); logLatency(); }
            }).then((ctx) => { turnCtx = ctx; sendSentenceToCartesia(ctx, text, isLast); });
          }
          sendSentenceToCartesia(turnCtx, text, isLast);
        }).catch((e) => console.debug("[dscc-voice] cartesia send failed:", e));
      }
      function completeSentence(text) {
        const s = text.trim();
        if (!s) return;
        if (pendingSentence != null) enqueueSend(pendingSentence, false);
        pendingSentence = s;
      }
      function drain() {
        let m;
        while ((m = sentenceBuffer.match(/^([^.!?\n]*[.!?\n]+)/))) {
          sentenceBuffer = sentenceBuffer.slice(m[1].length);
          completeSentence(m[1]);
        }
      }
      function finalizeSentences() {
        drain();
        if (pendingSentence != null) { enqueueSend(pendingSentence, true); pendingSentence = null; }
        else if (sentenceBuffer.trim()) { enqueueSend(sentenceBuffer.trim(), true); sentenceBuffer = ""; }
      }
      function finishTurnAudio() {
        (turnCtx ? turnCtx.donePromise.catch(() => {}) : Promise.resolve()).then(() => {
          if (!liveConvoRef.current) return;
          const entry = turnCtx && turnCtx.entry;
          // sealAvatarUtterance() only actually seals for HeyGen (returns
          // true there) - Simli has no equivalent "end of utterance" signal,
          // so it (like local/no-avatar playback) falls through to the
          // duration-based timeout below.
          const sealed = entry && entry.usedAvatar && !entry.fellBack && sealAvatarUtterance();
          if (sealed) {
            avatarSpeakEndSafetyRef.current = setTimeout(() => { if (liveConvoRef.current) setMode("listening"); }, AVATAR_SPEAK_END_TIMEOUT_MS);
          } else {
            if (entry && entry.usedAvatar && entry.fellBack) interruptAvatar(); // partial avatar use before falling back - stop the orphaned pose
            const ctx = cartesiaPlaybackCtxRef.current;
            const remainingMs = ctx ? Math.max(0, (cartesiaNextStartRef.current - ctx.currentTime) * 1000) : 0;
            setTimeout(() => { if (liveConvoRef.current) setMode("listening"); }, remainingMs + 60);
          }
        });
      }

      function streamFrom(url, body) {
        return fetch(url, {
          method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
          body: JSON.stringify(body),
        }).then((resp) => {
          if (!resp.ok || !resp.body) throw new Error("stream_failed");
          const reader = resp.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          function pump() {
            return reader.read().then(({ done, value }) => {
              if (done) return;
              buf += decoder.decode(value, { stream: true });
              let idx;
              while ((idx = buf.indexOf("\n")) >= 0) {
                const line = buf.slice(0, idx); buf = buf.slice(idx + 1);
                if (!line.trim()) continue;
                let msg; try { msg = JSON.parse(line); } catch (e) { continue; }
                if (msg.type === "system") {
                  if (msg.model) setProviderState((p) => ({ ...p, llm: msg.model }));
                } else if (msg.type === "text" && msg.text) {
                  if (!timingRef.current.firstLLMToken) { timingRef.current.firstLLMToken = Date.now(); logLatency(); }
                  fullText += msg.text;
                  sentenceBuffer += msg.text;
                  drain();
                } else if (msg.type === "result") {
                  if (msg.session_id) setSessionId(msg.session_id);
                  timingRef.current.chatResponseReceived = Date.now();
                } else if (msg.type === "error") {
                  throw new Error(msg.error || "stream_error");
                }
              }
              return pump();
            });
          }
          return pump();
        });
      }

      // Primary: the warm resident-agent path (avoids the ~3-5s cold CLI/
      // agent-build cost on every turn). Falls back to the per-turn
      // subprocess-streaming path if the warm path itself errors - Live
      // Conversation keeps working either way, just slower on that one turn.
      (liveIdRef.current
        ? streamFrom(API + "/chat/send/stream/live", { message: trimmed, live_id: liveIdRef.current, session_id: sessionIdRef.current })
        : streamFrom(API + "/chat/send/stream", { message: trimmed, session_id: sessionIdRef.current, voice: true })
      ).catch((e) => {
        console.debug("[dscc-voice] warm live-agent stream failed, falling back to subprocess stream:", e);
        fullText = ""; sentenceBuffer = ""; pendingSentence = null;
        return streamFrom(API + "/chat/send/stream", { message: trimmed, session_id: sessionIdRef.current, voice: true });
      }).then(() => {
        const finalText = fullText.trim();
        if (finalText) setMessages((m) => [...m, { role: "coach", text: finalText, ts: Date.now() }]);
        finalizeSentences();
        if (finalText) finishTurnAudio();
        else if (liveConvoRef.current) setMode("listening");
      }).catch((e) => {
        console.debug("[dscc-voice] streaming turn failed, falling back to whole-response path:", e);
        setProviderState((p) => ({ ...p, llm: (p.llm || "-") + " (buffered fallback)" }));
        send(trimmed, { voiceTurn: true, skipUserMessage: true });
      });
    }, [startedAt, logLatency, beginCartesiaTurn, sealAvatarUtterance, interruptAvatar, send]);

    // ---- Deepgram streaming STT (mic -> server relay -> transcript) ---------

    const handleDeepgramMessage = useCallback((msg) => {
      if (msg.type === "SpeechStarted") {
        if (voiceModeRef.current === "speaking") {
          // Real barge-in: bump the Cartesia turnId (late chunks from the
          // interrupted turn get dropped by handleCartesiaMessage) and stop
          // whatever's currently audible.
          cartesiaTurnIdRef.current += 1;
          stopCartesiaPlayback();
          if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; }
          interruptAvatar();
          setMode("listening");
        }
        return;
      }
      if (msg.type === "Results") {
        const alt = msg.channel && msg.channel.alternatives && msg.channel.alternatives[0];
        const transcript = alt ? alt.transcript : "";
        if (msg.speech_final && transcript && transcript.trim()) {
          timingRef.current.speechEnd = Date.now();
          timingRef.current.transcriptFinal = Date.now();
          setInterimText("");
          setMode("transcribing");
          sendLiveTurn(transcript);
        } else if (transcript) {
          setInterimText(transcript);
        }
      }
    }, [sendLiveTurn, stopCartesiaPlayback, interruptAvatar]);
    const handleDeepgramMessageRef = useRef(handleDeepgramMessage);
    handleDeepgramMessageRef.current = handleDeepgramMessage;

    const teardownDeepgramAudio = useCallback(() => {
      if (dgProcessorRef.current) { try { dgProcessorRef.current.disconnect(); } catch (e) {} dgProcessorRef.current = null; }
      if (dgAudioCtxRef.current) { dgAudioCtxRef.current.close().catch(() => {}); dgAudioCtxRef.current = null; }
    }, []);

    const connectDeepgram = useCallback(async (stream) => {
      const ticket = await mintWsTicket();
      const wsUrl = location.origin.replace(/^http/, "ws") + API + "/voice/deepgram/stream?sample_rate=" + DG_SAMPLE_RATE + "&ticket=" + encodeURIComponent(ticket);
      const ws = new WebSocket(wsUrl);
      dgSocketRef.current = ws;
      await new Promise((resolve, reject) => {
        ws.onopen = () => {
          const AudioCtx = window.AudioContext || window.webkitAudioContext;
          const ctx = new AudioCtx();
          dgAudioCtxRef.current = ctx;
          const source = ctx.createMediaStreamSource(stream);
          const processor = ctx.createScriptProcessor(4096, 1, 1);
          dgProcessorRef.current = processor;
          processor.onaudioprocess = (e) => {
            if (ws.readyState !== WebSocket.OPEN) return;
            const input = e.inputBuffer.getChannelData(0);
            const pcm = floatTo16BitPCM(downsampleTo16k(input, ctx.sampleRate));
            ws.send(pcm.buffer);
          };
          // ScriptProcessorNode only fires while connected to a destination;
          // route through a silent gain so raw mic audio is never played back
          // (that would be an instant feedback loop, not a real fallback).
          const silentGain = ctx.createGain();
          silentGain.gain.value = 0;
          source.connect(processor);
          processor.connect(silentGain);
          silentGain.connect(ctx.destination);
          dgReconnectingRef.current = false;
          resolve();
        };
        ws.onerror = () => reject(new Error("deepgram_ws_error"));
      });
      ws.onmessage = (ev) => {
        let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
        handleDeepgramMessageRef.current(msg);
      };
      ws.onclose = () => {
        teardownDeepgramAudio();
        if (dgSocketRef.current === ws) dgSocketRef.current = null;
        if (liveConvoRef.current && !dgReconnectingRef.current) {
          // One automatic reconnect attempt (fresh ticket + fresh mic pipeline);
          // if that also fails, voice conversation stops rather than getting
          // stuck silently - text chat below still works.
          dgReconnectingRef.current = true;
          setMode("reconnecting");
          setProviderState((p) => ({ ...p, stt: "Reconnecting…" }));
          connectDeepgram(stream).then(() => {
            setMode("listening");
            setProviderState((p) => ({ ...p, stt: "deepgram" }));
          }).catch(() => {
            setMode("provider_unavailable");
            setProviderState((p) => ({ ...p, stt: "unavailable" }));
            setTimeout(() => { if (liveConvoRef.current) stopLiveConversationRef.current(); }, 2000);
          });
        }
      };
    }, [teardownDeepgramAudio]);

    const stopLiveConversation = useCallback(() => {
      liveConvoRef.current = false;
      setLiveConvo(false);
      if (dgSocketRef.current) { try { dgSocketRef.current.onclose = null; dgSocketRef.current.close(); } catch (e) {} dgSocketRef.current = null; }
      teardownDeepgramAudio();
      stopCartesiaPlayback();
      if (cartesiaSocketRef.current) { try { cartesiaSocketRef.current.close(); } catch (e) {} cartesiaSocketRef.current = null; }
      cartesiaContextMapRef.current.clear();
      if (avatarSpeakEndSafetyRef.current) { clearTimeout(avatarSpeakEndSafetyRef.current); avatarSpeakEndSafetyRef.current = null; }
      disconnectAvatar("idle");
      if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
      if (liveIdRef.current) {
        // Releases the resident agent's resources server-side rather than
        // waiting for its idle timeout.
        fetch(API + "/chat/live/" + liveIdRef.current + "/close", { method: "POST", credentials: "same-origin" }).catch(() => {});
        liveIdRef.current = null;
      }
      setInterimText("");
      setMode("idle");
      setProviderState({ stt: "-", llm: "-", tts: "-", avatar: "-" });
    }, [teardownDeepgramAudio, stopCartesiaPlayback, disconnectAvatar]);
    const stopLiveConversationRef = useRef(stopLiveConversation);
    stopLiveConversationRef.current = stopLiveConversation;

    const startLiveConversation = useCallback(async () => {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setError("Live voice conversation isn't supported in this browser.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        await connectDeepgram(stream);
        liveConvoRef.current = true;
        liveIdRef.current = "live-" + Date.now() + "-" + Math.random().toString(36).slice(2);
        setLiveConvo(true);
        setVoiceOn(true);
        setError(null);
        if (!startedAt) setStartedAt(Date.now());
        setMode("listening");
        setProviderState({ stt: "deepgram", llm: "-", tts: "cartesia", avatar: "-" });
        // Best-effort, non-blocking: voice conversation is already live via
        // Deepgram/Cartesia even if the avatar never connects.
        connectAvatar();
      } catch (e) {
        if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
        setError(e && e.message === "deepgram_ws_error"
          ? "Couldn't reach the speech-recognition service. Text chat still works below."
          : "Microphone access is blocked. Allow microphone access in your browser to use Live Conversation — text chat still works below.");
      }
    }, [connectDeepgram, connectAvatar, startedAt]);

    // Clean up all realtime resources (mic stream, Deepgram WS/audio pipeline,
    // Cartesia socket, LiveAvatar room+WS, avatar timers) if the component
    // unmounts (e.g. navigating away) while a live conversation is active - no
    // orphaned mic access, sockets, timers, or billed avatar sessions.
    useEffect(() => () => {
      if (dgSocketRef.current) { try { dgSocketRef.current.onclose = null; dgSocketRef.current.close(); } catch (e) {} }
      teardownDeepgramAudio();
      stopCartesiaPlayback();
      if (cartesiaSocketRef.current) { try { cartesiaSocketRef.current.close(); } catch (e) {} }
      if (avatarSpeakEndSafetyRef.current) clearTimeout(avatarSpeakEndSafetyRef.current);
      disconnectAvatar();
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
      if (liveIdRef.current) fetch(API + "/chat/live/" + liveIdRef.current + "/close", { method: "POST", credentials: "same-origin" }).catch(() => {});
    }, []);

    const endSession = useCallback(() => {
      if (liveConvoRef.current) stopLiveConversation();
      send("Let's end here for now — please give a short summary and set the lesson stage to idle.");
    }, [send, stopLiveConversation]);

    const lastCoachMsg = [...messages].reverse().find((m) => m.role === "coach");
    const coachState = liveConvo && voiceMode !== "idle"
      ? { key: voiceMode, label: VOICE_STATE_LABEL[voiceMode] || voiceMode }
      : deriveCoachState(sending, paused, liveState);
    const yourTurn = liveState && liveState.stage === "your_turn";

    return h("div", { className: "dscc-live-layout" }, [
      h("div", { className: "dscc-live-center", key: "center" }, [
        h("div", { className: "dscc-coach-stage" + (fullscreen ? " fullscreen" : ""), key: "stage" }, [
          h("div", { className: "dscc-coach-photo-frame" + (coachState.key === "thinking" || coachState.key === "transcribing" ? " thinking" : coachState.key === "listening" ? " listening" : (sessionId && coachState.key !== "idle" && coachState.key !== "paused") ? " speaking" : ""), key: "frame" }, [
            // The LiveAvatar video tile renders inside this same frame - not a
            // separate demo page - and simply sits behind the static Avatar
            // image, which stays visible whenever the avatar isn't connected.
            h("video", {
              key: "avatarVideo", ref: avatarVideoRef, autoPlay: true, playsInline: true,
              style: { display: avatarStatus === "connected" ? "block" : "none", width: "100%", height: "100%", objectFit: "cover" },
            }),
            // Simli's SDK binds its own separate audio track here (video's
            // own audio stays muted/unused for Simli - HeyGen instead
            // attaches both tracks directly onto the video element above).
            h("audio", { key: "simliAudio", ref: simliAudioRef, autoPlay: true, style: { display: "none" } }),
            avatarStatus !== "connected" ? h(Avatar, { key: "photo", large: true }) : null,
          ]),
          h("div", { className: "dscc-stage-badges", key: "badges" }, [
            sessionId ? h("span", { className: "dscc-badge-live", key: "live" }, [h("span", { className: "dscc-live-reddot", key: "d" }), "LIVE"]) : null,
            sessionId ? h("span", { className: "dscc-badge-timer", key: "timer" }, "⏱ " + fmtElapsed(elapsed)) : null,
            liveConvo && avatarStatus !== "idle" ? h("span", { className: "dscc-badge-avatar dscc-badge-avatar-" + avatarStatus, key: "av" }, AVATAR_STATUS_LABEL[avatarStatus] || avatarStatus) : null,
          ]),
          h(CoachStateBadge, { key: "state", state: coachState, corner: true }),
          liveConvo && interimText ? h("div", { className: "dscc-interim-transcript", key: "interim" }, "“" + interimText + "”") : null,
          h("button", {
            className: "dscc-fullscreen-btn", key: "fs", onClick: () => setFullscreen((v) => !v),
            title: fullscreen ? "Exit fullscreen" : "Fullscreen",
          }, fullscreen ? "⤡" : "⤢"),
        ]),
        h("div", { className: "dscc-coach-caption", key: "cap" }, [
          h("span", { className: "dscc-coach-caption-name", key: "n" }, "AI Career Coach"),
          h("span", { className: "dscc-coach-caption-sub", key: "s" }, "Data Science Lecturer & Career Coach"),
        ]),
        h("div", { className: "dscc-live-convo-row", key: "convo" }, [
          h("button", {
            key: "convo", className: "dscc-live-convo-btn" + (liveConvo ? " active" : ""),
            onClick: liveConvo ? stopLiveConversation : startLiveConversation,
            disabled: recording || transcribing,
          }, liveConvo ? "⏹ End Live Conversation" : "🎙️ Start Live Conversation"),
          liveConvo ? h("span", { className: "dscc-live-convo-hint", key: "hint" }, "Speak naturally — no Send needed. Talk over the coach to interrupt.") : null,
        ]),
        liveConvo ? h("div", { className: "dscc-provider-panel", key: "providers" }, [
          h("span", { key: "stt" }, "STT: " + providerState.stt),
          h("span", { key: "llm" }, "LLM: " + providerState.llm),
          h("span", { key: "tts", className: providerState.tts === "kittentts_fallback" ? "dscc-provider-fallback" : "" }, "TTS: " + (providerState.tts === "kittentts_fallback" ? "KittenTTS fallback" : providerState.tts)),
          h("span", { key: "avatar" }, "Avatar: " + providerState.avatar),
        ]) : null,
        h("div", { className: "dscc-coach-controls", key: "controls" }, [
          h("button", {
            key: "mic", className: "dscc-ctrl-btn" + (recording ? " recording" : ""), disabled: sending || paused || transcribing || liveConvo,
            onClick: toggleRecording,
            title: liveConvo ? "Live Conversation is handling the microphone" : transcribing ? "Transcribing…" : recording ? "Stop recording" : "Quick dictate one message (real local speech-to-text) — review before sending",
          }, transcribing ? "⏳" : recording ? "⏹️" : "🎙️"),
          h("button", {
            key: "spk", className: "dscc-ctrl-btn" + (voiceOn ? " active" : ""), disabled: liveConvo,
            onClick: () => setVoiceOn((v) => !v),
            title: liveConvo ? "Voice replies are always on during Live Conversation (Cartesia, falling back to local TTS)" : voiceOn ? "Coach will speak replies aloud (local TTS)" : "Turn on spoken replies (local TTS)",
          }, voiceOn ? "🔊" : "🔈"),
          h("button", {
            key: "tr", className: "dscc-ctrl-btn" + (transcriptOpen ? " active" : ""),
            onClick: () => setTranscriptOpen((v) => !v), title: "Toggle transcript",
          }, "📝"),
          h("button", {
            key: "pause", className: "dscc-ctrl-btn" + (paused ? " active" : ""), disabled: !sessionId,
            onClick: () => setPaused((v) => !v), title: paused ? "Resume session" : "Pause session (stops the timer, holds input)",
          }, paused ? "▶️" : "⏸️"),
          h("button", {
            key: "end", className: "dscc-ctrl-btn dscc-ctrl-btn-end", disabled: sending || !sessionId,
            onClick: endSession, title: "End this lesson session",
          }, "⏹️ End Session"),
        ]),
        h("audio", {
          key: "audio", ref: audioRef, style: { display: "none" },
          onEnded: () => { if (liveConvoRef.current) setMode("listening"); else setMode("idle"); },
          onError: () => { if (liveConvoRef.current) setMode("listening"); else setMode("idle"); },
        }),
        h(LessonPanel, { key: "lesson", liveState }),
        h(TeachingArea, { key: "teach", lastCoachText: lastCoachMsg && lastCoachMsg.text, topicName: liveState && liveState.topic_name, onRunCode: runCode, showToast: props.showToast }),
        error ? h("div", { className: "dscc-error", key: "err" }, error) : null,
        transcriptOpen ? h("div", { className: "dscc-live-transcript", key: "tr", ref: transcriptRef },
          messages.length
            ? messages.map((m, i) => h(MessageBubble, { key: i, msg: m }))
            : h(Empty, null, "This is a real conversation with the coach — messages here actually reach it and are saved to your learning memory like any other session.")) : null,
        transcriptOpen && sending ? h("div", { className: "dscc-msg-row dscc-msg-row-coach", key: "think" }, [
          h(Avatar, { key: "av" }),
          h("div", { className: "dscc-bubble dscc-bubble-coach dscc-bubble-thinking", key: "b" }, "Thinking…"),
        ]) : null,
        h("div", { className: "dscc-live-quick", key: "quick" }, QUICK_ACTIONS.map(([icon, label, prompt]) =>
          h("button", { key: label, className: "dscc-quick-btn", disabled: sending || paused, onClick: () => send(prompt) }, [
            h("span", { key: "i" }, icon), " ", label,
          ]))),
        h("div", { className: "dscc-live-input-row", key: "input" }, [
          h("input", {
            key: "i", className: "dscc-live-input",
            value: input, placeholder: paused ? "Session paused — resume to continue" : (yourTurn ? "Type your attempt…" : "Ask a question or type your response…"),
            disabled: sending || paused,
            onChange: (e) => setInput(e.target.value),
            onKeyDown: (e) => { if (e.key === "Enter") send(input); },
          }),
          h("button", { key: "b", className: "dscc-live-send", disabled: sending || paused || !input.trim(), onClick: () => send(input) }, "Send"),
        ]),
      ]),
      h("div", { className: "dscc-live-rail", key: "rail" }, [
        h(TodayPanel, { key: "today", today: props.today, onGenerate: () => send("Please generate my plan for today."), onSelect: (label) => send("Let's work on: " + label) }),
        h(ProgressPanel, { key: "prog", progress: props.progress, onViewDetails: props.onGoPage ? () => props.onGoPage("progress") : undefined }),
        h(CareerGoalPanel, { key: "goal", profile: props.profile, onGoalUpdated: props.onDataChanged, showToast: props.showToast }),
        h(ActivityPanel, { key: "act", activity: props.activity }),
      ]),
    ]);
  }

  function CareerCoach() {
    const [page, setPage] = useState("live");
    const [navOpen, setNavOpen] = useState(false);
    const [profile, setProfile] = useState(null);
    const [today, setToday] = useState(null);
    const [progress, setProgress] = useState(null);
    const [roadmap, setRoadmap] = useState(null);
    const [activity, setActivity] = useState(null);
    const [projects, setProjects] = useState(null);
    const [jobs, setJobs] = useState(null);
    const [interviews, setInterviews] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    const [goals, setGoals] = useState(null);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [toast, setToast] = useState(null);

    const showToast = useCallback((message, type) => {
      setToast({ message, type: type || "success" });
      setTimeout(() => setToast((t) => (t && t.message === message ? null : t)), 3000);
    }, []);

    const load = useCallback(() => {
      setLoading(true);
      Promise.all([
        fetchJSON(API + "/profile"), fetchJSON(API + "/today"), fetchJSON(API + "/progress"),
        fetchJSON(API + "/roadmap"), fetchJSON(API + "/activity"), fetchJSON(API + "/projects"),
        fetchJSON(API + "/jobs"), fetchJSON(API + "/interviews"), fetchJSON(API + "/goals"),
        fetchJSON(API + "/interviews/analytics"), fetchJSON(API + "/stats"),
      ]).then(([p, t, pr, r, a, proj, j, iv, g, ivAnalytics, st]) => {
        setProfile(p); setToday(t); setProgress(pr); setRoadmap(r); setActivity(a);
        setProjects(proj); setJobs(j); setInterviews(iv); setGoals(g); setAnalytics(ivAnalytics); setStats(st);
        setError(null);
      }).catch((e) => setError(String(e && e.message || e)))
        .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);
    // Refresh the right-rail / dashboard data periodically so it reflects a lesson
    // in progress without needing a full page reload.
    useEffect(() => {
      const t = setInterval(load, 20000);
      return () => clearInterval(t);
    }, [load]);

    if (loading && !profile) return h("div", { className: "dscc-shell" }, h(Empty, null, "Loading your coach…"));

    return h("div", { className: "dscc-app" }, [
      h(Toast, { key: "toast", toast }),
      h("button", { className: "dscc-nav-toggle", key: "toggle", onClick: () => setNavOpen((v) => !v) }, "☰"),
      navOpen ? h("div", { className: "dscc-nav-scrim", key: "scrim", onClick: () => setNavOpen(false) }) : null,
      h(SideNav, { key: "nav", page, onGo: setPage, open: navOpen, onClose: () => setNavOpen(false) }),
      h("div", { className: "dscc-main", key: "main" }, [
        error ? h("div", { className: "dscc-error", key: "err" }, [error, h("button", { className: "dscc-quick-btn", key: "retry", onClick: load, style: { marginLeft: 10 } }, "Retry")]) : null,
        page !== "live" ? h(Header, { key: "header", profile }) : null,
        page === "live" ? h(LiveCoachPage, { key: "live", today, progress, profile, activity, showToast, onDataChanged: load, onGoPage: setPage }) : null,
        page === "dashboard" ? h("div", { className: "dscc-grid", key: "dash" }, [
          h(TodayPanel, { key: "today", today }),
          h(ProgressPanel, { key: "prog", progress }),
          h(RoadmapPanel, { key: "road", roadmap: (roadmap || []).slice(0, 3) }),
          h(ActivityPanel, { key: "act", activity }),
        ]) : null,
        page === "roadmap" ? h(RoadmapPanel, { key: "roadfull", roadmap }) : null,
        page === "progress" ? h("div", { className: "dscc-grid", key: "progfull" }, [
          h(StatsPanel, { key: "s0", stats }),
          h(ProgressPanel, { key: "p1", progress }), h(SkillsPanel, { key: "p2", progress }),
        ]) : null,
        page === "projects" ? h(ProjectsPage, { key: "proj", projects }) : null,
        page === "jobs" ? h(JobsPage, { key: "jobs", jobs }) : null,
        page === "interviews" ? h(InterviewsPage, { key: "iv", interviews, analytics }) : null,
        page === "goals" ? h(GoalsPage, { key: "goals", goals }) : null,
        page === "analytics" ? h(AnalyticsPage, { key: "an", stats, analytics, progress }) : null,
        h("div", { className: "dscc-footer", key: "foot" }, "AI Career Coach · data-science-career-coach profile"),
      ]),
    ]);
  }

  window.__HERMES_PLUGINS__.register("data-science-career-coach-hub", CareerCoach);
})();
