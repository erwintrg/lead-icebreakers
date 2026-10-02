"""Batching, parallel calls, retries, the second reader and failure handling."""
import threading

import pytest

from lead_icebreakers.pipeline import chunked, enrich_rows

from conftest import FakeBackend, make_rows


def test_chunked():
    assert [len(b) for b in chunked(list(range(12)), 4)] == [4, 4, 4]
    assert [len(b) for b in chunked(list(range(10)), 4)] == [4, 4, 2]
    assert chunked([], 4) == []
    with pytest.raises(ValueError):
        chunked([1, 2], 0)


def test_rows_are_batched_for_both_passes(quiet):
    backend = FakeBackend()
    res = enrich_rows(make_rows(10), backend, batch_size=4, review_batch=6, log=quiet)
    writer = sorted(n for task, n in backend.calls if task == "writer")
    reviewer = sorted(n for task, n in backend.calls if task == "reviewer")
    assert writer == [2, 4, 4]
    assert reviewer == [4, 6]
    assert res.written == 10 and not res.failed


def test_calls_run_in_parallel(quiet):
    # Each writer call waits until three calls are in flight at once. Run one at a time, the
    # barrier would time out and every row would fail.
    backend = FakeBackend(barrier=threading.Barrier(3, timeout=5))
    res = enrich_rows(make_rows(12), backend, workers=3, batch_size=4, log=quiet)
    assert res.written == 12 and not res.failed


def test_failed_call_is_retried_row_by_row(quiet):
    backend = FakeBackend(fail_writer_calls=1)
    res = enrich_rows(make_rows(8), backend, workers=1, batch_size=4, log=quiet)
    assert res.written == 8 and not res.failed
    assert backend.count("writer") == 2 + 4  # two batches, then the failed batch's 4 rows alone


def test_row_that_keeps_failing_is_left_blank(quiet):
    def writer(lead):
        company = "Company1 GmbH" if lead["first_name"] == "Person1" else lead["company_name"].split()[0]
        return {"nick": lead["first_name"], "company": company, "kind": "brand", "lang": "en"}

    rows = make_rows(3)
    res = enrich_rows(rows, FakeBackend(writer=writer), log=quiet)
    assert rows[1]["Icebreaker"] == ""
    assert "legal form" in res.failed[1]
    assert rows[0]["Icebreaker"].startswith("Hey Person0.") and rows[2]["Icebreaker"].startswith("Hey Person2.")


def test_existing_lines_are_kept_unless_overwrite(quiet):
    rows = make_rows(3)
    rows[0]["Icebreaker"] = "a line someone already checked"
    backend = FakeBackend()
    res = enrich_rows(rows, backend, log=quiet)
    assert rows[0]["Icebreaker"] == "a line someone already checked"
    assert res.skipped == 1 and res.written == 2
    enrich_rows(rows, backend, overwrite=True, log=quiet)
    assert rows[0]["Icebreaker"].startswith("Hey Person0.")


def test_rows_without_name_or_company_stay_blank(quiet):
    rows = make_rows(2)
    rows[1]["company_name"] = ""
    res = enrich_rows(rows, FakeBackend(), log=quiet)
    assert rows[1]["Icebreaker"] == "" and res.skipped == 1 and res.written == 1


def test_second_reader_fixes_are_applied_and_reported(quiet):
    def reviewer(row):
        if row["company"] == "Company1":
            return {"company": "your consulting business", "kind": "generic", "reason": "named after the lead"}
        return None

    rows = make_rows(3)
    res = enrich_rows(rows, FakeBackend(reviewer=reviewer), log=quiet)
    assert "about your consulting business for a bit" in rows[1]["Icebreaker"]
    assert [(c.row, c.stage, c.reason) for c in res.changes] == [(3, "review", "named after the lead")]
    assert res.drafts[1].company == "Company1"  # the writer's answer is kept for the report
    assert res.reviewed == 3


def test_reviewer_fix_that_breaks_the_rules_is_rejected(quiet):
    rows = make_rows(2)
    res = enrich_rows(rows, FakeBackend(reviewer=lambda r: {"company": "your business", "kind": "generic"}),
                      log=quiet)
    assert not res.changes
    assert rows[0]["Icebreaker"].startswith("Hey Person0. Been thinking about Company0 ")


def test_review_failure_means_no_line(quiet):
    # a reviewer call is tried twice; if both fail, those rows ship blank
    rows = make_rows(2)
    res = enrich_rows(rows, FakeBackend(fail_reviewer_calls=2), log=quiet)
    assert all(r["Icebreaker"] == "" for r in rows)
    assert all(reason.startswith("review failed") for reason in res.failed.values())


def test_review_retry_recovers(quiet):
    rows = make_rows(2)
    res = enrich_rows(rows, FakeBackend(fail_reviewer_calls=1), log=quiet)
    assert not res.failed and all(r["Icebreaker"] for r in rows)


def test_no_review_flag_skips_the_second_reader(quiet):
    backend = FakeBackend()
    res = enrich_rows(make_rows(2), backend, review=False, log=quiet)
    assert backend.count("reviewer") == 0
    assert "off" in res.report()


def test_country_language_beats_the_model(quiet):
    rows = make_rows(1, country="Austria")
    english = lambda lead: {"nick": lead["first_name"], "company": "Company0", "kind": "brand", "lang": "en"}
    res = enrich_rows(rows, FakeBackend(writer=english), log=quiet)
    assert rows[0]["Icebreaker"].startswith("Hey Person0. Hab Company0 schon")
    assert res.final[0].lang_source == "country"
