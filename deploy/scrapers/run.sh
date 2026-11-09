#!/usr/bin/env bash
# Run one scraper job in a fresh container, as cron does (see crontab).
#   run.sh <source> <script> [target]     e.g. run.sh otomoto scrapers/run_all.py next_3
# One job per source at a time: a run that finds the previous one still going is skipped.
# Output goes to /opt/sportscar/logs/<source>.log. A crash is reported to the run log
# (/api/log_run), as the GitHub workflows do.
set -uo pipefail

source_name=$1; shift
cd "$(dirname "$0")/../.."
mkdir -p logs
log="logs/$source_name.log"

{
  echo "=== $(date '+%F %T') $*"
  flock -n -E 75 "/run/lock/sportscar-$source_name.lock" \
    timeout 3h docker compose -f deploy/scrapers/compose.yml run --rm -T scraper python "$@"
  code=$?
  echo "=== exit $code"
} >> "$log" 2>&1

if [ "$code" -eq 75 ]; then
  echo "previous $source_name run still going, skipped" >> "$log"
elif [ "$code" -ne 0 ]; then
  set -a; . /opt/sportscar-secrets/scrapers.env; set +a
  curl -s -m 10 -X POST "$BASE_URL/api/log_run" \
    -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
    -d "{\"status\": \"error\", \"source\": \"$source_name\", \"message\": \"[VPS] $* crashed or failed (exit $code), see logs/$source_name.log on the VPS\"}" \
    > /dev/null || true
fi
