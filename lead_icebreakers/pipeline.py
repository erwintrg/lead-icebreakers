"""The run: writer pass -> second reader -> human overrides -> fixed template.

Both model passes send small batches of rows in parallel. Every answer is checked in code
before it can reach a line; a row that fails is retried once on its own, and a row that still
fails is left blank and reported, never guessed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from typing import Callable, Sequence

from . import language, leads, prompts
from .backends import Backend
from .overrides import Overrides
from .template import Change, Draft, check_slots, render

Log = Callable[[str], None]


def chunked(items: Sequence, size: int) -> list[list]:
    if size < 1:
        raise ValueError("batch size must be at least 1")
    return [list(items[k:k + size]) for k in range(0, len(items), size)]


def row_no(i: int) -> int:
    """Spreadsheet row number for row index i (the header is row 1)."""
    return i + 2


@dataclass
class Result:
    backend: str
    written: int = 0
    skipped: int = 0
    reviewed: int = 0  # lines the second reader saw (0 with --no-review)
    failed: dict[int, str] = field(default_factory=dict)  # row index -> reason
    drafts: dict[int, Draft] = field(default_factory=dict)  # the writer's answers, untouched
    final: dict[int, Draft] = field(default_factory=dict)  # what went into the lines
    changes: list[Change] = field(default_factory=list)  # second-reader fixes and overrides

    def report(self) -> str:
        review = sorted(c for c in self.changes if c.stage == "review")
        over = sorted(c for c in self.changes if c.stage == "override")
        if self.reviewed:
            lines = [f"second reader changed {len(review)} of {self.reviewed} lines"]
        else:
            lines = ["second reader: off (--no-review), lines were not checked"]
        lines += [f"- row {c.row}: {c.before} -> {c.after}  ({c.reason})" for c in review]
        if over:
            lines.append(f"overrides changed {len(over)} line{'s' if len(over) != 1 else ''}")
            lines += [f"- row {c.row}: {c.before} -> {c.after}  ({c.reason})" for c in over]
        return "\n".join(lines)


def _short(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:200]


def _calls(n: int) -> str:
    return f"{n} call{'s' if n != 1 else ''}"


def _to_draft(answer: dict | None, row: dict) -> tuple[Draft | None, str | None]:
    """Turn one writer answer into a checked draft; the language comes from code when it can."""
    if not isinstance(answer, dict):
        return None, "row missing from the answer"
    lang, source = language.resolve(row, answer.get("lang"))
    draft = Draft(
        nick=str(answer.get("nick") or "").strip(),
        company=str(answer.get("company") or "").strip(),
        kind=str(answer.get("kind") or ""),
        lang=lang,
        lang_source=source,
    )
    problem = check_slots(draft)
    return (None, problem) if problem else (draft, None)


def _write_batch(backend: Backend, batch: list[tuple[int, dict]]) -> dict[int, dict]:
    payload = [prompts.lead_payload(i, r) for i, r in batch]
    answer = backend(prompts.writer_system(), prompts.WRITER_SCHEMA, prompts.writer_prompt(payload))
    return {item["i"]: item for item in answer["rows"]}


def _review_batch(backend: Backend, batch: list[tuple[int, dict, Draft]]) -> dict[int, dict]:
    payload = [
        {**prompts.lead_payload(i, r), "nick": d.nick, "company": d.company, "kind": d.kind,
         "lang": d.lang, "line": render(d, r)}
        for i, r, d in batch
    ]

    def call() -> dict:
        return backend(prompts.reviewer_system(), prompts.REVIEW_SCHEMA, prompts.reviewer_prompt(payload))

    try:
        answer = call()
    except Exception:
        answer = call()  # one more go before these rows count as failed
    return {item["i"]: item for item in answer["rows"]}


def _writer_pass(todo, backend, workers, batch_size, res: Result, log: Log) -> dict[int, Draft]:
    drafts: dict[int, Draft] = {}

    def run(batches: list[list[tuple[int, dict]]]) -> list[list[tuple[int, dict]]]:
        retry = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_write_batch, backend, b): b for b in batches}
            for fut in as_completed(futures):
                batch = futures[fut]
                try:
                    answers = fut.result()
                except Exception as e:  # the whole call failed: retry its rows one by one
                    log(f"  writer call failed ({_short(e)}); retrying its {len(batch)} rows one by one")
                    for i, r in batch:
                        res.failed[i] = f"writer: {_short(e)}"
                        retry.append([(i, r)])
                    continue
                for i, r in batch:
                    draft, problem = _to_draft(answers.get(i), r)
                    if problem:
                        res.failed[i] = f"writer: {problem}"
                        retry.append([(i, r)])
                    else:
                        drafts[i] = draft
                        res.failed.pop(i, None)
        return retry

    batches = chunked(todo, batch_size)
    log(f"writer pass: {len(todo)} rows in {_calls(len(batches))} of up to {batch_size} rows, "
        f"up to {workers} at a time")
    retry = run(batches)
    if retry:
        log(f"  retrying {len(retry)} rows once, one row per call")
        run(retry)
    return drafts


def _review_pass(rows, drafts, backend, workers, review_batch, res: Result, log: Log) -> None:
    order = [(i, rows[i], drafts[i]) for i in sorted(drafts)]
    batches = chunked(order, review_batch)
    res.reviewed = len(order)
    log(f"review pass: {len(order)} lines in {_calls(len(batches))} of up to {review_batch} lines, "
        f"up to {workers} at a time")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_review_batch, backend, b): b for b in batches}
        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                answers = fut.result()
            except Exception as e:  # no line ships without a second read
                for i, _, _ in batch:
                    res.failed[i] = f"review failed: {_short(e)}"
                continue
            for i, _, draft in batch:
                answer = answers.get(i)
                if not isinstance(answer, dict):
                    res.failed[i] = "review: row missing from the answer"
                    continue
                new = replace(draft, nick=str(answer.get("nick") or "").strip(),
                              company=str(answer.get("company") or "").strip(), kind=str(answer.get("kind") or ""))
                if (new.nick, new.company, new.kind) == (draft.nick, draft.company, draft.kind):
                    continue
                if problem := check_slots(new):
                    log(f"  row {row_no(i)}: reviewer fix rejected ({problem}), writer version kept")
                    continue
                drafts[i] = new
                res.changes.append(Change(row_no(i), "review", draft.label, new.label, answer.get("reason") or ""))


def enrich_rows(
    rows: list[dict],
    backend: Backend,
    *,
    workers: int = 6,
    batch_size: int = 4,
    review: bool = True,
    review_batch: int = 12,
    overwrite: bool = False,
    overrides: Overrides | None = None,
    log: Log = print,
) -> Result:
    """Fill row["Icebreaker"] in place for every row with a first name and a company."""
    res = Result(backend=backend.name)
    todo: list[tuple[int, dict]] = []
    for i, r in enumerate(rows):
        if (r.get(leads.COLUMN) or "").strip() and not overwrite:
            res.skipped += 1
        elif not leads.first_name(r) or not leads.company(r):
            r.setdefault(leads.COLUMN, "")
            res.skipped += 1
            if any(isinstance(v, str) and v.strip() for v in r.values()):
                log(f"  row {row_no(i)}: no first name or company, left blank")
        else:
            todo.append((i, r))
    log(f"backend {backend.name}: {len(todo)} rows to write, {res.skipped} skipped")

    drafts = _writer_pass(todo, backend, workers, batch_size, res, log)
    res.drafts = {i: replace(d) for i, d in drafts.items()}
    if review and drafts:
        _review_pass(rows, drafts, backend, workers, review_batch, res, log)

    for i in sorted(drafts):
        if overrides and i not in res.failed and (change := overrides.apply(drafts[i], rows[i], row_no(i))):
            res.changes.append(change)
    for i, r in todo:
        if i in drafts and i not in res.failed:
            r[leads.COLUMN] = render(drafts[i], r)
            res.final[i] = drafts[i]
        else:
            r[leads.COLUMN] = ""
    res.written = len(res.final)
    res.changes.sort(key=lambda c: (c.row, c.stage != "review"))  # per row: reviewer fix, then override
    for i in sorted(res.failed):
        log(f"  row {row_no(i)} FAILED: {res.failed[i]}")
    return res
