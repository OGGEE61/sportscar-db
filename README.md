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

### How a listing becomes data

1. **Scrape** — a scraper reads an ad from otomoto, OLX or autoplac.
2. **Extract the VIN** — from the ad's structured data, the otomoto encrypted VIN reveal, or the description text.
3. **Validate it** — `validation.is_plausible_vin` (one implementation shared by scrapers and the app) rejects masked, fake or foreign-manufacturer VINs.
4. **Link it** —
   - **Known VIN** → the listing is attached to that car automatically and a price observation is recorded.
   - **New VIN** → the listing goes to the **Review Queue** for manual approval.
   - **No valid VIN** → the car gets a placeholder (`UNVERIFIED-…`) that is re-keyed to the real VIN once found, keeping all its history.
5. **Re-observe** — every later sighting of the same ad adds a new timestamped observation, so price changes are tracked per listing.

The same VIN appearing in a **new ad** (resale, new owner, relist) is expected: it becomes a new listing under the same car, so you see the car's full history across owners.

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

### Configuration

Copy `.env.example` to `.env` for local development. On Vercel, set these under **Settings → Environment Variables**; the scrapers on GitHub Actions read `API_TOKEN` and `API_BASE` from repository secrets.

| Variable | Needed for | Notes |
|---|---|---|
| `SECRET_KEY` | Vercel (required with `ADMIN_PASSWORD`) | Signs login sessions. The app **refuses to start** in production without it. |
| `ADMIN_PASSWORD` | Vercel | Password for the web UI. Unset = no login (local dev only). |
| `API_TOKEN` | Vercel + GitHub secret | Bearer token scrapers send to `/api/ingest*`, `/api/mark_removed`, `/api/log_run`. Missing in production = those endpoints return 503. |
| `DB_BACKEND` | Vercel | `d1` in production, `sqlite` locally. |
| `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_API_TOKEN` | Vercel | Cloudflare D1 access. |
| `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Vercel | Photo storage. Unset = photos saved to `static/photos/`. |
| `BASE_URL` | Scrapers | Where scrapers post data (GitHub secret `API_BASE`). Defaults to `http://127.0.0.1:5555`. |
| `OLLAMA_URL`, `BIELIK_MODEL` | `enrich_with_bielik.py` | Local LLM enrichment (optional). |

**Access control:** every page and every `/api/*` route needs a login, except the four scraper endpoints above, which use `API_TOKEN` instead.

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

# autoplac (VIN and plate are public there, no cookies):
python scrapers/autoplac/bmw_x3_m40i_g01.py
python scrapers/run_autoplac.py bmw       # also: mercedes, audi, porsche, all

# Check that every autoplac scraper fetches the right model (live, posts nothing):
python scripts/verify_autoplac.py
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
scrapers/              # otomoto / OLX / autoplac scrapers (run on GitHub Actions)
scripts/               # CV plate detection, CEPiK fetch, maintenance tools
```

---

## Development

```bash
python -m unittest tests.test_validation tests.test_system tests.test_fixes   # offline tests
ruff check --select F .                                                        # lint
python db.py                                                                   # create / migrate the local SQLite DB
```

CI (`.github/workflows/ci.yml`) runs the lint and the offline tests on every push and pull request. The other files in `tests/` call otomoto live and are not run in CI.

`tests/test_validation.py` pins which VINs and plates are accepted. If it fails, a change has altered which listings get linked to known cars — make that change deliberately, never as a side effect.

---

## License
MIT
