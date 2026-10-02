"""Offline mock backend for the demo and the tests. No network, no key.

It gets exactly what a real model would get (system prompt, JSON schema, prompt text), reads
the rows out of the prompt and answers from fixtures/mock_answers.json, keyed by
company_domain. The canned answers were written by hand; four writer answers contain
deliberate mistakes so the demo shows what the second reader is for.

Rows without a canned answer get a crude rule-based guess, so `--backend mock` runs on any
CSV. That guess is a stand-in for wiring tests, not a model.

Every call is checked for contact data: if an email address, phone number or contact column
ever reaches it, the mock raises.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .. import config, leads, prompts

DEFAULT_ANSWERS = config.FIXTURES / "mock_answers.json"
NICKNAMES = {"nicholas": "Nick", "michael": "Mike", "alexander": "Alex", "maximilian": "Max",
             "christopher": "Chris"}
_LEGAL_TAIL = re.compile(
    r"(\s*,?\s+(gmbh\s*&\s*co\.?\s*kg|gmbh|ag|ug|kg|ltd|llc|inc|corp|plc|b\.?v|s\.?l|s\.?r\.?l|sas|sarl|sa|a/s|ab|aps|oy)\.?)+$",
    re.I,
)


class ContactDataLeak(AssertionError):
    pass


class MockBackend:
    name = "mock"

    def __init__(self, answers_path: Path = DEFAULT_ANSWERS):
        data = json.loads(Path(answers_path).read_text(encoding="utf-8"))
        self.writer_answers: dict = data.get("writer", {})
        self.reviewer_answers: dict = data.get("reviewer", {})
        self.calls: list[tuple[str, int]] = []  # ("writer" | "reviewer", rows in the call)
        self.columns_seen: set[str] = set()
        self._lock = threading.Lock()

    def __call__(self, system: str, schema: dict, prompt: str) -> dict:
        rows = prompts.rows_in(prompt)
        task = "reviewer" if prompts.is_review(schema) else "writer"
        _assert_no_contact_data(rows)
        with self._lock:
            self.calls.append((task, len(rows)))
            for r in rows:
                self.columns_seen.update(r)
        answer = self._review if task == "reviewer" else self._write
        return {"rows": [{"i": r["i"], **answer(r)} for r in rows]}

    @staticmethod
    def _key(row: dict) -> str:
        return (row.get("company_domain") or leads.company(row)).lower()

    def _write(self, row: dict) -> dict:
        return self.writer_answers.get(self._key(row)) or guess(row)

    def _review(self, row: dict) -> dict:
        unchanged = {"nick": row["nick"], "company": row["company"], "kind": row["kind"], "reason": ""}
        return self.reviewer_answers.get(self._key(row)) or unchanged


def _assert_no_contact_data(rows: list[dict]) -> None:
    for r in rows:
        for key, value in r.items():
            if leads.is_contact_column(key) or (isinstance(value, str) and leads.looks_like_contact_value(value)):
                raise ContactDataLeak(f"contact data reached the model: column {key!r}")


def guess(row: dict) -> dict:
    """Crude stand-in for rows without a canned answer. Not what the real model does."""
    first = (leads.first_name(row).split() or [""])[0]
    nick = NICKNAMES.get(first.lower()) or (first.capitalize() if first.isupper() else first)
    name = re.split(r"\s+\|\s+|\s+-\s+", leads.company(row))[0]
    word = (_LEGAL_TAIL.sub("", name).split() or [""])[0]
    if word.isupper() and len(word) > 4:
        word = word.capitalize()
    lang = row.get("lang_hint") if row.get("lang_hint") in ("de", "en") else "en"
    return {"nick": nick, "company": word, "kind": "brand", "lang": lang}
