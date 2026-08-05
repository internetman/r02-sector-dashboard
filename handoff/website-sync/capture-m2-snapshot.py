#!/usr/bin/env python3
"""Capture one durable M2 selection snapshot for the display-only website.

Run this after the A-share close (recommended: 15:30 Asia/Shanghai). The script
does the network calls and VCP pre-screening locally, then writes one atomic JSON
file. The website reads that file and never needs to wait for six history API
calls just to paint its cards.
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

from server import M2_WATCHLIST, get_m2_history_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the M2 daily selection snapshot")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "m2-snapshot.json",
        help="output JSON path (default: repository root/m2-snapshot.json)",
    )
    args = parser.parse_args()

    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    history_payload = get_m2_history_payload(force=True, completed_only=True)
    history = history_payload.get("history") or {}
    expected = len(M2_WATCHLIST)

    quotes = []
    for item in M2_WATCHLIST:
        latest = (history.get(item["code"]) or {}).get("rows", [])[-1:]
        if not latest:
            continue
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

    if len(quotes) < expected or len(history) < expected:
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
    current_bar_is_partial = (
        local_now.hour < 15 or (local_now.hour == 15 and local_now.minute < 30)
    ) and any(value == today for value in as_of_values)
    snapshot = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "asOf": max(as_of_values) if as_of_values else None,
        "maxAgeHours": float(os.environ.get("M2_SNAPSHOT_MAX_AGE_HOURS", "36")),
        "barStatus": "partial" if current_bar_is_partial else "complete",
        "sourceStatus": "live",
        "source": "Local Session · Eastmoney adjusted daily OHLCV + M2 VCP scan",
        "quotes": quotes,
        "history": history,
        "warnings": history_payload.get("warnings") or [],
    }

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(output)
    print(f"Wrote {output}")
    print(f"asOf={snapshot['asOf']} generatedAt={generated_at} barStatus={snapshot['barStatus']} stocks={len(history)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
