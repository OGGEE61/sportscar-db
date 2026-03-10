# SportsCar DB

A lightweight, self-hosted web application for tracking the **performance car secondary market** — price history, listing observations, VIN verification, and condition reports, all backed by a single SQLite file.

Built for enthusiasts and researchers who want to systematically follow high-end car listings across Polish marketplaces (OLX, OtoMoto) and understand how prices move over time.

---

## What it does

Most car-tracking tools show you a snapshot: current listings, current price. SportsCar DB is **observation-based** — every time a scraper or user records a listing, a new row is created with a timestamp. This means you can:

- Watch a single ad's **price drop over weeks** before it sells
- See **when an ad disappeared** (likely sold)
- Compare what the same car sold for vs. what it was originally listed at
- Track market-wide trends: average prices, active inventory, source distribution

The **VIN is the permanent identity key**. All listing observations, condition reports, and tags attach to a VIN — not to an ad. If a car appears on OtoMoto and OLX simultaneously, both observations live under the same VIN.


<img width="1408" height="768" alt="Gemini_Generated_Image_wtgp3bwtgp3bwtgp" src="https://github.com/user-attachments/assets/15602997-05dc-43a8-91f8-71bec77e35fb" />



---

## Features

- **Dashboard** — stat cards + 4 live charts (make distribution, price ranges, weekly observation volume, source breakdown)
- **Vehicle list** — searchable, filterable, sortable table of all tracked VINs
- **Vehicle detail** — full history per VIN: grouped ad timelines, price chart, condition reports, tags, VIN correction log
- **Manual entry** — add a vehicle and its first listing observation via web form
- **OLX scraper** — automated scraping of 40+ model targets across BMW M, Mercedes-AMG, Audi RS/S, Porsche, and VW performance variants
- **Review queue** — scraped listings land in a staging area (`pending_listings`) for human review before being committed to the database
- **Placeholder VINs** — listings with no VIN get a deterministic `UNVERIFIED-SOURCE-ID` key; resolve to a real VIN later when discovered
- **VIN correction workflow** — re-keys all related data from a placeholder/wrong VIN to the correct one, with full audit trail
- **REST API** — `POST /api/ingest` for direct scraper ingest; `POST /api/ingest_pending` for review-gated ingest; `GET /api/vehicles` and `/api/stats`
- **Condition reports** — accident-free status, service history, condition score per inspection event

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, Flask |
| Database | SQLite (single file, WAL mode) |
| Frontend | Bootstrap 5, Chart.js |
| Scraping | requests + BeautifulSoup4 |
| Deployment | Any machine with Python — no Docker required |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/OGGEE61/sportscar-db.git
cd sportscar-db

# 2. Create virtual environment
python -m venv .venv

# 3. Activate
source .venv/Scripts/activate   # Windows (Git Bash)
.venv\Scripts\activate          # Windows (PowerShell)
source .venv/bin/activate       # macOS / Linux

# 4. Install dependencies
pip install -r requirements.txt

# 5. (Optional) Seed demo data — 6 cars with realistic price histories
python seed.py

# 6. Run
python app.py
```

Open **http://127.0.0.1:5555** in your browser.

---

## Running the OLX scraper

The scraper requires the Flask app to be running (it POSTs to `/api/ingest_pending`).

```bash
# In one terminal — start the web app
python app.py

# In another terminal — run the scraper
python scrapers/olx.py                  # all 40+ targets
python scrapers/olx.py bmw m3           # single target
python scrapers/olx.py --dry-run        # preview without posting
```

Scraped listings appear in **Review Queue** (`/review`). Review each listing, correct any fields, then approve or reject. Approved listings are committed to `vehicles` + `listing_observations`.

### Scraper targets (as of March 2026)

| Brand | Models |
|---|---|
| BMW | M2, M3, M4, M5, M6, M8, X3M, X4M, X5M, X6M |
| Mercedes-AMG | A45, CLA45, C63, E63, S63, SLS AMG, AMG GT, GLE63, GLS63, GL63 |
| Audi | RS3, RS4, RS5, RS6, RS7, R8, TT RS, S3–S7, SQ5, SQ7, RS Q3, RS Q3 Sportback, RS Q8 |
| Porsche | 911, Boxster, Cayman, Panamera, Cayenne, Macan |
| VW | Golf R/GTI R32, Scirocco R |

---

## Data model

```
vehicles
  vin (PK)           — 17-char real VIN or UNVERIFIED-SOURCE-ID placeholder
  make, model, variant
  year, body_type
  engine_cc, engine_cyl, power_hp
  drivetrain, transmission
  color_ext, color_int
  vin_status         — 'placeholder' | 'unverified' | 'verified'
  source_method      — how the record was created
  created_at, updated_at   (updated_at maintained by DB trigger)

listing_observations             — one row per scrape / sighting
  id (PK)
  vin (FK → vehicles, CASCADE DELETE)
  source             — 'otomoto' | 'olx' | 'manual' | ...
  source_listing_id  — the ad's ID on the source platform (groups observations of same ad)
  source_url
  title, price_pln, price_eur
  mileage_km
  location_city, location_region
  seller_type, seller_name
  first_seen_at, observed_at, last_seen_at, removed_at
  source_method, notes

