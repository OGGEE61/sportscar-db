from app import app
import re
with app.test_client() as c:
    r = c.get('/')
    print("Dashboard rawData:", re.search(r'const rawData = (\[.*?\]);', r.text, re.S))
