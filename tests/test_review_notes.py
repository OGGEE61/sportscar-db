"""The 'Do sprawdzenia' page (/review/notes): notes on cars a review left uncertain, added through the
review MCP server and ticked off on the page."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_review_notes.db")

import db
from app import app
from scripts import review_mcp as mcp_server
from webapp.services import verification

CAR, OTHER = "WDB4633221X147089", "WBSTS01000LS73520"
AD = "https://www.otomoto.pl/osobowe/oferta/mercedes-benz-klasa-g-ID6IgS3k.html"


class TestReviewNotes(unittest.TestCase):
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
        for vin, model in ((CAR, "Klasa G"), (OTHER, "X3 M")):
            conn.execute("INSERT INTO vehicles (vin, make, model, year) VALUES (?, 'Test', ?, 2004)", (vin, model))
        conn.commit()
        self.car_id = conn.execute("SELECT car_id FROM vehicles WHERE vin = ?", (CAR,)).fetchone()[0]
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def notes(self, resolved=False):
        conn = db.get_db()
        try:
            return verification.review_notes(conn, resolved=resolved)
        finally:
            conn.close()

    def test_notes_and_origin_conflicts_are_tabs_of_one_page(self):
        conn = db.get_db()
        verification.add_review_note(conn, CAR, "plate", "SK1K663, CEPiK: brak")
        conn.execute("UPDATE vehicles SET ai_conflict = 1 WHERE vin = ?", (OTHER,))
        conn.commit()
        conn.close()
        for url in ("/review/notes", "/review/origins"):
            page = self.client.get(url).get_data(as_text=True)
            self.assertIn("<h2 class=\"mb-0\">Do sprawdzenia</h2>", page)
            self.assertIn('Notatki <span class="badge bg-secondary">1</span>', page)
            self.assertIn('id="origin-conflict-count">1</span>', page)

    def test_the_mcp_server_notes_a_car_by_its_id_and_a_second_note_replaces_the_first(self):
        self.assertIn("Zapisano", mcp_server.add_review_note(f"#{self.car_id}", "plate", "SK1K663, CEPiK: brak", AD))
        self.assertIn("Zapisano", mcp_server.add_review_note(CAR, "plate", "SK1K663, potrzebna data za granicą"))
        notes = self.notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes[0]["note"], notes[0]["ad_url"]), ("SK1K663, potrzebna data za granicą", AD))
        # Another topic is another note
        mcp_server.add_review_note(CAR, "damage", "Import z Kanady: szukać aukcji")
        self.assertEqual(len(self.notes()), 2)

    def test_the_mcp_server_refuses_an_unknown_car_or_topic(self):
        self.assertIn("Nie ma auta", mcp_server.add_review_note("#999999", "plate", "x"))
        self.assertIn("Nieznany temat", mcp_server.add_review_note(CAR, "colour", "x"))
        self.assertIn("Opisz", mcp_server.add_review_note(CAR, "plate", "  "))
        self.assertEqual(self.notes(), [])

    def test_the_page_lists_open_notes_and_ticking_one_off_moves_it(self):
        mcp_server.add_review_note(CAR, "plate", "Tablica SK1K663 wyraźna", AD)
        page = self.client.get("/review/notes").get_data(as_text=True)
        self.assertIn(f"#{self.car_id}", page)
        self.assertIn("Tablica SK1K663 wyraźna", page)
        self.assertIn(f'href="/vehicle/{CAR}"', page)
        self.assertIn(AD, page)
        note_id = self.notes()[0]["id"]

        res = self.client.post(f"/review/notes/{note_id}", data={"resolved": "1"}, headers={"HX-Request": "true"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.notes(), [])
        self.assertNotIn("SK1K663", self.client.get("/review/notes").get_data(as_text=True))
        self.assertIn("SK1K663", self.client.get("/review/notes?status=resolved").get_data(as_text=True))

        # A new note on the same topic opens; the old one cannot be reopened next to it
        mcp_server.add_review_note(CAR, "plate", "Nowa tablica")
        self.assertEqual(self.client.post(f"/review/notes/{note_id}", data={"resolved": "0"}).status_code, 409)
        res = self.client.post("/review/notes/999", data={"resolved": "1"})
        self.assertEqual((res.status_code, res.get_data(as_text=True)), (409, "Nie ma takiej notatki."))

    def test_list_review_notes_names_the_car_by_its_id(self):
        mcp_server.add_review_note(OTHER, "date", "Tylko „luty 2020”")
        listed = mcp_server.list_review_notes()
        self.assertIn('"vin": "%s"' % OTHER, listed)
        self.assertIn("luty 2020", listed)
        self.assertIn('"resolved_at": null', listed)

    def test_a_corrected_vin_keeps_its_notes(self):
        placeholder = "UNVERIFIED-TEST-1"
        conn = db.get_db()
        conn.execute("INSERT INTO vehicles (vin, make, model, year, vin_status) VALUES (?, 'Test', 'M3', 2017, 'placeholder')",
                     (placeholder,))
        conn.execute("INSERT INTO review_notes (vin, topic, note) VALUES (?, 'vin', 'VIN zamaskowany')", (placeholder,))
        conn.commit()
        conn.close()
        db.resolve_placeholder(placeholder, "WBS3R9C56HK712345")
        self.assertEqual([n["vin"] for n in self.notes()], ["WBS3R9C56HK712345"])


if __name__ == "__main__":
    unittest.main()
