import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

async def test():
    url = "https://www.otomoto.pl/osobowe/oferta/audi-rs3-ID6G2Ybo.html"
    async with AsyncSession(impersonate="chrome") as session:
        r = await session.get(url, timeout=10)
        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        nd = json.loads(nd_m.group(1))
        advert = nd.get("props", {}).get("pageProps", {}).get("advert", {})
        
        with open("advert_dump.json", "w") as f:
            json.dump(advert, f, indent=2)
        print("Dumped to advert_dump.json")

asyncio.run(test())
