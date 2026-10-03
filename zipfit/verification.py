"""Recheck reviewed source versions without automatically approving new rules."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
import requests

from .catalog import ROOT, RUNTIME, load_catalog

HOSTS = {"apply.lh.or.kr", "www.i-sh.co.kr", "soco.seoul.go.kr", "www.applyhome.co.kr", "static.applyhome.co.kr", "apply.gh.or.kr", "apply-cdn.gh.or.kr"}
SCHEMA = 1


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def binding(notice):
    """A previous source check cannot authorize a different PDF or rule revision."""
    keys = ["id", "url", "rule_model", "rule_config", "rule_reviewed_at", "reference_date", "document", "application_start", "application_end", "daily_hours", "rent_options"]
    keys += [key for key in ("housing_units", "housing_document") if key in notice]
    return digest({key: notice.get(key) for key in keys})


def fetch(session, url, max_bytes=40 * 1024 * 1024):
    for _ in range(4):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.port not in (None, 443) or parsed.username:
            raise ValueError("허용하지 않은 원문 주소예요.")
        with session.get(url, timeout=(10, 30), stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            parts, size = [], 0
            for part in response.iter_content(65536):
                size += len(part)
                if size > max_bytes:
                    raise ValueError("원문 응답 크기 제한을 초과했어요.")
                parts.append(part)
            return b"".join(parts)
    raise ValueError("원문 주소 이동 횟수를 초과했어요.")


def extract_detail(raw, notice):
    html = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    doc = BeautifulSoup(html, "lxml")
    source, url = notice["source"], notice["url"]
    attachments, signals = [], {}
    if source == "LH":
        sections = doc.select("#sub_container > section")
        if not sections or not doc.select_one(".bbsV_atchmnfl"):
            raise ValueError("LH 상세 구조를 확인할 수 없어요.")
        root = BeautifulSoup("".join(str(n) for n in sections), "lxml")
        for a in root.select("a[href*='fileDownLoad']"):
            match = re.search(r"fileDownLoad\('([0-9]+)'\)", a["href"])
            if not match:
                raise ValueError("LH 첨부 주소를 해석할 수 없어요.")
            attachments.append({"url": "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=" + match[1], "name": a.get_text(" ", strip=True)})
        for key in ("currPanId", "currPanKdCd"):
            match = re.search(r"var\s+" + key + r"\s*=\s*['\"]([^'\"]*)['\"]", html)
            if not match:
                raise ValueError("LH 정정·취소 연결을 확인할 수 없어요.")
            signals[key] = match[1]
    elif source == "SH":
        root = doc.select_one(".firgs0401Table")
        match = re.search(r"initParam\.downList\s*=\s*(\[.*?\]);", html, re.S)
        if not root or not match:
            raise ValueError("SH 본문·첨부 목록을 확인할 수 없어요.")
        for item in json.loads(match[1]):
            params = {k: item[k] for k in ("brdId", "seq", "fileTp", "fileSeq")}
            attachments.append({"url": "https://www.i-sh.co.kr/app/com/file/innoFD.do?" + urlencode(params), "name": item["oriFileNm"]})
    elif source == "SEOUL_YOUTH":
        root = doc.select_one("#printArea")
        if root:
            for a in root.select("a[href*='/fileDown.do?']"):
                attachments.append({"url": urljoin(url, a["href"]), "name": a.get_text(" ", strip=True)})
    elif source == "APPLYHOME":
        root = doc.select_one("#printArea")
        if root:
            for a in root.select("a[href*='getAtchmnfl.do?']"):
                attachments.append({"url": urljoin(url, a["href"]), "name": a.get_text(" ", strip=True)})
    elif source == "GH":
        root = doc.select_one('.sub_content .guide')
        if root:
            for a in root.select('a[href*="selectFileDown.do"]'):
                attachments.append({"url":urljoin(url,a['href']),"name":a.get_text(' ',strip=True)})
    else:
        raise ValueError("아직 상세 재확인을 지원하지 않는 기관이에요.")
    if not root or not attachments or len(attachments) > 12:
        raise ValueError("본문·첨부 목록이 비어 있거나 예상 범위를 벗어났어요.")
    for node in root.select("script, style, input, button, .preview, .viewerIco, .file_ic, a[onclick*='previewAjax'], a[onclick*='preListen']"):
        node.decompose()
    text = " ".join(root.get_text(" ", strip=True).split())
    text = re.sub(r"조회\s*수\s*[:：]?\s*[\d,]+", "조회수", text)
    if len(text) < 100:
        raise ValueError("원문 본문이 너무 짧아요.")
    # Ordinary links and images can carry a correction or an image-only notice.
    links = sorted({urljoin(url, a["href"]) for a in root.select("a[href]") if not a["href"].startswith(("#", "javascript:"))})
    images = sorted({urljoin(url, a["src"]) for a in root.select("img[src]")})
    return {"body": text, "links": links, "images": images, "signals": signals, "attachments": sorted(attachments, key=lambda x: x["url"])}


def capture(notice, session=None):
    own = session is None
    session = session or requests.Session()
    session.headers["User-Agent"] = "ZipFit/0.1 (public housing source verification)"
    try:
        detail = extract_detail(fetch(session, notice["url"], 4 * 1024 * 1024), notice)
        files, total = [], 0
        for item in detail["attachments"]:
            raw = fetch(session, item["url"])
            total += len(raw)
            if total > 100 * 1024 * 1024 or not raw:
                raise ValueError("첨부파일 총 크기를 확인해야 해요.")
            if raw.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                raise ValueError("첨부파일 대신 오류 페이지가 반환됐어요.")
            suffix = item["name"].strip().lower().rsplit(".", 1)[-1]
            signatures = {"pdf": b"%PDF", "xlsx": b"PK", "hwpx": b"PK", "hwp": b"\xd0\xcf\x11\xe0"}
            if suffix in signatures and not raw.startswith(signatures[suffix]):
                raise ValueError("첨부파일 형식이 파일명과 일치하지 않아요.")
            files.append({**item, "sha256": digest(raw), "bytes": len(raw)})
        if not any(f["url"] == notice["document"]["url"] and f["sha256"] == notice["document"]["sha256"] for f in files):
            raise ValueError("검토한 PDF가 현재 첨부 목록과 일치하지 않아요.")
        if len(detail["images"]) > 12:
            raise ValueError("본문 이미지 수를 확인해야 해요.")
        media = [{"url": url, "sha256": digest(fetch(session, url, 5 * 1024 * 1024))} for url in detail["images"]]
        return {"schema": SCHEMA, "binding": binding(notice), "body_sha256": digest({k: detail[k] for k in ("body", "links", "images", "signals")}), "attachments": files, "media": media, "signals": detail["signals"]}, detail["body"]
    finally:
        if own:
            session.close()


def compare(notice, observed, checked_at):
    baseline = notice.get("reviewed_source")
    state = "missing_baseline" if not baseline else "unchanged" if baseline == observed else "changed"
    changed = []
    if baseline:
        changed = [key for key in ("binding", "body_sha256", "attachments", "media", "signals") if baseline.get(key) != observed.get(key)]
    return {"state": state, "checked_at": checked_at, "binding": binding(notice), "changed_fields": changed, "error": None}


def source_fresh(notice, now):
    record = notice.get("source_verification", {})
    baseline = notice.get("reviewed_source", {})
    try:
        checked = datetime.fromisoformat(record["checked_at"])
        return (baseline.get("schema") == SCHEMA and record.get("state") == "unchanged"
                and record.get("binding") == baseline.get("binding") == binding(notice)
                and checked.tzinfo is not None and timedelta() <= now - checked <= timedelta(hours=24))
    except (KeyError, TypeError, ValueError):
        return False


def verify_catalog(catalog, capture_fn=capture, now=None):
    now = now or datetime.now(timezone.utc)
    result = deepcopy(catalog)
    folder = RUNTIME.parent / "verification"
    folder.mkdir(parents=True, exist_ok=True)
    for notice in result["notices"]:
        if not notice.get("rule_model") or not notice.get("document"):
            continue
        try:
            observed, body = capture_fn(notice)
            record = compare(notice, observed, now.isoformat())
            stem = digest(notice["id"])[:16]
            (folder / (stem + ".json")).write_text(json.dumps({"id": notice["id"], "checked_at": now.isoformat(), "observed": observed, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")
            if record["state"] == "changed":
                notice["review_invalidated"] = True
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            record = {"state": "error", "checked_at": now.isoformat(), "binding": binding(notice), "changed_fields": [], "error": str(exc)[:240]}
        notice["source_verification"] = record
        print(json.dumps({"id": notice["id"], **record}, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    catalog = verify_catalog(load_catalog())
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    temp = RUNTIME.with_suffix(".tmp")
    temp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(RUNTIME)


if __name__ == "__main__":
    main()
