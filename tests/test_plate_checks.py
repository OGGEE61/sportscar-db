"""CEPiK checks of the pending /plates cards: which plate and date pairs are asked (the Polish plate
rules' readings, the car's dates), what an answer does, the VPS job's API, the hints on the card and
the "Niezgodne z CEPiK" marker."""
import importlib
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(ROOT, "tests", "test_plate_checks.db")

import db
from app import app
from webapp.services.plates import (MAX_LOOKUPS_PER_CARD, plate_card_hints, plate_check_plan, plate_check_tasks,
                                    swapped_date)

TOKEN = {"Authorization": "Bearer test-token"}
OCR, AD, IMPORT = "WBS8M9C50J5K99001", "WBS8M9C50J5K99002", "WBS8M9C50J5K99003"


def report(vin, make="BMW", year=2018):
    return {"vin": vin, "identifying_feature": vin, "registration_plate": "KR7VG22", "first_registration_date": "2018-05-10",
            "make": make, "model": "M3", "year_of_manufacture": year, "type": "", "subtype": "",
            "registration_status": "zarejestrowany", "tech_inspection_status": "Aktualne", "tech_inspection_until": "2027-05-10",
            "has_current_oc": 1, "insurance_expiry_date": "2027-01-01", "is_stolen": 0, "total_owners": 2,
            "last_odometer_km": 88000, "last_odometer_date": "2026-05-01", "odometer_history_json": "[]", "events_json": "[]"}


class PlateCheckCase(unittest.TestCase):
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
        # OCR: a photo reading with a Z where only a 2 can be, and two dates in its ads.
        # AD: a plate from the ad CEPiK did not find, sent back to /plates. IMPORT: a car from the USA
        # whose ad date is years after its model year, on a plate that cannot be Polish.
        cars = ((OCR, None, "2018-05-10", None, "KR7VG2Z", 0.8), (AD, "WA12345", "2019-01-02", "Polska", "WA12345", 0),
                (IMPORT, "8ZY5033", "2023-03-01", "USA", "8ZY5033", 0))
        for vin, plate, date, origin, reading, conf in cars:
            conn.execute("INSERT INTO vehicles (vin, make, model, year, registration_plate, first_registration_date, "
                         "origin_market) VALUES (?, 'BMW', 'M3', 2018, ?, ?, ?)", (vin, plate, date, origin))
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, first_registration_date) "
                         "VALUES ('otomoto', ?, 'approved', ?, ?)", (vin[-3:], vin, date))
            conn.execute("INSERT INTO plate_review_queue (vin, detected_plate, confidence, status) VALUES (?, ?, ?, 'pending')",
                         (vin, reading, conf))
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, first_registration_date) "
                     "VALUES ('olx', '9', 'approved', ?, '2018-06-01')", (OCR,))
        conn.execute("INSERT INTO cepik_sync_log (vin, status, message) VALUES (?, 'not_found', 'Pojazd nie odnaleziony')", (AD,))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def plan(self):
        conn = db.get_db()
        plan = {c["vin"]: c for c in plate_check_plan(conn).values()}
        conn.close()
        return plan

    def card_id(self, vin):
        conn = db.get_db()
        cid = conn.execute("SELECT id FROM plate_review_queue WHERE vin = ?", (vin,)).fetchone()[0]
        conn.close()
        return cid

    def result(self, vin, plate, date, **body):
        return self.client.post("/api/plate_check_result", headers=TOKEN, json={
            "card_id": self.card_id(vin), "vin": vin, "plate": plate, "first_registration_date": date, **body})


