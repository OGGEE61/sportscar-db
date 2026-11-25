"""Origin, mileage and first registration filters on /vehicles (the VIN base)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_history_filter.db")

import db
from app import app

# vin, origin, first registration, [(mileage, days ago), ...]
CARS = [
    ("WBA00000000000001", None, "2019-03-01", [(90000, 30), (120000, 1)]),   # newest sighting: 120 000
    ("WBA00000000000002", "USA", "2020-06-15", [(40000, 1)]),
    ("WBA00000000000003", "Kanada", None, [(60000, 1)]),
    ("WBA00000000000004", "Japonia", "2015-12-31", [(None, 1)]),
    ("WBA00000000000005", "Europa", "2021-01-01", [(15000, 1)]),
]


class TestHistoryFilter(unittest.TestCase):
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
        for vin, origin, reg, sightings in CARS:
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, origin_market, first_registration_date) "
                         "VALUES (?, 'BMW', 'X3', 'M40i G01', 2019, ?, ?)", (vin, origin, reg))
            for km, days in sightings:
                conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, price_pln, mileage_km, "
                             "observed_at) VALUES (?, 'otomoto', ?, 150000, ?, datetime('now', ?))",
                             (vin, f"id-{vin}", km, f"-{days} days"))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def cars(self, query=""):
        html = self.client.get("/vehicles" + query).get_data(as_text=True)
        return {int(vin[-1]) for vin, *_ in CARS if f'href="/vehicle/{vin}"' in html}

    def test_origin_leaves_out_north_america_or_everything_outside_europe(self):
        self.assertEqual(self.cars(), {1, 2, 3, 4, 5})
        self.assertEqual(self.cars("?origin=no_usa"), {1, 4, 5})      # unknown origin (1) stays
        self.assertEqual(self.cars("?origin=europe"), {1, 5})
        self.assertEqual(self.cars("?origin=mars"), {1, 2, 3, 4, 5})  # unknown choice: ignored

    def test_mileage_is_the_newest_sightings(self):
        self.assertEqual(self.cars("?km_to=100000"), {2, 3, 5})       # car 1 had 90 000, now 120 000
        self.assertEqual(self.cars("?km_from=50000&km_to=150000"), {1, 3})
        self.assertEqual(self.cars("?km_from=abc"), {1, 2, 3, 4, 5})  # not a number: ignored
        html = self.client.get("/vehicles").get_data(as_text=True)
        self.assertIn("120 000 km", html)
        self.assertNotIn("90 000 km", html)

    def test_first_registration_years_are_inclusive(self):
        self.assertEqual(self.cars("?reg_from=2019&reg_to=2020"), {1, 2})
        self.assertEqual(self.cars("?reg_to=2015"), {4})              # 31.12.2015 is still 2015
        self.assertEqual(self.cars("?reg_from=2021"), {5})            # without a date (3): left out
        self.assertEqual(self.cars("?reg_from=1900"), {1, 2, 3, 4, 5})  # outside the range: ignored

    def test_sorting_by_mileage_puts_cars_without_one_last(self):
        html = self.client.get("/vehicles?sort=mileage").get_data(as_text=True)
        order = sorted((html.index(f'href="/vehicle/{vin}"'), int(vin[-1])) for vin, *_ in CARS)
        self.assertEqual([n for _, n in order], [5, 2, 3, 1, 4])

    def test_the_form_and_page_links_keep_the_choices(self):
        query = "?origin=europe&km_to=150000&reg_from=2019"
        html = self.client.get("/vehicles" + query).get_data(as_text=True)
        self.assertIn('<option value="europe" selected>', html)
        self.assertIn('name="km_to" type="number"', html)
        self.assertIn('value="150000"', html)
        self.assertIn('<option value="2019" selected>od 2019</option>', html)
        with mock.patch("webapp.blueprints.vehicles.PER_PAGE", 1):
            paged = self.client.get("/vehicles" + query).get_data(as_text=True)
        self.assertIn("?origin=europe&amp;km_to=150000&amp;reg_from=2019&amp;page=2", paged)


if __name__ == "__main__":
    unittest.main()
