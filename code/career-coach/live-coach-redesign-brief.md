# Live Coach — full redesign brief (owner-provided, saved 2026-09-24)

Saved verbatim per the owner's instruction ("save this also before you start building"). Nothing in this brief has been implemented yet — this is the reference to work from once implementation resumes. See `data-science-career-coach.md` for the current baseline structure this brief builds on top of.

---

CONTINUE FROM THE CURRENT IMPLEMENTATION.

DO NOT START THIS PROJECT AGAIN FROM SCRATCH.

The current AI Career Coach dashboard now has:

- left navigation
- Live Coach page
- Today's Plan
- Learning Progress
- Career Goal
- Recent Activity
- quick-action controls
- text conversation input

However, the current implementation is still visually and functionally incomplete.

I want you to now finish the dashboard into a REAL, BEAUTIFUL, INTERACTIVE PRODUCT.

This is not another planning task.

Inspect the code already built, preserve all working backend functionality, then continue implementation.

========================================================
CURRENT PROBLEMS TO FIX
========================================================

From the current interface I can see:

1. The main coach area is mostly empty.
2. The coach is still represented by a generic circular user icon.
3. Several buttons appear not to be clickable or have no visible effect.
4. The quick-action controls are too small and visually weak.
5. There is almost no animation or interaction feedback.
6. The screen still feels static.
7. The UI looks closer to an admin panel than a premium AI coaching platform.
8. The Live Coach experience does not yet feel like a live visual coaching session.
9. Today's lesson is not visually represented in the main experience.
10. There is no obvious lesson progression.
11. There is no visible code-teaching workspace.
12. There is no proper "Your Turn" learning interaction.
13. There is no visible quiz experience.
14. Voice / microphone / speaking states are not visually convincing.
15. The centre of the screen contains far too much unused space.
16. The right-hand panels are too static and plain.
17. Navigation, cards and controls need much better visual hierarchy.
18. Some data appears in the interface but is not clearly connected to user actions.
19. There is insufficient visual feedback for loading, success, failure, thinking, listening, speaking and completed states.
20. The product still feels generic rather than like a sophisticated personal AI lecturer and career coach.

========================================================
IMPORTANT RULE
========================================================

DO NOT CREATE MORE STATIC UI.

From this point forward, every interactive control must either:

A. perform a real action,
B. open a real panel/modal,
C. change real application state,
D. call an existing backend/API,
E. or be visibly disabled with an explanation.

There must be no buttons that look clickable but do nothing.

========================================================
STEP 1 — AUDIT EVERY EXISTING BUTTON
========================================================

Before adding more UI: inspect every existing button and action. Create a temporary developer checklist internally containing: button/component, click handler, backend action, expected state change, current status.

Test every control: Explain Again, Simplify This, Give an Example, Ask Me a Question, Quiz Me, Show Code, Next Topic, Mock Interview, Send, Microphone, Speaker, Transcript, End Session.

For any broken button: trace the problem, fix the handler, wire it to the correct action, test it. Add automated tests where practical. Do not leave dead buttons.

========================================================
STEP 2 — COMPLETELY FINISH LIVE COACH
========================================================

The central Live Coach area must become the dominant part of the product.

Target desktop layout:

LEFT: Hermes / Coach navigation
CENTRE: Live Coach, Today's Lesson, Teaching Workspace, Chat / interaction
RIGHT: Today's Plan, Learning Progress, Career Goal, Recent Activity

Use the existing structure and refactor where appropriate. Do not create a second competing dashboard architecture.

========================================================
REAL HUMAN COACH AREA
========================================================

Replace the generic circular user icon. Use the supplied coach identity / coach portrait. Search existing assets first. If no coach image exists, use the already documented expected asset path.

The coach must occupy a substantial 16:9 visual area.

The coach area should support these visual states: READY, LISTENING, THINKING, SPEAKING, EXPLAINING, ENCOURAGING, INTERVIEWING, WAITING FOR USER, SESSION COMPLETE.

The state must be visually obvious, e.g. "● Listening..." with an animated microphone waveform, "● Thinking..." with animated dots/subtle glow, "● Speaking..." with an animated voice waveform. Do not overuse animation. Keep it professional.

========================================================
COACH VISUAL EXPERIENCE
========================================================

Until a true talking-avatar service is configured: use the real coach portrait. Add subtle professional animation such as slow breathing movement, very slight camera-style zoom, soft active border when speaking, audio waveform, state transitions. Do NOT distort the coach image. Do NOT create cartoon animation. The result must still feel like a professional lecturer. Architecture must remain ready for a future live avatar/video provider.

========================================================
LIVE SESSION HEADER
========================================================

Inside the visual coach area show: LIVE, session timer, current activity (e.g. "LIVE 00:24:18 Explaining Python OOP"). Controls: Microphone, Speaker, Transcript, Pause if supported, End Session. Use icons and tooltips. Show active states.

========================================================
ANIMATIONS
========================================================

