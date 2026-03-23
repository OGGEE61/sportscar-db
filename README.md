# SportsCar DB

A lightweight, self-hosted web application for tracking the **performance car secondary market** — price history, listing observations, VIN-based identity, and condition reports, all backed by a single SQLite file.

Built for enthusiasts and researchers who want to systematically follow high-end car listings on Polish marketplaces (otomoto.pl) and understand how prices move over time.


---

## What it does

<img width="1408" height="768" alt="sportscar_diagram" src="https://github.com/user-attachments/assets/eda8dc3d-bf05-4894-8e0d-aaf3686f4d94" />


Most car-tracking tools show a snapshot: current listings, current price. SportsCar DB is **observation-based** — every time a scraper records a listing, a new timestamped row is created. This means you can:

- Watch a single ad's **price drop over weeks** before it sells
- See **when an ad disappeared** (likely sold)
- Compare what the same car sold for vs. what it was originally listed at
- Track market-wide trends: average prices, active inventory, source distribution

The **VIN is the permanent identity key**. All listing observations, condition reports, and tags attach to a VIN — not to an ad ID. If the same car is listed twice at different prices, both observations live under the same VIN.

---

## Features

- **Dashboard** — stat cards + 4 live charts (make distribution, price ranges, weekly volume, source breakdown)
- **Vehicle list** — searchable, filterable, sortable table of all tracked VINs
- **Vehicle detail** — full history per VIN: grouped ad timelines, price chart, condition reports, tags, VIN correction log, photo
- **VIN decryption** — otomoto encrypts VINs client-side using AES-256-GCM; the scraper decrypts them locally using the listing's numeric ID as key material (no login required)
- **Photo persistence** — first photo is downloaded and compressed (Pillow, max 800px, JPEG q75) at scrape time; survives listing expiry
- **Review queue** — scraped listings land in a staging area for human review; approve → goes straight to the next pending listing
- **Tag management** — add/remove free-text tags on any vehicle detail page
- **Vehicle deletion** — double-confirm (type VIN + JS dialog); cascades all related data
- **Placeholder VINs** — listings with no VIN get a deterministic `UNVERIFIED-SOURCE-ID` key; resolve to a real VIN later via the web UI
- **VIN correction workflow** — re-keys all related data from placeholder/wrong VIN to correct one, with full audit trail
- **Manual entry** — add a vehicle and first observation via web form
- **REST API** — `POST /api/ingest_pending`, `POST /api/ingest`, `GET /api/vehicles`, `GET /api/stats`

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, Flask |
| Database | SQLite |
| Frontend | Bootstrap 5, Chart.js |
| HTTP client | curl_cffi (Chrome TLS fingerprint — bypasses DataDome bot detection) |
| VIN decryption | Python `cryptography` library — AES-256-GCM |
| Photo processing | Pillow |

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

# 5. Run
python app.py
```

Open **http://127.0.0.1:5555** in your browser.

---

## Running the scrapers

Each scraper is a self-contained Python file. The Flask app must be running first (scrapers POST results to `/api/ingest_pending`).

```bash
# Terminal 1 — web app
python app.py

# Terminal 2 — run any scraper
python scrapers/audi_rs3_8v.py
python scrapers/audi_rs5.py
python scrapers/bmw_m4_f82.py
python scrapers/mercedes_c63_w204.py
python scrapers/mercedes_e55_w211.py
python scrapers/porsche_997.py
```

### Cookie authentication (optional)

otomoto requires a logged-in session to display VINs in the browser. The scraper decrypts them locally without needing a session, but having cookies loaded also lets the session check confirm your identity.

1. Log into otomoto.pl in Chrome
2. Install the **Cookie-Editor** browser extension
3. Click **Export → Export as JSON** → save as `scrapers/otomoto_cookies.json`

The scraper loads this file automatically on startup.

### Scraper targets

| Scraper | Model | Years | Defaults |
|---|---|---|---|
| `audi_rs3_8v.py` | Audi RS3 8V | 2017–2020 | 400 HP, petrol, AWD, auto, 4-door |
| `audi_rs4_b8.py` | Audi RS4 B8/B8.5 | 2012–2015 | 450 HP, petrol, AWD, auto |
| `audi_rs5.py` | Audi RS5 B8/B9 | up to 2020 | 450 HP, petrol, AWD, auto |
| `bmw_m4_f82.py` | BMW M4 F82 + M3 F80 | 2014–2020 | 431 HP, petrol, RWD, auto |
| `mercedes_c63_w204.py` | Mercedes C63 AMG W204 | 2008–2015 | 457 HP, petrol, RWD, auto |
| `mercedes_e55_w211.py` | Mercedes E55 AMG W211 | 2003–2006 | 476 HP, petrol, RWD, auto |
| `porsche_997.py` | Porsche 911 997 | 2004–2012 | petrol, RWD |

---

## How it works — end to end

```
otomoto.pl search pages
        │
        │  curl_cffi (Chrome TLS fingerprint — bypasses DataDome)
        ▼
  List page: urqlState GraphQL cache in __NEXT_DATA__
  → listing cards (title, price, location, thumbnail URL)
        │
        │  1 request per listing
        ▼
  Detail page: __NEXT_DATA__ → advert object
  ┌─────────────────────────────────────────────┐
  │  params dict  → year, mileage, power, colour │
  │  AES-256-GCM decrypt(params["vin"],          │
  │      key=PBKDF2(SHA256(advert.id)[:16].hex)) │
  │  → real 17-char VIN (no login required)      │
  │  photo[0].id  → CDN URL                      │
  └─────────────────────────────────────────────┘
        │
        │  Pillow: download + compress photo
        │  (max 800px wide, JPEG q75 → static/photos/)
        ▼
  POST /api/ingest_pending
        │
        ▼
  pending_listings  (status = 'pending')
        │
        ▼
  /review queue — card grid with local photo, price, VIN badge
  ┌─────────────────────────────────────────────┐
  │  Approve → next pending listing immediately  │
  │  Reject  → next pending listing immediately  │
  │  Bulk reject, Reject all                     │
  └─────────────────────────────────────────────┘
        │ approve
        ▼
  vehicles (INSERT OR UPDATE)          ← VIN is the primary key
  listing_observations (INSERT)        ← one row per sighting
  pending_listings.status = 'approved'
  vehicles.photo = local_photo (if none set yet)
