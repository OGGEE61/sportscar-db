"""Offline tests for the listing enricher's output cleanup and market conflict check."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import enrich_with_bielik as enrich


class TestCleanAnalysis(unittest.TestCase):
    def test_market_outside_the_list_becomes_none(self):
        for market in ("Niemcy", "Korea Południowa", "Brak", "", None, 5):
            self.assertIsNone(enrich.clean_analysis({"origin_market": market})["origin_market"])

    def test_allowed_market_is_kept_in_canonical_form(self):
        self.assertEqual(enrich.clean_analysis({"origin_market": "usa"})["origin_market"], "USA")
        self.assertEqual(enrich.clean_analysis({"origin_market": "Zatoka Perska"})["origin_market"], "Zatoka Perska")

    def test_every_way_of_saying_empty_becomes_none(self):
        for empty in ("nie podano", "null", "Brak informacji", "  ", "brak"):
            self.assertIsNone(enrich.clean_analysis({"interior_color": empty})["interior_color"])
        self.assertEqual(enrich.clean_analysis({"interior_color": " czarny "})["interior_color"], "czarny")

    def test_accident_and_region_must_be_on_the_list(self):
        d = enrich.clean_analysis({"accident_status": "Bezwypadkowy", "location_region": "Texas"})
        self.assertEqual(d["accident_status"], "bezwypadkowy")
        self.assertIsNone(d["location_region"])

    def test_equipment_is_capped(self):
        self.assertEqual(len(enrich.clean_analysis({"key_equipment": list("ABCDEFGH")})["key_equipment"]), 5)

    def test_malformed_fields_do_not_raise(self):
        d = enrich.clean_analysis({"key_equipment": "BOSE", "has_panoramic_roof": "true", "summary": 7})
        self.assertEqual(d["key_equipment"], [])
        self.assertFalse(d["has_panoramic_roof"])
        self.assertIsNone(d["summary"])
        self.assertEqual(enrich.clean_analysis({"key_equipment": ["BOSE", "null", 3]})["key_equipment"], ["BOSE"])


class TestMarketsConflict(unittest.TestCase):
    def test_empty_side_is_no_conflict(self):
        self.assertFalse(enrich.markets_conflict(None, "USA"))
        self.assertFalse(enrich.markets_conflict("USA", None))

    def test_poland_and_europe_agree_both_ways(self):
        self.assertFalse(enrich.markets_conflict("Polska", "Europa"))
        self.assertFalse(enrich.markets_conflict("Europa", "Polska"))

    def test_resolver_usa_kanada_covers_both(self):
        self.assertFalse(enrich.markets_conflict("USA/Kanada", "Kanada"))
        self.assertFalse(enrich.markets_conflict("USA/Kanada", "USA"))
        self.assertTrue(enrich.markets_conflict("USA/Kanada", "Europa"))

    def test_real_disagreement(self):
        self.assertTrue(enrich.markets_conflict("USA", "Polska"))
        self.assertTrue(enrich.markets_conflict("Japonia", "Europa"))


if __name__ == "__main__":
    unittest.main()
