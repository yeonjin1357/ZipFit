import json
from pathlib import Path

import pytest

from scripts.build_catalog import normalize
from zipfit.catalog import ROOT
from zipfit.collect import jobs_for, merge_records
from zipfit.sources import parse_records
from tests.test_rules import NOW


def fixture(name,phase="research"):
    meta=json.loads((ROOT/phase/"evidence"/(name+".json")).read_text(encoding="utf-8"))
    return (ROOT/phase/meta["raw_file"]).read_text(encoding="utf-8"),meta["final_url"]


@pytest.mark.parametrize("name,source,count,phase,board",[("lh-list","LH",50,"research",None),("sh-list","SH",10,"research",None),("gh-purchase-list","GH",9,"research","sr7155"),("gh-main-board","GH_MAIN",10,"research/phase2",None),("seoul-audit-p1","SEOUL_YOUTH",10,"research/phase2",None),("applyhome-september-private-p1","APPLYHOME",0,"research/phase2",None)])
def test_real_source_snapshots(name,source,count,phase,board):
    raw,url=fixture(name,phase)
    rows=parse_records(raw,source,url,board)
    assert len(rows)==count
    for row in rows:
        n=normalize(row,NOW.isoformat())
        assert n["id"] and n["title"] and n["url"].startswith("https://")


def test_http_200_error_page_is_not_empty_success():
    raw,url=fixture("lh-list-page2")
    with pytest.raises(ValueError):parse_records(raw,"LH",url)


def test_refresh_retains_missing_items_and_invalidates_changed_rules():
    old={"id":"1","title":"curated","rule_model":"lh_20261001","region":"서울","housing_type":"임대","application_start":None,"application_end":None,"application_text":"","notes":["retained"],"document":{"sha256":"abc"},"rule_reviewed_at":"2026-10-01","list_fingerprint":{"title":"old"}}
    other={"id":"2","title":"other"}
    update={"id":"1","title":"changed","rule_model":None,"notes":[],"application_start":None,"application_end":None,"application_text":""}
    result=merge_records([old,other],[update])
    assert len(result)==2
    n=next(n for n in result if n["id"]=="1")
    assert n["review_invalidated"] and n["document"]["sha256"]=="abc"
    assert n["title"]=="curated" and n["notes"]==["retained"]
    assert n["rule_reviewed_at"]=="2026-10-01"


def test_lh_page_two_uses_published_paging_fields():
    jobs=jobs_for("LH",2,NOW)
    assert jobs[1]["data"]["srchY"]=="N"
    assert jobs[1]["data"]["currPage"]=="2"
    assert jobs[1]["data"]["prevListCo"]=="100"
