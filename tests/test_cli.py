"""The command line and the demo, end to end with the mock backend."""
import csv

from lead_icebreakers import config
from lead_icebreakers.cli import main

SAMPLE = config.FIXTURES / "sample_leads.csv"


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_csv_in_csv_out(tmp_path, capsys):
    out = tmp_path / "out.csv"
    code = main([str(SAMPLE), "-o", str(out), "--backend", "mock", "--overrides", str(config.OVERRIDES_EXAMPLE)])
    assert code == 0
    rows, source = read(out), read(SAMPLE)
    assert len(rows) == len(source) == 12
    assert list(rows[0])[:-1] == list(source[0]) and list(rows[0])[-1] == "Icebreaker"
    assert all(r["Icebreaker"].startswith("Hey ") for r in rows)
    assert [r["email"] for r in rows] == [r["email"] for r in source]  # contact columns kept in the file
    text = capsys.readouterr().out
    assert "second reader changed 4 of 12 lines" in text and "overrides changed 1 line" in text


def test_limit_and_no_review(tmp_path, capsys):
    out = tmp_path / "out.csv"
    assert main([str(SAMPLE), "-o", str(out), "--backend", "mock", "--limit", "3", "--no-review"]) == 0
    assert len(read(out)) == 3
    assert "second reader: off" in capsys.readouterr().out


def test_reapply_applies_overrides_to_a_finished_file(tmp_path, capsys):
    enriched, fixed = tmp_path / "enriched.csv", tmp_path / "fixed.csv"
    main([str(SAMPLE), "-o", str(enriched), "--backend", "mock", "--overrides", str(tmp_path / "none.csv")])
    before = read(enriched)
    assert "auf Cloudridge gestossen" in before[10]["Icebreaker"]
    assert main(["reapply", str(enriched), "-o", str(fixed), "--overrides", str(config.OVERRIDES_EXAMPLE)]) == 0
    after = read(fixed)
    assert "auf CloudRidge gestossen" in after[10]["Icebreaker"]
    assert [a["Icebreaker"] for i, a in enumerate(after) if i != 10] == \
        [b["Icebreaker"] for i, b in enumerate(before) if i != 10]


def test_demo_runs_offline(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import demo

    assert demo.main() == 0
    text = capsys.readouterr().out
    assert "Second reader changed 4 of 12 lines" in text
    assert "never    email, phone, linkedin_url" in text
    assert "gestossen und" in text  # Swiss spelling for the Zürich and Bern leads
