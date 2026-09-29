"""Full production-agency orchestrator: sequences every stage, persists job
state after each step, enforces the idea-selection gate and the QC retry
limit, and never advances past AWAITING_HUMAN_APPROVAL on its own.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from agent import YouTubeProductionAgent, slugify
from pipeline import stages
from pipeline.config import load_config
from pipeline.state import ProjectRecord, ProjectState, list_projects

OUTPUT_ROOT = Path(__file__).parent.parent / "outputs"

ProgressCB = Callable[[str, str], None]  # (stage_name, message)


def _noop(_stage: str, _msg: str) -> None:
    pass


def _save_artifact(slug: str, filename: str, content: str) -> Path:
    out_dir = OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def _extract_revised_script(retention_output: str, fallback: str) -> str:
    marker = "## REVISED SCRIPT"
    idx = retention_output.find(marker)
    if idx == -1:
        return fallback
    return retention_output[idx + len(marker):].strip()


def _extract_retention_issues(retention_output: str) -> str:
    """The issues-found half only - never the embedded revised-script copy,
    which would otherwise reach QC as a second, possibly-diverging script
    alongside the actual final script (QC caught exactly this ambiguity)."""
    marker = "## REVISED SCRIPT"
    idx = retention_output.find(marker)
    return retention_output[:idx].strip() if idx != -1 else retention_output


async def generate_candidates(agent: YouTubeProductionAgent, config: dict, trend_text: str,
                               count: int = 5) -> list[dict]:
    system = "Extract discrete YouTube video topic candidates from research notes into JSON."
    user = (
        f"Research notes:\n{trend_text}\n\n"
        f"Extract up to {count} concrete, distinct video topic candidates mentioned in the "
        "notes above. Return JSON: {\"candidates\": [{\"topic\": \"...\", \"rationale\": \"...\"}]}. "
        "Use only topics actually present in the notes - do not invent new ones."
    )
    result = await agent.call_json(system, user, model=config["models"]["routine"])
    return result.get("candidates", [])[:count]


async def run_pipeline(niche: str | None = None, audience: str | None = None,
                        duration_minutes: int | None = None,
                        tone: str = "conversational, confident, a little informal",
                        extra_context: str = "", candidate_count: int = 5,
                        model: str | None = None, cli_path: str | None = None,
                        force_below_threshold: bool = False,
                        on_progress: ProgressCB = _noop) -> ProjectRecord:
    """Runs trend discovery through quality control / human-approval gate for
    one video. Returns the persisted ProjectRecord. Never publishes anything.

    force_below_threshold: the spec for the selection gate is "REJECT unless
    manually approved" - this is that manual approval, for a human who has
    reviewed a below-threshold candidate and wants to proceed anyway. It does
    not change the score or hide that the gate was overridden."""
    config = load_config()
    niche = niche or ", ".join(config["niche"])
    audience = audience or config["default_audience"]
    duration_minutes = duration_minutes or config["default_duration_minutes"]

    agent = YouTubeProductionAgent(model=model or "sonnet", cli_path=cli_path)
    past = list_projects()
    past_topics = [p["topic"] for p in past if p.get("topic")]

    # --- Stage: trend discovery ------------------------------------------------
    on_progress("TREND_RESEARCH", "Searching the web for real, current opportunities...")
    trend_text = await stages.trend_research(agent, config, niche, audience, extra_context)

    placeholder = ProjectRecord.create(slug="pending", topic="(selecting)", niche=niche, audience=audience,
                                        video_length_minutes=duration_minutes)
    placeholder.advance(ProjectState.RESEARCHING, "Trend research complete")
    placeholder.limitations.append(
        "Trend research uses Claude's WebSearch tool, not a formal Google Trends/YouTube "
        "Data API - real and current, but not authoritative platform analytics."
    )

    if trend_text.startswith("UNAVAILABLE"):
        placeholder.slug = slugify("trend-research-unavailable")
        placeholder.fail(trend_text)
        placeholder.save()
        on_progress("FAILED", "Trend research (live web search) was unavailable - stopping honestly rather than inventing topics.")
        return placeholder

    on_progress("CANDIDATES", "Extracting discrete topic candidates...")
    candidates = await generate_candidates(agent, config, trend_text, candidate_count)
    if not candidates:
        placeholder.slug = slugify("no-viable-topic-found")
        placeholder.fail("Trend research completed but no extractable candidate topics were found in it.")
        placeholder.save()
        return placeholder

    # --- Stage: competitor outlier analysis + viral scoring per candidate -------
    scored: list[dict] = []
    for cand in candidates:
        topic = cand.get("topic", "").strip()
        if not topic:
            continue
        on_progress("OUTLIER_ANALYSIS", f"Checking competitor outliers for: {topic}")
        outlier_text = await stages.outlier_analysis(agent, config, niche, topic)
        on_progress("VIRAL_SCORE", f"Scoring: {topic}")
        score_result = await stages.score_topic(
            agent, config, topic, niche, audience, trend_text, outlier_text, past_topics,
        )
        scored.append({
            "topic": topic, "rationale": cand.get("rationale", ""),
            "outlier_text": outlier_text, "score_result": score_result,
        })

    if not scored:
        placeholder.slug = slugify("no-viable-topic-found")
        placeholder.fail("No candidate topics could be scored.")
        placeholder.save()
        return placeholder

    scored.sort(key=lambda s: s["score_result"]["score"], reverse=True)
    winner = scored[0]
    winner_score = winner["score_result"]["score"]
    gate = stages.gate_decision(winner_score, config)

    slug = slugify(winner["topic"])
    project = ProjectRecord.create(
        slug=slug, topic=winner["topic"], niche=niche, audience=audience,
        video_length_minutes=duration_minutes,
    )
    project.chosen_angle = winner["rationale"]
    project.viral_score = winner_score
    project.score_breakdown = winner["score_result"].get("score_breakdown", {})
    project.limitations = list(placeholder.limitations)
    project.advance(ProjectState.SCORED, f"Top candidate scored {winner_score}/100 ({gate})")

    _save_artifact(slug, "00_trend_research.md", trend_text)
    _save_artifact(slug, "01_candidate_scoring.json", json.dumps(
        [{"topic": s["topic"], "score": s["score_result"]["score"],
          "breakdown": s["score_result"].get("score_breakdown", {}),
          "evidence": s["score_result"].get("evidence", []),
          "risks": s["score_result"].get("risks", [])} for s in scored], indent=2,
    ))
    project.record_artifact("trend_research", OUTPUT_ROOT / slug / "00_trend_research.md")
    project.record_artifact("candidate_scoring", OUTPUT_ROOT / slug / "01_candidate_scoring.json")

    if gate == "REJECT" and not force_below_threshold:
        project.advance(ProjectState.REJECTED, f"Best candidate scored {winner_score}, below reject threshold")
        project.save()
        on_progress("REJECTED", f"Best candidate only scored {winner_score}/100 - stopping per selection gate")
        return project

    if gate == "REJECT" and force_below_threshold:
        project.limitations.append(
            f"Selection gate was manually overridden: best candidate scored {winner_score}/100, "
            f"below the reject threshold ({config['thresholds']['improve_angle']}). Proceeding "
            "into production was a human decision, not the gate's recommendation."
        )
        on_progress("OVERRIDE", f"Score {winner_score}/100 is below threshold - proceeding anyway (manually approved)")

    project.advance(ProjectState.SELECTED, f"Selected (gate={gate}{', manually overridden' if gate == 'REJECT' else ''})")
    project.save()

    # --- Stage: deep research + fact-check --------------------------------------
    on_progress("RESEARCH", "Building the research brief...")
    research_text = await stages.research_brief(agent, config, project.topic, project.chosen_angle, audience)
    if research_text.startswith("UNAVAILABLE"):
        project.limitations.append(
            "Live research was unavailable for this topic - the script below is written "
            "from general model knowledge only, not verified current sources. Treat "
            "specific facts/figures in it with caution until manually checked."
        )
    _save_artifact(slug, "02_research_brief.md", research_text)
    project.record_artifact("research_brief", OUTPUT_ROOT / slug / "02_research_brief.md")
    project.advance(ProjectState.RESEARCHING, "Research brief complete")
    project.save()

    on_progress("SCRIPTING", "Writing the first script draft...")
    script_text = await stages.write_script(
        agent, config, project.topic, project.chosen_angle, hook="", duration_minutes=duration_minutes,
        audience=audience, tone=tone, research_brief_text=research_text,
    )
    project.advance(ProjectState.SCRIPTING, "First draft complete")

    on_progress("FACT_CHECK", "Fact-checking the script against the research brief...")
    fact_check_result = await stages.fact_check(agent, config, research_text, script_text)
    fact_notes = "\n".join(
        f"- [{c.get('verdict')}] {c.get('claim')}: {c.get('note')}" for c in fact_check_result.get("claims", [])
        if c.get("verdict") in ("QUALIFIED", "REMOVE")
    )
    if fact_notes:
        on_progress("SCRIPTING", "Rewriting to correct flagged claims...")
        script_text = await stages.write_script(
            agent, config, project.topic, project.chosen_angle, hook="", duration_minutes=duration_minutes,
            audience=audience, tone=tone, research_brief_text=research_text, fact_check_notes=fact_notes,
        )
    _save_artifact(slug, "03_fact_check.json", json.dumps(fact_check_result, indent=2))
    project.record_artifact("fact_check", OUTPUT_ROOT / slug / "03_fact_check.json")
    project.advance(ProjectState.FACT_CHECK, f"Fact-check risk: {fact_check_result.get('overall_risk', 'UNKNOWN')}")
    project.save()

    # --- Stage: retention review -------------------------------------------------
    on_progress("RETENTION_REVIEW", "Reviewing for retention and revising...")
    retention_output = await stages.retention_review(agent, config, script_text, audience)
    final_script = _extract_revised_script(retention_output, fallback=script_text)
    _save_artifact(slug, "04_script_final.md", final_script)
    _save_artifact(slug, "04b_retention_review.md", retention_output)
    project.record_artifact("script", OUTPUT_ROOT / slug / "04_script_final.md")
    project.record_artifact("retention_review", OUTPUT_ROOT / slug / "04b_retention_review.md")
    project.hook = final_script.strip().split("\n\n")[0][:300]
    project.advance(ProjectState.RETENTION_REVIEW, "Retention pass complete")
    project.save()

    # --- Stage: storyboard, visuals, voice, assembly -----------------------------
    on_progress("STORYBOARD", "Building the scene-by-scene storyboard...")
    storyboard_text = await stages.storyboard(agent, config, final_script)
    _save_artifact(slug, "05_storyboard.md", storyboard_text)
    project.record_artifact("storyboard", OUTPUT_ROOT / slug / "05_storyboard.md")
    project.advance(ProjectState.STORYBOARD, "Storyboard complete")
    project.save()

    on_progress("VISUAL_PLAN", "Planning visual treatment per scene...")
    visual_plan_text = await stages.visual_plan(agent, config, storyboard_text)
    _save_artifact(slug, "06_visual_plan.md", visual_plan_text)
    project.record_artifact("visual_plan", OUTPUT_ROOT / slug / "06_visual_plan.md")
    project.limitations.append("No image/video generation tool is connected - visual plan is prompts/specs only, no assets rendered.")
    project.advance(ProjectState.VISUAL_PRODUCTION, "Visual plan complete (no assets rendered - see limitations)")
    project.save()

    on_progress("VOICE_PREP", "Preparing narration for text-to-speech...")
    voice_text = await stages.voice_prep(agent, config, final_script)
    _save_artifact(slug, "07_voice_production.md", voice_text)
    project.record_artifact("voice_production", OUTPUT_ROOT / slug / "07_voice_production.md")
    project.limitations.append("No TTS engine is connected - narration script prepared, no audio file generated.")
    project.advance(ProjectState.VOICE, "Narration script complete (no audio rendered - see limitations)")
    project.save()

    on_progress("ASSEMBLY", "Producing the assembly package...")
    assembly_text = await stages.assembly_plan(agent, config, storyboard_text, visual_plan_text)
    _save_artifact(slug, "08_assembly_plan.md", assembly_text)
    project.record_artifact("assembly_plan", OUTPUT_ROOT / slug / "08_assembly_plan.md")
    project.limitations.append("No video renderer is connected - assembly plan produced, no video file rendered.")
    project.advance(ProjectState.ASSEMBLY, "Assembly plan complete (no video rendered - see limitations)")
    project.save()

    # --- Stage: packaging ----------------------------------------------------------
    on_progress("TITLES", "Generating and scoring title candidates...")
    summary_for_titles = research_text[:1200]
    titles_result = await stages.title_engine(agent, config, project.topic, project.hook, summary_for_titles, audience)
    recommended_title = titles_result.get("recommended") or (titles_result.get("titles") or [{}])[0].get("title", project.topic)
    project.title = recommended_title
    _save_artifact(slug, "09_titles.json", json.dumps(titles_result, indent=2))
    project.record_artifact("titles", OUTPUT_ROOT / slug / "09_titles.json")

    on_progress("THUMBNAILS", "Designing thumbnail concepts...")
    thumbnails_text = await stages.thumbnail_engine(agent, config, recommended_title, project.topic, summary_for_titles, audience)
    _save_artifact(slug, "10_thumbnails.md", thumbnails_text)
    project.record_artifact("thumbnails", OUTPUT_ROOT / slug / "10_thumbnails.md")
    project.limitations.append("No image generation tool is connected - thumbnail concepts are production-ready specs, no image files created.")

    on_progress("PACKAGING", "Assembling description, chapters, tags, CTA...")
    packaging_text = await stages.packaging(agent, config, recommended_title, project.topic, storyboard_text)
    _save_artifact(slug, "11_packaging.md", packaging_text)
    project.record_artifact("packaging", OUTPUT_ROOT / slug / "11_packaging.md")
    project.advance(ProjectState.QUALITY_REVIEW, "Packaging complete, entering quality control")
    project.save()

    # --- Stage: quality control (with bounded retry loop) ---------------------------
    max_retries = config["qc_max_retries"]
    retention_issues = _extract_retention_issues(retention_output)
    verdict = "REVISE"
    qc_result: dict = {}
    while project.qc_attempts <= max_retries:
        on_progress("QUALITY_CONTROL", f"Running quality control (attempt {project.qc_attempts + 1})...")
        qc_result = await stages.quality_control(
            agent, config, project.topic, project.viral_score, research_text, fact_check_result,
            final_script, retention_issues, recommended_title, thumbnails_text,
        )
        verdict = qc_result.get("verdict", "REVISE")
        project.qc_attempts += 1
        if verdict == "APPROVE":
            break
        if verdict == "REJECT":
            break
        if project.qc_attempts > max_retries:
            break
        # REVISE: apply required changes with one more script pass, then redo retention pass only
        on_progress("QUALITY_CONTROL", "Revising script per QC feedback...")
        changes = "\n".join(f"- {c}" for c in qc_result.get("required_changes", []))
        final_script = await stages.write_script(
            agent, config, project.topic, project.chosen_angle, hook=project.hook,
            duration_minutes=duration_minutes, audience=audience, tone=tone,
            research_brief_text=research_text, fact_check_notes=fact_notes + "\n" + changes,
        )
        _save_artifact(slug, f"04_script_final.md", final_script)

    project.qc_verdict = verdict
    _save_artifact(slug, "12_quality_control.json", json.dumps(qc_result, indent=2))
    project.record_artifact("quality_control", OUTPUT_ROOT / slug / "12_quality_control.json")

    if verdict == "REJECT":
        project.fail(f"Quality control rejected the package: {qc_result.get('required_changes')}")
        project.save()
        return project

    if verdict == "REVISE":
        project.advance(ProjectState.QUALITY_REVIEW, f"Still REVISE after {max_retries} retries - stopping for human review")
        project.limitations.append(f"QC retry limit ({max_retries}) reached while still flagged REVISE - needs human editing.")
        project.save()
        return project

    # --- Stage: content handoff summary (no external agent contacted) ----------------
    on_progress("HANDOFF", "Preparing the repurposing handoff document...")
    handoff = await stages.content_handoff(agent, config, final_script, recommended_title, project.topic, audience)
    _save_artifact(slug, "13_content_handoff.json", json.dumps(handoff, indent=2))
    project.record_artifact("content_handoff", OUTPUT_ROOT / slug / "13_content_handoff.json")

    project.limitations.append("Performance learning is waiting for real data - no YouTube Analytics connection exists yet.")
    project.advance(ProjectState.AWAITING_HUMAN_APPROVAL, "Package approved by QC - awaiting your explicit approval before any publishing")
    project.save()
    on_progress("DONE", f"Package ready for human approval: {recommended_title}")
    return project
