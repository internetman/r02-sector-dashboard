#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${R02_SOURCE_DIR:-/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard}"
cd "$SOURCE_DIR"

echo "[M2] capture local selection snapshot"
python3 handoff/website-sync/capture-m2-snapshot.py

echo "[M2] publish snapshot to heimaq.com"
bash handoff/website-sync/sync-to-vercel-repo.sh "Refresh M2 daily selection snapshot"

echo "[M2] done"
