"""The review MCP server (scripts/review_mcp.py): what it shows of the /plates cards, that a CEPiK
lookup through it approves like the nightly job, and that its decisions are the screens' own."""
import base64
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_review_mcp.db")

from PIL import Image as PILImage

import db
from mcp.server.mcpserver import Image
from scripts import review_mcp as mcp_server

KNOWN, FOREIGN = "WBS8M9C50J5K99001", "WBS8M9C50J5K99002"


def jpeg(size=(2000, 1000)):
    out = io.BytesIO()
    PILImage.new("RGB", size, "white").save(out, "JPEG")
    return out.getvalue()


def report(vin):
    return {"vin": vin, "identifying_feature": vin, "registration_plate": "KR7VG22", "first_registration_date": "2018-05-10",
            "make": "BMW", "model": "M3", "year_of_manufacture": 2018, "type": "", "subtype": "",
            "registration_status": "zarejestrowany", "tech_inspection_status": "Aktualne", "tech_inspection_until": "2027-05-10",
            "has_current_oc": 1, "insurance_expiry_date": "2027-01-01", "is_stolen": 0, "total_owners": 2,
            "last_odometer_km": 88000, "last_odometer_date": "2026-05-01", "odometer_history_json": "[]", "events_json": "[]"}


class ReviewMcpCase(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        db.init_db()
        mcp_server._cepik = None
        conn = db.get_db()
        crop = "data:image/jpeg;base64," + base64.b64encode(jpeg((120, 30))).decode()
        # KNOWN: a Polish reading with a Z where only a 2 can be. FOREIGN: an American plate, an import.
        for vin, reading, date, origin, photos in ((KNOWN, "KR7VG2Z", "2018-05-10", "Polska", ["https://img/1", "https://img/2"]),
                                                   (FOREIGN, "8ZY5033", "2023-03-01", "USA", [])):
            conn.execute("INSERT INTO vehicles (vin, make, model, year, first_registration_date, origin_market) "
                         "VALUES (?, 'BMW', 'M3', 2018, ?, ?)", (vin, date, origin))
            lid = conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, raw_title, raw_description, "
                               "photos, first_registration_date) VALUES ('otomoto', ?, 'approved', ?, 'BMW M3', ?, ?, ?)",
                               (vin[-3:], vin, "Pierwsza rejestracja 10.05.2018 " + "x" * 5000, json.dumps(photos), date)).lastrowid
            conn.execute("INSERT INTO plate_review_queue (listing_id, vin, photo_url, crop_path, detected_plate, status) "
                         "VALUES (?, ?, ?, ?, ?, 'pending')", (lid, vin, photos[1] if photos else None, crop, reading))
        self.known, self.foreign = [r["id"] for r in conn.execute("SELECT id FROM plate_review_queue ORDER BY id")]
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def card(self, cid):
        conn = db.get_db()
        row = conn.execute("SELECT q.status, q.reviewed_plate, v.registration_plate FROM plate_review_queue q "
                           "JOIN vehicles v ON v.vin = q.vin WHERE q.id = ?", (cid,)).fetchone()
        conn.close()
        return tuple(row)

    def cepik(self, answer, status=200):
        client = mock.Mock(last_status=status)
        client.fetch_vehicle_data.return_value = answer
        return mock.patch("scripts.fetch_cepik.CepikClient", return_value=client), client


class TestCards(ReviewMcpCase):
    def test_list_gives_the_reading_its_correction_and_the_hints(self):
        listed = json.loads(mcp_server.list_plate_cards())
        self.assertEqual((listed["pending"], listed["needing_person"]), (2, 1))
        cards = {c["vin"]: c for c in listed["cards"]}
        self.assertEqual((cards[KNOWN]["photo_reading"], cards[KNOWN]["suggested_plate"]), ("KR7VG2Z", "KR7VG22"))
        self.assertGreater(cards[KNOWN]["cepik_lookups_left"], 0)
        self.assertTrue(any("nie pasuje do polskiej tablicy" in h for h in cards[FOREIGN]["hints"]))
        only = json.loads(mcp_server.list_plate_cards(only_needing_person=True))["cards"]
        self.assertEqual([c["vin"] for c in only], [FOREIGN])

    def test_show_gives_the_ad_the_crop_and_the_photos_plate_photo_first(self):
        fetched = []
        def get(url, **kw):
            fetched.append(url)
            if url.endswith("/1"):
                raise OSError("gone")
            return mock.Mock(content=jpeg(), raise_for_status=lambda: None)
        with mock.patch.object(mcp_server.requests, "get", side_effect=get):
            content = mcp_server.show_plate_card(self.known, photos=5)
        info = json.loads(content[0])
        self.assertTrue(info["ad"]["description"].startswith("Pierwsza rejestracja 10.05.2018"))
        self.assertLessEqual(len(info["ad"]["description"]), mcp_server.DESCRIPTION_CHARS + 1)
        self.assertEqual(fetched, ["https://img/2", "https://img/1"])
        images = [c for c in content if isinstance(c, Image)]
        self.assertEqual(len(images), 2)                       # the crop and the photo that downloaded
        self.assertLessEqual(max(PILImage.open(io.BytesIO(images[1].data)).size), mcp_server.PHOTO_SIDE)
        self.assertTrue(any("zdjęcie niedostępne" in c for c in content if isinstance(c, str)))

    def test_show_a_card_no_longer_pending(self):
        mcp_server.reject_plate(self.foreign)
        self.assertIn("nie czeka", mcp_server.show_plate_card(self.foreign)[0])


