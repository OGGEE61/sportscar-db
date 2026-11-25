"""The origin review page (/review/origins): cars whose stored origin market and Bielik's disagree,
and a person's decision, which scraping and later Bielik runs keep."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_origin_review.db")

import db
import enrich_with_bielik as enrich
from app import app
from webapp.services.listings import _approve_listing

FLAGGED, CALM = "WBA81FY090FU67516", "WBA81FY0X0FT60376"


class TestOriginReview(unittest.TestCase):
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
        conn.execute("INSERT INTO vehicles (vin, make, model, year, origin_market, ai_suggested_market, ai_conflict, "
                     "ai_reasoning, ai_interior_color) VALUES (?, 'BMW', 'Seria 3', 2020, 'Polska', 'USA', 1, "
                     "'Sprowadzony z USA, aukcja Copart', 'czarny / skóra')", (FLAGGED,))
        conn.execute("INSERT INTO vehicles (vin, make, model, year, origin_market, ai_suggested_market, ai_conflict) "
                     "VALUES (?, 'BMW', 'Seria 3', 2020, 'Polska', 'Polska', 0)", (CALM,))
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, source_url, status, vin, scraped_at, "
                     "raw_description) VALUES ('otomoto', '1', 'https://www.otomoto.pl/oferta/1', 'approved', ?, "
                     "'2026-11-20 10:00:00', 'Auto sprowadzone z USA po aukcji Copart, polski salon nie dotyczy.')",
                     (FLAGGED,))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def car(self, vin=FLAGGED):
        conn = db.get_db()
        row = dict(conn.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,)).fetchone())
        conn.close()
        return row

    def test_the_page_lists_only_flagged_cars_with_their_ads(self):
        self.assertEqual(self.client.get("/review/origins").headers["Location"], "/verify?issue=origin")
        page = self.client.get("/verify?issue=origin").get_data(as_text=True)
        self.assertIn(FLAGGED, page)
        self.assertNotIn(CALM, page)
        self.assertIn("Sprowadzony z USA, aukcja Copart", page)
        self.assertIn("https://www.otomoto.pl/oferta/1", page)
        self.assertIn("Rozbieżności rynku", self.client.get("/review").get_data(as_text=True))
        self.assertIn("Rozstrzygnij", self.client.get(f"/vehicle/{FLAGGED}").get_data(as_text=True))

    def approve_ad(self, vin, sid, origin):
        """A new ad of the car approved as the review queue does, with the scraper's origin market."""
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, make, model, origin_market) "
                     "VALUES ('olx', ?, 'pending', ?, 'BMW', 'Seria 3', ?)", (sid, vin, origin))
        ad = conn.execute("SELECT * FROM pending_listings WHERE source_listing_id = ?", (sid,)).fetchone()
        _approve_listing(conn, ad, overrides={"vin": vin})   # overrides: no fetch of the ad's page
        conn.commit()
        conn.close()

    def test_agreeing_with_bielik_sets_his_market_and_interior(self):
        r = self.client.post(f"/review/origins/{FLAGGED}", data={"market": "USA"}, headers={"HX-Request": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="origin-conflict-count" hx-swap-oob="true">0<', r.get_data(as_text=True))
        car = self.car()
        self.assertEqual((car["origin_market"], car["ai_conflict"], car["color_int"]), ("USA", 0, "czarny / skóra"))
        self.assertIsNotNone(car["origin_checked_at"])
        self.assertNotIn(FLAGGED, self.client.get("/review/origins").get_data(as_text=True))

    def test_keeping_the_stored_market_or_unknown(self):
        self.client.post(f"/review/origins/{FLAGGED}", data={"market": "Polska"})
        self.assertEqual((self.car()["origin_market"], self.car()["color_int"]), ("Polska", None))
        self.client.post(f"/review/origins/{FLAGGED}", data={"market": "nieznany"})
        self.assertIsNone(self.car()["origin_market"])

    def test_an_unknown_market_or_car_is_refused(self):
        self.assertEqual(self.client.post(f"/review/origins/{FLAGGED}", data={"market": "Mars"}).status_code, 400)
        self.assertEqual(self.client.post("/review/origins/WBA00000000000000", data={"market": "USA"}).status_code, 404)
        self.assertEqual(self.car()["ai_conflict"], 1)

    def test_the_decision_survives_scraping_and_bielik(self):
        self.client.post(f"/review/origins/{FLAGGED}", data={"market": "USA"})
        self.approve_ad(FLAGGED, "2", "Polska")
        self.assertEqual(self.car()["origin_market"], "USA")
        conn = db.get_db()
        car = conn.execute("SELECT vin, origin_market, origin_checked_at FROM vehicles WHERE vin = ?", (FLAGGED,)).fetchone()
        enrich.save_car(conn, car, {"ai_summary": "x", "ai_suggested_market": "Japonia", "ai_reasoning": "z Japonii",
                                    "ai_equipment": None, "ai_interior_color": None}, 1)
        conn.close()
        self.assertEqual(self.car()["ai_conflict"], 0)

    def test_scraping_still_fills_an_unchecked_market(self):
        self.approve_ad(CALM, "3", "Europa")
        self.assertEqual(self.car(CALM)["origin_market"], "Europa")


if __name__ == "__main__":
    unittest.main()
