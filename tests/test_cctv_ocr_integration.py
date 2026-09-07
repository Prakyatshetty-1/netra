"""Integration test ensuring both CCTV/OCR extraction and Photo entity cropping coexist seamlessly."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_cases_list(client):
    res = client.get("/cases")
    assert res.status_code == 200
    cases = res.json()
    assert len(cases) >= 120


def test_photo_and_crops_graph_integration(client):
    res = client.get("/cases/18/graph")
    assert res.status_code == 200
    data = res.json()
    nodes = data.get("nodes", [])
    # Check that nodes with images exist
    nodes_with_images = [n for n in nodes if n.get("image")]
    assert len(nodes_with_images) > 0
    # Check that photo edge types exist
    photo_edges = [e for e in data.get("edges", []) if "PHOTO" in e.get("relation", "")]
    assert len(photo_edges) > 0


def test_cctv_endpoint_integration(client):
    res = client.get("/cases/18/cctv/bab193a3")
    assert res.status_code == 200
    data = res.json()
    assert data.get("video_id") == "bab193a3"
    assert data.get("status") == "COMPLETED"


def test_ocr_document_endpoint_integration(client):
    res = client.get("/cases/1/ocr/documents/b595980c")
    assert res.status_code == 200
    data = res.json()
    assert data.get("document_id") == "b595980c"
    assert data.get("filename") == "handwritten_note_1.png"
