"""Shared test doubles. Every lead here is fictional."""
from __future__ import annotations

import threading

import pytest

from lead_icebreakers import prompts


def simple_writer(lead: dict) -> dict:
    """First word of the company as a brand; language from the hint."""
    lang = lead["lang_hint"] if lead["lang_hint"] in ("de", "en") else "en"
    return {"nick": lead["first_name"], "company": lead["company_name"].split()[0], "kind": "brand", "lang": lang}


class FakeBackend:
    """Answers through plain functions and records every prompt it was sent."""

    name = "fake"

    def __init__(self, writer=simple_writer, reviewer=None, fail_writer_calls=0, fail_reviewer_calls=0,
                 barrier: threading.Barrier | None = None):
        self.writer = writer
        self.reviewer = reviewer or (lambda row: None)  # None = leave the row unchanged
        self.fail_writer_calls = fail_writer_calls
        self.fail_reviewer_calls = fail_reviewer_calls
        self.barrier = barrier
        self.prompts: list[str] = []
        self.calls: list[tuple[str, int]] = []
        self._lock = threading.Lock()

    def __call__(self, system: str, schema: dict, prompt: str) -> dict:
        rows = prompts.rows_in(prompt)
        task = "reviewer" if prompts.is_review(schema) else "writer"
        with self._lock:
            self.prompts.append(prompt)
            self.calls.append((task, len(rows)))
            fail = False
            if task == "writer" and self.fail_writer_calls > 0:
                self.fail_writer_calls, fail = self.fail_writer_calls - 1, True
            if task == "reviewer" and self.fail_reviewer_calls > 0:
                self.fail_reviewer_calls, fail = self.fail_reviewer_calls - 1, True
        if self.barrier is not None and task == "writer":
            self.barrier.wait()  # only passes when enough calls run at the same time
        if fail:
            raise TimeoutError("simulated timeout")
        if task == "writer":
            return {"rows": [{"i": r["i"], **self.writer(r)} for r in rows]}
        out = []
        for r in rows:
            unchanged = {"nick": r["nick"], "company": r["company"], "kind": r["kind"], "reason": ""}
            out.append({"i": r["i"], **unchanged, **(self.reviewer(r) or {})})
        return {"rows": out}

    def count(self, task: str) -> int:
        return sum(1 for t, _ in self.calls if t == task)


def make_rows(n: int, **extra) -> list[dict]:
    return [
        {
            "first_name": f"Person{k}",
            "last_name": "Example",
            "company_name": f"Company{k} Ltd",
            "company_domain": f"company{k}.example",
            "country": "United Kingdom",
            "email": f"person{k}@company{k}.example",
            "phone": "+44 20 0000 0000",
            "linkedin_url": f"https://linkedin.example/in/person{k}",
            **extra,
        }
        for k in range(n)
    ]


@pytest.fixture
def quiet():
    return lambda *_: None