class TestPlan(PlateCheckCase):
    def test_pairs_are_the_rules_readings_with_the_cars_dates_likeliest_first(self):
        ocr = self.plan()[OCR]
        self.assertEqual(ocr["plates"], ["KR7VG22", "KR7V622"])
        self.assertEqual(ocr["dates"], ["2018-05-10", "2018-06-01"])
        # then the swapped day and month of 2018-05-10, last (2018-06-01 has none: the 1st is often a month alone)
        self.assertEqual(ocr["todo"], [("KR7VG22", "2018-05-10"), ("KR7VG22", "2018-06-01"), ("KR7V622", "2018-05-10"),
                                       ("KR7V622", "2018-06-01"), ("KR7VG22", "2018-10-05"), ("KR7V622", "2018-10-05")])

    def test_a_date_is_swapped_only_when_it_can_be_read_both_ways(self):
        self.assertEqual(swapped_date("2019-01-03"), "2019-03-01")
        self.assertIsNone(swapped_date("2019-03-13"))       # no 13th month
        self.assertIsNone(swapped_date("2019-04-04"))       # the same date
        self.assertIsNone(swapped_date("2020-02-01"))       # most likely only the month
        self.assertIsNone(swapped_date("2099-11-12"))       # 2099-12-11 is in the future

    def test_a_pair_the_nightly_car_check_missed_is_not_asked_again(self):
        from scripts.fetch_cepik import record_cepik_failure
        conn = db.get_db()
        record_cepik_failure(conn, mock.Mock(last_status=404), AD, "WA12345")
        conn.close()
        self.assertEqual(self.plan()[AD]["asked"], [("WA12345", "2019-01-02")])
        self.assertNotIn(("WA12345", "2019-01-02"), self.plan()[AD]["todo"])

    def test_a_plate_that_cannot_be_polish_is_not_asked(self):
        self.assertEqual(self.plan()[IMPORT]["todo"], [])

    def test_tasks_give_every_card_its_first_pair_before_any_second(self):
        conn = db.get_db()
        tasks = plate_check_tasks(conn, 10)
        conn.close()
        self.assertEqual([(t["vin"], t["plate"]) for t in tasks[:2]], [(OCR, "KR7VG22"), (AD, "WA12345")])
        self.assertLessEqual(len(tasks), 2 * MAX_LOOKUPS_PER_CARD)


