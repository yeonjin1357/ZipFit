from datetime import date, datetime, time
import json
from pathlib import Path

from .rules import KST

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "data/runtime/catalog.json"


def load_catalog():
    release = ROOT / "data/release-catalog.json"
    path = RUNTIME if RUNTIME.exists() else release if release.exists() else ROOT / "data/catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def schedule(notice, now=None):
    now = now or datetime.now(KST)
    if notice.get("superseded_by") or notice.get("correction_url"):
        return {"state":"superseded", "label":"정정본 있음"}
    if notice.get("withdrawn"):
        return {"state":"closed", "label":"취소된 공고"}
    if notice.get("source_status") == "접수마감":
        return {"state":"closed", "label":"목록상 접수 종료"}
    if notice.get("review_invalidated"):
        return {"state":"unknown", "label":"변경된 일정 확인 필요", "changed": True}
    def stamp(value, end=False):
        if not value:
            return None
        try:
            if "T" in value:
                parsed = datetime.fromisoformat(value)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)
            return datetime.combine(date.fromisoformat(value), time.max if end else time.min, KST)
        except (ValueError, TypeError):
            return None
    start = stamp(notice.get("application_start"))
    end_value = notice.get("application_end") or notice.get("listed_closing_date")
    end = stamp(end_value, True)
    if (notice.get("application_start") and start is None) or (end_value and end is None):
        return {"state":"unknown", "label":"일정 확인 필요"}
    if start and end and end < start:
        return {"state":"unknown", "label":"일정 확인 필요"}
    if end and now > end:
        return {"state":"closed", "label":"접수 종료"}
    if start and now < start:
        return {"state":"upcoming", "label":"접수 예정"}
    if start and end and start <= now <= end:
        date_only = "T" not in (notice.get("application_start") or "") or "T" not in (notice.get("application_end") or "")
        return {"state":"open", "label":"접수 기간 · 시간 확인" if date_only else "접수 기간", "date_only": date_only}
    return {"state":"unknown", "label":"접수일 확인 필요"}
