"""Configurable thresholds, retry limits, model tiers, and niche scope for the
production agency pipeline. Lives in pipeline_config.json at the project
root - created with sensible defaults on first use, editable by hand.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "pipeline_config.json"

DEFAULTS = {
    "thresholds": {
        "high_priority": 80,
        "improve_angle": 65,
    },
    "qc_max_retries": 2,
    "models": {
        "routine": "haiku",
        "standard": "sonnet",
        "research": "sonnet",
        "complex_reasoning": "sonnet",
        "fact_checking": "sonnet",
        "final_review": "sonnet",
    },
    "niche": [
        "AI", "AI agents", "Data science", "Machine learning",
        "Automation", "AI tools", "Practical tutorials", "Emerging technology",
    ],
    "default_audience": "people curious about practical AI and data tools, beginner to intermediate",
    "default_duration_minutes": 8,
}


def _merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            _merge(cfg, user_cfg)
        except (json.JSONDecodeError, OSError):
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
