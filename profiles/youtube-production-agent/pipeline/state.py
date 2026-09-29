"""Explicit, persistent job state for each video project, plus a content
memory of past projects (to reduce repeated topics/hooks/titles).

Each project is one JSON file under projects/<slug>.json. No database
dependency - this is genuinely persisted, inspectable state.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

PROJECTS_ROOT = Path(__file__).parent.parent / "projects"


class ProjectState(str, Enum):
    IDEA = "IDEA"
    RESEARCHING = "RESEARCHING"
    SCORED = "SCORED"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    SCRIPTING = "SCRIPTING"
    FACT_CHECK = "FACT_CHECK"
    RETENTION_REVIEW = "RETENTION_REVIEW"
    STORYBOARD = "STORYBOARD"
    VISUAL_PRODUCTION = "VISUAL_PRODUCTION"
    VOICE = "VOICE"
    ASSEMBLY = "ASSEMBLY"
    QUALITY_REVIEW = "QUALITY_REVIEW"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ANALYSING = "ANALYSING"
    FAILED = "FAILED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProjectRecord:
    slug: str
    topic: str
    niche: str = ""
    audience: str = ""
    state: str = ProjectState.IDEA.value
    viral_score: int | None = None
    score_breakdown: dict = field(default_factory=dict)
    chosen_angle: str = ""
    hook: str = ""
    title: str = ""
    video_length_minutes: int = 8
    qc_verdict: str = ""
    qc_attempts: int = 0
    created_at: str = ""
    updated_at: str = ""
    stage_history: list = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    lessons_learned: list = field(default_factory=list)
    performance: dict = field(default_factory=dict)
    limitations: list = field(default_factory=list)
    failure_reason: str = ""

    def touch(self) -> None:
        self.updated_at = _now()

    def advance(self, new_state: ProjectState, summary: str = "") -> None:
        self.state = new_state.value
        self.touch()
        self.stage_history.append({"state": new_state.value, "at": self.updated_at, "summary": summary})

    def fail(self, reason: str) -> None:
        self.failure_reason = reason
        self.advance(ProjectState.FAILED, summary=reason)

    def record_artifact(self, name: str, path: Path) -> None:
        try:
            rel = str(path.relative_to(Path(__file__).parent.parent))
        except ValueError:
            rel = str(path)
        self.artifacts[name] = rel

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self) -> Path:
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        path = PROJECTS_ROOT / f"{self.slug}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, slug: str) -> "ProjectRecord":
        path = PROJECTS_ROOT / f"{slug}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def create(cls, slug: str, topic: str, **kwargs) -> "ProjectRecord":
        now = _now()
        return cls(slug=slug, topic=topic, created_at=now, updated_at=now, **kwargs)


def list_projects() -> list[dict]:
    """Lightweight content-memory summary of every past project, newest
    last, used to flag repeated topics/hooks/titles before committing to a
    new one."""
    if not PROJECTS_ROOT.exists():
        return []
    out = []
    for f in sorted(PROJECTS_ROOT.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "slug": d.get("slug"), "topic": d.get("topic"), "title": d.get("title"),
            "hook": d.get("hook"), "state": d.get("state"), "viral_score": d.get("viral_score"),
            "created_at": d.get("created_at"), "lessons_learned": d.get("lessons_learned", []),
        })
    return out
