"""Human overrides beat both model passes."""
import pytest

from lead_icebreakers.overrides import Overrides, normalize_domain, reapply
from lead_icebreakers.pipeline import enrich_rows
from lead_icebreakers.template import Draft, render

from conftest import FakeBackend, make_rows

HEADER = "match,company,company_de,kind,note\n"


def load(tmp_path, body: str) -> Overrides:
    path = tmp_path / "overrides.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return Overrides.load(path)


def test_override_beats_writer_and_reviewer(tmp_path, quiet):
    table = load(tmp_path, "company1.example,CompanyOne,,brand,how they write it\n")
    reviewer = lambda r: {"company": "Company1 Labs", "reason": "fuller name"} if r["company"] == "Company1" else None
    rows = make_rows(3)
    res = enrich_rows(rows, FakeBackend(reviewer=reviewer), overrides=table, log=quiet)
    assert "about CompanyOne for a bit" in rows[1]["Icebreaker"]
    assert [(c.stage, c.before, c.after) for c in res.changes] == [
        ("review", "Person1 / Company1", "Person1 / Company1 Labs"),
        ("override", "Person1 / Company1 Labs", "Person1 / CompanyOne"),
    ]


def test_domain_match_wins_over_company_name(tmp_path):
    table = load(tmp_path, "Company0 Ltd,ByName,,brand,\nhttps://www.company0.example/about,ByDomain,,brand,\n")
    draft = Draft("Person0", "Company0", "brand", "en")
    table.apply(draft, make_rows(1)[0], 2)
    assert draft.company == "ByDomain"


def test_company_name_match_is_case_and_space_insensitive(tmp_path):
    table = load(tmp_path, "company0   LTD,ByName,,brand,\n")
    row = {**make_rows(1)[0], "company_domain": ""}
    draft = Draft("Person0", "Company0", "brand", "en")
    assert table.apply(draft, row, 2) is not None and draft.company == "ByName"


@pytest.mark.parametrize("raw, expected", [
    ("https://www.Example.example/path?x=1", "example.example"),
    ("www.example.example.", "example.example"),
    ("example.example", "example.example"),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_german_generic_ruling_needs_a_german_phrase(tmp_path):
    row = {**make_rows(1)[0], "country": "Germany"}
    english_only = load(tmp_path, "company0.example,your consulting business,,generic,\n")
    draft = Draft("Person0", "Company0", "brand", "de")
    assert english_only.apply(draft, row, 2) is None and draft.company == "Company0"

    both = load(tmp_path, "company0.example,your consulting business,deine Beratung,generic,\n")
    assert both.apply(draft, row, 2) is not None
    assert (draft.company, draft.kind) == ("deine Beratung", "generic")


def test_brand_ruling_applies_to_any_language(tmp_path):
    table = load(tmp_path, "company0.example,CompanyZero,,brand,\n")
    draft = Draft("Person0", "Company0", "brand", "de")
    table.apply(draft, {**make_rows(1)[0], "country": "Austria"}, 2)
    assert draft.company == "CompanyZero"


def test_no_change_is_not_reported(tmp_path):
    table = load(tmp_path, "company0.example,Company0,,brand,\n")
    assert table.apply(Draft("Person0", "Company0", "brand", "en"), make_rows(1)[0], 2) is None


def test_bad_kind_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="line 2: kind"):
        load(tmp_path, "company0.example,Company0,,brandname,\n")


def test_missing_file_means_no_overrides(tmp_path):
    assert len(Overrides.load(tmp_path / "nope.csv")) == 0


def test_reapply_rewrites_finished_lines_without_a_model(tmp_path, quiet):
    rows = make_rows(3)
    rows[2]["country"] = "Switzerland"
    rows[2]["city"] = "Bern"
    rows[0]["Icebreaker"] = render(Draft("Person0", "Company0", "brand", "en"), rows[0])
    rows[1]["Icebreaker"] = render(Draft("Person1", "Company1", "brand", "en"), rows[1])
    rows[2]["Icebreaker"] = render(Draft("Person2", "Company2", "brand", "de"), rows[2])
    before = rows[0]["Icebreaker"]
    table = load(tmp_path, "company1.example,CompanyOne,,brand,\ncompany2.example,CompanyTwo,,brand,\n")
    changes = reapply(rows, table, log=quiet)
    assert [c.row for c in changes] == [3, 4]
    assert rows[0]["Icebreaker"] == before  # untouched
    assert "about CompanyOne for a bit" in rows[1]["Icebreaker"]
    assert "Hab CompanyTwo schon" in rows[2]["Icebreaker"] and "grössere" in rows[2]["Icebreaker"]
