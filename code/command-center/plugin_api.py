"""Hermes Command Center dashboard API.

Read-only operational view of the whole Hermes installation: gateway state,
platform connections, profiles/providers, memory (Honcho), MCP servers, web
tools (Firecrawl), and host system metrics. Sources only real on-disk state
and already-running process info — never fabricates a value; fields that
cannot be determined are returned as null so the frontend can label them
"not available" instead of a fake number.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter

router = APIRouter()

SENSITIVE_KEY = re.compile(r"(api.?key|token|secret|credential|password|authorization)", re.I)
def _discover_profiles() -> list:
    root = (Path(os.environ["HERMES_HOME"]).resolve() if os.environ.get("HERMES_HOME") else Path.home() / ".hermes")
    names = ["default"]
    try:
        names += sorted(p.name for p in (root / "profiles").iterdir() if (p / "config.yaml").is_file())
    except OSError:
        pass
    return names


PROFILE_NAMES = _discover_profiles()


def _hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    return Path(configured).resolve() if configured else Path.home() / ".hermes"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "[REDACTED]" if SENSITIVE_KEY.search(str(k)) else _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _read_yaml(path: Path, default: Any) -> Any:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if value is not None else default
    except (OSError, yaml.YAMLError):
        return default


def _profile_home(name: str) -> Path:
    root = _hermes_home()
    return root if name == "default" else root / "profiles" / name


def _profile_provider(name: str) -> dict:
    cfg = _read_yaml(_profile_home(name) / "config.yaml", {})
    model = cfg.get("model", {}) if isinstance(cfg, dict) else {}
    return {
        "provider": model.get("provider"),
        "model": model.get("default"),
    }


def _gateway_state() -> dict:
    return _read_json(_hermes_home() / "gateway_state.json", {})


def _uptime_seconds(state: dict) -> float | None:
    """Wall-clock uptime derived from the process's own recorded start_time
    (a monotonic/jiffies-style counter, not epoch) compared against
    /proc/uptime's own clock base — both read from the same clock domain."""
    start_time = state.get("start_time")
    if not isinstance(start_time, (int, float)):
        return None
    try:
        clk_tck = os.sysconf("SC_CLK_TCK")
        with open("/proc/uptime") as f:
            system_uptime = float(f.read().split()[0])
        process_uptime = system_uptime - (start_time / clk_tck)
        return round(process_uptime, 1) if process_uptime >= 0 else None
    except (OSError, ValueError, IndexError):
        return None


def _run(cmd: list[str], timeout: float = 8.0) -> str | None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _honcho_status() -> dict:
    honcho_cfg = _read_json(_hermes_home() / "honcho.json", {})
    if not honcho_cfg:
        return {"configured": False}
    return {
        "configured": True,
        "enabled": honcho_cfg.get("enabled", True),
        "workspace": honcho_cfg.get("workspace_id") or honcho_cfg.get("workspace"),
        "user_peer": honcho_cfg.get("peer_name") or honcho_cfg.get("user_peer"),
        "ai_peer": honcho_cfg.get("ai_peer") or honcho_cfg.get("ai_peer_name"),
        "recall_mode": honcho_cfg.get("recall_mode"),
        "observation_mode": honcho_cfg.get("observation_mode"),
    }


def _obsidian_status() -> dict:
    vault_line = None
    env_path = _hermes_home() / ".env"
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("OBSIDIAN_VAULT_PATH="):
                vault_line = line.split("=", 1)[1].strip()
                break
    except OSError:
        pass
    if not vault_line:
        return {"configured": False}
    vault = Path(vault_line)
    note_count = None
    if vault.is_dir():
        try:
            note_count = sum(1 for _ in vault.rglob("*.md"))
        except OSError:
            note_count = None
    return {"configured": True, "path": vault_line, "exists": vault.is_dir(), "note_count": note_count}


def _mcp_status() -> list[dict]:
    """Parse `hermes mcp list` table output — no JSON output mode exists, so this
    is a best-effort text scrape; returns [] (not fake rows) if parsing fails."""
    out = _run(["hermes", "mcp", "list"])
    if not out:
        return []
    rows = []
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("Name", "─", "MCP Servers")):
            continue
        parts = [p.strip() for p in re.split(r"\s{2,}", stripped) if p.strip()]
        if len(parts) >= 4 and parts[0] not in ("Name",):
            rows.append({"name": parts[0], "transport": parts[1], "status": parts[-1]})
    return rows


def _firecrawl_status() -> dict:
    try:
        import sys
        sys.path.insert(0, "/usr/local/lib/hermes-agent")
        from plugins.web.firecrawl import provider as fc
        from hermes_constants import get_process_hermes_home
        from tui_gateway.launch_profile_policy import launch_profile_runtime_scope
        # FIRECRAWL_API_KEY is a profile-scoped secret; the multiplexed gateway's own leak-prevention
        # guard (agent/secret_scope.py) requires an active scope before any get_secret() call, which
        # this status check otherwise never establishes.
        with launch_profile_runtime_scope(get_process_hermes_home()):
            usable = fc.check_firecrawl_api_key()
            config = fc._get_direct_firecrawl_config()
        mode = config[0] if config else None
        return {"available": usable, "mode": mode, "backend": "firecrawl" if usable else None}
    except Exception:
        return {"available": False, "mode": None, "backend": None}


def _system_metrics() -> dict:
    try:
        import psutil
    except ImportError:
        return {"available": False}
    cpu_percent = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(_hermes_home()))
    load1, load5, load15 = os.getloadavg()
    return {
        "available": True,
        "cpu_percent": cpu_percent,
        "load_avg": {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)},
        "memory": {"percent": mem.percent, "used_gb": round(mem.used / 1e9, 2), "total_gb": round(mem.total / 1e9, 2)},
        "disk": {"percent": disk.percent, "used_gb": round(disk.used / 1e9, 2), "total_gb": round(disk.total / 1e9, 2)},
    }


def _recent_events(limit: int = 40) -> list[dict]:
    """Recent gateway journal lines, parsed into a compact event shape. Filters
    to lines that look like real platform/tool activity, drops raw tracebacks."""
    out = _run([
        "journalctl", "--user", "-u", "hermes-gateway.service",
        "--since", "2 hours ago", "--no-pager", "-o", "short-iso",
    ], timeout=10.0)
    if not out:
        return []
    events = []
    pattern = re.compile(r"^(\S+T\S+)\s+\S+\s+\S+\[\d+\]:\s+(?:\d{4}-\d\d-\d\d [\d:,]+ )?(\w+)\s+([\w.]+):\s+(.*)$")
    for line in out.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        ts, level, source, message = m.groups()
        if any(skip in message for skip in ("Traceback", "File \"", "  File ", "raise ", "await ", "^^^")):
            continue
        if level not in ("INFO", "WARNING", "ERROR"):
            continue
        events.append({"timestamp": ts, "level": level.lower(), "source": source, "message": message[:220]})
    return events[-limit:][::-1]


