"""Fuel and engine size filters on /vehicles and /models, and where a car's fuel comes from."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_engine_filter.db")

import db
from app import app
from webapp.services.listings import _approve_listing

# vin, model, variant, cc, fuel
CARS = [
    ("WDB4630311X000001", "G 350 d", "G 350 d", 2987, "diesel"),
    ("WDB4630311X000002", "G 320", "G 320", 3199, "petrol"),
    ("WDB4630311X000003", "G 500", "G 500", 4966, "petrol"),
    ("WDB4630311X000004", "G 400 CDI", "G 400 CDI", 3996, "diesel"),
    ("WDB4630311X000005", "G 300", "G 300", None, None),
]


class TestEngineFilter(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        app.config["TESTING"] = True
        self.client = app.test_client()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        os.environ.pop("ADMIN_PASSWORD", None)
        self.addCleanup(patcher.stop)

        conn = db.get_db()
        for vin, model, variant, cc, fuel in CARS:
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, engine_cc, fuel_type, model_id) "
                         "VALUES (?, 'Mercedes-Benz', ?, ?, 2005, ?, ?, 'g_w463')", (vin, model, variant, cc, fuel))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, "
                         "location_city, observed_at) VALUES (?, 'otomoto', ?, 'https://x', 200000, 'Poznań', datetime('now', '-1 days'))",
                         (vin, f"id-{vin}"))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def cars(self, path):
        html = self.client.get(path).get_data(as_text=True)
        return {vin for vin, *_ in CARS if f'href="/vehicle/{vin}"' in html}

    def vins(self, *numbers):
        return {CARS[n - 1][0] for n in numbers}

    def test_fuel_filter_on_both_pages(self):
        for page in ("/vehicles", "/models?model=g_w463"):
            sep = "&" if "?" in page else "?"
            self.assertEqual(self.cars(page), self.vins(1, 2, 3, 4, 5), page)
            self.assertEqual(self.cars(f"{page}{sep}fuel=diesel"), self.vins(1, 4), page)
            self.assertEqual(self.cars(f"{page}{sep}fuel=petrol"), self.vins(2, 3), page)
            self.assertEqual(self.cars(f"{page}{sep}fuel=steam"), self.vins(1, 2, 3, 4, 5), page)   # unknown: ignored

    def test_engine_size_is_compared_in_hundreds_of_cm3(self):
        for page in ("/vehicles", "/models?model=g_w463"):
            sep = "&" if "?" in page else "?"
            # 2987 cm3 counts as 3000: it passes "from 3000"; 3199 counts as 3200 and passes "to 3200"
            self.assertEqual(self.cars(f"{page}{sep}cc_from=3000&cc_to=3200"), self.vins(1, 2), page)
            self.assertEqual(self.cars(f"{page}{sep}cc_from=3500"), self.vins(3, 4), page)
            self.assertEqual(self.cars(f"{page}{sep}fuel=diesel&cc_from=3500"), self.vins(4), page)
            self.assertEqual(self.cars(f"{page}{sep}cc_to=abc"), self.vins(1, 2, 3, 4, 5), page)     # not a number: ignored
            self.assertEqual(self.cars(f"{page}{sep}cc_from=99999"), self.vins(1, 2, 3, 4, 5), page)   # outside the slider: ignored

    def test_models_statistics_follow_the_filter(self):
        html = self.client.get("/models?model=g_w463&fuel=diesel").get_data(as_text=True)
        self.assertIn("Śledzone auta", html)
        self.assertIn("(2)", html)                                   # the table's count
        self.assertIn('<option value="diesel" selected>', html)      # the form keeps the choice
        self.assertIn("Wyczyść", html)

    def test_filters_survive_paging_and_show_the_fuel(self):
        html = self.client.get("/vehicles?fuel=diesel&cc_from=3000").get_data(as_text=True)
        self.assertIn("Diesel</span>", html)
        self.assertNotIn("Benzyna</span>", html)
        self.assertIn('name="cc_from" value="3000"', html)        # the slider keeps its place
        self.assertIn('name="cc_to" value=""', html)
        with mock.patch("webapp.blueprints.vehicles.PER_PAGE", 1):    # two diesels, so two pages
            paged = self.client.get("/vehicles?fuel=diesel&cc_from=3000").get_data(as_text=True)
        self.assertIn("?fuel=diesel&amp;cc_from=3000&amp;page=2", paged)   # the page links keep the filters

    def test_approving_a_listing_gives_the_car_its_fuel(self):
        conn = db.get_db()
        vin = "WDB4630311X000009"
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, source_url, status, make, model, variant, year, "
                     "engine_cc, fuel_type, vin, price_pln) VALUES ('otomoto', 'new-1', 'https://x', 'pending', "
                     "'Mercedes-Benz', 'G 350 d', 'G 350 d', 2004, 2987, 'diesel', ?, 150000)", (vin,))
        listing = conn.execute("SELECT * FROM pending_listings WHERE source_listing_id = 'new-1'").fetchone()
        with mock.patch("webapp.services.listings._enrich_otomoto_ad", return_value={}):
            _approve_listing(conn, listing)
        conn.commit()
        self.assertEqual(conn.execute("SELECT fuel_type FROM vehicles WHERE vin = ?", (vin,)).fetchone()[0], "diesel")
        conn.close()

    def test_migration_fills_the_fuel_from_the_newest_ad(self):
        conn = db.get_db()
        vin = CARS[1][0]
        conn.execute("UPDATE vehicles SET fuel_type = NULL")
        for sid, fuel in (("old", "diesel"), ("new", "petrol")):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, fuel_type) "
                         "VALUES ('otomoto', ?, 'approved', ?, ?)", (sid, vin, fuel))
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, fuel_type) "
                     "VALUES ('otomoto', 'rej', 'rejected', ?, 'lpg')", (CARS[0][0],))
        conn.execute("DELETE FROM schema_migrations WHERE version = 25")
        conn.commit()
        conn.close()
        db.init_db()
        conn = db.get_db()
        fuels = dict(conn.execute("SELECT vin, fuel_type FROM vehicles").fetchall())
        conn.close()
        self.assertEqual(fuels[vin], "petrol")             # the newest ad wins
        self.assertIsNone(fuels[CARS[0][0]])               # a rejected ad says nothing about the car


if __name__ == "__main__":
    unittest.main()
