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

history_urls = [
    "https://www.heimaq.com/api/m2-history?force=1",
    "https://blackhorse-quant.vercel.app/api/m2-history?force=1",
]

for url in history_urls:
    print(f"\n{url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=35) as response:
        data = json.loads(response.read().decode("utf-8"))
    history = data.get("history") or {}
    row_counts = [len(item.get("rows") or []) for item in history.values()]
    print("sourceStatus:", data.get("sourceStatus"), "stocks:", len(history), "rows:", row_counts[:3])
    if not history or max(row_counts or [0]) < 100:
        raise RuntimeError("M2 history endpoint returned insufficient OHLCV data")

pages = [
    ("https://www.heimaq.com/", "Mark Minervini 2"),
    ("https://www.heimaq.com/m2-table", "8-5 早盘导入表"),
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
