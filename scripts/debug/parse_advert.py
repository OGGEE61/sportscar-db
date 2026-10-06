import json

with open("advert_dump.json") as f:
    advert = json.load(f)

for detail in advert.get("details", []):
    print(f"Key: {detail.get('key')} -> Value length: {len(str(detail.get('value')))}")
