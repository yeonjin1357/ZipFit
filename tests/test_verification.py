from copy import deepcopy
from datetime import timedelta

import pytest

from tests.test_rules import SONGPA, NOW, youth
from zipfit.catalog import ROOT
from zipfit.verification import binding, compare, extract_detail, source_fresh, verify_catalog
from zipfit.rules import evaluate
from zipfit.review import build_report, render_report


def approved():
    n = deepcopy(SONGPA)
    proof = {"schema": 1, "binding": binding(n), "body_sha256": "body", "attachments": [], "media": [], "signals": {}}
    n["reviewed_source"] = proof
    n["source_verification"] = compare(n, proof, (NOW + timedelta(days=2)).isoformat())
    return n


def test_unchanged_source_renews_freshness_without_rewriting_rule_review():
    n = approved()
    now = NOW + timedelta(days=2, hours=1)
    assert source_fresh(n, now)
    assert evaluate(n, youth(), now)["status"] == "match"
    assert n["rule_reviewed_at"] == SONGPA["rule_reviewed_at"]
    assert not source_fresh(n, now + timedelta(days=1))


@pytest.mark.parametrize("field,value", [("rule_model", "another"), ("rule_reviewed_at", NOW.isoformat()), ("rule_config", {"regions": []}), ("rent_options", []), ("application_end", "2030-01-01"), ("daily_hours", ["09:00", "18:00"])])
def test_proof_cannot_authorize_different_rule_revision(field, value):
    n = approved()
    n[field] = value
    assert not source_fresh(n, NOW + timedelta(days=2))


def test_proof_cannot_authorize_different_pdf_or_future_timestamp():
    n = approved()
    assert not source_fresh(n, NOW)
    n["document"]["sha256"] = "different"
    assert not source_fresh(n, NOW + timedelta(days=2))


def test_change_failure_and_sticky_invalidation_block_both_outcomes():
    for state in ("changed", "error", "missing_baseline"):
        n = approved()
        n["source_verification"]["state"] = state
        for p in (youth(), youth(birth_date="1980-01-01")):
            assert evaluate(n, p, NOW + timedelta(days=2))["status"] == "unknown"
    n = approved() | {"review_invalidated": True}
    assert evaluate(n, youth(), NOW + timedelta(days=2))["status"] == "unknown"


def test_failed_fetch_keeps_reviewed_copy_and_timestamp(tmp_path, monkeypatch):
    from zipfit import verification
    monkeypatch.setattr(verification, "RUNTIME", tmp_path / "catalog.json")
    n = approved()
    def fail(_): raise ValueError("blocked")
    result = verify_catalog({"notices": [n]}, capture_fn=fail, now=NOW)
    row = result["notices"][0]
    assert row["document"] == n["document"]
    assert row["reviewed_source"] == n["reviewed_source"]
    assert row["source_verification"]["state"] == "error"
    assert row["rule_reviewed_at"] == n["rule_reviewed_at"]
    assert n["source_verification"]["state"] == "unchanged"


def test_non_pdf_attachment_change_is_reviewed_too():
    n = approved()
    changed = deepcopy(n["reviewed_source"])
    changed["attachments"] = [{"url": "changed-xlsx", "sha256": "different"}]
    record = compare(n, changed, NOW.isoformat())
    assert record["state"] == "changed" and "attachments" in record["changed_fields"]


def test_original_detail_adapters_and_correction_signals():
    import json
    rows = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))["notices"]
    cases = [("lh_20261001", "lh", 4), ("sh_newlywed_20260930", "sh", 6), ("songpa_20260922", "seoul_youth", 1)]
    for model, stem, count in cases:
        n = next(n for n in rows if n.get("rule_model") == model)
        raw = (ROOT / f"research/phase4/evidence/{stem}-detail.html").read_bytes()
        detail = extract_detail(raw, n)
        assert len(detail["attachments"]) == count
        assert n["document"]["url"] in [f["url"] for f in detail["attachments"]]
        with pytest.raises(ValueError): extract_detail("<html>blocked</html>", n)
        if model == "lh_20261001":
            assert "currPanId" in detail["signals"]
    detail = extract_detail((ROOT / "research/evidence/applyhome-detail.html").read_bytes(), next(n for n in rows if n["source_id"] == "2026850050:2026850050"))
    assert len(detail["attachments"]) == 1


def test_review_report_escapes_source_and_prioritizes_changed_rule():
    n = approved() | {"review_invalidated": True, "title": '<script>alert("x")</script>'}
    report = build_report({"notices": [n], "sources": []}, NOW)
    assert report["queue"][0]["priority"] == 0
    html = render_report(report)
    assert "<script>" not in html and "&lt;script&gt;" in html
