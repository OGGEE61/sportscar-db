"""CEPiK reports fetched on the VPS: the app hands out the cars and stores what CEPiK answered."""
import os
import sys
import unittest
from unittest import mock

sys.path[:0] = [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrapers")]

os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_cepik_remote.db")

import db
from app import app

TOKEN = {"Authorization": "Bearer test-token"}
A, B, C = "WBS8M9C50J5K99001", "WBS8M9C50J5K99002", "WBS8M9C50J5K99003"


def report(vin, km=88000):
    return {"vin": vin, "registration_plate": "PO1234X", "first_registration_date": "2018-05-10",
            "make": "BMW", "model": "M3", "type": "", "subtype": "", "registration_status": "zarejestrowany",
            "tech_inspection_status": "Aktualne", "tech_inspection_until": "2027-05-10",
            "has_current_oc": 1, "insurance_expiry_date": "2027-01-01", "is_stolen": 0, "total_owners": 2,
            "last_odometer_km": km, "last_odometer_date": "2026-05-01",
            "odometer_history_json": "[]", "events_json": "[]"}


class TestCepikRemote(unittest.TestCase):
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
        for vin, plate, date in ((A, "PO1234X", "2018-05-10"), (B, "WA55555", "2019-01-02"), (C, None, "2019-01-02")):
            conn.execute("INSERT INTO vehicles (vin, make, model, variant, year, registration_plate, first_registration_date) "
                         "VALUES (?, 'BMW', 'M3', 'F80 M3', 2018, ?, ?)", (vin, plate, date))
        conn.commit()
        conn.close()

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def queue(self, **body):
        return [c["vin"] for c in self.client.post("/api/cepik_queue", headers=TOKEN, json=body).get_json()["cars"]]

    def result(self, vin, **body):
        return self.client.post("/api/cepik_result", headers=TOKEN, json={"vin": vin, "plate": "PO1234X", **body})

    def log(self, vin):
        conn = db.get_db()
        r = conn.execute("SELECT status FROM cepik_sync_log WHERE vin = ?", (vin,)).fetchone()
        conn.close()
        return r["status"] if r else None

    def test_needs_the_token(self):
        os.environ["ADMIN_PASSWORD"] = "secret"
        self.assertEqual(self.client.post("/api/cepik_queue", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/cepik_result", json={"vin": A}).status_code, 401)
        self.assertEqual(self.client.post("/api/cepik_queue", headers=TOKEN, json={}).status_code, 200)

    def test_queue_lists_cars_with_plate_and_date_and_no_report(self):
        self.assertEqual(self.queue(), [A, B])               # C has no plate
        self.assertEqual(self.queue(limit=1), [A])
        cars = self.client.post("/api/cepik_queue", headers=TOKEN, json={}).get_json()["cars"]
        self.assertEqual(cars[0], {"vin": A, "plate": "PO1234X", "first_registration_date": "2018-05-10",
                                   "make": "BMW", "model": "M3"})

    def test_report_is_saved_and_the_car_leaves_the_queue(self):
        self.assertEqual(self.result(A, report=report(A)).get_json(), {"outcome": "saved"})
        conn = db.get_db()
        row = conn.execute("SELECT last_odometer_km, total_owners FROM cepik_reports WHERE vin = ?", (A,)).fetchone()
        conn.close()
        self.assertEqual((row["last_odometer_km"], row["total_owners"]), (88000, 2))
        self.assertEqual(self.log(A), "success")
        self.assertEqual(self.queue(), [B])

    def test_a_report_for_another_car_or_an_unknown_car_is_refused(self):
        self.assertEqual(self.result(A, report=report(B)).status_code, 400)
        self.assertEqual(self.result("WBS8M9C50J5K99999", report=report("WBS8M9C50J5K99999")).status_code, 404)
        self.assertEqual(self.result(A, report={"vin": A}).status_code, 400)      # incomplete report
        self.assertEqual(self.queue(), [A, B])

    def test_not_known_to_cepik_goes_to_plates_and_is_not_asked_again(self):
        outcome = self.result(A, report=None, http_status=404).get_json()["outcome"]
        self.assertIn(outcome, ("reverted", "queued"))
        self.assertEqual(self.log(A), "not_found")
        self.assertEqual(self.queue(), [B])

    def test_a_failed_lookup_is_retried_after_the_cars_never_tried(self):
        self.assertEqual(self.result(A, report=None, http_status=None).get_json(), {"outcome": "error"})
        self.assertEqual(self.log(A), "error")
        self.assertEqual(self.queue(), [B, A])


class TestCepikJob(unittest.TestCase):
    def setUp(self):
        import importlib
        self.job = importlib.import_module("scripts.maintenance.cepik_remote")

    def run_job(self, cars, answers, outcomes):
        client = mock.Mock()
        def fetch(vin, plate, date):
            rep, status = answers[vin]
            client.last_status = status
            return rep
        client.fetch_vehicle_data.side_effect = fetch
        sent = []
        with mock.patch.object(self.job, "fetch_queue", return_value=cars), \
             mock.patch.object(self.job, "send_result",
                               side_effect=lambda car, rep, status: sent.append((car["vin"], bool(rep), status)) or outcomes[car["vin"]]):
            return self.job.run(60, client=client, pause=0), sent

    def car(self, vin):
        return {"vin": vin, "plate": "PO1", "first_registration_date": "2018-05-10", "make": "BMW", "model": "M3"}

    def test_counts_each_outcome(self):
        counts, sent = self.run_job([self.car(A), self.car(B), self.car(C)],
                                    {A: (report(A), 200), B: (None, 404), C: (None, None)},
                                    {A: "saved", B: "reverted", C: "error"})
        self.assertEqual(counts, {"cars": 3, "saved": 1, "not_found": 1, "failed": 1, "stopped": False})
        self.assertEqual(sent, [(A, True, 200), (B, False, 404), (C, False, None)])

    def test_stops_when_cepik_does_not_answer(self):
        cars = [self.car(f"WBS8M9C50J5K9{i:04d}") for i in range(12)]
        counts, sent = self.run_job(cars, {c["vin"]: (None, None) for c in cars}, {c["vin"]: "error" for c in cars})
        self.assertTrue(counts["stopped"])
        self.assertEqual(len(sent), self.job.STOP_AFTER_FAILED)

    def test_a_404_between_timeouts_does_not_stop_it(self):
        cars = [self.car(f"WBS8M9C50J5K9{i:04d}") for i in range(8)]
        answers = {c["vin"]: ((None, 404) if i % 2 else (None, None)) for i, c in enumerate(cars)}
        counts, sent = self.run_job(cars, answers, {c["vin"]: "error" for c in cars})
        self.assertFalse(counts["stopped"])
        self.assertEqual(len(sent), 8)


if __name__ == "__main__":
    unittest.main()
