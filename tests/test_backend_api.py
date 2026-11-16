import gzip
import json
from fastapi.testclient import TestClient

import backend.app as backend_app
from src.core.replay_exporter import build_demo_bundle


def test_health_and_seasons_endpoints():
    client = TestClient(backend_app.app)

    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res_root_health = client.get("/health")
    assert res_root_health.status_code == 200
    assert res_root_health.json()["status"] == "ok"

    seasons = client.get("/api/seasons")
    assert seasons.status_code == 200
    body = seasons.json()
    assert 2025 in body["seasons"]
    assert 2023 in body["seasons"]


def test_demo_manifest_and_frames_gzip():
    client = TestClient(backend_app.app)

    m_res = client.get("/api/sessions/demo/manifest")
    assert m_res.status_code == 200
    manifest = m_res.json()
    assert manifest["session_id"] == "demo"
    assert len(manifest["drivers"]) == 20

    f_res = client.get("/api/sessions/demo/frames", headers={"Accept-Encoding": "gzip"})
    assert f_res.status_code == 200
    frames = f_res.json()
    assert len(frames["t"]) == manifest["session_info"]["total_frames"]


def test_cached_session_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_app, "WEB_BUNDLE_DIR", tmp_path)
    manifest, frames = build_demo_bundle()
    manifest["session_id"] = "2025_12_R"

    bundle_dir = tmp_path / "2025_12_R"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle_dir / "frames.json.gz").write_bytes(gzip.compress(json.dumps(frames).encode("utf-8")))

    client = TestClient(backend_app.app)

    status_res = client.get("/api/sessions/2025/12/R/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "ready"

    prep_res = client.post("/api/sessions/2025/12/R/prepare")
    assert prep_res.status_code == 200
    assert prep_res.json()["status"] == "ready"

    m_res = client.get("/api/sessions/2025/12/R/manifest")
    assert m_res.status_code == 200
    assert m_res.json()["session_id"] == "2025_12_R"

    f_res = client.get("/api/sessions/2025/12/R/frames")
    assert f_res.status_code == 200
    assert "VER" in f_res.json()["drivers"]
