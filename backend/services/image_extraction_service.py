"""Visual extraction: YOLOv8 objects, face_recognition faces, EXIF location/timestamp.

Safe import pattern: if heavy ML deps are missing, we return an explicit response
with `error` populated so the frontend can surface the setup requirement (dlib/cmake
for face_recognition, ultralytics for YOLO) instead of a misleading empty result.
"""

from __future__ import annotations

import io
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from backend.db import ROOT, get_write_conn, query

ANNOTATED_DIR = ROOT / "frontend" / "annotated"
ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)

PERSON_EMBEDDING_COLUMN = "FaceEmbeddingJSON"


def _ensure_face_embedding_column() -> None:
    """Best-effort schema migration for Person.FaceEmbeddingJSON column."""
    try:
        conn = get_write_conn()
        try:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(Person)").fetchall()]
            if PERSON_EMBEDDING_COLUMN.lower() not in [c.lower() for c in cols]:
                conn.execute(
                    f"ALTER TABLE Person ADD COLUMN {PERSON_EMBEDDING_COLUMN} TEXT"
                )
                conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


_ensure_face_embedding_column()


# ---------- Object detection -----------------------------------------------------

GENERAL_CONF_THRESHOLD = 0.45
WEAPON_CLASSES = {"knife", "scissors", "baseball bat", "gun", "rifle", "pistol"}
SUPPORTED_OBJECT_CLASSES = WEAPON_CLASSES | {"person", "bottle", "backpack", "handbag", "suitcase"}
WEAPON_CONF_THRESHOLD = 0.15
DETECTION_FLOOR_CONF = 0.10

_base_model = None
_weapon_model = None
_weapon_model_tag = "uninitialized"


