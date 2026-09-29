"""Push a finished VideoProject into Notion as a page.

Requires a Notion internal integration token and a parent page it has been
shared with. Set these as environment variables:

    NOTION_TOKEN            - starts with "secret_" or "ntn_"
    NOTION_PARENT_PAGE_ID   - the page ID (from the page's URL) to create
                              each video's page under

Setup (one-time):
1. Go to https://www.notion.so/my-integrations and create a new internal
   integration. Copy its "Internal Integration Secret" - that's NOTION_TOKEN.
2. Open (or create) a Notion page you want video projects to live under.
3. Click "..." on that page -> Connections -> add your integration.
4. Copy the page ID from the page URL (the 32-char hex chunk after the
   last dash / before any "?") - that's NOTION_PARENT_PAGE_ID.
"""
from __future__ import annotations

import os
import textwrap

from notion_client import Client

from agent import VideoProject


class NotionNotConfigured(RuntimeError):
    pass


def _chunk_paragraphs(text: str, max_len: int = 1900) -> list[str]:
    """Notion rich_text blocks cap at ~2000 chars; split long text safely."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_len:
            if current:
                chunks.append(current)
            if len(para) > max_len:
                chunks.extend(textwrap.wrap(para, max_len, replace_whitespace=False))
                current = ""
            else:
                current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def _heading_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _paragraph_blocks(text: str) -> list[dict]:
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        }
        for chunk in _chunk_paragraphs(text)
    ]


def get_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise NotionNotConfigured(
            "NOTION_TOKEN is not set. See notion_export.py's module docstring "
            "for one-time setup steps."
        )
    return Client(auth=token)


def save_project_to_notion(project: VideoProject) -> str:
    """Creates a Notion page for the project. Returns the page URL."""
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_page_id:
        raise NotionNotConfigured(
            "NOTION_PARENT_PAGE_ID is not set. See notion_export.py's module "
            "docstring for one-time setup steps."
        )
    client = get_client()

    children: list[dict] = [
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {
                        "content": (
                            f"Audience: {project.audience} | Duration: "
                            f"{project.duration_minutes} min | Tone: {project.tone} | "
                            f"Keyword: {project.keyword or '(none)'}"
                        )
                    },
                }],
                "icon": {"emoji": "🎬"},
            },
        }
    ]

    for title, content in [
        ("Outline", project.outline),
        ("Script", project.script),
        ("Metadata (titles, description, tags)", project.metadata),
        ("Thumbnail concepts", project.thumbnails),
    ]:
        if not content:
            continue
        children.append(_heading_block(title))
        children.extend(_paragraph_blocks(content))

    # Notion's API allows at most 100 children per create call.
    first_batch, rest = children[:100], children[100:]

    page = client.pages.create(
        parent={"page_id": parent_page_id},
        properties={"title": {"title": [{"type": "text", "text": {"content": project.idea}}]}},
        children=first_batch,
    )
    page_id = page["id"]

    for i in range(0, len(rest), 100):
        client.blocks.children.append(block_id=page_id, children=rest[i:i + 100])

    return page.get("url", f"https://notion.so/{page_id.replace('-', '')}")
