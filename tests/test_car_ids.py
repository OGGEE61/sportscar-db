"""The car's ID: every car with a real VIN has one (numbered oldest first, then on insert by the
trigger, whichever path inserts the car), placeholders have none, a corrected VIN keeps it, and the
VIN base finds a car by it."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_car_ids.db")

import db
from app import app

OLD, NEW, PLH = "WBS8M9C50J5K99001", "WBS8M9C50J5K99002", "PLH0000000000001"


class CarIdCase(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        self.tearDown()
        db.init_db()
        app.config["TESTING"] = True
        self.client = app.test_client()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        os.environ.pop("ADMIN_PASSWORD", None)
        self.addCleanup(patcher.stop)

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def add(self, vin, created_at="2026-01-01", model="M3"):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, year, created_at) VALUES (?, 'BMW', ?, 2018, ?)",
                     (vin, model, created_at))
        conn.commit()
        conn.close()

    def ids(self):
        conn = db.get_db()
        rows = {r["vin"]: r["car_id"] for r in conn.execute("SELECT vin, car_id FROM vehicles")}
        conn.close()
        return rows


class TestNumbering(CarIdCase):
    def test_new_cars_are_numbered_in_turn_and_placeholders_are_not(self):
        self.add(OLD)
        self.add(PLH)
        self.add(NEW)
        self.assertEqual(self.ids(), {OLD: 1, PLH: None, NEW: 2})

    def test_the_migration_numbers_the_cars_without_an_id_oldest_first(self):
        self.add(OLD, "2026-03-01")
        self.add(NEW, "2026-02-01")
        self.add(PLH, "2026-01-01")
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET car_id = NULL")
        conn.execute("UPDATE vehicles SET car_id = 7 WHERE vin = ?", (OLD,))  # one kept its ID
        conn.commit()
        conn.close()
        db.init_db()
        self.assertEqual(self.ids(), {OLD: 7, NEW: 8, PLH: None})

    def test_a_car_from_a_scraped_ad_gets_an_id(self):
        from webapp.services.listings import _approve_listing
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, make, model, year) "
                     "VALUES ('otomoto', '1', 'pending', ?, 'BMW', 'M3', 2018)", (OLD,))
        ad = conn.execute("SELECT * FROM pending_listings").fetchone()
        _approve_listing(conn, ad)
        conn.commit()
        conn.close()
        self.assertEqual(self.ids()[OLD], 1)

    def test_a_resolved_placeholder_gets_an_id_and_a_corrected_vin_keeps_it(self):
        self.add(OLD)
        self.add(PLH)
        db.resolve_placeholder(PLH, NEW)
        self.assertEqual(self.ids(), {OLD: 1, NEW: 2})
        fixed = "WBS8M9C50J5K99003"
        db.resolve_placeholder(OLD, fixed, reason="typo in the VIN")
        self.assertEqual(self.ids(), {fixed: 1, NEW: 2})
        db.resolve_placeholder(fixed, NEW, reason="same car")     # NEW existed: it keeps its own ID
        self.assertEqual(self.ids(), {NEW: 2})


class TestSearch(CarIdCase):
    def test_the_vin_base_finds_a_car_by_its_id_and_shows_it(self):
        self.add(OLD, model="M3")
        self.add(NEW, model="M5")
        page = self.client.get("/vehicles").get_data(as_text=True)
        self.assertIn("#1", page)
        self.assertIn("#2", page)
        for query in ("2", "#2", " 2 "):
            page = self.client.get("/vehicles", query_string={"id": query}).get_data(as_text=True)
            self.assertIn(NEW, page, query)
            self.assertNotIn(OLD, page, query)
        page = self.client.get("/vehicles", query_string={"id": "abc"}).get_data(as_text=True)
        self.assertNotIn(OLD, page)
        self.assertIn("#2", self.client.get(f"/vehicle/{NEW}").get_data(as_text=True))

    def test_the_vin_base_finds_a_car_by_its_plate(self):
        self.add(OLD, model="M3")
        self.add(NEW, model="M5")
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET registration_plate = 'WE1KM05' WHERE vin = ?", (NEW,))
        conn.commit()
        conn.close()
        for query in ("WE1KM05", "we 1km05", "1KM0"):
            page = self.client.get("/vehicles", query_string={"q": query}).get_data(as_text=True)
            self.assertIn(NEW, page, query)
            self.assertNotIn(OLD, page, query)


if __name__ == "__main__":
    unittest.main()