@router.get("/status")
def status():
    state = _gateway_state()
    platforms = state.get("platforms", {}) if isinstance(state, dict) else {}
    profiles = []
    for name in PROFILE_NAMES:
        provider = _profile_provider(name)
        profiles.append({
            "name": name,
            "provider": provider["provider"],
            "model": provider["model"],
            "served_by_multiplex": name in (state.get("served_profiles") or []),
        })
    return {
        "gateway": {
            "running": state.get("gateway_state") == "running",
            "pid": state.get("pid"),
            "code_version": state.get("code_version"),
            "multiplex_profiles": state.get("served_profiles", []),
            "uptime_seconds": _uptime_seconds(state),
        },
        "platforms": {
            name: {"state": info.get("state"), "error": info.get("error_message"), "needs_attention": info.get("needs_attention")}
            for name, info in platforms.items()
        },
        "profiles": profiles,
        "honcho": _honcho_status(),
        "obsidian": _obsidian_status(),
        "mcp_servers": _mcp_status(),
        "firecrawl": _firecrawl_status(),
        "system": _system_metrics(),
        "generated_at": time.time(),
    }


@router.get("/events")
def events():
    return {"events": _recent_events()}


@router.post("/restart-gateway")
def restart_gateway():
    """Fires `hermes gateway restart` as a detached background process — the command
    itself waits for in-flight turns to drain, so this endpoint returns immediately
    rather than blocking the HTTP request for the full restart duration."""
    subprocess.Popen(
        ["hermes", "gateway", "restart"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True, "message": "Gateway restart requested."}


# ---------------------------------------------------------------------------
# Team-wide usage: aggregated read-only from every profile's state.db plus the
# shared kanban board. Real rows only; nothing is estimated beyond what Hermes
# itself recorded (cost is Hermes' own actual/estimated figure).
# ---------------------------------------------------------------------------
import sqlite3


def _ro(path: Path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    return con


@router.get("/usage")
def usage(days: int = 7):
    days = max(1, min(int(days), 90))
    since = time.time() - days * 86400
    per_profile, per_model, per_day = [], {}, {}
    totals = {"sessions": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
              "api_calls": 0, "tool_calls": 0, "cost_actual_usd": 0.0, "cost_estimated_usd": 0.0}
    for name in PROFILE_NAMES:
        db = _profile_home(name) / "state.db"
        row = {"name": name, "sessions": 0, "input_tokens": 0, "output_tokens": 0,
               "tool_calls": 0, "cost_usd": 0.0, "available": False}
        if db.is_file():
            try:
                con = _ro(db)
                q = ("select model, count(*) n, coalesce(sum(input_tokens),0) i, coalesce(sum(output_tokens),0) o, "
                     "coalesce(sum(cache_read_tokens),0) c, coalesce(sum(api_call_count),0) a, coalesce(sum(tool_call_count),0) t, "
                     "coalesce(sum(actual_cost_usd),0) ca, coalesce(sum(estimated_cost_usd),0) ce "
                     "from sessions where started_at >= ? group by model")
                for r in con.execute(q, (since,)):
                    row["available"] = True
                    row["sessions"] += r["n"]; row["input_tokens"] += r["i"]; row["output_tokens"] += r["o"]
                    row["tool_calls"] += r["t"]
                    free = str(r["model"] or "").endswith(":free")  # OpenRouter :free models cost $0 whatever Hermes estimates
                    cost = 0.0 if free else (r["ca"] or r["ce"])
                    row["cost_usd"] += cost
                    totals["sessions"] += r["n"]; totals["input_tokens"] += r["i"]; totals["output_tokens"] += r["o"]
                    totals["cache_read_tokens"] += r["c"]; totals["api_calls"] += r["a"]; totals["tool_calls"] += r["t"]
                    totals["cost_actual_usd"] += 0.0 if free else r["ca"]; totals["cost_estimated_usd"] += 0.0 if free else r["ce"]
                    m = per_model.setdefault(r["model"] or "unknown", {"model": r["model"] or "unknown", "sessions": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
                    m["sessions"] += r["n"]; m["input_tokens"] += r["i"]; m["output_tokens"] += r["o"]; m["cost_usd"] += cost
                for r in con.execute("select date(started_at,'unixepoch') d, count(*) n, coalesce(sum(input_tokens),0) i, "
                                     "coalesce(sum(output_tokens),0) o from sessions where started_at >= ? group by d", (since,)):
                    d = per_day.setdefault(r["d"], {"date": r["d"], "sessions": 0, "input_tokens": 0, "output_tokens": 0})
                    d["sessions"] += r["n"]; d["input_tokens"] += r["i"]; d["output_tokens"] += r["o"]
                con.close()
            except sqlite3.Error:
                pass
        per_profile.append(row)

    kanban = {"available": False, "runs": 0, "by_profile": []}
    kdb = _hermes_home() / "kanban.db"
    if kdb.is_file():
        try:
            con = _ro(kdb)
            by = {}
            for r in con.execute("select profile, status, coalesce(outcome,'') outcome, count(*) n from task_runs where started_at >= ? group by 1,2,3", (since,)):
                b = by.setdefault(r["profile"] or "unknown", {"profile": r["profile"] or "unknown", "runs": 0, "succeeded": 0, "failed": 0, "running": 0})
                b["runs"] += r["n"]
                if r["status"] in ("done", "completed") or r["outcome"] == "completed":
                    b["succeeded"] += r["n"]
                elif r["status"] in ("running", "claimed"):
                    b["running"] += r["n"]
                else:
                    b["failed"] += r["n"]
            for b in by.values():
                finished = b["succeeded"] + b["failed"]
                b["success_rate"] = round(100 * b["succeeded"] / finished) if finished else None
            kanban = {"available": True, "runs": sum(b["runs"] for b in by.values()), "by_profile": sorted(by.values(), key=lambda x: -x["runs"])}
            con.close()
        except sqlite3.Error:
            pass

    return {
        "days": days,
        "generated_at": time.time(),
        "totals": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in totals.items()},
        "per_profile": sorted(per_profile, key=lambda x: -(x["input_tokens"] + x["output_tokens"])),
        "per_model": sorted(per_model.values(), key=lambda x: -(x["input_tokens"] + x["output_tokens"]))[:8],
        "per_day": sorted(per_day.values(), key=lambda x: x["date"]),
        "kanban": kanban,
        "note": "Sessions are counted per profile database. Cost is Hermes' own recorded figure; models ending in :free are counted as $0.",
    }


# ---------------------------------------------------------------------------
# Server-sent events: pushes new gateway log lines and Kanban events as they
# happen. The browser falls back to polling /events if the stream drops.
# ---------------------------------------------------------------------------
import asyncio
from datetime import datetime, timezone

from fastapi.responses import StreamingResponse

_LOG_RE = re.compile(r"^(\S+T\S+)\s+\S+\s+\S+\[\d+\]:\s+(?:\d{4}-\d\d-\d\d [\d:,]+ )?(\w+)\s+([\w.]+):\s+(.*)$")
_LOG_SKIP = ("Traceback", "File \"", "  File ", "raise ", "await ", "^^^")
_AGENT_NAME = {"default": "Gideon", "scout": "Scout", "scribe": "Scribe", "socialmediaagent": "Reach",
               "youtube-production-agent": "Production", "product-factory": "Product Factory"}


def _parse_log_line(line: str):
    m = _LOG_RE.match(line.strip())
    if not m:
        return None
    ts, level, source, message = m.groups()
    if level not in ("INFO", "WARNING", "ERROR") or any(s in message for s in _LOG_SKIP):
        return None
    return {"timestamp": ts, "level": level.lower(), "source": source, "message": message[:220]}


def _kanban_max_id() -> int:
    db = _hermes_home() / "kanban.db"
    if not db.is_file():
        return 0
    try:
        con = _ro(db)
        try:
            return con.execute("select coalesce(max(id),0) from task_events").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def _kanban_new_events(last_id: int):
    db = _hermes_home() / "kanban.db"
    if not db.is_file():
        return [], last_id
    out, max_id = [], last_id
    try:
        con = _ro(db)
        try:
            rows = con.execute(
                "select e.id, e.kind, e.created_at, t.id tid, t.title, t.assignee from task_events e "
                "join tasks t on t.id = e.task_id where e.id > ? order by e.id", (last_id,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return [], last_id
    verbs = {"created": "new task for", "spawned": "started", "completed": "finished", "blocked": "blocked",
             "crashed": "crashed", "timed_out": "timed out", "spawn_failed": "failed to start", "gave_up": "gave up"}
    for r in rows:
        max_id = max(max_id, r["id"])
        verb = verbs.get(r["kind"])
        if not verb:
            continue
        who = _AGENT_NAME.get(r["assignee"] or "default", r["assignee"] or "unassigned")
        title = " ".join(str(r["title"] or "").split())[:90]
        msg = f"{verb} {who}: {title}" if r["kind"] == "created" else f"{who} {verb}: {title}"
        level = "error" if r["kind"] in ("crashed", "timed_out", "spawn_failed", "gave_up") else ("warning" if r["kind"] == "blocked" else "info")
        ts = datetime.fromtimestamp(r["created_at"] or time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        out.append({"timestamp": ts, "level": level, "source": "kanban", "message": msg})
    return out, max_id


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@router.get("/stream")
async def stream():
    async def gen():
        yield "retry: 3000\n\n"
        yield _sse({"type": "hello"})
        last_id = await asyncio.to_thread(_kanban_max_id)
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "--user", "-u", "hermes-gateway.service", "-f", "-n", "0", "-o", "short-iso",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        idle, last_k = 0, 0.0
        try:
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                    if not line:
                        break
                    ev = _parse_log_line(line.decode("utf-8", "replace"))
                    if ev:
                        idle = 0
                        yield _sse({"type": "log", **ev})
                except asyncio.TimeoutError:
                    pass
                if time.time() - last_k >= 1.0:
                    last_k = time.time()
                    evs, last_id = await asyncio.to_thread(_kanban_new_events, last_id)
                    for e in evs:
                        idle = 0
                        yield _sse({"type": "team", **e})
                idle += 1
                if idle >= 15:
                    idle = 0
                    yield ": ping\n\n"
        finally:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            asyncio.create_task(proc.wait())

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# ---------------------------------------------------------------------------
# Activity heat map (real sessions per day and hour, UTC, across all profiles)
# and the per-agent model dropdown (allowlist + live tool-call probe + audit log).
# ---------------------------------------------------------------------------
import sys
import urllib.error
import urllib.request

from fastapi import HTTPException
from pydantic import BaseModel, Field


@router.get("/heatmap")
def heatmap(days: int = 14, agent: str = ""):
    days = max(1, min(int(days), 60))
    since = time.time() - days * 86400
    grid, agents = {}, {}
    for name in PROFILE_NAMES:
        db = _profile_home(name) / "state.db"
        if not db.is_file():
            continue
        try:
            con = _ro(db)
            try:
                rows = con.execute(
                    "select strftime('%Y-%m-%d', started_at, 'unixepoch') d, cast(strftime('%H', started_at, 'unixepoch') as integer) h, count(*) n "
                    "from sessions where started_at >= ? group by d, h", (since,)).fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            continue
        for r in rows:
            agents[name] = agents.get(name, 0) + r["n"]
            if agent and name != agent:
                continue
            cell = grid.setdefault(r["d"], [0] * 24)
            cell[r["h"]] += r["n"]
    today = datetime.now(tz=timezone.utc).date()
    from datetime import timedelta
    rows_out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        rows_out.append({"date": d, "hours": grid.get(d, [0] * 24)})
    peak = max((max(r["hours"]) for r in rows_out), default=0)
    return {"days": days, "agent": agent or None, "grid": rows_out, "peak": peak,
            "total": sum(sum(r["hours"]) for r in rows_out), "agents": agents, "timezone": "UTC"}


# Models that were verified to answer and to make tool calls. Changing an agent's model is limited to
# this list, and every change is re-probed live before it is applied.
_MODEL_ALLOW = {"openrouter": [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nex-agi/nex-n2.5-pro:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]}
_EDITABLE = {"scout", "scribe", "socialmediaagent", "youtube-production-agent", "product-factory"}


def _env_value(name: str):
    try:
        for line in (_hermes_home() / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return None


def _log_action(text: str) -> None:
    try:
        with open(_hermes_home() / "dashboard-actions.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + text + "\n")
        os.chmod(_hermes_home() / "dashboard-actions.log", 0o600)
    except OSError:
        pass


def _model_rows() -> list:
    rows = []
    for name in PROFILE_NAMES:
        p = _profile_provider(name)
        provider, cur = p["provider"], p["model"]
        editable = name in _EDITABLE and provider in _MODEL_ALLOW
        opts = list(_MODEL_ALLOW.get(provider, [])) if editable else []
        if editable and cur and cur not in opts:
            opts.insert(0, cur)
        rows.append({"name": name, "provider": provider, "model": cur, "editable": editable, "options": opts})
    return rows


@router.get("/models")
def models():
    return {"profiles": _model_rows()}


def _probe_tool_call(model: str):
    """Live check that this model answers AND makes a tool call right now. Models are not
    deterministic, so it gets up to 3 tries; one tool call is enough."""
    key = _env_value("OPENROUTER_API_KEY")
    if not key:
        return False, "No OpenRouter key on the server."
    body = {"model": model, "max_tokens": 300, "tool_choice": "auto",
            "tools": [{"type": "function", "function": {"name": "get_weather", "description": "Get the weather for a city.",
                       "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}],
            "messages": [{"role": "user", "content": "What is the weather in Lagos? Use the tool."}]}
    why = "The model did not make a tool call in 3 tries, so agents could not rely on it."
    for attempt in range(3):
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            why = "The provider refused the test request (HTTP %s)." % e.code + (" It is rate limited right now, try again shortly." if e.code == 429 else "")
            if e.code == 429:
                break
            continue
        except Exception as e:
            why = "The test request failed (%s)." % type(e).__name__
            continue
        calls = ((out.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
        if calls:
            return True, "ok"
    return False, why


class ModelChange(BaseModel):
    model: str = Field(min_length=1, max_length=120)


@router.post("/profiles/{name}/model")
def change_model(name: str, payload: ModelChange):
    row = next((r for r in _model_rows() if r["name"] == name), None)
    if not row or not row["editable"]:
        raise HTTPException(status_code=400, detail="This profile's model can't be changed from the dashboard.")
    if payload.model not in _MODEL_ALLOW[row["provider"]]:
        raise HTTPException(status_code=400, detail="That model isn't on the verified list.")
    if payload.model == row["model"]:
        raise HTTPException(status_code=409, detail="That is already this agent's model.")
    ok, why = _probe_tool_call(payload.model)
    if not ok:
        raise HTTPException(status_code=409, detail="Not changed. " + why)
    env = dict(os.environ)
    env["HERMES_HOME"] = str(_hermes_home())
    try:
        p = subprocess.run([sys.executable, "-m", "hermes_cli.main", "config", "set", "model.default", payload.model, "--profile", name],
                           capture_output=True, text=True, timeout=30, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="The config command timed out.")
    if p.returncode != 0:
        raise HTTPException(status_code=400, detail="Config change failed: " + (p.stderr or p.stdout or "")[-200:])
    _log_action(f"model-change profile={name} {row['model']} -> {payload.model}")
    return {"ok": True, "profile": next(r for r in _model_rows() if r["name"] == name),
            "note": "Saved. New conversations use it; restart the gateway (Quick Commands) to apply it everywhere now."}


# ===========================================================================
# JARVIS: home page data, voice, threads, comms (read-only), docs.
# Real state only. Nothing here sends, deletes or creates anything in Gmail,
# Calendar or Drive: only read commands are ever run.
# ===========================================================================
import base64
import threading
from concurrent.futures import ThreadPoolExecutor

_JARVIS_SETTINGS = Path("/root/.hermes/jarvis-settings.json")
_JARVIS_LOCK = threading.Lock()
_GOOGLE_CLI = ["/usr/bin/python3", "/root/.hermes/skills/productivity/google-workspace/scripts/google_api.py"]
_PF_PROJECTS = Path("/root/.hermes/profiles/product-factory/runtime/projects")
_DEFAULT_SETTINGS = {"voice": "en-GB-RyanNeural", "rate": "-3%", "pitch": "-6Hz", "tts_enabled": True, "primary_project": "", "speed": "balanced", "engine": "jarvis", "jarvis_voice": "jarvis"}
# Per-session model overrides for Jarvis conversations (never written to any profile config). Measured on this server:
# fastest about 3 to 5 s a reply (small model, slips on details), balanced about 8 s (5 of 5 correct in tests), original about 25 s.
_SPEED_MODELS = {
    "fastest": {"provider": "openrouter", "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "reasoning_effort": "low"},
    "balanced": {"provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free", "reasoning_effort": "low"},
    "original": None,
    # ChatGPT subscription through Hermes' openai-codex provider (flat fee, no per-token cost). Measured 2026-09-21: median 4.7 s, first word 3.5 s, steadiest.
    "premium": {"provider": "openai-codex", "model": "gpt-5.6-terra"},
}
_TEXT_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|xox[abp]-[A-Za-z0-9\-]{10,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b)")
_cache: dict = {}


def _cached(key: str, ttl: float, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def _settings() -> dict:
    with _JARVIS_LOCK:
        try:
            data = json.loads(_JARVIS_SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    out = dict(_DEFAULT_SETTINGS)
    out.update({k: v for k, v in data.items() if k in _DEFAULT_SETTINGS})
    return out


def _codex_login_ok() -> bool:
    """True when the ChatGPT login used by Premium mode is present (cached 5 minutes; read-only check, no model request)."""
    def probe():
        try:
            p = subprocess.run(["hermes", "auth", "status", "openai-codex"], capture_output=True, text=True, timeout=10)
            return "logged in" in (p.stdout + p.stderr).lower() and "not logged in" not in (p.stdout + p.stderr).lower()
        except Exception:
            return False
    return bool(_cached("codex_login", 300, probe))


def _settings_public() -> dict:
    return dict(_settings(), speed_models=_SPEED_MODELS, premium_ok=_codex_login_ok())


def _save_settings(patch: dict) -> dict:
    cur = _settings()
    cur.update(patch)
    with _JARVIS_LOCK:
        tmp = _JARVIS_SETTINGS.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(_JARVIS_SETTINGS)
    return cur


def _scrub_text(s, limit=None):
    s = _TEXT_SECRET.sub("[REDACTED]", str(s or ""))
    return s[:limit] if limit else s


def _cli(args: list, timeout: int = 45):
    """Run one read-only Google CLI command; returns (ok, parsed_json_or_None, seconds)."""
    t = time.time()
    try:
        p = subprocess.run(_GOOGLE_CLI + args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except Exception:
        return False, None, round(time.time() - t, 1)
    try:
        data = json.loads(p.stdout) if p.returncode == 0 else None
    except ValueError:
        data = None
    return p.returncode == 0 and data is not None, data, round(time.time() - t, 1)


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


# ---------------- tools (live checks, cached) ----------------
def _google_tiles() -> list:
    now = time.time()
    jobs = {
        "gmail": ["gmail", "search", "in:inbox", "--max", "1"],
        "calendar": ["calendar", "list", "--start", _iso(now), "--end", _iso(now + 3600), "--max", "1"],
        "drive": ["drive", "search", "trashed=false", "--max", "1"],
    }
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {k: ex.submit(_cli, a) for k, a in jobs.items()}
        res = {k: f.result() for k, f in futs.items()}
    try:
        scopes = json.loads(Path("/root/.hermes/google_token.json").read_text(encoding="utf-8")).get("scopes") or []
    except (OSError, ValueError):
        scopes = []
    have = lambda frag: any(frag in s for s in scopes)
    tiles = []
    for key, label in (("gmail", "Gmail"), ("calendar", "Calendar"), ("drive", "Drive")):
        ok, _, secs = res[key]
        tiles.append({"key": key, "label": label, "status": "ok" if ok else "down", "detail": f"live read check ok ({secs}s)" if ok else "read check failed", "kind": "live"})
    tiles.append({"key": "docs", "label": "Docs", "status": "ok" if have("documents") else "down", "detail": "scope granted (same login)" if have("documents") else "scope missing", "kind": "scope"})
    tiles.append({"key": "sheets", "label": "Sheets", "status": "ok" if have("spreadsheets") else "down", "detail": "scope granted (same login)" if have("spreadsheets") else "scope missing", "kind": "scope"})
    return tiles


def _tools() -> dict:
    tiles = list(_cached("google_tiles", 300, _google_tiles))
    try:
        ob = _obsidian_status()
        tiles.append({"key": "obsidian", "label": "Obsidian", "status": "ok" if ob.get("configured") else "down",
                      "detail": (str(ob.get("note_count")) + " notes") if ob.get("note_count") is not None else "vault configured", "kind": "live"})
    except Exception:
        pass
    try:
        fc = _firecrawl_status()
        tiles.append({"key": "firecrawl", "label": "Firecrawl", "status": "ok" if fc.get("available") else "down", "detail": "keyless web search" if fc.get("available") else "unavailable", "kind": "live"})
    except Exception:
        pass
    try:
        for m in (_mcp_status() or []):
            if isinstance(m, dict) and m.get("name"):
                tiles.append({"key": "mcp-" + str(m["name"]), "label": str(m["name"]).title(), "status": "ok" if m.get("enabled", True) else "info", "detail": "MCP server " + ("enabled" if m.get("enabled", True) else "disabled"), "kind": "config"})
    except Exception:
        pass
    return {"tiles": tiles, "generated_at": time.time()}


@router.get("/jarvis/tools")
def jarvis_tools(refresh: int = 0):
    if refresh:
        _cache.pop("google_tiles", None)
    return _tools()


# ---------------- environment ----------------
def _vps_uptime():
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        return None


def _tailscale() -> dict:
    try:
        p = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=6)
        d = json.loads(p.stdout)
        me = d.get("Self", {})
        peers = [x for x in (d.get("Peer") or {}).values() if x.get("Online")]
        return {"online": bool(me.get("Online")), "ip": (me.get("TailscaleIPs") or [None])[0], "peers_online": len(peers)}
    except Exception:
        return {"online": False, "ip": None, "peers_online": 0}


def _cron_jobs() -> list:
    try:
        j = json.loads(Path("/root/.hermes/cron/jobs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    jobs = j.get("jobs", j) if isinstance(j, dict) else j
    return [x for x in jobs if isinstance(x, dict)]


def _backup_age_hours():
    newest = 0.0
    for d in ("custom", "data", "secrets"):
        for f in Path("/root/backups", d).glob(f"{d}-*.tar.gz"):
            try:
                newest = max(newest, f.stat().st_mtime)
            except OSError:
                pass
    return round((time.time() - newest) / 3600, 1) if newest else None


@router.get("/jarvis/env")
def jarvis_env():
    state = _gateway_state()
    plats = state.get("platforms", {}) if isinstance(state, dict) else {}
    ts = _cached("tailscale", 20, _tailscale)
    jobs = _cron_jobs()
    bad = [j for j in jobs if j.get("enabled") and j.get("last_status") not in (None, "ok")]
    age = _backup_age_hours()
    rows = [
        {"key": "vps", "label": "VPS", "status": "ok", "detail": "uptime " + fmt_uptime(_vps_uptime())},
        {"key": "tailscale", "label": "Tailscale", "status": "ok" if ts["online"] else "down", "detail": (ts["ip"] or "") + (f" · {ts['peers_online']} device(s) online" if ts["online"] else " offline")},
    ]
    for name in ("telegram", "slack"):
        p = plats.get(name) or {}
        rows.append({"key": name, "label": name.title(), "status": "ok" if p.get("state") == "connected" else "down", "detail": p.get("state") or "not configured"})
    g = next((t for t in _cached("google_tiles", 300, _google_tiles) if t["key"] == "gmail"), None)
    cal = next((t for t in _cached("google_tiles", 300, _google_tiles) if t["key"] == "calendar"), None)
    gok = bool(g and cal and g["status"] == "ok" and cal["status"] == "ok")
    rows.append({"key": "google", "label": "Google Workspace", "status": "ok" if gok else "degraded", "detail": "Gmail and Calendar reads ok" if gok else "a read check failed"})
    rows.append({"key": "cron", "label": "Scheduled jobs", "status": "ok" if jobs and not bad else ("degraded" if bad else "info"),
                 "detail": (f"{len(jobs)} jobs, last runs ok" if jobs and not bad else f"{len(bad)} job(s) last failed" if bad else "none")})
    rows.append({"key": "backup", "label": "Backups", "status": "ok" if age is not None and age < 36 else "degraded", "detail": (f"last backup {age}h ago" if age is not None else "no backup found")})
    return {"rows": rows, "generated_at": time.time()}


def fmt_uptime(sec):
    if sec is None:
        return "unknown"
    d, r = divmod(int(sec), 86400); h, r = divmod(r, 3600); m = r // 60
    return f"{d}d {h}h" if d else f"{h}h {m}m"


# ---------------- health score (transparent) ----------------
_UNITS = ["hermes-gateway", "hermes-dashboard", "hermes-dashboard-product-factory", "hermes-factory-floor", "hermes-library-export", "hermes-jarvis-voice", "hermes-backup.timer"]


def _health() -> dict:
    items = []

    def add(name, ok, weight, detail, warn=False):
        items.append({"name": name, "ok": ok, "weight": weight, "detail": detail, "warn": warn})

    active = []
    for u in _UNITS:
        try:
            p = subprocess.run(["systemctl", "--user", "is-active", u], capture_output=True, text=True, timeout=5)
            active.append(p.stdout.strip() == "active")
        except Exception:
            active.append(False)
    add("Services", all(active), 40, f"{sum(active)}/{len(_UNITS)} running")
    state = _gateway_state()
    plats = state.get("platforms", {}) if isinstance(state, dict) else {}
    conn = [n for n in ("telegram", "slack") if (plats.get(n) or {}).get("state") == "connected"]
    add("Channels", len(conn) == 2, 20, ", ".join(conn) + " connected" if conn else "none connected")
    sysm = _system_metrics() or {}
    disk = (sysm.get("disk") or {}).get("percent"); mem = (sysm.get("memory") or {}).get("percent"); cpu = sysm.get("cpu_percent")
    add("Resources", (disk or 0) < 85 and (mem or 0) < 85, 20, f"disk {disk}%, memory {mem}%, cpu {cpu}%")
    age = _backup_age_hours()
    add("Backups", age is not None and age < 36, 10, f"last backup {age}h ago" if age is not None else "none")
    try:
        out = subprocess.run(["journalctl", "--user", "-u", "hermes-gateway", "--since", "30 min ago", "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=10).stdout
        errs = sum(1 for line in out.splitlines() if " ERROR " in line or line.startswith("ERROR"))
    except Exception:
        errs = 0
    add("Recent errors", errs == 0, 10, f"{errs} gateway error(s) in 30 min")
    score = sum(i["weight"] for i in items if i["ok"])
    return {"score": score, "items": items, "generated_at": time.time()}


@router.get("/jarvis/health")
def jarvis_health():
    return _cached("health", 30, _health)


# ---------------- primary mission (from the Product Factory projects) ----------------
def _project_summary(state_file: Path) -> dict:
    try:
        st = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    explicit = st.get("selected_specialists")
    done = list(st.get("specialists_completed", []))
    cur = st.get("specialist_in_progress")
    pend = list(st.get("pending_specialists", []))
    selected = [str(x) for x in explicit] if isinstance(explicit, list) else list(dict.fromkeys([*done, *([cur] if cur else []), *pend]))
    steps = [{"name": s, "status": "COMPLETE" if s in done else "ACTIVE" if s == cur else "PENDING"} for s in selected]
    phase = st.get("current_phase", "UNKNOWN")
    pct = round(100 * len(done) / len(selected)) if selected else (100 if phase == "COMPLETED" else 0)
    return {"id": state_file.parent.name, "name": st.get("project_name", state_file.parent.name), "type": st.get("project_type", ""),
            "phase": phase, "milestone": st.get("current_milestone") or str(phase).replace("_", " ").title(),
            "progress": pct, "steps": steps, "updated_at": st.get("updated_at")}


@router.get("/jarvis/mission")
def jarvis_mission():
    projects = []
    if _PF_PROJECTS.is_dir():
        for f in _PF_PROJECTS.glob("*/state.json"):
            s = _project_summary(f)
            if s:
                s["_mtime"] = f.stat().st_mtime
                projects.append(s)
    projects.sort(key=lambda p: (p.get("updated_at") or "", p["_mtime"]), reverse=True)
    pinned = _settings().get("primary_project")
    primary = next((p for p in projects if p["id"] == pinned), None) or (projects[0] if projects else None)
    for p in projects:
        p.pop("_mtime", None)
    return {"primary": primary, "pinned": bool(pinned and primary and primary["id"] == pinned),
            "projects": [{"id": p["id"], "name": p["name"]} for p in projects]}


class MissionPin(BaseModel):
    project_id: str = Field(default="", max_length=120)


@router.post("/jarvis/mission")
def jarvis_mission_pin(payload: MissionPin):
    pid = payload.project_id.strip()
    if pid and not (_PF_PROJECTS / pid / "state.json").is_file():
        raise HTTPException(status_code=404, detail="Project not found.")
    if pid and Path(pid).name != pid:
        raise HTTPException(status_code=400, detail="Invalid project id.")
    _save_settings({"primary_project": pid})
    _log_action(f"jarvis primary mission set to {pid or '(latest)'}")
    return jarvis_mission()


# ---------------- voice ----------------
_MD = [(re.compile(r"```.*?```", re.S), " (code omitted) "), (re.compile(r"`([^`]*)`"), r"\1"), (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
       (re.compile(r"https?://\S+"), " link "), (re.compile(r"^#+\s*", re.M), ""), (re.compile(r"[*_>~|]+"), ""), (re.compile(r"^\s*[-•]\s+", re.M), "")]
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_TAG = re.compile(r"^\s*(?:Gideon|Scout|Scribe|Reach|Production|Product Factory)\s*:\s*", re.I)


def _speakable(text: str, limit: int = 1200) -> str:
    t = _EMOJI.sub("", str(text or ""))
    t = _TAG.sub("", t)
    for rx, rep_ in _MD:
        t = rx.sub(rep_, t)
    t = t.replace("—", ", ").replace("–", "-")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


_JV_ID = re.compile(r"^[a-z]{2,20}$")
_VOICE_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")
_RATE_RE = re.compile(r"^[+-]\d{1,2}%$")
_PITCH_RE = re.compile(r"^[+-]\d{1,2}Hz$")
_FALLBACK_VOICES = [("en-GB-RyanNeural", "Male", "en-GB"), ("en-GB-ThomasNeural", "Male", "en-GB"), ("en-GB-SoniaNeural", "Female", "en-GB"),
                    ("en-AU-WilliamNeural", "Male", "en-AU"), ("en-IE-ConnorNeural", "Male", "en-IE"), ("en-NG-AbeoNeural", "Male", "en-NG"),
                    ("en-ZA-LukeNeural", "Male", "en-ZA"), ("en-US-GuyNeural", "Male", "en-US"), ("en-US-AndrewNeural", "Male", "en-US")]


_VOICE_SVC = "http://127.0.0.1:9931"
_JV_FALLBACK = [{"id": "jarvis", "label": "Jarvis (signature blend)"}]


def _jarvis_presets() -> list:
    hit = _cache.get("jv_presets")
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        import urllib.request
        with urllib.request.urlopen(_VOICE_SVC + "/voices", timeout=2) as r:
            vs = json.loads(r.read().decode("utf-8")).get("voices") or _JV_FALLBACK
    except Exception:
        vs = _JV_FALLBACK if not hit else hit[1]
    _cache["jv_presets"] = (time.time(), vs)
    return vs


def _jarvis_tts(text: str, voice: str) -> bytes:
    import urllib.request
    req = urllib.request.Request(_VOICE_SVC + "/tts", data=json.dumps({"text": text, "voice": voice}).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


@router.get("/jarvis/voices")
async def jarvis_voices():
    async def fetch():
        import edge_tts
        vs = await edge_tts.list_voices()
        return [{"name": v["ShortName"], "gender": v.get("Gender"), "locale": v.get("Locale")} for v in vs if str(v.get("Locale", "")).startswith("en-")]
    hit = _cache.get("voices")
    if not (hit and time.time() - hit[0] < 6 * 3600):
        try:
            _cache["voices"] = (time.time(), await asyncio.wait_for(fetch(), timeout=15))
        except Exception:
            _cache["voices"] = (time.time() - 5 * 3600, [{"name": n, "gender": g, "locale": l} for n, g, l in _FALLBACK_VOICES])
    return {"voices": _cache["voices"][1], "jarvis_voices": _jarvis_presets(), "settings": _settings_public()}


class SpeakReq(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str = ""
    rate: str = ""
    pitch: str = ""
    engine: str = ""
    jarvis_voice: str = ""


@router.post("/jarvis/speak")
async def jarvis_speak(payload: SpeakReq):
    cfg = _settings()
    voice = payload.voice or cfg["voice"]; rate = payload.rate or cfg["rate"]; pitch = payload.pitch or cfg["pitch"]
    if not (_VOICE_RE.match(voice) and _RATE_RE.match(rate) and _PITCH_RE.match(pitch)):
        raise HTTPException(status_code=400, detail="Invalid voice settings.")
    text = _speakable(payload.text)
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to say.")
    engine = payload.engine or cfg.get("engine", "jarvis")
    jv_voice = payload.jarvis_voice or cfg.get("jarvis_voice", "jarvis")
    if engine == "jarvis" and _JV_ID.match(jv_voice):
        try:
            mp3 = await asyncio.wait_for(asyncio.to_thread(_jarvis_tts, text, jv_voice), timeout=28)
            if mp3:
                return {"ok": True, "data_url": "data:audio/mpeg;base64," + base64.b64encode(mp3).decode("ascii"), "voice": jv_voice, "engine": "jarvis", "chars": len(text)}
        except Exception:
            pass   # the local voice is busy or down: fall back to the cloud voice rather than going silent
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio = bytearray()

        async def run():
            async for chunk in comm.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk["data"])
        await asyncio.wait_for(run(), timeout=40)
    except Exception as e:
        raise HTTPException(status_code=502, detail="Speech synthesis failed (" + type(e).__name__ + ").")
    if not audio:
        raise HTTPException(status_code=502, detail="Speech synthesis returned no audio.")
    return {"ok": True, "data_url": "data:audio/mpeg;base64," + base64.b64encode(bytes(audio)).decode("ascii"), "voice": voice, "engine": "edge", "chars": len(text)}


class SettingsPatch(BaseModel):
    voice: str = ""
    rate: str = ""
    pitch: str = ""
    tts_enabled: bool | None = None
    speed: str = ""
    engine: str = ""
    jarvis_voice: str = ""


@router.get("/jarvis/settings")
def jarvis_settings_get():
    return _settings_public()


@router.post("/jarvis/settings")
def jarvis_settings_set(p: SettingsPatch):
    patch = {}
    if p.voice:
        if not _VOICE_RE.match(p.voice):
            raise HTTPException(status_code=400, detail="Invalid voice.")
        patch["voice"] = p.voice
    if p.rate:
        if not _RATE_RE.match(p.rate):
            raise HTTPException(status_code=400, detail="Invalid rate.")
        patch["rate"] = p.rate
    if p.pitch:
        if not _PITCH_RE.match(p.pitch):
            raise HTTPException(status_code=400, detail="Invalid pitch.")
        patch["pitch"] = p.pitch
    if p.tts_enabled is not None:
        patch["tts_enabled"] = bool(p.tts_enabled)
    if p.engine:
        if p.engine not in ("jarvis", "edge"):
            raise HTTPException(status_code=400, detail="Unknown voice engine.")
        patch["engine"] = p.engine
    if p.jarvis_voice:
        if not _JV_ID.match(p.jarvis_voice):
            raise HTTPException(status_code=400, detail="Invalid Jarvis voice.")
        patch["jarvis_voice"] = p.jarvis_voice
    if p.speed:
        if p.speed not in _SPEED_MODELS:
            raise HTTPException(status_code=400, detail="Unknown speed mode.")
        patch["speed"] = p.speed
    return _save_settings(patch) if patch else _settings()


# ---------------- threads (Telegram topics and Slack, from each profile's sessions) ----------------
def _route_labels() -> dict:
    """thread_id -> (label, profile) from gateway.profile_routes; General/Factory Floor are added by hand."""
    labels = {"1": ("General", "default"), "247": ("Factory Floor", "default")}
    try:
        cfg = yaml.safe_load((_hermes_home() / "config.yaml").read_text(encoding="utf-8")) or {}
        for r in (cfg.get("gateway", {}) or {}).get("profile_routes", []) or []:
            tid = str(r.get("thread_id") or "")
            if tid:
                labels[tid] = (str(r.get("name", "")).split("-")[-1].title() or tid, str(r.get("profile") or "default"))
    except Exception:
        pass
    return labels


@router.get("/jarvis/threads")
def jarvis_threads():
    labels = _route_labels()
    best: dict = {}      # group key -> newest session across every profile's database
    counts: dict = {}    # group key -> number of sessions seen
    for prof in PROFILE_NAMES:
        db = _profile_home(prof) / "state.db"
        if not db.is_file():
            continue
        try:
            con = _ro(db)
            try:
                rows = con.execute(
                    "select id, source, chat_id, chat_type, thread_id, display_name, title, last_activity_at "
                    "from sessions where source in ('telegram','slack') and coalesce(hidden,0)=0 order by last_activity_at desc limit 300").fetchall()
                for r in rows:
                    key = f"{r['source']}|{r['chat_id']}|{r['thread_id'] or ''}"
                    counts[key] = counts.get(key, 0) + 1
                    ts = r["last_activity_at"] or 0
                    if key not in best or ts > best[key]["ts"]:
                        best[key] = {"prof": prof, "row": dict(r), "ts": ts}
            finally:
                con.close()
        except sqlite3.Error:
            continue
    out = []
    for key, b in best.items():
        r, prof = b["row"], b["prof"]
        tid = str(r["thread_id"] or "")
        if r["source"] == "telegram" and r["chat_type"] != "dm" and tid in labels:
            label, agent = labels[tid]
        elif r["chat_type"] == "dm":
            label, agent = "Direct chat", prof
        else:
            label, agent = (r["display_name"] or r["title"] or "Conversation"), prof
        snippet, last_role = "", None
        try:
            con = _ro(_profile_home(prof) / "state.db")
            try:
                last = con.execute("select role, content from messages where session_id=? and role in ('user','assistant') and coalesce(content,'')!='' order by timestamp desc limit 1", (r["id"],)).fetchone()
            finally:
                con.close()
            if last:
                snippet, last_role = _scrub_text(" ".join(str(last["content"]).split()), 140), last["role"]
        except sqlite3.Error:
            pass
        out.append({"key": key, "label": label, "agent": agent, "platform": r["source"], "profile": prof, "session_id": r["id"],
                    "last_activity_at": _iso(b["ts"]) if b["ts"] else None, "_ts": b["ts"], "sessions": counts.get(key, 1), "snippet": snippet, "last_role": last_role})
    out.sort(key=lambda x: -x["_ts"])
    for o in out:
        o.pop("_ts", None)
    return {"threads": out[:40]}


@router.get("/jarvis/threads/{profile}/{session_id}")
def jarvis_thread_messages(profile: str, session_id: str, limit: int = 40):
    if profile not in PROFILE_NAMES or not re.match(r"^[A-Za-z0-9_\-]{4,64}$", session_id):
        raise HTTPException(status_code=400, detail="Invalid thread.")
    db = _profile_home(profile) / "state.db"
    if not db.is_file():
        raise HTTPException(status_code=404, detail="Thread not found.")
    con = _ro(db)
    try:
        rows = con.execute("select role, content, timestamp from messages where session_id=? and role in ('user','assistant') and coalesce(content,'')!='' order by timestamp desc limit ?",
                           (session_id, max(1, min(int(limit), 100)))).fetchall()
    finally:
        con.close()
    msgs = [{"role": r["role"], "text": _scrub_text(r["content"], 1500), "at": _iso(r["timestamp"]) if r["timestamp"] else None} for r in reversed(rows)]
    return {"messages": msgs}


# ---------------- comms (read-only) ----------------
def _comms() -> dict:
    now = time.time()
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_mail = ex.submit(_cli, ["gmail", "search", "is:unread in:inbox", "--max", "8"])
        f_cal = ex.submit(_cli, ["calendar", "list", "--start", _iso(now), "--end", _iso(now + 172800), "--max", "8"])
        mail_ok, mail, _ = f_mail.result(); cal_ok, cal, _ = f_cal.result()
    mails = [{"from": _scrub_text(m.get("from"), 80), "subject": _scrub_text(m.get("subject"), 120), "date": m.get("date"), "snippet": _scrub_text(m.get("snippet"), 160)}
             for m in (mail or []) if isinstance(m, dict)]
    events = []
    for e in (cal or []):
        if isinstance(e, dict):
            st = e.get("start") or {}
            events.append({"summary": _scrub_text(e.get("summary") or e.get("title") or "(no title)", 100),
                           "start": (st.get("dateTime") or st.get("date")) if isinstance(st, dict) else st, "location": _scrub_text(e.get("location"), 80)})
    return {"mail_ok": mail_ok, "calendar_ok": cal_ok, "unread": mails, "events": events, "read_only": True, "generated_at": now}


@router.get("/jarvis/comms")
def jarvis_comms(refresh: int = 0):
    if refresh:
        _cache.pop("comms", None)
    return _cached("comms", 120, _comms)


# ---------------- docs ----------------
@router.get("/jarvis/docs")
def jarvis_docs():
    try:
        text = (_hermes_home() / "RUNBOOK.md").read_text(encoding="utf-8")
    except OSError:
        text = "The runbook has not been written yet."
    return {"title": "Hermes VPS runbook", "content": _scrub_text(text), "updated_at": (_iso((_hermes_home() / "RUNBOOK.md").stat().st_mtime) if (_hermes_home() / "RUNBOOK.md").exists() else None)}


# ---------------- active tasks (shared Kanban board, read-only) ----------------
@router.get("/jarvis/tasks")
def jarvis_tasks():
    db = _hermes_home() / "kanban.db"
    if not db.is_file():
        return {"tasks": [], "counts": {}}
    con = _ro(db)
    try:
        rows = con.execute(
            "select id, title, assignee, status, created_at, started_at, completed_at from tasks "
            "where status != 'archived' order by case status when 'running' then 0 when 'blocked' then 1 when 'ready' then 2 when 'todo' then 3 else 4 end, "
            "coalesce(completed_at, started_at, created_at) desc limit 12").fetchall()
        counts = {r["status"]: r["n"] for r in con.execute("select status, count(*) n from tasks where status != 'archived' group by status")}
    finally:
        con.close()
    now = time.time()
    out = []
    for r in rows:
        elapsed = int(now - r["started_at"]) if r["status"] == "running" and r["started_at"] else None
        out.append({"id": r["id"], "title": _scrub_text(r["title"], 90), "agent": _AGENT_NAME.get(r["assignee"] or "default", r["assignee"] or "unassigned"),
                    "status": r["status"], "elapsed": elapsed, "at": _iso(r["completed_at"] or r["started_at"] or r["created_at"])})
    return {"tasks": out, "counts": counts}


# ---------------- live facts handed to Gideon with each spoken question ----------------
def _human_cron(expr: str) -> str:
    m = re.match(r"^(\d{1,2}) (\d{1,2}) \* \* (\*|1-5|0,6|[0-6])$", str(expr or "").strip())
    if not m:
        return str(expr or "")
    when = f"{int(m.group(2)):02d}:{int(m.group(1)):02d} UTC"
    dow = {"*": "every day", "1-5": "weekdays", "0,6": "weekends"}.get(m.group(3)) or ["Sundays", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays"][int(m.group(3))]
    return f"{dow} at {when}"


def _in_words(iso: str) -> str:
    try:
        secs = datetime.fromisoformat(str(iso)).timestamp() - time.time()
    except ValueError:
        return "unknown"
    if secs <= 0:
        return "due now"
    return f"in {max(1, round(secs / 60))} min" if secs < 3600 else f"in {round(secs / 3600)} h" if secs < 86400 else f"in {round(secs / 86400)} d"


_GMAIL_DIR = '/root/.hermes/skills/productivity/google-workspace/scripts'
_UNREAD_SNIPPET = ("import sys, json; sys.path.insert(0, %r); import google_api; s = google_api.build_service('gmail', 'v1'); "
                   "l = s.users().labels().get(userId='me', id='INBOX').execute(); print(json.dumps(l.get('messagesUnread')))") % _GMAIL_DIR


def _unread_count():
    try:
        p = subprocess.run(["/usr/bin/python3", "-c", _UNREAD_SNIPPET], capture_output=True, text=True, timeout=25, stdin=subprocess.DEVNULL)
        return int(json.loads(p.stdout.strip().splitlines()[-1]))
    except Exception:
        return None


def _brief() -> dict:
    now = time.time()
    parts = [f"Live facts from the dashboard, checked {time.strftime('%A %d %B %H:%M', time.gmtime(now))} UTC (use these for status questions instead of running tools):"]
    t = jarvis_tasks()
    counts = t.get("counts", {})
    parts.append("Task board: " + (", ".join(f"{n} {k}" for k, n in sorted(counts.items())) if counts else "empty") + ".")
    running = [x for x in t.get("tasks", []) if x["status"] == "running"]
    if running:
        parts.append("Running now: " + "; ".join(f"{x['agent']} on {x['title']}" for x in running[:3]) + ".")
    jobs = [j for j in _cron_jobs() if j.get("name")]
    if jobs:
        parts.append("Scheduled jobs (UTC): " + "; ".join(
            f"{j['name']} {_human_cron(j.get('schedule_display') or '')}" + (f" (next {_in_words(j.get('next_run_at'))})" if j.get("enabled") and j.get("next_run_at") else " (paused)") for j in jobs) + ".")
    try:
        parts.append(f"System health {_cached('health', 30, _health)['score']} percent.")
    except Exception:
        pass
    n = _cached("unread_count", 120, _unread_count)
    if n is not None:
        parts.append(f"Gmail inbox: {n} unread (count only).")
    try:
        cm = _cached("comms", 120, _comms)
        if cm.get("calendar_ok"):
            parts.append(f"Calendar: {len(cm.get('events', []))} event(s) in the next 48 hours (count only).")
    except Exception:
        pass
    return {"text": " ".join(parts), "generated_at": now}


_swr_busy: set = set()


def _swr(key: str, ttl: float, fn):
    hit, now = _cache.get(key), time.time()
    if hit:
        if now - hit[0] > ttl and key not in _swr_busy:
            _swr_busy.add(key)

            def run():
                try:
                    _cache[key] = (time.time(), fn())
                except Exception:
                    pass
                finally:
                    _swr_busy.discard(key)
            threading.Thread(target=run, daemon=True).start()
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


@router.get("/jarvis/brief")
def jarvis_brief():
    return _swr("brief", 20, _brief)
