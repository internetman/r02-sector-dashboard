#!/usr/bin/env python3
"""Fetch Eastmoney industry/concept labels for the current M2 watchlist."""

from __future__ import annotations

import json
import http.client
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TABLE_DATA = ROOT / "m2-table-data.js"
OUTPUT = ROOT / "m2-sector-map.js"
EASTMONEY_UT = "fa5fd1943c7b386f172d6893dbfba10b"


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def bare(code: str) -> str:
    return str(code).split(".", 1)[0]


def market_for(code: str) -> str:
    return "1" if str(code).endswith(".SH") or bare(code).startswith("6") else "0"


def load_watchlist() -> list[tuple[str, str]]:
    source = TABLE_DATA.read_text(encoding="utf-8")
    match = re.search(r"const raw\s*=\s*(\[\[.*?\]\]);\s*const rows", source, re.S)
    if not match:
        raise RuntimeError(f"Cannot parse raw rows from {TABLE_DATA}")
    rows = json.loads(match.group(1))
    return [(str(row[0]), str(row[1])) for row in rows]


def load_existing_items() -> dict[str, dict[str, Any]]:
    if not OUTPUT.exists():
        return {}
    match = re.search(r"window\.M2_SECTOR_MAP\s*=\s*(\{.*\});", OUTPUT.read_text(encoding="utf-8"), re.S)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    items = payload.get("items")
    return items if isinstance(items, dict) else {}


def fetch_stock_sector(code: str, name: str) -> dict[str, Any]:
    fields = "f57,f58,f127,f128,f129"
    secid = f"{market_for(code)}.{bare(code)}"
    url = (
        "https://push2.eastmoney.com/api/qt/stock/get"
        f"?ut={EASTMONEY_UT}&fltt=2&invt=2&secid={secid}&fields={fields}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.load(response)
            break
        except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.4 + attempt * 0.5)
    else:
        raise RuntimeError(last_error)
    data = payload.get("data") or {}
    concepts = [
        item.strip()
        for item in str(data.get("f129") or "").split(",")
        if item.strip() and item.strip() != "-"
    ]
    industry = data.get("f127") if data.get("f127") != "-" else None
    region = data.get("f128") if data.get("f128") != "-" else None
    return {
        "code": code,
        "symbol": bare(code),
        "name": data.get("f58") or name,
        "industry": industry or "行业待补",
        "region": region or "地域待补",
        "concepts": concepts[:12],
        "sectorGroup": sector_group(industry or "", concepts),
    }


def sector_group(industry: str, concepts: list[str]) -> str:
    text = f"{industry} {' '.join(concepts)}"
    industry_rules = [
        ("医药健康", ("医药", "医疗", "生物", "创新药", "化学制药")),
        ("半导体AI", ("半导体", "元件", "消费电子", "电子化学品", "通信设备", "光学光电子", "计算机设备", "软件开发")),
        ("新能源车链", ("电池", "汽车零部件", "汽车整车", "电机")),
        ("光伏储能", ("光伏", "风电", "能源金属")),
        ("资源周期", ("煤炭", "有色金属", "贵金属", "小金属", "工业金属", "采掘")),
        ("化工材料", ("化学制品", "化学原料", "化纤", "塑料制品", "玻璃玻纤", "非金属材料")),
        ("高端制造", ("电网设备", "专用设备", "通用设备", "工程机械", "仪器仪表", "航天航空", "船舶制造")),
        ("交通物流", ("航运", "港口", "物流", "铁路公路")),
        ("金融地产", ("银行", "证券", "保险", "房地产")),
        ("消费服务", ("食品饮料", "家电", "消费电子", "游戏", "文化传媒", "旅游酒店", "教育")),
    ]
    for label, keywords in industry_rules:
        if any(keyword in industry for keyword in keywords):
            return label
    rules = [
        ("医药健康", ("医药", "医疗", "生物", "创新药", "CXO", "CRO", "减肥药", "辅助生殖")),
        ("光伏储能", ("光伏", "逆变器", "储能", "太阳能")),
        ("新能源车链", ("电池", "新能源", "锂电", "固态电池", "特斯拉", "汽车", "充电桩")),
        ("半导体AI", ("半导体", "芯片", "算力", "人工智能", "AI", "存储", "PCB", "光通信")),
        ("资源周期", ("煤炭", "有色", "稀土", "钨", "锗", "锌", "铝", "锡", "贵金属", "小金属")),
        ("化工材料", ("化学", "化工", "材料", "氟化工", "新材料", "玻璃纤维", "塑料")),
        ("高端制造", ("设备", "机械", "机器人", "工业", "船舶", "电网", "电源")),
        ("交通物流", ("航运", "港口", "物流", "铁路", "公路")),
        ("金融地产", ("银行", "证券", "保险", "房地产")),
        ("消费服务", ("食品", "饮料", "家电", "消费", "传媒", "游戏", "教育")),
    ]
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return "其它主题"


def main() -> None:
    mapping: dict[str, dict[str, Any]] = {}
    existing = load_existing_items()
    failures: list[str] = []
    for index, (code, name) in enumerate(load_watchlist(), start=1):
        item = existing.get(code) or existing.get(bare(code))
        if not item or item.get("industry") == "行业待补":
            try:
                item = fetch_stock_sector(code, name)
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, json.JSONDecodeError, RuntimeError) as error:
                failures.append(f"{code}:{error}")
                item = {
                    "code": code,
                    "symbol": bare(code),
                    "name": name,
                    "industry": "行业待补",
                    "region": "地域待补",
                    "concepts": [],
                    "sectorGroup": "其它主题",
                }
        else:
            item = dict(item)
            item["sectorGroup"] = sector_group(str(item.get("industry") or ""), list(item.get("concepts") or []))
        mapping[code] = item
        mapping[bare(code)] = item
        time.sleep(0.15)

    payload = {
        "source": "Eastmoney stock/get fields f127 industry, f128 region, f129 concepts",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rowCount": len({code for code, _ in load_watchlist()}),
        "failures": failures[:20],
        "items": mapping,
    }
    OUTPUT.write_text("window.M2_SECTOR_MAP = " + js(payload) + ";\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {payload['rowCount']} rows; failures={len(failures)}")


if __name__ == "__main__":
    main()
