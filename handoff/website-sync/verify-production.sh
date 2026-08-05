#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import urllib.request

urls = [
    "https://www.heimaq.com/api/dashboard?force=1",
    "https://blackhorse-quant.vercel.app/api/dashboard?force=1",
]

for url in urls:
    print(f"\n{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    top5 = data.get("top5") or []
    status = data.get("sectorRankStatus") or {}
    print("generatedAt:", data.get("generatedAt"))
    print("indices/sectors/top5:", len(data.get("indices") or []), len(data.get("sectors") or []), len(top5))
    print("sectorRankStatus:", status)
    print("top1:", top5[0].get("name") if top5 else "--", top5[0].get("pct") if top5 else "--")
    print("warnings:", len(data.get("warnings") or []))
    for warning in (data.get("warnings") or [])[:5]:
        print("-", warning[:260])
PY

