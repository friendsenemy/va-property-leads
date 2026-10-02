#!/usr/bin/env bash
# Lay the regenerated data files on top of the latest main and push.
# Files a person edits by hand are never overwritten by a job.
set -euo pipefail
MSG="$1"
git config user.name "va-property-leads bot"
git config user.email "actions@users.noreply.github.com"
rm -rf /tmp/out && mkdir -p /tmp/out && cp -r data /tmp/out/
git fetch origin main
git checkout -f -B main origin/main
rsync -a \
  --exclude 'obits/manual.csv' --exclude 'heirs/import.csv' --exclude 'scc/status.csv' --exclude 'sales/parcels.csv' \
  --include 'obits/storke.json' --include 'obits/matches.json' --include 'obits/low.json' --include 'obits/clerk-filings.json' \
  --exclude 'obits/*.json' \
  /tmp/out/data/ data/
git add data
if git diff --cached --quiet; then echo "No changes."; exit 0; fi
git commit -m "$MSG"
git push origin main
