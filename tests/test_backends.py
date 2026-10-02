"""Backends without network: the API backend with a fake client, the CLI backend with a fake
subprocess, and the mock."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from lead_icebreakers import prompts
from lead_icebreakers.backends import get_backend
from lead_icebreakers.backends.anthropic_api import AnthropicBackend
from lead_icebreakers.backends.claude_cli import ClaudeCLIBackend
from lead_icebreakers.backends.mock import ContactDataLeak, MockBackend, guess


class FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def api_response(stop_reason="end_turn", text='{"rows": []}', category=None):
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    details = SimpleNamespace(category=category) if stop_reason == "refusal" else None
    return SimpleNamespace(stop_reason=stop_reason, stop_details=details, content=content, _request_id="req_test")


def test_api_backend_asks_for_schema_json_and_parses_the_text_block():
    messages = FakeMessages(api_response(text='{"rows": [{"i": 0}]}'))
    backend = AnthropicBackend(model="model-x", effort="low", client=SimpleNamespace(messages=messages))
    assert backend("system text", prompts.WRITER_SCHEMA, "prompt text") == {"rows": [{"i": 0}]}
    sent = messages.kwargs
    assert sent["model"] == "model-x" and sent["system"] == "system text"
    assert sent["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": prompts.WRITER_SCHEMA}}
    assert sent["messages"] == [{"role": "user", "content": "prompt text"}]


@pytest.mark.parametrize("stop_reason, message", [("refusal", "declined"), ("max_tokens", "cut off")])
def test_api_backend_raises_instead_of_reading_a_bad_answer(stop_reason, message):
    client = SimpleNamespace(messages=FakeMessages(api_response(stop_reason=stop_reason, text="")))
    with pytest.raises(RuntimeError, match=message):
        AnthropicBackend(client=client)("s", prompts.WRITER_SCHEMA, "p")


def test_cli_backend_command_and_structured_output(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["input"] = cmd, kwargs["input"]
        out = {"is_error": False, "result": "", "structured_output": {"rows": [{"i": 0}]}}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    answer = ClaudeCLIBackend(model="model-x", effort="low")("system text", prompts.REVIEW_SCHEMA, "prompt text")
    assert answer == {"rows": [{"i": 0}]}
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude", "-p"] and seen["input"] == "prompt text"
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--system-prompt") + 1] == "system text"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == prompts.REVIEW_SCHEMA
    assert "--no-session-persistence" in cmd


def test_cli_backend_reports_errors(monkeypatch):
    out = json.dumps({"is_error": True, "result": "not logged in"})
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, stdout=out, stderr=""))
    with pytest.raises(RuntimeError, match="not logged in"):
        ClaudeCLIBackend()("s", prompts.WRITER_SCHEMA, "p")


def test_auto_never_picks_the_mock(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(SystemExit, match="demo.py"):
        get_backend("auto")


def test_mock_raises_on_contact_data():
    prompt = prompts.writer_prompt([{"i": 0, "first_name": "Jane", "email": "jane@example.example"}])
    with pytest.raises(ContactDataLeak):
        MockBackend()("s", prompts.WRITER_SCHEMA, prompt)


def test_mock_guess_for_rows_without_a_canned_answer():
    assert guess({"first_name": "NICHOLAS", "company_name": "Quillmark Labs GmbH", "lang_hint": "de"}) == \
        {"nick": "Nick", "company": "Quillmark", "kind": "brand", "lang": "de"}
    assert guess({"first_name": "ZOË", "company_name": "VANTORO Ltd", "lang_hint": "decide: ..."})["nick"] == "Zoë"
