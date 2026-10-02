"""CSV in and out. Every input column is kept, contact columns included; the Icebreaker column
is added at the end when the file does not have one yet."""
from __future__ import annotations

import csv
from pathlib import Path

from .leads import COLUMN


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    if COLUMN not in header:
        header = [*header, COLUMN]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
