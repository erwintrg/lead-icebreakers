"""The Drive hand-off against an in-memory fake of the Drive and Sheets APIs."""
import re
from datetime import date

import pytest

from lead_icebreakers import drive as hand_off
from lead_icebreakers.drive import Folders, Options, col_letter, output_title
from lead_icebreakers.overrides import Overrides
from lead_icebreakers.template import Draft, render

from conftest import FakeBackend, make_rows

FOLDERS = Folders(to_enrich="folder-1", enriched="folder-2")
DAY = date(2026, 1, 6)
COLS = ["first_name", "last_name", "company_name", "company_domain", "country", "email"]


class Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeGoogle:
    """Just enough of drive.files() and sheets.spreadsheets() for the hand-off."""

    def __init__(self):
        self.files_store: dict[str, dict] = {}
        self.grids: dict[str, list[list[str]]] = {}
        self.tabs: dict[str, str] = {}
        self.n = 0

    # Drive
    def files(self):
        return self

    def list(self, q, fields=None, orderBy=None):
        folder = re.search(r"'([^']+)' in parents", q).group(1)
        mime = re.search(r"mimeType = '([^']+)'", q)
        return Call(lambda: {"files": [dict(m) for m in self.files_store.values()
                                       if folder in m["parents"] and not m["trashed"]
                                       and (not mime or m["mimeType"] == mime.group(1))]})

    def get(self, fileId, fields=None):
        return Call(lambda: dict(self.files_store[fileId]))

    def create(self, body, fields=None):
        def run():
            self.n += 1
            return dict(self.add(f"new-{self.n}", body["name"], body["parents"][0], []))
        return Call(run)

    def update(self, fileId, body):
        return Call(lambda: self.files_store[fileId].update(body))

    # Sheets
    def spreadsheets(self):
        return FakeSpreadsheets(self)

    def add(self, file_id, name, folder, grid, tab="Sheet1"):
        self.files_store[file_id] = {"id": file_id, "name": name, "mimeType": hand_off.SHEET, "parents": [folder],
                                     "trashed": False, "webViewLink": f"https://sheets.example/{file_id}"}
        self.grids[file_id], self.tabs[file_id] = [list(r) for r in grid], tab
        return self.files_store[file_id]


class FakeSpreadsheets:
    def __init__(self, g):
        self.g = g

    def values(self):
        return self

    def get(self, spreadsheetId, range=None, fields=None):
        if fields:  # spreadsheets().get(...): tab properties
            return Call(lambda: {"sheets": [{"properties": {"sheetId": 0, "title": self.g.tabs[spreadsheetId]}}]})
        grid = self.g.grids[spreadsheetId]
        if range.endswith("!A:A"):
            return Call(lambda: {"values": [[r[0]] for r in grid if r]})
        return Call(lambda: {"values": [list(r) for r in grid]})

    def batchUpdate(self, spreadsheetId, body):
        props = body["requests"][0]["updateSheetProperties"]["properties"]
        return Call(lambda: self.g.tabs.__setitem__(spreadsheetId, props["title"]))

    def update(self, spreadsheetId, range, valueInputOption, body):
        col_letters, row = re.search(r"!([A-Z]+)(\d+)$", range).groups()
        col = sum((ord(c) - 64) * 26 ** k for k, c in enumerate(reversed(col_letters))) - 1

        def run():
            grid = self.g.grids[spreadsheetId]
            for r_off, values in enumerate(body["values"]):
                ri = int(row) - 1 + r_off
                while len(grid) <= ri:
                    grid.append([])
                for c_off, v in enumerate(values):
                    while len(grid[ri]) <= col + c_off:
                        grid[ri].append("")
                    grid[ri][col + c_off] = v
        return Call(run)


def lead_grid(n: int) -> list[list[str]]:
    return [COLS] + [[r[c] for c in COLS] for r in make_rows(n)]


@pytest.fixture
def google():
    g = FakeGoogle()
    g.add("src", "2026-01-05 example-list KEEP-3", "folder-1", lead_grid(3))
    g.add("twin", "example-list raw copy", "folder-1", lead_grid(3))  # same leads, another file
    g.add("other", "another list", "folder-1", lead_grid(0) + [["Zed", "Other", "Zed Co", "zed.example", "UK", "zed@zed.example"]])
    return g


def run(google, tmp_path, backend=None, **opts):
    return hand_off.process(google, google, dict(google.files_store["src"]), FOLDERS, backend or FakeBackend(),
                            Overrides(), Options(**opts), local_dir=tmp_path, day=DAY, log=lambda *_: None)


