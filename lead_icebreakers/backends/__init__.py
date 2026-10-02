"""Model backends. Each is a callable (system prompt, JSON schema, prompt) -> parsed JSON dict.

api   Anthropic API, needs ANTHROPIC_API_KEY (pip install -r requirements.txt)
cli   headless `claude -p` on a logged-in Claude subscription, no key needed
mock  offline, canned answers for the sample file; used by the demo and the tests
"""
from __future__ import annotations

import os
import shutil
from typing import Protocol


class Backend(Protocol):
    name: str

    def __call__(self, system: str, schema: dict, prompt: str) -> dict: ...


def get_backend(name: str = "auto") -> Backend:
    """auto = api when a key is set, else cli when `claude` is installed. Never the mock."""
    if name == "mock":
        from .mock import MockBackend

        return MockBackend()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if name == "api" or (name == "auto" and has_key):
        from .anthropic_api import AnthropicBackend

        return AnthropicBackend()
    if name in ("cli", "auto") and shutil.which("claude"):
        from .claude_cli import ClaudeCLIBackend

        return ClaudeCLIBackend()
    if name == "cli":
        raise SystemExit("--backend cli needs the claude CLI on PATH, logged in.")
    raise SystemExit(
        "No model backend: set ANTHROPIC_API_KEY (api) or install and log in to the claude CLI (cli). "
        "To try it offline: python demo.py, or --backend mock."
    )
