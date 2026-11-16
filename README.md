# SportsCar DB

A small web app that follows the **Polish used market for performance cars**. Scrapers read
otomoto.pl, OLX and autoplac.pl several times a day; the app keeps every sighting, so you can see
how a car's price moved, when its ad disappeared, and whether the same car came back later under a
new ad.

Built for one enthusiast's daily use: about 45 models (BMW M, AMG, Audi RS, Porsche, a few
classics), a review queue for new cars, and pages that answer "what is this model worth now?" and
"is this ad a good deal?".

---

## How it works

**Observation-based.** Every time a scraper sees an ad it adds a timestamped row. Nothing is
overwritten, so the price history of each ad and the date it went offline are always there.

**The VIN is the car's identity.** All data hangs on the VIN, not on the ad. The same VIN in a new
ad (resale, relist) is expected: it becomes another listing of the same car.

How a listing becomes data:

1. **Scrape.** A scraper reads an ad from otomoto, OLX or autoplac.
2. **Find the VIN.** From the ad's data, from Otomoto's "Show VIN" (needs a logged-in session, and
   is rate-limited on purpose: see `REVEALS_PER_DAY` in `scrapers/base_scraper.py`), or from the
   description.
3. **Validate.** `validation.is_plausible_vin` (one implementation for scrapers and app) rejects
   masked, fake and wrong-maker VINs. Each model's scraper adds its own rules (engine, power, VIN
   prefix), and nearly new dealer stock is skipped for every model.
4. **Link.**
   - Known VIN: the listing joins that car and a price observation is recorded.
   - New VIN: the listing waits in the **review queue** ("Kolejka") for approval.
   - No valid VIN: the car gets a placeholder that is re-keyed to the real VIN once it is found.
5. **Re-observe.** Later sightings add observations; an ad that leaves the search is marked gone.

---

## Pages

| Page | What it shows |
|---|---|
| **Pulpit** (`/`) | Totals, charts (makes, price ranges, weekly volume, map), newest sightings |
| **Modele** (`/models`) | One model: median and average price, price vs mileage, table of its cars |
| **Auta** (`/vehicles`) | Every car, with filters and sorting |
| **Okazje** (`/deals`) | Newest ads around Poznań, each compared with the median of similar cars |
| **Ulubione** (`/favorites`) | Cars you starred (the star sits next to every VIN) |
| **Kolejka** (`/review`) | New listings to approve or reject |
| **Tablice** (`/plates`) | Registration plates read from photos, to confirm |
| **CEPiK** (`/cepik`) | Reports from the state vehicle register: insurance, inspection, odometer history |
| Car page (`/vehicle/<vin>`) | Everything about one car: ads, price timeline, damage history, tags |

