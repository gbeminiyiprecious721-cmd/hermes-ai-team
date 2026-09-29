"""Individual pipeline stage functions. Each wraps agent.YouTubeProductionAgent
with the agency prompts and the configured model tier for that kind of work.
Pure functions over (agent, config, ...) -> str | dict so the orchestrator can
sequence, persist, and gate between them.
"""
from __future__ import annotations

from agent import YouTubeProductionAgent
from pipeline import prompts_agency as p


def _model(config: dict, tier: str) -> str:
    return config["models"].get(tier, config["models"]["standard"])


async def _safe_search_call(agent: YouTubeProductionAgent, system: str, user: str, *,
                             model: str, stage_name: str) -> str:
    """WebSearch-backed stages depend on live, uncontrolled search behavior
    (result quality, how many searches the model needs, page fetch failures).
    A failure here (turn limit, tool error, network issue) must not take down
    the whole pipeline - it must be reported honestly as unavailable so the
    caller can decide how to proceed, per the no-fabrication requirement."""
    try:
        return await agent.call_with_search(system, user, model=model)
    except Exception as e:
        return (
            f"UNAVAILABLE: live web search failed for {stage_name} "
            f"({type(e).__name__}: {e}). No fabricated data is substituted."
        )


async def trend_research(agent: YouTubeProductionAgent, config: dict, niche: str,
                          audience: str, extra_context: str = "") -> str:
    system = p.TREND_RESEARCH_SYSTEM.format(niche=niche)
    user = p.TREND_RESEARCH_USER.format(
        niche=niche, audience=audience,
        extra_context=f"Additional context: {extra_context}" if extra_context else "",
    )
    return await _safe_search_call(agent, system, user, model=_model(config, "research"), stage_name="trend research")


async def outlier_analysis(agent: YouTubeProductionAgent, config: dict, niche: str, topic: str) -> str:
    user = p.OUTLIER_ANALYSIS_USER.format(niche=niche, topic=topic)
    return await _safe_search_call(
        agent, p.OUTLIER_ANALYSIS_SYSTEM, user, model=_model(config, "research"),
        stage_name=f"outlier analysis ({topic})",
    )


def compute_score(breakdown: dict) -> int:
    return sum(int(v) for v in breakdown.values())


async def score_topic(agent: YouTubeProductionAgent, config: dict, topic: str, niche: str,
                       audience: str, trend_research_text: str, outlier_text: str,
                       past_topics: list[str]) -> dict:
    user = p.VIRAL_SCORE_USER.format(
        topic=topic, niche=niche, audience=audience,
        trend_research=trend_research_text or "(unavailable)",
        outlier_analysis=outlier_text or "(unavailable)",
        past_topics="\n".join(f"- {t}" for t in past_topics) if past_topics else "(none yet)",
    )
    result = await agent.call_json(p.VIRAL_SCORE_SYSTEM, user, model=_model(config, "standard"))
    breakdown = result.get("score_breakdown", {})
    result["score"] = compute_score(breakdown) if breakdown else int(result.get("score", 0))
    return result


def gate_decision(score: int, config: dict) -> str:
    thresholds = config["thresholds"]
    if score >= thresholds["high_priority"]:
        return "HIGH_PRIORITY"
    if score >= thresholds["improve_angle"]:
        return "IMPROVE_ANGLE"
    return "REJECT"


async def research_brief(agent: YouTubeProductionAgent, config: dict, topic: str, angle: str,
                          audience: str) -> str:
    user = p.RESEARCH_BRIEF_USER.format(topic=topic, angle=angle, audience=audience)
    return await _safe_search_call(
        agent, p.RESEARCH_BRIEF_SYSTEM, user, model=_model(config, "research"),
        stage_name=f"research brief ({topic})",
    )


async def fact_check(agent: YouTubeProductionAgent, config: dict, research_brief_text: str,
                      script_text: str) -> dict:
    user = p.FACT_CHECK_USER.format(research_brief=research_brief_text, script=script_text)
    return await agent.call_json(p.FACT_CHECK_SYSTEM, user, model=_model(config, "fact_checking"))


