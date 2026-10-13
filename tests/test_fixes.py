"""Regression tests for schema drift, auth hardening and VIN re-keying."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_fixes.db")

import db
from app import app

TOKEN = {"Authorization": "Bearer test-token"}
VIN = "WBS11DM0108E8AG77"


class FixesTestCase(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        # Deliberately NOT loading schema.sql: init_db() alone must be enough
        db.init_db()
        app.config["TESTING"] = True
        self.client = app.test_client()
        # Default to "no password configured"; TestAuth turns it on explicitly
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        os.environ.pop("ADMIN_PASSWORD", None)
        self.addCleanup(patcher.stop)

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def login(self):
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True


class TestFreshSchema(FixesTestCase):
    def test_logs_page_works_on_fresh_db(self):
        res = self.client.post("/api/log_run", json={"status": "ok", "message": "hi", "found_count": 3},
                               headers=TOKEN)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/logs").status_code, 200)

    def test_init_db_is_idempotent(self):
        db.init_db()
        db.init_db()


class TestFlash(FixesTestCase):
    def test_bulk_reject_novin_flashes_message(self):
        self.client.post("/api/ingest_pending", json={"source": "olx", "source_listing_id": "1", "make": "BMW"},
                         headers=TOKEN)
        res = self.client.post("/review/bulk_reject_novin")
        self.assertEqual(res.status_code, 302)
        page = self.client.get("/review").get_data(as_text=True)
        self.assertIn("Automatically rejected 1 listings", page)


class TestAuth(FixesTestCase):
    def setUp(self):
        super().setUp()
        os.environ["ADMIN_PASSWORD"] = "secret"

    def test_browser_api_requires_login(self):
        for path in ("/api/plates/review", "/api/plates/scan_batch", f"/api/cepik/fetch/{VIN}"):
            self.assertEqual(self.client.post(path, json={}).status_code, 401, path)
        for path in ("/api/stats", "/api/vehicles"):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_browser_api_allowed_when_logged_in(self):
        self.login()
        res = self.client.post("/api/plates/review", json={})
        self.assertEqual(res.status_code, 400)  # reaches the handler: bad params

    def test_scraper_api_uses_token_not_session(self):
        payload = {"source": "olx", "source_listing_id": "2", "make": "BMW"}
        self.assertEqual(self.client.post("/api/ingest_pending", json=payload, headers=TOKEN).status_code, 200)
        bad = {"Authorization": "Bearer wrong"}
        self.assertEqual(self.client.post("/api/ingest_pending", json=payload, headers=bad).status_code, 401)
        self.assertEqual(self.client.post("/api/ingest_pending", json=payload).status_code, 401)

    def test_login(self):
        self.assertEqual(self.client.post("/login", data={"password": "nope"}).status_code, 200)
        self.assertEqual(self.client.post("/login", data={"password": "secret"}).status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_destructive_review_routes_reject_get(self):
        self.login()
        self.assertEqual(self.client.get("/review/reject_all_pending").status_code, 405)
        self.assertEqual(self.client.get("/review/clear_rejected").status_code, 405)
        self.assertEqual(self.client.post("/review/clear_rejected?ajax=1").status_code, 200)


class TestIngestUpsert(FixesTestCase):
    def test_unknown_make_does_not_overwrite(self):
        base = {"source": "otomoto", "source_listing_id": "10", "vin": VIN, "year": 2018}
        self.client.post("/api/ingest", json={**base, "make": "BMW", "model": "M2", "variant": "M2"},
                         headers=TOKEN)
        self.client.post("/api/ingest", json={**base, "variant": "M2 Competition"}, headers=TOKEN)
        conn = db.get_db()
        v = conn.execute("SELECT * FROM vehicles WHERE vin=?", (VIN,)).fetchone()
        conn.close()
        self.assertEqual((v["make"], v["model"], v["variant"], v["year"]), ("BMW", "M2", "M2 Competition", 2018))


class TestResolvePlaceholder(FixesTestCase):
    def test_keeps_all_data_and_moves_children(self):
        old = db.make_placeholder_vin("otomoto", "123")
        conn = db.get_db()
        conn.execute("""INSERT INTO vehicles(vin, make, model, year, vin_status, photo, registration_plate,
                        first_registration_date, equipment, origin_market)
                        VALUES(?, 'BMW', 'M2', 2018, 'placeholder', 'photos/a.jpg', 'WA12345',
                        '2018-05-01', '["HUD"]', 'PL')""", (old,))
        conn.execute("INSERT INTO listing_observations(vin, source) VALUES(?, 'otomoto')", (old,))
        conn.execute("INSERT INTO tags(vin, tag) VALUES(?, 'shared'), (?, 'only-old')", (old, old))
        conn.execute("INSERT INTO plate_review_queue(vin, detected_plate) VALUES(?, 'WA12345')", (old,))
        conn.execute("INSERT INTO cepik_reports(vin, total_owners) VALUES(?, 2)", (old,))
        # Real VIN already exists with one overlapping tag
        conn.execute("INSERT INTO vehicles(vin, make, model, year) VALUES(?, 'BMW', 'M2', 2018)", (VIN,))
        conn.execute("INSERT INTO tags(vin, tag) VALUES(?, 'shared')", (VIN,))
        conn.commit()
        conn.close()

        db.resolve_placeholder(old, VIN)

        conn = db.get_db()
        v = conn.execute("SELECT * FROM vehicles WHERE vin=?", (VIN,)).fetchone()
        self.assertEqual(v["photo"], "photos/a.jpg")
        self.assertEqual(v["registration_plate"], "WA12345")
        self.assertEqual(v["first_registration_date"], "2018-05-01")
        self.assertEqual(v["equipment"], '["HUD"]')
        self.assertEqual(v["origin_market"], "PL")
        self.assertIsNone(conn.execute("SELECT 1 FROM vehicles WHERE vin=?", (old,)).fetchone())
        tags = sorted(r[0] for r in conn.execute("SELECT tag FROM tags WHERE vin=?", (VIN,)))
        self.assertEqual(tags, ["only-old", "shared"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM listing_observations WHERE vin=?", (VIN,)).fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM plate_review_queue WHERE vin=?", (VIN,)).fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT total_owners FROM cepik_reports WHERE vin=?", (VIN,)).fetchone()[0], 2)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM vin_correction_log").fetchone()[0], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
