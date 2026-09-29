"""Coach memory tools plugin — profile-local, registers write/read access to
coach.db (learning/career/interview/project/job/goal memory) as agent tools
in the ``coach`` toolset, so the Data Science Career Coach can actually
persist what happens in a session instead of only being able to talk.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Loaded by file path, not as a `plugins.<name>` package import: this directory
# plugin lives under the profile's own plugins/ dir (not the app's bundled
# plugins/ package), and its dirname has a hyphen, so a normal package import
# would not resolve. Given a distinct sys.modules key ("coach_tools_impl") so
# it never collides with the framework's own top-level `tools` package.
_impl_path = Path(__file__).resolve().parent / "tools.py"
_spec = importlib.util.spec_from_file_location("coach_tools_impl", _impl_path)
_t = importlib.util.module_from_spec(_spec)
sys.modules["coach_tools_impl"] = _t
_spec.loader.exec_module(_t)


def register(ctx) -> None:
    for name, schema, handler, emoji in _t.TOOLS:
        ctx.register_tool(name=name, toolset="coach", schema=schema, handler=handler, emoji=emoji)