def test_output_title():
    assert output_title("2026-01-05 example-list KEEP-68", 68, DAY) == "2026-01-06 example-list ENRICHED-68"
    assert output_title("example_list_KEEP-7.csv", 7, DAY) == "2026-01-06 example_list ENRICHED-7"


def test_col_letter():
    assert [col_letter(i) for i in (0, 25, 26, 51, 52)] == ["A", "Z", "AA", "AZ", "BA"]


def test_list_moves_from_folder_1_to_a_new_sheet_in_folder_2(google, tmp_path):
    new_id = run(google, tmp_path)
    new = google.files_store[new_id]
    assert new["parents"] == ["folder-2"] and new["name"] == "2026-01-06 example-list ENRICHED-3"
    grid = google.grids[new_id]
    assert grid[0] == COLS + ["Icebreaker"]
    assert all(row[-1].startswith("Hey Person") for row in grid[1:])
    assert google.tabs[new_id] == "leads"
    assert google.files_store["src"]["trashed"] is True
    assert google.files_store["twin"]["trashed"] is True  # its leads are all in folder 2 now
    assert google.files_store["other"]["trashed"] is False
    assert (tmp_path / "2026-01-06 example-list ENRICHED-3.csv").exists()
    assert (tmp_path / "2026-01-06 example-list ENRICHED-3.review.txt").exists()


def test_dry_run_leaves_drive_untouched(google, tmp_path):
    assert run(google, tmp_path, dry_run=True) is None
    assert len(google.files_store) == 3 and not any(f["trashed"] for f in google.files_store.values())
    assert (tmp_path / "2026-01-06 example-list ENRICHED-3.csv").exists()


def test_keep_source(google, tmp_path):
    run(google, tmp_path, keep_source=True)
    assert google.files_store["src"]["trashed"] is False


def test_failed_rows_block_the_upload(google, tmp_path):
    broken = FakeBackend(writer=lambda lead: {"nick": lead["first_name"], "company": "Acme GmbH",
                                              "kind": "brand", "lang": "en"})
    with pytest.raises(SystemExit, match="nothing uploaded"):
        run(google, tmp_path, backend=broken)
    assert len(google.files_store) == 3 and google.files_store["src"]["trashed"] is False


def test_enriched_lists_are_skipped(google, tmp_path):
    meta = google.add("done", "2026-01-06 example-list ENRICHED-3", "folder-1", lead_grid(1))
    assert hand_off.process(google, google, dict(meta), FOLDERS, FakeBackend(), Overrides(), Options(),
                            local_dir=tmp_path, day=DAY, log=lambda *_: None) is None


def test_redo_overrides_only_rewrites_the_column_in_place(tmp_path):
    g = FakeGoogle()
    rows = make_rows(2)
    grid = [COLS + ["notes", "Icebreaker"]]
    for r in rows:
        line = render(Draft(r["first_name"], r["company_name"].split()[0], "brand", "en"), r)
        grid.append([r[c] for c in COLS] + ["keep me", line])
    g.add("sheet", "2026-01-06 example-list ENRICHED-2", "folder-2", grid, tab="leads")
    overrides_csv = tmp_path / "o.csv"
    overrides_csv.write_text("match,company,company_de,kind,note\ncompany1.example,CompanyOne,,brand,\n", encoding="utf-8")
    hand_off.redo(g, g, "sheet", FOLDERS, Options(), Overrides.load(overrides_csv), backend=None,
                  overrides_only=True, local_dir=tmp_path, log=lambda *_: None)
    after = g.grids["sheet"]
    assert after[1] == grid[1]  # untouched row
    assert "about CompanyOne for a bit" in after[2][-1] and after[2][-2] == "keep me"


def test_account_guard():
    hand_off.check_account("you@example.com", "")  # no expectation set: allowed
    hand_off.check_account("You@Example.com", "you@example.com")
    with pytest.raises(SystemExit, match="Refusing"):
        hand_off.check_account("someone-else@example.com", "you@example.com")


def test_folders_must_be_set(monkeypatch):
    monkeypatch.setenv("DRIVE_FOLDER_TO_ENRICH", "your-folder-1-id")
    monkeypatch.setenv("DRIVE_FOLDER_ENRICHED", "your-folder-2-id")
    with pytest.raises(SystemExit, match="DRIVE_FOLDER"):
        Folders.from_env()
