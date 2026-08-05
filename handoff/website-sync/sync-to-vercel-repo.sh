#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${R02_SOURCE_DIR:-/Users/leon/Library/Mobile Documents/iCloud~md~obsidian/Documents/投资/tools/r02-sector-dashboard}"
PROD_REPO="${R02_PROD_REPO:-https://github.com/internetman/blackhorse-quant.git}"
BRANCH="${R02_PROD_BRANCH:-main}"
WORKDIR="${R02_DEPLOY_WORKDIR:-$(mktemp -d /tmp/blackhorse-quant-deploy.XXXXXX)}"
COMMIT_MESSAGE="${1:-Sync R02 sector dashboard}"

echo "Source: $SOURCE_DIR"
echo "Production repo: $PROD_REPO"
echo "Workdir: $WORKDIR"

if [ ! -d "$SOURCE_DIR/.git" ]; then
  echo "Source dir is not a git repo: $SOURCE_DIR" >&2
  exit 1
fi

python3 -m py_compile "$SOURCE_DIR/server.py" "$SOURCE_DIR/api/dashboard.py"
node - "$SOURCE_DIR/index.html" <<'NODE'
const fs = require('fs');
const htmlPath = process.argv[2];
const html = fs.readFileSync(htmlPath, 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('script tag not found');
new Function(match[1]);
console.log('index script syntax ok');
NODE

if [ ! -d "$WORKDIR/.git" ]; then
  rm -rf "$WORKDIR"
  git clone "$PROD_REPO" "$WORKDIR"
fi

git -C "$WORKDIR" fetch origin "$BRANCH"
git -C "$WORKDIR" checkout "$BRANCH"
git -C "$WORKDIR" pull --ff-only origin "$BRANCH"

find "$WORKDIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

cp "$SOURCE_DIR/README.md" "$WORKDIR/README.md"
cp "$SOURCE_DIR/index.html" "$WORKDIR/index.html"
cp "$SOURCE_DIR/server.py" "$WORKDIR/server.py"
cp "$SOURCE_DIR/vercel.json" "$WORKDIR/vercel.json"
cp "$SOURCE_DIR/.gitignore" "$WORKDIR/.gitignore"
cp "$SOURCE_DIR/.vercelignore" "$WORKDIR/.vercelignore"
mkdir -p "$WORKDIR/api"
cp "$SOURCE_DIR/api/dashboard.py" "$WORKDIR/api/dashboard.py"

python3 -m py_compile "$WORKDIR/server.py" "$WORKDIR/api/dashboard.py"

git -C "$WORKDIR" status --short
if git -C "$WORKDIR" diff --quiet && git -C "$WORKDIR" diff --cached --quiet; then
  echo "No deployment changes to commit."
  exit 0
fi

git -C "$WORKDIR" add README.md index.html server.py vercel.json .gitignore .vercelignore api/dashboard.py
git -C "$WORKDIR" commit -m "$COMMIT_MESSAGE"
git -C "$WORKDIR" push origin "$BRANCH"

echo "Pushed. Vercel should deploy automatically from $PROD_REPO#$BRANCH."

