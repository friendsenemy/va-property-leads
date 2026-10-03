#!/usr/bin/env bash
# Commit this job's results on top of the latest main.
#
#   commit-data.sh "<message>" <file> [<file> ...]
#
# The files named are the ones this job is the source of truth for (what it fetched).
# Everything else under data/ is taken from the latest main, so a job never overwrites
# what another job fetched while it was running or anything a person edited by hand.
# The boards are then rebuilt from the merged inputs and committed.
set -euo pipefail
MSG="$1"; shift
git config user.name "va-property-leads bot"
git config user.email "actions@users.noreply.github.com"
rm -rf /tmp/own && mkdir -p /tmp/own
for f in "$@"; do
  if [ -f "$f" ]; then mkdir -p "/tmp/own/$(dirname "$f")"; cp "$f" "/tmp/own/$f"; fi
  if [ -d "$f" ]; then mkdir -p "/tmp/own/$f"; cp -r "$f/." "/tmp/own/$f/"; fi      # a whole folder this job owns
done
for attempt in 1 2 3 4; do
  git fetch origin main
  git checkout -f -B main origin/main
  git clean -fdq data
  cp -r /tmp/own/. .
  # King George's boards are rebuilt from the merged inputs when this job has its index;
  # a job for another county (which owns its whole folder) leaves them as they are on main.
  if [ -f .cache/kg.sqlite ]; then VAPL_COUNTY=king-george python -m engine.build_board --no-fetch; fi
  git add data
  if git diff --cached --quiet; then echo "No changes."; exit 0; fi
  git commit -q -m "$MSG"
  if git push origin main; then exit 0; fi
  echo "push raced with another commit; retrying"
  sleep $((attempt * 15))
done
exit 1
