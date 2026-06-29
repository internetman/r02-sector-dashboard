#!/usr/bin/env python3
"""Local R02 sector dashboard server.

The server calls public frontend APIs from Eastmoney and Dapanyuntu, then serves a
small dashboard at http://127.0.0.1:8765/.  It intentionally keeps a short cache
to avoid aggressive polling of public data sources.
"""

from __future__ import annotations

import argparse
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

EASTMONEY_REFERER = "https://quote.eastmoney.com/"
DAPANYUNTU_REFERER = "https://dapanyuntu.com/"
SCKD_REFERER = "https://sckd.dapanyuntu.com/"

INDEX_SECIDS = "1.000001,0.399006,1.000688,100.NDX,100.HSI"
TREND_DAYS = 10

R02_CURRENT = {
    "updated": "2026-06-26",
    "primary": "电子化学品",
    "secondary": "半导体",
    "note": "正式 R02 仍以行业市场宽度为准；实时板块涨跌只作为盘中温度计。",
}

_cache: dict[str, Any] = {"ts": 0.0, "payload": None}


class FetchError(RuntimeError):
    pass


def fetch_json(url: str, referer: str, timeout: float = 8.0) -> dict[str, Any]:
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
        f"&klt=101&fqt=1&beg={begin}&end={end}&lmt=40"
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
    indices = []
    market_distribution = {}
    r02_breadth = {}
    sectors = []

    try:
        indices = get_market_indices()
    except Exception as exc:
        warnings.append(str(exc))

    try:
        market_distribution = get_market_distribution()
    except Exception as exc:
        warnings.append(str(exc))

    try:
        r02_breadth = get_r02_breadth()
    except Exception as exc:
        warnings.append(str(exc))

    try:
        sectors = get_sector_rank(30)
        for sector in sectors[:5]:
            try:
                trend = get_sector_klines(sector["code"], TREND_DAYS)
                sector["trend10"] = trend
                sector["trend5"] = trend
            except Exception as exc:
                sector["trend10"] = []
                sector["trend5"] = []
                warnings.append(f"{sector['code']} kline: {exc}")
            try:
                sector["leaders10"] = get_sector_leaders(sector["code"], 10)
            except Exception as exc:
                sector["leaders10"] = []
                warnings.append(f"{sector['code']} leaders: {exc}")
    except Exception as exc:
        warnings.append(str(exc))

    payload = {
        "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "cacheTtlSeconds": CACHE_TTL_SECONDS,
        "cacheAgeSeconds": 0,
        "trendDays": TREND_DAYS,
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
