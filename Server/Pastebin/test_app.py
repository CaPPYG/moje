import io
import json
import time
from app import app

client = app.test_client()

def run_tests():
    print("Test 1: GET / unauthenticated shows login page")
    r = client.get("/")
    assert r.status_code == 200
    assert b"Vstup do PasteBin" in r.data
    print("  -> OK")

    print("Test 1b: POST /api/paste without master auth returns 401")
    r = client.post("/api/paste", json={"type": "text", "content": "spam"})
    assert r.status_code == 401
    print("  -> OK")

    print("Test 1c: POST /login with patrik3924 logs in")
    r = client.post("/login", data={"password": "patrik3924"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Text / K\xc3\xb3d" in r.data or b"Odhl\xc3\xa1si\xc5\xa5" in r.data
    print("  -> OK")

    print("Test 2: POST /api/paste (plain text) when authenticated")
    r = client.post("/api/paste", json={
        "type": "text",
        "content": "Ahoj svet, toto je bezpecny testovaci paste!",
        "ttl": 3600,
        "burn_after_reading": False
    })
    assert r.status_code == 201, f"Expected 201, got {r.status_code}"
    data = json.loads(r.data)
    paste_id = data["id"]
    print(f"  -> OK (created ID: {paste_id})")

    print("Test 3: GET /p/<id> (view text)")
    r = client.get(f"/p/{paste_id}")
    assert r.status_code == 200
    assert b"Ahoj svet" in r.data
    print("  -> OK")

    print("Test 4: GET /p/<id>/raw (raw text)")
    r = client.get(f"/p/{paste_id}/raw")
    assert r.status_code == 200
    assert r.data.decode("utf-8") == "Ahoj svet, toto je bezpecny testovaci paste!"
    print("  -> OK")

    print("Test 5: POST /api/paste with password")
    r = client.post("/api/paste", json={
        "type": "text",
        "content": "Tajny obsah za heslom",
        "password": "tajneheslo123"
    })
    assert r.status_code == 201
    pwd_paste_id = json.loads(r.data)["id"]
    
    # Bez hesla -> výzva na zadanie hesla
    r = client.get(f"/p/{pwd_paste_id}")
    assert r.status_code == 200
    assert b"Chr\xc3\xa1nen\xc3\xbd z\xc3\xa1znam" in r.data or b"heslo" in r.data.lower()
    
    # API bez hesla -> 401
    r = client.get(f"/api/paste/{pwd_paste_id}")
    assert r.status_code == 401
    
    # API so správnym heslom -> 200
    r = client.get(f"/api/paste/{pwd_paste_id}", headers={"X-Paste-Password": "tajneheslo123"})
    assert r.status_code == 200
    assert json.loads(r.data)["content"] == "Tajny obsah za heslom"
    print("  -> OK (password protection verified)")

    print("Test 6: Burn-after-reading test")
    r = client.post("/api/paste", json={
        "type": "text",
        "content": "Tento text sa sam zmaze po precitani",
        "burn_after_reading": True
    })
    assert r.status_code == 201
    burn_id = json.loads(r.data)["id"]

    # 1. zobrazenie -> 200 OK
    r = client.get(f"/p/{burn_id}")
    assert r.status_code == 200
    assert b"Tento text sa sam zmaze" in r.data

    # 2. zobrazenie -> 404 Not Found!
    r = client.get(f"/p/{burn_id}")
    assert r.status_code == 404
    print("  -> OK (successfully burned after 1st reading)")

    print("Test 7: POST /api/paste with Image upload")
    img_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    file_obj = (io.BytesIO(img_data), "pixel.png")
    r = client.post("/api/paste", data={
        "type": "image",
        "file": file_obj
    }, content_type="multipart/form-data")
    assert r.status_code == 201
    img_id = json.loads(r.data)["id"]

    r = client.get(f"/p/{img_id}")
    assert r.status_code == 200
    assert b"image" in r.data.lower()

    r = client.get(f"/p/{img_id}/raw")
    assert r.status_code == 200
    assert r.data == img_data
    print("  -> OK (image upload and raw stream verified)")

    print("Test 8: TTL expiration test (1 second)")
    r = client.post("/api/paste", json={
        "type": "text",
        "content": "Rychla expiracia",
        "ttl": 1
    })
    assert r.status_code == 201
    exp_id = json.loads(r.data)["id"]
    time.sleep(1.5)
    r = client.get(f"/p/{exp_id}")
    assert r.status_code == 404
    print("  -> OK (expired record automatically deleted and returned 404)")

    print("\nALL 8 TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    run_tests()
