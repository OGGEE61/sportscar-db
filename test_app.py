from app import app
with app.test_client() as c:
    r = c.get('/')
    print("Dashboard map_data:", [line for line in r.text.split('\n') if 'map_data' in line or 'mapData' in line])
    r2 = c.get('/model/1')
    print("Model 1 map_data:", [line for line in r2.text.split('\n') if 'map_data' in line or 'mapData' in line])
