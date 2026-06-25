#!/bin/bash
# 生成 frontend/vendor（Luckysheet + jQuery），供内网/容器离线部署
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
npm install luckysheet@2.1.13 jquery@3.6.4 --no-save
cd "$ROOT"
node scripts/copy-frontend-vendor.js

# Verify the vendored build includes English locale strings so the UI can switch
# to English when App.I18n.getLang() === 'en'.
if ! grep -q '"Undo"' frontend/vendor/luckysheet/luckysheet.umd.js; then
  echo "ERROR: Luckysheet English strings not found" >&2
  exit 1
fi

echo "Done. Vendor files are under frontend/vendor/"