pending_listings                 — scraper staging area (review-before-commit)
  id (PK)
  source, source_listing_id, source_url
  scraped_at
  status             — 'pending' | 'approved' | 'rejected'
  raw_title, raw_description
  photos             — JSON array of image URLs
  make, model, variant, year, body_type
  engine_cc, power_hp, fuel_type, drivetrain, transmission, color_ext, doors
  price_pln, price_eur, mileage_km
  location_city, location_region, seller_type, seller_name
  vin, vin_confidence  — 'found_in_schema' | 'found_in_description' | 'none'
  is_listing_active  — 1 if still live when scraped, 0 if removed
  review_notes, reviewed_at
  UNIQUE(source, source_listing_id)   — deduplication key

condition_reports
  vin (FK)
  report_date, mileage_km
  accident_free (0/1/null)
  service_history, condition_score
  inspection_by

tags
  vin (FK)
  tag                — free-text label, e.g. 'collector', 'low-mileage'
  source_method

vin_correction_log
  old_vin → new_vin  — full audit trail of every VIN re-key
  reason, corrected_by, created_at

schema_migrations
  version, name, applied_at   — tracks applied schema changes
```

**Key design rule:** `listing_observations` is append-only. The same ad observed 4 weeks in a row = 4 rows. This is what powers price-over-time charts and sold/removed detection.

---

## Review workflow (scraper → database)

```
OLX search pages
      ↓  (scrape listing cards, follow URLs)
listing detail pages
      ↓  (JSON-LD + HTML param extraction)
POST /api/ingest_pending
      ↓  (INSERT OR IGNORE — deduplication by source+id)
pending_listings  (status = 'pending')
      ↓
/review queue UI — human reviews, edits fields, approves or rejects
      ↓ approve                              ↓ reject
vehicles (INSERT or UPDATE)        pending_listings.status = 'rejected'
listing_observations (INSERT)
pending_listings.status = 'approved'
```

### VIN detection priority
1. `vehicleIdentificationNumber` from JSON-LD schema → `vin_confidence = 'found_in_schema'` (green)
2. Regex scan of description text → `vin_confidence = 'found_in_description'` (yellow, verify manually)
3. No VIN found → approve generates an `UNVERIFIED-OLX-{id}` placeholder

---

## REST API

### `POST /api/ingest_pending`

Used by the OLX scraper. Adds a listing to the review queue. Duplicate listings (same `source` + `source_listing_id`) are silently ignored.

```json
{
  "source": "olx",
  "source_listing_id": "IDxxxxxxx",
  "source_url": "https://www.olx.pl/d/oferta/...",
  "raw_title": "BMW M3 Competition ...",
  "make": "BMW", "model": "M3", "year": 2019,
  "power_hp": 510, "mileage_km": 28000,
  "price_pln": 295000,
  "location_city": "Kraków",
  "photos": ["https://...jpg"],
  "vin": null, "vin_confidence": "none"
}
```

### `POST /api/ingest`

Direct ingest — bypasses the review queue. Creates/updates a vehicle and appends one observation immediately. Use for trusted sources or manual scripting.

```json
{
  "vin": "WP0ZZZ99ZTS392124",
  "make": "Porsche", "model": "911", "year": 2020,
  "source": "otomoto",
  "source_listing_id": "OT-48291001",
  "price_pln": 375000,
  "mileage_km": 22000
}
```

**Response:** `{"status": "ok", "vin": "...", "observation_id": 42, "is_placeholder": false}`

### `GET /api/stats`

Aggregate counts and schema version. Useful for monitoring.

### `GET /api/vehicles`

All vehicles as a JSON array.

---

## Project structure

```
sportscar-db/
├── app.py                  # Flask routes — all UI pages + REST API
├── db.py                   # Schema definition, migrations, init_db(), resolve_placeholder()
├── seed.py                 # Demo data — 6 cars with realistic price histories
├── requirements.txt        # Python dependencies
├── scrapers/
│   ├── __init__.py
│   └── olx.py              # OLX.pl scraper — search + detail extraction + ingest
└── templates/
    ├── base.html            # Navbar, Bootstrap 5 + Chart.js CDN
    ├── dashboard.html       # Stat cards + 4 charts
    ├── vehicles.html        # Filterable/sortable vehicle table
    ├── vehicle.html         # VIN detail, price chart, observation timeline
    ├── add_vehicle.html     # Manual entry form
    ├── review.html          # Pending/approved/rejected listing cards
    ├── review_detail.html   # Single listing review form (approve / reject)
    └── corrections.html     # VIN correction audit log
```

---

## Placeholder VIN workflow

Some listings on OLX don't show the VIN. The scraper still ingests the data using a deterministic placeholder:

```
UNVERIFIED-OLX-99887766
```

All observations attach to this key. When the real VIN is later discovered (e.g., from a subsequent listing, or by contacting the seller), you resolve it via the web UI on the vehicle detail page. The system:

1. Copies the vehicle record to the real VIN
2. Re-keys all observations, condition reports, and tags
3. Deletes the placeholder record
4. Writes a row to `vin_correction_log`

No data is lost.

---

## Roadmap

- [x] OLX scraper 1.0
- [ ] OtoMoto scraper
- [ ] Pagination on vehicle list (currently unbounded)
- [ ] Price alert notifications
- [ ] CSV / JSON bulk export
- [ ] Multi-currency support (EUR ↔ PLN live rate)
- [ ] Public read-only sharing links per VIN
- [ ] Scraper scheduling (cron / Windows Task Scheduler)

---

## License

MIT
