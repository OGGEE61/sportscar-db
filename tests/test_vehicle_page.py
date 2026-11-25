"""The car's page: its "Do sprawdzenia" panel (the pending /plates card, approved or rejected right
there, and the open notes), its ads collapsed to the changes, and the ad description shown as text."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_vehicle_page.db")

import db
from app import app
from webapp.helpers import plain_text
from webapp.services import verification

CAR, OTHER = "WBA21GL000FW01591", "WBSTS01000LS73520"


class VehiclePageCase(unittest.TestCase):
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
        for vin in (CAR, OTHER):
            conn.execute("INSERT INTO vehicles (vin, make, model, year, registration_plate, first_registration_date) "
                         "VALUES (?, 'BMW', 'Seria 3', 2025, 'MXY1265', '2025-12-18')", (vin,))
        conn.execute("INSERT INTO plate_review_queue (vin, detected_plate, confidence, status) VALUES (?, 'MXY1265', 0.4, 'pending')",
                     (CAR,))
        self.card_id = conn.execute("SELECT id FROM plate_review_queue WHERE vin = ?", (CAR,)).fetchone()[0]
        verification.add_review_note(conn, CAR, "plate", "Plakietka dealera zamiast tablicy.", "https://example.com/ad")
        # One ad seen four times: the price drops once, the rest are repeats
        for day, price in (("2026-11-06", 268900), ("2026-11-08", 268900), ("2026-11-10", 264900), ("2026-11-12", 264900)):
            conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, source_url, price_pln, "
                         "mileage_km, observed_at, first_seen_at) VALUES (?, 'otomoto', '6149374009', 'https://example.com/ad', "
                         "?, 25300, ?, '2026-11-06')", (CAR, price, day + " 08:00:00"))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def panel(self, vin=CAR):
        return self.client.get(f"/vehicle/{vin}/to_check").get_data(as_text=True)

    def card(self):
        conn = db.get_db()
        try:
            card = conn.execute("SELECT status, reviewed_plate FROM plate_review_queue WHERE id = ?", (self.card_id,)).fetchone()
            plate = conn.execute("SELECT registration_plate FROM vehicles WHERE vin = ?", (CAR,)).fetchone()[0]
            return card["status"], card["reviewed_plate"], plate
        finally:
            conn.close()


class TestToCheckPanel(VehiclePageCase):
    def test_the_page_loads_the_panel_with_the_card_its_hints_and_the_notes(self):
        self.assertIn(f'hx-get="/vehicle/{CAR}/to_check"', self.client.get(f"/vehicle/{CAR}").get_data(as_text=True))
        panel = self.panel()
        self.assertIn(f"karta {self.card_id}", panel)
        self.assertIn("MXY1265 nie ma formatu polskiej tablicy", panel)
        self.assertIn("Plakietka dealera zamiast tablicy.", panel)
        self.assertNotIn("Do sprawdzenia", self.panel(OTHER))     # nothing waits for a person

    def test_a_reading_that_cannot_be_polish_is_not_offered(self):
        panel = self.panel()
        self.assertIn('name="plate" value=""', panel)          # MXY1265 is a configurator's sample plate
        self.assertIn("Brak tablicy</button>", panel)

    def test_rejecting_the_card_on_the_page_clears_the_plate(self):
        r = self.client.post(f"/vehicle/{CAR}/plate_card", data={"card_id": self.card_id, "action": "reject"})
        self.assertIn("tablica MXY1265 usunięta z auta", r.get_data(as_text=True))
        self.assertEqual(self.card(), ("rejected", "MXY1265", None))
        self.assertNotIn("Tablica do potwierdzenia", self.panel())
        self.assertIn("Plakietka dealera", self.panel())           # the note waits to be ticked off

    def test_approving_takes_the_typed_plate(self):
        self.client.post(f"/vehicle/{CAR}/plate_card", data={"card_id": self.card_id, "action": "approve", "plate": "sk 1k663"})
        self.assertEqual(self.card(), ("approved", "SK1K663", "SK1K663"))

    def test_another_cars_card_is_refused(self):
        r = self.client.post(f"/vehicle/{OTHER}/plate_card", data={"card_id": self.card_id, "action": "reject"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.card()[0], "pending")


class TestHeader(VehiclePageCase):
    def test_the_title_starts_with_the_cars_id(self):
        conn = db.get_db()
        car_id = conn.execute("SELECT car_id FROM vehicles WHERE vin = ?", (CAR,)).fetchone()[0]
        conn.close()
        page = self.client.get(f"/vehicle/{CAR}").get_data(as_text=True)
        title = page[page.index('class="vehicle-title"'):page.index("</h1>")]
        self.assertIn(f"#{car_id}", title)


class TestVinSearch(VehiclePageCase):
    def test_a_north_american_car_points_to_the_auctions(self):
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET origin_market = 'USA' WHERE vin = ?", (CAR,))
        conn.commit()
        conn.close()
        page = self.client.get(f"/vehicle/{CAR}").get_data(as_text=True)
        self.assertIn("Auto z Ameryki Północnej", page)
        self.assertIn(f"q=%22{CAR}%22%20%28bid.cars", page)
        other = self.client.get(f"/vehicle/{OTHER}").get_data(as_text=True)
        self.assertNotIn("Auto z Ameryki Północnej", other)
        self.assertIn("Sprawdź VIN w sieci", other)

    def test_a_vin_built_in_the_usa_alone_does_not_count(self):
        vin = "5UX83DP08P9S24709"     # every X3 is built in the USA, also the European ones
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES (?, 'BMW', 'X3', 2023)", (vin,))
        conn.commit()
        conn.close()
        self.assertNotIn("Auto z Ameryki Północnej", self.client.get(f"/vehicle/{vin}").get_data(as_text=True))


class TestAdsAndDescription(VehiclePageCase):
    def test_an_ad_shows_only_its_changes_and_keeps_every_sighting_folded(self):
        page = self.client.get(f"/vehicle/{CAR}").get_data(as_text=True)
        self.assertIn("Wszystkie obserwacje (4)", page)
        self.assertIn("było 268 900 zł", page)
        changes = page[page.index("<th>Od</th>"):page.index("Wszystkie obserwacje")]
        self.assertEqual(changes.count("<tr>"), 2)                # 268 900, then 264 900

    def test_the_ads_html_becomes_text(self):
        self.assertEqual(plain_text("<p>A &amp; B</p><p><br></p><p>C<br/>D</p>"), "A & B\n\nC\nD")
        self.assertEqual(plain_text("przebieg <10 tys>, 3<5"), "przebieg <10 tys>, 3<5")


if __name__ == "__main__":
    unittest.main()
