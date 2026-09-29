"""Shared storage module for the Data Science Career Coach profile.

Single source of truth for learning memory, session memory, career memory,
interview history, projects, jobs, goals and the roadmap. Both the dashboard
API (plugin_api.py) and the agent's own coach tools import this module
directly, so there is exactly one code path that writes coach.db - avoiding
the kind of two-path drift bug found and fixed earlier in kanban_db.py.

SQLite, matching the rest of this Hermes install's storage (kanban.db,
state.db, projects.db) - no new database engine introduced.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path("/root/.hermes/profiles/data-science-career-coach/coach.db")

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_topics (
    topic_id TEXT PRIMARY KEY,
    topic_name TEXT NOT NULL,
    category TEXT NOT NULL,
    phase TEXT,
    status TEXT NOT NULL DEFAULT 'not_started',
    confidence REAL,
    mastery_score REAL,
    times_studied INTEGER NOT NULL DEFAULT 0,
    times_practised INTEGER NOT NULL DEFAULT 0,
    quiz_score REAL,
    last_studied INTEGER,
    next_review INTEGER,
    weakness_notes TEXT,
    strength_notes TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    duration_seconds INTEGER,
    topic_id TEXT,
    topic_name TEXT,
    objectives TEXT,
    questions_asked TEXT,
    user_answers TEXT,
    mistakes TEXT,
    concepts_understood TEXT,
    concepts_misunderstood TEXT,
    practice_completed TEXT,
    coach_notes TEXT,
    recommended_next_lesson TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS career_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    career_goal TEXT,
    target_roles TEXT,
    cv_status TEXT DEFAULT 'not_assessed',
    linkedin_status TEXT DEFAULT 'not_assessed',
    github_status TEXT DEFAULT 'not_assessed',
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS skills_matrix (
    skill_name TEXT PRIMARY KEY,
    level TEXT NOT NULL DEFAULT 'not_assessed',
    evidence_notes TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    problem TEXT,
    dataset TEXT,
    skills_demonstrated TEXT,
    technologies TEXT,
    repo_url TEXT,
    demo_url TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    readme_quality TEXT,
    career_relevance TEXT,
    recommended_improvements TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    url TEXT,
    date_found INTEGER,
    date_applied INTEGER,
    status TEXT NOT NULL DEFAULT 'interested',
    salary TEXT,
    skills_required TEXT,
    skills_matched TEXT,
    gaps TEXT,
    notes TEXT,
    next_action TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    role TEXT,
    interview_type TEXT,
    difficulty TEXT,
    questions TEXT,
    answers TEXT,
    scores TEXT,
    feedback TEXT,
    weak_concepts TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    target_date INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS roadmap_phases (
    phase_id TEXT PRIMARY KEY,
    phase_name TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    items TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_log (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS live_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    stage TEXT,
    topic_name TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    topic_name TEXT,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""

# A live-session stage is only shown as "current" on the dashboard within this
# window - past that it's treated as stale (a finished/abandoned session), not
# faked as still in progress.
LIVE_STAGE_STALE_SECONDS = 20 * 60
VALID_LESSON_STAGES = ("explain_concept", "live_coding", "your_turn", "quiz", "summary", "interview", "idle")

_ROADMAP_SEED = [
    ("phase1", "Python", 1, ["Python fundamentals", "Functions", "OOP", "Error handling", "Files", "Modules", "Testing"]),
    ("phase2", "Data Analysis", 2, ["NumPy", "Pandas", "Cleaning", "EDA", "Visualisation"]),
    ("phase3", "Statistics", 3, ["Descriptive statistics", "Probability", "Distributions", "Hypothesis testing", "Correlation", "Regression foundations"]),
    ("phase4", "SQL", 4, ["Queries", "Filtering", "Aggregations", "Joins", "Subqueries", "CTEs", "Window functions"]),
    ("phase5", "Machine Learning", 5, ["Preprocessing", "Feature engineering", "Regression", "Classification", "Clustering", "Model evaluation", "Cross-validation", "Hyperparameter tuning", "Pipelines"]),
    ("phase6", "Advanced ML", 6, ["Ensembles", "XGBoost", "Feature importance", "Time series", "NLP foundations"]),
    ("phase7", "AI Engineering", 7, ["APIs", "Git", "Docker", "Deployment", "Cloud", "LLMs", "Embeddings", "Vector databases", "RAG", "Agents", "Evaluation", "Observability"]),
    ("phase8", "Employment", 8, ["Portfolio", "GitHub", "CV", "LinkedIn", "Applications", "Technical interviews", "Behavioural interviews", "Case studies", "Negotiation", "First 90 days"]),
]

_SKILLS_SEED = [
    "Python", "SQL", "Pandas", "NumPy", "Statistics", "Machine Learning",
    "Git", "Docker", "Cloud", "APIs", "LLMs", "RAG", "AI Agents",
]


def _now() -> int:
    return int(time.time())


@contextmanager
def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', ?)", (str(SCHEMA_VERSION),))
        existing = conn.execute("SELECT COUNT(*) c FROM roadmap_phases").fetchone()["c"]
        if existing == 0:
            for phase_id, name, order_index, items in _ROADMAP_SEED:
                conn.execute(
                    "INSERT INTO roadmap_phases (phase_id, phase_name, order_index, items) VALUES (?,?,?,?)",
                    (phase_id, name, order_index, json.dumps(items)),
                )
        existing_skills = conn.execute("SELECT COUNT(*) c FROM skills_matrix").fetchone()["c"]
        if existing_skills == 0:
            now = _now()
            for skill in _SKILLS_SEED:
                conn.execute(
                    "INSERT INTO skills_matrix (skill_name, level, updated_at) VALUES (?, 'not_assessed', ?)",
                    (skill, now),
                )
        existing_career = conn.execute("SELECT COUNT(*) c FROM career_profile").fetchone()["c"]
        if existing_career == 0:
            conn.execute(
                "INSERT INTO career_profile (id, career_goal, target_roles, updated_at) VALUES (1, NULL, '[]', ?)",
                (_now(),),
            )
        existing_live = conn.execute("SELECT COUNT(*) c FROM live_state").fetchone()["c"]
        if existing_live == 0:
            conn.execute(
                "INSERT INTO live_state (id, stage, topic_name, updated_at) VALUES (1, NULL, NULL, ?)",
                (_now(),),
            )


def _log_activity(conn, kind: str, summary: str) -> None:
    conn.execute(
        "INSERT INTO activity_log (id, kind, summary, created_at) VALUES (?,?,?,?)",
        (str(uuid.uuid4())[:8], kind, summary, _now()),
    )


# ---- learning topics -------------------------------------------------

def upsert_topic(topic_id: str, topic_name: str, category: str, phase: str | None = None, **fields: Any) -> dict:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM learning_topics WHERE topic_id=?", (topic_id,)).fetchone()
        now = _now()
        if row is None:
            conn.execute(
                "INSERT INTO learning_topics (topic_id, topic_name, category, phase, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (topic_id, topic_name, category, phase, fields.get("status", "not_started"), now, now),
            )
        allowed = {"status", "confidence", "mastery_score", "times_studied", "times_practised",
                   "quiz_score", "last_studied", "next_review", "weakness_notes", "strength_notes"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if sets:
            cols = ", ".join(f"{k}=?" for k in sets)
            conn.execute(f"UPDATE learning_topics SET {cols}, updated_at=? WHERE topic_id=?",
                         (*sets.values(), now, topic_id))
        _log_activity(conn, "topic_update", f"Updated topic: {topic_name}")
        return dict(conn.execute("SELECT * FROM learning_topics WHERE topic_id=?", (topic_id,)).fetchone())


def list_topics(status: str | None = None) -> list[dict]:
    with _conn() as conn:
        if status:
            rows = conn.execute("SELECT * FROM learning_topics WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM learning_topics ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]


def due_revisions(as_of: int | None = None) -> list[dict]:
    as_of = as_of or _now()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM learning_topics WHERE next_review IS NOT NULL AND next_review <= ? ORDER BY next_review ASC",
            (as_of,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---- sessions ----------------------------------------------------------

def record_session(topic_id: str | None, topic_name: str | None, started_at: int, ended_at: int | None = None,
                    **fields: Any) -> dict:
    with _conn() as conn:
        sid = str(uuid.uuid4())[:8]
        duration = (ended_at - started_at) if ended_at else None
        json_fields = {k: json.dumps(v) if isinstance(v, (list, dict)) else v
                       for k, v in fields.items()}
        conn.execute(
            "INSERT INTO sessions (id, started_at, ended_at, duration_seconds, topic_id, topic_name, objectives, "
            "questions_asked, user_answers, mistakes, concepts_understood, concepts_misunderstood, "
            "practice_completed, coach_notes, recommended_next_lesson, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, started_at, ended_at, duration, topic_id, topic_name,
             json_fields.get("objectives"), json_fields.get("questions_asked"), json_fields.get("user_answers"),
             json_fields.get("mistakes"), json_fields.get("concepts_understood"), json_fields.get("concepts_misunderstood"),
             json_fields.get("practice_completed"), json_fields.get("coach_notes"), json_fields.get("recommended_next_lesson"),
             _now()),
        )
        _log_activity(conn, "session", f"Session: {topic_name or topic_id or 'general'}")
        return dict(conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone())


def list_sessions(limit: int = 20) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


# ---- career profile / skills matrix ------------------------------------

def get_career_profile() -> dict:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM career_profile WHERE id=1").fetchone()
        return dict(row) if row else {}


def update_career_profile(**fields: Any) -> dict:
    allowed = {"career_goal", "target_roles", "cv_status", "linkedin_status", "github_status"}
    sets = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in fields.items() if k in allowed}
    with _conn() as conn:
        if sets:
            cols = ", ".join(f"{k}=?" for k in sets)
            conn.execute(f"UPDATE career_profile SET {cols}, updated_at=? WHERE id=1", (*sets.values(), _now()))
            _log_activity(conn, "career_update", "Updated career profile")
        return dict(conn.execute("SELECT * FROM career_profile WHERE id=1").fetchone())


def set_live_stage(stage: str, topic_name: str | None = None) -> dict:
    """Record the coach's own real signal of what stage of a live lesson/interview it's
    currently in. Only ever set by the coach itself calling coach_set_lesson_stage - never
    inferred or guessed by the dashboard, so it can never show a stage the coach didn't
    actually announce."""
    if stage not in VALID_LESSON_STAGES:
        raise ValueError(f"invalid stage {stage!r}, must be one of {VALID_LESSON_STAGES}")
    with _conn() as conn:
        conn.execute("UPDATE live_state SET stage=?, topic_name=?, updated_at=? WHERE id=1",
                     (stage, topic_name, _now()))
        return dict(conn.execute("SELECT * FROM live_state WHERE id=1").fetchone())


def get_live_state() -> dict:
    """Current lesson/interview stage, or stage=None if nothing was ever set or the last
    signal is older than LIVE_STAGE_STALE_SECONDS (treated as a finished/abandoned session,
    not shown as if still live)."""
    with _conn() as conn:
        row = dict(conn.execute("SELECT * FROM live_state WHERE id=1").fetchone())
    if row.get("stage") and row.get("stage") != "idle" and (_now() - row["updated_at"]) > LIVE_STAGE_STALE_SECONDS:
        row["stage"] = None
        row["stale"] = True
    else:
        row["stale"] = False
    return row


def save_note(content: str, topic_name: str | None = None) -> dict:
    with _conn() as conn:
        nid = str(uuid.uuid4())[:8]
        conn.execute("INSERT INTO notes (id, topic_name, content, created_at) VALUES (?,?,?,?)",
                     (nid, topic_name, content, _now()))
        _log_activity(conn, "note", "Saved notes" + (f": {topic_name}" if topic_name else ""))
        return dict(conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone())


def list_notes(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]


def list_skills() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM skills_matrix ORDER BY skill_name ASC").fetchall()
        return [dict(r) for r in rows]


def set_skill_level(skill_name: str, level: str, evidence_notes: str | None = None) -> dict:
    valid = {"not_assessed", "learning", "developing", "demonstrated", "interview_ready"}
    if level not in valid:
        raise ValueError(f"invalid level {level!r}, must be one of {valid}")
    with _conn() as conn:
        existing = conn.execute("SELECT 1 FROM skills_matrix WHERE skill_name=?", (skill_name,)).fetchone()
        now = _now()
        if existing:
            conn.execute("UPDATE skills_matrix SET level=?, evidence_notes=?, updated_at=? WHERE skill_name=?",
                         (level, evidence_notes, now, skill_name))
        else:
            conn.execute("INSERT INTO skills_matrix (skill_name, level, evidence_notes, updated_at) VALUES (?,?,?,?)",
                         (skill_name, level, evidence_notes, now))
        _log_activity(conn, "skill_update", f"Skill {skill_name} -> {level}")
        return dict(conn.execute("SELECT * FROM skills_matrix WHERE skill_name=?", (skill_name,)).fetchone())


# ---- projects / jobs / interviews / goals (CRUD) ------------------------

def create_project(title: str, **fields: Any) -> dict:
    with _conn() as conn:
        pid = str(uuid.uuid4())[:8]
        now = _now()
        json_fields = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in fields.items()}
        conn.execute(
            "INSERT INTO projects (id, title, description, problem, dataset, skills_demonstrated, technologies, "
            "repo_url, demo_url, status, readme_quality, career_relevance, recommended_improvements, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, title, json_fields.get("description"), json_fields.get("problem"), json_fields.get("dataset"),
             json_fields.get("skills_demonstrated"), json_fields.get("technologies"), json_fields.get("repo_url"),
             json_fields.get("demo_url"), json_fields.get("status", "planned"), json_fields.get("readme_quality"),
             json_fields.get("career_relevance"), json_fields.get("recommended_improvements"), now, now),
        )
        _log_activity(conn, "project", f"Project created: {title}")
        return dict(conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())


def list_projects() -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()]


def create_job(company: str, role: str, **fields: Any) -> dict:
    with _conn() as conn:
        jid = str(uuid.uuid4())[:8]
        now = _now()
        json_fields = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in fields.items()}
        conn.execute(
            "INSERT INTO jobs (id, company, role, url, date_found, date_applied, status, salary, skills_required, "
            "skills_matched, gaps, notes, next_action, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (jid, company, role, json_fields.get("url"), json_fields.get("date_found"), json_fields.get("date_applied"),
             json_fields.get("status", "interested"), json_fields.get("salary"), json_fields.get("skills_required"),
             json_fields.get("skills_matched"), json_fields.get("gaps"), json_fields.get("notes"),
             json_fields.get("next_action"), now, now),
        )
        _log_activity(conn, "job", f"Job tracked: {role} @ {company}")
        return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())


def list_jobs() -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()]


def record_interview(role: str, interview_type: str, difficulty: str, started_at: int, **fields: Any) -> dict:
    with _conn() as conn:
        iid = str(uuid.uuid4())[:8]
        now = _now()
        json_fields = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in fields.items()}
        conn.execute(
            "INSERT INTO interviews (id, started_at, ended_at, role, interview_type, difficulty, questions, answers, "
            "scores, feedback, weak_concepts, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, started_at, fields.get("ended_at"), role, interview_type, difficulty,
             json_fields.get("questions"), json_fields.get("answers"), json_fields.get("scores"),
             json_fields.get("feedback"), json_fields.get("weak_concepts"), now),
        )
        _log_activity(conn, "interview", f"{interview_type} interview ({role})")
        return dict(conn.execute("SELECT * FROM interviews WHERE id=?", (iid,)).fetchone())


def list_interviews(limit: int = 20) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM interviews ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]


def interview_analytics() -> dict:
    """Score trends and frequently-missed concepts across all recorded interviews.
    Real aggregation over stored rows only - an empty interviews table produces an
    explicitly empty result, never a fabricated trend."""
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM interviews ORDER BY created_at ASC").fetchall()
    trend = []
    concept_counts: dict[str, int] = {}
    for r in rows:
        d = dict(r)
        scores = json.loads(d["scores"]) if d.get("scores") else {}
        trend.append({
            "id": d["id"], "date": d["created_at"], "role": d["role"],
            "interview_type": d["interview_type"], "difficulty": d["difficulty"],
            "scores": scores,
        })
        for concept in json.loads(d["weak_concepts"]) if d.get("weak_concepts") else []:
            concept_counts[concept] = concept_counts.get(concept, 0) + 1
    frequently_missed = sorted(concept_counts.items(), key=lambda kv: -kv[1])
    dimensions = ["technical_accuracy", "clarity", "structure", "communication", "confidence", "completeness"]
    averages = {}
    for dim in dimensions:
        vals = [t["scores"][dim] for t in trend if dim in t["scores"]]
        averages[dim] = round(sum(vals) / len(vals), 1) if vals else None
    return {
        "total_interviews": len(trend),
        "trend": trend,
        "averages": averages,
        "frequently_missed_concepts": [{"concept": c, "count": n} for c, n in frequently_missed],
    }


def create_goal(kind: str, description: str, target_date: int | None = None) -> dict:
    with _conn() as conn:
        gid = str(uuid.uuid4())[:8]
        now = _now()
        conn.execute(
            "INSERT INTO goals (id, kind, description, status, target_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (gid, kind, description, "active", target_date, now, now),
        )
        _log_activity(conn, "goal", f"Goal set: {description}")
        return dict(conn.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone())


def list_goals(status: str | None = None) -> list[dict]:
    with _conn() as conn:
        if status:
            rows = conn.execute("SELECT * FROM goals WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def update_goal_status(goal_id: str, status: str) -> dict:
    with _conn() as conn:
        conn.execute("UPDATE goals SET status=?, updated_at=? WHERE id=?", (status, _now(), goal_id))
        return dict(conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone())


# ---- roadmap -------------------------------------------------------------

def get_roadmap() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM roadmap_phases ORDER BY order_index ASC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["items"] = json.loads(d["items"])
            out.append(d)
        return out


# ---- activity / dashboard composition -----------------------------------

def recent_activity(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()]


def learning_progress_summary() -> dict:
    """Progress per top-level category, 0-100. 'not_assessed' if no topics recorded for it."""
    categories = ["Python", "SQL", "Data Analysis", "Statistics", "Machine Learning",
                  "AI Engineering", "Projects", "Interview Preparation", "Career Preparation"]
    with _conn() as conn:
        out = {}
        for cat in categories:
            rows = conn.execute("SELECT mastery_score FROM learning_topics WHERE category=?", (cat,)).fetchall()
            scores = [r["mastery_score"] for r in rows if r["mastery_score"] is not None]
            out[cat] = round(sum(scores) / len(scores), 1) if scores else None
        return out


def today_plan() -> dict:
    """Deterministic composition of a default plan from stored state - not LLM-generated.
    The chat agent can produce a richer conversational /today using the same tables; this is
    what the dashboard renders without needing a model call."""
    revisions = due_revisions()
    topics = list_topics(status="learning") + list_topics(status="practising")
    goals = list_goals(status="active")
    next_new_topic = None
    if not topics:
        covered = {t["topic_name"] for t in list_topics()}
        for phase in get_roadmap():
            for item in phase["items"]:
                if item not in covered:
                    next_new_topic = {"phase": phase["phase_name"], "topic": item}
                    break
            if next_new_topic:
                break
    return {
        "due_revisions": revisions,
        "in_progress_topics": topics,
        "active_goals": goals,
        "suggested_next_topic": next_new_topic,
    }


def learning_stats() -> dict:
    """Real, computed stats for the My Progress / Analytics pages and the dashboard
    header - every number here comes from an actual query, nothing is estimated."""
    with _conn() as conn:
        total_seconds = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) s FROM sessions WHERE duration_seconds IS NOT NULL"
        ).fetchone()["s"]
        topics_completed = conn.execute(
            "SELECT COUNT(*) c FROM learning_topics WHERE status IN ('competent', 'mastered')"
        ).fetchone()["c"]
        total_topics = conn.execute("SELECT COUNT(*) c FROM learning_topics").fetchone()["c"]
        interview_count = conn.execute("SELECT COUNT(*) c FROM interviews").fetchone()["c"]
        project_count = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
        day_rows = conn.execute(
            "SELECT DISTINCT date(created_at, 'unixepoch') d FROM activity_log ORDER BY d DESC"
        ).fetchall()
    days = {r["d"] for r in day_rows}
    streak = 0
    cursor_date = datetime.now(timezone.utc).date()
    while cursor_date.isoformat() in days:
        streak += 1
        cursor_date -= timedelta(days=1)
    return {
        "total_learning_hours": round(total_seconds / 3600, 1),
        "topics_completed": topics_completed,
        "total_topics": total_topics,
        "interview_sessions": interview_count,
        "projects": project_count,
        "revision_queue": len(due_revisions()),
        "current_streak_days": streak,
    }


if __name__ == "__main__":
    init_db()
    print(f"coach.db initialised at {DB_PATH}")
