# Scrapers on the VPS

The Otomoto, OLX and Autoplac scrapers run on the cyber_Folks VPS (178.250.47.196) and send
listings to the app on Vercel, the same way the GitHub workflows did. GitHub's runners were
being blocked (Autoplac: Cloudflare 403, Otomoto: VIN reveals 403); the VPS is not.

How it works: the host's cron (`/etc/cron.d/sportscar-scrapers`, from [crontab](crontab)) calls
[run.sh](run.sh), which starts one fresh container from the `sportscar-scraper` image. Only one
job per source runs at a time; a run that finds the previous one still going is skipped.
[update.sh](update.sh) pulls `master` hourly and rebuilds the image when it changed.

## Layout on the server

| Path | What |
|---|---|
| `/opt/sportscar` | clone of this repo (public, cloned over https) |
| `/opt/sportscar/logs/<source>.log` | output of each run; `update.log` for rebuilds. Rotated weekly |
| `/opt/sportscar-secrets/scrapers.env` | `API_TOKEN=…`, `BASE_URL=https://…` (mode 600, root) |
| `/opt/sportscar-secrets/otomoto_cookies.json` | logged-in Otomoto cookies (mode 600, owner uid 10001 = the container user) |

## Install (once)

```bash
git clone https://github.com/OGGEE61/sportscar-db.git /opt/sportscar
install -d -m 700 /opt/sportscar-secrets
# copy scrapers.env and otomoto_cookies.json in from the Mac (file to file, never through a chat), then:
chmod 600 /opt/sportscar-secrets/*
chown 10001 /opt/sportscar-secrets/otomoto_cookies.json
/opt/sportscar/deploy/scrapers/update.sh --force          # first build, a few minutes
/opt/sportscar/deploy/scrapers/run.sh otomoto scrapers/run_all.py m2_g87   # one test run
install -m 644 /opt/sportscar/deploy/scrapers/crontab /etc/cron.d/sportscar-scrapers
install -m 644 /opt/sportscar/deploy/scrapers/logrotate /etc/logrotate.d/sportscar
```

## Everyday

- Logs: `tail -f /opt/sportscar/logs/otomoto.log`. Run results also appear in the app's run log, marked `[VPS]`.
- Run something now: `/opt/sportscar/deploy/scrapers/run.sh otomoto scrapers/run_all.py <target>` (targets: see `scrapers/run_all.py`).
- Update right after a merge: `/opt/sportscar/deploy/scrapers/update.sh`.
- New Otomoto cookies: copy the file over `/opt/sportscar-secrets/otomoto_cookies.json` (keep owner 10001, mode 600). The next run uses it.
- Pause everything: `rm /etc/cron.d/sportscar-scrapers`; resume by installing it again.
