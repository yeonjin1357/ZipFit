"""Explicit read-only investigation requests, isolated from phase-1 evidence.

Existing identifiers are reused from disk rather than overwritten. Use a new ID
for a later observation. No background scheduling or application actions.
"""
import concurrent.futures
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import probe

probe.ROOT = HERE
probe.OUT = HERE / "evidence"


def run_host(jobs):
    results = []
    for job in jobs:
        existing = probe.OUT / (job["id"] + ".json")
        if existing.exists():
            result = json.loads(existing.read_text(encoding="utf-8"))
            if result["requested_url"] != job["url"]:
                raise ValueError("Existing identifier belongs to a different URL")
            cached = True
        else:
            result = probe.probe(job)
            time.sleep(0.5)
            cached = False
        summary = {k:result.get(k) for k in ["id","status","bytes","title","error"]}
        summary["cached"] = cached
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        results.append(result)
    return results


def main():
    probe.OUT.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    hosts = {}
    for job in jobs:
        hosts.setdefault(urlsplit(job["url"]).hostname, []).append(job)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(run_host, hosts.values()))


if __name__ == "__main__":
    main()
