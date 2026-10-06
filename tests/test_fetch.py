import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

async def test():
    url = "https://www.otomoto.pl/osobowe/oferta/audi-rs3-ID6I9G1N.html"
    async with AsyncSession(impersonate="chrome") as session:
        response = await session.get(url, timeout=10)
        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.S)
        if not nd_m:
            print("No NEXT DATA")
            return
        nd = json.loads(nd_m.group(1))
        pageProps = nd.get("props", {}).get("pageProps", {})
        print("pageProps keys:", pageProps.keys())
        if "advert" in pageProps:
            advert = pageProps["advert"]
            print("Advert ID:", advert.get("id"))
            params = {d["key"]: d["value"] for d in advert.get("details", []) if "key" in d and "value" in d}
            print("registration:", params.get("registration"))
            print("date_registration:", params.get("date_registration"))
        else:
            print("NO ADVERT IN PAGEPROPS")

asyncio.run(test())
