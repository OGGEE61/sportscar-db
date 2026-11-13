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

OVERSEAS = "WBSJF0C55KB000003"  # from the USA, ad marked damaged, no plate: still abroad

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
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, vin, status) VALUES ('otomoto', ?, ?, 'approved')",
                         (f"id-{vin}", vin))
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

    def add_overseas(self, plate=None):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, registration_plate, model_id, origin_market) "
                     "VALUES (?, 'BMW', 'M5', 'F90 M5', 2019, ?, 'm5_f90', 'USA')", (OVERSEAS, plate))
        conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, mileage_km, "
                     "location_city, observed_at) VALUES (?, 'otomoto', 'id-us', 'https://x', 150000, 90000, 'Poznań', "
                     "datetime('now', '-1 days'))", (OVERSEAS,))
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, vin, status, origin_market, scraped_at) "
                     "VALUES ('otomoto', 'id-us', ?, 'approved', 'USA', datetime('now'))", (OVERSEAS,))
        conn.execute("INSERT INTO damaged_listings (source, source_listing_id) VALUES ('otomoto', 'id-us')")
        conn.commit()
        conn.close()

    def overseas_block(self, html):
        block = html[html.index(OVERSEAS):]
        return block[:block.index("</td>")] if "</td>" in block else block[:2000]

    def test_damaged_car_from_usa_is_still_abroad(self):
        self.add_overseas()
        for path in PAGES:
            html = self.flags_on(path)
            if OVERSEAS not in html:
                continue   # deals leave damaged cars out
            block = self.overseas_block(html)
            self.assertIn("W USA", block, path)
            self.assertNotIn("Brak tablicy", block, path)   # no Polish plate expected
            self.assertNotIn("bez CEPiK", block, path)      # nothing to look up
        models = self.client.get("/models?model=m5_f90").get_data(as_text=True)
        self.assertNotIn("90,000 km", models)               # its mileage is not in the averages

    def test_a_plate_means_it_was_brought_in(self):
        self.add_overseas(plate="WI12345")
        block = self.overseas_block(self.flags_on("/vehicles"))
        self.assertIn("WI12345", block)
        self.assertNotIn("W USA", block)
        self.assertIn("90,000 km", self.client.get("/models?model=m5_f90").get_data(as_text=True))

    def test_no_plate_reveal_for_a_car_still_abroad(self):
        self.add_overseas()
        with mock.patch.dict(os.environ, {"API_TOKEN": "t"}):
            out = self.client.post("/api/reveal_queue", json={"plates_since": "2000-01-01"},
                                   headers={"Authorization": "Bearer t"}).get_json()
        sids = [p["source_listing_id"] for p in out["plates"]]
        self.assertNotIn("id-us", sids)
        self.assertIn(f"id-{PLAIN}", sids)                  # damaged, but not from overseas

    def test_plate_on_the_vin_line_markers_under_it(self):
        html = self.flags_on("/vehicles")
        block = html[html.index(f'href="/vehicle/{CRASHED}" class="vin-code"'):]
        vin_line = block[:block.index("</div>")]
        self.assertIn("PO1234X", vin_line)
        self.assertNotIn("VIN ✓", vin_line)
        self.assertEqual(block.count("PO1234X", 0, block.index("Cofnięty licznik")), 1)  # not repeated below
        self.assertLess(block.index("Cofnięty licznik"), block.index("po lakierniku"))
        # Without a plate, "Brak tablicy" takes the plate's place on the VIN line
        plain = html[html.index(f'href="/vehicle/{PLAIN}" class="vin-code"'):]
        self.assertIn("Brak tablicy", plain[:plain.index("</div>")])
        self.assertEqual(plain.count(">Brak tablicy<", 0, plain.index("VIN niepewny")), 1)

    def test_vehicle_page(self):
        html = self.flags_on(f"/vehicle/{CRASHED}")
        for marker in ("VIN ✓", "PO1234X", "Cofnięty licznik", "Historia szkody: Belgia"):
            self.assertIn(marker, html)
        html = self.flags_on(f"/vehicle/{PLAIN}")
        for marker in ("VIN niepewny", "Brak tablicy", "bez CEPiK", "Uszkodzony</span>"):
            self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
