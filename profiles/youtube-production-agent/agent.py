"""Core YouTube production agent: drives Claude through each stage of turning
a channel niche into a fully scripted, SEO-tagged, thumbnail-briefed video.

Uses the Claude Agent SDK, which talks to the locally installed and
authenticated Claude Code CLI - so it runs against the user's Claude
subscription rather than requiring a separate ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

import prompts

# The Claude CLI prefers ANTHROPIC_API_KEY over subscription login when both are
# present. This agent is meant to run on the subscription, so strip any stray
# key from our own process before the SDK spawns the CLI subprocess - it would
# otherwise inherit a leftover/placeholder key from the parent environment.
os.environ.pop("ANTHROPIC_API_KEY", None)

DEFAULT_MODEL = "sonnet"
OUTPUT_ROOT = Path(__file__).parent / "outputs"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60] or "untitled"


@dataclass
class VideoProject:
    idea: str = ""
    audience: str = ""
    duration_minutes: int = 10
    tone: str = "conversational, confident, a little informal"
    keyword: str = ""
    ideas: str = ""
    outline: str = ""
    script: str = ""
    metadata: str = ""
    thumbnails: str = ""
    history: list = field(default_factory=list)


class YouTubeProductionAgent:
    def __init__(self, model: str = DEFAULT_MODEL, cli_path: str | None = None):
        self.model = model
        self.cli_path = cli_path or os.environ.get("CLAUDE_CODE_CLI_PATH")

    async def _call(self, system: str, user: str, *, model: str | None = None,
                     allowed_tools: list[str] | None = None, max_turns: int = 20,
                     permission_mode: str | None = None,
                     on_tool_use=None) -> str:
        """Low-level call to the Claude Code subprocess.

        Pure single-response text completion (no tools) by default. A small
        max_turns headroom (3, not 1) absorbs occasional multi-turn responses
        (e.g. long structured output) without changing behavior for calls
        that finish in one turn anyway - unused turns simply go unused.
        Passing allowed_tools enables genuine tool use (e.g. WebSearch) for stages
        that need real, current information rather than model knowledge.
        """
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=model or self.model,
            max_turns=max_turns,
            allowed_tools=allowed_tools if allowed_tools is not None else [],
        )
        if permission_mode:
            options.permission_mode = permission_mode
        if self.cli_path:
            options.cli_path = self.cli_path

        chunks: list[str] = []
        error: str | None = None
        async for message in query(prompt=user, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
                    elif isinstance(block, ToolUseBlock) and on_tool_use:
                        on_tool_use(block.name, block.input)
            elif isinstance(message, ResultMessage):
                if getattr(message, "is_error", False):
                    error = getattr(message, "result", None) or str(message)
        if error:
            raise RuntimeError(f"Claude Code query failed: {error}")
        return "".join(chunks).strip()

    async def call_with_search(self, system: str, user: str, *, model: str | None = None,
                                max_turns: int = 12, on_tool_use=None) -> str:
        """Call with WebSearch/WebFetch enabled, for stages that need real,
        current information instead of relying on model knowledge alone.
        Runs through the same subscription-authenticated CLI subprocess -
        no separate search API or key involved."""
        return await self._call(
            system, user, model=model, allowed_tools=["WebSearch", "WebFetch"],
            max_turns=max_turns, permission_mode="bypassPermissions",
            on_tool_use=on_tool_use,
        )

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        return json.loads(text)

    async def call_json(self, system: str, user: str, *, model: str | None = None,
                         allowed_tools: list[str] | None = None, max_turns: int = 20) -> dict:
        """Call expecting a strict JSON object back. Retries once with the
        parse error fed back to the model if the first attempt isn't valid
        JSON (smaller/faster models sometimes wrap JSON in prose or fences)."""
        json_system = system + "\n\nRespond with ONLY a single valid JSON object. No markdown fences, no prose before or after."
        raw = await self._call(json_system, user, model=model, allowed_tools=allowed_tools, max_turns=max_turns)
        try:
            return self._extract_json(raw)
        except (json.JSONDecodeError, AttributeError) as e:
            retry_user = (
                f"{user}\n\n---\nYour previous response could not be parsed as JSON "
                f"(error: {e}). Here is what you returned:\n{raw}\n\n"
                "Return ONLY a corrected, valid JSON object matching the requested shape."
            )
            raw2 = await self._call(json_system, retry_user, model=model, allowed_tools=allowed_tools, max_turns=max_turns)
            return self._extract_json(raw2)

    async def ideate(self, niche: str, audience: str, count: int = 5, extra_context: str = "") -> str:
        user = prompts.IDEATE_USER_TEMPLATE.format(
            niche=niche, audience=audience, count=count,
            extra_context=f"Additional context: {extra_context}" if extra_context else "",
        )
        return await self._call(prompts.IDEATE_SYSTEM, user)

    async def outline(self, idea: str, audience: str, duration_minutes: int = 10, extra_context: str = "") -> str:
        user = prompts.OUTLINE_USER_TEMPLATE.format(
            idea=idea, duration=duration_minutes, audience=audience,
            extra_context=f"Additional context: {extra_context}" if extra_context else "",
        )
        return await self._call(prompts.OUTLINE_SYSTEM, user)

    async def script(self, outline: str, duration_minutes: int = 10, tone: str = "conversational",
                      audience: str = "general") -> str:
        word_count = duration_minutes * 150
        user = prompts.SCRIPT_USER_TEMPLATE.format(
            outline=outline, duration=duration_minutes, word_count=word_count,
            tone=tone, audience=audience,
        )
        return await self._call(prompts.SCRIPT_SYSTEM, user)

    async def metadata(self, idea: str, content_summary: str, audience: str, keyword: str = "") -> str:
        user = prompts.METADATA_USER_TEMPLATE.format(
            idea=idea, content_summary=content_summary, audience=audience,
            keyword=keyword or "(none specified, infer from content)",
        )
        return await self._call(prompts.METADATA_SYSTEM, user)

    async def thumbnails(self, idea: str, content_summary: str, audience: str) -> str:
        user = prompts.THUMBNAIL_USER_TEMPLATE.format(
            idea=idea, content_summary=content_summary, audience=audience,
        )
        return await self._call(prompts.THUMBNAIL_SYSTEM, user)

    async def run_full_pipeline(self, idea: str, audience: str, duration_minutes: int = 10,
                                 tone: str = "conversational, confident, a little informal",
                                 keyword: str = "") -> VideoProject:
        project = VideoProject(
            idea=idea, audience=audience, duration_minutes=duration_minutes,
            tone=tone, keyword=keyword,
        )
        project.outline = await self.outline(idea, audience, duration_minutes)
        project.script = await self.script(project.outline, duration_minutes, tone, audience)
        summary = project.outline[:1500]
        project.metadata = await self.metadata(idea, summary, audience, keyword)
        project.thumbnails = await self.thumbnails(idea, summary, audience)
        return project


def save_project(project: VideoProject) -> Path:
    slug = slugify(project.idea)
    out_dir = OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    if project.outline:
        (out_dir / "01_outline.md").write_text(project.outline, encoding="utf-8")
    if project.script:
        (out_dir / "02_script.md").write_text(project.script, encoding="utf-8")
    if project.metadata:
        (out_dir / "03_metadata.md").write_text(project.metadata, encoding="utf-8")
    if project.thumbnails:
        (out_dir / "04_thumbnails.md").write_text(project.thumbnails, encoding="utf-8")

    summary_lines = [
        f"# {project.idea}",
        "",
        f"- Audience: {project.audience}",
        f"- Target duration: {project.duration_minutes} min",
        f"- Tone: {project.tone}",
        f"- Keyword focus: {project.keyword or '(none)'}",
        "",
        "Files: 01_outline.md, 02_script.md, 03_metadata.md, 04_thumbnails.md",
    ]
    (out_dir / "00_project.md").write_text("\n".join(summary_lines), encoding="utf-8")
    return out_dir
