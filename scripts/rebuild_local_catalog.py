"""Offline replay of saved list responses after an adapter/rule update.

Keeps runtime-only records, saved invalidations and collection health. Backs up
the previous runtime catalog. Does not claim a new fetch or review happened.
Run from the repository root: uv run python -m scripts.rebuild_local_catalog
"""
import json
import os
from datetime import datetime
from pathlib import Path

from scripts.build_catalog import build, normalize
from zipfit.catalog import ROOT, RUNTIME
from zipfit.collect import merge_records
from zipfit.rules import KST
from zipfit.sources import parse_records


def main():
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    lock = RUNTIME.parent / "collection.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("Collection or rebuild already running.")
    try:
        previous = json.loads(RUNTIME.read_text(encoding="utf-8")) if RUNTIME.exists() else None
        build()
        catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
        ids = {n["id"] for n in catalog["notices"]}
        if previous:
            catalog["notices"].extend(n for n in previous["notices"] if n["id"] not in ids)
        replayed = 0
        for path in sorted((RUNTIME.parent / "snapshots").glob("*/*.json")):
            meta = json.loads(path.read_text(encoding="utf-8"))
            raw_path = path.with_suffix(".bin")
            if meta.get("error") or not raw_path.exists():
                continue
            request = meta["request"]
            rows = parse_records(raw_path.read_text(encoding="utf-8"), request["source"], request["url"], request.get("board"))
            for row in rows:
                row["snapshot_id"] = f"{path.parent.name}/{path.stem}"
            catalog["notices"] = merge_records(catalog["notices"], [normalize(r, meta["checked_at"]) for r in rows])
            replayed += 1
        if previous:
            old = {n["id"]: n for n in previous["notices"]}
            assert set(old) <= {n["id"] for n in catalog["notices"]}, "Rebuild must not discard records"
            for notice in catalog["notices"]:
                if old.get(notice["id"], {}).get("review_invalidated"):
                    notice["review_invalidated"] = True
            catalog["sources"] = previous["sources"]
            backup = RUNTIME.parent / f"catalog-before-rebuild-{datetime.now(KST):%Y%m%dT%H%M%S%f}.json"
            backup.write_bytes(RUNTIME.read_bytes())
        for source in catalog["sources"]:
            source["count"] = sum(n["provider"] == source["provider"] for n in catalog["notices"])
        temporary = RUNTIME.with_suffix(".tmp")
        temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(RUNTIME)
        print(json.dumps({"replayed_responses": replayed, "posts": len(catalog["notices"])}))
    finally:
        os.close(fd)
        lock.unlink()


if __name__ == "__main__":
    main()
