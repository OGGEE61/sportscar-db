import re
import requests
from bs4 import BeautifulSoup

API_URL = "http://127.0.0.1:5555/api/ingest_pending"


def parse_price(text):
    """Extract numeric PLN value from strings like '539 000 zł'."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def scrape_bmw_m3_olx(pages=1, post_to_api=True):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for page in range(1, pages + 1):
        url = (
            f"https://www.olx.pl/motoryzacja/samochody/bmw/"
            f"?search%5Bfilter_float_price%3Afrom%5D=&search%5Bfilter_float_price%3Ato%5D="
            f"&search%5Bfilter_enum_model%5D%5B0%5D=m3&page={page}"
        )

        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        for item in soup.select("[data-cy='l-card']"):
            title_el = item.select_one("h4")
            price_el = item.select_one("[data-testid='ad-price']")
            link_el  = item.select_one("a[href]")
            paragraphs = item.select("p")

            title     = title_el.text.strip() if title_el else "N/A"
            price_raw = price_el.text.strip()  if price_el else ""
            price_pln = parse_price(price_raw)
            source_url      = link_el["href"] if link_el else None
            source_listing_id = item.get("id")  # numeric id on the card div

            # Second <p> typically holds "City, District - date"
            location_city = None
            if len(paragraphs) >= 2:
                loc_text = paragraphs[1].text.strip()
                location_city = loc_text.split(" - ")[0].split(",")[0].strip() or None

            # First image in the card
            img_el = item.select_one("img[src]")
            photos = [img_el["src"]] if img_el else []

            payload = {
                "source":             "olx",
                "source_listing_id":  source_listing_id,
                "source_url":         source_url,
                "raw_title":          title,
                "make":               "BMW",
                "model":              "M3",
                "price_pln":          price_pln,
                "location_city":      location_city,
                "photos":             photos,
            }

            results.append(payload)
            print(f"{title} — {price_raw} ({location_city})")

            if post_to_api:
                try:
                    r = requests.post(API_URL, json=payload, timeout=5)
                    print(f"  > API {r.status_code} {r.json()}")
                except Exception as e:
                    print(f"  > API error: {e}")

    return results


if __name__ == "__main__":
    scrape_bmw_m3_olx(pages=2, post_to_api=True)
