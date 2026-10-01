"""Small, explicit HTTP probe for public housing notices; no application actions.

Run: uv run --no-project --with requests --with beautifulsoup4 python research/probe.py research/requests-01.json
Each job is one public URL. Responses and metadata are saved for inspection.
No credentials, automatic link traversal, or access-control workarounds are used.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "evidence"
MAX_BYTES = 30 * 1024 * 1024


def probe(job: dict) -> dict:
    name = job["id"]
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        raise ValueError("Unsafe evidence identifier")
    result = {
        "id": name,
        "requested_url": job["url"],
        "method": job.get("method", "GET"),
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if result["method"] not in {"GET", "POST"}:
        raise ValueError("Only explicit public-page GET/read-only POST jobs are supported")
    started = time.monotonic()
    try:
        with requests.Session() as session:
            session.headers["User-Agent"] = "ZipFit-Research/0.1 (public housing notice availability probe)"
            if job.get("referer"):
                session.headers["Referer"] = job["referer"]
            with session.request(result["method"], job["url"], data=job.get("data"), timeout=(10, 25), stream=True) as response:
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Response exceeded 30 MiB limit")
                    chunks.append(chunk)
                body = b"".join(chunks)
                result.update({
                    "status": response.status_code,
                    "final_url": response.url,
                    "redirects": [{"status": r.status_code, "url": r.url} for r in response.history],
                    "content_type": response.headers.get("Content-Type"),
                    "content_disposition": response.headers.get("Content-Disposition"),
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "is_pdf_signature": body.startswith(b"%PDF-"),
                })
                kind = "pdf" if body.startswith(b"%PDF-") else "zip" if body.startswith(b"PK\x03\x04") else "bin" if body.startswith(b"\xd0\xcf\x11\xe0") else "html" if "html" in (result["content_type"] or "").lower() else "txt"
                raw = OUT / f"{name}.{kind}"
                raw.write_bytes(body)
                result["raw_file"] = str(raw.relative_to(ROOT))
                if kind in {"html", "txt"}:
                    response._content = body
                    if not response.encoding or response.encoding.lower() == "iso-8859-1":
                        response.encoding = response.apparent_encoding or "utf-8"
                    content = response.text
                    soup = BeautifulSoup(content, "html.parser")
                    result["title"] = soup.title.get_text(" ", strip=True) if soup.title else None
                    result["links"] = [{"text": a.get_text(" ", strip=True), "href": urljoin(response.url, a.get("href", "")), "onclick": a.get("onclick")} for a in soup.find_all("a") if a.get("href") or a.get("onclick")]
                    result["forms"] = [{"action": urljoin(response.url, f.get("action", "")), "method": f.get("method", "GET"), "fields": [{"name": n.get("name"), "value": n.get("value"), "type": n.get("type")} for n in f.find_all(["input", "select", "textarea"]) if n.get("name")]} for f in soup.find_all("form")]
                    result["scripts"] = [urljoin(response.url, s["src"]) for s in soup.find_all("script", src=True)]
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    text_path = OUT / f"{name}.text.txt"
                    text_path.write_text(soup.get_text("\n", strip=True), encoding="utf-8")
                    result["text_file"] = str(text_path.relative_to(ROOT))
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    except ValueError as exc:
        result["error"] = str(exc)
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    (OUT / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    # One explicit job per host in a batch keeps initial checks small and polite.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for result in executor.map(probe, jobs):
            print(json.dumps({k: result.get(k) for k in ["id", "status", "title", "bytes", "is_pdf_signature", "elapsed_seconds", "error"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