async def write_script(agent: YouTubeProductionAgent, config: dict, topic: str, angle: str,
                        hook: str, duration_minutes: int, audience: str, tone: str,
                        research_brief_text: str, fact_check_notes: str = "") -> str:
    word_count = duration_minutes * 150
    user = p.AGENCY_SCRIPT_USER.format(
        topic=topic, angle=angle, hook=hook, duration=duration_minutes, word_count=word_count,
        audience=audience, tone=tone, research_brief=research_brief_text,
        fact_check_notes=fact_check_notes or "(no fact-check notes yet)",
    )
    return await agent._call(p.AGENCY_SCRIPT_SYSTEM, user, model=_model(config, "complex_reasoning"))


async def retention_review(agent: YouTubeProductionAgent, config: dict, script_text: str,
                            audience: str) -> str:
    user = p.RETENTION_REVIEW_USER.format(script=script_text, audience=audience)
    return await agent._call(p.RETENTION_REVIEW_SYSTEM, user, model=_model(config, "complex_reasoning"))


async def storyboard(agent: YouTubeProductionAgent, config: dict, script_text: str) -> str:
    user = p.STORYBOARD_USER.format(script=script_text)
    return await agent._call(p.STORYBOARD_SYSTEM, user, model=_model(config, "standard"))


async def visual_plan(agent: YouTubeProductionAgent, config: dict, storyboard_text: str) -> str:
    user = p.VISUAL_PLAN_USER.format(storyboard=storyboard_text)
    return await agent._call(p.VISUAL_PLAN_SYSTEM, user, model=_model(config, "standard"))


async def voice_prep(agent: YouTubeProductionAgent, config: dict, script_text: str) -> str:
    user = p.VOICE_PREP_USER.format(script=script_text)
    return await agent._call(p.VOICE_PREP_SYSTEM, user, model=_model(config, "routine"))


async def assembly_plan(agent: YouTubeProductionAgent, config: dict, storyboard_text: str,
                         visual_plan_text: str) -> str:
    user = p.ASSEMBLY_PLAN_USER.format(storyboard=storyboard_text, visual_plan=visual_plan_text)
    return await agent._call(p.ASSEMBLY_PLAN_SYSTEM, user, model=_model(config, "routine"))


async def title_engine(agent: YouTubeProductionAgent, config: dict, topic: str, hook: str,
                        summary: str, audience: str) -> dict:
    user = p.TITLE_ENGINE_USER.format(topic=topic, hook=hook, summary=summary, audience=audience)
    return await agent.call_json(p.TITLE_ENGINE_SYSTEM, user, model=_model(config, "standard"))


async def thumbnail_engine(agent: YouTubeProductionAgent, config: dict, title: str, topic: str,
                            summary: str, audience: str) -> str:
    user = p.AGENCY_THUMBNAIL_USER.format(title=title, topic=topic, summary=summary, audience=audience)
    return await agent._call(p.AGENCY_THUMBNAIL_SYSTEM, user, model=_model(config, "standard"))


async def packaging(agent: YouTubeProductionAgent, config: dict, title: str, topic: str,
                     storyboard_text: str) -> str:
    user = p.PACKAGING_USER.format(title=title, topic=topic, storyboard=storyboard_text)
    return await agent._call(p.PACKAGING_SYSTEM, user, model=_model(config, "routine"))


async def quality_control(agent: YouTubeProductionAgent, config: dict, topic: str, viral_score: int,
                           research_brief_text: str, fact_check_result: dict, script_text: str,
                           retention_notes: str, title: str, thumbnails_text: str) -> dict:
    import json
    user = p.QUALITY_CONTROL_USER.format(
        topic=topic, viral_score=viral_score, research_brief=research_brief_text,
        fact_check=json.dumps(fact_check_result, indent=2), script=script_text,
        retention_notes=retention_notes, title=title, thumbnails=thumbnails_text,
    )
    return await agent.call_json(p.QUALITY_CONTROL_SYSTEM, user, model=_model(config, "final_review"))


async def content_handoff(agent: YouTubeProductionAgent, config: dict, script_text: str, title: str,
                           topic: str, audience: str) -> dict:
    user = p.HANDOFF_USER.format(script=script_text, title=title, topic=topic, audience=audience)
    return await agent.call_json(p.HANDOFF_SYSTEM, user, model=_model(config, "routine"))
