"""Public list adapters. Successful HTML is not necessarily a valid result."""
import json
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup


def compact(text):
    return " ".join(text.split())


def parse_records(raw, source, url, board=None):
    records = []
    if source == "SEOUL_YOUTH":
        data = json.loads(raw)
        if not isinstance(data.get("resultList"), list):
            raise ValueError("서울 청년안심주택 목록 구조가 변경됐어요.")
        for row in data["resultList"]:
            records.append({"notice_id":str(row["boardId"]),"title":row["nttSj"],"published_date":row.get("optn1"),"application_date_raw":row.get("optn4"),"detail_url":"https://soco.seoul.go.kr/youth/bbs/BMSR00015/view.do?"+urlencode({"boardId":row["boardId"],"menuNo":"400008"})})
    else:
        doc = BeautifulSoup(raw, "lxml")
        selector = {"LH":"a.wrtancInfoBtn","SH":"a[onclick*='getDetailView']","GH":"a[data-pbancno]","GH_MAIN":"a[href*='mode=view'][href*='articleNo=']","APPLYHOME":"tr[data-hmno]"}[source]
        for node in doc.select(selector):
            row = node if node.name == "tr" else node.find_parent("tr")
            if row is None:
                continue
            cells = [compact(td.get_text(" ",strip=True)) for td in row.find_all("td",recursive=False)]
            r = {"raw_columns":cells}
            if source == "LH":
                for badge in node.select("em"): badge.decompose()
                params = {"mi":"1026","panId":node["data-id1"],"ccrCnntSysDsCd":node["data-id2"],"uppAisTpCd":node["data-id3"],"aisTpCd":node["data-id4"]}
                r.update(notice_id=node["data-id1"],title=compact(node.get_text(" ",strip=True)),detail_url="https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?"+urlencode(params),published_date=cells[5],listed_closing_date=cells[6],status_raw=cells[7],housing_type=cells[1],region=cells[3])
            elif source == "SH":
                sid = re.search(r"getDetailView\('([0-9]+)'\)",node["onclick"])[1]
                r.update(notice_id=sid,title=compact(node.get_text(" ",strip=True)),published_date=cells[3],detail_url="https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/view.do?multi_itm_seq=2&seq="+sid)
            elif source == "GH":
                params = {"previewYn":node["data-previewyn"],"pbancNo":node["data-pbancno"],"pbancKndCd":node["data-pbanckndcd"]}
                r.update(notice_id=node["data-pbancno"],title=compact(node.get_text(" ",strip=True)),board=board,detail_url=f"https://apply.gh.or.kr/sb/sr/{board}/selectPbancDetailView.do?"+urlencode(params),published_date=cells[5],region=cells[3],listed_closing_date=cells[6],status_raw=cells[7])
            elif source == "GH_MAIN":
                r.update(notice_id=parse_qs(urlsplit(node["href"]).query)["articleNo"][0],title=compact(node.get_text(" ",strip=True)),source_category=cells[1],published_date="20"+cells[4],detail_url=urljoin(url,node["href"]))
            else:
                params = {"houseManageNo":node["data-hmno"],"pblancNo":node["data-pbno"],"houseSecd":node["data-hsecd"]}
                r.update(notice_id=node["data-hmno"]+":"+node["data-pbno"],title=node["data-honm"],housing_type=cells[1],region=cells[0],published_date=cells[5],application_period_raw=cells[6],detail_url="https://www.applyhome.co.kr/ai/aia/selectPRMOLttotPblancDetailView.do?"+urlencode(params))
            records.append(r)
        if not records:
            # Empty output is only trusted for a source whose empty state was
            # actually verified. Other layouts fail closed and keep old data.
            valid_empty = source == "APPLYHOME" and doc.select_one("select[name=searchHouseSecd]") and doc.select_one("table") and re.search(r"없습니다|없음",doc.get_text(" ",strip=True))
            if source == "GH":
                visible = doc.get_text(" ",strip=True)
                valid_empty = bool(doc.select_one("table") and "청약공고" in visible and "총게시물" in visible and "There is no data." in visible)
            if not valid_empty:
                raise ValueError("예상한 공고 목록을 찾지 못했어요. 기존 자료를 유지해요.")
    for r in records:
        r["source"] = source
    return records