class TestApi(PlateCheckCase):
    def test_needs_the_token(self):
        os.environ["ADMIN_PASSWORD"] = "secret"
        self.assertEqual(self.client.post("/api/plate_check_queue", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/plate_check_result", json={}).status_code, 401)

    def test_queue_hands_out_the_tasks(self):
        checks = self.client.post("/api/plate_check_queue", headers=TOKEN, json={"limit": 1}).get_json()["checks"]
        self.assertEqual(checks, [{"card_id": self.card_id(OCR), "vin": OCR, "plate": "KR7VG22",
                                   "first_registration_date": "2018-05-10"}])

    def test_a_confirmed_pair_approves_the_card_and_takes_the_date(self):
        r = self.result(OCR, "KR7VG22", "2018-06-01", report=report(OCR), http_status=200)
        self.assertEqual(r.get_json(), {"outcome": "confirmed"})
        conn = db.get_db()
        car = conn.execute("SELECT registration_plate, first_registration_date FROM vehicles WHERE vin = ?", (OCR,)).fetchone()
        card = conn.execute("SELECT status, reviewed_plate FROM plate_review_queue WHERE vin = ?", (OCR,)).fetchone()
        log = conn.execute("SELECT status FROM cepik_sync_log WHERE vin = ?", (OCR,)).fetchone()
        conn.close()
        self.assertEqual((car["registration_plate"], car["first_registration_date"]), ("KR7VG22", "2018-06-01"))
        self.assertEqual((card["status"], card["reviewed_plate"], log["status"]), ("approved", "KR7VG22", "success"))
        self.assertNotIn(OCR, self.plan())
        self.assertEqual(self.result(OCR, "KR7V622", "2018-05-10", report=None, http_status=404).get_json(), {"outcome": "gone"})

    def test_a_miss_is_not_asked_again_and_a_timeout_is(self):
        self.assertEqual(self.result(OCR, "KR7VG22", "2018-05-10", report=None, http_status=404).get_json()["outcome"], "not_found")
        self.assertEqual(self.result(OCR, "KR7V622", "2018-05-10", report=None, http_status=None).get_json()["outcome"], "error")
        plan = self.plan()[OCR]
        self.assertEqual(plan["asked"], [("KR7VG22", "2018-05-10")])
        self.assertIn(("KR7V622", "2018-05-10"), plan["todo"])

    def test_another_car_in_the_answer_is_not_approved(self):
        r = self.result(OCR, "KR7VG22", "2018-05-10", report=report(OCR, make="AUDI"), http_status=200)
        self.assertEqual(r.get_json()["outcome"], "other_car")
        self.assertEqual(self.plan()[OCR]["asked"], [("KR7VG22", "2018-05-10")])

    def test_bad_input_is_refused(self):
        self.assertEqual(self.result(OCR, "8ZY5033", "2018-05-10").status_code, 400)
        self.assertEqual(self.result(OCR, "KR7VG22", "jutro").status_code, 400)
        self.assertEqual(self.result(OCR, "KR7VG22", "2018-05-10", report=report(AD)).status_code, 400)


class TestJob(PlateCheckCase):
    def test_the_nightly_job_asks_and_skips_a_confirmed_cards_other_pairs(self):
        job = importlib.import_module("scripts.maintenance.cepik_remote")
        client = mock.Mock(last_status=404)
        client.fetch_vehicle_data.side_effect = lambda vin, plate, date: report(vin) if (plate, date) == ("KR7VG22", "2018-05-10") else None

        def post(path, payload):
            r = self.client.post(path, headers=TOKEN, json=payload)
            return r.get_json()
        with mock.patch.object(job, "fetch_queue", return_value=[]), mock.patch.object(job, "post", side_effect=post):
            counts = job.run(60, client=client, pause=0, plate_limit=20)
        self.assertEqual(counts["plates_confirmed"], 1)
        asked = [c.args[1:] for c in client.fetch_vehicle_data.call_args_list]
        self.assertEqual(asked.count(("KR7VG22", "2018-05-10")), 1)
        self.assertNotIn(("KR7V622", "2018-05-10"), asked)     # its card was approved already


class TestHints(PlateCheckCase):
    def test_hints_name_the_suspect_data(self):
        plan = self.plan()
        imp = " ".join(plate_card_hints(plan[IMPORT]))
        self.assertIn("8ZY5033 nie ma formatu polskiej tablicy", imp)
        self.assertIn("Auto sprowadzone (USA)", imp)
        ocr = " ".join(plate_card_hints(plan[OCR]))
        self.assertIn("różne daty pierwszej rejestracji: 2018-05-10, 2018-06-01", ocr)
        self.assertIn("Czeka na automatyczne sprawdzenie w CEPiK: 6 kombinacji", ocr)
        self.assertNotIn("sam rok", ocr)
        conn = db.get_db()
        conn.execute("UPDATE vehicles SET first_registration_date = '2018-01-01' WHERE vin = ?", (OCR,))
        conn.commit()
        conn.close()
        self.assertIn("Data 2018-01-01 to najpewniej sam rok z ogłoszenia", " ".join(plate_card_hints(self.plan()[OCR])))

    def test_the_card_shows_hints_and_the_corrected_reading(self):
        page = self.client.get("/plates").get_data(as_text=True)
        self.assertIn('value="KR7VG22"', page)
        self.assertIn("poprawiony według reguł polskich tablic", page)
        self.assertIn("Do wyjaśnienia: CEPiK nie potwierdził tych danych", page)
        self.assertLess(page.index(IMPORT), page.index(OCR))      # nothing left to try: first

    def test_cards_show_the_car_id_and_are_found_by_it(self):
        conn = db.get_db()
        car_id = conn.execute("SELECT car_id FROM vehicles WHERE vin = ?", (AD,)).fetchone()[0]
        conn.close()
        page = self.client.get("/plates").get_data(as_text=True)
        self.assertIn(f"#{car_id}</span>", page)
        self.assertGreaterEqual(page.count(f'href="/vehicle/{AD}"'), 2)       # the title and "Strona auta"
        for q in (f"%23{car_id}", str(car_id), AD[-6:], "wa12345"):
            page = self.client.get(f"/plates?q={q}").get_data(as_text=True)
            self.assertIn(AD, page, q)
            self.assertNotIn(OCR, page, q)

    def test_a_car_cepik_did_not_find_is_marked_everywhere(self):
        self.assertIn("Niezgodne z CEPiK", self.client.get(f"/vehicle/{AD}").get_data(as_text=True))
        self.assertNotIn("Niezgodne z CEPiK", self.client.get(f"/vehicle/{OCR}").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