def _compute_iou(box1: list[float], box2: list[float]) -> float:
    """Compute Intersection over Union (IoU) between two [x1, y1, x2, y2] boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter_area <= 0:
        return 0.0

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    if union_area <= 0:
        return 0.0

    return inter_area / union_area


def _load_models():
    """Load yolov8m base model and dedicated weapon_model."""
    global _base_model, _weapon_model, _weapon_model_tag
    try:
        from ultralytics import YOLO
    except Exception as e:
        _weapon_model_tag = "unavailable"
        return None, None, f"Missing dependency ultralytics: {e}. pip install ultralytics"

    errs = []
    if _base_model is None:
        base_path = ROOT / "yolov8m.pt"
        if not base_path.exists():
            base_path = ROOT / "yolov8n.pt" if (ROOT / "yolov8n.pt").exists() else Path("yolov8m.pt")
        try:
            _base_model = YOLO(str(base_path))
        except Exception as e:
            errs.append(f"Failed to load base YOLO model: {e}")

    if _weapon_model is None:
        weapon_path = ROOT / "weapon_model.pt"
        if weapon_path.exists():
            try:
                _weapon_model = YOLO(str(weapon_path))
            except Exception as e:
                errs.append(f"Failed to load weapon model: {e}")
        else:
            _weapon_model = None

    if _weapon_model is not None and _base_model is not None:
        _weapon_model_tag = "coco-baseline-limited-classes + weapon-model-v1"
    elif _base_model is not None:
        _weapon_model_tag = "coco-baseline-limited-classes"
    else:
        _weapon_model_tag = "unavailable"

    if _base_model is None:
        return None, None, "; ".join(errs) or "No detection models available"

    return _base_model, _weapon_model, None


def _merge_detections(base_dets: list[dict], weapon_dets: list[dict]) -> list[dict]:
    """Merge detections from base COCO model and specialized weapon model.

    Deduplicates overlapping weapon boxes (preferring weapon model's classification
    and highest confidence), while ensuring weapon boxes NEVER suppress person boxes.
    """
    merged: list[dict] = []
    # Process weapon model detections first so weapon classifications take precedence
    candidates = list(weapon_dets) + list(base_dets)

    for cand in candidates:
        matched = False
        for acc in merged:
            iou = _compute_iou(cand["bbox"], acc["bbox"])
            if iou >= 0.45:
                # Rule: Never allow weapon detections to suppress person detections or vice versa
                if (cand.get("is_weapon") and acc["label"] == "person") or (
                    acc.get("is_weapon") and cand["label"] == "person"
                ):
                    continue

                # Both are weapons: duplicate detection of the same weapon
                if cand.get("is_weapon") and acc.get("is_weapon"):
                    matched = True
                    # Prefer weapon_model's classification; take maximum confidence
                    if cand.get("source") == "weapon_model" and acc.get("source") != "weapon_model":
                        acc["label"] = cand["label"]
                        acc["bbox"] = cand["bbox"]
                        acc["source"] = "weapon_model"
                    acc["confidence"] = max(acc["confidence"], cand["confidence"])
                    break

                # Same class non-weapon duplicates (e.g. overlapping person or backpack boxes)
                if cand["label"] == acc["label"]:
                    matched = True
                    acc["confidence"] = max(acc["confidence"], cand["confidence"])
                    break

        if not matched:
            merged.append(dict(cand))

    return merged


def detect_objects(image_bytes: bytes) -> tuple[list[dict], list[dict], str, str | None]:
    """Return (objects, low_confidence_flagged, weapon_model_tag, error_message_or_None).

    - objects: high-confidence detections meeting per-class threshold
      (0.15 for weapons, 0.45 for general objects)
    - low_confidence_flagged: detections between floor 0.10 and threshold, flagged for review
    Each object dict: {"label": str, "confidence": float, "bbox": [x1,y1,x2,y2], ...}
    """
    base_model, weapon_model, err = _load_models()
    if err is not None and base_model is None:
        return [], [], "unavailable", err

    try:
        from PIL import Image
    except ImportError as e:
        return [], [], "unavailable", f"Missing dependency pillow: {e}"

    try:
        img = Image.open(io.BytesIO(image_bytes))
        base_results = base_model.predict(
            source=img,
            conf=DETECTION_FLOOR_CONF,
            iou=0.5,
            agnostic_nms=False,
            verbose=False,
        )[0]
    except Exception as e:
        return [], [], _weapon_model_tag, f"Base YOLO predict failed: {e}"

    raw_base_dets = []
    names = base_results.names or {}
    boxes = getattr(base_results, "boxes", None)
    if boxes is not None:
        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].tolist() if hasattr(boxes, "xyxy") else None
            conf = float(boxes.conf[i]) if hasattr(boxes, "conf") else 0.0
            cls_idx = int(boxes.cls[i]) if hasattr(boxes, "cls") else -1
            raw_label = str(names.get(cls_idx, f"cls_{cls_idx}")).lower()
            if raw_label in SUPPORTED_OBJECT_CLASSES:
                raw_base_dets.append(
                    {
                        "label": raw_label,
                        "confidence": round(conf, 4),
                        "bbox": [round(v, 1) for v in (xyxy or [0, 0, 0, 0])],
                        "is_weapon": raw_label in WEAPON_CLASSES,
                        "source": "coco",
                    }
                )

    raw_weapon_dets = []
    if weapon_model is not None:
        try:
            weapon_results = weapon_model.predict(
                source=img,
                conf=DETECTION_FLOOR_CONF,
                iou=0.5,
                agnostic_nms=False,
                verbose=False,
            )[0]
            wnames = weapon_results.names or {}
            wboxes = getattr(weapon_results, "boxes", None)
            if wboxes is not None:
                for i in range(len(wboxes)):
                    xyxy = wboxes.xyxy[i].tolist() if hasattr(wboxes, "xyxy") else None
                    conf = float(wboxes.conf[i]) if hasattr(wboxes, "conf") else 0.0
                    cls_idx = int(wboxes.cls[i]) if hasattr(wboxes, "cls") else -1
                    raw_label = str(wnames.get(cls_idx, f"cls_{cls_idx}")).lower()
                    raw_weapon_dets.append(
                        {
                            "label": raw_label,
                            "confidence": round(conf, 4),
                            "bbox": [round(v, 1) for v in (xyxy or [0, 0, 0, 0])],
                            "is_weapon": True,
                            "source": "weapon_model",
                        }
                    )
        except Exception:
            pass  # Non-fatal: base detections still available

    merged = _merge_detections(raw_base_dets, raw_weapon_dets)

    objects = []
    low_confidence_flagged = []

    for item in merged:
        label = item["label"]
        conf = item["confidence"]
        bbox = item["bbox"]
        is_weapon = item.get("is_weapon", False)

        threshold = WEAPON_CONF_THRESHOLD if is_weapon else GENERAL_CONF_THRESHOLD

        if conf >= threshold:
            objects.append(
                {
                    "label": label,
                    "confidence": conf,
                    "bbox": bbox,
                }
            )
        elif conf >= DETECTION_FLOOR_CONF:
            low_confidence_flagged.append(
                {
                    "label": label,
                    "confidence": conf,
                    "bbox": bbox,
                    "note": "below display threshold — review manually",
                }
            )

    return objects, low_confidence_flagged, _weapon_model_tag, None


# ---------- Face detection -------------------------------------------------------

_FACE_TOLERANCE = 0.55


def _load_face_rec():
    try:
        import face_recognition  # noqa: F401
        return True, None
    except ImportError as e:
        return False, (
            "Missing dependency face_recognition. It requires dlib which needs "
            "cmake + C++ build toolchain. Install: pip install face_recognition "
            "or use a Docker base image with dlib preinstalled."
        )


def detect_faces(image_bytes: bytes, case_id: int | None = None) -> tuple[list[dict], str | None]:
    """Return (faces, error_message_or_None).

    Each face: {
      "bbox": [x1,y1,x2,y2],
      "embedding": [..] | null,
      "matched_person_id": int | null,
      "matched_person_name": str | null,
      "match_confidence": float | null,
      "status": "CANDIDATE_MATCH" | "NEW_FACE_NO_MATCH",
    }
    """
    ok, err = _load_face_rec()
    if not ok:
        return [], err
    import face_recognition
    import numpy as np

    try:
        import PIL.Image
        img_arr = np.array(PIL.Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    except Exception as e:
        return [], f"Failed to decode image for face detect: {e}"

    try:
        boxes_tlbr = face_recognition.face_locations(img_arr, model="hog")
        embeddings = face_recognition.face_encodings(img_arr, boxes_tlbr)
    except Exception as e:
        return [], f"face_recognition pipeline failed: {e}"

    # Collect existing persons with embeddings (case-scoped first, then DB-wide)
    rows_case = []
    rows_all = []
    try:
        if case_id is not None:
            rows_case = query(
                f"SELECT PersonID, FullName, {PERSON_EMBEDDING_COLUMN} AS emb FROM Person "
                f"WHERE CaseMasterID = ? AND {PERSON_EMBEDDING_COLUMN} IS NOT NULL",
                (case_id,),
            )
        rows_all = query(
            f"SELECT PersonID, FullName, {PERSON_EMBEDDING_COLUMN} AS emb FROM Person "
            f"WHERE {PERSON_EMBEDDING_COLUMN} IS NOT NULL"
        )
    except Exception:
        pass
    existing = {}
    for r in rows_all:
        existing.setdefault(r["PersonID"], r)
    for r in rows_case:
        existing[r["PersonID"]] = r
    known_ids = []
    known_embeds = []
    known_names = {}
    for pid, r in existing.items():
        try:
            arr = np.array(json.loads(r["emb"]), dtype="float64")
            if arr.shape == (128,):
                known_ids.append(pid)
                known_embeds.append(arr)
                known_names[pid] = r["FullName"]
        except Exception:
            continue

    faces = []
    for idx, box in enumerate(boxes_tlbr):
        t, r, b, l = box  # top, right, bottom, left
        bbox = [float(l), float(t), float(r), float(b)]
        emb = embeddings[idx] if idx < len(embeddings) else None
        status = "NEW_FACE_NO_MATCH"
        matched_id = None
        matched_name = None
        match_conf = None
        if emb is not None and known_embeds:
            dists = face_recognition.face_distance(known_embeds, emb)
            best_i = int(np.argmin(dists))
            best_dist = float(dists[best_i])
            if best_dist <= _FACE_TOLERANCE:
                matched_id = known_ids[best_i]
                matched_name = known_names.get(matched_id)
                match_conf = round(1.0 - best_dist, 4)
                status = "CANDIDATE_MATCH"
        faces.append(
            {
                "bbox": bbox,
                "embedding": emb.tolist() if emb is not None else None,
                "matched_person_id": matched_id,
                "matched_person_name": matched_name,
                "match_confidence": match_conf,
                "status": status,
            }
        )
    return faces, None


# ---------- EXIF extraction ------------------------------------------------------

def _dms_to_deg(dms, ref) -> float:
    d, m, s = [float(x) for x in dms]
    val = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        val = -val
    return round(val, 6)


def extract_exif(image_bytes: bytes) -> dict:
    try:
        from PIL import Image
    except ImportError as e:
        return {"exif_present": False, "error": f"Missing dependency pillow: {e}"}
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        return {"exif_present": False, "error": f"PIL decode failed: {e}"}
    raw = None
    try:
        raw = img._getexif()
    except Exception:
        raw = None
    if not raw:
        return {"exif_present": False}
    TAG_GPS_INFO = 0x8825
    TAG_DATE_ORIG = 0x9003
    out: dict = {"exif_present": True}
    try:
        date_str = raw.get(TAG_DATE_ORIG)
        if date_str:
            try:
                dt = datetime.strptime(str(date_str), "%Y:%m:%d %H:%M:%S")
                out["timestamp"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                out["timestamp_raw"] = str(date_str)
    except Exception:
        pass
    gps = raw.get(TAG_GPS_INFO)
    if gps:
        try:
            lat = _dms_to_deg(gps[2], gps[1]) if 2 in gps and 1 in gps else None
            lon = _dms_to_deg(gps[4], gps[3]) if 4 in gps and 3 in gps else None
            if lat is not None:
                out["latitude"] = lat
            if lon is not None:
                out["longitude"] = lon
        except Exception as e:
            out["gps_error"] = str(e)
    return out


# ---------- Annotated preview drawing --------------------------------------------

_COLORS = {
    "person": (255, 107, 0, 255),
    "knife": (255, 80, 80, 255),
    "scissors": (255, 150, 80, 255),
    "pistol": (255, 50, 50, 255),
    "gun": (255, 50, 50, 255),
    "rifle": (255, 50, 50, 255),
    "baseball bat": (255, 120, 80, 255),
    "bottle": (160, 91, 239, 255),
    "backpack": (91, 141, 239, 255),
    "handbag": (91, 141, 239, 255),
    "suitcase": (91, 141, 239, 255),
    "face_match": (74, 210, 158, 255),
    "face_new": (91, 141, 239, 255),
    "default": (120, 120, 120, 255),
}


def _draw_dashed_line(draw, p1: tuple[float, float], p2: tuple[float, float], fill, width: int = 2, dash_len: int = 6):
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    dist = (dx**2 + dy**2) ** 0.5
    if dist <= 0:
        return
    num_dashes = int(dist / (dash_len * 2))
    for i in range(num_dashes + 1):
        start_ratio = (i * 2 * dash_len) / dist
        end_ratio = min(1.0, ((i * 2 + 1) * dash_len) / dist)
        if start_ratio < 1.0:
            sx = x1 + dx * start_ratio
            sy = y1 + dy * start_ratio
            ex = x1 + dx * end_ratio
            ey = y1 + dy * end_ratio
            draw.line([(sx, sy), (ex, ey)], fill=fill, width=width)


def _draw_dashed_rect(draw, bbox: list[float], outline, width: int = 2, dash_len: int = 6):
    x1, y1, x2, y2 = bbox
    _draw_dashed_line(draw, (x1, y1), (x2, y1), outline, width, dash_len)
    _draw_dashed_line(draw, (x2, y1), (x2, y2), outline, width, dash_len)
    _draw_dashed_line(draw, (x2, y2), (x1, y2), outline, width, dash_len)
    _draw_dashed_line(draw, (x1, y2), (x1, y1), outline, width, dash_len)


def draw_annotated_preview(
    image_bytes: bytes,
    objects: list[dict],
    faces: list[dict],
    low_confidence: list[dict] | None = None,
) -> str:
    """Draw boxes on a copy and return a URL path like /annotated/<uuid>.jpg.

    Draws regular objects with solid boxes, low-confidence flagged objects with
    dashed amber boxes, and faces with status-colored boxes.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception:
        return ""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 13)
    except Exception:
        font = ImageFont.load_default()

    # 1. Low confidence flagged detections (amber dashed boxes + warning tag)
    amber_color = (245, 166, 35, 230)
    for lo in low_confidence or []:
        bbox = lo.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = bbox
        _draw_dashed_rect(draw, [x1, y1, x2, y2], outline=amber_color, width=2, dash_len=5)
        label = f"? {lo.get('label')} {round(100 * lo.get('confidence', 0))}%"
        text_bbox = draw.textbbox((x1, max(0, y1 - 16)), label, font=font)
        draw.rectangle(text_bbox, fill=(*amber_color[:3], 180))
        draw.text((x1 + 2, max(0, y1 - 15)), label, fill="black", font=font)

    # 2. Confirmed high-confidence objects / weapons (solid boxes)
    for o in objects or []:
        color = _COLORS.get(o.get("label", ""), _COLORS["default"])
        bbox = o.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = bbox
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        label = f"{o.get('label')} {round(100 * o.get('confidence', 0))}%"
        text_bbox = draw.textbbox((x1, max(0, y1 - 16)), label, font=font)
        draw.rectangle(text_bbox, fill=(*color[:3], 210))
        draw.text((x1 + 2, max(0, y1 - 15)), label, fill="white", font=font)

    # 3. Faces
    for f in faces or []:
        is_match = f.get("status") == "CANDIDATE_MATCH"
        color = _COLORS["face_match"] if is_match else _COLORS["face_new"]
        bbox = f.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = bbox
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        if is_match:
            label = f"MATCH #{f.get('matched_person_id')} {f.get('matched_person_name') or ''}"
        else:
            label = "NEW FACE"
        text_bbox = draw.textbbox((x1, max(0, y1 - 16)), label, font=font)
        draw.rectangle(text_bbox, fill=(*color[:3], 220))
        draw.text((x1 + 2, max(0, y1 - 15)), label, fill="white", font=font)

    combined = Image.alpha_composite(img, overlay).convert("RGB")
    name = f"{uuid.uuid4().hex}.jpg"
    out_path = ANNOTATED_DIR / name
    combined.save(out_path, format="JPEG", quality=85)
    return f"/annotated/{name}"


