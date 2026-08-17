#!/usr/bin/env python3
"""Generate the M2 website data files from a close-time iWencai export."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import re
import subprocess
import sys
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
    "exchange": "交易所",
    "from_low": "(收盘价-最低价最小值)/绝对值(最低价最小值)",
}


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
    try:
        return server._get_m2_history(item, close_date)
    except Exception:
        return None


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
    metrics = calc_metrics(rows)
    return {
        **history,
        "asOf": close_iso,
        "rows": rows[-160:],
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


def calc_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
    last_ma200 = finite(rows[-1].get("ma200"))
    prior_ma200 = finite(rows[-21].get("ma200")) if len(rows) >= 21 else None
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
        "contractionCount": len(contractions),
        "contractions": contractions,
        "vcpStatus": vcp_status,
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


def classify(row: dict[str, Any], pivot: dict[str, Any], metrics: dict[str, Any], close_label: str) -> dict[str, Any]:
    if not row["currentQualified"]:
        return {
            "recommendation": "待复核，不直接买",
            "className": "review",
            "reason": f"旧观察池保留项，没有新的 {close_label} 收盘导入确认；先复核趋势和图形。",
            "stars": 1,
            "label": "1星 待复核",
            "action": "旧观察池保留，先复核趋势和图形。",
            "buyRank": 0,
        }
    price = finite(row["price"])
    pivot_price = finite(pivot.get("price"))
    distance = (pivot_price - price) / price * 100 if price and pivot_price else None
    breakout = (price / pivot_price - 1) * 100 if price and pivot_price else None
    amount_ratio = row.get("amountRatio")
    contractions = int(metrics.get("contractionCount") or 0)
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
        and contractions >= 1
        and (price_to_ma50 is None or price_to_ma50 <= 15)
        and pct <= 7
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
    if distance is not None and -3 <= distance <= 3 and contractions >= 1 and (amount_ratio or 0) >= 0.8:
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
    args = parser.parse_args()

    export = pd.read_excel(args.xlsx)
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
    ]
    histories: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(fetch_history, item, close_date): item for item in watch_items}
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            history = future.result()
            if history:
                histories[item["code"]] = history

    rows: list[dict[str, Any]] = []
    snapshot_history: dict[str, Any] = {}
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
        history = append_current_bar(histories.get(bare(code)), current_quote, close_date)
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
        row_seed = {
            "code": code,
            "name": name,
            "price": price,
            "pct": pct,
            "currentQualified": is_current,
            "amountRatio": amount_ratio,
            "priceToMa50Pct": price_to_ma50,
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
        from_high = (price / high52 - 1) * 100 if price and high52 else None
        from_low = (price / low52 - 1) * 100 if price and low52 else None
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
  return {{ asOf: '{close_iso} 收盘行情', selectionAsOf: '{close_iso} 收盘', snapshotAsOf: '{close_iso}', snapshotGeneratedAt: {js(generated_at)}, quoteGeneratedAt: {js(generated_at)}, quoteSourceStatus: 'live', quoteSource: {js(quote_source)}, source: "观察池：{close_label} 收盘合格候选 ∪ 既有观察池待复核；图形：历史日K追加 {close_label} 收盘 OHLCV；报价：东方财富收盘行情", rowCount: rows.length, importedCount: {len(export)}, currentQualifiedCount: {current_count}, priorCloseQualified: {prior_count}, newSinceClose: {new_count}, carryForwardCount: {carry_count}, priorityCount: {len(star4)}, executableCount: {len(star5)}, nearPivotCount: {len(star3)}, waitCount: {len(wait)}, cautionCount: {len(caution)}, reviewCount: {len(review)}, upCount: {sum((row['pct'] or 0) > 0 for row in rows)}, period: '{close_iso} 收盘观察池 / {close_iso} 收盘行情', note: "{close_label} 收盘已按星级重新分层；5 星才是规则化可执行候选，4 星仍是确认中，不生成自动买入指令。", topMovers: {js([row_summary(row) for row in sorted(rows, key=lambda row: row['pct'] or -999, reverse=True)[:8]])}, executableCandidates: {js([row_summary(row) for row in star5[:8]])}, priorityCandidates: {js([row_summary(row) for row in star4[:8]])}, nearPivotCandidates: {js([row_summary(row) for row in star3[:8]])}, cautionCandidates: {js([row_summary(row) for row in caution[:8]])}, reviewStrongCandidates: {js([row_summary(row) for row in sorted(review, key=lambda row: row['pct'] or -999, reverse=True)[:5]])}, rows }};
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
        {"label": "今日上涨", "value": f"{sum((row['pct'] or 0) > 0 for row in rows)} 只"},
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
        "source": f"Local Session · history plus {close_iso} close quote/import append",
        "quotes": quote_rows,
        "history": snapshot_history,
        "warnings": [] if len(snapshot_history) == len(ordered_codes) else [f"部分历史日K未取到：{len(snapshot_history)}/{len(ordered_codes)}"],
        "reusedSnapshotCodes": [],
    }
    (ROOT / "m2-snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

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


if __name__ == "__main__":
    raise SystemExit(main())
