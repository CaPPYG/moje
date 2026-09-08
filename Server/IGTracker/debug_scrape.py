import sys
import traceback
import scraper

username = sys.argv[1] if len(sys.argv) > 1 else "urfavclaragarz"
print(f"Testing scrape for @{username}...")

try:
    res = scraper.fetch_profile_instaloader(username)
    print("SUCCESS:")
    for k, v in res.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
