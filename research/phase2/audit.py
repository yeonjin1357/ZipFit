"""Offline coverage and lifecycle audit of explicitly collected public evidence.

uv run --no-project --with beautifulsoup4 --with lxml --with pypdf python research/phase2/audit.py
This is a research verifier, not a production crawler or eligibility engine.
"""
from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import analyze
analyze.ROOT = HERE
analyze.EVIDENCE = HERE / "evidence"
START, END = "2026-09-01", "2026-09-30"


def meta(name, phase1=False):
    root = HERE.parent if phase1 else HERE
    return json.loads((root / "evidence" / (name + ".json")).read_text(encoding="utf-8"))


def doc(name, phase1=False):
    root = HERE.parent if phase1 else HERE
    return BeautifulSoup((root / meta(name,phase1)["raw_file"]).read_bytes(),"lxml")


def text(name):
    return (HERE / meta(name)["text_file"]).read_text(encoding="utf-8")


def date(value):
    return value.replace(".","-")


def classify(title):
    # Only triage hints. Unknown and ambiguous records must remain reviewable.
    if re.search(r"접수\s*마감.*안내",title):
        return "deadline_update"
    if re.search(r"(?:모집|공고).*취소|공급\s*중단",title):
        return "cancellation_update"
    if re.search(r"당첨자.*발표|선정결과|심사결과|경쟁률|계약안내|서류심사대상자|면접평가.*(?:대상자|발표)|입주대상자.*발표|예비입주자.*발표|서류제출\s*안내",title):
        return "result_or_followup"
    if re.search(r"정정|수정|변경",title) and re.search(r"모집|입주",title):
        return "recruitment_revision"
    if re.search(r"추가|재모집",title) and re.search(r"모집",title):
        return "additional_recruitment"
    if "모집" in title:
        return "recruitment_candidate"
    return "review_required"


def records(name,source):
    if source == "APPLYHOME" and not doc(name).select("tr[data-hmno]"):
        page = doc(name)
        # A verified empty result must still have the expected search controls,
        # result table and explicit empty-state text. HTTP 200 is insufficient.
        if not page.select_one("select[name=searchHouseSecd]") or not page.select_one("table") or not re.search(r"없습니다|없음",page.get_text(" ",strip=True)):
            raise ValueError("Unverified empty page: "+name)
        return []
    if source != "GH_MAIN":
        out = analyze.extract(name,source)
    else:
        out=[]
        for a in doc(name).select('a[href*="mode=view"][href*="articleNo="]'):
            row=a.find_parent("tr")
            if row is None: continue
            cells=[c.get_text(" ",strip=True) for c in row.find_all("td",recursive=False)]
            out.append({"source":source,"snapshot_id":name,"notice_id":parse_qs(urlsplit(a["href"]).query)["articleNo"][0],"title":a.get_text(" ",strip=True),"source_category":cells[1],"published_date":"20"+cells[4],"detail_url":urljoin(meta(name)["final_url"],a["href"]),"raw_columns":cells})
    if source == "GH":
        for row in out: row["published_date"]=row["raw_columns"][5]
    for row in out:
        row["published_date"]=date(row["published_date"])
        row["triage_hint"]=classify(row["title"])
    return out


