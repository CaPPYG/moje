import io
import json
from app import app, DEFAULT_PASSWORD

client = app.test_client()

def run_tests():
    print("Test 1: GET / (unauthenticated)")
    r = client.get("/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert b"Drive Drop" in r.data
    assert b"passwordInput" in r.data
    print("  -> OK (login view rendered)")

    print("Test 2: POST /login (wrong password)")
    r = client.post("/login", json={"password": "wrongpassword"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    print("  -> OK (rejected)")

    print("Test 3: POST /login (valid password)")
    r = client.post("/login", json={"password": DEFAULT_PASSWORD})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = json.loads(r.data)
    assert data.get("status") == "ok"
    print("  -> OK (authenticated)")

    print("Test 4: GET / (authenticated)")
    r = client.get("/")
    assert r.status_code == 200
    assert b"dropzone" in r.data
    assert b"UPLOADED" in r.data
    print("  -> OK (dashboard view rendered)")

    print("Test 5: GET /api/files")
    r = client.get("/api/files")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("status") == "ok"
    print(f"  -> OK (files count: {data.get('count')})")

    print("Test 6: POST /api/upload (test file)")
    test_content = b"Toto je testovaci subor zo skoly pre Drive Drop!"
    test_file = (io.BytesIO(test_content), "test_skola.txt")
    r = client.post("/api/upload", data={"file": test_file}, content_type="multipart/form-data")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.data}"
    data = json.loads(r.data)
    assert data.get("status") == "ok"
    uploaded = data.get("uploaded", [])
    assert len(uploaded) == 1
    file_id = uploaded[0]["id"]
    print(f"  -> OK (uploaded file id: {file_id})")

    print("Test 7: GET /api/files (check presence)")
    r = client.get("/api/files")
    data = json.loads(r.data)
    names = [f["name"] for f in data.get("files", [])]
    assert "test_skola.txt" in names
    print(f"  -> OK (found test_skola.txt in files list)")

    print("Test 8: GET /download/<id>?proxy=1")
    r = client.get(f"/download/{file_id}?proxy=1")
    assert r.status_code == 200
    assert r.data == test_content
    r.close()
    print("  -> OK (download content verified)")

    print("Test 9: POST /api/delete/<id>")
    r = client.post(f"/api/delete/{file_id}")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data.get("status") == "ok"
    print("  -> OK (file deleted)")

    print("Test 10: GET /api/files (verify deleted)")
    r = client.get("/api/files")
    data = json.loads(r.data)
    names = [f["name"] for f in data.get("files", [])]
    assert "test_skola.txt" not in names
    print("  -> OK (file clean)")

    print("\nALL 10 TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    run_tests()
