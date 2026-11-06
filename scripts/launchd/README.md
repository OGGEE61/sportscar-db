# VIN reveals from the Mac

Otomoto blocks "Show VIN" requests from GitHub's runners after a burst (HTTP 403), but answers a home
connection. GitHub keeps collecting listings, prices and removals. Every 4 hours this Mac fills in the
VINs of pending Otomoto listings (`scripts/maintenance/reveal_pending_vins.py`). Each run writes a
`[lokalnie] VIN backfill: ...` line to the run log.

It needs a logged-in `scrapers/otomoto_cookies.json`, the same cookies as the `OTOMOTO_COOKIES` secret.

Install:

    sed "s|REPO|$PWD|g" scripts/launchd/pl.sportscar-db.reveal-vins.plist > ~/Library/LaunchAgents/pl.sportscar-db.reveal-vins.plist
    mkdir -p logs
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/pl.sportscar-db.reveal-vins.plist

Run now: `launchctl kickstart gui/$(id -u)/pl.sportscar-db.reveal-vins`. Output: `logs/reveal_vins.log`.

Remove:

    launchctl bootout gui/$(id -u)/pl.sportscar-db.reveal-vins
    rm ~/Library/LaunchAgents/pl.sportscar-db.reveal-vins.plist

It runs whatever branch is checked out in this folder.
