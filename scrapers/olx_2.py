import requests
from bs4 import BeautifulSoup

def scrape_bmw_m3_olx(pages=1):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for page in range(1, pages + 1):
        url = f"https://www.olx.pl/motoryzacja/samochody/bmw/?search%5Bfilter_float_price%3Afrom%5D=&search%5Bfilter_float_price%3Ato%5D=&search%5Bfilter_enum_model%5D%5B0%5D=m3&page={page}"
        
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        listings = soup.select("[data-cy='l-card']")

        for item in listings:
            title_el = item.select_one("h6")
            price_el = item.select_one("[data-testid='ad-price']")

            title = title_el.text.strip() if title_el else "N/A"
            price = price_el.text.strip() if price_el else "N/A"

            results.append({"title": title, "price": price})
            print(f"{title} — {price}")

    return results

if __name__ == "__main__":
    scrape_bmw_m3_olx(pages=2)