class TestCepik(ReviewMcpCase):
    def test_a_confirmed_lookup_approves_the_card(self):
        patch, client = self.cepik(report(KNOWN))
        with patch:
            answer = json.loads(mcp_server.check_plate_in_cepik(self.known, "kr 7vg22", "2018-05-10"))
        client.fetch_vehicle_data.assert_called_once_with(KNOWN, "KR7VG22", "2018-05-10")
        self.assertEqual(answer["report"]["total_owners"], 2)
        self.assertEqual(self.card(self.known), ("approved", "KR7VG22", "KR7VG22"))

    def test_a_miss_is_remembered_and_not_asked_again(self):
        patch, client = self.cepik(None, status=404)
        with patch:
            self.assertIn("nie zna", mcp_server.check_plate_in_cepik(self.known, "KR7VG22", "2018-05-10"))
            self.assertIn("już sprawdzane", mcp_server.check_plate_in_cepik(self.known, "KR7VG22", "2018-05-10"))
        self.assertEqual(client.fetch_vehicle_data.call_count, 1)
        self.assertEqual(self.card(self.known)[0], "pending")

    def test_no_lookup_for_a_foreign_plate_a_bad_date_or_a_reviewed_card(self):
        patch, client = self.cepik(report(FOREIGN))
        with patch:
            self.assertIn("nie jest polską", mcp_server.check_plate_in_cepik(self.foreign, "8ZY5033", "2018-05-10"))
            self.assertIn("Niepoprawna data", mcp_server.check_plate_in_cepik(self.known, "KR7VG22", "2018"))
            mcp_server.reject_plate(self.foreign)
            self.assertIn("nie czeka", mcp_server.check_plate_in_cepik(self.foreign, "KR7VG22", "2018-05-10"))
        client.fetch_vehicle_data.assert_not_called()


class TestDecisions(ReviewMcpCase):
    def test_approve_reject_and_undo_are_the_screens_own(self):
        self.assertEqual(json.loads(mcp_server.approve_plate(self.known, "KR7VG22"))["status"], "ok")
        self.assertEqual(self.card(self.known), ("approved", "KR7VG22", "KR7VG22"))
        mcp_server.undo_plate_review(self.known)
        self.assertEqual(self.card(self.known), ("pending", None, None))
        self.assertEqual(json.loads(mcp_server.approve_plate(self.known, "KRÓL1"))["status"], "error")
        mcp_server.reject_plate(self.known)
        self.assertEqual(self.card(self.known)[0], "rejected")

    def test_origin_conflicts_are_listed_and_decided(self):
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET ai_conflict = 1, ai_suggested_market = 'USA', ai_reasoning = 'Carfax' WHERE vin = ?", (KNOWN,))
        conn.commit()
        conn.close()
        listed = json.loads(mcp_server.list_origin_conflicts())
        self.assertEqual([(c["vin"], c["ai_suggested_market"]) for c in listed["cars"]], [(KNOWN, "USA")])
        self.assertEqual(mcp_server.set_origin_market(KNOWN, "Mars"), "Nieznany rynek")
        self.assertEqual(mcp_server.set_origin_market(KNOWN, "USA"), "Zapisano rynek: USA.")
        self.assertEqual(json.loads(mcp_server.list_origin_conflicts())["conflicts"], 0)


if __name__ == "__main__":
    unittest.main()
