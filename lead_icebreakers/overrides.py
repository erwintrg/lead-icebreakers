"""Human rulings per company. They beat both model passes, on every run, for every future list.

The CSV has one row per company: match (a domain or a company name), company (the words to
use), company_de (the German phrase, needed only for generic rulings), kind (brand or
generic) and note (why, shown in the change report).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import leads
from .template import Change, Draft, parse_line, render


def normalize_domain(value: str) -> str:
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value.strip().lower())
    v = re.split(r"[/?#]", v, maxsplit=1)[0]
    return re.sub(r"^www\.", "", v).rstrip(".")


def normalize_name(value: str) -> str:
    return " ".join(value.lower().split())


def _key(match: str) -> str:
    looks_like_domain = "." in match and " " not in match.strip()
    return normalize_domain(match) if looks_like_domain else normalize_name(match)


@dataclass(frozen=True)
class Override:
    company: str
    company_de: str
    kind: str
    note: str


class Overrides:
    def __init__(self, table: dict[str, Override] | None = None, source: str = ""):
        self.table = table or {}
        self.source = source

    def __len__(self) -> int:
        return len(self.table)

    @classmethod
    def load(cls, path: Path | None) -> Overrides:
        """Read an overrides CSV. A missing file means no overrides; a malformed row is an error."""
        if path is None or not path.exists():
            return cls()
        table = {}
        with path.open(newline="", encoding="utf-8-sig") as f:
            for line_no, r in enumerate(csv.DictReader(f), start=2):
                match = (r.get("match") or "").strip()
                if not match:
                    continue
                kind = (r.get("kind") or "").strip().lower()
                company = (r.get("company") or "").strip()
                if kind not in ("brand", "generic"):
                    raise ValueError(f"{path} line {line_no}: kind must be brand or generic")
                if not company:
                    raise ValueError(f"{path} line {line_no}: company is empty")
                table[_key(match)] = Override(company, (r.get("company_de") or "").strip(), kind,
                                              (r.get("note") or "").strip())
        return cls(table, str(path))

    def find(self, row: dict) -> Override | None:
        """Match by domain first, then by company name."""
        domain = normalize_domain(leads.pick(row, leads.DOMAIN_COLS))
        if domain and domain in self.table:
            return self.table[domain]
        name = normalize_name(leads.company(row))
        return self.table.get(name) if name else None

    def apply(self, draft: Draft, row: dict, row_no: int) -> Change | None:
        """Swap in the human's words. Returns the change, or None when nothing changed."""
        o = self.find(row)
        if o is None:
            return None
        words = o.company
        if draft.lang == "de" and o.kind == "generic":
            if not o.company_de:
                return None  # no German phrase given for this ruling: keep the model's words
            words = o.company_de
        if (draft.company, draft.kind) == (words, o.kind):
            return None
        before = draft.label
        draft.company, draft.kind = words, o.kind
        return Change(row_no, "override", before, draft.label, o.note or "override")


def reapply(rows: list[dict], overrides: Overrides, log: Callable[[str], None] = print) -> list[Change]:
    """Apply overrides to lines that are already finished. No model call; other lines untouched."""
    changes = []
    for i, row in enumerate(rows):
        draft = parse_line(row.get(leads.COLUMN) or "")
        if draft is None:
            continue
        change = overrides.apply(draft, row, i + 2)
        if change:
            row[leads.COLUMN] = render(draft, row)
            changes.append(change)
            log(f"  row {change.row}: {change.before} -> {change.after} (override)")
    return changes
