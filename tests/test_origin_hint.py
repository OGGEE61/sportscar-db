"""North American equipment in the ads (validation.north_american_equipment): a car whose ads list a
satellite tuner, the VIN label under the windscreen or a US/Canadian country version waits on the
Weryfikacja page for its origin market, and its page points to the auctions until a person decides."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_origin_hint.db")

import db
from app import app
from validation import north_american_equipment
from webapp.services.listings import _approve_listing

CAR, EUROPEAN = "5YM13EC08P9P39912", "WBS8M9C53J5L01183"

US_BUILD_SHEET = ("S655 Tuner satelitarny\nS688 System dźwięku przestrzennego Harman/Kardon\n"
                  "S8SM Numer identyfikacyjny samochodu widoczny z zewnątrz")


class TestEquipment(unittest.TestCase):
    def test_north_american_options_are_found(self):
        market, why = north_american_equipment(US_BUILD_SHEET)
        self.assertEqual(market, "USA")
        self.assertEqual(len(why), 2)
        self.assertEqual(north_american_equipment("S838 Wersja krajowa (Kanada)\nS655 Tuner satelitarny")[0], "Kanada")
        self.assertEqual(north_american_equipment("494 U.S. VERSION\n461 INSTRUMENT WITH MILES")[0], "USA")
        self.assertEqual(north_american_equipment("W wyposażeniu radio satelitarne")[0], "USA")

    def test_european_equipment_is_not_taken_for_it(self):
        for text in ("System nawigacji satelitarnej, radio DAB+", "S0654 Radio cyfrowe DAB+, salon Polska",
                     "Usługi BMW ConnectedDrive", "", None):
            self.assertEqual(north_american_equipment(text), (None, []), text)


class TestOriginHint(unittest.TestCase):
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

    def approve_ad(self, vin, sid, description, origin=None):
        """An ad approved as the review queue does, with the scraper's origin market."""
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, source_url, status, vin, make, model, "
                     "origin_market, raw_description) VALUES ('autoplac', ?, ?, 'pending', ?, 'BMW', 'X3', ?, ?)",
                     (sid, f"https://autoplac.pl/oferta/{sid}", vin, origin, description))
        ad = conn.execute("SELECT * FROM pending_listings WHERE source_listing_id = ?", (sid,)).fetchone()
        _approve_listing(conn, ad, overrides={"vin": vin})   # overrides: no fetch of the ad's page
        conn.commit()
        conn.close()

    def car(self, vin=CAR):
        conn = db.get_db()
        row = dict(conn.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,)).fetchone())
        conn.close()
        return row

    def test_an_undeclared_import_waits_for_its_market_and_points_to_the_auctions(self):
        self.approve_ad(CAR, "1", "Przedstawiamy ofertę:\n" + US_BUILD_SHEET)
        self.assertEqual(self.car()["origin_hint_market"], "USA")
        self.assertIn(CAR, self.client.get("/verify?issue=origin").get_data(as_text=True))
        page = self.client.get(f"/vehicle/{CAR}").get_data(as_text=True)
        self.assertIn("Najpewniej import z Ameryki Północnej", page)
        panel = self.client.get(f"/vehicle/{CAR}/to_check").get_data(as_text=True)
        self.assertIn("Ustaw: USA", panel)
        self.assertIn("tuner satelitarny", panel)

        self.client.post(f"/review/origins/{CAR}", data={"market": "USA"}, headers={"HX-Request": "true"})
        self.assertNotIn(CAR, self.client.get("/verify?issue=origin").get_data(as_text=True))
        self.assertIn(CAR, self.client.get("/verify?issue=damage").get_data(as_text=True))   # now: look for the damage
        self.assertIn("Auto z Ameryki Północnej", self.client.get(f"/vehicle/{CAR}").get_data(as_text=True))

    def test_keeping_a_european_market_ends_the_hint(self):
        self.approve_ad(CAR, "1", US_BUILD_SHEET, origin="Europa")
        self.client.post(f"/review/origins/{CAR}", data={"market": "Europa"}, headers={"HX-Request": "true"})
        self.assertNotIn(CAR, self.client.get("/verify?issue=origin").get_data(as_text=True))
        self.assertNotIn("Najpewniej import", self.client.get(f"/vehicle/{CAR}").get_data(as_text=True))

    def test_a_car_already_north_american_or_without_such_equipment_is_not_flagged(self):
        self.approve_ad(CAR, "1", US_BUILD_SHEET, origin="USA")
        self.approve_ad(EUROPEAN, "2", "Salon Polska, radio DAB+, nawigacja satelitarna")
        page = self.client.get("/verify?issue=origin").get_data(as_text=True)
        self.assertNotIn(CAR, page)
        self.assertNotIn(EUROPEAN, page)
        self.assertIsNone(self.car(EUROPEAN)["origin_hint_market"])


if __name__ == "__main__":
    unittest.main()
