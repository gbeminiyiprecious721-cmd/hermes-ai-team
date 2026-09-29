"""Streamlit dashboard for the YouTube production agent.

Runs the same pipeline as cli.py (ideate / outline / script / metadata /
thumbnails / full agency production) through the Claude Agent SDK, using
your Claude Code subscription - no API key needed.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import streamlit as st

from agent import VideoProject, YouTubeProductionAgent, save_project
from notion_export import NotionNotConfigured, save_project_to_notion
from pipeline.config import load_config
from pipeline.orchestrator import run_pipeline
from pipeline.state import ProjectState, list_projects

PROJECT_ROOT = Path(__file__).parent

STATE_BADGE_COLOR = {
    ProjectState.AWAITING_HUMAN_APPROVAL.value: "orange",
    ProjectState.APPROVED.value: "green",
    ProjectState.PUBLISHED.value: "green",
    ProjectState.REJECTED.value: "red",
    ProjectState.FAILED.value: "red",
}
VERDICT_BADGE_COLOR = {"APPROVE": "green", "REVISE": "orange", "REJECT": "red"}

ARTIFACT_LABELS = {
    "trend_research": ("Trend research", ":material/travel_explore:"),
    "candidate_scoring": ("Candidate scoring", ":material/query_stats:"),
    "research_brief": ("Research brief", ":material/menu_book:"),
    "fact_check": ("Fact check", ":material/fact_check:"),
    "script": ("Script", ":material/description:"),
    "retention_review": ("Retention review", ":material/trending_up:"),
    "storyboard": ("Storyboard", ":material/view_carousel:"),
    "visual_plan": ("Visual plan", ":material/image:"),
    "voice_production": ("Voice production", ":material/graphic_eq:"),
    "assembly_plan": ("Assembly plan", ":material/movie_edit:"),
    "titles": ("Titles", ":material/title:"),
    "thumbnails": ("Thumbnails", ":material/photo_camera:"),
    "packaging": ("Packaging", ":material/inventory_2:"),
    "quality_control": ("Quality control", ":material/verified:"),
    "content_handoff": ("Content handoff", ":material/share:"),
}

st.set_page_config(page_title="YouTube production agent", page_icon="🎬", layout="wide")

st.session_state.setdefault("project", None)
st.session_state.setdefault("ideas_text", None)
st.session_state.setdefault("notion_url", None)
st.session_state.setdefault("agency_project", None)


def get_notion_credentials() -> tuple[str | None, str | None]:
    try:
        notion_secrets = st.secrets.get("notion", {})
    except st.errors.StreamlitSecretNotFoundError:
        notion_secrets = {}
    token = notion_secrets.get("token") or os.environ.get("NOTION_TOKEN")
    parent_page_id = notion_secrets.get("parent_page_id") or os.environ.get("NOTION_PARENT_PAGE_ID")
    return token, parent_page_id


def state_badge(state: str) -> None:
    st.badge(state.replace("_", " ").title(), color=STATE_BADGE_COLOR.get(state, "blue"))


def render_artifact_tabs(artifacts: dict) -> None:
    available = [(key, *ARTIFACT_LABELS[key]) for key in ARTIFACT_LABELS if key in artifacts]
    if not available:
        return
    tabs = st.tabs([label for _, label, _icon in available])
    for (key, label, _icon), tab in zip(available, tabs):
        with tab:
            full_path = PROJECT_ROOT / artifacts[key]
            try:
                content = full_path.read_text(encoding="utf-8")
            except OSError as e:
                st.error(f"Could not read {full_path}: {e}")
                continue
            if full_path.suffix == ".json":
                try:
                    st.json(json.loads(content))
                except json.JSONDecodeError:
                    st.code(content)
            else:
                st.markdown(content)
            st.download_button(
                f"Download {label.lower()}", content, file_name=full_path.name,
                icon=":material/download:", key=f"dl_{key}",
            )


async def run_full_pipeline_with_status(agent: YouTubeProductionAgent, idea: str, audience: str,
                                         duration: int, tone: str, keyword: str,
                                         status) -> VideoProject:
    project = VideoProject(idea=idea, audience=audience, duration_minutes=duration,
                            tone=tone, keyword=keyword)

    status.update(label="Writing outline...")
    project.outline = await agent.outline(idea, audience, duration)

    status.update(label="Writing full script...")
    project.script = await agent.script(project.outline, duration, tone, audience)

    status.update(label="Writing SEO metadata...")
    summary = project.outline[:1500]
    project.metadata = await agent.metadata(idea, summary, audience, keyword)

    status.update(label="Writing thumbnail concepts...")
    project.thumbnails = await agent.thumbnails(idea, summary, audience)

    status.update(label="Done", state="complete")
    return project


st.title("YouTube production agent", icon=":material/smart_display:")
st.caption("A faceless-channel production agency, powered by your Claude Code subscription - no API key needed.")

with st.sidebar:
    st.subheader("Settings", icon=":material/tune:")
    model = st.text_input("Model alias", value="sonnet", key="model_alias")
    cli_path = st.text_input(
        "Claude CLI path (optional)", value="", key="cli_path",
        placeholder="Leave blank to auto-detect",
    )

    st.subheader("Notion export", icon=":material/description:")
    notion_token, notion_parent_id = get_notion_credentials()
    if notion_token and notion_parent_id:
        st.badge("Configured", icon=":material/check_circle:", color="green")
    else:
        st.badge("Not configured", icon=":material/warning:", color="orange")
        with st.expander("Setup instructions", icon=":material/help:"):
            st.markdown(
                "1. Create an internal integration at "
                "[notion.so/my-integrations](https://www.notion.so/my-integrations) "
                "and copy its secret.\n"
                "2. Share a Notion page with that integration (page `...` menu -> "
                "Connections).\n"
                "3. Copy that page's ID from its URL.\n"
                "4. Add both to `.streamlit/secrets.toml`:\n"
                "```toml\n[notion]\ntoken = \"secret_...\"\n"
                "parent_page_id = \"...\"\n```"
            )

mode = st.segmented_control(
    "Mode", ["Ideate", "Full pipeline", "Agency (full production)"], default="Full pipeline", key="mode",
)

if mode == "Ideate":
    with st.container(border=True):
        st.subheader("Generate video ideas", icon=":material/lightbulb:")
        with st.form("ideate_form", border=False):
            niche = st.text_input("Channel niche", placeholder="e.g. personal finance for freelancers")
            audience = st.text_input("Target audience", placeholder="e.g. UK freelancers in their 20s-30s")
            with st.container(horizontal=True):
                count = st.number_input("Number of ideas", min_value=1, max_value=10, value=5)
            context = st.text_area("Additional context (optional)", height=80)
            submitted = st.form_submit_button("Generate ideas", icon=":material/lightbulb:", type="primary")

    if submitted:
        if not niche or not audience:
            st.error("Channel niche and target audience are required.")
        else:
            agent = YouTubeProductionAgent(model=model, cli_path=cli_path or None)
            with st.spinner("Generating video ideas..."):
                try:
                    st.session_state.ideas_text = asyncio.run(
                        agent.ideate(niche, audience, int(count), context)
                    )
                except Exception as e:
                    st.error(f"Generation failed: {e}")
                    st.session_state.ideas_text = None

    if st.session_state.ideas_text:
        with st.container(border=True):
            st.subheader("Ideas", icon=":material/format_list_bulleted:")
            st.markdown(st.session_state.ideas_text)
            st.download_button(
                "Download ideas", st.session_state.ideas_text, file_name="ideas.md",
                icon=":material/download:",
            )

elif mode == "Full pipeline":
    with st.container(border=True):
        st.subheader("Video details", icon=":material/edit_note:")
        with st.form("full_pipeline_form", border=False):
            idea = st.text_input("Video idea / working title", placeholder="e.g. 3 tax mistakes UK freelancers make")
            audience = st.text_input("Target audience", placeholder="e.g. UK freelancers in their 20s-30s")
            with st.container(horizontal=True):
                duration = st.number_input("Target duration (minutes)", min_value=2, max_value=30, value=8)
                keyword = st.text_input("Primary keyword (optional)", placeholder="e.g. self assessment UK")
            tone = st.text_input(
                "Tone", value="conversational, confident, a little informal",
            )
            submitted = st.form_submit_button("Run full pipeline", icon=":material/play_arrow:", type="primary")

    if submitted:
        if not idea or not audience:
            st.error("Video idea and target audience are required.")
        else:
            agent = YouTubeProductionAgent(model=model, cli_path=cli_path or None)
            st.session_state.notion_url = None
            with st.status("Running production pipeline...", expanded=True) as status:
                try:
                    st.session_state.project = asyncio.run(
                        run_full_pipeline_with_status(
                            agent, idea, audience, int(duration), tone, keyword, status,
                        )
                    )
                except Exception as e:
                    status.update(label="Failed", state="error")
                    st.error(f"Generation failed: {e}")
                    st.session_state.project = None

    project = st.session_state.project
    if project:
        with st.container(border=True):
            st.subheader(project.idea, icon=":material/movie:")
            st.caption(f"Audience: {project.audience} · {project.duration_minutes} min · Tone: {project.tone}")

            outline_tab, script_tab, metadata_tab, thumbnails_tab = st.tabs(
                ["Outline", "Script", "Metadata", "Thumbnails"]
            )
            with outline_tab:
                st.markdown(project.outline)
            with script_tab:
                st.markdown(project.script)
            with metadata_tab:
                st.markdown(project.metadata)
            with thumbnails_tab:
                st.markdown(project.thumbnails)

            with st.container(horizontal=True):
                st.download_button(
                    "Download outline", project.outline, file_name="01_outline.md",
                    icon=":material/download:",
                )
                st.download_button(
                    "Download script", project.script, file_name="02_script.md",
                    icon=":material/download:",
                )
                st.download_button(
                    "Download metadata", project.metadata, file_name="03_metadata.md",
                    icon=":material/download:",
                )
                st.download_button(
                    "Download thumbnails", project.thumbnails, file_name="04_thumbnails.md",
                    icon=":material/download:",
                )

            with st.container(horizontal=True):
                if st.button("Save to outputs folder", icon=":material/save:"):
                    out_dir = save_project(project)
                    st.toast(f"Saved to {out_dir}", icon=":material/check_circle:")

                notion_token, notion_parent_id = get_notion_credentials()
                if st.button(
                    "Save to Notion", icon=":material/description:",
                    disabled=not (notion_token and notion_parent_id),
                ):
                    with st.spinner("Creating Notion page..."):
                        try:
                            if notion_token:
                                os.environ["NOTION_TOKEN"] = notion_token
                            if notion_parent_id:
                                os.environ["NOTION_PARENT_PAGE_ID"] = notion_parent_id
                            st.session_state.notion_url = save_project_to_notion(project)
                        except NotionNotConfigured as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"Notion save failed: {e}")

            if st.session_state.notion_url:
                st.success(f"Saved to Notion: {st.session_state.notion_url}")

else:  # Agency (full production)
    cfg = load_config()
    st.caption(
        "Trend discovery -> outlier analysis -> viral scoring -> selection gate -> research -> "
        "fact-check -> scripting -> retention review -> storyboard -> visual/voice/assembly plans -> "
        "titles -> thumbnails -> packaging -> quality control -> awaiting your approval. "
        "Nothing is ever published or scheduled automatically."
    )

    with st.container(border=True):
        st.subheader("New production run", icon=":material/precision_manufacturing:")
        with st.expander("Configuration (pipeline_config.json)", icon=":material/settings:"):
            st.json(cfg)

        with st.form("agency_form", border=False):
            niche = st.text_input("Niche (blank = use config default)", value=", ".join(cfg["niche"]))
            audience = st.text_input("Audience (blank = use config default)", value=cfg["default_audience"])
            with st.container(horizontal=True):
                duration = st.number_input(
                    "Target duration (minutes)", min_value=3, max_value=30,
                    value=cfg["default_duration_minutes"],
                )
                candidates = st.number_input("Candidate topics to score", min_value=1, max_value=8, value=3)
            tone = st.text_input("Tone", value="conversational, confident, a little informal", key="agency_tone")
            context = st.text_area("Extra context to steer trend research (optional)", height=80)
            force_below_threshold = st.checkbox(
                "Manually approve production even if the best candidate scores below the reject threshold",
                value=False, key="agency_force",
            )
            submitted = st.form_submit_button(
                "Run full agency pipeline", icon=":material/rocket_launch:", type="primary",
            )

    if submitted:
        with st.status("Running production agency pipeline...", expanded=True) as status:
            def on_progress(stage: str, message: str) -> None:
                status.update(label=f"[{stage}] {message}")

            async def _run():
                return await run_pipeline(
                    niche=niche or None, audience=audience or None, duration_minutes=int(duration),
                    tone=tone, extra_context=context, candidate_count=int(candidates),
                    model=model, cli_path=cli_path or None, force_below_threshold=force_below_threshold,
                    on_progress=on_progress,
                )

            try:
                st.session_state.agency_project = asyncio.run(_run())
                final_state = st.session_state.agency_project.state
                if final_state == ProjectState.AWAITING_HUMAN_APPROVAL.value:
                    status.update(label="Awaiting your approval", state="complete")
                elif final_state in (ProjectState.REJECTED.value, ProjectState.FAILED.value):
                    status.update(label=f"Stopped: {final_state}", state="error")
                else:
                    status.update(label=f"Stopped at {final_state}", state="complete")
            except Exception as e:
                status.update(label="Failed", state="error")
                st.error(f"Pipeline failed: {e}")
                st.session_state.agency_project = None

    project = st.session_state.agency_project
    if project:
        with st.container(border=True):
            with st.container(horizontal=True, horizontal_alignment="left", vertical_alignment="center"):
                st.subheader(project.topic, icon=":material/movie:")
                state_badge(project.state)

            with st.container(horizontal=True):
                st.metric(
                    "Viral score", f"{project.viral_score}/100" if project.viral_score is not None else "-",
                    border=True,
                )
                with st.container(border=True):
                    st.caption("QC verdict")
                    if project.qc_verdict:
                        st.badge(project.qc_verdict, color=VERDICT_BADGE_COLOR.get(project.qc_verdict, "gray"))
                    else:
                        st.write("-")
                st.metric("QC attempts", project.qc_attempts, border=True)
                st.metric("Duration target", f"{project.video_length_minutes} min", border=True)

            if project.state == ProjectState.REJECTED.value:
                st.warning(
                    f"Best candidate topic was rejected by the selection gate "
                    f"(score {project.viral_score}). No production stages ran beyond scoring.",
                    icon=":material/block:",
                )
            if project.state == ProjectState.FAILED.value:
                st.error(f"Pipeline failed: {project.failure_reason}", icon=":material/error:")
            if project.state == ProjectState.AWAITING_HUMAN_APPROVAL.value:
                st.success(
                    "Awaiting your explicit approval - nothing has been published, "
                    "scheduled, or posted anywhere.", icon=":material/pause_circle:",
                )

            if project.title:
                st.markdown(f"**Recommended title:** {project.title}")
            if project.chosen_angle:
                st.caption(f"Angle: {project.chosen_angle}")

            if project.limitations:
                with st.expander(f"Limitations ({len(project.limitations)})", icon=":material/info:"):
                    for lim in dict.fromkeys(project.limitations):
                        st.write(f"- {lim}")

        if project.artifacts:
            with st.container(border=True):
                st.subheader("Production artifacts", icon=":material/folder_open:")
                render_artifact_tabs(project.artifacts)

    with st.container(border=True):
        st.subheader("Content memory", icon=":material/history:")
        st.caption("Past agency projects, used to avoid repeating topics, hooks, and titles.")
        past = list_projects()
        if past:
            st.dataframe(
                past, width="stretch", hide_index=True,
                column_config={
                    "slug": None,
                    "topic": st.column_config.TextColumn("Topic", width="large"),
                    "title": st.column_config.TextColumn("Title", width="large"),
                    "hook": None,
                    "state": st.column_config.TextColumn("State"),
                    "viral_score": st.column_config.NumberColumn("Score", format="%d/100"),
                    "created_at": st.column_config.DatetimeColumn("Created"),
                    "lessons_learned": None,
                },
            )
        else:
            st.caption("No past projects yet.")
