import json
import unittest
from app import app
import db


class TestIGTracker(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        db.init_db()

    def test_01_db_add_account_and_snapshot(self):
        aid = db.add_account("testuser", full_name="Test User", avatar_url="https://example.com/avatar.jpg")
        self.assertIsNotNone(aid)

        # 1. snapshot: 10 000 followerov
        s1 = db.add_snapshot(
            account_id=aid,
            followers=10000,
            following=300,
            posts_count=50,
            top_reel_url="https://www.instagram.com/reel/xyz123/",
            top_reel_views=50000,
            top_reel_likes=2500,
            total_views=150000,
            avg_views=15000,
            engagement_rate=4.5,
            last_post_date="pred 1 dňom"
        )
        self.assertIsNotNone(s1)

        # 2. snapshot (novší): 10 150 followerov (delta = +150)
        s2 = db.add_snapshot(
            account_id=aid,
            followers=10150,
            following=302,
            posts_count=51,
            top_reel_url="https://www.instagram.com/reel/xyz123/",
            top_reel_views=55000,
            top_reel_likes=2800,
            total_views=165000,
            avg_views=15500,
            engagement_rate=4.7,
            last_post_date="pred 2 h"
        )
        self.assertIsNotNone(s2)

        # Overenie delty a metrík
        metrics = db.get_accounts_with_metrics()
        acc_metric = next((m for m in metrics if m["username"] == "testuser"), None)
        self.assertIsNotNone(acc_metric)
        self.assertEqual(acc_metric["followers"], 10150)
        self.assertEqual(acc_metric["delta_followers"], 150)
        self.assertEqual(acc_metric["delta_fmt"], "+150")
        self.assertEqual(acc_metric["followers_fmt"], "10.2k")

    def test_02_auth_and_api(self):
        # 1. Neoverený prístup
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Vstup do IG Tracker", r.data)

        # API bez hesla -> 401
        r = self.client.get("/api/ig-tracker")
        self.assertEqual(r.status_code, 401)

        # 2. Prihlásenie s patrik3924
        r = self.client.post("/login", data={"password": "patrik3924"}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"IG Analytics Tracker", r.data)

        # 3. Overený prístup k API
        r = self.client.get("/api/ig-tracker")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")
        self.assertIn("accounts", data)

        # 4. Pridanie profilu cez API
        r = self.client.post("/api/ig-tracker/add", json={"username": "newcreator"})
        self.assertEqual(r.status_code, 201)
        res_data = json.loads(r.data)
        self.assertEqual(res_data["status"], "ok")
        created = next((a for a in res_data["accounts"] if a["username"] == "newcreator"), None)
        self.assertIsNotNone(created)

        # 5. Zmazanie účtu cez API
        del_id = created["id"]
        r = self.client.delete(f"/api/ig-tracker/{del_id}")
        self.assertEqual(r.status_code, 200)
        del_data = json.loads(r.data)
        self.assertIsNone(next((a for a in del_data["accounts"] if a["id"] == del_id), None))


if __name__ == "__main__":
    unittest.main()
