#!/usr/bin/env python3
"""Capture one durable M2 selection snapshot for the display-only website.

Run this after the A-share close (recommended: 15:30 Asia/Shanghai). The script
does the network calls and VCP pre-screening locally, then writes one atomic JSON
file. The website reads that file and never needs to wait for one history API
call per card just to paint its cards.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import M2_WATCHLIST, get_m2_history_payload, get_m2_watchlist_payload


def load_existing_snapshot(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the M2 daily selection snapshot")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "m2-snapshot.json",
        help="output JSON path (default: repository root/m2-snapshot.json)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="include the current intraday bar and live quotes instead of completed bars only",
    )
    args = parser.parse_args()

    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    history_payload = get_m2_history_payload(force=True, completed_only=not args.live)
    quote_payload = get_m2_watchlist_payload(force=True)
    history = history_payload.get("history") or {}
    expected = len(M2_WATCHLIST)
    reused_from_api = set(history_payload.get("reusedSnapshotCodes") or [])
    live_history_count = max(0, len(history) - len(reused_from_api))

    output = args.output.resolve()
    existing = load_existing_snapshot(output)
    existing_history = existing.get("history") or {}
    existing_quotes = {str(item.get("code")): item for item in existing.get("quotes") or []}
    live_quotes = {str(item.get("code")): item for item in quote_payload.get("quotes") or []}
    reused_codes = []
    for item in M2_WATCHLIST:
        code = item["code"]
        if code not in history and code in existing_history:
            history[code] = existing_history[code]
            reused_codes.append(code)

    quotes = []
    for item in M2_WATCHLIST:
        if item["code"] in live_quotes:
            quotes.append(live_quotes[item["code"]])
            continue
        latest = (history.get(item["code"]) or {}).get("rows", [])[-1:]
        if not latest and item["code"] in existing_quotes:
            quotes.append(existing_quotes[item["code"]])
            continue
        if latest:
            row = latest[0]
            quotes.append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "price": row.get("close"),
                    "pct": row.get("pct"),
                    "change": row.get("change"),
                    "volumeLots": row.get("volume"),
                    "amountYi": row.get("amountYi"),
                    "amplitude": row.get("amplitude"),
                    "turnover": row.get("turnover"),
                }
            )

    if not live_history_count and existing_history:
        print(
            f"Snapshot not written: live history unavailable; kept existing "
            f"snapshot with history={len(existing_history)}",
            file=sys.stderr,
        )
        for warning in history_payload.get("warnings") or []:
            print(f"- {warning}", file=sys.stderr)
        return 1
    if not history:
        print(
            f"Snapshot not written: quotes={len(quotes)}/{expected}, "
            f"history={len(history)}/{expected}",
            file=sys.stderr,
        )
        for warning in history_payload.get("warnings") or []:
            print(f"- {warning}", file=sys.stderr)
        return 1

    as_of_values = [item.get("asOf") for item in history.values() if item.get("asOf")]
    local_now = dt.datetime.now().astimezone()
    today = local_now.date().isoformat()
    current_bar_is_partial = args.live and (
        local_now.hour < 15 or (local_now.hour == 15 and local_now.minute < 30)
    ) and any(value == today for value in as_of_values)
    quotes_complete = len(live_quotes) == expected
    snapshot = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "asOf": max(as_of_values) if as_of_values else None,
        "maxAgeHours": float(os.environ.get("M2_SNAPSHOT_MAX_AGE_HOURS", "36")),
        "barStatus": "partial" if current_bar_is_partial else "complete",
        "sourceStatus": "live" if live_history_count == expected and len(history) == expected and quotes_complete else "partial",
        "source": "Local Session · Eastmoney live quotes + adjusted daily OHLCV + M2 VCP scan",
        "quoteGeneratedAt": quote_payload.get("generatedAt") or generated_at,
        "quoteSource": quote_payload.get("source") or "Eastmoney push2/push2delay ulist",
        "quotes": quotes,
        "history": history,
        "warnings": (history_payload.get("warnings") or [])
        + (quote_payload.get("warnings") or [])
        + ([] if quotes_complete else [f"实时报价不完整：{len(live_quotes)}/{expected}"])
        + ([f"沿用已有快照代码：{','.join(reused_codes)}"] if reused_codes else []),
        "reusedSnapshotCodes": sorted(set(reused_codes) | reused_from_api),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output)
    print(f"Wrote {output}")
    print(f"asOf={snapshot['asOf']} generatedAt={generated_at} barStatus={snapshot['barStatus']} stocks={len(history)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
