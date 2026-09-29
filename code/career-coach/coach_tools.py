"""Agent-callable tools for the Data Science Career Coach profile.

Thin wrappers around coach_db.py (the same module the dashboard API reads
from) so a live coaching session actually leaves a trace: every lesson,
quiz result, interview, project/job update, or goal the coach records
through these tools is immediately visible on the "AI Career Coach"
dashboard tab - closing the gap between "the coach can talk" and "the
coach remembers".
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

from tools.registry import tool_error, tool_result

_COACH_DB_PATH = Path("/root/.hermes/profiles/data-science-career-coach/coach_db.py")
_coach_db = None


def _db():
    global _coach_db
    if _coach_db is not None:
        return _coach_db
    plugin_dir = str(_COACH_DB_PATH.parent)
    inserted = plugin_dir not in sys.path
    if inserted:
        sys.path.insert(0, plugin_dir)
    try:
        spec = importlib.util.spec_from_file_location("coach_db", _COACH_DB_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules["coach_db"] = module
        spec.loader.exec_module(module)
        module.init_db()
        _coach_db = module
        return module
    finally:
        if inserted:
            try:
                sys.path.remove(plugin_dir)
            except ValueError:
                pass


def _now() -> int:
    return int(time.time())


# ---- schema helpers (matches the style used by other Hermes tool plugins) ----

def _s(name: str, description: str, properties: dict, required: tuple = ()) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required)}}


_STR = {"type": "string"}
_NUM = {"type": "number"}
_INT = {"type": "integer"}
_STR_ARRAY = {"type": "array", "items": _STR}


COACH_RECORD_SESSION_SCHEMA = _s(
    "coach_record_session",
    "Record a completed or in-progress lesson/practice session so the coach remembers it next time. "
    "Call this at the end of any /learn, /practice, or /quiz interaction.",
    {
        "topic_id": {**_STR, "description": "Stable id for the topic, e.g. 'python-oop-getters-setters'. Reuse the same id across sessions on the same topic."},
        "topic_name": {**_STR, "description": "Human-readable topic name."},
        "duration_minutes": {**_NUM, "description": "How long the session lasted, in minutes."},
        "objectives": _STR,
        "concepts_understood": _STR_ARRAY,
        "concepts_misunderstood": _STR_ARRAY,
        "coach_notes": {**_STR, "description": "Your own notes on how it went, for future context."},
        "recommended_next_lesson": _STR,
    },
    ("topic_name",),
)

COACH_UPSERT_TOPIC_SCHEMA = _s(
    "coach_upsert_topic",
    "Create or update a learning-memory record for one topic: status, confidence, mastery score, "
    "quiz score, and next revision date. Call this whenever you assess how well the owner knows a topic.",
    {
        "topic_id": {**_STR, "description": "Stable id, e.g. 'python-oop-getters-setters'."},
        "topic_name": _STR,
        "category": {**_STR, "description": "One of: Python, SQL, Data Analysis, Statistics, Machine Learning, AI Engineering, Projects, Interview Preparation, Career Preparation."},
        "phase": {**_STR, "description": "Roadmap phase name, e.g. 'Python'."},
        "status": {"type": "string", "enum": ["not_started", "learning", "practising", "needs_revision", "competent", "mastered"]},
        "confidence": {**_NUM, "description": "0-100 self/coach-assessed confidence."},
        "mastery_score": {**_NUM, "description": "0-100 mastery score, used on the dashboard progress bars."},
        "quiz_score": _NUM,
        "next_review_in_days": {**_NUM, "description": "Schedule next revision this many days from now (spaced revision: 1, 3, 7, 14, or 30 are typical)."},
        "weakness_notes": _STR,
        "strength_notes": _STR,
    },
    ("topic_id", "topic_name", "category"),
)

COACH_RECORD_INTERVIEW_SCHEMA = _s(
    "coach_record_interview",
    "Save the result of a completed mock interview session, including scores and feedback.",
    {
        "role": {**_STR, "description": "Target role, e.g. 'Junior Data Scientist'."},
        "interview_type": {**_STR, "description": "e.g. Technical, Behavioural, Python, SQL, ML, AI Engineering, Portfolio, Case Study."},
        "difficulty": {"type": "string", "enum": ["entry", "intermediate", "senior"]},
        "questions": _STR_ARRAY,
        "answers": _STR_ARRAY,
        "scores": {"type": "object", "description": "e.g. {\"technical_accuracy\": 70, \"clarity\": 80, \"structure\": 75, \"communication\": 85, \"confidence\": 60, \"completeness\": 70}"},
        "feedback": _STR,
        "weak_concepts": _STR_ARRAY,
    },
    ("role", "interview_type", "difficulty"),
)

COACH_CREATE_PROJECT_SCHEMA = _s(
    "coach_create_project",
    "Track a new portfolio project the owner is starting or has built.",
    {
        "title": _STR, "description": _STR, "problem": _STR, "dataset": _STR,
        "skills_demonstrated": _STR_ARRAY, "technologies": _STR_ARRAY,
        "repo_url": _STR, "demo_url": _STR,
        "status": {"type": "string", "enum": ["planned", "in_progress", "complete", "deployed"]},
        "career_relevance": _STR,
    },
    ("title",),
)

COACH_CREATE_JOB_SCHEMA = _s(
    "coach_create_job",
    "Track a job the owner is interested in or has applied to, from a pasted job description.",
    {
        "company": _STR, "role": _STR, "url": _STR,
        "status": {"type": "string", "enum": ["interested", "preparing", "applied", "assessment", "interviewing", "offer", "rejected", "withdrawn"]},
        "skills_required": _STR_ARRAY, "skills_matched": _STR_ARRAY, "gaps": _STR_ARRAY,
        "notes": _STR, "next_action": _STR,
    },
    ("company", "role"),
)

COACH_CREATE_GOAL_SCHEMA = _s(
    "coach_create_goal",
    "Set a daily, weekly, or longer-term goal for the owner.",
    {
        "kind": {"type": "string", "enum": ["daily", "weekly", "goal"]},
        "description": _STR,
        "target_date": {**_STR, "description": "ISO date (YYYY-MM-DD), optional."},
    },
    ("kind", "description"),
)

COACH_UPDATE_CAREER_SCHEMA = _s(
    "coach_update_career",
    "Update the owner's overall career profile: goal, target roles, CV/LinkedIn/GitHub status.",
    {
        "career_goal": _STR,
        "target_roles": _STR_ARRAY,
        "cv_status": {"type": "string", "enum": ["not_assessed", "needs_work", "solid"]},
        "linkedin_status": {"type": "string", "enum": ["not_assessed", "needs_work", "solid"]},
        "github_status": {"type": "string", "enum": ["not_assessed", "needs_work", "solid"]},
    },
    (),
)

COACH_SET_SKILL_SCHEMA = _s(
    "coach_set_skill",
    "Update one skill's level on the career skill matrix. Only mark demonstrated/interview_ready "
    "when there is real evidence (a lesson, quiz, project, or interview) - never from a passing mention.",
    {
        "skill_name": _STR,
        "level": {"type": "string", "enum": ["not_assessed", "learning", "developing", "demonstrated", "interview_ready"]},
        "evidence_notes": {**_STR, "description": "What evidence justifies this level."},
    },
    ("skill_name", "level"),
)

COACH_GET_TODAY_SCHEMA = _s(
    "coach_get_today",
    "Get the owner's current due revisions, in-progress topics, active goals, and suggested next topic "
    "from stored memory - use this to ground a /today plan in real history instead of guessing.",
    {},
)

COACH_GET_PROGRESS_SCHEMA = _s(
    "coach_get_progress",
    "Get the owner's current learning progress by category and full skill matrix from stored memory.",
    {},
)

COACH_SET_LESSON_STAGE_SCHEMA = _s(
    "coach_set_lesson_stage",
    "Announce which stage of a live lesson or interview you're currently in, so the Live Coach "
    "dashboard can show a real, accurate progress tracker (never fabricated - only what you "
    "actually announce here shows up). Call this at the START of each stage during /learn: "
    "explain_concept, then live_coding (walking through code together), then your_turn (owner "
    "attempts something), then quiz, then summary. Call it with 'interview' when starting a mock "
    "interview, and 'idle' when the lesson/interview ends or you move to something unrelated.",
    {
        "stage": {"type": "string", "enum": ["explain_concept", "live_coding", "your_turn", "quiz", "summary", "interview", "idle"]},
        "topic_name": {**_STR, "description": "What the lesson/interview is about, shown alongside the stage."},
    },
    ("stage",),
)

COACH_GET_INTERVIEW_ANALYTICS_SCHEMA = _s(
    "coach_get_interview_analytics",
    "Get score trends across all past mock interviews (technical accuracy, clarity, structure, "
    "communication, confidence, completeness) and the most frequently missed concepts. Use this "
    "before or after a mock interview to reference real progress instead of guessing at trends.",
    {},
)


# ---- handlers ----

def _handle_record_session(args: dict, **kw) -> str:
    db = _db()
    duration_min = args.get("duration_minutes")
    started_at = _now() - int(duration_min * 60) if duration_min else _now()
    try:
        row = db.record_session(
            topic_id=args.get("topic_id"), topic_name=args.get("topic_name"),
            started_at=started_at, ended_at=_now(),
            objectives=args.get("objectives"),
            concepts_understood=args.get("concepts_understood"),
            concepts_misunderstood=args.get("concepts_misunderstood"),
            coach_notes=args.get("coach_notes"),
            recommended_next_lesson=args.get("recommended_next_lesson"),
        )
        return tool_result(session_id=row["id"], recorded=True)
    except Exception as exc:
        return tool_error(f"Failed to record session: {exc}")


def _handle_upsert_topic(args: dict, **kw) -> str:
    db = _db()
    fields: dict[str, Any] = {}
    for key in ("status", "confidence", "mastery_score", "quiz_score", "weakness_notes", "strength_notes"):
        if args.get(key) is not None:
            fields[key] = args[key]
    if args.get("next_review_in_days") is not None:
        fields["next_review"] = _now() + int(args["next_review_in_days"] * 86400)
    fields["last_studied"] = _now()
    try:
        row = db.upsert_topic(args["topic_id"], args["topic_name"], args["category"], args.get("phase"), **fields)
        return tool_result(topic=row)
    except Exception as exc:
        return tool_error(f"Failed to update topic: {exc}")


def _handle_record_interview(args: dict, **kw) -> str:
    db = _db()
    try:
        row = db.record_interview(
            role=args["role"], interview_type=args["interview_type"], difficulty=args["difficulty"],
            started_at=_now(), ended_at=_now(),
            questions=args.get("questions"), answers=args.get("answers"), scores=args.get("scores"),
            feedback=args.get("feedback"), weak_concepts=args.get("weak_concepts"),
        )
        return tool_result(interview_id=row["id"], recorded=True)
    except Exception as exc:
        return tool_error(f"Failed to record interview: {exc}")


def _handle_create_project(args: dict, **kw) -> str:
    db = _db()
    try:
        fields = {k: v for k, v in args.items() if k != "title" and v is not None}
        row = db.create_project(args["title"], **fields)
        return tool_result(project_id=row["id"], recorded=True)
    except Exception as exc:
        return tool_error(f"Failed to create project: {exc}")


def _handle_create_job(args: dict, **kw) -> str:
    db = _db()
    try:
        fields = {k: v for k, v in args.items() if k not in ("company", "role") and v is not None}
        row = db.create_job(args["company"], args["role"], **fields)
        return tool_result(job_id=row["id"], recorded=True)
    except Exception as exc:
        return tool_error(f"Failed to create job: {exc}")


def _handle_create_goal(args: dict, **kw) -> str:
    db = _db()
    target_date = None
    if args.get("target_date"):
        try:
            import datetime
            target_date = int(datetime.datetime.strptime(args["target_date"], "%Y-%m-%d").timestamp())
        except ValueError:
            return tool_error("target_date must be an ISO date, YYYY-MM-DD")
    try:
        row = db.create_goal(args["kind"], args["description"], target_date)
        return tool_result(goal_id=row["id"], recorded=True)
    except Exception as exc:
        return tool_error(f"Failed to create goal: {exc}")


def _handle_update_career(args: dict, **kw) -> str:
    db = _db()
    try:
        fields = {k: v for k, v in args.items() if v is not None}
        row = db.update_career_profile(**fields)
        return tool_result(career=row)
    except Exception as exc:
        return tool_error(f"Failed to update career profile: {exc}")


def _handle_set_skill(args: dict, **kw) -> str:
    db = _db()
    try:
        row = db.set_skill_level(args["skill_name"], args["level"], args.get("evidence_notes"))
        return tool_result(skill=row)
    except ValueError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"Failed to set skill: {exc}")


def _handle_get_today(args: dict, **kw) -> str:
    db = _db()
    try:
        return tool_result(db.today_plan())
    except Exception as exc:
        return tool_error(f"Failed to load today plan: {exc}")


def _handle_get_progress(args: dict, **kw) -> str:
    db = _db()
    try:
        return tool_result(categories=db.learning_progress_summary(), skills=db.list_skills())
    except Exception as exc:
        return tool_error(f"Failed to load progress: {exc}")


def _handle_set_lesson_stage(args: dict, **kw) -> str:
    db = _db()
    try:
        row = db.set_live_stage(args["stage"], args.get("topic_name"))
        return tool_result(stage=row)
    except ValueError as exc:
        return tool_error(str(exc))
    except Exception as exc:
        return tool_error(f"Failed to set lesson stage: {exc}")


def _handle_get_interview_analytics(args: dict, **kw) -> str:
    db = _db()
    try:
        return tool_result(db.interview_analytics())
    except Exception as exc:
        return tool_error(f"Failed to load interview analytics: {exc}")


TOOLS = (
    ("coach_record_session", COACH_RECORD_SESSION_SCHEMA, _handle_record_session, "📘"),
    ("coach_upsert_topic", COACH_UPSERT_TOPIC_SCHEMA, _handle_upsert_topic, "🧠"),
    ("coach_record_interview", COACH_RECORD_INTERVIEW_SCHEMA, _handle_record_interview, "🎤"),
    ("coach_create_project", COACH_CREATE_PROJECT_SCHEMA, _handle_create_project, "🛠"),
    ("coach_create_job", COACH_CREATE_JOB_SCHEMA, _handle_create_job, "💼"),
    ("coach_create_goal", COACH_CREATE_GOAL_SCHEMA, _handle_create_goal, "🎯"),
    ("coach_update_career", COACH_UPDATE_CAREER_SCHEMA, _handle_update_career, "🧭"),
    ("coach_set_skill", COACH_SET_SKILL_SCHEMA, _handle_set_skill, "📊"),
    ("coach_get_today", COACH_GET_TODAY_SCHEMA, _handle_get_today, "📅"),
    ("coach_get_progress", COACH_GET_PROGRESS_SCHEMA, _handle_get_progress, "📈"),
    ("coach_get_interview_analytics", COACH_GET_INTERVIEW_ANALYTICS_SCHEMA, _handle_get_interview_analytics, "📊"),
    ("coach_set_lesson_stage", COACH_SET_LESSON_STAGE_SCHEMA, _handle_set_lesson_stage, "🎬"),
)