def fingerprint(rows):
    # Excludes counters, navigation and HTML scripts. This is a LIST fingerprint;
    # detecting detail or attachment edits requires separately fetching them.
    fields=["notice_id","title","published_date","housing_type","region","listed_closing_date","status_raw","application_period_raw"]
    core=[{key:row[key] for key in fields if key in row} for row in rows]
    return hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def main():
    groups={
        "LH":["lh-september-p1","lh-september-p2"],
        "SH":[f"sh-audit-p{i}" for i in range(1,7)],
        "SEOUL_YOUTH":[f"seoul-audit-p{i}" for i in range(1,5)],
        "GH":["gh-rental-audit-p1","gh-purchase-audit-p1"],
        "GH_MAIN":["gh-main-board","gh-main-board-p2"],
        "APPLYHOME":["applyhome-september-public-p1","applyhome-september-private-p1"],
    }
    snapshots={name:records(name,source) for source,names in groups.items() for name in names}
    monthly={source:[r for name in names for r in snapshots[name] if START<=r["published_date"]<=END] for source,names in groups.items()}
    checks=[]
    def check(name,condition,detail):
        checks.append({"name":name,"passed":bool(condition),"detail":detail})
        if not condition: raise ValueError(name+": "+str(detail))

    lh_total=int(re.search(r"전체\s*([\d,]+)",doc("lh-september-p1").select_one(".bbs_total").get_text(" ",strip=True))[1].replace(",",""))
    lh_ids={r["notice_id"] for r in monthly["LH"]}
    check("LH query total reconciles",len(lh_ids)==lh_total==sum(len(snapshots[n]) for n in groups["LH"]),{"listed_total":lh_total,"unique_ids":len(lh_ids)})
    for source in ["SH","SEOUL_YOUTH","GH_MAIN"]:
        rows=[r for n in groups[source] for r in snapshots[n]]
        dates=[r["published_date"] for r in rows]
        check(source+" date boundary reached",dates==sorted(dates,reverse=True) and dates[-1]<START,{"last_date":dates[-1],"unique_ids":len({r["notice_id"] for r in rows})})
        check(source+" no duplicate page IDs",len(rows)==len({r["notice_id"] for r in rows}),len(rows))
    for name,source in [("lh-september-p1","LH"),("sh-audit-p1","SH"),("seoul-audit-p1","SEOUL_YOUTH")]:
        again=records(name+"-recheck",source)
        check(name+" first-page recheck",fingerprint(snapshots[name])==fingerprint(again),{"raw_sha_changed":meta(name)["sha256"]!=meta(name+"-recheck")["sha256"],"core_fingerprint_same":True})

    old=json.loads((HERE.parent/"notice_samples.json").read_text(encoding="utf-8"))["seoul-list-data"]
    old_ids={r["notice_id"] for r in old}; new_ids={r["notice_id"] for r in snapshots["seoul-audit-p1"]}
    all_new_ids={r["notice_id"] for n in groups["SEOUL_YOUTH"] for r in snapshots[n]}
    displaced=old_ids-new_ids
    pagination_change={"new_first_page_ids":sorted(new_ids-old_ids),"displaced_first_page_ids":sorted(displaced),"displaced_ids_found_on_later_pages":sorted(displaced&all_new_ids),"deletions_inferred":False}
    check("First-page disappearance is not deletion",bool(displaced) and displaced<=all_new_ids,pagination_change)
    check("Valid empty rental result",snapshots["applyhome-september-private-p1"]==[],"Explicit September private-rental filter returned the site's empty state")
    invalid=doc("lh-list-page2",phase1=True)
    check("HTTP-200 error rejected",meta("lh-list-page2",True)["status"]==200 and not invalid.select("a.wrtancInfoBtn") and "잘못된 경로" in invalid.get_text(" ",strip=True),"Phase-1 error response is not a valid empty list")

    long_running=records("lh-long-running","LH")
    old_active=[r for r in long_running if r["published_date"]<START and r["status_raw"]=="접수중"]
    check("Old active notices detected",bool(old_active),[{"id":r["notice_id"],"published":r["published_date"],"closes":r["listed_closing_date"]} for r in old_active])

    corr=(HERE/meta("lh-correction-musil")["raw_file"]).read_text(encoding="utf-8")
    orig=(HERE/meta("lh-musil-original")["raw_file"]).read_text(encoding="utf-8")
    parent=re.search(r"var sOtxtPanId\s*=\s*'([^']+)'",corr)[1]
    latest=re.search(r"var currPanId\s*=\s*'([^']+)'",orig)[1]
    check("Explicit LH revision relationship",parent=="2015122300020739" and latest=="2015122300020792",{"original":parent,"correction":latest})
    gh_rows=snapshots["gh-purchase-audit-p1"]
    repeated=[r for r in gh_rows if r["notice_id"] in ["803","812"]]
    check("Same-title GH rounds preserved",len(repeated)==2 and repeated[0]["title"]==repeated[1]["title"] and repeated[0]["published_date"]!=repeated[1]["published_date"],[{"id":r["notice_id"],"date":r["published_date"]} for r in repeated])
    check("Result titles take precedence over recruitment words",any("모집공고" in r["title"] and r["triage_hint"]=="result_or_followup" for r in monthly["SH"]),"SH titles can contain both 모집공고 and 당첨자 발표")
    check("GH closing notice retained",any(r["triage_hint"]=="deadline_update" for r in monthly["GH_MAIN"]),"GH main site has a closing update classified as 기타")

    old_pdf=meta("seoul-public-notice-pdf",True); corrected_pdf=meta("sh-youth-corrected-pdf")
    check("Cross-site PDF version conflict",old_pdf["sha256"]!=corrected_pdf["sha256"] and "정정" in text("sh-youth-corrected-detail"),"Both source PDFs visually inspected at printed page 7: 581 vs 595 units")
    coverage={source:{"pages_checked":len(names),"september_board_items":len(monthly[source]),"triage_hints":dict(Counter(r["triage_hint"] for r in monthly[source]))} for source,names in groups.items()}
    coverage["LH"]["query_listed_total"]=lh_total
    coverage["GH"]["qualification"]="Only two intake-board first pages inspected: both newest entries predate September; not a claim about all GH channels."
    summary={"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"window":{"start":START,"end":END,"basis":"Source list publication date; not application period or eligibility reference date"},"coverage":coverage,"checks":checks,"first_page_change":pagination_change,"old_active_notices":old_active,"revision_relationship":{"provider":"LH","original_id":parent,"corrected_id":latest,"evidence":"Explicit original/latest IDs in both official detail pages"},"cross_site_version":{"sources":["SEOUL_YOUTH:6624","SH:GS0401:309925"],"same_recruitment_basis":"Same issuing body, 2026 second youth-housing round, 2026-07-31 reference date; SH explicitly identifies republication with corrected volume","original_units_visually_checked":581,"corrected_units_visually_checked":595,"original_pdf_sha256":old_pdf["sha256"],"corrected_pdf_sha256":corrected_pdf["sha256"],"prefer":"Issuing body's explicitly corrected version; retain both sources and versions"},"limitations":["This is bounded list reconciliation, not independently established nationwide recall.","Pagination during a changing website can still miss records; three first pages were rechecked once, not continuously monitored.","No actual cancellation case was found in the September LH sample; cancellation handling remains specified but not live-validated.","Title classification is a review hint; no user eligibility or application status was automatically decided.","Cross-site grouping and authoritative version selection were reviewed for one case, not automated generally."]}
    (HERE/"audit-records.json").write_text(json.dumps(snapshots,ensure_ascii=False,indent=2),encoding="utf-8")
    (HERE/"audit-results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"coverage":coverage,"checks_passed":len(checks),"new_first_page_items":len(pagination_change["new_first_page_ids"]),"old_active_notices":len(old_active)},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
