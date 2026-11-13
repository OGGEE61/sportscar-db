"""Whether a listing is still up: the scrapers keep it, the recheck of rejected listings reads it
from the listing page, and every page shows it."""
import os
import sys
import unittest
from unittest import mock

sys.path[:0] = [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_listing_active.db")

import base_scraper
import db
from app import app

TOKEN = {"Authorization": "Bearer test-token"}
VIN = "WBS8M9C50J5K99001"


class TestFetchListing(unittest.TestCase):
    def state(self, status=None, exc=None):
        resp = mock.Mock(status_code=status, text="<html></html>")
        side = exc if exc else None
        with mock.patch.object(base_scraper.requests, "get", return_value=resp, side_effect=side), \
                mock.patch.object(base_scraper, "parse_detail", return_value={"year": 2020}):
            return base_scraper.fetch_listing("https://www.otomoto.pl/osobowe/oferta/x-ID1.html")

    def test_states(self):
        self.assertEqual(self.state(410), ("gone", {}))      # otomoto, OLX
        self.assertEqual(self.state(404), ("gone", {}))      # autoplac
        self.assertEqual(self.state(200), ("active", {"year": 2020}))
        self.assertEqual(self.state(403), ("error", {}))     # blocked: cannot tell
        self.assertEqual(self.state(exc=TimeoutError("t")), ("error", {}))

    def test_fetch_detail_unchanged(self):
        resp = mock.Mock(status_code=410, text="")
        with mock.patch.object(base_scraper.requests, "get", return_value=resp):
            self.assertEqual(base_scraper.fetch_detail("https://www.otomoto.pl/osobowe/oferta/x-ID1.html"), {})


class TestRecheckDecision(unittest.TestCase):
    def setUp(self):
        from scripts.maintenance import recheck_rejected
        from otomoto.mercedes_gla45_x156 import CONFIG
        self.r = recheck_rejected
        self.configs = {("otomoto", CONFIG.model, CONFIG.variant): [CONFIG]}

    def listing(self, **kw):
        base = {"id": 1, "source": "otomoto", "found_by": "otomoto", "model": "GLA", "variant": "GLA45 AMG X156",
                "raw_title": "Mercedes-Benz GLA 45 AMG", "year": 2017, "power_hp": 381, "engine_cc": 1991,
                "vin": None, "vin_confidence": "none", "raw_description": "", "review_notes": None,
                "registration_plate": None, "first_registration_date": None, "price_pln": 150000, "mileage_km": 80000}
        return {**base, **kw}

    def test_vin_added_since_comes_back(self):
        d = self.r.decide(self.listing(), "active", {"vin": "WDD1569421J123456", "vin_confidence": "found_in_schema"},
                          self.configs)
        self.assertEqual(d["action"], "restore")
        self.assertEqual(d["listing"]["vin"], "WDD1569421J123456")

    def test_vin_behind_show_vin_comes_back(self):
        d = self.r.decide(self.listing(), "active", {"vin_confidence": "found_in_schema"}, self.configs)
        self.assertEqual((d["action"], d["why"]), ("restore", "VIN: behind_reveal"))

    def test_still_no_vin_stays(self):
        self.assertEqual(self.r.decide(self.listing(), "active", {}, self.configs)["action"], "keep")

    def test_broken_rule_stays(self):
        d = self.r.decide(self.listing(), "active", {"power_hp": 156, "vin": "WDD1569421J123456"}, self.configs)
        self.assertEqual(d["action"], "keep")
        self.assertIn("156 HP", d["why"])

    def test_rejected_with_a_reason_stays(self):
        d = self.r.decide(self.listing(review_notes="BMW M8 Gran Coupé, nie M5 F90"), "active",
                          {"vin": "WDD1569421J123456"}, self.configs)
        self.assertEqual(d["action"], "keep")
        self.assertTrue(self.r.restorable_reason("Missing/Invalid VIN - Retroactively Rejected"))

    def test_gone_and_error(self):
        self.assertEqual(self.r.decide(self.listing(), "gone", {}, self.configs)["action"], "gone")
        self.assertEqual(self.r.decide(self.listing(), "error", {}, self.configs)["action"], "error")


class DbCase(unittest.TestCase):
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

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def row(self, lid):
        conn = db.get_db()
        r = conn.execute("SELECT * FROM pending_listings WHERE source_listing_id = ?", (lid,)).fetchone()
        conn.close()
        return dict(r)


class TestScrapersKeepTheState(DbCase):
    def add_approved(self, lid):
        conn = db.get_db()
        conn.execute("INSERT OR IGNORE INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'M3', 'F80 M3', 2018)", (VIN,))
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, make, model, variant, vin, status) "
                     "VALUES ('otomoto', ?, 'BMW', 'M3', 'F80 M3', ?, 'approved')", (lid, VIN))
        conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id) VALUES (?, 'otomoto', ?)", (VIN, lid))
        conn.commit()
        conn.close()

    def test_gone_from_the_search_then_seen_again(self):
        self.add_approved("1")
        self.client.post("/api/mark_removed", headers=TOKEN, json={"source": "otomoto", "make": "BMW", "model": "M3",
                                                                    "variant": "F80 M3", "seen_ids": ["other"]})
        r = self.row("1")
        self.assertEqual(r["is_listing_active"], 0)
        self.assertIsNotNone(r["checked_at"])
        self.client.post("/api/ingest_pending", headers=TOKEN, json={"source": "otomoto", "source_listing_id": "1",
                                                                      "make": "BMW", "model": "M3", "variant": "F80 M3"})
        self.assertEqual(self.row("1")["is_listing_active"], 1)

    def test_migration_marks_listings_whose_ads_are_all_gone(self):
        self.add_approved("2")
        conn = db.get_db()
        conn.execute("UPDATE listing_observations SET removed_at = '2026-11-01 10:00:00' WHERE source_listing_id = '2'")
        conn.execute("DELETE FROM schema_migrations WHERE version = 20")
        conn.commit()
        conn.close()
        db.init_db()
        r = self.row("2")
        self.assertEqual((r["is_listing_active"], r["checked_at"]), (0, "2026-11-01 10:00:00"))


