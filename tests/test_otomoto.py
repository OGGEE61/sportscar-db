from curl_cffi import requests
r = requests.get("https://www.otomoto.pl/osobowe/audi/rs3", impersonate="chrome")
print("Status:", r.status_code)
print("NEXT_DATA in text:", "__NEXT_DATA__" in r.text)
print("Length:", len(r.text))
