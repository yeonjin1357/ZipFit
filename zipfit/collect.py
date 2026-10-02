"""Bounded, explicitly invoked public-list refresh.

uv run python -m zipfit.collect --pages 2
Never submits an application, logs in, deletes missing notices, or renews rule
review dates. All retained records are merged atomically after collection.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode

import requests

from scripts.build_catalog import normalize
from .catalog import ROOT, RUNTIME, load_catalog
from .rules import KST
from .sources import parse_records


def jobs_for(provider, pages, now):
    start = now.date() - timedelta(days=60)
    jobs = []
    for page in range(1, pages+1):
        if provider == "LH":
            data = {"panId":"","ccrCnntSysDsCd":"","srchUppAisTpCd":"061339","uppAisTpCd":"06","aisTpCd":"","srchAisTpCd":"","prevListCo":"","mi":"1026","currPage":str(page),"srchY":"Y","indVal":"N","viewType":"","netbgn":"","srchFilter":"N","mvinQf":"0","cnpCd":"","panSs":"","schTy":"0","startDt":start.isoformat(),"endDt":now.date().isoformat(),"panNm":"","listCo":"100"}
            if page > 1:
                data.update(srchY="N",prevListCo="100",uppAisTpCd="061339",csCd="CNP_CD",xssChk="N",panStDt=start.strftime("%Y%m%d"),panEdDt=now.strftime("%Y%m%d"),minSn=str((page-2)*100),maxSn=str((page-1)*100),mvinQf="")
            jobs.append({"source":"LH","url":"https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancList.do","data":data})
        elif provider == "SH":
            jobs.append({"source":"SH","url":f"https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/list.do?multi_itm_seq=2&page={page}"})
        elif provider == "GH":
            for board in ("sr7150","sr7155"):
                jobs.append({"source":"GH","board":board,"url":f"https://apply.gh.or.kr/sb/sr/{board}/selectPbancRentHouseList.do?pageIndex={page}"})
            jobs.append({"source":"GH_MAIN","url":f"https://www.gh.or.kr/gh/announcement-of-salerental001.do?article.offset={(page-1)*10}&articleLimit=10"})
        elif provider == "SEOUL_YOUTH":
            jobs.append({"source":"SEOUL_YOUTH","url":"https://soco.seoul.go.kr/youth/pgm/home/yohome/bbsListJson.json","data":{"bbsId":"BMSR00015","pageIndex":str(page),"searchAdresGu":"","searchCondition":"all","searchKeyword":"","optn2":"","optn5":""},"referer":"https://soco.seoul.go.kr/youth/bbs/BMSR00015/list.do?menuNo=400008"})
        else:
            for kind in ("0303","0203"):
                params = {"beginPd":start.strftime("%Y%m"),"endPd":now.strftime("%Y%m"),"searchHouseSecd":kind,"pageIndex":page}
                jobs.append({"source":"APPLYHOME","url":"https://www.applyhome.co.kr/ai/aia/selectOtherLttotPblancListView.do?"+urlencode(params)})
    return jobs


def collect_provider(provider, pages, now, folder):
    session = requests.Session()
    session.headers["User-Agent"] = "ZipFit-LocalMVP/0.1 (public housing notice reader)"
    rows, errors = [], []
    seen_pages = {}
    jobs = jobs_for(provider,pages,now)
    for i, job in enumerate(jobs):
        snapshot = f"{provider.lower()}-{i+1}"
        meta = {"request":job,"checked_at":datetime.now(KST).isoformat()}
        try:
            with session.request("POST" if "data" in job else "GET",job["url"],data=job.get("data"),headers={"Referer":job.get("referer",job["url"])},timeout=(10,25),stream=True) as response:
                response.raise_for_status()
                parts,size=[],0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 10*1024*1024: raise ValueError("목록 응답 크기 제한 초과")
                    parts.append(chunk)
                raw = b"".join(parts)
                (folder/(snapshot+".bin")).write_bytes(raw)
                encoding = "utf-8" if job["source"] == "SEOUL_YOUTH" else response.encoding
                # requests' default ISO-8859-1 is not an encoding declaration.
                if not encoding or encoding.lower() == "iso-8859-1": encoding = "utf-8"
                text = raw.decode(encoding)
                parsed = parse_records(text,job["source"],response.url,job.get("board"))
                lane = (job["source"],job.get("board"), "0203" if "0203" in job["url"] else "0303" if "0303" in job["url"] else "")
                ids = {r["notice_id"] for r in parsed}
                if ids and ids <= seen_pages.get(lane,set()):
                    raise ValueError("페이지 이동 결과가 이전 페이지와 같아요. 수집 범위를 확인해야 해요.")
                seen_pages.setdefault(lane,set()).update(ids)
                for r in parsed:
                    r["snapshot_id"] = f"{folder.name}/{snapshot}"
                    rows.append(normalize(r,meta["checked_at"]))
                meta.update(status=response.status_code,bytes=size,sha256=hashlib.sha256(raw).hexdigest(),records=len(parsed))
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            error = str(exc)[:240]
            meta["error"] = error;errors.append(error)
        (folder/(snapshot+".json")).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
        time.sleep(.5)
    session.close()
    return provider,rows,errors,len(jobs)


def merge_records(existing, updates):
    result = {n["id"]:dict(n) for n in existing}
    fields = ("title","published_date","listed_closing_date","application_start","application_end","application_text","source_status")
    for n in updates:
        old = result.get(n["id"])
        if old:
            changed = any(old.get(k) != n.get(k) for k in fields if k not in ("application_start","application_end","application_text","title"))
            # Reviewed titles/schedules are curated; compare the source fields
            # captured before curation, not display text, to detect revisions.
            old_fingerprint = old.get("list_fingerprint")
            fingerprint = {k:n.get(k) for k in fields}
            if old_fingerprint is not None:
                changed = fingerprint != old_fingerprint
            keep = {k:v for k,v in old.items() if k not in n}
            if old.get("rule_model"):
                keep.update({k:old[k] for k in ("title","region","housing_type","application_start","application_end","application_text","notes","rule_model")})
                keep["review_invalidated"] = old.get("review_invalidated",False) or changed
            keep["notes"] = old.get("notes",[])
            if changed:
                previous = old_fingerprint or old
                keep["list_changes"] = [{"field": k, "before": previous.get(k), "after": fingerprint.get(k)} for k in fields if previous.get(k) != fingerprint.get(k)]
                keep["list_changed_at"] = n.get("observed_at")
            n = {**n,**keep,"list_fingerprint":fingerprint}
        else:
            n = {**n,"list_fingerprint":{k:n.get(k) for k in fields}}
        result[n["id"]] = n
    return list(result.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages",type=int,default=2,choices=range(1,11))
    args = parser.parse_args()
    RUNTIME.parent.mkdir(parents=True,exist_ok=True)
    lock = RUNTIME.parent / "collection.lock"
    try:
        lock_fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("이미 수집 중이에요. 중단된 작업이라면 data/runtime/collection.lock을 확인해 주세요.")
    try:
        catalog = load_catalog();now=datetime.now(KST)
        folder = RUNTIME.parent/"snapshots"/now.strftime("%Y%m%dT%H%M%S%f")
        folder.mkdir(parents=True)
        def run(source): return collect_provider(source["provider"],args.pages,now,folder)
        with ThreadPoolExecutor(max_workers=5) as pool:
            for provider,rows,errors,count in pool.map(run,catalog["sources"]):
                catalog["notices"] = merge_records(catalog["notices"],rows)
                source = next(s for s in catalog["sources"] if s["provider"]==provider)
                source.update(state="partial" if errors else "bounded_refresh",last_attempt=now.isoformat(),last_error=" / ".join(dict.fromkeys(errors)),count=sum(n["provider"]==provider for n in catalog["notices"]),scope=f"최근 목록 경로별 최대 {args.pages}페이지 갱신 + 기존 보관 자료. 과거·수시모집 전체 및 첨부파일 변경은 별도 확인이 필요해요.")
                if not errors: source["last_success"]=now.isoformat()
                print(json.dumps({"provider":provider,"requests":count,"rows":len(rows),"errors":errors},ensure_ascii=False),flush=True)
        temporary = RUNTIME.with_suffix(".tmp")
        catalog["last_collection_attempt"] = now.isoformat()
        temporary.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
        temporary.replace(RUNTIME)
        print("Saved: " + str(RUNTIME))
    finally:
        os.close(lock_fd);lock.unlink()


if __name__ == "__main__":
    main()
