"""Headless `claude -p` backend: runs on a logged-in Claude subscription, no API key needed.

No tools, no saved session, no user or project settings: the model gets the system prompt,
the JSON schema and the rows, nothing else.
"""
from __future__ import annotations

import json
import subprocess
import tempfile

from .. import config


class ClaudeCLIBackend:
    def __init__(self, model: str | None = None, effort: str | None = None, timeout: int = 600):
        self.model = model or config.model()
        self.effort = effort or config.effort()
        self.timeout = timeout
        self.name = f"cli:{self.model}"

    def __call__(self, system: str, schema: dict, prompt: str) -> dict:
        cmd = [
            "claude", "-p", "--model", self.model, "--effort", self.effort,
            "--tools", "", "--no-session-persistence", "--setting-sources", "",
            "--output-format", "json", "--system-prompt", system,
            "--json-schema", json.dumps(schema),
        ]
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout,
                           cwd=tempfile.gettempdir())
        try:
            out = json.loads(p.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"claude -p exit {p.returncode}: {(p.stderr or p.stdout)[-300:]}") from None
        if out.get("is_error"):
            raise RuntimeError(f"claude -p error: {str(out.get('result'))[:300]}")
        if out.get("structured_output") is not None:
            return out["structured_output"]
        return json.loads(out["result"])
