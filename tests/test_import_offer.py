"""Brokers' import offers (a car still at an auction abroad, priced at an estimate) are kept and
left out of the market data."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"

import db
from app import app
from validation import is_import_offer

TOKEN = {"Authorization": "Bearer test-token"}
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_import_offer.db")
OFFER = ("Samochód dostępny do zakupu i importu z licytacji firmy ubezpieczeniowej w USA. "
         "Podana cena jest szacunkiem z cłem i transportem.")


class TestIsImportOffer(unittest.TestCase):
    def test_broker_templates(self):
        for text in [
            OFFER,
            "#### 2016 BMW M3 - **Oferta licytacji / sprowadzenie z USA** Na sprzedaż oferujemy BMW M3",
            "Szkoda opisana jako uszkodzenie przodu. Szacowana cena z transportem pod dom 89000zł!",
            "Ten egzemplarz będzie licytowany w USA 19.10.2026. Szacowana cena zakupu: 124 500 zł",
            "Podana kwota zawiera: \\- Cena za którą zakupimy samochód na licytacji wraz z kosztami aukcyjnymi",
            "Ocena na karcie aukcyjnej: 4.5/B Szacowany koszt zakupu i importu z Japonii wraz z transportem",
            "--- AUTA CAŁE I USZKODZONE --- Prezentowany pojazd jest propozycją do sprowadzenia z USA lub Kanady.",
            "KUP AUTO NAWET DO 40% TANIEJ! Samochód dostępny do zakupu i bezpośredniego importu od dealera w Korei.",
            "-- AMER-POL -- Auto do wylicytowania i sprowadzenia z aukcji firmy ubezpieczeniowej w USA.",
        ]:
            self.assertTrue(is_import_offer("BMW", text), text)

    def test_cars_already_in_poland(self):
        for text in [
            "Samochód sprowadzony z USA niegroźnie uszkodzony (zdjęcia z aukcji oraz raport do wglądu).",
            "Zakupiony na aukcji w Japonii z oceną aukcyjną 4,5 B. Samochód bezwypadkowy.",
            "Kupiłem je w 2023 roku na licytacji od ubezpieczyciela, naprawiłem i do tej pory jeździłem.",
            "PKO Leasing S.A. przeprowadza transakcje poprzez swój portal: aukcje.pkoleasing.pl",
            "Nie pochodzi z aukcji samochodów uszkodzonych. Posiada czysty raport Carfax.",
            "", None,
        ]:
            self.assertFalse(is_import_offer("BMW", text), text)


class TestImportOfferSightings(unittest.TestCase):
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

    def ingest(self, sid, vin, text):
        r = self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "autoplac", "source_listing_id": sid, "make": "BMW", "model": "M2", "variant": "G87",
            "vin": vin, "vin_confidence": "found_in_schema", "price_pln": 170000, "raw_title": "BMW M2",
            "raw_description": text})
        return r.get_json()

    def query(self, sql, *args):
        conn = db.get_db()
        rows = [tuple(r) for r in conn.execute(sql, args).fetchall()]
        conn.close()
        return rows

    def test_offer_is_flagged_and_its_sightings_excluded(self):
        offer = self.ingest("offer", "WBS11HP0X0CR00001", OFFER)
        plain = self.ingest("plain", "WBS11HP0X0CR00002", "Polski salon, stan idealny.")
        self.assertEqual(self.query("SELECT source_listing_id, import_offer FROM pending_listings ORDER BY id"),
                         [("offer", 1), ("plain", 0)])
        queue = self.client.get("/review").get_data(as_text=True)
        self.assertEqual(queue.count(">Do sprowadzenia</span>"), 1)
        for listing in (offer, plain):
            self.client.post(f"/review/{listing['id']}/approve", data={})
        self.assertEqual(self.query("SELECT source_listing_id, excluded_reason FROM listing_observations ORDER BY source_listing_id"),
                         [("offer", "import_offer"), ("plain", None)])
        # A second ad of a known car arrives as an import offer: its sighting is excluded too
        self.ingest("offer2", "WBS11HP0X0CR00002", OFFER)
        self.assertEqual(self.query("SELECT excluded_reason FROM listing_observations WHERE source_listing_id = 'offer2'"),
                         [("import_offer",)])
        # The VIN base lists both; the offer is marked, out of the market data
        html = self.client.get("/vehicles").get_data(as_text=True)
        self.assertIn("WBS11HP0X0CR00002", html)
        self.assertIn("WBS11HP0X0CR00001", html)
        self.assertEqual(html.count(">Do sprowadzenia</span>"), 1)
        self.assertEqual(self.client.get("/vehicle/WBS11HP0X0CR00001").status_code, 200)

    def test_migration_flags_ads_already_stored(self):
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, raw_description, status, make, model) "
                     "VALUES ('autoplac', 'old', ?, 'approved', 'BMW', 'M2')", (OFFER,))
        conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES ('WBS11HP0X0CR00003', 'BMW', 'M2', 2024)")
        conn.execute("INSERT INTO listing_observations (vin, source, source_listing_id, price_pln) "
                     "VALUES ('WBS11HP0X0CR00003', 'autoplac', 'old', 170000)")
        conn.execute("UPDATE pending_listings SET import_offer = 0")
        conn.execute("UPDATE listing_observations SET excluded_reason = NULL")
        conn.execute("DELETE FROM schema_migrations WHERE version = 26")
        conn.commit()
        conn.close()
        db.init_db()
        self.assertEqual(self.query("SELECT import_offer FROM pending_listings WHERE source_listing_id = 'old'"), [(1,)])
        self.assertEqual(self.query("SELECT excluded_reason FROM listing_observations WHERE source_listing_id = 'old'"),
                         [("import_offer",)])


if __name__ == "__main__":
    unittest.main()
