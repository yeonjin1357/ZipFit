"""Offline catalog integrity audit; no personal inputs or network requests."""
import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .catalog import ROOT, load_catalog, schedule
from .models import Profile
from .rules import KST, evaluate

HOSTS = {"LH": "apply.lh.or.kr", "SH": "www.i-sh.co.kr", "GH": "apply.gh.or.kr", "GH_MAIN": "www.gh.or.kr", "SEOUL_YOUTH": "soco.seoul.go.kr", "APPLYHOME": "www.applyhome.co.kr"}


def audit(catalog, now=None):
    now = now or datetime.now(KST)
    errors, warnings = [], []
    rows = catalog["notices"]
    ids = {n["id"]: n for n in rows}
    for key, count in Counter(n["id"] for n in rows).items():
        if count > 1:
            errors.append(f"Duplicate ID: {key}")
    pdfs, reviewed, tracks = 0, 0, 0
    for n in rows:
        prefix = n["id"] + ": "
        url = urlsplit(n["url"])
        if url.scheme != "https" or url.hostname != HOSTS.get(n["source"]):
            errors.append(prefix + "Unexpected source URL")
        for key in ("published_date", "listed_closing_date", "listed_application_date", "reference_date", "application_start", "application_end"):
            value = n.get(key)
            if value:
                try:
                    datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
                except (TypeError, ValueError):
                    errors.append(prefix + f"Invalid {key}: {value}")
        if n.get("application_start") and n.get("application_end") and n["application_start"][:10] > n["application_end"][:10]:
            errors.append(prefix + "Application ends before it starts")
        for key, inverse in (("superseded_by", "corrects"),):
            if n.get(key) and (n[key] not in ids or ids[n[key]].get(inverse) != n["id"]):
                errors.append(prefix + "Broken correction link")
        if n.get("correction_url"):
            correction = urlsplit(n["correction_url"])
            if correction.scheme != "https" or correction.hostname not in HOSTS.values():
                errors.append(prefix + "Unexpected correction URL")
        if n.get("document"):
            doc = n["document"]
            path = (ROOT / doc["path"]).resolve()
            if not path.is_relative_to((ROOT / "research").resolve()) or not path.is_file():
                errors.append(prefix + "Missing or unsafe PDF path")
            else:
                raw = path.read_bytes()
                if not raw.startswith(b"%PDF") or hashlib.sha256(raw).hexdigest() != doc["sha256"]:
                    errors.append(prefix + "PDF checksum mismatch")
                pdfs += 1
        result = evaluate(n, Profile(), now)
        if n.get('housing_units'):
            doc=n.get('housing_document',{})
            path=(ROOT/doc.get('path','')).resolve()
            if not path.is_relative_to((ROOT/'research').resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=doc.get('sha256'):
                errors.append(prefix+'Missing or changed housing spreadsheet')
            if not any(f.get('sha256')==doc.get('sha256') and f.get('url')==doc.get('url') for f in n.get('reviewed_source',{}).get('attachments',[])):
                errors.append(prefix+'Housing spreadsheet absent from approved source')
            units=n['housing_units']
            if len({u['id'] for u in units})!=len(units) or any(type(u['deposit']) is not int or u['deposit']<=0 or type(u['monthly_rent']) is not int or u['monthly_rent']<0 or not u.get('address') or u['area']<=0 for u in units):
                errors.append(prefix+'Invalid housing unit')
        if result["status"] != "unknown":
            errors.append(prefix + "Empty profile must not assert eligibility")
        if n.get("rule_model"):
            reviewed += 1
            tracks += len(result["tracks"])
            if not result["tracks"] or not n.get("document") or not n.get("reference_date"):
                errors.append(prefix + "Incomplete rule evidence")
            if result["version_stale"]:
                warnings.append(prefix + "Rule review expired or source changed")
            known_tracks = {t["id"] for t in result["tracks"]}
            for option in n.get("rent_options", []):
                if option["track"] not in known_tracks or any(type(option[k]) is not int or option[k] < 0 for k in ("deposit", "monthly_rent")):
                    errors.append(prefix + "Invalid rent option")
            if n.get("reviewed_source"):
                from .verification import SCHEMA, HOSTS as VERIFIED_HOSTS, binding
                proof = n["reviewed_source"]
                files = proof.get("attachments", [])
                if proof.get("schema") != SCHEMA or proof.get("binding") != binding(n):
                    errors.append(prefix + "Reviewed source bound to different rules or evidence")
                if not any(f.get("url") == n["document"]["url"] and f.get("sha256") == n["document"]["sha256"] for f in files):
                    errors.append(prefix + "Reviewed PDF absent from source baseline")
                for f in files:
                    target = urlsplit(f.get("url", ""))
                    if target.scheme != "https" or target.hostname not in VERIFIED_HOSTS or len(f.get("sha256", "")) != 64:
                        errors.append(prefix + "Invalid source baseline attachment")
        state = schedule(n, now)
        if n.get("review_invalidated") and state["state"] in ("open", "upcoming"):
            errors.append(prefix + "Changed schedule still advertised")
    for source in catalog["sources"]:
        count = sum(n["provider"] == source["provider"] for n in rows)
        if count != source["count"]:
            errors.append(f"Source count mismatch: {source['provider']}")
    return {"checked_at": now.isoformat(), "source_posts": len(rows), "recruitment_candidates": sum(n["kind"] == "recruitment" for n in rows), "reviewed_notices": reviewed, "reviewed_tracks": tracks, "verified_pdf_files": pdfs, "schedule_states": dict(Counter(schedule(n, now)["state"] for n in rows)), "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(load_catalog())
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