# ---------- Confirm (write to DB) ------------------------------------------------

from backend.services.extraction_service import _insert_group, _match_or_create_person  # noqa: E402


def confirm_image_extraction(
    case_id: int,
    confirmed_objects: list[dict],
    confirmed_faces: list[dict],
    confirmed_location: dict | None,
    filename: str,
) -> dict:
    """Persist investigator-approved image evidence into GraphEdge + Person embeddings."""
    conn = get_write_conn()
    created_nodes = []
    edges_added = 0
    try:
        cur = conn.cursor()
        # 1. Group node to represent the photo itself
        photo_gid = _insert_group(cur, case_id, f"Photo: {filename}")
        photo_node_key = ("PHOTO", photo_gid)
        created_nodes.append({"type": "PHOTO", "label": filename, "id": photo_gid})
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        exif_dt = confirmed_location.get("timestamp") if confirmed_location else None
        exif_dt_parsed = exif_dt or now

        # 2. Objects / weapons
        obj_to_node = {}
        for o in confirmed_objects or []:
            lab = (o.get("label") or "OBJECT").upper()
            if o.get("label") == "person":
                continue  # persons handled under faces
            gid = _insert_group(cur, case_id, f"{lab} (from {filename})")
            key = (lab, gid)
            obj_to_node[(o.get("label") or "").lower()] = key
            created_nodes.append({"type": lab, "label": o.get("label"), "id": gid})
            conf = float(o.get("confidence") or 0.5)
            cur.execute(
                """
                INSERT INTO GraphEdge (
                    CaseMasterID, SourceEntityType, SourceEntityID,
                    TargetEntityType, TargetEntityID, RelationType, EventDateTime,
                    SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'IMAGE_UPLOAD', NULL, ?, ?)
                """,
                (
                    case_id,
                    "EVIDENCE_GROUP", photo_gid,
                    "EVIDENCE_GROUP", gid,
                    "DEPICTS_OBJECT", exif_dt_parsed,
                    conf, photo_gid,
                ),
            )
            edges_added += 1

        # 3. Faces
        face_person_ids = []
        name_to_node: dict[tuple[str, str], tuple[str, int]] = {}
        for f in confirmed_faces or []:
            if not f.get("included", True):
                continue
            pid = f.get("matched_person_id")
            create_new = f.get("force_create_new") or (pid is None)
            name = (f.get("matched_person_name") or "").strip()
            if create_new or not name:
                # Create a new unresolved Person; name it "Unresolved Person #N" if needed
                ordinal = len([n for n in created_nodes if n["type"] == "PERSON"]) + 1
                fallback_name = f.get("provisional_name") or f"Unresolved Person {ordinal}"
                pid = _match_or_create_person(cur, case_id, fallback_name)
                created_nodes.append({"type": "PERSON", "label": fallback_name, "id": pid})
            elif pid is not None:
                # existing matched person — confirm selection (pid already set)
                pass
            face_person_ids.append(pid)
            name_to_node[(f"person:{pid}".lower(), "PERSON")] = ("PERSON", pid)

            # Store embedding if we have one
            emb = f.get("embedding")
            if pid is not None and emb:
                try:
                    cur.execute(
                        f"UPDATE Person SET {PERSON_EMBEDDING_COLUMN} = ? WHERE PersonID = ?",
                        (json.dumps(emb), pid),
                    )
                except Exception:
                    pass

            # DEPICTED_IN_PHOTO edge between person and photo group
            conf = float(f.get("match_confidence") or 0.5)
            cur.execute(
                """
                INSERT INTO GraphEdge (
                    CaseMasterID, SourceEntityType, SourceEntityID,
                    TargetEntityType, TargetEntityID, RelationType, EventDateTime,
                    SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'IMAGE_UPLOAD', NULL, ?, ?)
                """,
                (
                    case_id,
                    "PERSON", pid,
                    "EVIDENCE_GROUP", photo_gid,
                    "DEPICTED_IN_PHOTO", exif_dt_parsed,
                    conf, photo_gid,
                ),
            )
            edges_added += 1

        # CO_APPEARS_IN_PHOTO between every pair of persons in the same photo
        for i, a in enumerate(face_person_ids):
            for b in face_person_ids[i + 1 :]:
                cur.execute(
                    """
                    INSERT INTO GraphEdge (
                        CaseMasterID, SourceEntityType, SourceEntityID,
                        TargetEntityType, TargetEntityID, RelationType, EventDateTime,
                        SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'IMAGE_UPLOAD', NULL, ?, ?)
                    """,
                    (
                        case_id,
                        "PERSON", a,
                        "PERSON", b,
                        "CO_APPEARS_IN_PHOTO", exif_dt_parsed,
                        0.75, photo_gid,
                    ),
                )
                edges_added += 1

        # 4. EXIF location / timestamp
        if confirmed_location and confirmed_location.get("included"):
            parts = []
            if confirmed_location.get("latitude") is not None:
                parts.append(str(confirmed_location["latitude"]))
            if confirmed_location.get("longitude") is not None:
                parts.append(str(confirmed_location["longitude"]))
            loc_label = f"Photo Location ({', '.join(parts) or 'from EXIF'})"
            loc_gid = _insert_group(cur, case_id, loc_label)
            created_nodes.append({"type": "LOCATION", "label": loc_label, "id": loc_gid})
            cur.execute(
                """
                INSERT INTO GraphEdge (
                    CaseMasterID, SourceEntityType, SourceEntityID,
                    TargetEntityType, TargetEntityID, RelationType, EventDateTime,
                    SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'EXIF', NULL, ?, ?)
                """,
                (
                    case_id,
                    "EVIDENCE_GROUP", photo_gid,
                    "EVIDENCE_GROUP", loc_gid,
                    "PHOTOGRAPHED_AT", exif_dt_parsed,
                    0.9, photo_gid,
                ),
            )
            edges_added += 1

        conn.commit()
        return {"created": created_nodes, "edges_added": edges_added}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
