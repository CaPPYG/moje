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
        # 4. Pridanie profilu cez API (s mockom scrapera pre unit test)
        import scraper
        orig_fetch_profile = scraper.fetch_profile
        try:
            scraper.fetch_profile = lambda uname: {
                "username": uname,
                "full_name": "New Creator",
                "avatar_url": "https://example.com/new.jpg",
                "followers": 500,
                "following": 100,
                "posts_count": 10,
                "total_views": 5000,
                "avg_views": 500,
                "top_reel_url": "https://www.instagram.com/reel/abc123/",
                "top_reel_views": 2500,
                "top_reel_likes": 150,
                "engagement_rate": 3.2,
                "last_post_date": "pred 2 h",
                "last_post_views": 800,
                "last_post_url": "https://www.instagram.com/reel/xyz789/",
                "last_post_likes": 40
            }
            r = self.client.post("/api/ig-tracker/add", json={"username": "newcreator"})
            self.assertEqual(r.status_code, 201)
            res_data = json.loads(r.data)
            self.assertEqual(res_data["status"], "ok")
            created = next((a for a in res_data["accounts"] if a["username"] == "newcreator"), None)
            self.assertIsNotNone(created)
        finally:
            scraper.fetch_profile = orig_fetch_profile

        # 5. Zmazanie účtu cez API
        del_id = created["id"]
        r = self.client.delete(f"/api/ig-tracker/{del_id}")
        self.assertEqual(r.status_code, 200)
        del_data = json.loads(r.data)
        self.assertIsNone(next((a for a in del_data["accounts"] if a["id"] == del_id), None))

    def test_03_reels_db_operations(self):
        old_acc = db.get_account_by_username("reelscreator")
        if old_acc:
            db.delete_account(old_acc["id"])

        aid = db.add_account("reelscreator", full_name="Reels Creator", avatar_url="https://example.com/avatar.jpg")
        self.assertIsNotNone(aid)

        # 1. Upsert jednotlivého reelka
        r1 = {
            "shortcode": "TEST_REEL_1",
            "pk": "123456789",
            "url": "https://www.instagram.com/reel/TEST_REEL_1/",
            "video_url": "https://example.com/video1.mp4",
            "thumbnail_url": "https://example.com/thumb1.jpg",
            "views_count": 25000,
            "likes_count": 1200,
            "comments_count": 85,
            "caption": "Reels o fitness a motivácii #fitness #gym",
            "taken_at": "2024-05-10T12:00:00Z",
            "is_pinned": 0,
            "accessibility_caption": "May be an image of 1 person, indoor, lifting weights, gym",
            "topics": ["Fitness", "Bodybuilding"],
            "music_title": "Eye of the Tiger",
            "music_artist": "Survivor"
        }
        res1 = db.upsert_reel(aid, r1)
        self.assertIsNotNone(res1)
        self.assertEqual(res1["shortcode"], "TEST_REEL_1")
        self.assertEqual(res1["views_count"], 25000)
        self.assertEqual(res1["accessibility_caption"], "May be an image of 1 person, indoor, lifting weights, gym")

        # 2. Upsert ďalšieho reelka cez batch
        r2 = {
            "shortcode": "TEST_REEL_2",
            "pk": "987654321",
            "url": "https://www.instagram.com/reel/TEST_REEL_2/",
            "video_url": "https://example.com/video2.mp4",
            "thumbnail_url": "https://example.com/thumb2.jpg",
            "views_count": 150000,  # Top viral reel
            "likes_count": 8900,
            "comments_count": 420,
            "caption": "Mega virálne video #viral #comedy",
            "taken_at": "2024-05-15T18:30:00Z",
            "is_pinned": 1,
            "accessibility_caption": "May be an image of 2 people, laughing, outdoors, stage",
            "topics": ["Comedy", "Humor"],
            "music_title": "Funny Laugh",
            "music_artist": "Audio Library"
        }
        batch_cnt = db.upsert_reels_batch(aid, [r2])
        self.assertEqual(batch_cnt, 1)

        # 3. Získanie uložených reels
        reels = db.get_account_reels(aid, sort_by="taken_at")
        self.assertEqual(len(reels), 2)
        scs = [r["shortcode"] for r in reels]
        self.assertIn("TEST_REEL_1", scs)
        self.assertIn("TEST_REEL_2", scs)

        # Overenie parsovania topics
        r2_db = next(r for r in reels if r["shortcode"] == "TEST_REEL_2")
        self.assertIn("Comedy", r2_db["topics"])
        self.assertEqual(r2_db["views_fmt"], "150.0k")

        # 4. Sumár reels
        summary = db.get_reels_summary(aid)
        self.assertEqual(summary["reels_count"], 2)
        self.assertEqual(summary["total_views"], 175000)
        self.assertEqual(summary["total_likes"], 10100)
        self.assertEqual(summary["avg_views"], 87500)
        self.assertIsNotNone(summary["top_reel"])
        self.assertEqual(summary["top_reel"]["shortcode"], "TEST_REEL_2")

        # 5. Aktualizácia existujúceho reelka (zvýšenie views bez dátumu a bez is_pinned)
        r1_update = {
            "shortcode": "TEST_REEL_1",
            "views_count": 30000,
            "likes_count": 1500
        }
        db.upsert_reel(aid, r1_update)
        updated_r1 = next(r for r in db.get_account_reels(aid) if r["shortcode"] == "TEST_REEL_1")
        self.assertEqual(updated_r1["views_count"], 30000)
        # Pôvodný AI caption zostal zachovaný
        self.assertEqual(updated_r1["accessibility_caption"], "May be an image of 1 person, indoor, lifting weights, gym")
        # Pôvodný timestamp publikovania nesmie byť prepísaný na aktuálny čas!
        self.assertEqual(updated_r1["taken_at"], "2024-05-10T12:00:00+00:00")

        # 5b. Overenie zachovania is_pinned pri aktualizácii druhého reelka
        db.upsert_reel(aid, {"shortcode": "TEST_REEL_2", "views_count": 160000})
        updated_r2 = next(r for r in db.get_account_reels(aid) if r["shortcode"] == "TEST_REEL_2")
        self.assertEqual(updated_r2["is_pinned"], 1)

        # 5c. Overenie triedenia podľa views_count (najvyššie videnia prvé, aj keď iné je pinned)
        db.upsert_reel(aid, {"shortcode": "TEST_REEL_1", "is_pinned": 1})
        db.upsert_reel(aid, {"shortcode": "TEST_REEL_2", "is_pinned": 0})
        by_views = db.get_account_reels(aid, sort_by="views_count")
        self.assertEqual(by_views[0]["shortcode"], "TEST_REEL_2")  # 160k views > 30k views
        self.assertEqual(by_views[1]["shortcode"], "TEST_REEL_1")
        by_taken = db.get_account_reels(aid, sort_by="taken_at")
        self.assertEqual(by_taken[0]["shortcode"], "TEST_REEL_1")  # Pinned je prvý pri timeline zoradení

        # 6. Synchronizácia summary do snapshotu (atomická aktualizácia)
        db.sync_reels_summary_to_snapshot(aid)
        metrics = db.get_accounts_with_metrics()
        acc_metric = next((m for m in metrics if m["username"] == "reelscreator"), None)
        self.assertIsNotNone(acc_metric)
        self.assertEqual(acc_metric["total_views"], 190000)
        self.assertEqual(acc_metric["top_reel_views"], 160000)
        self.assertEqual(acc_metric["reels_count"], 2)

    def test_04_scraper_parsers(self):
        import scraper
        # 1. Test Apify item parsera s AI caption a témami
        mock_apify_item = {
            "shortCode": "C8AbCdEf",
            "id": "11223344",
            "url": "https://www.instagram.com/reel/C8AbCdEf/",
            "videoPlayCount": 42000,
            "likesCount": 1800,
            "commentsCount": 95,
            "caption": "Tréningový deň #fitness #workout",
            "timestamp": "2024-06-01T10:00:00Z",
            "accessibilityCaption": "May be an image of 1 person, indoor, barbell",
            "relatedTopicPills": [{"topic_name": "Sport & Fitness"}, {"topic_name": "Strength Training"}],
            "musicInfo": {"song_name": "Stronger", "artist_name": "Kanye West"}
        }
        parsed = scraper.parse_apify_reel_item(mock_apify_item, "testuser")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["shortcode"], "C8AbCdEf")
        self.assertEqual(parsed["views_count"], 42000)
        self.assertEqual(parsed["accessibility_caption"], "May be an image of 1 person, indoor, barbell")
        self.assertIn("Sport & Fitness", parsed["topics"])
        self.assertEqual(parsed["music_title"], "Stronger")

        # 2. Test SSR JSON parsera s rôznym poradím atribútov (<script data-sjs type="application/json">)
        mock_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Instagram</title></head>
        <body>
        <script data-sjs type="application/json">
        {
            "require": [
                ["PolarisProfilePostsLoggedOutTabGridUIContentQuery", "use", [], [{
                    "data": {
                        "xdt_api__v1__clips__user__clips_graphql_connection": {
                            "edges": [
                                {
                                    "node": {
                                        "media": {
                                            "code": "C9XyZ123",
                                            "id": "99887766",
                                            "play_count": 88000,
                                            "like_count": 4500,
                                            "comment_count": 120,
                                            "caption": {"text": "Nové video na profile!"},
                                            "taken_at": 1718000000,
                                            "display_url": "https://example.com/thumb.jpg",
                                            "video_url": "https://example.com/clip.mp4",
                                            "accessibility_caption": "May be an image of \\\"mountains\\\", outdoor, sunset",
                                            "related_topic_pills": [{"topic_name": "Nature & Travel"}]
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }]]
            ]
        }
        </script>
        </body>
        </html>
        """
        reels_from_html = scraper.parse_reels_from_html(mock_html, "traveler")
        self.assertEqual(len(reels_from_html), 1)
        r_html = reels_from_html[0]
        self.assertEqual(r_html["shortcode"], "C9XyZ123")
        self.assertEqual(r_html["views_count"], 88000)
        self.assertEqual(r_html["likes_count"], 4500)
        self.assertEqual(r_html["accessibility_caption"], 'May be an image of "mountains", outdoor, sunset')
        self.assertIn("Nature & Travel", r_html["topics"])

    def test_05_reels_api_endpoints(self):
        # 1. Prihlásenie
        self.client.post("/login", data={"password": "patrik3924"}, follow_redirects=True)

        old_acc = db.get_account_by_username("apicreator")
        if old_acc:
            db.delete_account(old_acc["id"])

        aid = db.add_account("apicreator", full_name="API Creator")
        db.upsert_reel(aid, {
            "shortcode": "API_REEL_1",
            "views_count": 12000,
            "likes_count": 600,
            "comments_count": 30,
            "caption": "Reel cez API",
            "accessibility_caption": "May be an image of office desk",
            "topics": ["Technology"]
        })

        # 2. GET /api/ig-tracker/<id>/reels
        r = self.client.get(f"/api/ig-tracker/{aid}/reels")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["reels"][0]["shortcode"], "API_REEL_1")
        self.assertEqual(data["reels"][0]["accessibility_caption"], "May be an image of office desk")
        self.assertIn("Technology", data["reels"][0]["topics"])

        # 3. POST /api/ig-tracker/<id>/sync-reels-fast (mock scraper)
        import scraper
        orig_fetch_html = scraper.fetch_recent_reels_html
        try:
            scraper.fetch_recent_reels_html = lambda uname: [{
                "shortcode": "FAST_REEL_2",
                "views_count": 34000,
                "likes_count": 1500,
                "comments_count": 75,
                "caption": "Rýchlo načítané video",
                "accessibility_caption": "May be an image of coffee cup",
                "topics": ["Food & Drink"]
            }]
            r_sync = self.client.post(f"/api/ig-tracker/{aid}/sync-reels-fast")
            self.assertEqual(r_sync.status_code, 200)
            sync_data = json.loads(r_sync.data)
            self.assertEqual(sync_data["status"], "ok")
            self.assertGreaterEqual(sync_data["count"], 1)
            reels_after = sync_data["reels"]
            self.assertIsNotNone(next((x for x in reels_after if x["shortcode"] == "FAST_REEL_2"), None))
        finally:
            scraper.fetch_recent_reels_html = orig_fetch_html

        # 4. POST /api/ig-tracker/<id>/sync-reels-full (mock scraper)
        orig_fetch_apify = scraper.fetch_all_reels_apify
        try:
            scraper.fetch_all_reels_apify = lambda uname, limit=100: [{
                "shortcode": "FULL_APIFY_REEL",
                "views_count": 500000,
                "likes_count": 25000,
                "comments_count": 1200,
                "caption": "Kompletné historické video cez Apify",
                "accessibility_caption": "May be an image of stage with lights",
                "topics": ["Entertainment", "Concert"]
            }]
            r_full = self.client.post(f"/api/ig-tracker/{aid}/sync-reels-full", json={"limit": 50})
            self.assertEqual(r_full.status_code, 200)
            full_data = json.loads(r_full.data)
            self.assertEqual(full_data["status"], "ok")
            reels_full = full_data["reels"]
            self.assertIsNotNone(next((x for x in reels_full if x["shortcode"] == "FULL_APIFY_REEL"), None))
            self.assertEqual(full_data["summary"]["top_reel"]["shortcode"], "FULL_APIFY_REEL")
        finally:
            scraper.fetch_all_reels_apify = orig_fetch_apify

    def test_06_reels_edge_cases(self):
        # 1. Prihlásenie pre autorizovaný prístup
        self.client.post("/login", data={"password": "patrik3924"}, follow_redirects=True)

        old_acc = db.get_account_by_username("empty_reels_user")
        if old_acc:
            db.delete_account(old_acc["id"])

        empty_aid = db.add_account("empty_reels_user")
        s = db.get_reels_summary(empty_aid)
        self.assertEqual(s["reels_count"], 0)
        self.assertEqual(s["total_views"], 0)
        self.assertEqual(s["avg_views"], 0)
        self.assertIsNone(s["top_reel"])
        self.assertIsNone(s["latest_reel"])

        # 2. Upsert reel s chýbajúcim shortcode vracia None
        self.assertIsNone(db.upsert_reel(empty_aid, {}))
        self.assertIsNone(db.upsert_reel(empty_aid, {"caption": "Bez shortcode"}))

        # 3. Upsert dávky s prázdnym zoznamom
        self.assertEqual(db.upsert_reels_batch(empty_aid, []), 0)

        # 4. Neexistujúci účet v API vráti 404
        r = self.client.get("/api/ig-tracker/999999/reels")
        self.assertEqual(r.status_code, 404)
        r2 = self.client.post("/api/ig-tracker/999999/sync-reels-fast")
        self.assertEqual(r2.status_code, 404)
        r3 = self.client.post("/api/ig-tracker/999999/sync-reels-full")
        self.assertEqual(r3.status_code, 404)

        # 5. Atomická synchronizácia snapshotu (žiadny chiméra mix URL, views a lajkov)
        s_initial = db.add_snapshot(
            empty_aid, 1000, 100, 5,
            top_reel_url="https://example.com/reel/old",
            top_reel_views=50000,
            top_reel_likes=3000
        )
        # Pridáme reel s MENŠÍM počtom views (40k), ale VIAC lajkov (5000)
        db.upsert_reel(empty_aid, {
            "shortcode": "LOWER_REEL",
            "url": "https://example.com/reel/lower",
            "views_count": 40000,
            "likes_count": 5000
        })
        db.sync_reels_summary_to_snapshot(empty_aid)
        s_after_lower = db.get_latest_snapshot(empty_aid)
        # Snapshot nesmie byť skontaminovaný URL nižšieho reelka ani jeho lajkami
        self.assertEqual(s_after_lower["top_reel_url"], "https://example.com/reel/old")
        self.assertEqual(s_after_lower["top_reel_views"], 50000)
        self.assertEqual(s_after_lower["top_reel_likes"], 3000)

        # Pridáme reel s VYŠŠÍM počtom views (60k), ale MENŠÍM počtom lajkov (1000)
        db.upsert_reel(empty_aid, {
            "shortcode": "NEW_HIGHER",
            "url": "https://example.com/reel/higher",
            "views_count": 60000,
            "likes_count": 1000
        })
        db.sync_reels_summary_to_snapshot(empty_aid)
        s_after_higher = db.get_latest_snapshot(empty_aid)
        # URL, views aj lajky musia byť z nového reelka ako jeden celok
        self.assertEqual(s_after_higher["top_reel_url"], "https://example.com/reel/higher")
        self.assertEqual(s_after_higher["top_reel_views"], 60000)
        self.assertEqual(s_after_higher["top_reel_likes"], 1000)

        # 6. Test HTML regex fallbacku s escaped úvodzovkami v accessibility_caption a related_topic_pills
        import scraper
        mock_reel_page_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta property="og:description" content="1,234 likes, 56 comments: Test reel #fitness #gym">
          <meta property="og:image" content="https://example.com/poster.jpg">
          <meta property="og:video" content="https://example.com/video.mp4">
        </head>
        <body>
          <script>
            var dummy = {"accessibility_caption": "May be an image of \\\"superhero\\\", outdoor", "related_topic_pills": [{"topic_name": "Cinema & Movies"}]};
          </script>
        </body>
        </html>
        """
        orig_get = scraper.requests.get
        try:
            class MockResponse:
                status_code = 200
                text = mock_reel_page_html
            scraper.requests.get = lambda *args, **kwargs: MockResponse()
            det = scraper.fetch_reel_details_html("XYZ999")
            self.assertIsNotNone(det)
            self.assertEqual(det["accessibility_caption"], 'May be an image of "superhero", outdoor')
            self.assertIn("Cinema & Movies", det["topics"])
            self.assertEqual(det["likes_count"], 1234)
            self.assertEqual(det["comments_count"], 56)
        finally:
            scraper.requests.get = orig_get


if __name__ == "__main__":
    unittest.main()

