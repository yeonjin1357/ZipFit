"""Rebuild a reproducible seed catalog from verified research snapshots."""
import hashlib
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def iso(value):
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", value or "")
    if not m:
        return None
    # Bad source dates must never crash every user's results endpoint.
    try:
        return date(*map(int, m.groups())).isoformat()
    except ValueError:
        return None


def classify(r):
    t = r["title"]
    if any(s in t for s in ("임대상가", "산업시설", "청년창업몰", "분양주택")):
        return "other"
    if any(s in t for s in ("마감 안내", "마감안내", "접수마감", "종료 안내", "취소공고")):
        return "update"
    if any(s in t for s in ("당첨자", "심사대상자", "심사 대상자", "입주대상자 발표", "예비입주자 발표", "선정결과 발표", "선정 결과 발표", "순번추첨", "순번 발표", "계약체결 안내", "납부", "조사결과")):
        return "other"
    if r["source"] == "GH_MAIN" and r.get("source_category") not in ("주택", "기타"):
        return "other"
    if r.get("housing_type") in ("상가", "토지", "분양주택", "공공분양", "신혼희망타운", "오피스텔", "도시형생활주택"):
        return "other"
    if r["source"] == "APPLYHOME":
        return "recruitment" if "임대" in r.get("housing_type", "") else "other"
    if any(s in t for s in ("주택 매도", "주택매도", "매입공고", "공급현황", "잔금", "일반매각")):
        return "other"
    if "모집" in t or "입주자" in t:
        return "recruitment"
    if "정정" in t:
        return "update"
    return "review"


def normalize(r, observed):
    source = r["source"]
    query = parse_qs(urlsplit(r["detail_url"]).query)
    board = r.get("board") or {"SH": "GS0401", "SEOUL_YOUTH": "BMSR00015", "GH_MAIN": "announcement"}.get(source, "notices")
    if source == "LH":
        board = "wrtanc-" + query.get("ccrCnntSysDsCd", ["unknown"])[0]
    uid = f"{source}:{board}:{r['notice_id']}"
    cells = r.get("raw_columns", [])
    published = iso(r.get("published_date"))
    region = r.get("region", "")
    if source == "GH" and len(cells) >= 6:
        published = published or iso(cells[5])
        city = cells[3]
        region = city if city.startswith("경기") else f"경기도 {city}" if city and city != "-" else "경기도"
    if source in ("SH", "SEOUL_YOUTH"):
        region = "서울특별시"
    if source == "GH_MAIN":
        region = "경기도"
    period = r.get("application_period_raw", "")
    dates = re.findall(r"20\d{2}[-.]\d{2}[-.]\d{2}", period)
    title = re.sub(r"\s*\d+일전$", "", r["title"]).strip()
    result = {"id": uid, "source": source, "provider": "GH" if source == "GH_MAIN" else source, "board": board, "source_id": r["notice_id"], "title": title,
        "url": r["detail_url"], "published_date": published, "region": region or "지역 확인 필요", "housing_type": r.get("housing_type", "") or (cells[1] if source == "GH" and len(cells)>1 else "임대주택"),
        "kind": classify(r), "source_status": r.get("status_raw") or (cells[7] if source == "GH" and len(cells) > 7 else None), "listed_closing_date": iso(r.get("listed_closing_date")) or (iso(cells[6]) if source == "GH" and len(cells) > 6 else None),
        "application_start": iso(dates[0]) if len(dates) == 2 else None, "application_end": iso(dates[1]) if len(dates) == 2 else None,
        "application_text": period, "listed_application_date": iso(r.get("application_date_raw")), "observed_at": observed, "snapshot_id": r.get("snapshot_id"), "rule_model": None, "notes": []}
    result["list_fingerprint"] = {k:result.get(k) for k in ("title","published_date","listed_closing_date","application_start","application_end","application_text","source_status")}
    result["withdrawn"] = "취소공고" in title or "공고취소" in title
    return result


