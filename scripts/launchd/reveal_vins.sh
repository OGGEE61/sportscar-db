#!/bin/zsh
# Run by launchd (see README.md next to it): fill in VINs of pending Otomoto listings from this Mac.
cd "$(dirname "$0")/../.." || exit 1
echo "=== $(date '+%F %T')"
DB_BACKEND=d1 .venv/bin/python scripts/maintenance/reveal_pending_vins.py
