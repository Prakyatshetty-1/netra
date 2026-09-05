"""Image upload → visual extraction draft → human confirm into GraphEdge.

Parallel to routers/extraction.py but for photo/visual evidence channels.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.routers.graph import _public
from backend.services.image_extraction_service import (
    build_photo_detections,
    confirm_image_extraction,
    detect_faces,
    detect_objects,
    draw_annotated_preview,
    extract_exif,
    map_confirmed_crops,
    save_photo_and_crops,
)
from backend.services.intelligence_service import enrich_case_graph

router = APIRouter(tags=["image_upload"])


class ConfirmedCrop(BaseModel):
    crop_id: str
    entity_type: str = "OBJECT"  # PERSON / WEAPON / OBJECT
    label: str = "object"
    confidence: float = 0.0
    included: bool = True
    linked_person_id: int | None = None
    matched_person_id: int | None = None
    matched_person_name: str | None = None
    force_create_new: bool = False
    provisional_name: str | None = None
    embedding: list[float] | None = None


class ConfirmedFace(BaseModel):
    bbox: list[float] = Field(default_factory=list)
    embedding: list[float] | None = None
    matched_person_id: int | None = None
    matched_person_name: str | None = None
    match_confidence: float | None = None
    status: str = "NEW_FACE_NO_MATCH"
    included: bool = True
    force_create_new: bool = False
    provisional_name: str | None = None


class ConfirmedObject(BaseModel):
    label: str
    confidence: float = 0.0
    bbox: list[float] = Field(default_factory=list)
    included: bool = True


class ConfirmedLocation(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    timestamp: str | None = None
    exif_present: bool = False
    included: bool = False


class ConfirmImageBody(BaseModel):
    photo_id: int | None = None
    confirmed_crops: list[ConfirmedCrop] = Field(default_factory=list)
    objects: list[ConfirmedObject] = Field(default_factory=list)
    faces: list[ConfirmedFace] = Field(default_factory=list)
    location: ConfirmedLocation | None = None
    filename: str = ""


_ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "heic", "bmp", "tiff"}


def _is_image(fn: str) -> bool:
    ext = (fn or "").rsplit(".", 1)[-1].lower()
    return ext in _ALLOWED_EXT


@router.post("/cases/{case_id}/upload-image")
async def upload_image(case_id: int, file: UploadFile = File(...)):
    if not file.filename or not _is_image(file.filename):
        raise HTTPException(400, f"Upload an image file ({', '.join(sorted(_ALLOWED_EXT))})")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")

    objects, low_conf, weapon_tag, obj_err = detect_objects(raw)
    faces, face_err = detect_faces(raw, case_id=case_id)
    location = extract_exif(raw)
    preview_url = draw_annotated_preview(raw, objects, faces, low_confidence=low_conf)

    # 1. Unified detections & entity cropping
    detections = build_photo_detections(raw, objects, low_confidence=low_conf, faces=faces)

    # 2. Persist PhotoEvidence & DetectedEntityCrop rows
    photo_id = save_photo_and_crops(case_id, file.filename, preview_url, location, detections)

    warnings = []
    for msg in (obj_err, face_err):
        if msg:
            warnings.append(msg)
    if weapon_tag == "unavailable":
        warnings.append("Object detector unavailable. Install ultralytics for YOLO detection.")

    return {
        "photo_id": photo_id,
        "filename": file.filename,
        "annotated_preview_url": preview_url,
        "detections": detections,
        "objects": objects,
        "low_confidence_flagged": low_conf,
        "faces": faces,
        "location": location,
        "weapon_model": weapon_tag,
        "warnings": warnings,
    }


@router.post("/cases/{case_id}/upload-image/confirm")
def confirm_image(case_id: int, body: ConfirmImageBody):
    loc = body.location.model_dump() if body.location else None
    if body.confirmed_crops:
        crops = [c.model_dump() for c in body.confirmed_crops]
        summary = map_confirmed_crops(
            case_id=case_id,
            photo_id=body.photo_id,
            confirmed_crops=crops,
            location_data=loc,
            filename=body.filename or "image",
        )
    else:
        objs = [o.model_dump() for o in body.objects if getattr(o, "included", True)]
        faces = [f.model_dump() for f in body.faces]
        summary = confirm_image_extraction(
            case_id=case_id,
            confirmed_objects=objs,
            confirmed_faces=faces,
            confirmed_location=loc,
            filename=body.filename or "image",
            photo_id=body.photo_id,
        )
    graph = _public(enrich_case_graph(case_id))
    return {**summary, "graph": graph}

