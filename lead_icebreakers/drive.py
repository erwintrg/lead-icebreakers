"""Optional Google Drive hand-off (real mode only): folder 1 -> enriched Sheet in folder 2.

For each lead list waiting in folder 1 ("to enrich"):
  1. read it (a Google Sheet, or a CSV file picked with --file-id)
  2. write icebreakers with the same pipeline as the CSV command
  3. create a NEW Google Sheet in folder 2: "<date> <list name> ENRICHED-<n>". It is created
     there, never moved there: n8n's Drive trigger fires on a file's createdTime, so a moved
     file would never start the notify workflow in n8n/
  4. read it back, then move the source to the Drive trash (restorable for 30 days), along
     with any other file in folder 1 whose leads are already enriched (a CSV twin of a Sheet)
A local copy and the change report land in out/enriched/.

If any row fails, nothing is uploaded and the source stays in folder 1 (--allow-partial ships
with blank lines instead).

Env (.env): GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN (Drive + Sheets
scopes), DRIVE_FOLDER_TO_ENRICH, DRIVE_FOLDER_ENRICHED, optional GOOGLE_EXPECTED_ACCOUNT
(refuse any other Google account) and ICEBREAKERS_TZ (date in the title, default UTC).
Needs: pip install -r requirements-drive.txt
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import config
from .backends import Backend, get_backend
from .csvio import write_csv
from .leads import COLUMN, pick
from .overrides import Overrides, reapply
from .pipeline import Result, enrich_rows

SHEET = "application/vnd.google-apps.spreadsheet"
LOCAL_DIR = config.OUT_DIR / "enriched"
EMAIL_COLS = ("email", "Email", "E-Mail", "work_email", "email_combined")
Log = Callable[[str], None]


@dataclass(frozen=True)
class Folders:
    to_enrich: str
    enriched: str

    @classmethod
    def from_env(cls) -> Folders:
        a = os.environ.get("DRIVE_FOLDER_TO_ENRICH", "")
        b = os.environ.get("DRIVE_FOLDER_ENRICHED", "")
        if not a or not b or a.startswith("your-") or b.startswith("your-"):
            raise SystemExit("Set DRIVE_FOLDER_TO_ENRICH and DRIVE_FOLDER_ENRICHED in .env (see .env.example).")
        return cls(a, b)


@dataclass
class Options:
    dry_run: bool = False
    keep_source: bool = False
    allow_partial: bool = False
    workers: int = 6
    batch_size: int = 4


def check_account(actual: str, expected: str) -> None:
    if expected and actual.lower() != expected.lower():
        raise SystemExit(f"Refusing: the Google token belongs to {actual}; this flow runs as {expected} only.")


def connect():
    """Drive and Sheets clients from the refresh token in .env, after the account check."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        raise SystemExit("The Drive hand-off needs: pip install -r requirements-drive.txt") from e
    missing = [k for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing in .env: {', '.join(missing)}")
    creds = Credentials(
        None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    who = drive.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]
    check_account(who, os.environ.get("GOOGLE_EXPECTED_ACCOUNT", ""))
    return drive, build("sheets", "v4", credentials=creds, cache_discovery=False)


def today() -> date:
    return datetime.now(ZoneInfo(os.environ.get("ICEBREAKERS_TZ") or "UTC")).date()


def output_title(source_name: str, n: int, day: date) -> str:
    """'2026-01-05 example-list KEEP-68' -> '<day> example-list ENRICHED-68'."""
    name = re.sub(r"\.csv$", "", source_name, flags=re.I)
    name = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", name)
    name = re.sub(r"[\s_-]+KEEP-\d+$", "", name, flags=re.I).strip()
    return f"{day.isoformat()} {name} ENRICHED-{n}"


def col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def waiting(drive, folder: str) -> list[dict]:
    q = f"'{folder}' in parents and trashed = false"
    return drive.files().list(q=q, fields="files(id,name,mimeType,createdTime)", orderBy="createdTime").execute()["files"]


def read_source(drive, sheets, meta: dict) -> tuple[list[str], list[dict]]:
    if meta["mimeType"] == SHEET:
        values = sheets.spreadsheets().values().get(spreadsheetId=meta["id"], range="A:ZZ").execute().get("values", [])
        if not values:
            return [], []
        header, body = values[0], values[1:]
        rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in body if any(c.strip() for c in r)]
        return header, rows
    from googleapiclient.http import MediaIoBaseDownload

    buf = io.BytesIO()
    download = MediaIoBaseDownload(buf, drive.files().get_media(fileId=meta["id"]))
    done = False
    while not done:
        _, done = download.next_chunk()
    reader = csv.DictReader(io.StringIO(buf.getvalue().decode("utf-8-sig")))
    return list(reader.fieldnames or []), list(reader)


