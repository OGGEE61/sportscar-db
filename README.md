# SportsCar DB

A lightweight, self-hosted web application for tracking the **sportscar secondary market** — price history, listing observations, VIN verification, and condition reports, all backed by a single SQLite file.

Built for enthusiasts and researchers who want to systematically follow high-end car listings across Polish marketplaces (OtoMoto, OLX) and understand how prices move over time.

---

## What it does

Most car-tracking tools show you a snapshot: current listings, current price. SportsCar DB is **observation-based** — every time a scraper or user records a listing, a new row is created with a timestamp. This means you can:

- Watch a single ad's **price drop over weeks** before it sells
- See **when an ad disappeared** (likely sold)
- Compare what the same car sold for vs. what it was originally listed at
- Track market-wide trends: average prices, active inventory, source distribution

The **VIN is the permanent identity key**. All listing observations, condition reports, and tags attach to a VIN — not to an ad. If a car appears on OtoMoto and OLX simultaneously, both observations live under the same VIN.

---

## Features

- **Dashboard** — stat cards + 4 live charts (make distribution, price ranges, weekly observation volume, source breakdown)
- **Vehicle list** — searchable, filterable, sortable table of all tracked VINs
- **Vehicle detail** — full history per VIN: grouped ad timelines, price chart, condition reports, tags, VIN correction log
- **Manual entry** — add a vehicle and its first listing observation via web form
- **Placeholder VINs** — listings with no VIN get a deterministic `UNVERIFIED-SOURCE-ID` key; resolve to a real VIN later when discovered
- **VIN correction workflow** — re-keys all related data from a placeholder/wrong VIN to the correct one, with full audit trail
- **REST API** — `POST /api/ingest` for scrapers; `GET /api/vehicles` and `/api/stats` for downstream consumers
- **Condition reports** — accident-free status, service history, condition score per inspection event

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, Flask |
| Database | SQLite (single file, WAL mode) |
| Frontend | Bootstrap 5, Chart.js |
| Deployment | Any machine with Python — no Docker required |

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/your-username/sportscar-db.git
cd sportscar-db

# 2. Create virtual environment
python -m venv .venv

# 3. Activate
source .venv/Scripts/activate   # Windows (Git Bash / PowerShell)
source .venv/bin/activate        # macOS / Linux

# 4. Install dependencies
pip install flask

# 5. (Optional) Seed demo data — 6 cars, realistic price histories
python seed.py

# 6. Run
python app.py
```

Open **http://127.0.0.1:5555** in your browser.

### Save your dependencies

```bash
pip freeze > requirements.txt
```

Next time:

```bash
pip install -r requirements.txt
python app.py
```

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
  created_at, updated_at

listing_observations             — one row per scrape / sighting
  id (PK)
  vin (FK → vehicles)
  source             — 'otomoto' | 'olx' | 'manual' | ...
  source_listing_id  — the ad's ID on the source platform
  source_url
  title, price_pln, price_eur
  mileage_km
  location_city, location_region
  seller_type, seller_name
  first_seen_at, observed_at, last_seen_at, removed_at
  source_method, notes

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
```

**Key design rule:** `listing_observations` is append-only. The same ad observed 4 weeks in a row = 4 rows. This is what powers price-over-time charts and sold/removed detection.

---

## REST API

### `POST /api/ingest`

Used by scrapers. Creates or updates a vehicle and appends one observation row.

```json
{
  "vin": "WP0ZZZ99ZTS392124",
  "make": "Porsche",
  "model": "911",
  "variant": "Carrera 4S",
  "year": 2020,
  "power_hp": 450,
  "source": "otomoto",
  "source_listing_id": "OT-48291001",
  "source_url": "https://otomoto.pl/48291001",
  "price_pln": 375000,
  "mileage_km": 22000,
  "location_city": "Warszawa",
  "seller_type": "private"
}
```

If `vin` is missing or invalid and a `source_listing_id` is present, a placeholder VIN is generated automatically.

**Response:**

```json
{
  "status": "ok",
  "vin": "WP0ZZZ99ZTS392124",
  "observation_id": 42,
  "is_placeholder": false
}
```

### `GET /api/stats`

Returns aggregate counts and schema version. Useful for monitoring scraper health.

### `GET /api/vehicles`

Returns all vehicles as a JSON array.

---

## Project structure

```
sportscar-db/
├── app.py              # Flask routes
├── db.py               # Schema, init_db(), resolve_placeholder()
├── seed.py             # Demo data (6 cars, realistic observations)
├── sportscar_market.db # SQLite database (auto-created on first run)
├── templates/
│   ├── base.html       # Navbar, Bootstrap/Chart.js CDN
│   ├── dashboard.html  # Stats + 4 charts
│   ├── vehicles.html   # Filterable vehicle list
│   ├── vehicle.html    # VIN detail, price chart, observations
│   ├── add_vehicle.html# Manual entry form
│   └── corrections.html# VIN correction audit log
└── requirements.txt
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

- [ ] OtoMoto scraper
- [ ] OLX scraper
- [ ] Pagination on vehicle list
- [ ] Price alert notifications
- [ ] CSV / JSON export
- [ ] Multi-currency support (EUR ↔ PLN)
- [ ] Public read-only sharing links per VIN

---

## License

MIT
