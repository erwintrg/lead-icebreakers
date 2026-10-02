"""Anthropic API backend. Structured JSON output, so every answer parses against the schema."""
from __future__ import annotations

import json

from .. import config


class AnthropicBackend:
    def __init__(self, model: str | None = None, effort: str | None = None, max_tokens: int = 16000,
                 client=None):
        if client is None:
            try:
                import anthropic
            except ImportError as e:
                raise SystemExit("The api backend needs the SDK: pip install -r requirements.txt") from e
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY; retries 429 and 5xx itself
        self.client = client
        self.model = model or config.model()
        self.effort = effort or config.effort()
        self.max_tokens = max_tokens
        self.name = f"api:{self.model}"

    def __call__(self, system: str, schema: dict, prompt: str) -> dict:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            category = resp.stop_details.category if resp.stop_details else None
            raise RuntimeError(f"model declined (category {category}, request {resp._request_id})")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError(f"answer cut off at max_tokens (request {resp._request_id})")
        text = next((block.text for block in resp.content if block.type == "text"), None)
        if text is None:
            raise RuntimeError(f"no text block in the answer (request {resp._request_id})")
        return json.loads(text)
