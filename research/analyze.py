"""Validate saved evidence and extract notice samples without network requests.

uv run --no-project --with beautifulsoup4 --with lxml --with pypdf python research/analyze.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import zipfile
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"


def metadata(name):
    return json.loads((EVIDENCE / f"{name}.json").read_text(encoding="utf-8"))


def soup(name):
    return BeautifulSoup((ROOT / metadata(name)["raw_file"].replace("\\", "/")).read_bytes(), "lxml")


def compact(value):
    return " ".join(value.split())


def extract(name, source):
    records = []
    if source == "SEOUL_YOUTH":
        data = json.loads((ROOT / metadata(name)["raw_file"].replace("\\", "/")).read_text(encoding="utf-8"))
        for row in data["resultList"]:
            records.append({
                "notice_id": str(row["boardId"]), "title": row["nttSj"],
                "published_date": row.get("optn1"), "application_date_raw": row.get("optn4"),
                "public_private_code": row.get("optn2"), "initial_additional_code": row.get("optn5"),
                "detail_url": "https://soco.seoul.go.kr/youth/bbs/BMSR00015/view.do?" + urlencode({"boardId":row["boardId"],"menuNo":"400008"}),
            })
    else:
        doc = soup(name)
        selectors = {"LH":"a.wrtancInfoBtn", "SH":"a[onclick*='getDetailView']", "GH":"a[data-pbancno]", "APPLYHOME":"tr[data-hmno]"}
        for node in doc.select(selectors[source]):
            row = node if node.name == "tr" else node.find_parent("tr")
            cells = [compact(td.get_text(" ", strip=True)) for td in row.find_all("td", recursive=False)]
            record = {"raw_columns": cells}
            if source == "LH":
                for badge in node.select("em"):
                    badge.decompose()
                params = {"mi":"1026", "panId":node["data-id1"], "ccrCnntSysDsCd":node["data-id2"], "uppAisTpCd":node["data-id3"], "aisTpCd":node["data-id4"]}
                record.update(notice_id=node["data-id1"], title=compact(node.get_text(" ",strip=True)), detail_url="https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?"+urlencode(params), published_date=cells[5], listed_closing_date=cells[6], status_raw=cells[7], housing_type=cells[1], region=cells[3])
            elif source == "SH":
                notice_id = re.search(r"getDetailView\('([0-9]+)'\)",node["onclick"]).group(1)
                record.update(notice_id=notice_id, title=compact(node.get_text(" ",strip=True)), published_date=cells[3], detail_url="https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/view.do?multi_itm_seq=2&seq="+notice_id)
            elif source == "GH":
                board = "sr7155" if "purchase" in name else "sr7150"
                params = {"previewYn":node["data-previewyn"],"pbancNo":node["data-pbancno"],"pbancKndCd":node["data-pbanckndcd"]}
                record.update(notice_id=node["data-pbancno"], title=compact(node.get_text(" ",strip=True)), board=board, detail_url=f"https://apply.gh.or.kr/sb/sr/{board}/selectPbancDetailView.do?"+urlencode(params))
            else:
                params = {"houseManageNo":node["data-hmno"],"pblancNo":node["data-pbno"],"houseSecd":node["data-hsecd"]}
                record.update(notice_id=node["data-hmno"]+":"+node["data-pbno"], title=node["data-honm"], housing_type=cells[1], region=cells[0], published_date=cells[5], application_period_raw=cells[6], detail_url="https://www.applyhome.co.kr/ai/aia/selectPRMOLttotPblancDetailView.do?"+urlencode(params))
            records.append(record)
    for record in records:
        record.update(source=source, snapshot_id=name, eligibility_evaluated=False)
    if not records:
        raise ValueError(f"No expected notice records found in {name}")
    return records


def main():
    groups = {
        "LH": ["lh-list", "lh-list-page2-form", "lh-list-all-statuses"],
        "SH": ["sh-list", "sh-list-page2"],
        "GH": ["gh-purchase-list", "gh-rental-list", "gh-rental-list-page2"],
        "SEOUL_YOUTH": ["seoul-list-data", "seoul-list-page2", "seoul-public-list"],
        "APPLYHOME": ["applyhome-list", "applyhome-list-page2", "applyhome-public-rental-list", "applyhome-private-rental-list"],
    }
    samples = {name:extract(name,source) for source,names in groups.items() for name in names}
    pairs = [("lh-list","lh-list-page2-form"),("sh-list","sh-list-page2"),("gh-rental-list","gh-rental-list-page2"),("seoul-list-data","seoul-list-page2"),("applyhome-list","applyhome-list-page2")]
    pagination = []
    for first,second in pairs:
        a,b = ({r["notice_id"] for r in samples[n]} for n in [first,second])
        check = {"pages":[first,second],"first_page_count":len(a),"second_page_count":len(b),"overlap_count":len(a&b),"new_ids_on_second_page":len(b-a)}
        if not b-a:
            raise ValueError(f"Pagination did not produce new records: {first}")
        pagination.append(check)
    documents = []
    for path in sorted(EVIDENCE.glob("*.pdf")):
        reader = PdfReader(path)
        first_page_text = reader.pages[0].extract_text() or ""
        info = metadata(path.stem)
        if info["status"] != 200 or not info["is_pdf_signature"] or not first_page_text.strip():
            raise ValueError(f"Downloaded PDF did not validate: {path.name}")
        documents.append({"snapshot_id":path.stem,"file":str(path.relative_to(ROOT)),"pages":len(reader.pages),"first_page_text_characters":len(first_page_text),"bytes":info["bytes"],"sha256":info["sha256"],"source_url":info["final_url"]})
    hwp = ROOT / metadata("sh-notice-hwp")["raw_file"].replace("\\", "/")
    hwpx = ROOT / metadata("lh-notice-hwpx")["raw_file"].replace("\\", "/")
    with zipfile.ZipFile(hwpx) as archive:
        hwpx_checks = {"crc_error_file":archive.testzip(),"contains_contents":any(n.startswith("Contents/") for n in archive.namelist()),"mimetype":archive.read("mimetype").decode("ascii") if "mimetype" in archive.namelist() else None}
    if hwp.read_bytes()[:8] != bytes.fromhex("D0CF11E0A1B11AE1") or hwpx_checks["crc_error_file"] or not hwpx_checks["contains_contents"]:
        raise ValueError("HWP/HWPX container validation failed")
    all_metadata = [json.loads(p.read_text(encoding="utf-8")) for p in EVIDENCE.glob("*.json")]
    counts = {source:{"page_samples":len(names),"unique_board_items":len({r["notice_id"] for name in names for r in samples[name]})} for source,names in groups.items()}
    for source in counts:
        if source == "APPLYHOME":
            rental_records=[r for n in groups[source] for r in samples[n] if r["housing_type"] in ["민간임대","공공지원민간임대"]]
            counts[source]["unique_rental_items"] = len({r["notice_id"] for r in rental_records})
    checks = {
        "lh_all_statuses_filter_selected": soup("lh-list-all-statuses").select_one("select[name=panSs] option[selected]").get("value") == "",
        "applyhome_public_filter": all(r["housing_type"]=="공공지원민간임대" for r in samples["applyhome-public-rental-list"]),
        "applyhome_private_filter": all(r["housing_type"]=="민간임대" for r in samples["applyhome-private-rental-list"]),
        "seoul_public_filter": all(r["public_private_code"]=="1" for r in samples["seoul-public-list"]),
    }
    if not all(checks.values()):
        raise ValueError(f"A source filter failed: {checks}")
    report = {
        "generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "checked_at_utc_range":[min(m["checked_at_utc"] for m in all_metadata),max(m["checked_at_utc"] for m in all_metadata)],
        "scope":"Public access and sample retrieval only; no eligibility determination, historical completeness, or scheduled production operation tested.",
        "http_requests":len(all_metadata),"source_counts":counts,"pagination_checks":pagination,"filter_checks":checks,"pdf_documents":documents,
        "other_attachments":{"hwp_container_signature_valid":True,"hwpx":hwpx_checks},
        "credentialed_api_checks":[{"snapshot_id":name,"status":metadata(name)["status"],"result":"Missing API key; authenticated data response not tested"} for name in ["lh-api-without-key","reb-api-without-key"]],
        "observed_false_http_success":{"snapshot_id":"lh-list-page2","status":200,"result":"Error page returned when paging fields omitted; normal published paging form succeeded in lh-list-page2-form"},
        "limitations":["SH board samples include announcements/results/service notices; item counts are not open housing offer counts.","Applyhome default list includes non-rental types; use and verify source housing-type filters.","Seoul JSON endpoint is an internal public-page endpoint, not a contracted public OpenAPI.","LH default page uses date and status filters; tested explicit all-status query but not all dates or all pages.","GH purchase/rental boards tested separately; other GH recruitment channels have not been audited.","No scheduled repeat runs, production approval, source terms review, or completeness audit performed.","PDF page count and first-page extraction were checked; full eligibility tables and HWP text parsing were not evaluated."]
    }
    (ROOT/"notice_samples.json").write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding="utf-8")
    (ROOT/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"http_requests":len(all_metadata),"source_counts":counts,"pdf_count":len(documents),"pagination_checks_passed":len(pagination),"filter_checks":checks,"hwpx":hwpx_checks},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
