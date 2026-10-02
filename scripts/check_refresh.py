"""Fail the monitoring run after publishing safe fallback data on source errors."""
import json
from zipfit.catalog import load_catalog


def main():
    catalog = load_catalog()
    failures = [{"provider": s["provider"], "error": s["last_error"]} for s in catalog["sources"] if s.get("last_error")]
    failures += [{"id": n["id"], "error": n["source_verification"].get("error")} for n in catalog["notices"] if n.get("source_verification", {}).get("state") == "error"]
    print(json.dumps({"failures": failures, "notices": len(catalog["notices"])}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
