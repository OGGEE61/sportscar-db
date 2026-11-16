"""Damage stated only in an ad's text: the car is marked damaged, and a wrong match can be dismissed."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_damage_text.db")

import db
from app import app
from validation import damage_in_text

TOKEN = {"Authorization": "Bearer test-token"}
VIN = "WBS8M9C50J5K99001"


class TestDamageInText(unittest.TestCase):
    def test_offered_as_damaged(self):
        for title, text in [
            ("BMW M 2 3.0 lekko uszkodzona", ""),
            ("BMW M3", "BMW M3 | 2016 | 3.0 | automat | Run & Drive Uszkodzenie auta: przód pojazdu. Szacunkowy koszt zakupu…"),
            ("BMW M2", "Dokument: Salvage Title Kluczyki: są VIN: 3MF13DM0XR8E63048 Numer lota: 123"),
            ("BMW M2", "Auto do zakupu i importu z licytacji firmy ubezpieczeniowej w USA."),
            ("BMW X3", "<p>Sprzedam auto mocno uszkodzone BMW X3 M40i pierwsza rej. 2023</p>"),
            ("BMW M3", "BMW E46 M3 Cabrio – auto do naprawy. Na sprzedaż oferuję…"),
            ("Audi RS3", "Świetna wersja. UWAGA: pojazd uszkodzony. 4 drzwi."),
            ("BMW M2", "Polski salon | FV VAT. Samochód uszkodzony. Na sprzedaż BMW M2 G87."),
            ("BMW M4", "Belka jest cała. Do naprawy blacharskiej tył oraz wymiana klapy."),
        ]:
            self.assertIsNotNone(damage_in_text(title, text), text or title)

    def test_not_damaged_or_repaired_long_ago(self):
        for title, text in [
            ("BMW M3 bezwypadkowy", "Samochód jest całkowicie bezwypadkowy, nie był uszkodzony ani malowany."),
            ("BMW M3 nieuszkodzony", "Stan idealny."),
            ("BMW M4", "Auto zostało kupione w USA. Samochód miał uszkodzony przód. W ramach naprawy wymieniono zderzak."),
            ("BMW M4", "Sprowadzony do Polski kilka lat temu jako pojazd uszkodzony, informacja jest jawna."),
            ("Mercedes GLA", "Funkcja automatycznego hamowania po kolizji, przycisk sport."),
            ("BMW M5", "Prześwietlone przez ASO, nie było nic do naprawy."),
            ("Audi R8", "Miał rozbity reflektor w pierwszym roku, wymieniony w ASO."),
            ("BMW M2", "Brak jakichkolwiek uszkodzeń, lakier oryginalny."),
            ("BMW M2", ""), (None, None),
        ]:
            self.assertIsNone(damage_in_text(title, text), text or title)


class TestDamageMarks(unittest.TestCase):
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

    def marks(self):
        conn = db.get_db()
        out = {r["source_listing_id"]: (r["reason"], r["dismissed"]) for r in conn.execute("SELECT * FROM damaged_listings")}
        conn.close()
        return out

    def ingest(self, sid, **extra):
        return self.client.post("/api/ingest_pending", headers=TOKEN, json={
            "source": "otomoto", "source_listing_id": sid, "make": "BMW", "model": "M3", "variant": "F80 M3",
            "vin": VIN, "vin_confidence": "found_in_schema", "price_pln": 90000, **extra})

    def add_car(self):
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, variant, year) VALUES (?, 'BMW', 'M3', 'F80 M3', 2016)", (VIN,))
        conn.commit()
        conn.close()

    def test_ingest_marks_by_portal_flag_or_text(self):
        self.ingest("flag", damaged=True, raw_description="Ładny egzemplarz.")
        self.ingest("text", raw_title="BMW M3", raw_description="Run & Drive. Uszkodzenie auta: przód pojazdu.")
        self.ingest("fine", raw_title="BMW M3", raw_description="Bezwypadkowy, nie był uszkodzony.")
        marks = self.marks()
        self.assertEqual(marks["flag"], ("portal", 0))
        self.assertTrue(marks["text"][0].startswith("text: "))
        self.assertIn("uszkodzenie auta", marks["text"][0])
        self.assertNotIn("fine", marks)

    def test_dismissed_mark_stays_dismissed_and_car_counts_again(self):
        self.add_car()
        self.ingest("text", raw_title="BMW M3 lekko uszkodzona", raw_description="")
        page = self.client.get(f"/vehicle/{VIN}").get_data(as_text=True)
        self.assertIn("z treści ogłoszenia", page)
        self.assertIn("Uszkodzony</span>", page)
        self.client.post(f"/vehicle/{VIN}/damage_mark", data={"dismissed": "1"})
        self.assertEqual(self.marks()["text"][1], 1)
        page = self.client.get(f"/vehicle/{VIN}").get_data(as_text=True)
        self.assertNotIn("Uszkodzony</span>", page)
        self.assertIn("Przywróć oznaczenie", page)
        self.ingest("text", raw_title="BMW M3 lekko uszkodzona", raw_description="")   # the next scrape
        self.assertEqual(self.marks()["text"][1], 1)
        self.client.post(f"/vehicle/{VIN}/damage_mark", data={"dismissed": "0"})
        self.assertIn("Uszkodzony</span>", self.client.get(f"/vehicle/{VIN}").get_data(as_text=True))

    def test_migration_checks_stored_listings_once(self):
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, raw_title, raw_description) "
                     "VALUES ('autoplac', 'a1', 'approved', 'BMW M2', 'Dokument: Salvage. Numer lota: 5')")
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, raw_title, raw_description) "
                     "VALUES ('autoplac', 'a2', 'approved', 'BMW M2', 'Bezwypadkowy.')")
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, raw_title, raw_description) "
                     "VALUES ('autoplac', 'a3', 'rejected', 'BMW M2 uszkodzony', '')")
        conn.execute("INSERT INTO damaged_listings (source, source_listing_id) VALUES ('otomoto', 'old')")
        conn.execute("DELETE FROM schema_migrations WHERE version = 23")
        conn.commit()
        conn.close()
        db.init_db()
        marks = self.marks()
        self.assertEqual(set(marks), {"a1", "old"})
        self.assertEqual(marks["old"], ("portal", 0))
        self.assertTrue(marks["a1"][0].startswith("text: "))


if __name__ == "__main__":
    unittest.main()
