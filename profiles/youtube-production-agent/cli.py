"""CLI for the YouTube production agent.

Runs on your Claude Code subscription (via the Claude Agent SDK) - no
separate API key needed, as long as the `claude` CLI is installed and
logged in on this machine.

Examples:
    py cli.py ideate --niche "personal finance for freelancers" --audience "UK freelancers in their 20s-30s"
    py cli.py outline --idea "3 tax mistakes freelancers make" --audience "UK freelancers" --duration 8
    py cli.py full --idea "3 tax mistakes freelancers make" --audience "UK freelancers" --duration 8
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agent import OUTPUT_ROOT, YouTubeProductionAgent, save_project, slugify
from pipeline.orchestrator import run_pipeline
from pipeline.state import ProjectState


async def cmd_ideate(agent: YouTubeProductionAgent, args):
    result = await agent.ideate(args.niche, args.audience, args.count, args.context or "")
    print(result)
    if args.save:
        out_dir = OUTPUT_ROOT / slugify(args.niche)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ideas.md").write_text(result, encoding="utf-8")
        print(f"\nSaved to {out_dir / 'ideas.md'}")


async def cmd_outline(agent: YouTubeProductionAgent, args):
    result = await agent.outline(args.idea, args.audience, args.duration, args.context or "")
    print(result)
    if args.save:
        out_dir = OUTPUT_ROOT / slugify(args.idea)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "01_outline.md").write_text(result, encoding="utf-8")
        print(f"\nSaved to {out_dir / '01_outline.md'}")


async def cmd_script(agent: YouTubeProductionAgent, args):
    outline_text = args.outline
    if args.outline_file:
        outline_text = Path(args.outline_file).read_text(encoding="utf-8")
    result = await agent.script(outline_text, args.duration, args.tone, args.audience)
    print(result)
    if args.save and args.idea:
        out_dir = OUTPUT_ROOT / slugify(args.idea)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "02_script.md").write_text(result, encoding="utf-8")
        print(f"\nSaved to {out_dir / '02_script.md'}")


async def cmd_metadata(agent: YouTubeProductionAgent, args):
    content_summary = args.summary
    if args.summary_file:
        content_summary = Path(args.summary_file).read_text(encoding="utf-8")
    result = await agent.metadata(args.idea, content_summary, args.audience, args.keyword or "")
    print(result)
    if args.save:
        out_dir = OUTPUT_ROOT / slugify(args.idea)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "03_metadata.md").write_text(result, encoding="utf-8")
        print(f"\nSaved to {out_dir / '03_metadata.md'}")


async def cmd_thumbnails(agent: YouTubeProductionAgent, args):
    content_summary = args.summary
    if args.summary_file:
        content_summary = Path(args.summary_file).read_text(encoding="utf-8")
    result = await agent.thumbnails(args.idea, content_summary, args.audience)
    print(result)
    if args.save:
        out_dir = OUTPUT_ROOT / slugify(args.idea)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "04_thumbnails.md").write_text(result, encoding="utf-8")
        print(f"\nSaved to {out_dir / '04_thumbnails.md'}")


async def cmd_full(agent: YouTubeProductionAgent, args):
    print(f"Running full pipeline for: {args.idea}\n")
    print("-> Generating outline...")
    project = await agent.run_full_pipeline(
        idea=args.idea, audience=args.audience, duration_minutes=args.duration,
        tone=args.tone, keyword=args.keyword or "",
    )
    out_dir = save_project(project)
    print(f"\nDone. Project saved to: {out_dir}\n")
    print("=" * 60)
    print("OUTLINE")
    print("=" * 60)
    print(project.outline)
    print("\n" + "=" * 60)
    print("SCRIPT")
    print("=" * 60)
    print(project.script)
    print("\n" + "=" * 60)
    print("METADATA")
    print("=" * 60)
    print(project.metadata)
    print("\n" + "=" * 60)
    print("THUMBNAILS")
    print("=" * 60)
    print(project.thumbnails)


async def cmd_agency(_agent: YouTubeProductionAgent, args):
    """Full production-agency pipeline: trend discovery through quality
    control, stopping at AWAITING_HUMAN_APPROVAL. Never publishes anything."""
    def on_progress(stage: str, message: str) -> None:
        print(f"[{stage}] {message}")

    project = await run_pipeline(
        niche=args.niche, audience=args.audience, duration_minutes=args.duration,
        tone=args.tone, extra_context=args.context or "", candidate_count=args.candidates,
        model=args.model, cli_path=args.cli_path, force_below_threshold=args.force,
        on_progress=on_progress,
    )

    print("\n" + "=" * 60)
    print(f"FINAL STATE: {project.state}")
    print("=" * 60)
    print(f"Topic: {project.topic}")
    print(f"Viral score: {project.viral_score}")
    print(f"Title: {project.title}")
    print(f"QC verdict: {project.qc_verdict}")
    if project.failure_reason:
        print(f"Failure reason: {project.failure_reason}")
    print(f"\nArtifacts saved under: {OUTPUT_ROOT / project.slug}")
    print(f"Project state file: projects/{project.slug}.json")
    if project.limitations:
        print("\nLimitations:")
        for lim in project.limitations:
            print(f"  - {lim}")
    if project.state == ProjectState.AWAITING_HUMAN_APPROVAL.value:
        print("\n>>> AWAITING_HUMAN_APPROVAL - nothing has been published or scheduled. <<<")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube production agent")
    parser.add_argument("--model", default=None, help="Override the Claude model alias (default: sonnet)")
    parser.add_argument("--cli-path", default=None, help="Path to the claude CLI executable, if not on PATH")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ideate", help="Generate video ideas for a niche")
    p.add_argument("--niche", required=True)
    p.add_argument("--audience", required=True)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--context", default="")
    p.add_argument("--save", action="store_true")
    p.set_defaults(func=cmd_ideate)

    p = sub.add_parser("outline", help="Generate a retention-focused outline")
    p.add_argument("--idea", required=True)
    p.add_argument("--audience", required=True)
    p.add_argument("--duration", type=int, default=10)
    p.add_argument("--context", default="")
    p.add_argument("--save", action="store_true")
    p.set_defaults(func=cmd_outline)

    p = sub.add_parser("script", help="Write a full narration script from an outline")
    p.add_argument("--idea", help="Used only for --save file naming")
    p.add_argument("--outline", default="", help="Outline text inline")
    p.add_argument("--outline-file", default=None, help="Path to a file containing the outline")
    p.add_argument("--audience", required=True)
    p.add_argument("--duration", type=int, default=10)
    p.add_argument("--tone", default="conversational, confident, a little informal")
    p.add_argument("--save", action="store_true")
    p.set_defaults(func=cmd_script)

    p = sub.add_parser("metadata", help="Generate titles, description, tags, hashtags")
    p.add_argument("--idea", required=True)
    p.add_argument("--summary", default="", help="Content summary inline")
    p.add_argument("--summary-file", default=None, help="Path to a file with outline/script to summarize")
    p.add_argument("--audience", required=True)
    p.add_argument("--keyword", default="")
    p.add_argument("--save", action="store_true")
    p.set_defaults(func=cmd_metadata)

    p = sub.add_parser("thumbnails", help="Generate thumbnail concepts")
    p.add_argument("--idea", required=True)
    p.add_argument("--summary", default="")
    p.add_argument("--summary-file", default=None)
    p.add_argument("--audience", required=True)
    p.add_argument("--save", action="store_true")
    p.set_defaults(func=cmd_thumbnails)

    p = sub.add_parser("full", help="Run the entire pipeline end to end and save all files")
    p.add_argument("--idea", required=True)
    p.add_argument("--audience", required=True)
    p.add_argument("--duration", type=int, default=10)
    p.add_argument("--tone", default="conversational, confident, a little informal")
    p.add_argument("--keyword", default="")
    p.set_defaults(func=cmd_full)

    p = sub.add_parser(
        "agency",
        help="Run the full production-agency pipeline: trend discovery -> outlier analysis -> "
             "viral scoring -> selection gate -> research -> fact-check -> scripting -> retention "
             "review -> storyboard -> visual/voice/assembly plans -> titles -> thumbnails -> "
             "packaging -> quality control -> AWAITING_HUMAN_APPROVAL. Never publishes.",
    )
    p.add_argument("--niche", default=None, help="Defaults to pipeline_config.json niche list")
    p.add_argument("--audience", default=None, help="Defaults to pipeline_config.json default_audience")
    p.add_argument("--duration", type=int, default=None, help="Defaults to pipeline_config.json default_duration_minutes")
    p.add_argument("--tone", default="conversational, confident, a little informal")
    p.add_argument("--context", default="", help="Extra context to steer trend research")
    p.add_argument("--candidates", type=int, default=5, help="Number of candidate topics to score")
    p.add_argument(
        "--force", action="store_true",
        help="Manually approve production even if the best candidate scores below the reject "
             "threshold (per the spec: 'REJECT unless manually approved'). Does not change the score.",
    )
    p.set_defaults(func=cmd_agency)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    kwargs = {}
    if args.model:
        kwargs["model"] = args.model
    if args.cli_path:
        kwargs["cli_path"] = args.cli_path
    agent = YouTubeProductionAgent(**kwargs)

    try:
        asyncio.run(args.func(agent, args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if "authenticate" in str(e).lower() or "oauth" in str(e).lower() or "login" in str(e).lower():
            print(
                "\nThis agent needs the Claude Code CLI installed and logged in "
                "(npm install -g @anthropic-ai/claude-code, then run `claude` once "
                "to log in with your subscription). If it's installed somewhere not "
                "on PATH, pass --cli-path.",
                file=sys.stderr,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
