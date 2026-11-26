"""The ad's "Zarejestrowany w Polsce" and "Pierwszy właściciel" (migration 34): read from otomoto and
autoplac, stored with the listing, and used by the /plates queue. Only a yes is sure (otomoto leaves an
unticked field out, autoplac shows it as "Nie"), so a no marks a card and puts it last, never drops it."""
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_registered_field.db")

import base_scraper
import db
from app import app
from validation import yes_no
from webapp.blueprints.plates import plate_cards

OTOMOTO = "https://www.otomoto.pl/osobowe/oferta/x-ID1.html"
AUTOPLAC = "https://autoplac.pl/oferta/bmw/m2/abc-NH"


def otomoto(**params):
    pd = {k: {"label": k, "values": [{"value": v, "label": "Tak" if v == "1" else "Nie"}]} for k, v in params.items()}
    nd = {"props": {"pageProps": {"advert": {"price": {"value": "1", "currency": "PLN"}, "description": "x",
                                              "parametersDict": pd}}}}
    return base_scraper.parse_detail(f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>', OTOMOTO)


def autoplac(**offer):
    state = {f"{base_scraper.AUTOPLAC_API}offer/abc-NH": {"body": {"offer": offer}}}
    return base_scraper.parse_detail(f'<script id="ng-state" type="application/json">{json.dumps(state)}</script>', AUTOPLAC)


class TestReading(unittest.TestCase):
    def test_yes_no(self):
        self.assertEqual([yes_no(v) for v in ("1", 1, True, "0", 0, False, None, "", "Tak")], [1, 1, 1, 0, 0, 0, None, None, None])

    def test_otomoto(self):
        d = otomoto(registered="1", original_owner="1")
        self.assertEqual((d["registered_in_pl"], d["first_owner"]), (1, 1))
        self.assertEqual(otomoto(has_registration="1")["registered_in_pl"], 1)      # a registration number given
        self.assertEqual(otomoto(registered="0", original_owner="0")["registered_in_pl"], 0)
        d = otomoto()                                                                # unticked: left out
        self.assertEqual((d["registered_in_pl"], d["first_owner"]), (None, None))

    def test_autoplac(self):
        d = autoplac(registered=True, firstOwner=False)
        self.assertEqual((d["registered_in_pl"], d["first_owner"]), (1, 0))
        self.assertEqual(autoplac(title="BMW M2")["registered_in_pl"], None)


class TestStoredAndQueued(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        app.config["TESTING"] = True
        self.client = app.test_client()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        os.environ.pop("API_TOKEN", None)
        os.environ.pop("ADMIN_PASSWORD", None)
        self.addCleanup(patcher.stop)

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def ingest(self, sid, **fields):
        r = self.client.post("/api/ingest_pending", json={"source": "autoplac", "source_listing_id": sid, "make": "BMW",
                                                           "model": "M3", **fields})
        self.assertEqual(r.status_code, 200)

    def listing(self, sid):
        conn = db.get_db()
        row = conn.execute("SELECT registered_in_pl, first_owner FROM pending_listings WHERE source_listing_id = ?",
                           (sid,)).fetchone()
        conn.close()
        return tuple(row)

    def test_the_ingest_stores_it_and_a_later_sighting_fills_it_in(self):
        self.ingest("1", registered_in_pl=0, first_owner=1)
        self.assertEqual(self.listing("1"), (0, 1))
        self.ingest("2")
        self.assertEqual(self.listing("2"), (None, None))
        self.ingest("2", registered_in_pl=1)
        self.assertEqual(self.listing("2"), (1, None))

    def test_registered_cards_come_first_not_registered_last_with_a_hint(self):
        conn = db.get_db()
        for vin, registered in (("WBS00000000000001", 0), ("WBS00000000000002", None), ("WBS00000000000003", 1)):
            conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES (?, 'BMW', 'M3', 2018)", (vin,))
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, registered_in_pl) "
                         "VALUES ('autoplac', ?, 'approved', ?, ?)", (vin[-1], vin, registered))
            conn.execute("INSERT INTO plate_review_queue (vin, detected_plate, status) VALUES (?, '', 'pending')", (vin,))
        conn.commit()
        cards = plate_cards(conn, "pending")
        conn.close()
        self.assertEqual([c["vin"][-1] for c in cards], ["3", "2", "1"])
        self.assertIn("zarejestrowany w Polsce", cards[0]["hints"][0])
        self.assertIn("niezarejestrowany w Polsce", cards[2]["hints"][0])
        self.assertFalse(any("rejestrowany" in h for h in cards[1]["hints"]))
        panel = self.client.get("/vehicle/WBS00000000000001/to_check").get_data(as_text=True)
        self.assertIn("niezarejestrowany w Polsce", panel)


if __name__ == "__main__":
    unittest.main()
