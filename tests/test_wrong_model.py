"""A car filed under the wrong model is hidden from its page; a new ad of it does not bring it back."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_wrong_model.db")

import db
from app import app

TOKEN = {"Authorization": "Bearer test-token"}
M8 = "WBSGV01030CP94224"     # an M8 filed as an M5
M5 = "WBSJF0C55KB000002"


class TestWrongModel(unittest.TestCase):
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
        for vin in (M8, M5):
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, model_id) "
                         "VALUES (?, 'BMW', 'M5', 'F90 M5', 2020, 'm5_f90')", (vin,))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, observed_at) "
                         "VALUES (?, 'otomoto', ?, 'https://x', 400000, datetime('now', '-1 days'))", (vin, f"id-{vin}"))
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, vin, status, make, model, variant) "
                         "VALUES ('otomoto', ?, ?, 'approved', 'BMW', 'M5', 'F90 M5')", (f"id-{vin}", vin))
        # an older sighting of the M8 that was already left out as dealer stock keeps its own reason
        conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, excluded_reason, observed_at) "
                     "VALUES (?, 'otomoto', 'old', 'dealer_new', datetime('now', '-90 days'))", (M8,))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def state(self, vin=M8):
        conn = db.get_db()
        listings = {r["source_listing_id"]: (r["status"], r["review_notes"])
                    for r in conn.execute("SELECT * FROM pending_listings WHERE vin = ?", (vin,))}
        reasons = {r["source_listing_id"]: r["excluded_reason"]
                   for r in conn.execute("SELECT * FROM listing_observations WHERE vin = ?", (vin,))}
        conn.close()
        return listings, reasons

    def hide(self, reason="M8 Gran Coupé, nie M5"):
        return self.client.post(f"/vehicle/{M8}/wrong_model", data={"reason": reason}, follow_redirects=True)

    def test_hide(self):
        page = self.hide().get_data(as_text=True)
        listings, reasons = self.state()
        self.assertEqual(listings[f"id-{M8}"], ("rejected", "Nie ten model: M8 Gran Coupé, nie M5"))
        self.assertEqual(reasons, {f"id-{M8}": "wrong_model", "old": "dealer_new"})
        self.assertEqual(self.state(M5)[1], {f"id-{M5}": None})                  # the other car is untouched
        self.assertIn("Auto ukryte jako błędnie przypisany model: <strong>M8 Gran Coupé, nie M5</strong>", page)
        for path in ("/vehicles", "/models?model=m5_f90", "/api/dashboard/recent"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotIn(M8, html, path)
            self.assertIn(M5[:12], html, path)

    def test_a_reason_is_required(self):
        page = self.hide(reason="   ").get_data(as_text=True)
        self.assertIn("Podaj, czym to auto jest naprawdę", page)
        self.assertEqual(self.state()[0][f"id-{M8}"], ("approved", None))

    def test_restore(self):
        self.hide()
        self.client.post(f"/vehicle/{M8}/restore_model")
        listings, reasons = self.state()
        self.assertEqual(listings[f"id-{M8}"], ("approved", None))
        self.assertEqual(reasons, {f"id-{M8}": None, "old": "dealer_new"})      # its own reason stays
        self.assertIn(M8, self.client.get("/vehicles").get_data(as_text=True))
        self.assertNotIn("Auto ukryte", self.client.get(f"/vehicle/{M8}").get_data(as_text=True))

    def test_a_new_ad_does_not_bring_it_back(self):
        self.hide()
        out = self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "autoplac", "source_listing_id": "new-ad", "vin": M8, "vin_confidence": "found_in_schema",
            "make": "BMW", "model": "M5", "variant": "F90 M5", "price_pln": 390000}).get_json()
        self.assertEqual(out["tag"], "wrong_model")
        listings, reasons = self.state()
        self.assertEqual(listings["new-ad"], ("rejected", "Nie ten model: M8 Gran Coupé, nie M5"))
        self.assertNotIn("new-ad", reasons)                                      # no sighting was added
        self.assertNotIn(M8, self.client.get("/vehicles").get_data(as_text=True))

    def test_a_new_ad_of_a_normal_car_is_approved_as_before(self):
        self.hide()
        out = self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "autoplac", "source_listing_id": "new-m5", "vin": M5, "vin_confidence": "found_in_schema",
            "make": "BMW", "model": "M5", "variant": "F90 M5", "price_pln": 390000}).get_json()
        self.assertEqual(out["tag"], "known_vin")
        self.assertEqual(self.state(M5)[1]["new-m5"], None)


if __name__ == "__main__":
    unittest.main()