class TestRecheckWrites(DbCase):
    def test_restore_and_gone(self):
        from scripts.maintenance import recheck_rejected
        conn = db.get_db()
        for lid in ("a", "b"):
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, source_url, status) "
                         "VALUES ('otomoto', ?, 'https://x', 'rejected')", (lid,))
        conn.commit()
        a, b = self.row("a"), self.row("b")
        recheck_rejected.write(conn, {"state": "active", "action": "restore", "why": "",
                                      "listing": dict(a, vin="WDD1569421J123456", vin_confidence="found_in_schema")})
        recheck_rejected.write(conn, {"state": "gone", "action": "gone", "why": "", "listing": b})
        conn.close()
        a, b = self.row("a"), self.row("b")
        self.assertEqual((a["status"], a["vin"], a["is_listing_active"]), ("pending", "WDD1569421J123456", 1))
        self.assertEqual((b["status"], b["is_listing_active"]), ("rejected", 0))


class TestPagesShowIt(DbCase):
    def test_car_marker_and_queue_badge(self):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'M3', 'F80 M3', 2018)", (VIN,))
        conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, removed_at) "
                     "VALUES (?, 'otomoto', '9', '2026-11-12 08:00:00')", (VIN,))
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, is_listing_active, checked_at, scraped_at) "
                     "VALUES ('otomoto', '9', 'pending', 0, '2026-11-12 08:00:00', '2026-10-01 10:00:00')")
        conn.commit()
        conn.close()
        self.assertIn("Zniknęło 12.11", self.client.get("/vehicles").get_data(as_text=True))
        self.assertIn("zniknęło · 12.11", self.client.get("/review").get_data(as_text=True))
        conn = db.get_db()
        conn.execute("UPDATE listing_observations SET removed_at = NULL")
        conn.commit()
        conn.close()
        self.assertIn("Ogłoszenie aktywne", self.client.get("/vehicles").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
