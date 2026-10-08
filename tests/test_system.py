import os
import unittest
import json
import sqlite3

# Force sqlite backend and test DB
os.environ["DB_BACKEND"] = "sqlite"
os.environ["API_TOKEN"] = "test-token"
TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_sportscar.db")

# Ensure test DB is clean before importing
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

import db
db.DB_PATH = TEST_DB_PATH

from app import app, is_plausible_vin

class TestSportsCarDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()
        
    def setUp(self):
        # Fresh DB for each test
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        
        # Init schema
        conn = sqlite3.connect(TEST_DB_PATH)
        with open(os.path.join(os.path.dirname(__file__), "../schema.sql"), "r") as f:
            conn.executescript(f.read())
        
        # Run db.py's internal schema initialization and migrations
        db.init_db()

    def tearDown(self):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_vin_validation(self):
        """Test the is_plausible_vin function against known valid and invalid VINs"""
        # True positives (Modern BMWs with letters at the end)
        self.assertTrue(is_plausible_vin("WBS11DM0108E8AG77"))
        self.assertTrue(is_plausible_vin("3MF13DM03R8E15622"))
        
        # True positives (Standard Audi, Mercedes, Porsche)
        self.assertTrue(is_plausible_vin("WUAZZZ8V2LA900174"))
        self.assertTrue(is_plausible_vin("WDD2040771F408260"))
        self.assertTrue(is_plausible_vin("WP0ZZZ98ZGK194519"))
        
        # True negatives
        self.assertFalse(is_plausible_vin("WBS11DM0108E8XXXX")) # Masked
        self.assertFalse(is_plausible_vin("JTDAF4E340A0XXXXX")) # Masked
        self.assertFalse(is_plausible_vin("12345678912345678")) # Bad WMI
        self.assertFalse(is_plausible_vin("WBA81DP0109J85XXX")) # Bad suffix
        self.assertFalse(is_plausible_vin("XXXXXXXXXXXXXXXXX")) # Too many repetitive chars

    def test_api_ingest_pending(self):
        """Test that the scraper can post a new listing to pending_listings"""
        headers = {"Authorization": "Bearer test-token"}
        payload = {
            "source": "dummy_scraper",
            "source_listing_id": "999111",
            "vin": "WBS11DM0108E8AG77",
            "make": "BMW",
            "model": "M2",
            "registration_plate": "WA12345",
            "price_pln": 300000
        }
        
        res = self.client.post("/api/ingest_pending", json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")
        
        conn = db.get_db()
        pending = conn.execute("SELECT * FROM pending_listings WHERE source_listing_id='999111'").fetchone()
        conn.close()
        
        self.assertIsNotNone(pending)
        self.assertEqual(pending["vin"], "WBS11DM0108E8AG77")
        self.assertEqual(pending["registration_plate"], "WA12345")
        self.assertEqual(pending["status"], "pending")

    def test_approve_listing_flow(self):
        """Test the review approval flow creates vehicles and listing_observations correctly"""
        headers = {"Authorization": "Bearer test-token"}
        payload = {
            "source": "dummy_scraper",
            "source_listing_id": "999111",
            "vin": "WBS11DM0108E8AG77",
            "make": "BMW",
            "model": "M2",
            "registration_plate": "WA12345",
            "price_pln": 300000
        }
        res = self.client.post("/api/ingest_pending", json=payload, headers=headers)
        pending_id = res.get_json()["id"]
        
        # Approve the listing via the review endpoint
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
        res_approve = self.client.post(f"/review/{pending_id}/approve", data={"notes": "looks good"}, headers=headers)
        self.assertEqual(res_approve.status_code, 302) # Should redirect
        
        conn = db.get_db()
        
        # 1. Check vehicles table
        vehicle = conn.execute("SELECT * FROM vehicles WHERE vin='WBS11DM0108E8AG77'").fetchone()
        self.assertIsNotNone(vehicle)
        self.assertEqual(vehicle["make"], "BMW")
        self.assertEqual(vehicle["registration_plate"], "WA12345")
        
        # 2. Check listing_observations table
        obs = conn.execute("SELECT * FROM listing_observations WHERE vin='WBS11DM0108E8AG77'").fetchone()
        conn.close()
        
        self.assertIsNotNone(obs)
        self.assertEqual(obs["price_pln"], 300000)
        self.assertEqual(obs["registration_plate"], "WA12345")
        self.assertEqual(obs["source"], "dummy_scraper")

    def test_ingest_duplicate_updates_observation(self):
        """Test that re-scraping the same active listing inserts a new timeline observation"""
        headers = {"Authorization": "Bearer test-token"}
        payload = {
            "source": "dummy_scraper",
            "source_listing_id": "999111",
            "vin": "WBS11DM0108E8AG77",
            "make": "BMW",
            "model": "M2",
            "registration_plate": "WA12345",
            "price_pln": 300000
        }
        
        # Step 1: Ingest and approve
        self.client.post("/api/ingest_pending", json=payload, headers=headers)
        conn = db.get_db()
        pending_id = conn.execute("SELECT id FROM pending_listings WHERE source_listing_id='999111'").fetchone()["id"]
        conn.close()
        
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
        self.client.post(f"/review/{pending_id}/approve", data={})
        
        # Step 2: Ingest again with a price drop and new license plate!
        payload["price_pln"] = 280000
        payload["registration_plate"] = "NEW6789"
        res2 = self.client.post("/api/ingest_pending", json=payload, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["tag"], "price_updated")
        
        # Check listing_observations
        conn = db.get_db()
        obs = conn.execute("SELECT * FROM listing_observations WHERE vin='WBS11DM0108E8AG77' ORDER BY id").fetchall()
        conn.close()
        
        # There should be 2 observations in the timeline now
        self.assertEqual(len(obs), 2)
        
        self.assertEqual(obs[0]["price_pln"], 300000)
        self.assertEqual(obs[0]["registration_plate"], "WA12345")
        
        self.assertEqual(obs[1]["price_pln"], 280000)
        self.assertEqual(obs[1]["registration_plate"], "NEW6789")

if __name__ == '__main__':
    unittest.main()