def create_sheet(drive, sheets, folder: str, title: str, header: list[str], rows: list[dict]) -> dict:
    meta = drive.files().create(
        body={"name": title, "mimeType": SHEET, "parents": [folder]}, fields="id,name,webViewLink"
    ).execute()
    values = [header] + [[r.get(h, "") for h in header] for r in rows]
    tab = sheets.spreadsheets().get(spreadsheetId=meta["id"], fields="sheets.properties").execute()
    sheet_id = tab["sheets"][0]["properties"]["sheetId"]
    sheets.spreadsheets().batchUpdate(spreadsheetId=meta["id"], body={"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "title": "leads", "gridProperties": {
                "rowCount": max(len(values), 2), "columnCount": len(header), "frozenRowCount": 1}},
            "fields": "title,gridProperties(rowCount,columnCount,frozenRowCount)",
        }}]}).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=meta["id"], range="leads!A1", valueInputOption="RAW", body={"values": values}
    ).execute()
    back = sheets.spreadsheets().values().get(spreadsheetId=meta["id"], range="leads!A:A").execute().get("values", [])
    if len(back) != len(values):
        raise SystemExit(f"Read-back mismatch: wrote {len(values)} rows, found {len(back)}. Source left in folder 1.")
    return meta


def emails(rows: list[dict]) -> set[str]:
    """Used locally to spot duplicates. Never sent to the model."""
    return {pick(r, EMAIL_COLS).lower() for r in rows if pick(r, EMAIL_COLS)}


def trash_copies(drive, sheets, folders: Folders, enriched: set[str], log: Log = print) -> None:
    """Folder 2 loaded means folder 1 cleared: trash any file in folder 1 whose leads (by email)
    are at least 90% enriched already, e.g. the raw CSV twin of a Sheet."""
    for f in waiting(drive, folders.to_enrich):
        found = emails(read_source(drive, sheets, f)[1])
        if found and len(found & enriched) >= 0.9 * len(found):
            drive.files().update(fileId=f["id"], body={"trashed": True}).execute()
            log(f"   copy of an enriched list trashed from folder 1: {f['name']} "
                f"({len(found & enriched)}/{len(found)} leads already in folder 2)")


def save_local(local_dir: Path, title: str, header: list[str], rows: list[dict], report: str, log: Log) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    write_csv(local_dir / f"{title}.csv", header, rows)
    (local_dir / f"{title}.review.txt").write_text(report + "\n", encoding="utf-8")
    log(f"   local copy: {local_dir / title}.csv\n   " + report.replace("\n", "\n   "))


def process(drive, sheets, meta: dict, folders: Folders, backend: Backend, overrides: Overrides,
            opts: Options, local_dir: Path = LOCAL_DIR, day: date | None = None, log: Log = print) -> str | None:
    """One list end to end. Returns the new Sheet's id, or None on a dry run or a skip."""
    log(f"\n== {meta['name']}  ({meta['id']})")
    if "ENRICHED" in meta["name"].upper():
        log("   already an ENRICHED list, skipped")
        return None
    header, rows = read_source(drive, sheets, meta)
    res: Result = enrich_rows(rows, backend, workers=opts.workers, batch_size=opts.batch_size,
                              overrides=overrides, log=log)
    if COLUMN not in header:
        header = [*header, COLUMN]
    filled = sum(1 for r in rows if (r.get(COLUMN) or "").strip())
    title = output_title(meta["name"], filled, day or today())
    save_local(local_dir, title, header, rows, res.report(), log)

    if res.failed and not opts.allow_partial:
        raise SystemExit(f"   {len(res.failed)} rows failed; nothing uploaded, the source stays in folder 1. "
                         "Re-run, or pass --allow-partial to ship with blank lines.")
    if opts.dry_run:
        log("   dry run: Drive untouched")
        return None

    out = create_sheet(drive, sheets, folders.enriched, title, header, rows)
    log(f"   created in folder 2: {out['name']}\n   {out.get('webViewLink', '')}")
    if opts.keep_source:
        log("   source kept in folder 1 (--keep-source)")
        return out["id"]
    parents = drive.files().get(fileId=meta["id"], fields="parents").execute().get("parents", [])
    if folders.to_enrich in parents:
        drive.files().update(fileId=meta["id"], body={"trashed": True}).execute()
        log("   source moved to the Drive trash (restorable for 30 days)")
    trash_copies(drive, sheets, folders, emails(rows), log)
    return out["id"]


def sweep(drive, sheets, folders: Folders, log: Log = print) -> None:
    """Check every file in folder 1 against every Sheet in folder 2."""
    q = f"'{folders.enriched}' in parents and trashed = false and mimeType = '{SHEET}'"
    enriched: set[str] = set()
    for f in drive.files().list(q=q, fields="files(id,name,mimeType)").execute()["files"]:
        enriched |= emails(read_source(drive, sheets, f)[1])
    log(f"{len(enriched)} leads in folder 2")
    trash_copies(drive, sheets, folders, enriched, log)


