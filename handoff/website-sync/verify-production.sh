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
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print("unavailable:", exc)
        continue

    top5 = data.get("top5") or []
    status = data.get("sectorRankStatus") or {}
    print("generatedAt:", data.get("generatedAt"))
    print("indices/sectors/top5:", len(data.get("indices") or []), len(data.get("sectors") or []), len(top5))
    print("sectorRankStatus:", status)
    print("top1:", top5[0].get("name") if top5 else "--", top5[0].get("pct") if top5 else "--")
    print("warnings:", len(data.get("warnings") or []))
    for warning in (data.get("warnings") or [])[:5]:
        print("-", warning[:260])

quote_urls = [
    "https://www.heimaq.com/api/m2-watchlist?force=1",
    "https://blackhorse-quant.vercel.app/api/m2-watchlist?force=1",
]

for url in quote_urls:
    print(f"\n{url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print("unavailable:", exc)
        continue
    quotes = data.get("quotes") or []
    print("sourceStatus:", data.get("sourceStatus"), "quotes:", len(quotes), "generatedAt:", data.get("generatedAt"))
    if not quotes:
        raise RuntimeError("M2 watchlist quote endpoint returned no quotes")

snapshot_urls = [
    "https://www.heimaq.com/m2-snapshot.json",
    "https://blackhorse-quant.vercel.app/m2-snapshot.json",
]

for url in snapshot_urls:
    print(f"\n{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
    with urllib.request.urlopen(req, timeout=35) as response:
        content_length = int(response.headers.get("Content-Length") or 0)
        content_type = response.headers.get("Content-Type") or ""
    print("snapshot bytes:", content_length, "content-type:", content_type)
    if content_length < 1_000_000 or "json" not in content_type:
        raise RuntimeError("M2 static snapshot file is missing or unexpectedly small")

index_urls = [
    "https://www.heimaq.com/m2-history-index.json",
    "https://blackhorse-quant.vercel.app/m2-history-index.json",
]

for url in index_urls:
    print(f"\n{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    print("asOf:", data.get("asOf"), "available/total:", data.get("availableCount"), data.get("totalCount"))
    if data.get("availableCount") != 437 or data.get("totalCount") != 439:
        raise RuntimeError("M2 lazy history index counts are incorrect")

for code in ("600397", "600353", "600988"):
    url = f"https://www.heimaq.com/m2-history/{code}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    print("lazy history:", code, "rows:", len(data.get("rows") or []), "asOf:", data.get("asOf"))
    if len(data.get("rows") or []) < 200:
        raise RuntimeError(f"M2 lazy history is incomplete: {code}")

pages = [
    ("https://www.heimaq.com/", "Mark Minervini 2"),
    ("https://www.heimaq.com/m2-table", "M2 双阶段股票池"),
    ("https://www.heimaq.com/radar", "R02 盘面板块雷达"),
]

for url, marker in pages:
    print(f"\n{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8")
    if marker not in html:
        raise RuntimeError(f"marker missing: {marker}")
    print("page ok:", marker)
PY