```

### VIN detection tiers

| Priority | Method | Badge |
|---|---|---|
| 1 | AES-256-GCM decrypt of `params["vin"]` using `advert.id` | green **VIN** |
| 2 | Regex scan of seller's description text | yellow **VIN?** |
| 3 | No VIN → `UNVERIFIED-SOURCE-ID` placeholder | — |

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
  photo              — path to locally cached compressed photo
  vin_status         — 'placeholder' | 'unverified' | 'verified'
  source_method
  created_at, updated_at

listing_observations             — append-only; one row per scrape/sighting
  vin (FK → vehicles)
  source             — 'otomoto' | 'olx' | 'manual'
  source_listing_id  — groups multiple observations of the same ad
  source_url, title
  price_pln, mileage_km
  location_city, seller_type, seller_name
  first_seen_at, observed_at, removed_at
  source_method, notes

pending_listings                 — scraper staging area
  source, source_listing_id, source_url
  scraped_at, status             — 'pending' | 'approved' | 'rejected'
  raw_title, raw_description
  photos (JSON), local_photo     — remote URLs + locally cached path
  make, model, variant, year
  power_hp, fuel_type, drivetrain, transmission, color_ext
  price_pln, mileage_km, location_city
  vin, vin_confidence            — 'found_in_schema' | 'found_in_description' | 'none'
  UNIQUE(source, source_listing_id)

condition_reports
  vin (FK), report_date, mileage_km
  accident_free (0/1/null), service_history
  condition_score (1–10), inspection_by

tags
  vin (FK), tag, source_method   — free-text labels; add/remove in vehicle detail UI

vin_corrections
  old_vin → new_vin, reason, corrected_by, created_at

schema_migrations
  version, name, applied_at
```

**Key design rule:** `listing_observations` is append-only. The same ad observed 4 weeks in a row = 4 rows. This powers price-over-time charts and sold/removed detection.

---

## REST API

### `POST /api/ingest_pending`
Adds a listing to the review queue. Duplicates (same `source` + `source_listing_id`) are silently ignored.

### `POST /api/ingest`
Direct ingest — bypasses review queue. Creates/updates a vehicle and appends one observation immediately.

### `GET /api/vehicles`
All vehicles as a JSON array.

### `GET /api/stats`
Aggregate counts and schema version.

---

## Project structure

```
sportscar-db/
├── app.py                      # Flask routes — UI pages + REST API
├── db.py                       # Schema, get_db(), migrations
├── requirements.txt
├── scrapers/
│   ├── base_scraper.py         # curl_cffi engine, VIN decryption, photo download
│   ├── audi_rs3_8v.py
│   ├── audi_rs4_b8.py
│   ├── audi_rs5.py
│   ├── bmw_m4_f82.py           # runs M4 F82 + M3 F80
│   ├── mercedes_c63_w204.py
│   ├── mercedes_e55_w211.py
│   └── porsche_997.py
├── static/
│   └── photos/                 # locally cached + compressed car photos (gitignored)
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── vehicles.html
    ├── vehicle.html             # detail: price chart, tags, delete, condition reports
    ├── add_vehicle.html
    ├── review.html              # card grid: pending / approved / rejected
    ├── review_detail.html       # single listing approve / reject form
    └── corrections.html
```

---

## Placeholder VIN workflow

Listings without a VIN get a deterministic placeholder: `UNVERIFIED-OTOMOTO-99887766`

All observations attach to this key. When the real VIN is discovered, resolve it via the web UI on the vehicle detail page. The system:

1. Copies the vehicle record to the real VIN
2. Re-keys all observations, condition reports, and tags
3. Deletes the placeholder
4. Writes a row to `vin_corrections`

No data is lost.

---

## Roadmap

- [x] otomoto.pl scraper with DataDome bypass (curl_cffi Chrome TLS fingerprint)
- [x] Client-side AES-256-GCM VIN decryption (no login required)
- [x] Cookie-based session authentication (Cognito JWT refresh)
- [x] Local photo persistence (download + compress at ingest time)
- [x] Known-model spec defaults (HP, drivetrain, fuel auto-filled per scraper)
- [x] Review queue with fast approve→next flow
- [x] Tag add/remove on vehicle detail page
- [x] Vehicle deletion with double-confirm
- [ ] Scheduled scraping (cron / Windows Task Scheduler)
- [ ] Mileage history chart per vehicle
- [ ] Price alert notifications
- [ ] CSV / JSON bulk export
- [ ] Pagination on vehicle list
- [ ] Multi-currency support (EUR ↔ PLN live rate)

---

## License

MIT
