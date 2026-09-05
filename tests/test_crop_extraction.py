"""Test crop detection, PhotoEvidence, DetectedEntityCrop, and map_confirmed_crops."""

import io
from pathlib import Path
from PIL import Image, ImageDraw

from backend.db import ROOT, get_write_conn, query, query_one
from backend.services.graph_service import case_graph
from backend.services.image_extraction_service import (
    crop_detections,
    build_photo_detections,
    save_photo_and_crops,
    map_confirmed_crops,
)
from backend.services.intelligence_service import enrich_case_graph


def create_dummy_image():
    img = Image.new("RGB", (640, 480), color=(50, 50, 50))
    draw = ImageDraw.Draw(img)
    # Draw a "person" box
    draw.rectangle([50, 50, 200, 350], fill=(200, 100, 100))
    # Draw a "weapon" box
    draw.rectangle([250, 200, 350, 300], fill=(100, 200, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_crop_detections():
    raw = create_dummy_image()
    detections = [
        {"bbox": [50, 50, 200, 350], "label": "person", "confidence": 0.9, "entity_type": "PERSON"},
        {"bbox": [250, 200, 350, 300], "label": "knife", "confidence": 0.22, "entity_type": "WEAPON"},
    ]
    crops = crop_detections(raw, detections)
    assert len(crops) == 2
    for c in crops:
        assert "crop_id" in c
        assert "crop_image_url" in c
        assert c["crop_image_url"].startswith("/static/crops/")
        # Verify file exists on disk
        crop_file = ROOT / "frontend" / "crops" / f"{c['crop_id']}.jpg"
        assert crop_file.exists(), f"Expected crop file at {crop_file}"
        crop_img = Image.open(crop_file)
        assert crop_img.width > 0 and crop_img.height > 0
    print("test_crop_detections passed!")


def test_photo_and_crops_persistence_and_mapping():
    raw = create_dummy_image()
    case_row = query_one("SELECT CaseMasterID FROM CaseMaster LIMIT 1")
    assert case_row is not None
    case_id = case_row["CaseMasterID"]

    detections = [
        {"crop_id": "test_person_1", "bbox": [50, 50, 200, 350], "label": "person", "confidence": 0.88, "entity_type": "PERSON", "crop_image_url": "/static/crops/test_person_1.jpg"},
        {"crop_id": "test_weapon_1", "bbox": [250, 200, 350, 300], "label": "knife", "confidence": 0.22, "entity_type": "WEAPON", "crop_image_url": "/static/crops/test_weapon_1.jpg"},
    ]

    # Save to PhotoEvidence and DetectedEntityCrop
    photo_id = save_photo_and_crops(
        case_id=case_id,
        filename="test_crime_scene.jpg",
        preview_url="/annotated/test_preview.jpg",
        location={"timestamp": "2026-09-05 12:00:00", "latitude": 12.9716, "longitude": 77.5946, "included": True},
        crops=detections,
    )
    assert photo_id > 0

    # Verify rows in DB
    photo_row = query_one("SELECT * FROM PhotoEvidence WHERE PhotoID = ?", (photo_id,))
    assert photo_row is not None
    assert photo_row["FileName"] == "test_crime_scene.jpg"

    crop_rows = query("SELECT * FROM DetectedEntityCrop WHERE SourcePhotoID = ?", (photo_id,))
    assert len(crop_rows) == 2

    # Now test confirmation and relationship mapping
    confirmed_crops = [
        {
            "crop_id": "test_person_1",
            "entity_type": "PERSON",
            "label": "person",
            "confidence": 0.88,
            "included": True,
            "provisional_name": "Suspect in Test Photo",
            "force_create_new": True,
        },
        {
            "crop_id": "test_weapon_1",
            "entity_type": "WEAPON",
            "label": "knife",
            "confidence": 0.22,
            "included": True,
        },
    ]

    summary = map_confirmed_crops(
        case_id=case_id,
        photo_id=photo_id,
        confirmed_crops=confirmed_crops,
        location_data={"timestamp": "2026-09-05 12:00:00", "latitude": 12.9716, "longitude": 77.5946, "included": True},
        filename="test_crime_scene.jpg",
    )

    assert summary["edges_added"] > 0
    group_id = summary["independence_group_id"]
    assert group_id is not None

    # Check that all edges added share IndependenceGroupID
    edges = query("SELECT * FROM GraphEdge WHERE IndependenceGroupID = ?", (group_id,))
    assert len(edges) >= 3  # PERSON-PHOTO, WEAPON-PHOTO, PERSON-WEAPON, plus LOCATION

    rel_types = [e["RelationType"] for e in edges]
    assert "NEAR_WEAPON_IN_PHOTO" in rel_types
    assert "DEPICTS_OBJECT" in rel_types
    assert "DEPICTED_IN_PHOTO" in rel_types

    for e in edges:
        assert e["IndependenceGroupID"] == group_id

    # Verify that DetectedEntityCrop updated LinkedPersonID
    updated_crop = query_one("SELECT LinkedPersonID FROM DetectedEntityCrop WHERE CropID = 'test_person_1'")
    assert updated_crop["LinkedPersonID"] is not None

    # Verify that enrich_case_graph populates image on nodes
    graph_res = enrich_case_graph(case_id)
    nodes = graph_res["nodes"]
    weapon_node = next((n for n in nodes if n["id"] == "WEAPON:test_weapon_1"), None)
    assert weapon_node is not None
    assert weapon_node["image"] == "/static/crops/test_weapon_1.jpg", f"Expected weapon node image, got {weapon_node}"

    person_node = next((n for n in nodes if n["id"] == f"PERSON:{updated_crop['LinkedPersonID']}"), None)
    assert person_node is not None
    assert person_node["image"] == "/static/crops/test_person_1.jpg"

    print("test_photo_and_crops_persistence_and_mapping passed!")


if __name__ == "__main__":
    test_crop_detections()
    test_photo_and_crops_persistence_and_mapping()
    print("ALL TESTS PASSED SUCCESSFULLY!")