def redo(drive, sheets, file_id: str, folders: Folders, opts: Options, overrides: Overrides,
         backend: Backend | None, overrides_only: bool, local_dir: Path = LOCAL_DIR, log: Log = print) -> None:
    """Rewrite the Icebreaker column of a Sheet already in folder 2, in place: same file, same
    link, no new notify mail. With overrides_only, no model call and every other line stays."""
    meta = drive.files().get(fileId=file_id, fields="id,name,mimeType,parents,webViewLink").execute()
    if meta["mimeType"] != SHEET or folders.enriched not in meta.get("parents", []):
        raise SystemExit("--redo takes a Google Sheet that sits in folder 2.")
    log(f"\n== redo {meta['name']}  ({file_id})")
    tab = sheets.spreadsheets().get(spreadsheetId=file_id, fields="sheets.properties").execute()
    tab_title = tab["sheets"][0]["properties"]["title"]
    values = sheets.spreadsheets().values().get(spreadsheetId=file_id, range=f"'{tab_title}'").execute()["values"]
    header = values[0]
    if COLUMN not in header:
        raise SystemExit(f"No {COLUMN} column in {meta['name']}.")
    rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in values[1:]]  # keep blank rows
    if overrides_only:
        changes = reapply(rows, overrides, log)
        report, done, failed = f"{len(changes)} lines changed by overrides", len(changes), {}
    else:
        assert backend is not None
        res = enrich_rows(rows, backend, workers=opts.workers, batch_size=opts.batch_size,
                          overwrite=True, overrides=overrides, log=log)
        report, done, failed = res.report(), res.written, res.failed
    if failed and not opts.allow_partial:
        raise SystemExit(f"   {len(failed)} rows failed; Sheet left unchanged. Re-run, or --allow-partial.")
    save_local(local_dir, meta["name"], header, rows, report, log)
    if opts.dry_run:
        log("   dry run: local copy only")
        return
    col = col_letter(header.index(COLUMN))
    sheets.spreadsheets().values().update(
        spreadsheetId=file_id, range=f"'{tab_title}'!{col}1", valueInputOption="RAW",
        body={"values": [[COLUMN]] + [[r.get(COLUMN, "")] for r in rows]},
    ).execute()
    log(f"   {done} icebreakers rewritten in column {col}\n   {meta.get('webViewLink', '')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="icebreakers.py drive", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="show what is waiting in folder 1")
    g.add_argument("--file-id", help="one Sheet or CSV in folder 1")
    g.add_argument("--all", action="store_true", help="every Google Sheet in folder 1 (CSV files only via --file-id)")
    g.add_argument("--redo", metavar="FILE_ID", help="rewrite the icebreakers of a Sheet in folder 2, in place")
    g.add_argument("--sweep", action="store_true", help="trash files in folder 1 whose leads are already in folder 2")
    ap.add_argument("--dry-run", action="store_true", help="write the local copy only, Drive untouched")
    ap.add_argument("--overrides-only", action="store_true", help="with --redo: apply overrides, no model calls")
    ap.add_argument("--keep-source", action="store_true", help="leave the source in folder 1")
    ap.add_argument("--allow-partial", action="store_true", help="upload even if some rows failed")
    ap.add_argument("--backend", choices=("auto", "api", "cli"), default="auto")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--overrides", type=Path, default=config.OVERRIDES_FILE)
    a = ap.parse_args(argv)
    if a.overrides_only and not a.redo:
        ap.error("--overrides-only only works with --redo")

    config.load_env()
    folders = Folders.from_env()
    drive, sheets = connect()
    opts = Options(a.dry_run, a.keep_source, a.allow_partial, a.workers, a.batch_size)
    overrides = Overrides.load(a.overrides)

    if a.redo:
        backend = None if a.overrides_only else get_backend(a.backend)
        redo(drive, sheets, a.redo, folders, opts, overrides, backend, a.overrides_only)
        return 0
    if a.sweep:
        sweep(drive, sheets, folders)
        return 0
    files = waiting(drive, folders.to_enrich)
    if a.list:
        for f in files:
            print(f"{f['id']}  {f['mimeType'].split('.')[-1]:<12} {f['name']}")
        return 0
    if a.file_id:
        todo = [f for f in files if f["id"] == a.file_id]
        if not todo:
            raise SystemExit(f"{a.file_id} is not in folder 1.")
    else:
        todo = [f for f in files if f["mimeType"] == SHEET]
        for f in files:
            if f["mimeType"] != SHEET:
                print(f"skipping non-Sheet {f['name']} (run it with --file-id if it is a separate list)")
    backend = get_backend(a.backend)
    for meta in todo:
        process(drive, sheets, meta, folders, backend, overrides, opts)
    return 0
