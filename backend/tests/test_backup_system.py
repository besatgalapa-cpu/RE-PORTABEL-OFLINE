"""Tests for backup, restore, system info, shutdown, portable download, galeri, RBAC."""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
API = f"{BASE_URL}/api"

ADMIN = ("admin", "adminRE1234#")


def _login(u, p):
    r = requests.post(f"{API}/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}"})
    return s


@pytest.fixture(scope="module")
def verifikator_client(admin_client):
    # ensure a verifikator user exists
    users = admin_client.get(f"{API}/users").json()
    existing = next((u for u in users if u["username"] == "test_verif_backup"), None)
    if not existing:
        r = admin_client.post(f"{API}/users", json={
            "username": "test_verif_backup", "name": "Test Verifikator",
            "password": "P@ssw0rd123", "role": "Verifikator Data",
        })
        assert r.status_code == 200, r.text
    tok = _login("test_verif_backup", "P@ssw0rd123")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    yield s
    # cleanup
    users = admin_client.get(f"{API}/users").json()
    u = next((u for u in users if u["username"] == "test_verif_backup"), None)
    if u:
        admin_client.delete(f"{API}/users/{u['id']}")


# ---- System info ----
def test_system_info(admin_client):
    r = admin_client.get(f"{API}/system/info")
    assert r.status_code == 200
    j = r.json()
    assert j["portable_mode"] is False
    assert j["can_shutdown"] is False
    assert "backup_dir" in j and "galeri_dir" in j


def test_system_info_unauth():
    r = requests.get(f"{API}/system/info")
    assert r.status_code == 401


# ---- Shutdown (should 400 in preview) ----
def test_shutdown_not_portable(admin_client):
    r = admin_client.post(f"{API}/system/shutdown")
    assert r.status_code == 400


# ---- Backup CRUD ----
def test_backup_flow(admin_client):
    # list initial
    r = admin_client.get(f"{API}/backup")
    assert r.status_code == 200
    initial = r.json()

    # create manual
    r2 = admin_client.post(f"{API}/backup")
    assert r2.status_code == 200, r2.text
    created = r2.json()
    assert created["name"].startswith("manual_")
    assert created["kind"] == "manual"
    assert created["size"] > 0
    name = created["name"]

    # list contains it
    r3 = admin_client.get(f"{API}/backup")
    assert r3.status_code == 200
    names = [b["name"] for b in r3.json()]
    assert name in names

    # download works
    r4 = admin_client.get(f"{API}/backup/{name}/download")
    assert r4.status_code == 200
    assert r4.headers.get("content-type", "").startswith("application/zip") or r4.headers.get("content-type") == "application/zip"
    assert len(r4.content) > 0

    # download 404 for non-existent
    r5 = admin_client.get(f"{API}/backup/does_not_exist.zip/download")
    assert r5.status_code == 404

    # path traversal blocked -> 404
    r6 = admin_client.get(f"{API}/backup/..%2F..%2Fetc%2Fpasswd/download")
    assert r6.status_code == 404

    # delete our created backup
    r7 = admin_client.delete(f"{API}/backup/{name}")
    assert r7.status_code == 200
    # verify gone
    r8 = admin_client.get(f"{API}/backup")
    assert name not in [b["name"] for b in r8.json()]


# ---- RBAC ----
def test_backup_requires_data_write(verifikator_client):
    # Verifikator has data:write -> can list & create
    r = verifikator_client.get(f"{API}/backup")
    assert r.status_code == 200
    r2 = verifikator_client.post(f"{API}/backup")
    assert r2.status_code == 200, r2.text
    name = r2.json()["name"]
    # cleanup by admin after (verifikator cannot delete)
    r3 = verifikator_client.delete(f"{API}/backup/{name}")
    assert r3.status_code == 403, r3.text


def test_restore_requires_super_admin(verifikator_client, admin_client):
    # need a backup existing
    existing = admin_client.get(f"{API}/backup").json()
    if not existing:
        admin_client.post(f"{API}/backup")
        existing = admin_client.get(f"{API}/backup").json()
    name = existing[0]["name"]
    r = verifikator_client.post(f"{API}/backup/{name}/restore")
    assert r.status_code == 403


def test_shutdown_requires_super_admin(verifikator_client):
    r = verifikator_client.post(f"{API}/system/shutdown")
    assert r.status_code == 403


# ---- Portable download ----
def test_portable_download_head():
    # allow 200 or 404 (rebuilding)
    r = requests.head(f"{BASE_URL}/api/portable/download", allow_redirects=True)
    assert r.status_code in (200, 404, 405), r.status_code
    if r.status_code == 200:
        # content-type may be application/zip
        assert "zip" in r.headers.get("content-type", "").lower()


# ---- Galeri upload / delete ----
def _make_png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()


def test_galeri_upload_and_delete(admin_client):
    data = _make_png_bytes()
    files = {"file": ("test.png", data, "image/png")}
    headers = {"Authorization": admin_client.headers["Authorization"]}
    r = requests.post(f"{API}/galeri/upload", files=files,
                      data={"judul": "TEST_upload", "kecamatan": "", "kategori": "Wilayah"},
                      headers=headers)
    assert r.status_code == 200, r.text
    doc = r.json()
    fid = doc["id"]
    # storage_path stored locally
    assert doc["storage_path"].startswith("murung-raya-re/galeri/")
    # file endpoint returns bytes
    r2 = admin_client.get(f"{API}/galeri/file/{fid}")
    assert r2.status_code == 200
    assert len(r2.content) > 0
    # thumb variant
    r3 = admin_client.get(f"{API}/galeri/file/{fid}", params={"variant": "thumb"})
    assert r3.status_code == 200
    # delete
    r4 = admin_client.delete(f"{API}/galeri/{fid}")
    assert r4.status_code == 200
    # gone from list
    r5 = admin_client.get(f"{API}/galeri")
    assert fid not in [g["id"] for g in r5.json()]


# ---- Upload/preview validation ----
def test_upload_non_xlsx_returns_400(admin_client):
    files = {"file": ("bad.txt", io.BytesIO(b"nope"), "text/plain")}
    headers = {"Authorization": admin_client.headers["Authorization"]}
    r = requests.post(f"{API}/upload/preview", files=files, headers=headers)
    assert r.status_code == 400
