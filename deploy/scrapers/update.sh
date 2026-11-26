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

# The schedule follows master too. Only while installed: removing it pauses everything (README)
cron_file=/etc/cron.d/sportscar-scrapers
if [ -f "$cron_file" ] && ! cmp -s deploy/scrapers/crontab "$cron_file"; then
  install -m 644 deploy/scrapers/crontab "$cron_file"
  echo "=== $(date '+%F %T') crontab installed from ${after:0:7}" >> logs/update.log
fi

if [ "$before" != "$after" ] || [ "${1:-}" = "--force" ] || ! docker image inspect sportscar-scraper > /dev/null 2>&1; then
  {
    echo "=== $(date '+%F %T') build ${after:0:7}"
    docker compose -f deploy/scrapers/compose.yml build -q scraper
    docker image prune -f > /dev/null
    docker builder prune -af --filter until=168h > /dev/null   # build cache unused for a week
  } >> logs/update.log 2>&1
fi
