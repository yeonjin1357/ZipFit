from copy import deepcopy
from datetime import datetime

import pytest

from scripts.build_catalog import classify, iso, normalize
from tests.test_rules import CATALOG, NOW, SONGPA, youth
from zipfit.audit import audit
from zipfit.catalog import schedule
from zipfit.models import Profile
from zipfit.rules import evaluate
from tests.test_sources import fixture
from zipfit.sources import parse_records


def test_catalog_checksums_counts_links_and_rules():
    report = audit(CATALOG, NOW)
    assert report["errors"] == []
    assert report["verified_pdf_files"] == 7
    assert report["reviewed_notices"] == 3
    assert report["reviewed_tracks"] == 6


def test_audit_detects_duplicate_record_and_broken_document():
    bad = deepcopy(CATALOG)
    bad["notices"].append(deepcopy(bad["notices"][0]))
    next(n for n in bad["notices"] if n.get("document"))["document"]["sha256"] = "bad"
    errors = audit(bad, NOW)["errors"]
    assert any("Duplicate ID" in e for e in errors)
    assert any("checksum" in e for e in errors)


def test_followup_order_recruitment_is_not_result_announcement():
    n = next(n for n in CATALOG["notices"] if n["source_id"] == "2015122300020703")
    assert n["kind"] == "recruitment"
    assert classify({"source":"SH","title":"장기전세 예비 3차 입주대상자 발표"}) == "other"
    assert classify({"source":"LH","title":"임대료 인하 주택 입주자 모집"}) == "recruitment"


def test_gh_list_preserves_city_deadline_and_closed_status():
    raw, url = fixture("gh-rental-list-page2")
    rows = parse_records(raw,"GH",url,"sr7150")
    n = normalize(next(r for r in rows if r["notice_id"] == "784"), NOW.isoformat())
    assert n["region"].startswith("경기도 ")
    assert n["listed_closing_date"]
    assert schedule(n, NOW)["state"] == "closed"


def test_single_listed_application_date_is_not_full_period():
    row = {"source":"SEOUL_YOUTH","notice_id":"test","title":"모집공고","detail_url":"https://soco.seoul.go.kr/","application_date_raw":"2026-10-01"}
    n = normalize(row,NOW.isoformat())
    assert not n["application_text"]
    assert n["listed_application_date"] == "2026-10-01"
    assert schedule(n,NOW)["state"] == "unknown"


@pytest.mark.parametrize("value", ["2026-02-30","2026-13-01","garbage",None])
def test_bad_source_dates_do_not_break_results(value):
    assert iso(value) is None
    n = {"application_start":"2026-10-01", "application_end":value}
    assert schedule(n,NOW)["state"] == "unknown"


def test_changed_cancelled_and_reversed_schedules_not_advertised():
    assert schedule(SONGPA | {"review_invalidated":True},NOW)["changed"]
    assert schedule(SONGPA | {"withdrawn":True},NOW)["label"] == "취소된 공고"
    assert schedule({"application_start":"2026-10-16","application_end":"2026-10-14"},NOW)["state"] == "unknown"
    assert schedule({"application_start":"2026-10-01","application_end":"2026-10-02"},NOW)["date_only"]


def test_unknown_reasons_do_not_request_profile_for_unreviewed_or_stale():
    assert evaluate({},Profile(),NOW)["unknown_reason"] == "unreviewed"
    stale = evaluate(SONGPA | {"review_invalidated":True},Profile(),NOW)
    assert stale["unknown_reason"] == "stale" and not stale["missing_fields"]
    needed = evaluate(SONGPA,youth(reference_confirmed=False),NOW)
    assert needed["unknown_reason"] == "needs_input"
    for bad in ("bad", "2026-10-01", "2099-10-01T00:00:00+09:00"):
        assert evaluate(SONGPA | {"rule_reviewed_at":bad},youth(),NOW)["version_stale"]


def test_verified_cross_source_correction_and_cancelled_rules():
    repost = next(n for n in CATALOG["notices"] if n["source_id"] == "6624")
    assert "seq=309925" in repost["correction_url"]
    assert schedule(repost,NOW)["state"] == "superseded"
    for invalid in ({"withdrawn":True}, {"superseded_by":"replacement"}):
        assert evaluate(SONGPA | invalid,youth(),NOW)["status"] == "unknown"
