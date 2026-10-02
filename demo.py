#!/usr/bin/env python3
"""Offline demo: 12 fictional leads -> icebreakers, using the mock backend. No key, no network.

The pipeline is the real one (payload, contact stripping, batching, parallel calls, checks,
second reader, overrides, template). Only the model is replaced by canned answers from
fixtures/mock_answers.json.
"""
from __future__ import annotations

import sys

from lead_icebreakers import config
from lead_icebreakers.backends.mock import MockBackend
from lead_icebreakers.csvio import read_csv, write_csv
from lead_icebreakers.leads import COLUMN
from lead_icebreakers.overrides import Overrides
from lead_icebreakers.pipeline import enrich_rows, row_no

SAMPLE = config.FIXTURES / "sample_leads.csv"
OUT = config.OUT_DIR / "sample_leads-icebreakers.csv"
LANG_SOURCE = {"country": "by country", "city": "by Swiss city", "model": "model decided",
               "default": "no country"}


def cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def rel(path) -> str:
    return str(path.relative_to(config.ROOT))


def main() -> int:
    header, rows = read_csv(SAMPLE)
    source = [dict(r) for r in rows]  # untouched copy for the "before" column
    mock = MockBackend()
    overrides = Overrides.load(config.OVERRIDES_EXAMPLE)

    print("lead-icebreakers demo: offline, mock backend, no API key\n")
    print(f"input      {rel(SAMPLE)}  ({len(rows)} fictional leads, {len(header)} columns)")
    print(f"overrides  {rel(config.OVERRIDES_EXAMPLE)}  ({len(overrides)} human rulings)\n")
    res = enrich_rows(rows, mock, overrides=overrides, log=lambda m: print("  " + m.strip()))

    print("\nBefore -> after  (row = spreadsheet row, the header is row 1)\n")
    print(f"{'row':>3}  {'first_name':<12} {'company_name':<32}  {'nick':<9} {'company words':<31} language")
    for i in sorted(res.final):
        d, s = res.final[i], source[i]
        lang = f"{d.lang}, {LANG_SOURCE.get(d.lang_source, d.lang_source)}"
        print(f"{row_no(i):>3}  {cut(s['first_name'], 12):<12} {cut(s['company_name'], 32):<32}"
              f"  {d.nick:<9} {cut(d.company, 31):<31} {lang}")

    review = [c for c in res.changes if c.stage == "review"]
    over = [c for c in res.changes if c.stage == "override"]
    print(f"\nSecond reader changed {len(review)} of {res.reviewed} lines")
    for c in review:
        print(f"  row {c.row:<3} {c.before}  ->  {c.after}\n          {c.reason}")
    print(f"\nHuman overrides changed {len(over)} line{'s' if len(over) != 1 else ''} (applied after both model passes)")
    for c in over:
        print(f"  row {c.row:<3} {c.before}  ->  {c.after}\n          {c.reason}")

    print("\nFinished lines")
    for i in sorted(res.final):
        print(f"  row {row_no(i):<3} {rows[i][COLUMN]}")

    sent = [c for c in header if c in mock.columns_seen]
    never = [c for c in header if c not in mock.columns_seen]
    writer = [n for task, n in mock.calls if task == "writer"]
    reviewer = [n for task, n in mock.calls if task == "reviewer"]
    print("\nWhat the model saw")
    print(f"  columns  {', '.join(sent)} (+ lang_hint)")
    print(f"  never    {', '.join(never)}  (the mock raises if contact data reaches it)")
    print(f"  calls    {len(writer)} writer calls of {'/'.join(map(str, writer))} rows run in parallel, "
          f"{len(reviewer)} reviewer call{'s' if len(reviewer) != 1 else ''} of {'/'.join(map(str, reviewer))} lines")

    write_csv(OUT, header, rows)
    print(f"\nwrote {rel(OUT)}  ({res.written} written, {res.skipped} skipped, {len(res.failed)} failed; "
          f"all {len(header)} input columns kept)")
    return 1 if res.failed else 0


if __name__ == "__main__":
    sys.exit(main())
