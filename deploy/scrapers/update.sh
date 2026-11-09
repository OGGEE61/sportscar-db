#!/usr/bin/env bash
# Bring the scrapers up to date with master: pull, and rebuild the image when something changed.
# Cron runs it hourly, so the VPS follows master like the GitHub workflows did. Run it by hand
# after a merge to update right away. A run already in progress keeps its old image.
#   update.sh [--force]    --force rebuilds even when master did not change
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p logs

before=$(git rev-parse HEAD)
git pull -q --ff-only
after=$(git rev-parse HEAD)

if [ "$before" != "$after" ] || [ "${1:-}" = "--force" ] || ! docker image inspect sportscar-scraper > /dev/null 2>&1; then
  {
    echo "=== $(date '+%F %T') build ${after:0:7}"
    docker compose -f deploy/scrapers/compose.yml build -q scraper
    docker image prune -f > /dev/null
  } >> logs/update.log 2>&1
fi