Add tasteful animation throughout: page transitions, card entrance, button hover/press, progress bar fill, active navigation transition, loading skeletons, coach speaking pulse, microphone listening animation, thinking animation, live waveform, toast notifications, success tick, lesson stage progression, modal slide/fade, expand/collapse cards.

Do NOT create distracting constant movement. Animation should communicate application state. Use CSS transitions / existing framework animation utilities where possible. Respect prefers-reduced-motion.

========================================================
TODAY'S LESSON
========================================================

Directly underneath the live coach visual show: topic, description, session duration, current stage. Create an actual lesson stage component: 1 Explain Concept, 2 Live Coding, 3 Your Turn, 4 Quiz, 5 Summary. Current step should animate/highlight. Completed steps should show completion. Clicking an available stage should change the lesson state where appropriate. Do not allow users to skip required stages if lesson logic says otherwise.

========================================================
LIVE TEACHING WORKSPACE
========================================================

Create a real teaching workspace using tabs or panels: Lesson, Code, Notes, Resources, Your Turn. The default lesson view should contain meaningful content.

========================================================
CODE PANEL
========================================================

Create a proper code display/editor component with syntax highlighting. For teaching examples: show code. For exercises: allow the user to write code. If code execution is already safely supported: wire it. Otherwise: use AI evaluation and clearly label execution unavailable. Controls may include Run, Reset, Ask Coach, Hint — only expose working controls.

========================================================
KEY POINTS PANEL
========================================================

Alongside code/examples show key points (e.g. Getter/Setter/Deleter/Inheritance with short descriptions). The information should come from the current lesson state.

========================================================
YOUR TURN MODE
========================================================

Critical. When the lesson reaches "Your Turn": replace passive content with an exercise (e.g. "Create a getter for the School name"). Provide: exercise, editor/answer box, Submit, Hint. On Submit: send answer to coach/backend, receive evaluation, show feedback, update learning progress, record the attempt. If incorrect: do not immediately reveal full solution — follow the Socratic teaching rules already defined.

========================================================
QUIZ MODE
========================================================

Interactive quiz component. One question at a time. Show "Question 2 of 5", progress bar, question, answer choices or text response, Submit Answer. After submit: correct/incorrect, brief explanation, progress update. At end: score, weak topics, recommended review. Persist quiz result.

========================================================
CHAT EXPERIENCE
========================================================

The coach conversation must remain available but not one huge blank rectangle. Modern message bubbles/cards. Coach message: coach image, coach name, response. User response: right-aligned or visually distinct. Show typing/thinking state, scroll to newest message, maintain history. Compact conversation area under the teaching workspace or in a collapsible panel.

========================================================
QUICK ACTION CONTROLS
========================================================

Redesign: Explain Again, Simplify This, Give an Example, Ask Me a Question, Quiz Me, Show Code, Next Topic, Mock Interview. Use icons, stronger button sizing, hover states, active states, tooltips. Every button must work:
- EXPLAIN AGAIN: send contextual command using current lesson.
- SIMPLIFY THIS: ask coach to explain current concept at a simpler level.
- GIVE AN EXAMPLE: generate another example for current lesson.
- ASK ME A QUESTION: coach asks the user a knowledge-check question.
- QUIZ ME: switch into quiz mode.
- SHOW CODE: open Code panel.
- NEXT TOPIC: move to correct next curriculum topic after eligibility check.
- MOCK INTERVIEW: open Interview mode.

========================================================
RIGHT SIDEBAR
========================================================

Improve all cards visually.

**Today's Plan**: show progress, time, task type, completion state (e.g. "● Learning Python OOP 30 min In progress", "○ Practice OOP exercise 20 min"). Use checkboxes/completion controls only if real task completion is supported. Clicking a task should open the relevant view.

**Learning Progress**: animated progress bars, icons, tooltips, expandable detail. For assessed subjects show real progress; for unknown subjects show "Not assessed" — never manufacture percentages. Click a subject to open My Progress / roadmap detail.

**Career Goal**: do not leave an empty card. If no goal exists show "No career goal configured" + working "Set Career Goal" button opening a real modal/form (target role, target timeline, priority skills). Save the result.

**Recent Activity**: proper timeline with event type icons (e.g. "✓ Completed Python lesson · 24 Sep · 14:20", "🎤 Mock interview · 24 Sep · 12:10"). Clicking relevant events should open related details.

========================================================
MAIN DASHBOARD PAGE
========================================================

Should NOT just duplicate Live Coach — an executive overview. Top: greeting, current streak, today completion %, next session. Sections: Today's Plan, Continue Learning, Skill Progress, Career Roadmap, Portfolio Projects, Job Application Pipeline, Interview Readiness, Recent Wins, Upcoming Review Topics, Quick Actions. Should feel like a personalised mission-control dashboard.

**Continue Learning**: current learning cards (e.g. "Python OOP 60% complete [Continue]"). Clicking Continue must open the correct lesson.

