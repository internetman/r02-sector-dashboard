#!/usr/bin/env python3
"""Generate the M2 website data files from S1->S2 and S2 iWencai exports."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


BASE_COLS = {
    "code": "股票代码",
    "name": "股票简称",
    "price": "现价(元)",
    "pct": "涨跌幅(%)",
}

FORMAL_STAGES = {"S1→S2过渡", "S2趋势", "S2延伸"}
S2_STAGES = {"S2趋势", "S2延伸", "S2转弱"}


def infer_close_date(path: Path, columns: list[str]) -> dt.date:
    for column in columns:
        match = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", str(column))
        if match:
            return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = re.search(r"(\d{1,2})-(\d{1,2})\s*收盘", path.name)
    if match:
        return dt.date(dt.date.today().year, int(match.group(1)), int(match.group(2)))
    raise ValueError(f"Cannot infer close date from {path}")


def date_label(value: dt.date) -> str:
    return f"{value.month}-{value.day}"


def period_label(column: str, close_date: dt.date) -> str:
    match = re.search(r"20\d{2}\.(\d{2})\.(\d{2})-(\d{4})(\d{2})(\d{2})", column)
    if match:
        return f"{int(match.group(1))}/{int(match.group(2))} → {int(match.group(4))}/{int(match.group(5))}"
    return f"近 20 日 → {date_label(close_date)}"


def infer_columns(columns: list[str], close_date: dt.date) -> tuple[dict[str, str], str]:
    col_dot = close_date.strftime("%Y.%m.%d")

    def find_one(key: str, predicate) -> str:
        matches = [column for column in columns if predicate(str(column))]
        if not matches:
            raise ValueError(f"Missing required column for {key} on {col_dot}")
        return matches[0]

    def find_optional(predicate) -> str | None:
        matches = [column for column in columns if predicate(str(column))]
        return matches[0] if matches else None

    out = dict(BASE_COLS)
    out.update(
        {
            "close": find_one("close", lambda c: c.startswith("收盘价:前复权") and col_dot in c),
            "ma50": find_one("ma50", lambda c: c.startswith("ma50(元)") and col_dot in c),
            "ma150": find_one("ma150", lambda c: c.startswith("ma150(元)") and col_dot in c),
            "ma200": find_one("ma200", lambda c: c.startswith("ma200(元)") and col_dot in c),
            "period_pct": find_one("period_pct", lambda c: c.startswith("涨跌幅(%)\n")),
            "low52": find_one("low52", lambda c: c.startswith("最低价最小值(元)")),
            "high52": find_one("high52", lambda c: c.startswith("最高价最大值(元)")),
            "avg_amount": find_one("avg_amount", lambda c: c.startswith("成交额平均值(元)")),
            "market_cap": find_optional(lambda c: c.startswith("总市值(元)") and col_dot in c),
            "open": find_one("open", lambda c: c.startswith("开盘价") and "前复权" in c and col_dot in c),
            "high": find_one("high", lambda c: c.startswith("最高价") and "前复权" in c and col_dot in c),
            "low": find_one("low", lambda c: c.startswith("最低价") and "前复权" in c and col_dot in c),
            "pb": find_optional(lambda c: c.startswith("市净率") and col_dot in c),
            "float_market_cap": find_optional(lambda c: c.startswith("a股流通市值(元)") and col_dot in c),
            "pe": find_optional(lambda c: c.startswith("动态市盈率") and col_dot in c),
        }
    )
    return out, period_label(out["period_pct"], close_date)


def find_column(columns: list[str], predicate) -> str | None:
    return next((column for column in columns if predicate(str(column))), None)


def read_stage_export(path: Path, pool: str) -> tuple[dt.date, dict[str, dict[str, Any]]]:
    frame = pd.read_excel(path)
    columns = [str(column) for column in frame.columns]
    close_date = infer_close_date(path, columns)
    col_dot = close_date.strftime("%Y.%m.%d")
    code_col = BASE_COLS["code"]
    name_col = BASE_COLS["name"]
    price_col = BASE_COLS["price"]
    pct_col = BASE_COLS["pct"]
    if any(column not in frame.columns for column in (code_col, name_col, price_col, pct_col)):
        raise ValueError(f"{path.name} 缺少股票代码、简称、现价或涨跌幅字段")
    frame = frame[frame[code_col].astype(str).str.match(r"^\d{6}\.(SZ|SH|BJ)$", na=False)].copy()
    if frame[code_col].astype(str).duplicated().any():
        duplicates = frame.loc[frame[code_col].astype(str).duplicated(), code_col].tolist()
        raise ValueError(f"{path.name} 股票代码重复：{duplicates[:10]}")

    keys = {
        "close": find_column(columns, lambda c: c.startswith("收盘价:前复权") and col_dot in c),
        "open": find_column(columns, lambda c: c.startswith("开盘价:前复权") and col_dot in c),
        "high": find_column(columns, lambda c: c.startswith("最高价:前复权") and col_dot in c),
        "low": find_column(columns, lambda c: c.startswith("最低价:前复权") and col_dot in c),
        "ma50": find_column(columns, lambda c: c.startswith("ma50(元)") and col_dot in c),
        "ma150": find_column(columns, lambda c: c.startswith("ma150(元)") and col_dot in c),
        "ma200": find_column(columns, lambda c: c.startswith("ma200(元)") and col_dot in c),
        "periodPct": find_column(columns, lambda c: c.startswith("涨跌幅(%)\n")),
        "high52": find_column(columns, lambda c: c.startswith("最高价最大值(元)")),
        "low52": find_column(columns, lambda c: c.startswith("最低价最小值(元)")),
    }
    records: dict[str, dict[str, Any]] = {}
    for _, source in frame.iterrows():
        code = str(source[code_col])
        record = {
            "code": code,
            "name": str(source[name_col]).strip(),
            "price": finite(source[price_col]),
            "pct": finite(source[pct_col]),
            "pools": [pool],
            "sourceFile": path.name,
        }
        for key, column in keys.items():
            record[key] = finite(source[column]) if column else None
        if record["close"] is not None:
            record["price"] = record["close"]
        records[code] = record
    return close_date, records


def merge_stage_exports(*exports: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for export in exports:
        for code, incoming in export.items():
            if code not in merged:
                merged[code] = dict(incoming)
                continue
            current = merged[code]
            current["pools"] = list(dict.fromkeys([*(current.get("pools") or []), *(incoming.get("pools") or [])]))
            for key, value in incoming.items():
                if key != "pools" and value not in (None, "", "--"):
                    current[key] = value
    return merged


def finite(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def market_for(code: str) -> str:
    return "1" if code.endswith(".SH") else "0"


def exchange_for(code: str) -> str:
    if code.endswith(".SH"):
        return "上交所"
    if code.endswith(".BJ"):
        return "北交所"
    return "深交所"


def bare(code: str) -> str:
    return str(code).split(".", 1)[0]


def pct_text(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:+.{digits}f}%"


def amount_yi(value: float | None) -> float | None:
    return round(value / 100000000, 2) if value is not None else None


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_snapshot_bundle(snapshot: dict[str, Any]) -> None:
    """Write the full API snapshot plus small files for lazy chart loading."""
    history = snapshot.get("history") if isinstance(snapshot.get("history"), dict) else {}
    history_dir = ROOT / "m2-history"
    history_dir.mkdir(exist_ok=True)
    expected_files = {f"{bare(code)}.json" for code in history}
    for old_file in history_dir.glob("*.json"):
        if old_file.name not in expected_files:
            old_file.unlink()
    for code, payload in history.items():
        (history_dir / f"{bare(code)}.json").write_text(js(payload), encoding="utf-8")

    quote_codes = {bare(item.get("code") or item.get("symbol")) for item in snapshot.get("quotes") or []}
    available_codes = sorted({bare(code) for code in history})
    index = {
        "schemaVersion": 1,
        "generatedAt": snapshot.get("generatedAt"),
        "asOf": snapshot.get("asOf"),
        "maxAgeHours": snapshot.get("maxAgeHours"),
        "barStatus": snapshot.get("barStatus"),
        "sourceStatus": snapshot.get("sourceStatus"),
        "source": snapshot.get("source"),
        "totalCount": len(quote_codes),
        "availableCount": len(available_codes),
        "availableCodes": available_codes,
        "missingCodes": sorted(quote_codes - set(available_codes)),
        "warnings": snapshot.get("warnings") or [],
    }
    (ROOT / "m2-history-index.json").write_text(js(index), encoding="utf-8")
    (ROOT / "m2-snapshot.json").write_text(js(snapshot), encoding="utf-8")


def load_old_rows(path: Path) -> list[list[Any]]:
    source = path.read_text(encoding="utf-8")
    match = re.search(r"const raw\s*=\s*(\[\[.*?\]\]);\s*const rows", source, re.S)
    if not match:
        return []
    return json.loads(match.group(1))


def fetch_quotes(codes: list[str]) -> tuple[dict[str, dict[str, Any]], str]:
    quotes: dict[str, dict[str, Any]] = {}
    fields = "f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f9,f15,f16,f17,f18,f20,f21"
    for index in range(0, len(codes), 80):
        chunk = codes[index : index + 80]
        secids = ",".join(f"{market_for(code)}.{bare(code)}" for code in chunk)
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get"
            f"?fltt=2&invt=2&fields={fields}&secids="
            + urllib.parse.quote(secids, safe=".,")
        )
        payload = server.fetch_eastmoney_json(url)
        for row in payload.get("data", {}).get("diff") or []:
            quotes[str(row.get("f12"))] = row
    return quotes, "Eastmoney push2/push2delay ulist"


def fetch_history(item: dict[str, str], close_date: dt.date) -> dict[str, Any] | None:
    for attempt in range(3):
        try:
            return server._get_m2_history(item, close_date)
        except Exception:
            if attempt < 2:
                time.sleep(0.6 + attempt * 0.8)
    return None


def load_snapshot_history(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    history = payload.get("history") if "history" in payload else payload
    return history if isinstance(history, dict) else {}


def load_committed_snapshot_history() -> dict[str, dict[str, Any]]:
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:m2-snapshot.json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return {}
    history = payload.get("history")
    return history if isinstance(history, dict) else {}


def append_current_bar(
    history: dict[str, Any] | None,
    current: dict[str, Any],
    close_date: dt.date,
) -> dict[str, Any] | None:
    if not history:
        return None
    close_iso = close_date.isoformat()
    rows = [row for row in history.get("rows", []) if str(row.get("date")) < close_iso]
    current_bar = {
        "date": close_iso,
        "open": current.get("open"),
        "close": current.get("price"),
        "high": current.get("high"),
        "low": current.get("low"),
        "volume": current.get("volumeLots"),
        "amountYi": current.get("amountYi"),
        "amplitude": current.get("amplitude"),
        "pct": current.get("pct"),
        "change": current.get("change"),
        "turnover": current.get("turnover"),
    }
    if current_bar["open"] is None:
        current_bar["open"] = current_bar["close"]
    if current_bar["high"] is None:
        current_bar["high"] = current_bar["close"]
    if current_bar["low"] is None:
        current_bar["low"] = current_bar["close"]
    rows.append(current_bar)
    for index, row in enumerate(rows):
        for window, key in ((50, "ma50"), (150, "ma150"), (200, "ma200")):
            if index + 1 >= window:
                closes = [finite(point.get("close")) for point in rows[index + 1 - window : index + 1]]
                closes = [value for value in closes if value is not None]
                row[key] = sum(closes) / window if len(closes) == window else None
            else:
                row[key] = None
    metrics = calc_metrics(rows, str(history.get("code") or ""))
    return {
        **history,
        "asOf": close_iso,
        "rows": rows[-250:],
        "metrics": {
            **(history.get("metrics") or {}),
            **metrics,
            "source": f"Tencent/Eastmoney history plus {close_iso} close quote/import append",
        },
    }


def avg_field(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [finite(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def range_pct(rows: list[dict[str, Any]]) -> float | None:
    highs = [finite(row.get("high")) for row in rows]
    lows = [finite(row.get("low")) for row in rows]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    if not highs or not lows or max(highs) <= 0:
        return None
    return (max(highs) - min(lows)) / max(highs) * 100


def row_amount_yi(row: dict[str, Any], volume_multiplier: int = 100) -> float | None:
    amount = finite(row.get("amountYi"))
    if amount is not None:
        return amount
    close = finite(row.get("close"))
    volume_lots = finite(row.get("volume"))
    return close * volume_lots * volume_multiplier / 100000000 if close and volume_lots else None


def weekly_supply_metrics(rows: list[dict[str, Any]], volume_multiplier: int = 100) -> dict[str, Any]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows[-70:]:
        try:
            day = dt.date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        iso = day.isocalendar()
        groups.setdefault((iso.year, iso.week), []).append(row)
    weeks = []
    for points in list(groups.values())[-10:]:
        open_price = finite(points[0].get("open"))
        close_price = finite(points[-1].get("close"))
        amounts = [row_amount_yi(point, volume_multiplier) for point in points]
        amounts = [value for value in amounts if value is not None]
        if open_price and close_price and amounts:
            weeks.append({"up": close_price > open_price, "amountYi": sum(amounts)})
    if not weeks:
        return {
            "weeklyUpVolumeCount": None,
            "weeklyDownVolumeCount": None,
            "demandSupplyRatio10w": None,
            "strongVolumeUpWeek": None,
        }
    average = sum(week["amountYi"] for week in weeks) / len(weeks)
    large = [week for week in weeks if week["amountYi"] >= average]
    up_large = [week for week in large if week["up"]]
    down_large = [week for week in large if not week["up"]]
    demand = sum(week["amountYi"] for week in weeks if week["up"])
    supply = sum(week["amountYi"] for week in weeks if not week["up"])
    return {
        "weeklyUpVolumeCount": len(up_large),
        "weeklyDownVolumeCount": len(down_large),
        "demandSupplyRatio10w": round(demand / supply, 2) if supply else (99.0 if demand else None),
        "strongVolumeUpWeek": any(week["up"] and week["amountYi"] >= average * 1.3 for week in weeks),
    }


def calc_metrics(rows: list[dict[str, Any]], code: str = "") -> dict[str, Any]:
    # Tencent returns STAR-board volume in shares while the other A-share boards
    # use lots. Eastmoney rows already carry amountYi and bypass this fallback.
    volume_multiplier = 1 if str(code).startswith("688") else 100
    contractions = []
    for window in (40, 20, 10):
        if len(rows) < window * 2:
            continue
        previous = rows[-window * 2 : -window]
        current = rows[-window:]
        previous_range = range_pct(previous)
        current_range = range_pct(current)
        previous_volume = avg_field(previous, "volume")
        current_volume = avg_field(current, "volume")
        if (
            previous_range is not None
            and current_range is not None
            and previous_volume
            and current_volume
            and current_range <= previous_range * 0.9
            and current_volume <= previous_volume * 0.95
        ):
            contractions.append(
                {
                    "window": window,
                    "startDate": current[0]["date"],
                    "endDate": current[-1]["date"],
                    "rangePct": round(current_range, 2),
                    "volumeRatio": round(current_volume / previous_volume, 2),
                }
            )
    base_depth = range_pct(rows[-40:])
    range20 = range_pct(rows[-20:])
    recent_volume = avg_field(rows[-5:], "volume")
    prior_volume = avg_field(rows[-25:-5], "volume")
    last = rows[-1] if rows else {}
    last_ma50 = finite(last.get("ma50"))
    last_ma200 = finite(last.get("ma200"))
    prior_ma50 = finite(rows[-21].get("ma50")) if len(rows) >= 21 else None
    prior_ma200 = finite(rows[-21].get("ma200")) if len(rows) >= 21 else None
    ma200_points = {
        days: finite(rows[-1 - days].get("ma200")) if len(rows) > days else None
        for days in (5, 10, 20)
    }
    latest20 = rows[-20:]
    previous20 = rows[-40:-20]
    recent_highs = [finite(row.get("high")) for row in latest20]
    prior_highs = [finite(row.get("high")) for row in previous20]
    recent_lows = [finite(row.get("low")) for row in latest20]
    prior_lows = [finite(row.get("low")) for row in previous20]
    recent_highs = [value for value in recent_highs if value is not None]
    prior_highs = [value for value in prior_highs if value is not None]
    recent_lows = [value for value in recent_lows if value is not None]
    prior_lows = [value for value in prior_lows if value is not None]
    all_highs = [finite(row.get("high")) for row in rows[-250:]]
    all_lows = [finite(row.get("low")) for row in rows[-250:]]
    all_highs = [value for value in all_highs if value is not None]
    all_lows = [value for value in all_lows if value is not None]
    closes = [finite(row.get("close")) for row in rows]
    current_close = closes[-1] if closes else None
    prior_close20 = closes[-21] if len(closes) >= 21 else None
    avg_amount20_yi = avg_field([{"amount": row_amount_yi(row, volume_multiplier)} for row in latest20], "amount")
    weekly = weekly_supply_metrics(rows, volume_multiplier)
    if len(contractions) >= 2:
        vcp_status = "VCP 候选：价格与量能连续收缩"
    elif len(contractions) == 1:
        vcp_status = "VCP 初步收缩：继续观察"
    else:
        vcp_status = "VCP 收缩未确认"
    return {
        "baseDays": 40,
        "baseDepthPct": round(base_depth, 2) if base_depth is not None else None,
        "range20Pct": round(range20, 2) if range20 is not None else None,
        "volumeDryUpRatio": round(recent_volume / prior_volume, 2) if recent_volume and prior_volume else None,
        "ma200SlopePct20d": round((last_ma200 / prior_ma200 - 1) * 100, 2) if last_ma200 and prior_ma200 else None,
        "ma50SlopePct20d": round((last_ma50 / prior_ma50 - 1) * 100, 2) if last_ma50 and prior_ma50 else None,
        "ma200Monotonic20d": bool(
            last_ma200
            and ma200_points[5]
            and ma200_points[10]
            and ma200_points[20]
            and last_ma200 > ma200_points[5] > ma200_points[10] > ma200_points[20]
        ),
        "ma200Points": {str(key): round(value, 4) if value is not None else None for key, value in ma200_points.items()},
        "high20Higher": max(recent_highs) > max(prior_highs) if recent_highs and prior_highs else None,
        "low20Higher": min(recent_lows) > min(prior_lows) if recent_lows and prior_lows else None,
        "high250": max(all_highs) if all_highs else None,
        "low250": min(all_lows) if all_lows else None,
        "periodPct20d": round((current_close / prior_close20 - 1) * 100, 2) if current_close and prior_close20 else None,
        "avgAmount20Yi": round(avg_amount20_yi, 2) if avg_amount20_yi is not None else None,
        "contractionCount": len(contractions),
        "contractions": contractions,
        "vcpStatus": vcp_status,
        **weekly,
    }


def derive_prior_pivot(history: dict[str, Any] | None, close_date: dt.date) -> dict[str, Any]:
    rows = (history or {}).get("rows") or []
    close_iso = close_date.isoformat()
    usable = [row for row in rows if str(row.get("date")) < close_iso and finite(row.get("high")) is not None]
    if not usable:
        return {"price": None, "date": "", "lookback": None}
    windows = [
        int(item["window"])
        for item in (history.get("metrics", {}) if history else {}).get("contractions", [])
        if finite(item.get("window")) is not None and int(item["window"]) >= 5
    ]
    lookback = min(windows) if windows else 20
    sample = usable[-lookback:]
    high_row = max(sample, key=lambda row: finite(row.get("high")) or 0)
    return {"price": finite(high_row.get("high")), "date": high_row.get("date") or "", "lookback": lookback}


def classify_stage(row: dict[str, Any], metrics: dict[str, Any], ever_s2: bool) -> tuple[str, str]:
    price = finite(row.get("price"))
    ma50 = finite(row.get("ma50"))
    ma150 = finite(row.get("ma150"))
    ma200 = finite(row.get("ma200"))
    slope200 = finite(metrics.get("ma200SlopePct20d"))
    slope50 = finite(metrics.get("ma50SlopePct20d"))
    period_pct = finite(metrics.get("periodPct20d"))
    high250 = finite(metrics.get("high250"))
    low250 = finite(metrics.get("low250"))
    required = (price, ma50, ma150, ma200, slope200, slope50, high250, low250)
    if any(value is None for value in required):
        return "待复核", "历史日K或均线数据不足，不能按新规则硬判通过。"
    from_low = (price / low250 - 1) * 100
    from_high = (price / high250 - 1) * 100
    price_to_ma50 = (price / ma50 - 1) * 100
    s2_structure = (
        price > ma50 > ma150 > ma200
        and slope200 >= 0.20
        and from_low > 25
        and from_high >= -25
    )
    if s2_structure:
        if (period_pct is not None and period_pct > 30) or price_to_ma50 > 15:
            return "S2延伸", f"多头排列成立；近20日 {pct_text(period_pct)}、距MA50 {pct_text(price_to_ma50)}，位置过度延伸。"
        return "S2趋势", f"收盘价 > MA50 > MA150 > MA200；MA200近20日 {pct_text(slope200, 2)}。"
    if ever_s2:
        return "S2转弱", f"曾进入S2，但当前完整多头排列或趋势条件已破坏；MA200近20日 {pct_text(slope200, 2)}。"
    transition = (
        price > ma150
        and price > ma200
        and ma150 > ma200
        and slope200 >= 0.20
        and bool(metrics.get("ma200Monotonic20d"))
        and slope50 > 0
    )
    if transition:
        return "S1→S2过渡", f"价格站上MA150/MA200，MA200近20日 {pct_text(slope200, 2)}且连续上行，MA50斜率 {pct_text(slope50, 2)}。"
    return "待复核", f"未同时满足S1→S2或S2硬条件；MA200近20日 {pct_text(slope200, 2)}、MA50近20日 {pct_text(slope50, 2)}。"


def classify(row: dict[str, Any], pivot: dict[str, Any], metrics: dict[str, Any], close_label: str) -> dict[str, Any]:
    stage = row.get("stage")
    if stage in {"待复核", "S2转弱"}:
        return {
            "recommendation": "待复核，不直接买",
            "className": "review",
            "reason": f"{stage}：{row.get('stageReason') or '先复核趋势和图形。'}",
            "stars": 1,
            "label": "1星 待复核",
            "action": "趋势结构未确认，先复核，不执行。",
            "buyRank": 0,
        }
    if stage == "S1→S2过渡":
        return {
            "recommendation": "过渡观察",
            "className": "wait",
            "reason": "处于S1→S2过渡池，先等待完整S2结构和规则化Pivot。",
            "stars": 2,
            "label": "2星 过渡观察",
            "action": "只跟踪阶段变化，不提前当作S2买点。",
            "buyRank": 10,
        }
    if stage == "S2延伸":
        return {
            "recommendation": "过热不追",
            "className": "caution",
            "reason": row.get("stageReason") or "S2结构仍在，但位置过度延伸。",
            "stars": 1,
            "label": "1星 不追",
            "action": "等待回踩MA50或形成新平台。",
            "buyRank": 0,
        }
    price = finite(row["price"])
    pivot_price = finite(pivot.get("price"))
    distance = (pivot_price - price) / price * 100 if price and pivot_price else None
    breakout = (price / pivot_price - 1) * 100 if price and pivot_price else None
    amount_ratio = row.get("amountRatio")
    avg_amount20_yi = finite(metrics.get("avgAmount20Yi"))
    stop_distance = finite(row.get("stopDistancePct"))
    contractions = int(metrics.get("contractionCount") or 0)
    base_depth = finite(metrics.get("baseDepthPct"))
    from_high = finite(row.get("fromHighPct"))
    price_to_ma50 = row.get("priceToMa50Pct")
    pct = finite(row.get("pct")) or 0
    if pct >= 8 or (price_to_ma50 is not None and price_to_ma50 > 25) or (distance is not None and distance < -6):
        return {
            "recommendation": "过热不追",
            "className": "caution",
            "reason": f"收盘涨幅/偏离较高（涨跌 {pct_text(pct, 2)}，距 MA50 {pct_text(price_to_ma50, 1)}），等回踩或新平台。",
            "stars": 1,
            "label": "1星 不追",
            "action": "涨幅或均线偏离过高，等回踩或新平台。",
            "buyRank": 0,
        }
    if (
        distance is not None
        and breakout is not None
        and breakout >= 0
        and breakout <= 3
        and (amount_ratio or 0) >= 1.3
        and contractions >= 2
        and base_depth is not None
        and base_depth <= 40
        and from_high is not None
        and from_high >= -25
        and (price_to_ma50 is None or price_to_ma50 <= 15)
        and pct <= 5
        and avg_amount20_yi is not None
        and avg_amount20_yi >= 1
        and stop_distance is not None
        and stop_distance <= 8
    ):
        return {
            "recommendation": "5星可执行，收盘突破",
            "className": "execute",
            "reason": f"收盘站上参考 Pivot {pivot_price:.2f}（越过 {breakout:.1f}%），成交额约为近 20 日均额 {amount_ratio:.2f}×，收缩 {contractions} 次；只按预设止损和仓位执行。",
            "stars": 5,
            "label": "5星 可执行",
            "action": "规则化触发已满足；下单前复核止损、仓位和盘口成交。",
            "buyRank": 120 - abs(distance) * 4 + (amount_ratio or 0) * 8 + contractions * 5,
        }
    if (
        distance is not None
        and -3 <= distance <= 3
        and contractions >= 2
        and (amount_ratio or 0) >= 0.8
        and base_depth is not None
        and base_depth <= 40
        and from_high is not None
        and from_high >= -25
        and pct <= 5
        and avg_amount20_yi is not None
        and avg_amount20_yi >= 1
    ):
        return {
            "recommendation": "买点候选，等确认",
            "className": "priority",
            "reason": f"参考 Pivot {pivot_price:.2f}，当前{('距 Pivot +' + f'{distance:.1f}%') if distance >= 0 else ('已越过 ' + f'{abs(distance):.1f}%')}，成交额 {amount_ratio:.2f}×，收缩 {contractions} 次；还不是 5 星。",
            "stars": 4,
            "label": "4星 确认中",
            "action": "进入触发区；继续确认量能、止损位和仓位计划。",
            "buyRank": 95 - abs(distance) * 3 + (amount_ratio or 0) * 5 + contractions * 4,
        }
    if distance is not None and -5 <= distance <= 5 and contractions >= 1:
        return {
            "recommendation": "贴近 Pivot，重点盯",
            "className": "wait",
            "reason": f"离参考 Pivot {abs(distance):.1f}%，已有 {contractions} 次收缩；等突破、量能与风险点确认。",
            "stars": 3,
            "label": "3星 重点盯",
            "action": "接近触发区，等突破与量能；不提前买。",
            "buyRank": 65 - abs(distance) * 2 + contractions * 3,
        }
    return {
        "recommendation": "等待平台 / 突破",
        "className": "wait",
        "reason": "未贴近可执行的 Pivot，继续观察。",
        "stars": 2,
        "label": "2星 观察",
        "action": "记录观察，不是买点。",
        "buyRank": 0,
    }


def row_summary(row: dict[str, Any]) -> dict[str, Any]:
    pivot = row.get("pivotPrice")
    dist = (pivot - row["price"]) / row["price"] * 100 if pivot and row.get("price") else None
    return {
        "code": row["code"],
        "name": row["name"],
        "price": row["price"],
        "pct": row["pct"],
        "current": row["currentQualified"],
        "recommendation": row["recommendation"],
        "className": row["recommendationClass"],
        "reason": row["recommendationReason"],
        "pivot": pivot,
        "contractions": row["contractionCount"],
        "buyRank": row["buyRank"],
        "amountYi": row["quoteAmountYi"],
        "turnover": row["quoteTurnover"],
        "dist": dist,
        "stars": row["executionStars"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("--analysis-dir", type=Path, default=Path("/Users/leon/Documents/400=学习/402=投资/Mark Minervini 2/分析"))
    parser.add_argument(
        "--prior-current-codes",
        default="",
        help="comma-separated previous close qualified codes, used when regenerating the same close snapshot",
    )
    parser.add_argument(
        "--prior-xlsx",
        type=Path,
        help="previous close iWencai export used to identify prior qualified codes",
    )
    parser.add_argument(
        "--external-history-json",
        type=Path,
        help="optional code-keyed history JSON used when public history endpoints are unavailable",
    )
    args = parser.parse_args()

    export = pd.read_excel(args.xlsx)
    fallback_histories = load_committed_snapshot_history()
    for code, history in load_snapshot_history(ROOT / "m2-snapshot.json").items():
        existing = fallback_histories.get(code)
        if not existing or len(history.get("rows", [])) > len(existing.get("rows", [])):
            fallback_histories[code] = history
    if args.external_history_json:
        fallback_histories.update(load_snapshot_history(args.external_history_json))
    close_date = infer_close_date(args.xlsx, [str(column) for column in export.columns])
    close_iso = close_date.isoformat()
    close_label = date_label(close_date)
    close_compact = close_date.strftime("%Y%m%d")
    cols, period_text = infer_columns([str(column) for column in export.columns], close_date)
    export = export[export[cols["code"]].astype(str).str.match(r"^\d{6}\.(SZ|SH)$", na=False)].copy()
    current_by_code = {str(row[cols["code"]]): row for _, row in export.iterrows()}

    old_rows = load_old_rows(ROOT / "m2-table-data.js")
    old_by_code = {row[0]: row for row in old_rows}
    old_current = {row[0] for row in old_rows if row[19]}
    explicit_prior = {
        f"{code.strip()}.{'SH' if code.strip().startswith('6') else 'SZ'}"
        for code in args.prior_current_codes.split(",")
        if re.match(r"^\d{6}$", code.strip())
    }
    if args.prior_xlsx:
        prior_export = pd.read_excel(args.prior_xlsx)
        prior_code_col = BASE_COLS["code"]
        if prior_code_col not in prior_export.columns:
            raise ValueError(f"Missing {prior_code_col} in {args.prior_xlsx}")
        explicit_prior = {
            str(code)
            for code in prior_export[prior_code_col]
            if re.match(r"^\d{6}\.(SZ|SH)$", str(code))
        }
    if explicit_prior:
        old_current = explicit_prior
    ordered_codes = list(current_by_code)
    ordered_codes.extend(code for code in old_by_code if code not in current_by_code)
    for item in server.M2_CORE_WATCHLIST:
        full = f"{item['code']}.{'SH' if item['market'] == '1' else 'SZ'}"
        if full not in ordered_codes:
            ordered_codes.append(full)

    quotes, quote_source = fetch_quotes(ordered_codes)
    watch_items = [
        {
            "code": bare(code),
            "market": market_for(code),
            "name": str(current_by_code[code][cols["name"]])
            if code in current_by_code
            else old_by_code.get(code, ["", bare(code)])[1],
        }
        for code in ordered_codes
        if len((fallback_histories.get(bare(code)) or fallback_histories.get(code) or {}).get("rows", [])) < 250
    ]
    histories: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(fetch_history, item, close_date): item for item in watch_items}
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            history = future.result()
            if history:
                histories[item["code"]] = history

    rows: list[dict[str, Any]] = []
    snapshot_history: dict[str, Any] = {}
    reused_snapshot_codes: list[str] = []
    quote_rows = []
    for code in ordered_codes:
        q = quotes.get(bare(code), {})
        current = current_by_code.get(code)
        old = old_by_code.get(code)
        is_current = current is not None
        if is_current:
            value = lambda key: finite(current[cols[key]]) if cols.get(key) else None
            name = str(current[cols["name"]])
            price = value("price")
            pct = value("pct")
            open_price = value("open")
            high_price = value("high")
            low_price = value("low")
            ma50 = value("ma50")
            ma150 = value("ma150")
            ma200 = value("ma200")
            high52 = value("high52")
            low52 = value("low52")
            avg_amount = value("avg_amount")
            market_cap = value("market_cap") or finite(q.get("f20"))
            pe_ratio = value("pe") or finite(q.get("f9"))
            pb_ratio = value("pb")
            float_market_cap = value("float_market_cap") or finite(q.get("f21"))
            exchange = str(current[cols["exchange"]])
            period_pct = value("period_pct")
        elif old:
            name = old[1]
            price = finite(q.get("f2")) or finite(old[2])
            pct = finite(q.get("f3")) if finite(q.get("f3")) is not None else finite(old[3])
            open_price = finite(q.get("f17")) or price
            high_price = finite(q.get("f15")) or price
            low_price = finite(q.get("f16")) or price
            ma50, ma150, ma200 = finite(old[5]), finite(old[6]), finite(old[7])
            high52, low52 = finite(old[8]), finite(old[9])
            avg_amount = finite(old[10])
            market_cap = finite(q.get("f20")) or finite(old[11])
            pe_ratio = finite(q.get("f9")) or (finite(old[38]) if len(old) > 38 else None)
            pb_ratio = finite(old[39]) if len(old) > 39 else None
            float_market_cap = finite(q.get("f21")) or (finite(old[40]) if len(old) > 40 else None)
            exchange = old[12]
            period_pct = finite(old[4])
        else:
            name = next((item["name"] for item in server.M2_CORE_WATCHLIST if item["code"] == bare(code)), bare(code))
            price = finite(q.get("f2"))
            pct = finite(q.get("f3"))
            open_price = finite(q.get("f17")) or price
            high_price = finite(q.get("f15")) or price
            low_price = finite(q.get("f16")) or price
            ma50 = ma150 = ma200 = high52 = low52 = avg_amount = market_cap = period_pct = None
            market_cap = finite(q.get("f20"))
            pe_ratio = finite(q.get("f9"))
            pb_ratio = None
            float_market_cap = finite(q.get("f21"))
            exchange = "上交所" if code.endswith(".SH") else "深交所"

        current_quote = {
            "price": price,
            "pct": pct,
            "change": finite(q.get("f4")),
            "volumeLots": finite(q.get("f5")),
            "amountYi": amount_yi(finite(q.get("f6"))),
            "amplitude": finite(q.get("f7")),
            "turnover": finite(q.get("f8")),
            "open": open_price,
            "high": high_price,
            "low": low_price,
        }
        history_source = histories.get(bare(code))
        if not history_source:
            history_source = fallback_histories.get(bare(code)) or fallback_histories.get(code)
            if history_source:
                reused_snapshot_codes.append(bare(code))
        history = append_current_bar(history_source, current_quote, close_date)
        if history:
            snapshot_history[bare(code)] = history
            latest = history["rows"][-1]
            if not is_current:
                ma50 = finite(latest.get("ma50")) or ma50
                ma150 = finite(latest.get("ma150")) or ma150
                ma200 = finite(latest.get("ma200")) or ma200
                high_values = [finite(item.get("high")) for item in history["rows"]]
                low_values = [finite(item.get("low")) for item in history["rows"]]
                high_values = [item for item in high_values if item is not None]
                low_values = [item for item in low_values if item is not None]
                high52 = max(high_values[-250:]) if high_values else high52
                low52 = min(low_values[-250:]) if low_values else low52
        metrics = (history or {}).get("metrics") or {}
        pivot = derive_prior_pivot(history, close_date)
        amount_ratio = current_quote["amountYi"] / amount_yi(avg_amount) if current_quote["amountYi"] and avg_amount else None
        price_to_ma50 = (price / ma50 - 1) * 100 if price and ma50 else None
        from_high = (price / high52 - 1) * 100 if price and high52 else None
        from_low = (price / low52 - 1) * 100 if price and low52 else None
        row_seed = {
            "code": code,
            "name": name,
            "price": price,
            "pct": pct,
            "currentQualified": is_current,
            "amountRatio": amount_ratio,
            "priceToMa50Pct": price_to_ma50,
            "fromHighPct": from_high,
        }
        rating = classify(row_seed, pivot, metrics, close_label)
        status = "当前合格观察" if is_current else "待复核观察"
        prior = code in old_current
        if is_current and not prior:
            transition = f"{close_label} 收盘新进观察"
        elif is_current and prior:
            transition = f"{close_label} 收盘继续观察"
        elif is_current:
            transition = f"{close_label} 收盘重新确认入池"
        else:
            transition = f"{close_label} 收盘未出现，保留记录待复核"
        rows.append(
            {
                "code": code,
                "name": name,
                "price": price,
                "pct": pct,
                "periodPct": period_pct,
                "ma50": ma50,
                "ma150": ma150,
                "ma200": ma200,
                "high52": high52,
                "low52": low52,
                "avgAmount": avg_amount,
                "marketCap": market_cap,
                "peRatio": pe_ratio,
                "pbRatio": pb_ratio,
                "floatMarketCap": float_market_cap,
                "exchange": exchange,
                "dataAsOf": f"{close_iso} 收盘" if is_current else (old[13] if old else "历史档案"),
                "status": status,
                "recommendation": rating["recommendation"],
                "recommendationClass": rating["className"],
                "recommendationReason": rating["reason"],
                "transition": transition,
                "currentQualified": is_current,
                "priorQualified": prior,
                "quoteChange": current_quote["change"],
                "quoteVolumeLots": current_quote["volumeLots"],
                "quoteAmountYi": current_quote["amountYi"],
                "quoteAmplitude": current_quote["amplitude"],
                "quoteTurnover": current_quote["turnover"],
                "pivotPrice": pivot["price"],
                "pivotDate": pivot["date"],
                "pivotLookback": pivot["lookback"],
                "contractionCount": metrics.get("contractionCount"),
                "baseDepthPct": metrics.get("baseDepthPct"),
                "range20Pct": metrics.get("range20Pct"),
                "volumeDryUpRatio": metrics.get("volumeDryUpRatio"),
                "buyRank": round(rating["buyRank"], 4),
                "executionStars": rating["stars"],
                "executionLabel": rating["label"],
                "executionAction": rating["action"],
                "amountRatio": amount_ratio,
                "priceToMa50Pct": price_to_ma50,
                "fromHighPct": from_high,
                "fromLowPct": from_low,
            }
        )
        quote_rows.append(
            {
                "code": bare(code),
                "name": name,
                "price": price,
                "pct": pct,
                "change": current_quote["change"],
                "volumeLots": current_quote["volumeLots"],
                "amountYi": current_quote["amountYi"],
                "amplitude": current_quote["amplitude"],
                "turnover": current_quote["turnover"],
            }
        )

    rows.sort(key=lambda row: (row["executionStars"], row["buyRank"], row["pct"] or -999), reverse=True)
    raw = [
        [
            row["code"],
            row["name"],
            row["price"],
            row["pct"],
            row["periodPct"],
            row["ma50"],
            row["ma150"],
            row["ma200"],
            row["high52"],
            row["low52"],
            row["avgAmount"],
            row["marketCap"],
            row["exchange"],
            row["dataAsOf"],
            row["status"],
            row["recommendation"],
            row["recommendationClass"],
            row["recommendationReason"],
            row["transition"],
            row["currentQualified"],
            row["priorQualified"],
            row["quoteChange"],
            row["quoteVolumeLots"],
            row["quoteAmountYi"],
            row["quoteAmplitude"],
            row["quoteTurnover"],
            row["pivotPrice"],
            row["pivotDate"],
            row["pivotLookback"],
            row["contractionCount"],
            row["baseDepthPct"],
            row["range20Pct"],
            row["volumeDryUpRatio"],
            row["buyRank"],
            row["executionStars"],
            row["executionLabel"],
            row["executionAction"],
            row["amountRatio"],
            row["peRatio"],
            row["pbRatio"],
            row["floatMarketCap"],
        ]
        for row in rows
    ]
    current_count = sum(row["currentQualified"] for row in rows)
    prior_count = len(old_current) if explicit_prior else sum(row[19] for row in old_rows)
    star5 = [row for row in rows if row["executionStars"] >= 5]
    star4 = [row for row in rows if row["executionStars"] == 4]
    star3 = [row for row in rows if row["executionStars"] == 3]
    caution = [row for row in rows if row["recommendationClass"] == "caution"]
    review = [row for row in rows if row["recommendationClass"] == "review"]
    wait = [row for row in rows if row["recommendationClass"] == "wait" and row["executionStars"] <= 2]
    new_count = sum(row["currentQualified"] and not row["priorQualified"] for row in rows)
    carry_count = sum(not row["currentQualified"] for row in rows)
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    table_js = f"""window.M2_TABLE_DATA = (() => {{
  const raw = {js(raw)};
  const rows = raw.map(([code,name,price,pct,periodPct,ma50,ma150,ma200,high52,low52,avgAmount,marketCap,exchange,dataAsOf,status,recommendation,recommendationClass,recommendationReason,transition,currentQualified,priorQualified,quoteChange,quoteVolumeLots,quoteAmountYi,quoteAmplitude,quoteTurnover,pivotPrice,pivotDate,pivotLookback,contractionCount,baseDepthPct,range20Pct,volumeDryUpRatio,buyRank,executionStars,executionLabel,executionAction,amountRatio,peRatio,pbRatio,floatMarketCap]) => {{
    const priceToMa50Pct = price && ma50 ? (price / ma50 - 1) * 100 : null;
    const priceToMa150Pct = price && ma150 ? (price / ma150 - 1) * 100 : null;
    const priceToMa200Pct = price && ma200 ? (price / ma200 - 1) * 100 : null;
    const ma50ToMa150Pct = ma50 && ma150 ? (ma50 / ma150 - 1) * 100 : null;
    const ma150ToMa200Pct = ma150 && ma200 ? (ma150 / ma200 - 1) * 100 : null;
    const fromHighPct = price && high52 ? (price / high52 - 1) * 100 : null;
    const fromLowPct = price && low52 ? (price / low52 - 1) * 100 : null;
    const pivotDistanceValue = pivotPrice && price ? (pivotPrice - price) / price * 100 : null;
    const pivotText = Number.isFinite(Number(pivotPrice)) ? Number(pivotPrice).toFixed(2) : '待确认';
    const pivotDistance = pivotDistanceValue === null ? '—' : (Math.abs(pivotDistanceValue) < 0.01 ? '已到上沿' : (pivotDistanceValue > 0 ? '距上沿 +' + pivotDistanceValue.toFixed(1) + '%' : '已越过 ' + Math.abs(pivotDistanceValue).toFixed(1) + '%'));
    return {{ code, symbol: code.slice(0,6), name, price, pct, closeAdj: price, ma50, ma150, ma200, periodPct, high52, low52, fromHighPct, fromLowPct, avgAmount, marketCap, peRatio, pbRatio, floatMarketCap, exchange, dataAsOf, quoteAsOf: '{close_iso} 收盘行情', quoteGeneratedAt: {js(generated_at)}, quoteSource: {js(quote_source)}, quoteChange, quoteVolumeLots, quoteAmountYi, quoteAmplitude, quoteTurnover, status, transition, currentQualified, priorQualified, buyRank, amountRatio,
      maStacked: price > ma50 && ma50 > ma150 && ma150 > ma200, aboveMa50: price > ma50, aboveMa200: price > ma200,
      priceToMa50Pct, priceToMa150Pct, priceToMa200Pct, ma50ToMa150Pct, ma150ToMa200Pct, stageInference: currentQualified ? '阶段 2 初筛通过' : '历史观察待复核',
      recommendation, recommendationClass, recommendationReason, executionRating: {{ stars: executionStars, label: executionLabel, action: executionAction }}, pivot: pivotText, pivotPrice, pivotStatus: pivotLookback ? pivotLookback + '日参考买点' : '待确认', pivotDistance, pivotReason: pivotLookback ? '参考 Pivot 买点取 {close_label} 前最近 ' + pivotLookback + ' 日最高价 ' + pivotText + '（' + pivotDate + '）；收盘突破并明显放量才算触发。' : '观察池记录未包含 Pivot；必须结合动态历史 OHLCV 与图形核验。', pivotLocked: true, contractions: Number.isFinite(Number(contractionCount)) ? contractionCount + ' 次' : '待确认', contractionCount, baseDepthPct, range20Pct, volumeDryUpRatio,
      rsRank: null, rsTrend: '待补 RS', vcpStatus: contractionCount >= 2 ? 'VCP 收缩候选' : (contractionCount >= 1 ? 'VCP 初步收缩' : '待人工复核'), dataQuality: currentQualified ? '{close_label} 收盘导入与收盘报价已更新；Pivot 采用 {close_label} 前高，不把当日高点误作触发点。' : '{close_label} 收盘未重新入选；历史观察保留，待人工复核是否移出。', ma200Slope: '动态日K已补 MA200，斜率仍需人工复核' }};
  }});
  return {{ asOf: '{close_iso} 收盘行情', selectionAsOf: '{close_iso} 收盘', snapshotAsOf: '{close_iso}', closeLabel: '{close_label}', periodLabel: {js(period_text)}, snapshotGeneratedAt: {js(generated_at)}, quoteGeneratedAt: {js(generated_at)}, quoteSourceStatus: 'live', quoteSource: {js(quote_source)}, source: "观察池：{close_label} 收盘合格候选 ∪ 既有观察池待复核；图形：历史日K追加 {close_label} 收盘 OHLCV；报价：东方财富收盘行情", rowCount: rows.length, importedCount: {len(export)}, currentQualifiedCount: {current_count}, priorCloseQualified: {prior_count}, newSinceClose: {new_count}, carryForwardCount: {carry_count}, priorityCount: {len(star4)}, executableCount: {len(star5)}, nearPivotCount: {len(star3)}, waitCount: {len(wait)}, cautionCount: {len(caution)}, reviewCount: {len(review)}, upCount: {sum(row['currentQualified'] and (row['pct'] or 0) > 0 for row in rows)}, period: '{close_iso} 收盘观察池 / {close_iso} 收盘行情', note: "{close_label} 收盘已按星级重新分层；5 星才是规则化可执行候选，4 星仍是确认中，不生成自动买入指令。", topMovers: {js([row_summary(row) for row in sorted(rows, key=lambda row: row['pct'] or -999, reverse=True)[:8]])}, executableCandidates: {js([row_summary(row) for row in star5[:8]])}, priorityCandidates: {js([row_summary(row) for row in star4[:8]])}, nearPivotCandidates: {js([row_summary(row) for row in star3[:8]])}, cautionCandidates: {js([row_summary(row) for row in caution[:8]])}, reviewStrongCandidates: {js([row_summary(row) for row in sorted(review, key=lambda row: row['pct'] or -999, reverse=True)[:5]])}, rows }};
}})();
"""
    (ROOT / "m2-table-data.js").write_text(table_js, encoding="utf-8")
    valuation_items: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = {
            "code": row["code"],
            "symbol": bare(row["code"]),
            "name": row["name"],
            "marketCap": row["marketCap"],
            "floatMarketCap": row["floatMarketCap"],
            "peRatio": row["peRatio"],
            "pbRatio": row["pbRatio"],
        }
        valuation_items[row["code"]] = item
        valuation_items[bare(row["code"])] = item
    valuation_payload = {
        "source": "iWencai export plus Eastmoney push2 fields f9/f20/f21",
        "generatedAt": generated_at,
        "rowCount": len(rows),
        "items": valuation_items,
    }
    (ROOT / "m2-valuation-map.js").write_text(
        "window.M2_VALUATION_MAP = " + js(valuation_payload) + ";\n",
        encoding="utf-8",
    )

    focus_rows = star5 + star4 + star3
    focus_names = " / ".join(row["name"] for row in focus_rows[:6]) or "暂无"
    market_stats = [
        {"label": "观察池", "value": f"{len(rows)} 只"},
        {"label": "5星可执行", "value": f"{len(star5)} 只"},
        {"label": "4星确认中", "value": f"{len(star4)} 只"},
        {"label": "3星重点盯", "value": f"{len(star3)} 只"},
        {"label": "当前池上涨", "value": f"{sum(row['currentQualified'] and (row['pct'] or 0) > 0 for row in rows)} 只"},
    ]
    changes = [
        {"time": "收盘", "text": f"{close_label} 收盘表有效股票 {len(export)} 只；合并旧观察池后持续记录 {len(rows)} 只。"},
        {"time": "星级", "text": f"5 星可执行 {len(star5)} 只：{'、'.join(row['name'] for row in star5) or '暂无'}；4 星确认中 {len(star4)} 只。"},
        {"time": "盯盘", "text": f"3 星重点盯 {len(star3)} 只：{'、'.join(row['name'] for row in star3[:8]) or '暂无'}。"},
        {"time": "边界", "text": "5 星只代表规则化触发候选；仍需按交易计划复核止损、仓位和流动性，不是自动买入指令。"},
    ]
    candidates = []
    for index, row in enumerate(focus_rows[:12], start=1):
        candidates.append(
            {
                "code": bare(row["code"]),
                "name": row["name"],
                "sector": "待 R02 板块复核",
                "state": row["status"],
                "stateClass": "watch" if row["executionStars"] >= 3 else row["recommendationClass"],
                "stage": "阶段 2 初筛",
                "price": f"{row['price']:.2f}" if row["price"] is not None else "—",
                "change": pct_text(row["pct"], 2),
                "marketCap": row["marketCap"],
                "peRatio": row["peRatio"],
                "volume": f"{row['quoteAmountYi']:.2f}亿" if row["quoteAmountYi"] is not None else "数据不足",
                "volumeLabel": f"成交额/均额 {row['amountRatio']:.2f}×" if row["amountRatio"] is not None else "成交额待复核",
                "pivot": f"{row['pivotPrice']:.2f}" if row["pivotPrice"] else "待确认",
                "distance": "—",
                "range": 20,
                "pivotPrice": row["pivotPrice"],
                "pivotLocked": True,
                "pivotStatus": f"{row['pivotLookback']}日参考买点" if row["pivotLookback"] else "待确认",
                "pivotReason": f"参考 Pivot 买点取 {close_label} 前最近 {row['pivotLookback']} 日最高价（{row['pivotDate']}），收盘突破并明显放量才算触发。" if row["pivotLookback"] else "Pivot 待确认。",
                "stageReason": f"当前通过 {close_label} 收盘 M2-01 初筛，距 MA50 {pct_text(row['priceToMa50Pct'], 1)}。",
                "volumeRule": "突破日需明显放量",
                "advice": row["recommendation"],
                "adviceClass": row["recommendationClass"],
                "adviceReason": row["recommendationReason"],
                "executionStars": row["executionStars"],
                "executionLabel": row["executionLabel"],
                "executionAction": row["executionAction"],
                "buyRank": row["buyRank"],
                "action": row["executionAction"],
                "note": row["transition"],
                "baseAge": "40 个交易日（算法）",
                "contractions": f"{row['contractionCount']} 次" if row["contractionCount"] is not None else "待确认",
                "contractionDetail": f"动态历史 + {close_label} 收盘补全的算法初筛；需人工确认图形。",
                "correction": f"{row['baseDepthPct']:.1f}%" if row["baseDepthPct"] is not None else "待确认",
                "chart": None,
                "priority": index,
            }
        )
    m2_data = {
        "asOf": f"{close_iso} 收盘行情",
        "selectionAsOf": f"{close_iso} 收盘",
        "snapshotAsOf": close_iso,
        "quoteGeneratedAt": generated_at,
        "market": {
            "status": "🟢 收盘复核完成" if star5 else "🟡 收盘观察",
            "note": f"{close_label} 收盘表已导入；观察池按执行星级从高到低排序，5 星才代表规则化可执行候选。",
            "stats": market_stats,
        },
        "decision": {
            "title": f"待观察股票池：{len(rows)} 只",
            "text": f"{close_label} 收盘 5 星可执行 {len(star5)} 只：{'、'.join(row['name'] for row in star5) or '暂无'}。4 星确认中 {len(star4)} 只，仍需继续确认。",
            "nextFocus": focus_rows[0]["name"] if focus_rows else "暂无",
            "pivot": f"{focus_rows[0]['pivotPrice']:.2f}" if focus_rows and focus_rows[0]["pivotPrice"] else "未确认",
            "distance": "—",
        },
        "changes": changes,
        "candidates": candidates,
    }
    (ROOT / "m2-data.js").write_text("window.M2_DATA = " + js(m2_data) + ";\n", encoding="utf-8")

    snapshot = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "asOf": close_iso,
        "maxAgeHours": 36,
        "barStatus": "complete",
        "sourceStatus": "live" if len(snapshot_history) == len(ordered_codes) else "partial",
        "source": f"Local Session · history plus {close_iso} close quote/import append; snapshot fallback {len(reused_snapshot_codes)}",
        "quotes": quote_rows,
        "history": snapshot_history,
        "warnings": [] if len(snapshot_history) == len(ordered_codes) else [f"部分历史日K未取到：{len(snapshot_history)}/{len(ordered_codes)}"],
        "reusedSnapshotCodes": sorted(set(reused_snapshot_codes)),
    }
    write_snapshot_bundle(snapshot)

    args.analysis_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {close_iso} M2 收盘分析",
        "",
        f"- 数据源：`导入/{args.xlsx.name}`，有效股票 {len(export)} 只。",
        f"- 合并观察池：{len(rows)} 只；其中当前合格 {current_count} 只，旧池待复核 {carry_count} 只，新进/重新入池 {new_count} 只。",
        f"- 5 星可执行：{len(star5)} 只：{'、'.join(row['name'] for row in star5) or '暂无'}。",
        f"- 4 星确认中：{len(star4)} 只：{'、'.join(row['name'] for row in star4[:20]) or '暂无'}。",
        f"- 3 星重点盯：{len(star3)} 只：{'、'.join(row['name'] for row in star3[:20]) or '暂无'}。",
        "",
        "## 口径",
        "",
        f"5 星表示本轮规则化触发候选：收盘站上 {close_label} 前参考 Pivot、成交额相对近 20 日均额放大、位置不过热且有算法收缩证据；仍需执行前复核止损、仓位和流动性。4 星只是确认中，3 星是重点盯盘，2 星普通观察，1 星不追或待复核。",
    ]
    (args.analysis_dir / f"{close_iso} M2收盘分析.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sector_script = Path(__file__).with_name("generate-m2-sector-map.py")
    if sector_script.exists():
        try:
            subprocess.run([sys.executable, str(sector_script)], check=True, timeout=120)
        except (subprocess.SubprocessError, OSError) as error:
            print(f"warning: sector map refresh failed: {error}", file=sys.stderr)
    print(json.dumps({"rows": len(rows), "current": current_count, "star5": [row["name"] for row in star5], "star4": len(star4), "star3": len(star3)}, ensure_ascii=False))
    return 0


def legacy_rows_to_state(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for row in rows:
        if len(row) < 21:
            continue
        state[row[0]] = {
            "code": row[0],
            "name": row[1],
            "price": finite(row[2]),
            "pct": finite(row[3]),
            "periodPct": finite(row[4]),
            "ma50": finite(row[5]),
            "ma150": finite(row[6]),
            "ma200": finite(row[7]),
            "high52": finite(row[8]),
            "low52": finite(row[9]),
            "avgAmount": finite(row[10]),
            "marketCap": finite(row[11]),
            "exchange": row[12],
            "dataAsOf": row[13],
            "stage": "S2趋势",
            "currentQualified": bool(row[19]),
            "everS2": True,
            "peRatio": finite(row[38]) if len(row) > 38 else None,
            "pbRatio": finite(row[39]) if len(row) > 39 else None,
            "floatMarketCap": finite(row[40]) if len(row) > 40 else None,
        }
    return state


def legacy_rows_as_state() -> dict[str, dict[str, Any]]:
    return legacy_rows_to_state(load_old_rows(ROOT / "m2-table-data.js"))


def committed_legacy_state() -> dict[str, dict[str, Any]]:
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:m2-table-data.js"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        match = re.search(r"const raw\s*=\s*(\[\[.*?\]\]);\s*const rows", result.stdout, re.S)
        return legacy_rows_to_state(json.loads(match.group(1))) if match else {}
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return {}


def load_stage_state(path: Path, close_iso: str) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return legacy_rows_as_state() or committed_legacy_state()
    if str(payload.get("asOf") or "") >= close_iso:
        return committed_legacy_state()
    rows = payload.get("rows") or []
    return {str(row["code"]): row for row in rows if isinstance(row, dict) and row.get("code")}


def main_stage() -> int:
    parser = argparse.ArgumentParser(description="Generate the dual-pool M2 close snapshot")
    parser.add_argument("transition_xlsx", type=Path)
    parser.add_argument("s2_xlsx", type=Path)
    parser.add_argument("--analysis-dir", type=Path, default=Path("/Users/leon/Documents/400=学习/402=投资/Mark Minervini 2/分析"))
    parser.add_argument("--external-history-json", type=Path)
    args = parser.parse_args()

    transition_date, transition_export = read_stage_export(args.transition_xlsx, "S1→S2导出")
    s2_date, s2_export = read_stage_export(args.s2_xlsx, "S2导出")
    if transition_date != s2_date:
        raise ValueError(f"两份导出日期不一致：{transition_date} / {s2_date}")
    close_date = transition_date
    close_iso = close_date.isoformat()
    close_label = date_label(close_date)
    current_by_code = merge_stage_exports(transition_export, s2_export)

    fallback_histories = load_committed_snapshot_history()
    for code, history in load_snapshot_history(ROOT / "m2-snapshot.json").items():
        existing = fallback_histories.get(code)
        if not existing or len(history.get("rows", [])) > len(existing.get("rows", [])):
            fallback_histories[code] = history
    if args.external_history_json:
        fallback_histories.update(load_snapshot_history(args.external_history_json))

    prior_by_code = load_stage_state(ROOT / "m2-stage-state.json", close_iso)
    prior_formal = {code for code, row in prior_by_code.items() if row.get("stage") in FORMAL_STAGES}
    ordered_codes = list(current_by_code)
    ordered_codes.extend(code for code in prior_by_code if code not in current_by_code)

    quotes, quote_source = fetch_quotes(ordered_codes)
    watch_items = []
    for code in ordered_codes:
        cached = fallback_histories.get(bare(code)) or fallback_histories.get(code) or {}
        if len(cached.get("rows", [])) >= 250:
            continue
        source = current_by_code.get(code) or prior_by_code.get(code) or {}
        watch_items.append({"code": bare(code), "market": market_for(code), "name": source.get("name") or bare(code)})
    histories: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {executor.submit(fetch_history, item, close_date): item for item in watch_items}
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            history = future.result()
            if history:
                histories[item["code"]] = history

    rows: list[dict[str, Any]] = []
    snapshot_history: dict[str, Any] = {}
    quote_rows: list[dict[str, Any]] = []
    reused_snapshot_codes: list[str] = []
    history_missing: list[str] = []
    for code in ordered_codes:
        imported = current_by_code.get(code)
        prior = prior_by_code.get(code) or {}
        q = quotes.get(bare(code), {})
        name = (imported or prior).get("name") or str(q.get("f14") or bare(code))
        price = finite((imported or {}).get("price")) or finite(q.get("f2")) or finite(prior.get("price"))
        pct = finite((imported or {}).get("pct"))
        if pct is None:
            pct = finite(q.get("f3")) if finite(q.get("f3")) is not None else finite(prior.get("pct"))
        open_price = finite((imported or {}).get("open")) or finite(q.get("f17")) or price
        high_price = finite((imported or {}).get("high")) or finite(q.get("f15")) or price
        low_price = finite((imported or {}).get("low")) or finite(q.get("f16")) or price
        quote_amount_yi = amount_yi(finite(q.get("f6")))
        current_quote = {
            "price": price,
            "pct": pct,
            "change": finite(q.get("f4")),
            "volumeLots": finite(q.get("f5")),
            "amountYi": quote_amount_yi,
            "amplitude": finite(q.get("f7")),
            "turnover": finite(q.get("f8")),
            "open": open_price,
            "high": high_price,
            "low": low_price,
        }
        history_source = histories.get(bare(code))
        if not history_source:
            history_source = fallback_histories.get(bare(code)) or fallback_histories.get(code)
            if history_source:
                reused_snapshot_codes.append(bare(code))
        history = append_current_bar(history_source, current_quote, close_date)
        if history:
            snapshot_history[bare(code)] = history
        else:
            history_missing.append(code)
        metrics = (history or {}).get("metrics") or {}
        latest = ((history or {}).get("rows") or [{}])[-1]
        ma50 = finite(latest.get("ma50")) or finite((imported or {}).get("ma50")) or finite(prior.get("ma50"))
        ma150 = finite(latest.get("ma150")) or finite((imported or {}).get("ma150")) or finite(prior.get("ma150"))
        ma200 = finite(latest.get("ma200")) or finite((imported or {}).get("ma200")) or finite(prior.get("ma200"))
        high52 = finite(metrics.get("high250")) or finite((imported or {}).get("high52")) or finite(prior.get("high52"))
        low52 = finite(metrics.get("low250")) or finite((imported or {}).get("low52")) or finite(prior.get("low52"))
        period_pct = finite(metrics.get("periodPct20d"))
        if period_pct is None:
            period_pct = finite((imported or {}).get("periodPct")) or finite(prior.get("periodPct"))
        avg_amount20_yi = finite(metrics.get("avgAmount20Yi"))
        avg_amount = avg_amount20_yi * 100000000 if avg_amount20_yi is not None else finite(prior.get("avgAmount"))
        market_cap = finite(q.get("f20")) or finite(prior.get("marketCap"))
        pe_ratio = finite(q.get("f9")) or finite(prior.get("peRatio"))
        pb_ratio = finite(prior.get("pbRatio"))
        float_market_cap = finite(q.get("f21")) or finite(prior.get("floatMarketCap"))
        from_high = (price / high52 - 1) * 100 if price and high52 else None
        from_low = (price / low52 - 1) * 100 if price and low52 else None
        price_to_ma50 = (price / ma50 - 1) * 100 if price and ma50 else None
        ever_s2 = bool(prior.get("everS2")) or prior.get("stage") in S2_STAGES
        stage_seed = {"price": price, "ma50": ma50, "ma150": ma150, "ma200": ma200}
        stage, stage_reason = classify_stage(stage_seed, metrics, ever_s2)
        stop_values = [finite(item.get("low")) for item in ((history or {}).get("rows") or [])[-10:]]
        stop_values = [value for value in stop_values if value is not None]
        stop_price = min(stop_values) if stop_values else None
        stop_distance = (price / stop_price - 1) * 100 if price and stop_price else None
        pivot = derive_prior_pivot(history, close_date)
        amount_ratio = quote_amount_yi / avg_amount20_yi if quote_amount_yi and avg_amount20_yi else None
        row_seed = {
            "price": price,
            "pct": pct,
            "stage": stage,
            "stageReason": stage_reason,
            "amountRatio": amount_ratio,
            "priceToMa50Pct": price_to_ma50,
            "fromHighPct": from_high,
            "stopDistancePct": stop_distance,
        }
        rating = classify(row_seed, pivot, metrics, close_label)
        formal = stage in FORMAL_STAGES
        previous_stage = prior.get("stage")
        if not previous_stage:
            transition = f"{close_label} 首次按新规则分类为{stage}"
        elif previous_stage == stage:
            transition = f"{close_label} 维持{stage}"
        else:
            transition = f"{close_label} {previous_stage} → {stage}"
        row = {
            "code": code,
            "symbol": bare(code),
            "name": name,
            "price": price,
            "pct": pct,
            "periodPct": period_pct,
            "ma50": ma50,
            "ma150": ma150,
            "ma200": ma200,
            "high52": high52,
            "low52": low52,
            "fromHighPct": from_high,
            "fromLowPct": from_low,
            "avgAmount": avg_amount,
            "avgAmount20Yi": avg_amount20_yi,
            "marketCap": market_cap,
            "peRatio": pe_ratio,
            "pbRatio": pb_ratio,
            "floatMarketCap": float_market_cap,
            "exchange": exchange_for(code),
            "dataAsOf": f"{close_iso} 收盘" if history else "历史日K不足",
            "status": "正式阶段池" if formal else "历史观察/待复核",
            "stage": stage,
            "stageInference": stage,
            "stageReason": stage_reason,
            "importPools": (imported or {}).get("pools") or [],
            "importedCandidate": imported is not None,
            "currentQualified": formal,
            "priorQualified": code in prior_formal,
            "everS2": ever_s2 or stage in S2_STAGES,
            "transition": transition,
            "maStacked": bool(price and ma50 and ma150 and ma200 and price > ma50 > ma150 > ma200),
            "aboveMa50": bool(price and ma50 and price > ma50),
            "aboveMa200": bool(price and ma200 and price > ma200),
            "priceToMa50Pct": price_to_ma50,
            "priceToMa150Pct": (price / ma150 - 1) * 100 if price and ma150 else None,
            "priceToMa200Pct": (price / ma200 - 1) * 100 if price and ma200 else None,
            "ma50ToMa150Pct": (ma50 / ma150 - 1) * 100 if ma50 and ma150 else None,
            "ma150ToMa200Pct": (ma150 / ma200 - 1) * 100 if ma150 and ma200 else None,
            "ma200SlopePct20d": finite(metrics.get("ma200SlopePct20d")),
            "ma50SlopePct20d": finite(metrics.get("ma50SlopePct20d")),
            "ma200Monotonic20d": metrics.get("ma200Monotonic20d"),
            "high20Higher": metrics.get("high20Higher"),
            "low20Higher": metrics.get("low20Higher"),
            "strongVolumeUpWeek": metrics.get("strongVolumeUpWeek"),
            "weeklyUpVolumeCount": metrics.get("weeklyUpVolumeCount"),
            "weeklyDownVolumeCount": metrics.get("weeklyDownVolumeCount"),
            "demandSupplyRatio10w": finite(metrics.get("demandSupplyRatio10w")),
            "recommendation": rating["recommendation"],
            "recommendationClass": rating["className"],
            "recommendationReason": rating["reason"],
            "executionStars": rating["stars"],
            "executionLabel": rating["label"],
            "executionAction": rating["action"],
            "executionRating": {"stars": rating["stars"], "label": rating["label"], "action": rating["action"]},
            "buyRank": round(rating["buyRank"], 4),
            "quoteAsOf": f"{close_iso} 收盘行情",
            "quoteSource": quote_source,
            "quoteChange": current_quote["change"],
            "quoteVolumeLots": current_quote["volumeLots"],
            "quoteAmountYi": quote_amount_yi,
            "quoteAmplitude": current_quote["amplitude"],
            "quoteTurnover": current_quote["turnover"],
            "amountRatio": amount_ratio,
            "pivot": f"{pivot['price']:.2f}" if pivot["price"] else "待确认",
            "pivotPrice": pivot["price"],
            "pivotDate": pivot["date"],
            "pivotLookback": pivot["lookback"],
            "pivotStatus": f"{pivot['lookback']}日参考买点" if pivot["lookback"] else "待确认",
            "pivotDistance": pct_text(((pivot["price"] - price) / price * 100) if pivot["price"] and price else None),
            "pivotReason": f"参考Pivot取{close_label}前最近{pivot['lookback']}日最高价；突破与量能需同时确认。" if pivot["lookback"] else "历史数据不足，Pivot待确认。",
            "pivotLocked": True,
            "stopPrice": stop_price,
            "stopDistancePct": stop_distance,
            "contractionCount": metrics.get("contractionCount"),
            "contractions": f"{metrics.get('contractionCount')} 次" if metrics.get("contractionCount") is not None else "待确认",
            "baseDepthPct": metrics.get("baseDepthPct"),
            "range20Pct": metrics.get("range20Pct"),
            "volumeDryUpRatio": metrics.get("volumeDryUpRatio"),
            "vcpStatus": metrics.get("vcpStatus") or "待人工复核",
            "rsRank": None,
            "rsTrend": "待补 RS",
            "dataQuality": f"{close_label}收盘历史日K已补齐并按新规则精算。" if history else "历史日K不足，不判定通过。",
            "ma200Slope": pct_text(finite(metrics.get("ma200SlopePct20d")), 2),
        }
        rows.append(row)
        quote_rows.append({
            "code": row["symbol"],
            "name": row["name"],
            "price": row["price"],
            "pct": row["pct"],
            "change": row["quoteChange"],
            "volumeLots": row["quoteVolumeLots"],
            "amountYi": row["quoteAmountYi"],
            "amplitude": row["quoteAmplitude"],
            "turnover": row["quoteTurnover"],
        })

    rows.sort(key=lambda row: (row["currentQualified"], row["executionStars"], row["buyRank"], row["pct"] or -999), reverse=True)
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    stage_counts = {stage: sum(row["stage"] == stage for row in rows) for stage in ("S1→S2过渡", "S2趋势", "S2延伸", "S2转弱", "待复核")}
    star_counts = {stars: sum(row["executionStars"] == stars for row in rows) for stars in range(1, 6)}
    formal_rows = [row for row in rows if row["currentQualified"]]
    star5 = [row for row in rows if row["executionStars"] == 5]
    star4 = [row for row in rows if row["executionStars"] == 4]
    star3 = [row for row in rows if row["executionStars"] == 3]
    new_count = sum(row["currentQualified"] and not row["priorQualified"] for row in rows)
    changed = [row for row in rows if row["transition"].find(" → ") >= 0]
    table_payload = {
        "asOf": f"{close_iso} 收盘行情",
        "selectionAsOf": f"{close_iso} 收盘",
        "snapshotAsOf": close_iso,
        "closeLabel": close_label,
        "periodLabel": f"近20日 → {close_label}",
        "snapshotGeneratedAt": generated_at,
        "quoteGeneratedAt": generated_at,
        "quoteSourceStatus": "live" if not history_missing else "partial",
        "quoteSource": quote_source,
        "source": f"{close_label} S1→S2与S2双导出 + 历史日K精算",
        "rowCount": len(rows),
        "importedCount": len(current_by_code),
        "transitionImportCount": len(transition_export),
        "s2ImportCount": len(s2_export),
        "overlapImportCount": len(set(transition_export) & set(s2_export)),
        "currentQualifiedCount": len(formal_rows),
        "priorCloseQualified": len(prior_formal),
        "newSinceClose": new_count,
        "carryForwardCount": len(rows) - len(formal_rows),
        "priorityCount": len(star4),
        "executableCount": len(star5),
        "nearPivotCount": len(star3),
        "upCount": sum(row["currentQualified"] and (row["pct"] or 0) > 0 for row in rows),
        "stageCounts": stage_counts,
        "starCounts": star_counts,
        "historyMissing": history_missing,
        "note": "阶段与执行星级分离；进入阶段池不等于可以买入，5星仍需人工复核止损、仓位和流动性。",
        "topMovers": [row_summary(row) for row in sorted(formal_rows, key=lambda row: row["pct"] or -999, reverse=True)[:8]],
        "executableCandidates": [row_summary(row) for row in star5[:8]],
        "priorityCandidates": [row_summary(row) for row in star4[:8]],
        "nearPivotCandidates": [row_summary(row) for row in star3[:8]],
        "rows": rows,
    }
    (ROOT / "m2-table-data.js").write_text("window.M2_TABLE_DATA = " + js(table_payload) + ";\n", encoding="utf-8")

    valuation_items: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = {key: row.get(key) for key in ("code", "symbol", "name", "marketCap", "floatMarketCap", "peRatio", "pbRatio")}
        valuation_items[row["code"]] = item
        valuation_items[row["symbol"]] = item
    (ROOT / "m2-valuation-map.js").write_text(
        "window.M2_VALUATION_MAP = " + js({"source": "Eastmoney close valuation fields", "generatedAt": generated_at, "rowCount": len(rows), "items": valuation_items}) + ";\n",
        encoding="utf-8",
    )

    focus_rows = star5 + star4 + star3
    candidates = []
    for index, row in enumerate(focus_rows[:12], start=1):
        candidates.append({
            "code": row["symbol"], "name": row["name"], "sector": "待R02板块复核", "state": row["status"],
            "stateClass": "watch" if row["executionStars"] >= 3 else row["recommendationClass"], "stage": row["stage"],
            "price": f"{row['price']:.2f}" if row["price"] is not None else "—", "change": pct_text(row["pct"], 2),
            "marketCap": row["marketCap"], "peRatio": row["peRatio"], "volume": f"{row['quoteAmountYi']:.2f}亿" if row["quoteAmountYi"] is not None else "数据不足",
            "volumeLabel": f"成交额/均额 {row['amountRatio']:.2f}×" if row["amountRatio"] is not None else "成交额待复核",
            "pivot": row["pivot"], "pivotPrice": row["pivotPrice"], "pivotLocked": True, "pivotStatus": row["pivotStatus"],
            "pivotReason": row["pivotReason"], "stageReason": row["stageReason"], "volumeRule": "突破日需明显放量",
            "advice": row["recommendation"], "adviceClass": row["recommendationClass"], "adviceReason": row["recommendationReason"],
            "executionStars": row["executionStars"], "executionLabel": row["executionLabel"], "executionAction": row["executionAction"],
            "buyRank": row["buyRank"], "action": row["executionAction"], "note": row["transition"], "baseAge": "40个交易日（算法）",
            "contractions": row["contractions"], "contractionDetail": f"历史日K + {close_label}收盘算法初筛，需人工确认图形。",
            "correction": f"{row['baseDepthPct']:.1f}%" if row["baseDepthPct"] is not None else "待确认", "chart": None, "priority": index,
        })
    m2_data = {
        "asOf": f"{close_iso} 收盘行情", "selectionAsOf": f"{close_iso} 收盘", "snapshotAsOf": close_iso,
        "quoteGeneratedAt": generated_at,
        "market": {"status": "收盘复核完成" if not history_missing else "部分数据待复核", "note": f"{close_label}双股票池已按统一规则精算；阶段符合不等于买点。", "stats": [
            {"label": "S1→S2过渡", "value": f"{stage_counts['S1→S2过渡']} 只"},
            {"label": "S2趋势", "value": f"{stage_counts['S2趋势']} 只"},
            {"label": "S2延伸", "value": f"{stage_counts['S2延伸']} 只"},
            {"label": "5星可执行", "value": f"{len(star5)} 只"},
        ]},
        "decision": {"title": f"正式阶段池：{len(formal_rows)} 只", "text": f"S1→S2过渡 {stage_counts['S1→S2过渡']} 只，S2趋势 {stage_counts['S2趋势']} 只，S2延伸 {stage_counts['S2延伸']} 只；5星 {len(star5)} 只。", "nextFocus": focus_rows[0]["name"] if focus_rows else "暂无", "pivot": focus_rows[0]["pivot"] if focus_rows else "未确认", "distance": focus_rows[0]["pivotDistance"] if focus_rows else "—"},
        "changes": [
            {"time": "阶段", "text": f"过渡 {stage_counts['S1→S2过渡']} / S2趋势 {stage_counts['S2趋势']} / 延伸 {stage_counts['S2延伸']} / 转弱 {stage_counts['S2转弱']} / 待复核 {stage_counts['待复核']}。"},
            {"time": "星级", "text": f"5星 {len(star5)}、4星 {len(star4)}、3星 {len(star3)}；过渡池最高只给2星。"},
            {"time": "变化", "text": f"新进入正式池 {new_count} 只，阶段状态变化 {len(changed)} 只。"},
            {"time": "边界", "text": "阶段与执行星级分离；5星也不替代止损、仓位和人工图形复核。"},
        ],
        "stageCounts": stage_counts,
        "candidates": candidates,
    }
    (ROOT / "m2-data.js").write_text("window.M2_DATA = " + js(m2_data) + ";\n", encoding="utf-8")
    snapshot = {
        "schemaVersion": 2, "generatedAt": generated_at, "asOf": close_iso, "maxAgeHours": 72, "barStatus": "complete",
        "sourceStatus": "live" if len(snapshot_history) == len(ordered_codes) else "partial",
        "source": f"history plus {close_iso} close import append; snapshot fallback {len(set(reused_snapshot_codes))}",
        "quotes": quote_rows, "history": snapshot_history,
        "warnings": [] if not history_missing else [f"历史日K不足：{len(history_missing)}只（{'、'.join(history_missing[:10])}）"],
        "reusedSnapshotCodes": sorted(set(reused_snapshot_codes)),
    }
    write_snapshot_bundle(snapshot)
    (ROOT / "m2-stage-state.json").write_text(json.dumps({"asOf": close_iso, "generatedAt": generated_at, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    args.analysis_dir.mkdir(parents=True, exist_ok=True)
    top_names = lambda values, limit=20: "、".join(row["name"] for row in values[:limit]) or "暂无"
    lines = [
        f"# {close_iso} M2 双阶段收盘分析", "", "## 数据校验", "",
        f"- S1→S2 导出：`导入/{args.transition_xlsx.name}`，有效 {len(transition_export)} 只。",
        f"- S2 导出：`导入/{args.s2_xlsx.name}`，有效 {len(s2_export)} 只。",
        f"- 两表重叠 {len(set(transition_export) & set(s2_export))} 只，合并去重后 {len(current_by_code)} 只；合并历史观察记录后网站共 {len(rows)} 只。",
        f"- 历史日K完整 {len(snapshot_history)} 只，数据不足 {len(history_missing)} 只：{'、'.join(history_missing) or '无'}。", "",
        "## 阶段结论", "",
        f"- S1→S2过渡：{stage_counts['S1→S2过渡']} 只。",
        f"- S2趋势：{stage_counts['S2趋势']} 只。",
        f"- S2延伸：{stage_counts['S2延伸']} 只。",
        f"- S2转弱：{stage_counts['S2转弱']} 只。",
        f"- 待复核：{stage_counts['待复核']} 只。", "",
        "阶段归属按 S2趋势结构 → S2转弱历史 → S1→S2硬条件 → 待复核 的顺序唯一判定。MA50与MA150的相对位置不再作为过渡池额外硬限制，也没有21～60日的人为阶段边界。", "",
        "## 执行星级", "",
        "| 星级 | 数量 | 候选 |", "| --- | ---: | --- |",
        *[f"| {stars}星 | {star_counts[stars]} | {top_names([row for row in rows if row['executionStars'] == stars], 12)} |" for stars in range(5, 0, -1)], "",
        "## 重点候选", "",
        "| 股票 | 阶段 | 星级 | 收盘/涨跌 | MA200斜率20日 | MA50斜率20日 | Pivot | 成交额/均额 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (star5 + star4 + star3)[:20]:
        lines.append(f"| {row['name']} | {row['stage']} | {row['executionStars']} | {row['price']:.2f} / {pct_text(row['pct'], 2)} | {pct_text(row['ma200SlopePct20d'], 2)} | {pct_text(row['ma50SlopePct20d'], 2)} | {row['pivot']} | {row['amountRatio']:.2f}x |" if row["amountRatio"] is not None else f"| {row['name']} | {row['stage']} | {row['executionStars']} | {row['price']:.2f} / {pct_text(row['pct'], 2)} | {pct_text(row['ma200SlopePct20d'], 2)} | {pct_text(row['ma50SlopePct20d'], 2)} | {row['pivot']} | 数据不足 |")
    lines.extend(["", "## 规则边界", "", "- S1→S2过渡股票最高为2星，只跟踪阶段变化，不提前视为S2买点。", "- S2延伸、S2转弱和待复核均为1星；4星和5星只允许出现在位置正常的S2趋势中。", "- 5星仍要求Pivot突破、成交额至少1.3倍、收缩证据、算法止损距离不超过8%和基本流动性；最终仍需人工复核。", "- 本报告是规则化筛选记录，不构成投资建议。"])
    (args.analysis_dir / f"{close_iso} M2收盘分析.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    sector_script = Path(__file__).with_name("generate-m2-sector-map.py")
    if sector_script.exists():
        try:
            subprocess.run([sys.executable, str(sector_script)], check=True, timeout=120)
        except (subprocess.SubprocessError, OSError) as error:
            print(f"warning: sector map refresh failed: {error}", file=sys.stderr)
    print(json.dumps({"rows": len(rows), "imports": len(current_by_code), "stages": stage_counts, "stars": star_counts, "historyMissing": history_missing}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_stage())