def attach_document(n, snapshot, filename, phase="research"):
    metadata = read(f"{phase}/evidence/{snapshot}.json")
    path = ROOT / phase / "evidence" / filename
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == metadata["sha256"]
    n["document"] = {"url": metadata["final_url"], "path": path.relative_to(ROOT).as_posix(), "sha256": digest, "checked_at": metadata["checked_at_utc"]}


def build():
    catalog = {}
    for path, evidence in (("research/notice_samples.json", "research/evidence"), ("research/phase2/audit-records.json", "research/phase2/evidence")):
        for snapshot, rows in read(path).items():
            meta = read(f"{evidence}/{snapshot}.json")
            for r in rows:
                n = normalize(r, meta["checked_at_utc"])
                if n["id"] not in catalog or n["observed_at"] > catalog[n["id"]]["observed_at"]:
                    catalog[n["id"]] = n
    old_active = read("research/phase2/audit-results.json")["old_active_notices"]
    observed = read("research/phase2/evidence/lh-long-running.json")["checked_at_utc"]
    for row in old_active:
        n = normalize(row,observed)
        catalog[n["id"]] = n
    def get(provider, source_id):
        return next(n for n in catalog.values() if n["source"] == provider and n["source_id"] == source_id)

    n = get("SEOUL_YOUTH", "6679")
    n.update(rule_model="songpa_20260922", rule_reviewed_at="2026-10-01T07:40:00+00:00", reference_date="2026-09-22", kind="recruitment", region="서울특별시 송파구", housing_type="청년안심주택 · 민간임대", application_start="2026-09-30T09:00:00+09:00", application_end="2026-10-05T23:00:00+09:00", application_text="9.30 09:00 ~ 10.05 23:00", title="장지역 송파해링턴타워 청년안심주택 최초모집", rent_options=[])
    attach_document(n, "seoul-notice-pdf", "seoul-notice-pdf.pdf")
    n["notes"] = ["한 사람은 한 유형만 신청할 수 있으며, 부부 중복신청도 무효 처리돼요.", "청년은 현재 등본상 다른 가족이 주택을 소유해도 신청할 수 있지만, 실제 입주예정자는 모두 무주택이어야 해요.", "지역은 특별공급의 우선순위에 영향을 주며, 신청 자체의 거주지역 제한은 아니에요.", "보증금·월세는 같은 행의 조합이에요. 관리비와 보증료는 별도예요.", "공동지분 차량, 주택 소유 예외, 중복신청 여부와 증빙은 별도로 확인해야 해요."]
    for track, area, values in [
        ("youth_special",18.01,[(3000,47),(4400,41),(5900,35)]), ("couple_special",36.05,[(5900,84),(8900,74),(11800,63)]),
        ("youth_general",18.01,[(3500,56),(5300,49),(7000,42)]), ("couple_general",36.05,[(7000,100),(10500,88),(14100,75)])]:
        for deposit, rent in values:
            n["rent_options"].append({"track":track,"area":area,"deposit":deposit*10000,"monthly_rent":rent*10000,"page":8})
    n = get("LH", "2015122300020843")
    n.update(rule_model="lh_20261001", rule_reviewed_at="2026-10-01T07:40:00+00:00", reference_date="2026-10-01", kind="recruitment", application_start="2026-10-14T10:00:00+09:00", application_end="2026-10-16T16:00:00+09:00", application_text="10.14 10:00 ~ 10.16 16:00")
    attach_document(n, "lh-notice-pdf", "lh-notice-pdf.pdf")
    n["notes"] = ["무주택세대구성원·수도권 거주·성년 여부의 기본조건을 비교해요.", "외국인·재외국민 배우자의 등록 여부, 미성년 세대주 예외, 주택 소유 예외는 원문 4쪽을 확인해 주세요.", "1세대 1주택 신청, 동일 유형 중복신청 및 든든전세 기계약자 제한은 원문 1쪽 확인이 필요해요.", "공급주택 목록에 보증금이 별도로 있어요. 현재는 금액으로 제외하지 않아요.", "자녀·신생아 관련 배점과 당첨 가능성은 이번 버전에서 계산하지 않아요."]
    documents = [("SH","310653","sh-notice-pdf","research"),("GH","812","gh-purchase-notice-pdf","research"),("GH","808","gh-rental-notice-pdf","research"),("APPLYHOME","2026850050:2026850050","applyhome-notice-pdf","research"),("APPLYHOME","2026950017:2026950017","applyhome-private-notice-pdf","research")]
    for provider, sid, snapshot, phase in documents:
        n = get(provider,sid);attach_document(n,snapshot,snapshot+".pdf",phase)
    n = get("SH", "310653")
    n.update(rule_model="sh_newlywed_20260930", rule_reviewed_at="2026-10-01T08:40:06+00:00", reference_date="2026-09-30",
             application_start="2026-10-13T10:00:00+09:00", application_end="2026-10-15T17:00:00+09:00", application_text="10.13 10:00 ~ 10.15 17:00 (온라인)")
    n["notes"] = ["신혼·신생아 매입임대Ⅱ는 혼인 7년을 넘긴 혼인가구도 신청 유형에 포함돼요. 순위·가점·당첨 가능성은 계산하지 않아요.",
                  "소득·자산은 공고상 세대 전원, 예비신혼은 혼인으로 구성될 세대 기준이에요. 가구원 수에는 태아도 포함해요.",
                  "자동차는 총자산에 합산해요. 송파 공고의 별도 차량 한도를 이 공고에 적용하지 않아요.",
                  "Ⅰ·Ⅱ 중복신청, 세대 간 중복신청, 과거 불법양도·전대 제한 등은 원문 PDF 8쪽을 확인해 주세요.",
                  "주택형별 표의 임대료는 평균이에요. 실제 보증금·월세는 별도 공급주택 목록을 확인해야 해요.",
                  "표시 일정은 온라인 접수예요. 미성년 예외 신청자의 방문 접수는 10.13~10.15, 10~16시(점심시간 제외)예요."]
    for n in catalog.values():
        if n.get("rule_model"):
            n["schedule_reviewed"] = True
    original = get("LH", "2015122300020739")
    corrected = get("LH", "2015122300020792")
    original["superseded_by"] = corrected["id"]
    original["notes"].append("정정 공고가 확인됐어요. 연결된 최신 공고를 확인해 주세요.")
    corrected["corrects"] = original["id"]
    repost = get("SEOUL_YOUTH", "6624")
    correction = read("research/phase2/evidence/sh-youth-corrected-detail.json")
    repost["correction_url"] = correction["final_url"]
    repost["correction_checked_at"] = correction["checked_at_utc"]
    repost["notes"].append("이 게시물의 보관 PDF와 SH 정정본의 공급 물량이 달라요. SH가 물량을 정정해 재게시한 원문을 우선 확인해 주세요.")
    providers = {"LH":"LH 청약플러스", "SH":"SH 서울주택도시개발공사", "GH":"GH 경기주택도시공사", "SEOUL_YOUTH":"서울 청년안심주택", "APPLYHOME":"청약홈 민간임대"}
    source_status = []
    for provider,label in providers.items():
        rows = [n for n in catalog.values() if n["provider"] == provider]
        source_status.append({"provider":provider,"label":label,"last_success":max(n["observed_at"] for n in rows),"count":len(rows),"scope":"2026년 9월 게시물·최근 목록·일부 과거 공고 표본. 전체 기간 수집을 보장하지 않아요.","state":"snapshot"})
    result = {"format_version":1,"seed_date":"2026-10-01", "sources":source_status,"notices":list(catalog.values())}
    (ROOT/"data").mkdir(exist_ok=True)
    (ROOT/"data/catalog.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"source_posts":len(catalog),"recruitment_candidates":sum(n["kind"]=="recruitment" for n in catalog.values()),"reviewed_notices":sum(bool(n["rule_model"]) for n in catalog.values()),"providers":{s["provider"]:s["count"] for s in source_status}},ensure_ascii=False))


if __name__ == "__main__":
    build()
