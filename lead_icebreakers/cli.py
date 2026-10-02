"""Command line.

    python icebreakers.py leads.csv [options]          CSV in -> leads-icebreakers.csv out
    python icebreakers.py reapply finished.csv         overrides only, no model calls
    python icebreakers.py drive --list | --file-id ID  optional Google Drive hand-off
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .backends import get_backend
from .csvio import read_csv, write_csv
from .overrides import Overrides, reapply
from .pipeline import enrich_rows


def _overrides(path: Path | None) -> Overrides:
    table = Overrides.load(path if path is not None else config.OVERRIDES_FILE)
    if len(table):
        print(f"overrides: {len(table)} rulings from {table.source}")
    return table


def run_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="icebreakers.py", description="Add an Icebreaker column to a lead CSV.")
    ap.add_argument("csv", type=Path, help="lead list with at least a first-name and a company column")
    ap.add_argument("-o", "--out", type=Path, help="default: <input>-icebreakers.csv")
    ap.add_argument("--backend", choices=("auto", "api", "cli", "mock"), default="auto",
                    help="auto = api if ANTHROPIC_API_KEY is set, else the claude CLI")
    ap.add_argument("--workers", type=int, default=6, help="parallel model calls (default 6)")
    ap.add_argument("--batch-size", type=int, default=4, help="rows per writer call (default 4)")
    ap.add_argument("--review-batch", type=int, default=12, help="lines per reviewer call (default 12)")
    ap.add_argument("--limit", type=int, help="only the first N rows (quick test)")
    ap.add_argument("--overwrite", action="store_true", help="rewrite rows that already have an icebreaker")
    ap.add_argument("--no-review", action="store_true", help="skip the second reader (quick tests only)")
    ap.add_argument("--overrides", type=Path, help=f"human rulings CSV (default: {config.OVERRIDES_FILE.name} if present)")
    a = ap.parse_args(argv)

    header, rows = read_csv(a.csv)
    if a.limit:
        rows = rows[: a.limit]
    backend = get_backend(a.backend)
    res = enrich_rows(rows, backend, workers=a.workers, batch_size=a.batch_size, review=not a.no_review,
                      review_batch=a.review_batch, overwrite=a.overwrite, overrides=_overrides(a.overrides))
    out = a.out or a.csv.with_name(f"{a.csv.stem}-icebreakers.csv")
    write_csv(out, header, rows)
    print(res.report())
    print(f"wrote {out}  ({res.written} written, {res.skipped} skipped, {len(res.failed)} failed)")
    return 1 if res.failed else 0


def reapply_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="icebreakers.py reapply",
                                 description="Apply the overrides CSV to an enriched CSV. No model calls.")
    ap.add_argument("csv", type=Path, help="a CSV that already has an Icebreaker column")
    ap.add_argument("-o", "--out", type=Path, help="default: <input>-reapplied.csv")
    ap.add_argument("--in-place", action="store_true", help="overwrite the input file")
    ap.add_argument("--overrides", type=Path, help=f"default: {config.OVERRIDES_FILE.name}")
    a = ap.parse_args(argv)

    header, rows = read_csv(a.csv)
    table = _overrides(a.overrides)
    if not len(table):
        raise SystemExit("No overrides found. Create config/overrides.csv (see config/overrides.example.csv).")
    changes = reapply(rows, table)
    out = a.csv if a.in_place else (a.out or a.csv.with_name(f"{a.csv.stem}-reapplied.csv"))
    write_csv(out, header, rows)
    print(f"{len(changes)} lines changed by overrides, every other line untouched\nwrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config.load_env()
    if argv[:1] == ["drive"]:
        from .drive import main as drive_main

        return drive_main(argv[1:])
    if argv[:1] == ["reapply"]:
        return reapply_main(argv[1:])
    return run_main(argv)
