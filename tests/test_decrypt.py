import asyncio
import json
import re
from curl_cffi.requests import AsyncSession
from scrapers.base_scraper import _decrypt_vin

async def test():
    url = "https://www.otomoto.pl/osobowe/oferta/audi-rs3-ID6G2Ybo.html"
    async with AsyncSession(impersonate="chrome") as session:
        r = await session.get(url, timeout=10)
        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        nd = json.loads(nd_m.group(1))
        pageProps = nd.get("props", {}).get("pageProps", {})
        advert = pageProps["advert"]
        advert_id = str(advert.get("id"))
        params = {d["key"]: d["value"] for d in advert.get("details", []) if "key" in d and "value" in d}
        print("Params keys:", list(params.keys()))
        enc_reg = params.get("registration")
        print("Encrypted registration:", enc_reg)
        if enc_reg:
            print("Decrypted registration:", _decrypt_vin(enc_reg, advert_id))

asyncio.run(test())
