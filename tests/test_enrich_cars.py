"""Bielik's analysis per car (enrich_with_bielik.py): one prompt for all of a car's ads, a copy of
the per-ad analysis when the car has one ad text, and the car page showing it."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_BACKEND"] = "sqlite"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_enrich_cars.db")

import db
import enrich_with_bielik as enrich
from app import app

SOLO, MULTI, DONE = "WBA00000000000001", "WBA00000000000002", "WBA00000000000003"


def ad(source, day, text, city="Łódź"):
    return {"source": source, "scraped_at": f"2026-11-{day:02d} 10:00:00", "raw_title": "BMW X3",
            "raw_description": text, "location_city": city}


class TestCarPrompt(unittest.TestCase):
    def test_one_ad_gets_exactly_the_per_ad_prompt(self):
        one = ad("otomoto", 20, "Polski salon, bezwypadkowy.")
        self.assertEqual(enrich.build_car_prompt([one], "BMW", "X3"),
                         enrich.build_prompt("BMW X3", one["raw_description"], "BMW", "X3", "Łódź"))

    def test_a_cross_post_with_the_same_text_counts_once(self):
        ads = [ad("otomoto", 20, "<p>Polski salon.</p>"), ad("olx", 19, "Polski  salon."), ad("autoplac", 1, "Z USA.")]
        self.assertEqual([a["source"] for a in enrich.distinct_ads(ads)], ["otomoto", "autoplac"])

    def test_several_ads_go_in_one_prompt_newest_first_within_the_budget(self):
        ads = [ad("otomoto", 20, "Sprowadzony z USA. " + "a" * 5000), ad("autoplac", 1, "Polski salon. " + "b" * 5000)]
        prompt = enrich.build_car_prompt(ads, "BMW", "X3")
        self.assertIn("jednego samochodu BMW X3", prompt)
        self.assertIn("Gdy ogłoszenia sobie przeczą", prompt)
        self.assertLess(prompt.index("Ogłoszenie 1 (otomoto, 2026-11-20)"), prompt.index("Ogłoszenie 2 (autoplac, 2026-11-01)"))
        self.assertLessEqual(prompt.count("a") + prompt.count("b"), enrich.CAR_TOTAL_CHARS + 200)


class TestEnrichCars(unittest.TestCase):
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
        for vin, origin in ((SOLO, None), (MULTI, "Polska"), (DONE, None)):
            conn.execute("INSERT INTO vehicles (vin, make, model, year, origin_market) VALUES (?, 'BMW', 'X3', 2019, ?)",
                         (vin, origin))
        rows = [  # vin, sid, status, scraped_at, text, per-ad summary
            (SOLO, "1", "approved", "2026-11-10", "Jedyny opis tego auta, polski salon.", None),
            (MULTI, "2", "approved", "2026-11-20", "Sprowadzony z USA, przebieg 140 tys.", None),
            (MULTI, "3", "approved", "2026-10-01", "Polski salon, przebieg 120 tys.", None),
            (MULTI, "4", "rejected", "2026-11-21", "Odrzucone ogłoszenie, nie bierze udziału.", None),
            (DONE, "5", "approved", "2026-11-10", "Opis już przeanalizowany przez Bielika.", "Gotowe podsumowanie."),
        ]
        for vin, sid, status, at, text, summary in rows:
            conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, scraped_at, raw_title, "
                         "raw_description, ai_summary, ai_suggested_market, ai_equipment, ai_processed_at) "
                         "VALUES ('otomoto', ?, ?, ?, ?, 'BMW X3', ?, ?, ?, ?, ?)",
                         (sid, status, vin, at, text, summary, "Polska" if summary else None,
                          json.dumps(["BOSE"]) if summary else None, at if summary else None))
        conn.commit()
        conn.close()
        self.prompts = []
        self.answer = {"summary": "Podsumowanie auta.", "origin_market": "USA", "origin_reasoning": "Sprowadzony z USA",
                       "key_equipment": ["Head-up"], "has_panoramic_roof": True, "interior_color": "czarny",
                       "interior_material": "skóra"}
        ask = mock.patch.object(enrich, "_ask", side_effect=lambda prompt, model_name=None: (
            self.prompts.append(prompt), enrich.clean_analysis(dict(self.answer)))[1])
        ask.start()
        self.addCleanup(ask.stop)
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    def tearDown(self):
        for suffix in ("", "-shm", "-wal"):
            if os.path.exists(TEST_DB_PATH + suffix):
                os.remove(TEST_DB_PATH + suffix)

    def run_cars(self):
        conn = db.get_db()
        enrich.enrich_cars(conn)
        cars = {r["vin"]: dict(r) for r in conn.execute("SELECT * FROM vehicles")}
        conn.close()
        return cars

    def test_each_car_is_analysed_once_from_all_its_ads(self):
        cars = self.run_cars()
        self.assertEqual(len(self.prompts), 2)                      # SOLO and MULTI; DONE is copied
        multi = next(p for p in self.prompts if "140 tys." in p)
        self.assertIn("120 tys.", multi)
        self.assertNotIn("Odrzucone ogłoszenie", multi)
        m = cars[MULTI]
        self.assertEqual((m["ai_summary"], m["ai_suggested_market"], m["ai_ad_count"], m["ai_conflict"]),
                         ("Podsumowanie auta.", "USA", 2, 1))       # Polska in the base, USA per Bielik
        self.assertEqual(json.loads(m["ai_equipment"]), ["Head-up", "Dach panoramiczny/szyberdach"])
        self.assertIsNone(m["color_int"])                           # not taken over a market conflict
        self.assertEqual(cars[SOLO]["color_int"], "czarny / skóra")

    def test_a_car_with_one_analysed_ad_text_gets_that_analysis_copied(self):
        cars = self.run_cars()
        self.assertFalse(any("już przeanalizowany" in p for p in self.prompts))
        self.assertEqual((cars[DONE]["ai_summary"], cars[DONE]["ai_suggested_market"]), ("Gotowe podsumowanie.", "Polska"))

    def test_only_cars_with_a_newer_ad_are_analysed_again(self):
        self.run_cars()
        self.assertEqual(enrich.cars_to_analyze(db.get_db()), [])
        conn = db.get_db()
        conn.execute("INSERT INTO pending_listings (source, source_listing_id, status, vin, scraped_at, raw_description) "
                     "VALUES ('olx', '9', 'approved', ?, '2099-01-01 00:00:00', 'Nowe ogłoszenie z innym opisem auta.')", (MULTI,))
        conn.commit()
        self.assertEqual([c["vin"] for c in enrich.cars_to_analyze(conn)], [MULTI])
        conn.close()

    def test_it_stops_after_errors_in_a_row(self):
        with mock.patch.object(enrich, "_ask", side_effect=RuntimeError("Ollama down")) as ask, \
                mock.patch.object(enrich, "MAX_ERRORS_IN_A_ROW", 1):
            cars = self.run_cars()
        self.assertEqual(ask.call_count, 1)
        self.assertIsNone(cars[MULTI]["ai_processed_at"])           # retried on the next run

    def test_the_car_page_shows_the_cars_analysis(self):
        page = self.client.get(f"/vehicle/{MULTI}").get_data(as_text=True)
        self.assertIn("Ekspertyza ogłoszenia", page)                # before: no analysis yet
        self.run_cars()
        page = self.client.get(f"/vehicle/{MULTI}").get_data(as_text=True)
        self.assertIn("Podsumowanie auta.", page)
        self.assertIn("Ekspertyza 2 ogłoszeń tego auta", page)


if __name__ == "__main__":
    unittest.main()
