#!/usr/bin/env python3
"""Local R02 sector dashboard server.

The server calls public frontend APIs from Eastmoney and Dapanyuntu, then serves a
small dashboard at http://127.0.0.1:8765/.  It intentionally keeps a short cache
to avoid aggressive polling of public data sources.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
import re
import statistics
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC_FILES = {
    "/": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/radar.html": (ROOT / "radar.html", "text/html; charset=utf-8"),
    "/radar": (ROOT / "radar.html", "text/html; charset=utf-8"),
    "/m2-styles.css": (ROOT / "m2-styles.css", "text/css; charset=utf-8"),
    "/m2-data.js": (ROOT / "m2-data.js", "text/javascript; charset=utf-8"),
    "/m2-sector-map.js": (ROOT / "m2-sector-map.js", "text/javascript; charset=utf-8"),
    "/m2-valuation-map.js": (ROOT / "m2-valuation-map.js", "text/javascript; charset=utf-8"),
    "/m2-app.js": (ROOT / "m2-app.js", "text/javascript; charset=utf-8"),
    "/m2-table": (ROOT / "m2-table.html", "text/html; charset=utf-8"),
    "/m2-table.html": (ROOT / "m2-table.html", "text/html; charset=utf-8"),
    "/m2-table.css": (ROOT / "m2-table.css", "text/css; charset=utf-8"),
    "/m2-table-data.js": (ROOT / "m2-table-data.js", "text/javascript; charset=utf-8"),
    "/m2-table-app.js": (ROOT / "m2-table-app.js", "text/javascript; charset=utf-8"),
    "/m2-snapshot.json": (ROOT / "m2-snapshot.json", "application/json; charset=utf-8"),
}
CACHE_TTL_SECONDS = 45
TREND_CACHE_TTL_SECONDS = int(os.environ.get("R02_TREND_CACHE_TTL_SECONDS", "1800"))
SECTOR_RANK_CACHE_MAX_AGE_SECONDS = int(
    os.environ.get("R02_SECTOR_RANK_CACHE_MAX_AGE_SECONDS", "86400")
)
FETCH_TIMEOUT_SECONDS = float(os.environ.get("R02_FETCH_TIMEOUT_SECONDS", "4"))
FETCH_RETRY_ATTEMPTS = max(1, int(os.environ.get("R02_FETCH_RETRY_ATTEMPTS", "2")))
API_WORKERS = int(os.environ.get("R02_API_WORKERS", "12"))
M2_HISTORY_WORKERS = max(1, int(os.environ.get("R02_M2_HISTORY_WORKERS", "4")))
M2_HISTORY_ATTEMPTS = max(1, int(os.environ.get("R02_M2_HISTORY_ATTEMPTS", "2")))
M2_HISTORY_RETRY_DELAY_SECONDS = float(
    os.environ.get("R02_M2_HISTORY_RETRY_DELAY_SECONDS", "0.5")
)

EASTMONEY_REFERER = "https://quote.eastmoney.com/"
EASTMONEY_UT = "fa5fd1943c7b386f172d6893dbfba10b"
TENCENT_STOCK_REFERER = "https://gu.qq.com/"
DAPANYUNTU_REFERER = "https://dapanyuntu.com/"
SCKD_REFERER = "https://sckd.dapanyuntu.com/"

INDEX_SECIDS = "1.000001,0.399006,1.000688,100.NDX,100.HSI"
TREND_DAYS = 10

R02_CURRENT = {
    "updated": "2026-06-29 收盘",
    "primary": "电子化学品",
    "secondary": "半导体",
    "note": (
        "正式 R02：电子化学品为核心主线，半导体为常规主线。"
        "盘面板块涨幅榜用于 S02 热点轮动观察，不能直接替代 R02 宽度资格。"
    ),
}

M2_CORE_WATCHLIST = [
    {"code": "300628", "market": "0", "name": "亿联网络"},
    {"code": "601677", "market": "1", "name": "明泰铝业"},
    {"code": "002648", "market": "0", "name": "卫星化学"},
    {"code": "601872", "market": "1", "name": "招商轮船"},
    {"code": "300750", "market": "0", "name": "宁德时代"},
    {"code": "000582", "market": "0", "name": "北部湾港"},
]


def _load_m2_watchlist() -> list[dict[str, str]]:
    """Load the current import candidates so history coverage follows the table.

    The homepage promotes the rows in m2-table-data.js to M2 cards. Keeping
    the server-side history list separate from that file meant new cards had no
    matching OHLCV entry and rendered the empty-chart state. The table is a
    generated JSON-compatible JavaScript literal, so parse its raw rows here.
    Fall back to the six core archives if the table is unavailable or malformed.
    """
    table_path = ROOT / "m2-table-data.js"
    try:
        source = table_path.read_text(encoding="utf-8")
        match = re.search(r"const raw\s*=\s*(\[\[.*?\]\]);\s*const rows", source, re.S)
        if not match:
            raise ValueError("m2-table-data.js raw rows not found")
        raw_rows = json.loads(match.group(1))
        candidates: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in raw_rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            raw_code = str(row[0] or "")
            code = raw_code.split(".", 1)[0]
            name = str(row[1] or "")
            if not code or not name or code in seen:
                continue
            suffix = raw_code.rsplit(".", 1)[-1].upper()
            market = "1" if suffix == "SH" else "0"
            candidates.append({"code": code, "market": market, "name": name})
            seen.add(code)
        if candidates:
            for item in M2_CORE_WATCHLIST:
                if item["code"] in seen:
                    continue
                candidates.append(dict(item))
                seen.add(item["code"])
            return candidates
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return [dict(item) for item in M2_CORE_WATCHLIST]


M2_WATCHLIST = _load_m2_watchlist()

_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_m2_quote_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_m2_history_cache: dict[str, dict[str, Any]] = {
    "live": {"ts": 0.0, "payload": None},
    "completed": {"ts": 0.0, "payload": None},
}
_trend_cache: dict[str, dict[str, Any]] = {}
_sector_rank_cache: dict[str, Any] = {"ts": 0.0, "updatedAt": None, "rows": []}


class FetchError(RuntimeError):
    pass


def fetch_json(url: str, referer: str, timeout: float | None = None) -> dict[str, Any]:
    if timeout is None:
        timeout = FETCH_TIMEOUT_SECONDS
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Referer": referer,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(FETCH_RETRY_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            break
        except Exception as exc:  # pragma: no cover - surfaced to dashboard
            last_exc = exc
            if attempt < FETCH_RETRY_ATTEMPTS - 1:
                time.sleep(0.25 * (attempt + 1))
                continue
    else:
        raise FetchError(f"fetch failed: {url}: {last_exc}") from last_exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid json: {url}: {raw[:160]}") from exc


def append_query_param(url: str, key: str, value: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urllib.parse.urlencode({key: value})}"


def fetch_eastmoney_json(url: str) -> dict[str, Any]:
    base_variants = [url]
    for host in ("push2.eastmoney.com", "push2his.eastmoney.com"):
        if host in url:
            base_variants.append(url.replace(host, "push2delay.eastmoney.com"))

    variants = []
    for base_url in base_variants:
        variants.append(base_url)
        if "ut=" not in base_url:
            variants.append(append_query_param(base_url, "ut", EASTMONEY_UT))

    errors = []
    for variant in dict.fromkeys(variants):
        try:
            return fetch_json(variant, EASTMONEY_REFERER)
        except FetchError as exc:
            errors.append(str(exc))
    raise FetchError(" | ".join(errors)[:720])


def num(value: Any) -> float | None:
    if value in (None, "-", "--", ""):
        return None
    try:
        out = float(str(value).replace(",", ""))
    except ValueError:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def pct_fmt(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:+.2f}%"


def money_yi(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 100000000, 2)


def get_market_indices() -> list[dict[str, Any]]:
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        "?fltt=2&invt=2&fields=f12,f13,f14,f2,f3,f4,f6&secids="
        + urllib.parse.quote(INDEX_SECIDS, safe=",.")
    )
    payload = fetch_eastmoney_json(url)
    diff = payload.get("data", {}).get("diff") or []
    return [
        {
            "code": str(row.get("f12", "")),
            "name": row.get("f14") or row.get("f12"),
            "price": num(row.get("f2")),
            "change": num(row.get("f4")),
            "pct": num(row.get("f3")),
            "amountYi": money_yi(num(row.get("f6"))),
        }
        for row in diff
    ]


def get_m2_watchlist_quotes() -> list[dict[str, Any]]:
    secids = ",".join(f"{item['market']}.{item['code']}" for item in M2_WATCHLIST)
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get"
        "?fltt=2&invt=2&fields=f12,f13,f14,f2,f3,f4,f5,f6,f7,f8&secids="
        + urllib.parse.quote(secids, safe=".,")
    )
    payload = fetch_eastmoney_json(url)
    diff = payload.get("data", {}).get("diff") or []
    rows_by_code = {str(row.get("f12")): row for row in diff}
    quotes = []
    for item in M2_WATCHLIST:
        row = rows_by_code.get(item["code"])
        if not row:
            continue
        quotes.append(
            {
                "code": item["code"],
                "name": row.get("f14") or item["name"],
                "price": num(row.get("f2")),
                "pct": num(row.get("f3")),
                "change": num(row.get("f4")),
                "volumeLots": num(row.get("f5")),
                "amountYi": money_yi(num(row.get("f6"))),
                "amplitude": num(row.get("f7")),
                "turnover": num(row.get("f8")),
            }
        )
    if not quotes:
        raise FetchError("M2 watchlist quote source returned no rows")
    return quotes


def get_m2_watchlist_payload(force: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force and _m2_quote_cache["payload"] and now - _m2_quote_cache["ts"] < CACHE_TTL_SECONDS:
        cached = dict(_m2_quote_cache["payload"])
        cached["cacheAgeSeconds"] = round(now - _m2_quote_cache["ts"])
        return cached

    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        quotes = get_m2_watchlist_quotes()
        payload = {
            "generatedAt": generated_at,
            "cacheTtlSeconds": CACHE_TTL_SECONDS,
            "cacheAgeSeconds": 0,
            "sourceStatus": "live",
            "source": "Eastmoney push2/push2delay ulist",
            "quotes": quotes,
            "warnings": [],
        }
        _m2_quote_cache["ts"] = now
        _m2_quote_cache["payload"] = payload
        return payload
    except Exception as exc:
        cached_payload = _m2_quote_cache.get("payload")
        if cached_payload:
            stale = dict(cached_payload)
            stale["sourceStatus"] = "stale"
            stale["cacheAgeSeconds"] = round(now - _m2_quote_cache["ts"])
            stale["warnings"] = [f"行情源暂时失败，沿用上次报价：{exc}"]
            return stale
        return {
            "generatedAt": generated_at,
            "cacheTtlSeconds": CACHE_TTL_SECONDS,
            "cacheAgeSeconds": 0,
            "sourceStatus": "unavailable",
            "source": "Eastmoney push2/push2delay ulist",
            "quotes": [],
            "warnings": [f"行情源暂时失败：{exc}"],
        }


def get_m2_watchlist_snapshot_payload() -> dict[str, Any]:
    snapshot_path = ROOT / "m2-snapshot.json"
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "generatedAt": generated_at,
            "cacheTtlSeconds": CACHE_TTL_SECONDS,
            "cacheAgeSeconds": 0,
            "sourceStatus": "unavailable",
            "source": "published m2-snapshot.json quotes",
            "quotes": [],
            "warnings": [f"M2 静态行情快照读取失败：{exc}"],
            "endpointMode": "snapshot",
        }

    quotes = snapshot.get("quotes") or []
    return {
        "generatedAt": snapshot.get("quoteGeneratedAt") or snapshot.get("generatedAt") or generated_at,
        "cacheTtlSeconds": CACHE_TTL_SECONDS,
        "cacheAgeSeconds": 0,
        "sourceStatus": snapshot.get("sourceStatus") or ("live" if quotes else "unavailable"),
        "source": snapshot.get("quoteSource") or "published m2-snapshot.json quotes",
        "quotes": quotes if isinstance(quotes, list) else [],
        "warnings": list(snapshot.get("warnings") or []),
        "endpointMode": "snapshot",
        "asOf": snapshot.get("asOf"),
    }


def _avg_field(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [num(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _range_pct(rows: list[dict[str, Any]]) -> float | None:
    highs = [num(row.get("high")) for row in rows]
    lows = [num(row.get("low")) for row in rows]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    if not highs or not lows or max(highs) <= 0:
        return None
    return (max(highs) - min(lows)) / max(highs) * 100


def _fetch_tencent_m2_history(item: dict[str, Any], end_date: dt.date | None = None) -> list[dict[str, Any]]:
    market_prefix = "sh" if item["market"] == "1" else "sz"
    symbol = f"{market_prefix}{item['code']}"
    end = end_date or dt.date.today()
    begin = (end - dt.timedelta(days=650)).isoformat()
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={symbol},day,{begin},{end.isoformat()},500,qfq"
    )
    payload = fetch_json(url, TENCENT_STOCK_REFERER, timeout=max(FETCH_TIMEOUT_SECONDS, 8))
    node = (payload.get("data") or {}).get(symbol) or {}
    raw_rows = node.get("qfqday") or node.get("day") or []
    rows: list[dict[str, Any]] = []
    previous_close: float | None = None
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < 6:
            continue
        close = num(raw[2])
        change = close - previous_close if close is not None and previous_close else None
        pct = (change / previous_close * 100) if change is not None and previous_close else None
        rows.append(
            {
                "date": str(raw[0]),
                "open": num(raw[1]),
                "close": close,
                "high": num(raw[3]),
                "low": num(raw[4]),
                "volume": num(raw[5]),
                "amountYi": None,
                "amplitude": None,
                "pct": pct,
                "change": change,
                "turnover": None,
            }
        )
        if close is not None:
            previous_close = close
    return rows


def _get_m2_history(item: dict[str, Any], end_date: dt.date | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    source = "Tencent ifzq adjusted daily OHLCV"
    tencent_error: Exception | None = None
    try:
        rows = _fetch_tencent_m2_history(item, end_date)
    except Exception as exc:
        tencent_error = exc

    if len(rows) >= 210:
        raw_rows: list[str] = []
        last_count = len(rows)
    else:
        # Eastmoney's historical endpoint can intermittently return an empty array
        # when a normal rolling begin/end date window is supplied. Fetch the durable
        # full series and trim locally so a bad date window cannot blank the chart.
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={item['market']}.{urllib.parse.quote(item['code'])}"
            "&fields1=f1,f2,f3,f4,f5,f6"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&ut={EASTMONEY_UT}&klt=101&fqt=1&beg=0&end=20500101&lmt=500"
        )
        raw_rows = []
        last_count = 0
        for attempt in range(M2_HISTORY_ATTEMPTS):
            payload = fetch_eastmoney_json(url)
            raw_rows = payload.get("data", {}).get("klines") or []
            last_count = len(raw_rows)
            if len(raw_rows) >= 210:
                break
            if attempt < M2_HISTORY_ATTEMPTS - 1:
                time.sleep(M2_HISTORY_RETRY_DELAY_SECONDS * (attempt + 1))
        rows = []
        for raw in raw_rows:
            parts = raw.split(",")
            if len(parts) < 11:
                continue
            rows.append(
                {
                    "date": parts[0],
                    "open": num(parts[1]),
                    "close": num(parts[2]),
                    "high": num(parts[3]),
                    "low": num(parts[4]),
                    "volume": num(parts[5]),
                    "amountYi": money_yi(num(parts[6])),
                    "amplitude": num(parts[7]),
                    "pct": num(parts[8]),
                    "change": num(parts[9]),
                    "turnover": num(parts[10]),
                }
            )
        if end_date:
            end_date_text = end_date.isoformat()
            rows = [row for row in rows if str(row.get("date")) <= end_date_text]
        source = "Eastmoney push2his adjusted daily OHLCV"

    if len(rows) < 210 and tencent_error:
        raise FetchError(f"{item['code']} Tencent fallback failed: {tencent_error}") from tencent_error
    if len(rows) < 210:
        raise FetchError(
            f"{item['code']} history returned only {len(rows)} rows "
            f"after Tencent primary and {M2_HISTORY_ATTEMPTS} Eastmoney attempts "
            f"(last raw={last_count})"
        )

    # Keep the older Eastmoney parsing block below out of the execution path.
    if False:
        pass
    """
    # Eastmoney's historical endpoint can intermittently return an empty array
    # when a normal rolling begin/end date window is supplied. Fetch the durable
    # full series and trim locally so a bad date window cannot blank the chart.
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={item['market']}.{urllib.parse.quote(item['code'])}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&ut={EASTMONEY_UT}&klt=101&fqt=1&beg=0&end=20500101&lmt=500"
    )
    raw_rows: list[str] = []
    last_count = 0
    for attempt in range(M2_HISTORY_ATTEMPTS):
        payload = fetch_eastmoney_json(url)
        raw_rows = payload.get("data", {}).get("klines") or []
        last_count = len(raw_rows)
        if len(raw_rows) >= 210:
            break
        if attempt < M2_HISTORY_ATTEMPTS - 1:
            time.sleep(M2_HISTORY_RETRY_DELAY_SECONDS * (attempt + 1))
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        parts = raw.split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "date": parts[0],
                "open": num(parts[1]),
                "close": num(parts[2]),
                "high": num(parts[3]),
                "low": num(parts[4]),
                "volume": num(parts[5]),
                "amountYi": money_yi(num(parts[6])),
                "amplitude": num(parts[7]),
                "pct": num(parts[8]),
                "change": num(parts[9]),
                "turnover": num(parts[10]),
            }
        )
    if end_date:
        end_date_text = end_date.isoformat()
        rows = [row for row in rows if str(row.get("date")) <= end_date_text]
    source = "Eastmoney push2his adjusted daily OHLCV"
    if len(rows) < 210:
        rows = _fetch_tencent_m2_history(item, end_date)
        source = "Tencent ifzq adjusted daily OHLCV"
    if len(rows) < 210:
        raise FetchError(
            f"{item['code']} history returned only {len(rows)} rows "
            f"after {M2_HISTORY_ATTEMPTS} Eastmoney attempts and Tencent fallback "
            f"(last raw={last_count})"
        )
    """

    for index, row in enumerate(rows):
        for window, key in ((50, "ma50"), (150, "ma150"), (200, "ma200")):
            if index + 1 >= window:
                closes = [num(point.get("close")) for point in rows[index + 1 - window : index + 1]]
                closes = [value for value in closes if value is not None]
                row[key] = sum(closes) / len(closes) if len(closes) == window else None
            else:
                row[key] = None

    contraction_windows = []
    for window in (40, 20, 10):
        if len(rows) < window * 2:
            continue
        previous = rows[-window * 2 : -window]
        current = rows[-window:]
        previous_range = _range_pct(previous)
        current_range = _range_pct(current)
        previous_volume = _avg_field(previous, "volume")
        current_volume = _avg_field(current, "volume")
        if (
            previous_range is not None
            and current_range is not None
            and previous_volume
            and current_volume
            and current_range <= previous_range * 0.9
            and current_volume <= previous_volume * 0.95
        ):
            contraction_windows.append(
                {
                    "window": window,
                    "startDate": current[0]["date"],
                    "endDate": current[-1]["date"],
                    "rangePct": round(current_range, 2),
                    "volumeRatio": round(current_volume / previous_volume, 2),
                }
            )

    recent_five = rows[-5:]
    prior_twenty = rows[-25:-5]
    recent_volume = _avg_field(recent_five, "volume")
    prior_volume = _avg_field(prior_twenty, "volume")
    last_ma200 = num(rows[-1].get("ma200"))
    prior_ma200 = num(rows[-21].get("ma200")) if len(rows) >= 21 else None
    price_range_20 = _range_pct(rows[-20:])
    base_highs = [num(row.get("high")) for row in rows[-40:]]
    base_lows = [num(row.get("low")) for row in rows[-40:]]
    base_highs = [value for value in base_highs if value is not None]
    base_lows = [value for value in base_lows if value is not None]
    base_depth = ((max(base_highs) - min(base_lows)) / max(base_highs) * 100) if base_highs and base_lows and max(base_highs) > 0 else None
    if len(contraction_windows) >= 2:
        vcp_status = "VCP 候选：价格与量能连续收缩"
    elif len(contraction_windows) == 1:
        vcp_status = "VCP 初步收缩：继续观察"
    else:
        vcp_status = "VCP 收缩未确认"

    return {
        "code": item["code"],
        "name": item["name"],
        "asOf": rows[-1]["date"],
        "rows": rows[-160:],
        "metrics": {
            "source": source,
            "baseDays": 40,
            "baseDepthPct": round(base_depth, 2) if base_depth is not None else None,
            "range20Pct": round(price_range_20, 2) if price_range_20 is not None else None,
            "volumeDryUpRatio": round(recent_volume / prior_volume, 2) if recent_volume and prior_volume else None,
            "ma200SlopePct20d": round((last_ma200 / prior_ma200 - 1) * 100, 2) if last_ma200 and prior_ma200 else None,
            "contractionCount": len(contraction_windows),
            "contractions": contraction_windows,
            "vcpStatus": vcp_status,
        },
    }


def _load_m2_snapshot_history() -> dict[str, Any]:
    snapshot_path = ROOT / "m2-snapshot.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    history = snapshot.get("history")
    return history if isinstance(history, dict) else {}


def get_m2_snapshot_payload() -> dict[str, Any]:
    snapshot_path = ROOT / "m2-snapshot.json"
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "generatedAt": generated_at,
            "cacheTtlSeconds": 600,
            "cacheAgeSeconds": 0,
            "sourceStatus": "unavailable",
            "source": "published m2-snapshot.json",
            "barStatus": "snapshot",
            "history": {},
            "warnings": [f"M2 静态快照读取失败：{exc}"],
            "reusedSnapshotCodes": [],
            "endpointMode": "snapshot",
        }

    payload = dict(snapshot)
    payload.setdefault("generatedAt", snapshot.get("generatedAt") or generated_at)
    payload.setdefault("cacheTtlSeconds", 600)
    payload["cacheAgeSeconds"] = 0
    payload.setdefault("sourceStatus", "live" if payload.get("history") else "unavailable")
    payload.setdefault("source", "published m2-snapshot.json")
    payload.setdefault("barStatus", "snapshot")
    payload.setdefault("warnings", [])
    payload.setdefault("reusedSnapshotCodes", [])
    payload["endpointMode"] = "snapshot"
    return payload


def get_m2_history_payload(force: bool = False, completed_only: bool = False) -> dict[str, Any]:
    cache = _m2_history_cache["completed" if completed_only else "live"]
    now = time.time()
    if not force and cache["payload"] and now - cache["ts"] < 600:
        cached = json.loads(json.dumps(cache["payload"], ensure_ascii=False))
        cached["cacheAgeSeconds"] = round(now - cache["ts"])
        return cached

    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    end_date = None
    if completed_only:
        shanghai_now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
        before_close = shanghai_now.hour < 15 or (shanghai_now.hour == 15 and shanghai_now.minute < 30)
        if before_close:
            end_date = shanghai_now.date() - dt.timedelta(days=1)
    history: dict[str, Any] = {}
    warnings: list[str] = []
    workers = min(M2_HISTORY_WORKERS, len(M2_WATCHLIST))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_get_m2_history, item, end_date): item for item in M2_WATCHLIST}
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            try:
                history[item["code"]] = future.result()
            except Exception as exc:
                warnings.append(f"{item['name']} 动态日K失败：{exc}")

    snapshot_history = _load_m2_snapshot_history()
    reused_codes = []
    for item in M2_WATCHLIST:
        code = item["code"]
        if code not in history and code in snapshot_history:
            history[code] = snapshot_history[code]
            reused_codes.append(code)
    if reused_codes:
        warnings.append(f"部分动态日K沿用本地快照：{','.join(reused_codes)}")

    source_status = "live" if len(history) == len(M2_WATCHLIST) and not reused_codes else ("partial" if history else "unavailable")
    payload = {
        "generatedAt": generated_at,
        "cacheTtlSeconds": 600,
        "cacheAgeSeconds": 0,
        "sourceStatus": source_status,
        "source": "Eastmoney push2his/push2delay daily adjusted OHLCV",
        "barStatus": "complete" if completed_only else "current",
        "history": history,
        "warnings": warnings,
        "reusedSnapshotCodes": reused_codes,
    }
    if history:
        cache["ts"] = now
        cache["payload"] = payload
        return payload
    cached_payload = cache.get("payload")
    if cached_payload:
        stale = json.loads(json.dumps(cached_payload, ensure_ascii=False))
        stale["sourceStatus"] = "stale"
        stale["cacheAgeSeconds"] = round(now - cache["ts"])
        stale["warnings"] = warnings + ["动态日K源暂时失败，沿用上次成功数据。"]
        return stale
    return payload


def get_sector_rank(limit: int = 20) -> list[dict[str, Any]]:
    fields = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f20,f104,f105,f128,f136,f140"
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs=m:90+t:2&fields={fields}"
    )
    payload = fetch_eastmoney_json(url)
    diff = payload.get("data", {}).get("diff") or []
    sectors = []
    for rank, row in enumerate(diff, start=1):
        sectors.append(
            {
                "rank": rank,
                "code": row.get("f12"),
                "name": row.get("f14"),
                "price": num(row.get("f2")),
                "pct": num(row.get("f3")),
                "change": num(row.get("f4")),
                "amplitude": num(row.get("f7")),
                "turnover": num(row.get("f8")),
                "amountYi": money_yi(num(row.get("f6"))),
                "marketCapYi": money_yi(num(row.get("f20"))),
                "upCount": int(row.get("f104") or 0),
                "downCount": int(row.get("f105") or 0),
                "leader": row.get("f128") or "--",
                "leaderCode": row.get("f140") or "",
                "leaderPct": num(row.get("f136")),
            }
        )
    return sectors


def build_sector_rank_status(
    sectors: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    if error:
        return {
            "ready": False,
            "reason": "source_error",
            "message": "东方财富板块排行接口暂时失败，等待下一次刷新。",
            "detail": error[:360],
        }
    if not sectors:
        return {
            "ready": False,
            "reason": "empty",
            "message": "板块排行暂无数据，等待实时行情源返回。",
        }

    has_intraday_snapshot = any(
        (sector.get("amountYi") is not None and sector.get("amountYi") > 0)
        or ((sector.get("upCount") or 0) + (sector.get("downCount") or 0) > 0)
        or sector.get("leaderPct") is not None
        or (sector.get("leader") not in (None, "", "-", "--") and sector.get("leaderCode"))
        or (sector.get("pct") not in (None, 0))
        or (sector.get("amplitude") not in (None, 0))
        for sector in sectors[:15]
    )
    if has_intraday_snapshot:
        return {
            "ready": True,
            "reason": "ok",
            "message": "板块排行已更新。",
        }
    return {
        "ready": False,
        "reason": "not_started",
        "message": "东方财富板块实时报价尚未开始更新；盘前排行不具备参考意义。",
    }


def get_sector_leaders(code: str, limit: int = 10) -> list[dict[str, Any]]:
    fields = "f12,f14,f2,f3,f4,f6,f7,f8,f10,f20,f21,f23"
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs=b:{urllib.parse.quote(code)}&fields={fields}"
    )
    payload = fetch_eastmoney_json(url)
    diff = payload.get("data", {}).get("diff") or []
    leaders = []
    for rank, row in enumerate(diff, start=1):
        leaders.append(
            {
                "rank": rank,
                "code": row.get("f12"),
                "name": row.get("f14"),
                "price": num(row.get("f2")),
                "pct": num(row.get("f3")),
                "change": num(row.get("f4")),
                "amountYi": money_yi(num(row.get("f6"))),
                "amplitude": num(row.get("f7")),
                "turnover": num(row.get("f8")),
                "pe": num(row.get("f10")),
                "marketCapYi": money_yi(num(row.get("f20"))),
                "floatMarketCapYi": money_yi(num(row.get("f21"))),
                "pb": num(row.get("f23")),
            }
        )
    return leaders


def get_sector_klines(code: str, days: int = TREND_DAYS) -> list[dict[str, Any]]:
    # Fetch a longer window because non-trading days are omitted by the endpoint.
    today = dt.date.today()
    begin = (today - dt.timedelta(days=35)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid=90.{urllib.parse.quote(code)}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&ut={EASTMONEY_UT}&klt=101&fqt=1&beg={begin}&end={end}&lmt=40"
    )
    payload = fetch_eastmoney_json(url)
    rows = payload.get("data", {}).get("klines") or []
    parsed = []
    for row in rows[-days:]:
        parts = row.split(",")
        if len(parts) < 11:
            continue
        parsed.append(
            {
                "date": parts[0],
                "open": num(parts[1]),
                "close": num(parts[2]),
                "high": num(parts[3]),
                "low": num(parts[4]),
                "volume": num(parts[5]),
                "amountYi": money_yi(num(parts[6])),
                "amplitude": num(parts[7]),
                "pct": num(parts[8]),
                "change": num(parts[9]),
                "turnover": num(parts[10]),
            }
        )
    return parsed


def clone_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def apply_trend_cache(
    sector: dict[str, Any],
    code: str,
    now: float,
    source: str,
) -> bool:
    cached = _trend_cache.get(code)
    if not cached:
        return False
    trend = clone_rows(cached["rows"])
    sector["trend10"] = trend
    sector["trend5"] = trend
    sector["trend10Source"] = source
    sector["trend10Cached"] = True
    sector["trend10CachedAt"] = cached["updatedAt"]
    sector["trend10CacheAgeSeconds"] = round(now - cached["ts"])
    return True


def store_trend_cache(code: str, trend: list[dict[str, Any]], now: float) -> str:
    updated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    _trend_cache[code] = {
        "ts": now,
        "updatedAt": updated_at,
        "rows": clone_rows(trend),
    }
    return updated_at


def store_sector_rank_cache(sectors: list[dict[str, Any]], now: float) -> str:
    updated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    _sector_rank_cache["ts"] = now
    _sector_rank_cache["updatedAt"] = updated_at
    _sector_rank_cache["rows"] = clone_rows(sectors)
    return updated_at


def apply_sector_rank_cache(
    now: float,
    reason: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    rows = _sector_rank_cache.get("rows") or []
    ts = float(_sector_rank_cache.get("ts") or 0)
    if not rows or now - ts > SECTOR_RANK_CACHE_MAX_AGE_SECONDS:
        return None
    updated_at = _sector_rank_cache.get("updatedAt")
    return clone_rows(rows), {
        "ready": True,
        "reason": reason,
        "message": "沿用上一次成功板块排行。",
        "cached": True,
        "cachedAt": updated_at,
        "cacheAgeSeconds": round(now - ts),
    }


def summarize_map_param(payload: dict[str, Any]) -> dict[str, Any]:
    values = []
    data = payload.get("data")
    if isinstance(data, dict):
        for raw in data.values():
            if not isinstance(raw, str):
                continue
            value = num(raw.split("|", 1)[0])
            if value is not None:
                values.append(value)
    values.sort()
    if not values:
        return {"n": 0, "median": None, "upPct": None, "downPct": None}
    up = sum(1 for value in values if value > 0)
    down = sum(1 for value in values if value < 0)
    return {
        "n": len(values),
        "median": round(statistics.median(values), 2),
        "mean": round(statistics.mean(values), 2),
        "p25": round(values[int(0.25 * (len(values) - 1))], 2),
        "p75": round(values[int(0.75 * (len(values) - 1))], 2),
        "upPct": round(up / len(values) * 100, 2),
        "downPct": round(down / len(values) * 100, 2),
    }


def get_market_distribution() -> dict[str, Any]:
    url = "https://data.dapanyuntu.com/dpyt/getMapParamDataV2?param=mkt_idx.cur_chng_pct"
    return summarize_map_param(fetch_json(url, DAPANYUNTU_REFERER))


def summarize_breadth(payload: dict[str, Any]) -> dict[str, Any]:
    dates = payload.get("dates") or []
    industries = payload.get("industries") or []
    data = payload.get("data") or []
    by_industry = {industry: [None] * len(dates) for industry in industries}
    for date_idx, industry_idx, ratio in data:
        try:
            by_industry[industries[industry_idx]][date_idx] = float(ratio)
        except (IndexError, TypeError, ValueError):
            continue
    rows = []
    for industry, values in by_industry.items():
        clean = [value for value in values if value is not None]
        if len(clean) < 5:
            continue
        last5 = clean[-5:]
        previous5 = clean[-10:-5] if len(clean) >= 10 else []
        avg5 = statistics.mean(last5)
        prev_avg5 = statistics.mean(previous5) if previous5 else avg5
        latest = clean[-1]
        rows.append(
            {
                "industry": industry,
                "latest": round(latest, 2),
                "avg5": round(avg5, 2),
                "days70": sum(1 for value in clean if value >= 70),
                "daysTotal": len(clean),
                "slope5": round(avg5 - prev_avg5, 2),
                "last5": [round(value, 2) for value in last5],
                "isCurrentR02": industry in {R02_CURRENT["primary"], R02_CURRENT["secondary"]},
            }
        )
    rows.sort(key=lambda row: (row["avg5"], row["latest"], row["days70"]), reverse=True)
    return {
        "dateStart": dates[0] if dates else None,
        "dateEnd": dates[-1] if dates else None,
        "rows": rows[:12],
    }


def get_r02_breadth() -> dict[str, Any]:
    today = dt.date.today()
    start = (today - dt.timedelta(days=60)).isoformat()
    end = today.isoformat()
    url = (
        "https://sckd.dapanyuntu.com/api/api/industry_ma20_analysis_range"
        f"?start_date={urllib.parse.quote(start)}&end_date={urllib.parse.quote(end)}"
    )
    return summarize_breadth(fetch_json(url, SCKD_REFERER))


def build_dashboard_payload(force: bool = False) -> dict[str, Any]:
    now = time.time()
    if not force and _cache["payload"] and now - _cache["ts"] < CACHE_TTL_SECONDS:
        cached = dict(_cache["payload"])
        cached["cacheAgeSeconds"] = round(now - _cache["ts"])
        return cached

    warnings = []
    indices: list[dict[str, Any]] = []
    market_distribution: dict[str, Any] = {}
    r02_breadth: dict[str, Any] = {}
    sectors: list[dict[str, Any]] = []
    sector_rank_status = {
        "ready": False,
        "reason": "pending",
        "message": "板块排行等待更新。",
    }

    def read_future(
        label: str,
        future: concurrent.futures.Future[Any],
        default: Any,
    ) -> Any:
        try:
            return future.result()
        except Exception as exc:
            warnings.append(f"{label}: {exc}")
            return default

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        base_futures = {
            "indices": executor.submit(get_market_indices),
            "marketDistribution": executor.submit(get_market_distribution),
            "r02Breadth": executor.submit(get_r02_breadth),
            "sectorRank": executor.submit(get_sector_rank, 30),
        }
        indices = read_future("indices", base_futures["indices"], [])
        market_distribution = read_future(
            "marketDistribution",
            base_futures["marketDistribution"],
            {},
        )
        r02_breadth = read_future("r02Breadth", base_futures["r02Breadth"], {})
        try:
            sectors = base_futures["sectorRank"].result()
        except Exception as exc:
            sector_rank_error = str(exc)
            warnings.append(f"sectorRank: {sector_rank_error}")
            sectors = []
        else:
            sector_rank_error = None
        sector_rank_status = build_sector_rank_status(sectors, sector_rank_error)
        if sector_rank_status["ready"]:
            sector_rank_status["cached"] = False
            sector_rank_status["updatedAt"] = store_sector_rank_cache(sectors, now)
        else:
            cached_rank = apply_sector_rank_cache(
                now,
                f"server-cache-after-{sector_rank_status['reason']}",
            )
            if cached_rank:
                sectors, cached_status = cached_rank
                cached_status["fallbackReason"] = sector_rank_status["reason"]
                cached_status["fallbackMessage"] = sector_rank_status["message"]
                if sector_rank_status.get("detail"):
                    cached_status["detail"] = sector_rank_status["detail"]
                sector_rank_status = cached_status
                warnings.append(
                    f"sectorRank {sector_rank_status['fallbackReason']}; using cached rank "
                    f"from {sector_rank_status['cachedAt']}"
                )

    top_sectors = sectors[:5] if sector_rank_status["ready"] else []
    if top_sectors:
        detail_workers = min(API_WORKERS, max(1, len(top_sectors)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=detail_workers) as executor:
            leader_futures = {}
            for sector in top_sectors:
                code = str(sector.get("code") or "")
                leader_futures[executor.submit(get_sector_leaders, code, 10)] = (
                    sector,
                    code,
                )

            for sector in top_sectors:
                code = str(sector.get("code") or "")
                cached = _trend_cache.get(code)
                if cached and now - cached["ts"] < TREND_CACHE_TTL_SECONDS:
                    apply_trend_cache(sector, code, now, "server-cache")
                    continue

                try:
                    trend = get_sector_klines(code, TREND_DAYS)
                    if len(trend) < 2:
                        raise FetchError(f"not enough kline rows: {len(trend)}")
                    sector["trend10"] = trend
                    sector["trend5"] = trend
                    sector["trend10Source"] = "live"
                    sector["trend10Cached"] = False
                    sector["trend10UpdatedAt"] = store_trend_cache(code, trend, now)
                except Exception as exc:
                    if apply_trend_cache(sector, code, now, "server-cache-stale"):
                        warnings.append(
                            f"{code} kline: {exc}; using cached trend from "
                            f"{sector['trend10CachedAt']}"
                        )
                    else:
                        sector["trend10"] = []
                        sector["trend5"] = []
                        sector["trend10Source"] = "missing"
                        sector["trend10Cached"] = False
                        warnings.append(f"{code} kline: {exc}")

            for future in concurrent.futures.as_completed(leader_futures):
                sector, code = leader_futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    sector["leaders10"] = []
                    warnings.append(f"{code} leaders: {exc}")
                    continue

                sector["leaders10"] = result

    for sector in top_sectors:
        sector.setdefault("trend10", [])
        sector.setdefault("trend5", sector["trend10"])
        sector.setdefault("leaders10", [])

    payload = {
        "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "cacheTtlSeconds": CACHE_TTL_SECONDS,
        "cacheAgeSeconds": 0,
        "trendDays": TREND_DAYS,
        "trendCacheTtlSeconds": TREND_CACHE_TTL_SECONDS,
        "sectorRankCacheMaxAgeSeconds": SECTOR_RANK_CACHE_MAX_AGE_SECONDS,
        "source": {
            "sectorRank": "Eastmoney push2/push2delay clist, fs=m:90+t:2, sorted by f3",
            "sectorKline": "Eastmoney push2his/push2delay daily kline, secid=90.BKxxxx",
            "sectorLeaders": "Eastmoney push2/push2delay clist, fs=b:BKxxxx, sorted by f3",
            "indices": "Eastmoney push2/push2delay ulist",
            "marketDistribution": "Dapanyuntu mkt_idx.cur_chng_pct",
            "r02Breadth": "Dapanyuntu industry_ma20_analysis_range",
        },
        "r02": R02_CURRENT,
        "indices": indices,
        "marketDistribution": market_distribution,
        "sectorRankStatus": sector_rank_status,
        "r02Breadth": r02_breadth,
        "sectors": sectors,
        "top5": top_sectors,
        "warnings": warnings,
    }
    _cache["ts"] = now
    _cache["payload"] = payload
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "R02SectorDashboard/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in STATIC_FILES:
            path, content_type = STATIC_FILES[parsed.path]
            self.serve_file(path, content_type)
            return
        if parsed.path.startswith("/m2-assets/"):
            asset_name = urllib.parse.unquote(parsed.path.removeprefix("/m2-assets/"))
            if not asset_name or Path(asset_name).name != asset_name:
                self.send_error(404, "Not found")
                return
            content_type = "image/jpeg" if asset_name.lower().endswith((".jpg", ".jpeg")) else "image/png"
            self.serve_file(ROOT / "m2-assets" / asset_name, content_type)
            return
        if parsed.path == "/api/dashboard":
            params = urllib.parse.parse_qs(parsed.query)
            force = params.get("force", ["0"])[0] == "1"
            self.serve_json(build_dashboard_payload(force=force))
            return
        if parsed.path == "/api/m2-watchlist":
            params = urllib.parse.parse_qs(parsed.query)
            dynamic = params.get("dynamic", ["0"])[0] == "1"
            force = params.get("force", ["0"])[0] == "1"
            payload = get_m2_watchlist_payload(force=force) if dynamic else get_m2_watchlist_snapshot_payload()
            self.serve_json(payload)
            return
        if parsed.path == "/api/m2-history":
            params = urllib.parse.parse_qs(parsed.query)
            dynamic = params.get("dynamic", ["0"])[0] == "1"
            force = params.get("force", ["0"])[0] == "1"
            payload = get_m2_history_payload(force=force) if dynamic else get_m2_snapshot_payload()
            self.serve_json(payload)
            return
        self.send_error(404, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def serve_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local R02 sector dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("R02_DASHBOARD_PORT", "8765")))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"R02 sector dashboard: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