Every list marks a car with the same set of badges: plate, VIN status, origin market, CEPiK
(including rolled-back odometer and stolen), whether an ad is still up, damage, and "W USA" for a
damaged import that has not reached Poland yet. Damaged cars and cars still abroad are left out of
price statistics. A car filed under the wrong model can be hidden from its page ("To nie ten
model") and restored later.

The interface is in Polish. Code, comments, commits and pull requests are in English.

---

## Architecture

| Part | Where | Notes |
|---|---|---|
| Web app and API | **Vercel** (Hobby), Flask, region `fra1` | `vercel.json`; only `master` and `preview` build |
| Database | **Cloudflare D1** (free plan) | SQLite over HTTP; 5 million rows read a day |
| Photos | **Cloudflare R2** | Compressed on upload; pages link to them with presigned URLs |
| Scrapers | **VPS**, Docker + cron | `deploy/scrapers/`; they talk to the app's API with a token, not to the database |

The scrapers moved from GitHub Actions to the VPS because GitHub's runners were being blocked by
the portals. The `Run Scrapers` workflows remain for manual runs.

Two limits shape the code. Read [CLAUDE.md](CLAUDE.md) before changing anything that queries the
database or deploys:

- **D1 reads.** Past 5 million rows a day every read fails until midnight UTC. Each response
  carries `X-D1-Rows-Read`; audits and exploratory SQL run on a local copy
  (`scripts/maintenance/export_d1.py`), never on production.
- **Vercel deployments.** Feature branches are not deployed. Check a change on `preview`, merge to
  `master` for production, then prune old deployments with `scripts/vercel_prune.sh`.

**Migrations** live in `init_db()` in `db.py` and do not run on Vercel. Apply a new one to
production by hand, right before or after the deploy that needs it, or the pages that use it
return errors:

```bash
DB_BACKEND=d1 python -c "from db import init_db; init_db()"
```

---

## Configuration

Copy `.env.example` to `.env` for local development. On Vercel set these under
**Settings → Environment Variables**. The VPS keeps `API_TOKEN` and `BASE_URL` in
`/opt/sportscar-secrets/scrapers.env`.

| Variable | Needed for | Notes |
|---|---|---|
| `SECRET_KEY` | Vercel | Signs login sessions. The app refuses to start in production without it. |
| `ADMIN_PASSWORD` | Vercel | PIN for the web UI (use 8+ digits: there is no lockout). Unset = no login, the app is open to everyone. |
| `API_TOKEN` | Vercel + scrapers | Bearer token for the scraper endpoints. Missing in production = they return 503. |
| `BASE_URL` | Scrapers | Where scrapers send data. Defaults to `http://127.0.0.1:5555`. |
| `DB_BACKEND` | Vercel | `d1` in production, `sqlite` locally. |
| `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, `CF_API_TOKEN` | Vercel | Cloudflare D1 access (token permission: D1 Edit). |
| `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Vercel | Photo storage. Unset = photos go to `static/photos/`. |
| `CF_ANALYTICS_TOKEN` | Local, optional | Cloudflare token with Account Analytics: Read, to see D1 usage per day and per query. |
| `OLLAMA_URL`, `BIELIK_MODEL` | `enrich_with_bielik.py`, optional | Local LLM that summarises ads. |

**Access control.** Every page and `/api/*` route needs a login, except the endpoints the scrapers
call (`TOKEN_API_PATHS` in `webapp/blueprints/auth.py`), which take `API_TOKEN` instead.

---

## Running locally

With plain SQLite, no Cloudflare keys needed:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python db.py          # create or migrate the local database
python app.py         # http://127.0.0.1:5555
```

Run a scraper in a second terminal:

```bash
# Otomoto
python scrapers/otomoto/audi_rs3_8v.py     # one model
python scrapers/run_all.py next_3          # the three models that waited longest
python scrapers/run_all.py w124            # by target name (see run_all.py)

# OLX
python scrapers/run_olx.py next_4

# autoplac (VIN and plate are public there, no cookies needed)
python scrapers/run_autoplac.py bmw        # also: mercedes, audi, porsche, all

# Check that every autoplac scraper fetches the right model (live, saves nothing)
python scripts/verify_autoplac.py
```

Other tools:

```bash
python scripts/fetch_cepik.py --limit 50       # CEPiK reports for cars that lack one
python scripts/detect_plates.py                # read plates from photos (needs requirements-cv.txt)
python scripts/maintenance/export_d1.py        # copy production into local_copy.db for analysis
```

### Adding a model

1. Add `scrapers/otomoto/<model>.py` with a `ScraperConfig` (search URL, year range, validator).
2. Add the OLX and autoplac variants, which reuse the Otomoto config (`dataclasses.replace`).
3. Register all three in `scrapers/run_all.py`, `run_olx.py` and `run_autoplac.py`.
4. Add the model to `webapp/model_catalog.py` so it appears on **Modele**.
5. Add its expected power and engine range to `scripts/verify_autoplac.py`, and a test for its rules.

---

## Project layout

```
app.py                 # entry point (Vercel and `python app.py`)
db.py                  # SQLite / D1 backends, schema and migrations
validation.py          # VIN, plate and dealer-stock rules (shared by scrapers and app)
webapp/
  __init__.py          # create_app(): config, Jinja helpers, blueprints, D1 read counter
  helpers.py           # SQL fragments shared by pages (car badges, visibility), parsing helpers
  model_catalog.py     # the models shown on /models
  regions.py           # city → voivodeship, distance from Poznań
  services/            # listing approval, deals, photos, plates, R2, stored cache
  blueprints/          # routes: auth, dashboard, vehicles, deals, review, plates, cepik, api
templates/             # Jinja templates; _car_flags.html holds the badges every page uses
scrapers/
  base_scraper.py      # the scraping engine: list pages, details, VIN reveal limits, API calls
  otomoto/ olx/ autoplac/   # one file per model and portal
  run_all.py run_olx.py run_autoplac.py   # run a target or the next models in rotation
scripts/               # CEPiK fetch, plate detection, maintenance tools
deploy/scrapers/       # VPS setup: Dockerfile, cron schedule, run and update scripts
tests/                 # offline tests
```

---

## Development

```bash
python -m pytest -q tests     # every test is offline
ruff check --select F .       # lint
```

CI (`.github/workflows/ci.yml`) runs both on every push and pull request.

`tests/test_validation.py` pins which VINs and plates are accepted. If it fails, a change has
altered which listings get linked to known cars: make that change on purpose, never as a side
effect.

---

## License
MIT
