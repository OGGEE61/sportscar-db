"""Every page that lists a car marks it with the same set of flags (templates/_car_flags.html)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_car_flags.db")

import db
from app import app

CRASHED = "WBSJF0C55KB000001"   # verified, plate from a photo, CEPiK rollback, damage history
PLAIN = "WBSJF0C55KB000002"     # unverified, no plate, no CEPiK report, ad marked damaged

PAGES = ("/api/dashboard/recent", "/vehicles", "/models?model=m5_f90", "/api/deals?km=50&days=30")


class TestSameFlagsEverywhere(unittest.TestCase):
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
        for vin, status, plate in ((CRASHED, "verified", "PO1234X"), (PLAIN, "unverified", None)):
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, vin_status, registration_plate, model_id, origin_market) "
                         "VALUES (?, 'BMW', 'M5', 'F90 M5', 2019, ?, ?, 'm5_f90', ?)", (vin, status, plate, "Kanada" if plate else None))
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, "
                         "location_city, observed_at) VALUES (?, 'otomoto', ?, 'https://x', 300000, 'Poznań', datetime('now', '-1 days'))",
                         (vin, f"id-{vin}"))
        conn.execute("INSERT INTO tags (vin, tag) VALUES (?, 'photo extracted')", (CRASHED,))
        conn.execute("INSERT INTO tags (vin, tag) VALUES (?, 'CEPiK: Ważne OC i SKP')", (CRASHED,))
        conn.execute("INSERT INTO tags (vin, tag) VALUES (?, 'po lakierniku')", (CRASHED,))
        conn.execute("INSERT INTO tags (vin, tag) VALUES (?, 'missing plates')", (PLAIN,))
        conn.execute("INSERT INTO cepik_reports (vin, odometer_rollback, rollback_diff_km, last_odometer_km) VALUES (?, 1, 52000, 152000)", (CRASHED,))
        conn.execute("INSERT INTO condition_reports (vin, report_date, accident_free, country) VALUES (?, '2020-10-11', 0, 'Belgia')", (CRASHED,))
        conn.execute("INSERT INTO damaged_listings (source, source_listing_id) VALUES ('otomoto', ?)", (f"id-{PLAIN}",))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def flags_on(self, path):
        html = self.client.get(path).get_data(as_text=True)
        self.assertIn("car-flags", html, path)
        return html

    def test_list_pages(self):
        for path in PAGES:
            html = self.flags_on(path)
            self.assertNotIn("CEPiK: Ważne OC i SKP", html, path)  # a CEPiK tag is the CEPiK marker
            self.assertNotIn("missing plates", html, path)        # "Brak tablicy" says it
            for marker in ("VIN ✓", "PO1234X", "bi-camera", "Kanada</span>", "po lakierniku</span>", "Cofnięty licznik", "Historia szkody: Belgia",
                           "VIN niepewny", "Brak tablicy", "bez CEPiK", "Uszkodzony</span>"):
                self.assertIn(marker, html, f"{marker} missing on {path}")

    def test_plate_on_the_vin_line_markers_under_it(self):
        html = self.flags_on("/vehicles")
        block = html[html.index(f'href="/vehicle/{CRASHED}" class="vin-code"'):]
        vin_line = block[:block.index("</div>")]
        self.assertIn("PO1234X", vin_line)
        self.assertNotIn("VIN ✓", vin_line)
        self.assertEqual(block.count("PO1234X", 0, block.index("Cofnięty licznik")), 1)  # not repeated below
        self.assertLess(block.index("Cofnięty licznik"), block.index("po lakierniku"))
        # Without a plate, "Brak tablicy" leads the markers under the VIN
        plain = html[html.index(f'href="/vehicle/{PLAIN}" class="vin-code"'):]
        self.assertNotIn("Brak tablicy", plain[:plain.index("</div>")])
        self.assertLess(plain.index("Brak tablicy"), plain.index("VIN niepewny"))

    def test_vehicle_page(self):
        html = self.flags_on(f"/vehicle/{CRASHED}")
        for marker in ("VIN ✓", "PO1234X", "Cofnięty licznik", "Historia szkody: Belgia"):
            self.assertIn(marker, html)
        html = self.flags_on(f"/vehicle/{PLAIN}")
        for marker in ("VIN niepewny", "Brak tablicy", "bez CEPiK", "Uszkodzony</span>"):
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