**Projects**: cards with name, status, technologies, skills demonstrated, completion %, GitHub if available. Actions: Continue Project, Review Project.

**Jobs**: pipeline (Interested/Preparing/Applied/Assessment/Interview/Offer) from real saved jobs. Working "Add Job" flow.

**Interview Prep**: polished mock interview screen, same coach identity. Layout: coach visual, question, timer, "Question x of y", response area, voice controls, interview type, current role. On completion show Technical Accuracy/Clarity/Structure/Communication/Completeness, animated result meters. Store the result.

**My Progress**: learning hours, topics completed, current streak, quiz average, interview sessions, projects, skills, revision queue. Charts sparingly. Only real data.

**Roadmap**: visually interactive phase nodes (Python, Data Analysis, Statistics, SQL, ML, Advanced ML, AI Engineering, Career Prep) with status (Not started/Learning/Practising/Needs revision/Competent/Mastered). Clicking a topic shows description, prerequisites, current status, last studied, recommended next action, Start/Continue Lesson.

========================================================
VISUAL DESIGN / DESIGN SYSTEM
========================================================

Strong visual hierarchy, professional typography, dark navy background, elevated cards, subtle gradients, blue/violet/cyan accents, meaningful icons, careful spacing, rounded panels, border highlights, subtle shadows, interactive states. Do not make everything the same colour or everything glow — create hierarchy.

Reusable tokens: background, surface, surface elevated, border, primary, secondary, success, warning, danger, text primary, text muted.

Reusable components: Card, Button, IconButton, ProgressBar, Badge, Modal, Tooltip, Toast, Tabs, Skeleton, EmptyState, Avatar, StatusIndicator. Do not duplicate styling across every page.

========================================================
EMPTY / LOADING / ERROR STATES
========================================================

No empty cards — always a useful message + working call-to-action (e.g. "No career goal yet [Set Career Goal]", "No projects yet [Create Project]", "No jobs saved [Add Job]", "No interview history [Start Mock Interview]").

Loading: skeleton UI, never blank panels.

Errors: useful message + Retry (e.g. "Unable to load learning progress. [Retry]"). Log errors appropriately. Do not silently fail.

========================================================
TOASTS / MICROINTERACTIONS
========================================================

Toast feedback for actions: "Progress saved", "Lesson completed", "Interview started", "Goal updated", "Unable to connect to coach".

Buttons: hover/press/disabled/loading. Cards: hover only where clickable. Progress: smooth changes. Navigation: animated selection indicator. Modals: fade/scale. Coach status: smooth state transitions.

========================================================
FUNCTIONAL TESTING
========================================================

After implementation, test every visible control via browser/dev tools or automated tests. Minimum matrix:
- Live Coach: start session, send message, Explain Again, Simplify, Example, Question, Quiz, Code, Next Topic, Mock Interview, Microphone, Speaker, Transcript, End Session.
- Dashboard: continue lesson, today's plan task, career goal, project, job, interview, progress detail.
- Navigation: all sidebar items.

========================================================
NO FAKE INTERACTION / REAL DATA
========================================================

A hover animation is NOT functionality. Every action must have actual application behaviour. Do not declare completion merely because something looks better.

Use the existing backend — do not overwrite the working data architecture. Wire plans, sessions, learning topics, career goals, activity, projects, jobs, interviews to the real UI. If an API does not yet exist, implement the minimal backend endpoint needed.

========================================================
RESPONSIVENESS / ACCESSIBILITY / PERFORMANCE
========================================================

Desktop: 3 columns. Laptop: adjust right sidebar width. Tablet: sidebar collapses. Mobile: coach first, lesson, quick actions, chat, progress, with a mobile navigation drawer.

Accessibility: keyboard navigation, visible focus, ARIA labels, button labels, sufficient contrast, reduced motion support.

Performance: lazy-load charts/code editor/avatar-video functionality. Avoid unnecessary animation loops.

========================================================
FINAL QUALITY EXPECTATION
========================================================

Must feel like a premium personal AI university lecturer + a career command centre + a productivity coach + an interview training platform. Must NOT feel like a generic chatbot, a static dashboard, an admin template, a collection of empty cards, or a UI prototype.

========================================================
BEFORE DECLARING COMPLETION
========================================================

Personally inspect every page. Click every visible button. Test real navigation. Test responsive behaviour. Test live backend data. Check browser console for errors. Check server logs. Verify persistence after refresh. Verify persistence after service restart. Verify Telegram/Hermes has not been broken.

========================================================
FINAL REPORT (expected format when this is implemented)
========================================================

1. Components redesigned.
2. Functional buttons repaired.
3. Buttons still disabled and why.
4. Animations implemented.
5. Live interactions implemented.
6. Real backend data sources used.
7. New backend endpoints created.
8. Coach image path.
9. Voice status.
10. Avatar status.
11. Responsive behaviour tested.
12. Tests run.
13. Browser console errors.
14. Server errors.
15. Remaining work.
16. Exact URL to test.
