"""Maps must only ever receive known voivodeship codes."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.regions import CITY_TO_REGION, REGION_NAMES, resolve_region


class TestResolveRegion(unittest.TestCase):
    def test_known_code_and_name(self):
        self.assertEqual(resolve_region("PL-MZ"), "PL-MZ")
        self.assertEqual(resolve_region("mazowieckie"), "PL-MZ")
        self.assertEqual(resolve_region("Śląskie"), "PL-SL")

    def test_unknown_five_char_value_falls_back_to_city(self):
        self.assertEqual(resolve_region("XX-YY", "Żory"), "PL-SL")
        self.assertIsNone(resolve_region("XX-YY"))

    def test_unknown_everything_is_none(self):
        self.assertIsNone(resolve_region(None, None))
        self.assertIsNone(resolve_region("", "Nigdzie"))

    def test_city_with_voivodeship_after_comma(self):
        # autoplac and OLX store the location as 'City, Voivodeship'
        self.assertEqual(resolve_region(None, "Tarnów, Małopolskie"), "PL-MA")
        self.assertEqual(resolve_region(None, "Chwaszczyno, Pomorskie"), "PL-PM")
        self.assertEqual(resolve_region(None, "Toruń, Kujawsko-Pomorskie"), "PL-KP")
        self.assertEqual(resolve_region("", "Wijewo, Wielkopolskie"), "PL-WP")
        self.assertEqual(resolve_region(None, "Swadzim"), "PL-WP")  # from the Poznań-area coordinates

    def test_location_is_the_same_whatever_the_format(self):
        from webapp.regions import location
        expected = {"place": "Tarnów", "region": "PL-MA", "region_name": "Małopolskie"}
        self.assertEqual(location("Tarnów, Małopolskie"), expected)
        self.assertEqual(location("Tarnów", "PL-MA"), expected)
        self.assertEqual(location("Tarnów"), expected)
        self.assertEqual(location(None), {"place": None, "region": None, "region_name": ""})

    def test_city_map_only_yields_known_codes(self):
        self.assertTrue(set(CITY_TO_REGION.values()) <= set(REGION_NAMES))


if __name__ == "__main__":
    unittest.main()
