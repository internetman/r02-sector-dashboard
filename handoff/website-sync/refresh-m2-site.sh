#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${R02_SOURCE_DIR:-/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard}"
M2_PROJECT_DIR="${M2_PROJECT_DIR:-/Users/leon/Documents/400=学习/402=投资/Mark Minervini 2}"
IMPORT_DIR="${M2_IMPORT_DIR:-$M2_PROJECT_DIR/导入}"
cd "$SOURCE_DIR"

if [ -n "${M2_TRANSITION_XLSX:-}" ]; then
  TRANSITION_XLSX="$M2_TRANSITION_XLSX"
else
  TRANSITION_XLSX=$(python3 -c 'from pathlib import Path; import sys; files=list(Path(sys.argv[1]).glob("*收盘*S1-S2*.xlsx")); print(max(files, key=lambda p: p.stat().st_mtime) if files else "")' "$IMPORT_DIR")
fi

if [ -n "${M2_S2_XLSX:-}" ]; then
  S2_XLSX="$M2_S2_XLSX"
else
  S2_XLSX=$(python3 -c 'from pathlib import Path; import sys; files=list(Path(sys.argv[1]).glob("*收盘*S2 阶段*.xlsx")); print(max(files, key=lambda p: p.stat().st_mtime) if files else "")' "$IMPORT_DIR")
fi

if [ -z "$TRANSITION_XLSX" ] || [ ! -f "$TRANSITION_XLSX" ] || [ -z "$S2_XLSX" ] || [ ! -f "$S2_XLSX" ]; then
  echo "Missing S1-S2 or S2 close export in $IMPORT_DIR" >&2
  exit 1
fi

echo "[M2] generate close analysis from $TRANSITION_XLSX and $S2_XLSX"
python3 handoff/website-sync/generate-m2-close.py "$TRANSITION_XLSX" "$S2_XLSX"

echo "[M2] validate generated assets"
python3 -m py_compile server.py api/dashboard.py api/m2-watchlist.py api/m2-history.py handoff/website-sync/generate-m2-close.py handoff/website-sync/generate-m2-sector-map.py
node -e "const fs=require('fs'),vm=require('vm'); const c={window:{}}; vm.createContext(c); for (const f of ['m2-table-data.js','m2-data.js','m2-sector-map.js','m2-valuation-map.js']) vm.runInContext(fs.readFileSync(f,'utf8'),c); const t=c.window.M2_TABLE_DATA,s=JSON.parse(fs.readFileSync('m2-snapshot.json')); const codes=new Set(s.candidateCodes||[]),history=s.history||{}; if(!t.currentQualifiedCount || codes.size!==t.rowCount || [...codes].some(code=>!history[code])) throw new Error('generated M2 candidate assets failed consistency check'); console.log({candidates:t.rowCount,archived:t.archivedRowCount,current:t.currentQualifiedCount,asOf:t.asOf});"

echo "[M2] commit source snapshot"
git add m2-data.js m2-table-data.js m2-snapshot.json m2-history-index.json m2-history m2-stage-state.json m2-sector-map.js m2-valuation-map.js
if ! git diff --cached --quiet; then
  git commit -m "Refresh M2 close snapshot"
  git push origin HEAD:main
fi

echo "[M2] publish snapshot to heimaq.com"
bash handoff/website-sync/sync-to-vercel-repo.sh "Refresh M2 daily selection snapshot"

echo "[M2] done"
