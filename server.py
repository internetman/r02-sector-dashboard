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
import statistics
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CACHE_TTL_SECONDS = 45
TREND_CACHE_TTL_SECONDS = int(os.environ.get("R02_TREND_CACHE_TTL_SECONDS", "1800"))
FETCH_TIMEOUT_SECONDS = float(os.environ.get("R02_FETCH_TIMEOUT_SECONDS", "4"))
API_WORKERS = int(os.environ.get("R02_API_WORKERS", "12"))

EASTMONEY_REFERER = "https://quote.eastmoney.com/"
EASTMONEY_UT = "fa5fd1943c7b386f172d6893dbfba10b"
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

_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_trend_cache: dict[str, dict[str, Any]] = {}


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
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - surfaced to dashboard
        raise FetchError(f"fetch failed: {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid json: {url}: {raw[:160]}") from exc


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
    payload = fetch_json(url, EASTMONEY_REFERER)
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


def get_sector_rank(limit: int = 20) -> list[dict[str, Any]]:
    fields = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f20,f104,f105,f128,f136,f140"
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs=m:90+t:2&fields={fields}"
    )
    payload = fetch_json(url, EASTMONEY_REFERER)
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


def get_sector_leaders(code: str, limit: int = 10) -> list[dict[str, Any]]:
    fields = "f12,f14,f2,f3,f4,f6,f7,f8,f10,f20,f21,f23"
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fs=b:{urllib.parse.quote(code)}&fields={fields}"
    )
    payload = fetch_json(url, EASTMONEY_REFERER)
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
    payload = fetch_json(url, EASTMONEY_REFERER)
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
        sectors = read_future("sectorRank", base_futures["sectorRank"], [])

    top_sectors = sectors[:5]
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
        "source": {
            "sectorRank": "Eastmoney push2 clist, fs=m:90+t:2, sorted by f3",
            "sectorKline": "Eastmoney push2his daily kline, secid=90.BKxxxx",
            "sectorLeaders": "Eastmoney push2 clist, fs=b:BKxxxx, sorted by f3",
            "indices": "Eastmoney push2 ulist",
            "marketDistribution": "Dapanyuntu mkt_idx.cur_chng_pct",
            "r02Breadth": "Dapanyuntu industry_ma20_analysis_range",
        },
        "r02": R02_CURRENT,
        "indices": indices,
        "marketDistribution": market_distribution,
        "r02Breadth": r02_breadth,
        "sectors": sectors,
        "top5": sectors[:5],
        "warnings": warnings,
    }
    _cache["ts"] = now
    _cache["payload"] = payload
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "R02SectorDashboard/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(ROOT / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/dashboard":
            params = urllib.parse.parse_qs(parsed.query)
            force = params.get("force", ["0"])[0] == "1"
            self.serve_json(build_dashboard_payload(force=force))
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
