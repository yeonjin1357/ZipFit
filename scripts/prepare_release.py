"""Bundle the audited public notice catalog without logs or personal profiles."""
import json

from zipfit.audit import audit
from zipfit.catalog import ROOT, load_catalog


def main():
    catalog = load_catalog()
    report = audit(catalog)
    if report["errors"]:
        raise SystemExit(json.dumps(report["errors"], ensure_ascii=False))
    path = ROOT / "data/release-catalog.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    print(json.dumps({"catalog": path.relative_to(ROOT).as_posix(), "notices": len(catalog["notices"]), "review_warnings": report["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
