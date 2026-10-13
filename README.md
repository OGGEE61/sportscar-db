# SportsCar DB

A lightweight, serverless web application for tracking the **performance car secondary market** (e.g., otomoto.pl). It tracks price history, listing observations, VIN-based identity, and condition reports. 

Built for enthusiasts and researchers who want to systematically follow high-end car listings and understand how prices move over time.

---

## What makes it different?

Most car-tracking tools show a snapshot: current listings and current prices. SportsCar DB is **observation-based**. Every time a scraper runs, a new timestamped row is created. This allows you to:
- Watch a single ad's **price drop over weeks** before it sells.
- See exactly **when an ad disappeared** (likely sold).
- Compare what the same car sold for vs. what it was originally listed at.
- Track market-wide trends: average prices, active inventory, and source distribution.

The **VIN is the permanent identity key**. All data attaches to a VIN, not an ad ID. If the same car is listed twice at different prices, both observations live under the same VIN.

---

## Key Features
- **Dashboard** — Live charts showing make distribution, price ranges, weekly volume.
- **VIN Decryption** — Bypasses otomoto client-side AES-256-GCM encryption locally.
- **Cloud Storage** — Photos are automatically compressed and saved to Cloudflare R2 to save space and survive listing expiries.
- **Review Queue** — New cars land in a staging area for manual approval; known cars are silently tracked.
- **Automated Scrapers** — Designed to run on GitHub Actions to continually feed data to the Vercel-hosted API.
- **Placeholder VINs** — Listings missing a VIN get a placeholder and can be manually merged later.

---

## Deployment (Vercel + Cloudflare)

This project is optimized for a Serverless architecture:
1. **Frontend/API**: Hosted on **Vercel** (`vercel.json` included).
2. **Database**: Hosted on **Cloudflare D1** (Serverless SQLite).
3. **Photos**: Hosted on **Cloudflare R2** (S3-compatible bucket).
4. **Scraping**: Automated via **GitHub Actions** (`.github/workflows/scrapers.yml`).

### Running Locally
You can run it locally with standard SQLite by simply cloning the repo and skipping the `.env` Cloudflare keys.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then run any scraper in a second terminal:
```bash
# Otomoto:
python scrapers/otomoto/audi_rs3_8v.py
python scrapers/run_all.py single

# OLX:
python scrapers/olx/bmw_alpina.py
python scrapers/run_olx.py all
```

---

## Project Layout

```
app.py                 # entry point (Vercel + `python app.py`)
db.py                  # SQLite / D1 backends, schema + migrations
validation.py          # VIN + plate validation (CORE: shared by scrapers and app)
webapp/
  __init__.py          # create_app(): config, Jinja filters, blueprint registration
  helpers.py           # parsing helpers, paths, env flags
  regions.py           # city → voivodeship lookup tables
  services/            # listing approval & spec inference, photo storage
  blueprints/          # routes: auth, dashboard, vehicles, review, plates, cepik, api
scrapers/              # otomoto / OLX scrapers (run on GitHub Actions)
scripts/               # CV plate detection, CEPiK fetch, maintenance tools
```

Tests: `python -m unittest tests.test_validation tests.test_system tests.test_fixes` (CI runs these plus `ruff check --select F .`).

---

## License
MIT
