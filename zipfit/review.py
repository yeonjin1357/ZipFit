"""Generate a local, read-only review queue; never approve an unreviewed notice."""
import argparse
from collections import Counter
from datetime import datetime
from html import escape
import json
from pathlib import Path

from .catalog import load_catalog, schedule
from .models import Profile
from .rules import KST, evaluate


def build_report(catalog, now=None):
    now = now or datetime.now(KST)
    queue = []
    for n in catalog["notices"]:
        if n["kind"] != "recruitment":
            continue
        state = schedule(n, now)["state"]
        evaluation = evaluate(n, Profile(), now)
        verification = n.get("source_verification", {})
        reasons = []
        if n.get("review_invalidated") or verification.get("state") == "changed":
            reasons.append("원문 변경")
        if verification.get("state") == "error":
            reasons.append("원문 재확인 실패")
        if evaluation["version_stale"]:
            reasons.append("검토 유효성 재확인")
        if state not in ("closed", "superseded"):
            if state == "unknown":
                reasons.append("접수 일정 확인")
            if not n.get("rule_model"):
                reasons.append("조건 규칙 미검토")
        if reasons:
            queue.append({"id": n["id"], "title": n["title"], "provider": n["provider"], "url": n["url"], "published_date": n["published_date"], "schedule": state, "priority": 0 if n.get("rule_model") and evaluation["version_stale"] else 1 if state in ("open", "upcoming") else 2, "reasons": reasons, "changed_fields": verification.get("changed_fields", []), "error": verification.get("error"), "last_source_check": verification.get("checked_at"), "list_changes": n.get("list_changes", [])})
    queue.sort(key=lambda x: (x["priority"], -(int((x["published_date"] or "0000-00-00").replace("-", "")))))
    return {"checked_at": now.isoformat(), "source_posts": len(catalog["notices"]), "source_failures": [{"provider": s["provider"], "error": s["last_error"]} for s in catalog["sources"] if s.get("last_error")], "reason_counts": dict(Counter(reason for row in queue for reason in row["reasons"])), "queue": queue}


def render_report(report):
    def e(value): return escape(str(value or ""), quote=True)
    rows = []
    for n in report["queue"]:
        detail = " · ".join(n["reasons"])
        if n["changed_fields"]:
            detail += " / 변경: " + ", ".join(n["changed_fields"])
        if n["error"]:
            detail += " / " + n["error"]
        changes = "".join(f"<li>{e(c['field'])}: {e(c.get('before'))} → {e(c.get('after'))}</li>" for c in n["list_changes"])
        rows.append(f'<article><span>{e(n["provider"])} · {e(n["published_date"])} · {e(n["schedule"])}</span><h2><a href="{e(n["url"])}" target="_blank" rel="noopener noreferrer">{e(n["title"])}</a></h2><p>{e(detail)}</p>{"<ul>"+changes+"</ul>" if changes else ""}<small>{e(n["id"])}</small></article>')
    failures = " / ".join(f"{x['provider']}: {x['error']}" for x in report["source_failures"])
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>집핏 공고 검토</title><style>body{{font:16px/1.65 system-ui,sans-serif;background:#f6f8fb;color:#263445;margin:0;padding:24px}}main{{max-width:960px;margin:auto}}article{{background:white;padding:24px;border-radius:16px;margin:16px 0;overflow-wrap:anywhere}}h2{{font-size:19px;margin:8px 0}}a{{color:#246be5;text-decoration:none}}span,small{{color:#64748b}}.summary{{background:#eaf2ff;padding:20px;border-radius:16px}}</style><main><h1>공고 검토 대기</h1><p>{e(report['checked_at'])} · 원본 {report['source_posts']}건 · 검토 대기 {len(rows)}건</p><div class="summary">{e(report['reason_counts'])}<br>{e(failures) if failures else '최근 목록 수집 오류 없음'}<p>변경된 기존 판정 → 접수 중·예정 공고 → 일정 미확인 공고 순서입니다. 원문과 첨부를 검토한 뒤 코드·근거를 함께 수정해야 합니다. 이 화면에는 승인·수정 기능이 없습니다.</p></div>{''.join(rows)}</main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("tmp/review/index.html"))
    args = parser.parse_args()
    report = build_report(load_catalog())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(report), encoding="utf-8")
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.output), "queue": len(report["queue"]), "source_failures": len(report["source_failures"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
