"""Paths and settings. The editable files live in ./config so they are easy to find."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("ICEBREAKERS_CONFIG_DIR") or ROOT / "config")
TEMPLATES_FILE = CONFIG_DIR / "templates.toml"
RULES_FILE = CONFIG_DIR / "rules.md"
OVERRIDES_FILE = CONFIG_DIR / "overrides.csv"  # your own rulings; gitignored, it is lead data
OVERRIDES_EXAMPLE = CONFIG_DIR / "overrides.example.csv"  # fictional, used by the demo
FIXTURES = ROOT / "fixtures"
OUT_DIR = ROOT / "out"

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"


def load_env() -> None:
    """Load ./.env when python-dotenv is installed. Variables already set in the shell win."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def model() -> str:
    return os.environ.get("ICEBREAKERS_MODEL") or DEFAULT_MODEL


def effort() -> str:
    return os.environ.get("ICEBREAKERS_EFFORT") or DEFAULT_EFFORT
