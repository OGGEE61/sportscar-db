from curl_cffi import requests
r = requests.get("https://www.otomoto.pl/osobowe/oferta/audi-rs3-ID6G2Ybo.html", impersonate="chrome")
with open("test.html", "w") as f:
    f.write(r.text)
