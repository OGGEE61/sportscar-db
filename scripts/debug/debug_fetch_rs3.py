import asyncio
import json
import re
from curl_cffi.requests import AsyncSession

async def test():
    urls = [
        "https://www.otomoto.pl/osobowe/oferta/audi-rs3-ID6G2Ybo.html",
        "https://www.otomoto.pl/osobowe/oferta/audi-rs3-ID6IdOaJ.html"
    ]
    async with AsyncSession(impersonate="chrome") as session:
        for url in urls:
            r = await session.get(url, timeout=10)
            if r.status_code == 404:
                print(f"{url} is 404 Not Found")
                continue
            nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
            if not nd_m:
                print(f"No NEXT_DATA for {url}")
                continue
            nd = json.loads(nd_m.group(1))
            pageProps = nd.get("props", {}).get("pageProps", {})
            if "advert" in pageProps:
                print(f"{url} HAS advert!")
            else:
                print(f"{url} NO advert in pageProps. Keys: {pageProps.keys()}")

asyncio.run(test())
