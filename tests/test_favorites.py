"""The star next to a VIN adds the car to /favorites; it shows on every page that lists cars."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_favorites.db")

import db
from app import app

LIKED = "WBSJF0C55KB000001"
OTHER = "WBSJF0C55KB000002"
PAGES = ("/api/dashboard/recent", "/vehicles", "/models?model=m5_f90", "/api/poznan?km=50&days=30", f"/vehicle/{LIKED}")


class TestFavorites(unittest.TestCase):
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
        for vin in (LIKED, OTHER):
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, model_id) "
                         "VALUES (?, 'BMW', 'M5', 'F90 M5', 2019, 'm5_f90')", (vin,))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, "
                         "location_city, observed_at) VALUES (?, 'otomoto', ?, 'https://x', 300000, 'Poznań', datetime('now', '-1 days'))",
                         (vin, f"id-{vin}"))
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, vin, status) VALUES ('otomoto', ?, ?, 'approved')",
                         (f"id-{vin}", vin))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def star(self, vin, on=True):
        return self.client.post("/api/favorite", json={"vin": vin, "on": on})

    def stored(self):
        conn = db.get_db()
        vins = [r["vin"] for r in conn.execute("SELECT vin FROM favorites ORDER BY vin")]
        conn.close()
        return vins

    def pressed(self, html, vin):
        """aria-pressed of the car's star on a page."""
        at = html.index(f'data-vin="{vin}"')
        return html[at:at + 80].split('aria-pressed="')[1].split('"')[0]

    def test_toggle(self):
        self.assertEqual(self.star(LIKED).get_json(), {"favorite": True})
        self.assertEqual(self.star(LIKED).get_json(), {"favorite": True})     # twice: still one row
        self.assertEqual(self.stored(), [LIKED])
        self.assertEqual(self.star(LIKED, on=False).get_json(), {"favorite": False})
        self.assertEqual(self.star(LIKED, on=False).get_json(), {"favorite": False})
        self.assertEqual(self.stored(), [])

    def test_unknown_car(self):
        self.assertEqual(self.star("WBSJF0C55KB999129").status_code, 404)
        self.assertEqual(self.star("").status_code, 404)
        self.assertEqual(self.stored(), [])

    def test_needs_a_session(self):
        os.environ["ADMIN_PASSWORD"] = "secret"
        self.assertEqual(self.star(LIKED).status_code, 401)
        self.assertEqual(self.stored(), [])

    def test_star_on_every_page(self):
        self.star(LIKED)
        for path in PAGES:
            html = self.client.get(path).get_data(as_text=True)
            self.assertEqual(self.pressed(html, LIKED), "true", path)
            if OTHER in html:
                self.assertEqual(self.pressed(html, OTHER), "false", path)
        self.assertIn("bi-star-fill", self.client.get("/vehicles").get_data(as_text=True))

    def test_favorites_page(self):
        empty = self.client.get("/favorites").get_data(as_text=True)
        self.assertIn("Nie masz jeszcze ulubionych aut", empty)
        self.assertNotIn(LIKED, empty)
        self.star(LIKED)
        html = self.client.get("/favorites").get_data(as_text=True)
        self.assertIn(f"/vehicle/{LIKED}", html)
        self.assertNotIn(OTHER, html)
        self.assertIn(">Ulubione</h2>", html)
        self.assertIn('href="/favorites"', self.client.get("/vehicles").get_data(as_text=True))   # navbar
        self.assertIn(OTHER, self.client.get("/vehicles").get_data(as_text=True))                # full list unchanged

    def test_newest_favourite_first(self):
        conn = db.get_db()
        conn.execute("INSERT INTO favorites (vin, created_at) VALUES (?, '2026-11-01 10:00:00')", (LIKED,))
        conn.execute("INSERT INTO favorites (vin, created_at) VALUES (?, '2026-11-10 10:00:00')", (OTHER,))
        conn.commit()
        conn.close()
        html = self.client.get("/favorites").get_data(as_text=True)
        self.assertLess(html.index(f"/vehicle/{OTHER}"), html.index(f"/vehicle/{LIKED}"))

    def test_deleting_the_car_drops_the_favourite(self):
        self.star(LIKED)
        self.client.post(f"/vehicle/{LIKED}/delete", data={"confirm_vin": LIKED})
        self.assertEqual(self.stored(), [])

    def test_favourite_follows_a_resolved_placeholder(self):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, year, vin_status) VALUES ('PLH0000000000001', 'BMW', 'M5', 2019, 'placeholder')")
        conn.execute("INSERT INTO favorites (vin) VALUES ('PLH0000000000001')")
        conn.commit()
        conn.close()
        db.resolve_placeholder("PLH0000000000001", "WBSJF0C55KB000003")
        self.assertEqual(self.stored(), ["WBSJF0C55KB000003"])


if __name__ == "__main__":
    unittest.main()
