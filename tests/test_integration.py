"""
Integration smoke test for the drone dashboard API.
Tests boundary upload flow, session creation, map endpoints, and export endpoints.
Does NOT test the actual video processing pipeline (requires ffmpeg + real video).
"""
import io
import json
import os
import sys
import tempfile
import zipfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SHAPEFILE_DIR = r"C:\Users\davi.tantra\Downloads\REVEGETASI2026"
SHP_BASENAME = "rvg_gmo_kum_2605"
SHAPEFILE_AVAILABLE = os.path.isdir(SHAPEFILE_DIR) and os.path.exists(
    os.path.join(SHAPEFILE_DIR, SHP_BASENAME + ".shp")
)
SHP_EXTENSIONS = [".shp", ".dbf", ".prj", ".shx"]


def _build_shapefile_zip() -> bytes:
    """Zip the shapefile components into an in-memory ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in SHP_EXTENSIONS:
            path = os.path.join(SHAPEFILE_DIR, SHP_BASENAME + ext)
            zf.write(path, arcname=SHP_BASENAME + ext)
    return buf.getvalue()


@pytest.fixture(scope="module")
def app():
    """Create app with a temporary isolated database."""
    import app as app_module
    from database import init_db
    import config

    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch DB and upload paths for isolation
        orig_db = config.DB_PATH
        orig_upload = config.UPLOAD_DIR
        config.DB_PATH = os.path.join(tmpdir, "test.db")
        config.UPLOAD_DIR = os.path.join(tmpdir, "uploads")
        os.makedirs(config.UPLOAD_DIR, exist_ok=True)

        # Also patch database module's import
        import database
        database.DB_PATH = config.DB_PATH

        init_db()

        flask_app = app_module.create_app()
        flask_app.config["TESTING"] = True

        yield flask_app

        # Restore
        config.DB_PATH = orig_db
        config.UPLOAD_DIR = orig_upload
        database.DB_PATH = orig_db


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


# ─────────────────────────────────────────────────────────────────────────────
# Boundary flow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not SHAPEFILE_AVAILABLE, reason="Shapefile not found at SHAPEFILE_DIR")
class TestBoundaryFlow:
    boundary_id = None

    def test_upload_boundary_returns_201(self, client):
        zip_bytes = _build_shapefile_zip()
        data = {
            "nama": "Revegetasi GMO 2026",
            "deskripsi": "Test boundary",
            "file": (io.BytesIO(zip_bytes), "rvg_gmo.zip"),
        }
        resp = client.post(
            "/api/boundaries",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.data}"
        body = resp.get_json()
        assert "id" in body
        assert body["nama"] == "Revegetasi GMO 2026"
        assert "jumlah_blok" in body
        assert body["jumlah_blok"] == 7, f"Expected 7 bloks, got {body['jumlah_blok']}"
        TestBoundaryFlow.boundary_id = body["id"]

    def test_list_boundaries_contains_uploaded(self, client):
        resp = client.get("/api/boundaries")
        assert resp.status_code == 200
        items = resp.get_json()
        ids = [b["id"] for b in items]
        assert TestBoundaryFlow.boundary_id in ids

    def test_list_bloks_returns_7(self, client):
        bid = TestBoundaryFlow.boundary_id
        resp = client.get(f"/api/boundaries/{bid}/bloks")
        assert resp.status_code == 200
        bloks = resp.get_json()
        assert len(bloks) == 7, f"Expected 7 bloks, got {len(bloks)}"

    def test_map_bloks_geojson_has_7_features(self, client):
        bid = TestBoundaryFlow.boundary_id
        resp = client.get(f"/api/map/bloks/{bid}")
        assert resp.status_code == 200
        fc = resp.get_json()
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 7, f"Expected 7 features, got {len(fc['features'])}"

    def test_delete_boundary_returns_ok(self, client):
        bid = TestBoundaryFlow.boundary_id
        resp = client.delete(f"/api/boundaries/{bid}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body == {"ok": True}

    def test_list_boundaries_empty_after_delete(self, client):
        resp = client.get("/api/boundaries")
        assert resp.status_code == 200
        items = resp.get_json()
        ids = [b["id"] for b in items]
        assert TestBoundaryFlow.boundary_id not in ids


# ─────────────────────────────────────────────────────────────────────────────
# Session flow
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionFlow:
    session_id = None

    def test_post_session_no_file_returns_400(self, client):
        resp = client.post(
            "/api/sessions",
            data={"nama": "Test Sesi"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_post_session_with_dummy_file_returns_201(self, client):
        dummy = (io.BytesIO(b"dummy video content"), "test_video.mp4")
        data = {
            "nama": "Sesi Test Integration",
            "tanggal_terbang": "2026-06-06",
            "videos": dummy,
        }
        resp = client.post(
            "/api/sessions",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.data}"
        body = resp.get_json()
        assert "id" in body
        assert body["nama"] == "Sesi Test Integration"
        assert body["status"] == "pending"
        TestSessionFlow.session_id = body["id"]

    def test_get_map_session_empty_featurecollection(self, client):
        sid = TestSessionFlow.session_id
        resp = client.get(f"/api/map/{sid}")
        assert resp.status_code == 200
        fc = resp.get_json()
        assert fc["type"] == "FeatureCollection"
        assert fc["features"] == []

    def test_export_csv_returns_200_csv(self, client):
        sid = TestSessionFlow.session_id
        resp = client.get(f"/api/export/{sid}/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_excel_returns_200_xlsx(self, client):
        sid = TestSessionFlow.session_id
        resp = client.get(f"/api/export/{sid}/excel")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type or "officedocument" in resp.content_type
