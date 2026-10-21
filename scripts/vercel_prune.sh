#!/usr/bin/env bash
# Delete old Vercel deployments for a project, keeping the current production
# deployment and the newest preview. Usage: scripts/vercel_prune.sh [project] [--yes]
set -euo pipefail
PROJECT="${1:-sportscar-db}"
YES="${2:-}"
TEAM=nexopel
LIST=$(mktemp)

npx vercel api "/v6/deployments?teamId=$TEAM&limit=100&app=$PROJECT" --raw | python3 -c '
import sys, json
ds = json.load(sys.stdin)["deployments"]
ds.sort(key=lambda d: d["created"], reverse=True)
keep, seen = set(), set()
for d in ds:
    env = d.get("target") or "preview"
    if d["state"] == "READY" and env not in seen:
        seen.add(env); keep.add(d["uid"])
for d in ds:
    if d["uid"] not in keep:
        print(d["uid"], d.get("target") or "preview", d["state"])
' > "$LIST"

echo "Will delete $(wc -l < "$LIST") deployments of $PROJECT"
cat "$LIST"
[ "$YES" = "--yes" ] || { echo "Dry run. Re-run with --yes to delete."; exit 0; }
while read -r uid _; do npx vercel remove "$uid" --safe --yes || true; done < "$LIST"
