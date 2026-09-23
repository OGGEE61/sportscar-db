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
python scrapers/audi_rs3_8v.py
```

---

## License
MIT
