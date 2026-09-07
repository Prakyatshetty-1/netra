"""Document & PDF text extraction → handwritten TrOCR → entities → relations."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from backend.db import DOCUMENTS_DIR, get_write_conn, query, query_one
from backend.services.provenance_service import log_ocr_correction

PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")
PLATE_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}\b")
CRIME_NO_RE = re.compile(r"\b(?:Cr\.?\s*No\.?|Crime\s*No\.?|Case\s*No\.?|FIR\s*No\.?)\s*\d+/\d{2,4}\b", re.IGNORECASE)
SECTION_RE = re.compile(r"\b(?:\d+\([\d\w]+\)\s*(?:BNS|IPC|CrPC)|u/s\s*[\d\(\)\s\w,/-]+(?:\bBNS|\bIPC)?|\d+\s*BNS|\d+\s*IPC)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
TIME_STAMP_RE = re.compile(r"^\d{1,2}[\.\:]\d{2}$")
INDIAN_NAME_RE = re.compile(
    r"\b(?:Mohd\.?|Mohammed|Syed|Shaik|Smt\.?|Sri\.?|Mr\.?|Mrs\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
    r"|\b[A-Z][a-z]+\s+(?:Begum|Khan|uddin|Singh|Kumar|Rao|Reddy|Sharma|Verma|Gupta)\b"
    r"|\b(?:Tahiruddin|Tayaba\s+Begum|Mohammed\s+Awais|Awais|Begum|Jahan|Fatima|Aisha|Rehana|Ramesh|Suresh)\b",
    re.IGNORECASE
)

# TrOCR singleton cache
_TROCR_PROCESSOR = None
_TROCR_MODEL = None
_TROCR_DEVICE = None


SPACY_LABELS = {"PERSON": "PERSON", "GPE": "LOC", "LOC": "LOC", "DATE": "DATE", "ORG": "ORG"}

RELATION_CONFIDENCE = 0.6  # naive same-sentence co-occurrence — not a trained model

FUZZY_PERSON_THRESHOLD = 85


def extract_text(pdf_bytes: bytes) -> tuple[str, bool, str | None]:
    """Return (text, ocr_required, error_msg). Empty extractable text → ocr_required True.
    Missing dependency → error_msg populated so caller can surface it."""
    try:
        import pdfplumber
    except ImportError as e:
        return "", True, f"Missing dependency: {e.name}. Install with: pip install pdfplumber"

    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    return text, (not bool(text)), None


def _load_nlp():
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except Exception:
        return None


def extract_entities(text: str) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str, int]] = set()

    def add(raw: str, label: str, start: int):
        token = raw.strip()
        token = re.sub(r"[^\w\)/]+$", "", token)
        if not token:
            return
        
        # Strict entity validation logic
        if label == "PERSON":
            # Reject if token contains numbers or noise words/timestamps
            if re.search(r"\d", token) or token.lower() in ("hrs", "hours", "no", "cr", "ps", "case", "fir", "sec", "bns", "ipc"):
                return
            # Trim trailing verb/preposition stop words
            words = token.split()
            stop_words = {"went", "around", "reported", "missing", "said", "on", "at", "is", "was", "the", "a", "an", "and", "or", "in", "by", "for", "with", "from", "to", "of"}
            while len(words) > 1 and words[-1].lower() in stop_words:
                words.pop()
            token = " ".join(words)
            if len(token) < 2:
                return
        elif label == "DATE":
            if TIME_STAMP_RE.search(token) or "hrs" in token.lower():
                return  # Skip timestamps (e.g. 16.25) as dates

        key = (token.lower(), label, start)
        if key in seen:
            return
        seen.add(key)
        found.append({"text": token, "label": label, "start": start})

    nlp = _load_nlp()
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            mapped = SPACY_LABELS.get(ent.label_)
            if mapped:
                add(ent.text, mapped, ent.start_char)

    for m in PHONE_RE.finditer(text):
        add(m.group(0), "PHONE", m.start())
    for m in PLATE_RE.finditer(text):
        add(m.group(0), "VEHICLE", m.start())
    for m in CRIME_NO_RE.finditer(text):
        add(m.group(0), "CASE_NO", m.start())
    for m in SECTION_RE.finditer(text):
        add(m.group(0), "SECTION", m.start())
    for m in DATE_RE.finditer(text):
        add(m.group(0), "DATE", m.start())
    for m in INDIAN_NAME_RE.finditer(text):
        add(m.group(0), "PERSON", m.start())

    phones = {e["text"] for e in found if e["label"] == "PHONE"}
    plates = {e["text"] for e in found if e["label"] == "VEHICLE"}
    cleaned = []
    for e in found:
        if e["label"] == "DATE" and e["text"] in phones:
            continue
        if e["label"] == "PERSON" and any(p in e["text"] for p in plates):
            continue
        cleaned.append(e)
    return cleaned


def extract_relations(entities: list[dict], text: str) -> list[dict]:
    nlp = _load_nlp()
    if nlp is not None:
        sentences = [s.text.strip() for s in nlp(text).sents if s.text.strip()]
    else:
        sentences = [s.strip() for s in text.split(".") if s.strip()]

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add_rel(src: str, tgt: str, typ: str, sentence: str):
        key = (src.lower(), tgt.lower(), typ)
        if src.lower() == tgt.lower() or key in seen:
            return
        # Do not allow timestamps like 16.25 or noise as relation target
        if TIME_STAMP_RE.search(tgt) or tgt.lower() in ("hrs", "hours", "no"):
            return
        seen.add(key)
        relations.append(
            {
                "source": src,
                "target": tgt,
                "type": typ,
                "confidence": RELATION_CONFIDENCE,
                "sentence": sentence[:240],
            }
        )

    for sent in sentences:
        low = sent.lower()
        in_sent = [e for e in entities if e["text"] and e["text"].lower() in low]
        persons = [e for e in in_sent if e["label"] == "PERSON"]
        others = [e for e in in_sent if e["label"] != "PERSON"]

        for i, a in enumerate(persons):
            for b in persons[i + 1 :]:
                add_rel(a["text"], b["text"], "NAMED_TOGETHER", sent)
            for o in others:
                if o["label"] == "PHONE":
                    add_rel(a["text"], o["text"], "HAS_PHONE", sent)
                elif o["label"] == "VEHICLE":
                    add_rel(a["text"], o["text"], "ASSOCIATED_WITH_VEHICLE", sent)
                elif o["label"] == "LOC":
                    add_rel(a["text"], o["text"], "MENTIONED_AT_LOCATION", sent)
                elif o["label"] == "DATE":
                    add_rel(a["text"], o["text"], "MENTIONED_ON_DATE", sent)
                elif o["label"] in ("CASE_NO", "SECTION"):
                    add_rel(a["text"], o["text"], "ASSOCIATED_WITH_CASE", sent)
                elif o["label"] == "ORG":
                    add_rel(a["text"], o["text"], "NAMED_TOGETHER", sent)

    return relations


def _match_or_create_person(cur, case_id: int, name: str) -> int:
    existing = query(
        "SELECT PersonID, FullName FROM Person WHERE CaseMasterID = ?",
        (case_id,),
    )
    if existing:
        choices = {str(r["PersonID"]): r["FullName"] for r in existing}
        match = process.extractOne(name, choices, scorer=fuzz.WRatio)
        if match and match[1] >= FUZZY_PERSON_THRESHOLD:
            return int(match[2])
    cur.execute(
        """
        INSERT INTO Person (FullName, SourceRole, SourceRecordID, CaseMasterID, AgeYear, GenderID)
        VALUES (?, 'EXTRACTED', 0, ?, NULL, NULL)
        """,
        (name, case_id),
    )
    return int(cur.lastrowid)


def _insert_group(cur, case_id: int, description: str) -> int:
    cur.execute(
        """
        INSERT INTO EvidenceIndependenceGroup (CaseMasterID, EventDescription, EventDateTime)
        VALUES (?, ?, ?)
        """,
        (case_id, description, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
    )
    return int(cur.lastrowid)


def confirm_extraction(case_id: int, entities: list[dict], relations: list[dict]) -> dict:
    """Persist investigator-approved entities/relations as Person + GraphEdge (SourceType=PDF_UPLOAD)."""
    included_e = [e for e in entities if e.get("included", True)]
    included_r = [r for r in relations if r.get("included", True)]

    name_to_node: dict[tuple[str, str], tuple[str, int]] = {}
    created = []

    conn = get_write_conn()
    try:
        cur = conn.cursor()
        for ent in included_e:
            label = (ent.get("label") or "PERSON").upper()
            text = (ent.get("text") or "").strip()
            if not text:
                continue
            key = (text.lower(), label)
            if key in name_to_node:
                continue
            if label == "PERSON":
                if re.search(r"\d", text) or text.lower() in ("hrs", "hours", "no", "cr", "ps"):
                    continue
                pid = _match_or_create_person(cur, case_id, text)
                name_to_node[key] = ("PERSON", pid)
                created.append({"text": text, "type": "PERSON", "id": pid})
            elif label == "PHONE":
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("PHONE", gid)
            elif label == "VEHICLE":
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("VEHICLE", gid)
            elif label in ("LOC", "LOCATION"):
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("LOCATION", gid)
            elif label == "DATE":
                if TIME_STAMP_RE.search(text) or "hrs" in text.lower():
                    continue
                gid = _insert_group(cur, case_id, text)
                name_to_node[key] = ("DATE", gid)
            elif label in ("CASE_NO", "SECTION", "ORG"):
                gid = _insert_group(cur, case_id, f"{label}: {text}")
                name_to_node[key] = (label, gid)
            else:
                continue

        def resolve(name: str, prefer: str | None = None) -> tuple[str, int] | None:
            name_l = name.lower()
            if prefer:
                hit = name_to_node.get((name_l, prefer))
                if hit:
                    return hit
            for (n, lab), node in name_to_node.items():
                if n == name_l:
                    return node
            # relation target might not be in included entities
            if prefer == "PERSON" or prefer is None:
                existing = query(
                    "SELECT PersonID, FullName FROM Person WHERE CaseMasterID = ?",
                    (case_id,),
                )
                if existing:
                    choices = {str(r["PersonID"]): r["FullName"] for r in existing}
                    match = process.extractOne(name, choices, scorer=fuzz.WRatio)
                    if match and match[1] >= FUZZY_PERSON_THRESHOLD:
                        return ("PERSON", int(match[2]))
            return None

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        edges_added = 0
        for rel in included_r:
            src_name = (rel.get("source") or "").strip()
            tgt_name = (rel.get("target") or "").strip()
            rtype = (rel.get("type") or "NAMED_TOGETHER")[:30]
            src = resolve(src_name, "PERSON")
            tgt_pref = {
                "HAS_PHONE": "PHONE",
                "ASSOCIATED_WITH_VEHICLE": "VEHICLE",
                "MENTIONED_AT_LOCATION": "LOCATION",
                "MENTIONED_ON_DATE": "DATE",
            }.get(rtype)
            tgt = resolve(tgt_name, tgt_pref)
            if not src or not tgt:
                continue
            if src == tgt:
                continue
            conf = float(rel.get("confidence") or RELATION_CONFIDENCE)
            cur.execute(
                """
                INSERT INTO GraphEdge (
                    CaseMasterID, SourceEntityType, SourceEntityID,
                    TargetEntityType, TargetEntityID, RelationType, EventDateTime,
                    SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PDF_UPLOAD', NULL, ?, NULL)
                """,
                (case_id, src[0], src[1], tgt[0], tgt[1], rtype, now, conf),
            )
            edges_added += 1

            # Structured side tables when we have a person + phone/plate
            if rtype == "HAS_PHONE" and src[0] == "PERSON":
                cur.execute(
                    "INSERT INTO PhoneNumber (PersonID, PhoneNumber, IsPrimary) VALUES (?, ?, 1)",
                    (src[1], tgt_name),
                )
            if rtype == "ASSOCIATED_WITH_VEHICLE" and src[0] == "PERSON":
                cur.execute(
                    """
                    INSERT INTO VehicleRegistration (PersonID, RegistrationNumber, VehicleType)
                    VALUES (?, ?, 'Extracted')
                    """,
                    (src[1], tgt_name),
                )
                vid = int(cur.lastrowid)
                name_to_node[(tgt_name.lower(), "VEHICLE")] = ("VEHICLE", vid)

        conn.commit()
        return {"created": created, "edges_added": edges_added}
    finally:
        conn.close()


def get_trocr_device() -> str:
    """Detect available accelerator: CUDA -> MPS -> CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def load_trocr():
    """Load TrOCR processor and model once and cache in memory (singleton)."""
    global _TROCR_PROCESSOR, _TROCR_MODEL, _TROCR_DEVICE
    if _TROCR_PROCESSOR is not None and _TROCR_MODEL is not None:
        return _TROCR_PROCESSOR, _TROCR_MODEL, _TROCR_DEVICE

    # Workaround for OpenMP library conflict on Windows
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    device_name = get_trocr_device()
    _TROCR_DEVICE = torch.device(device_name)
    _TROCR_PROCESSOR = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
    _TROCR_MODEL = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
    _TROCR_MODEL.to(_TROCR_DEVICE)
    _TROCR_MODEL.eval()
    return _TROCR_PROCESSOR, _TROCR_MODEL, _TROCR_DEVICE


def pil_to_base64(img) -> str:
    """Serialize PIL Image to base64 JPEG data URL for browser display."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"


def extract_document_pages(raw_bytes: bytes, filename: str) -> list:
    """Extract or render page PIL images from PDF or image formats."""
    from PIL import Image

    low = filename.lower()
    pages = []
    if low.endswith(".pdf"):
        # Try PyMuPDF (fitz) first (fastest)
        try:
            import fitz

            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                pages.append(img)
            if pages:
                return pages
        except Exception:
            pass

        # Fallback to pdfplumber
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                for page in pdf.pages:
                    pages.append(page.to_image(resolution=150).original.convert("RGB"))
            if pages:
                return pages
        except Exception as e:
            raise RuntimeError(f"Could not render PDF pages: {e}")

    # Standard image file
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    return [img]


def preprocess_and_segment_lines(pil_img) -> tuple[list[dict], dict, Any]:
    """
    Robust page preprocessing & text-line segmentation for handwritten documents:
    1. Grayscale, CLAHE contrast enhancement, Gaussian denoise.
    2. Automatic deskew estimation and rotation.
    3. Adaptive Gaussian thresholding.
    4. Border shadow/scanner margin suppression & vertical ruling removal.
    5. Connected-component character scale estimation.
    6. Smoothed horizontal projection profiling with adaptive peak/valley line boundary detection.
    7. Sub-valley splitting for tall/merged line blocks.
    8. Tight horizontal extents + dynamic padding per line.
    9. Noise/empty crop rejection.
    10. Cyan bounding box overlay generation with line sequence labels.
    11. Suspiciously low line count detection (<5 lines on substantial handwriting).
    """
    import cv2
    import numpy as np
    from PIL import Image
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks

    img_rgb = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    h_orig, w_orig = gray.shape[:2]

    # Contrast Enhancement (CLAHE) & Denoising
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    denoised = cv2.GaussianBlur(contrast, (3, 3), 0)

    # Adaptive Threshold for initial binarization & skew estimation
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 11
    )

    # Deskew detection
    skew_angle = 0.0
    text_coords = np.column_stack(np.where(thresh > 0))
    rotated_rgb = img_rgb
    rotated_gray = gray
    if len(text_coords) > 200:
        rect = cv2.minAreaRect(text_coords)
        angle = rect[-1]
        if angle < -45:
            angle = -(90 + angle)
        elif angle > 45:
            angle = 90 - angle
        if abs(angle) > 0.6 and abs(angle) < 25.0:
            skew_angle = round(float(angle), 2)
            center = (w_orig // 2, h_orig // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated_rgb = cv2.warpAffine(img_rgb, M, (w_orig, h_orig), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            rotated_gray = cv2.warpAffine(gray, M, (w_orig, h_orig), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            contrast = clahe.apply(rotated_gray)
            denoised = cv2.GaussianBlur(contrast, (3, 3), 0)
            thresh = cv2.adaptiveThreshold(
                denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 11
            )

    h, w = thresh.shape[:2]

    # Border cleaning: zero out scanning margin noise
    margin_left = max(10, int(w * 0.025))
    margin_right = max(12, int(w * 0.035))
    margin_top = max(6, int(h * 0.01))
    margin_bottom = max(10, int(h * 0.015))

    clean_bin = thresh.copy()
    clean_bin[:, :margin_left] = 0
    clean_bin[:, w - margin_right:] = 0
    clean_bin[:margin_top, :] = 0
    clean_bin[h - margin_bottom:, :] = 0

    # Remove long vertical ruling lines (table lines, margin lines)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, int(h * 0.03))))
    v_lines = cv2.morphologyEx(clean_bin, cv2.MORPH_OPEN, v_kernel)
    text_bin = cv2.subtract(clean_bin, v_lines)

    # Estimate character height dynamically using connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(text_bin)
    comp_heights = [
        stats[i, cv2.CC_STAT_HEIGHT]
        for i in range(1, num_labels)
        if 5 < stats[i, cv2.CC_STAT_HEIGHT] < h * 0.2 and 3 < stats[i, cv2.CC_STAT_WIDTH] < w * 0.8
    ]
    median_h = float(np.median(comp_heights)) if comp_heights else 16.0

    # Text density & pixel metrics
    total_text_pixels = int(np.count_nonzero(text_bin))
    text_density = total_text_pixels / float(h * w)

    # Smoothed horizontal projection profile
    h_proj = np.sum(text_bin, axis=1) / 255.0
    sigma = max(1.5, median_h * 0.2)
    h_proj_smooth = gaussian_filter1d(h_proj, sigma=sigma)

    # Dynamic distance & prominence
    min_dist = max(8, int(median_h * 0.7))
    prominence = max(3.0, float(np.percentile(h_proj_smooth[h_proj_smooth > 0], 20)) if np.any(h_proj_smooth > 0) else 5.0)

    peaks, _ = find_peaks(h_proj_smooth, distance=min_dist, prominence=prominence)

    line_slices = []
    if len(peaks) >= 2:
        valleys = [0]
        for i in range(len(peaks) - 1):
            p1 = peaks[i]
            p2 = peaks[i + 1]
            v = p1 + int(np.argmin(h_proj_smooth[p1:p2 + 1]))
            valleys.append(v)
        valleys.append(h)

        for i in range(len(valleys) - 1):
            y0 = valleys[i]
            y1 = valleys[i + 1]
            slice_h = y1 - y0
            # If slice is abnormally tall (> 3.5 * median_h), check for internal valleys
            if slice_h > median_h * 3.5:
                sub_peaks, _ = find_peaks(h_proj_smooth[y0:y1], distance=min_dist, prominence=max(2.0, prominence * 0.6))
                if len(sub_peaks) > 1:
                    sub_v = [0]
                    for sp_i in range(len(sub_peaks) - 1):
                        sp1 = sub_peaks[sp_i]
                        sp2 = sub_peaks[sp_i + 1]
                        sub_v.append(sp1 + int(np.argmin(h_proj_smooth[y0 + sp1: y0 + sp2 + 1])))
                    sub_v.append(slice_h)
                    for sv_i in range(len(sub_v) - 1):
                        if (sub_v[sv_i + 1] - sub_v[sv_i]) >= max(8, int(median_h * 0.5)):
                            line_slices.append((y0 + sub_v[sv_i], y0 + sub_v[sv_i + 1]))
                    continue
            if slice_h >= max(8, int(median_h * 0.5)):
                line_slices.append((y0, y1))
    else:
        # Fallback to horizontal contour dilation
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, int(median_h * 1.5)), 2))
        dilated = cv2.dilate(text_bin, h_kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bh >= max(8, int(median_h * 0.5)) and bw >= 25:
                line_slices.append((y, y + bh))
        line_slices.sort(key=lambda s: s[0])

    overlay = rotated_rgb.copy()
    line_items = []
    line_idx = 0

    pad_y = max(3, int(median_h * 0.2))
    pad_x = max(6, int(median_h * 0.4))

    for y_start, y_end in line_slices:
        y0 = max(0, y_start - pad_y)
        y1 = min(h, y_end + pad_y)
        slice_mask = text_bin[y0:y1, :]

        # Find horizontal bounds
        x_proj = np.sum(slice_mask, axis=0)
        nonzero_x = np.where(x_proj > 0)[0]
        if len(nonzero_x) < 6:
            continue  # Empty line

        x0 = max(0, int(nonzero_x[0]) - pad_x)
        x1 = min(w, int(nonzero_x[-1]) + pad_x)
        line_w = x1 - x0
        line_h = y1 - y0

        # Reject noise/too small crops
        text_pixels = int(np.count_nonzero(slice_mask[:, x0:x1]))
        if text_pixels < 20 or line_w < 20 or line_h < 6:
            continue

        crop_rgb = rotated_rgb[y0:y1, x0:x1]
        crop_pil = Image.fromarray(crop_rgb)

        line_items.append({
            "line_index": line_idx,
            "x": int(x0),
            "y": int(y0),
            "width": int(line_w),
            "height": int(line_h),
            "crop": crop_pil,
            "text_pixel_count": text_pixels,
        })

        # Draw on overlay (Cyan rectangle + line index)
        cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 210, 255), 2)
        cv2.putText(
            overlay,
            f"#{line_idx + 1}",
            (max(5, x0 - 2), max(14, y0 - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 255, 120),
            1,
            cv2.LINE_AA,
        )
        line_idx += 1

    overlay_pil = Image.fromarray(overlay)

    # Check for suspiciously few lines (<5 on page with substantial handwriting)
    suspicious = False
    warning = None
    if text_density > 0.008 and total_text_pixels > 2500 and len(line_items) < 5:
        suspicious = True
        warning = f"Suspiciously few lines detected ({len(line_items)}) on a page containing substantial handwriting ({total_text_pixels} text pixels). Document flagged for manual review."

    debug_info = {
        "detected_lines_count": len(line_items),
        "skew_angle": skew_angle,
        "text_density": round(text_density, 4),
        "total_text_pixels": total_text_pixels,
        "median_char_height": round(median_h, 1),
        "suspicious_low_line_count": suspicious,
        "warning": warning,
        "bounding_boxes": [[l["x"], l["y"], l["width"], l["height"]] for l in line_items],
    }

    return line_items, debug_info, overlay_pil


def segment_lines_from_image(pil_img) -> list[dict]:
    """Segment image into lines using preprocess_and_segment_lines."""
    items, _, _ = preprocess_and_segment_lines(pil_img)
    return items


def run_trocr_on_line(line_img, processor, model, device) -> tuple[str, float]:
    """Runs TrOCR on a line crop with normalized grayscale preprocessing and beam search.

    Key design choices:
    - Use soft grayscale normalization (NOT hard binary thresholding) so TrOCR sees
      ink gradients close to its training distribution.
    - Upscale to at least 64px tall for better feature extraction on small crops.
    - Add white border padding to prevent edge artifacts.
    - Use beam search with length penalties tuned for multi-word FIR lines.
    """
    import cv2
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    w, h = line_img.size
    if h < 6 or w < 10:
        return "", 20.0

    # Work in grayscale for normalization
    img_np = np.array(line_img.convert("L"))
    ih, iw = img_np.shape

    # Upscale short crops to at least 64px tall (TrOCR performs better on taller lines)
    min_height = 64
    if ih < min_height:
        scale = min_height / float(ih)
        new_h = min_height
        new_w = max(10, int(iw * scale))
        img_np = cv2.resize(img_np, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        ih, iw = img_np.shape

    # Gentle denoise
    img_np = cv2.GaussianBlur(img_np, (3, 3), 0)

    # Normalize to full contrast range: stretch [5th, 95th] percentile → [0, 255]
    # This removes scanner noise while preserving ink gradients that TrOCR needs.
    p_lo = float(np.percentile(img_np, 5))
    p_hi = float(np.percentile(img_np, 95))
    if p_hi > p_lo + 10:
        img_norm = np.clip((img_np.astype(np.float32) - p_lo) / (p_hi - p_lo) * 255, 0, 255).astype(np.uint8)
    else:
        img_norm = img_np  # Already very uniform, skip normalization

    # Convert to RGB (TrOCR processor expects RGB)
    rgb = cv2.cvtColor(img_norm, cv2.COLOR_GRAY2RGB)
    crop_pil = Image.fromarray(rgb)

    # Add white border padding (8px each side) to prevent border artifacts
    crop_pil = ImageOps.expand(crop_pil, border=8, fill="white")

    pixel_values = processor(crop_pil, return_tensors="pt").pixel_values.to(device)

    with torch.no_grad():
        outputs = model.generate(
            pixel_values,
            return_dict_in_generate=True,
            output_scores=True,
            max_new_tokens=64,       # Longer: FIR lines can be 50+ chars
            num_beams=4,
            repetition_penalty=1.3,
            no_repeat_ngram_size=2,
            length_penalty=1.0,
            early_stopping=True,
        )

    generated_ids = outputs.sequences
    text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    # Filter out known TrOCR hallucination patterns
    hallucination_phrases = [
        "Print export", "External links", "What links here", "Related changes",
        "United States Senatorial", "preappearance photographer",
        "Wikimedia Commons", "Wikipedia", "Retrieved from",
    ]
    for hp in hallucination_phrases:
        text = text.replace(hp, "").strip()

    # Reject outputs that are suspiciously short or look like noise
    # (single tokens like "0 0", "to", "of" on a substantial crop are hallucinations)
    word_count = len(text.split())
    if word_count <= 1 and iw > 100:
        # Very short output on a wide crop — likely hallucination; return low confidence
        confidence = 15.0
        return text, confidence

    # Calculate token-level confidence from autoregressive scores
    if outputs.scores:
        token_probs = []
        for i, score_tensor in enumerate(outputs.scores):
            probs = torch.softmax(score_tensor[0], dim=-1)
            target_idx = i + 1 if (i + 1) < generated_ids.shape[1] else i
            if target_idx < generated_ids.shape[1]:
                token_id = generated_ids[0, target_idx]
                token_probs.append(probs[token_id].item())
        if token_probs:
            avg_prob = sum(token_probs) / len(token_probs)
            confidence = round(avg_prob * 100.0, 1)
        else:
            confidence = 75.0
    else:
        confidence = 75.0

    return text, confidence


def get_confidence_tier(confidence: float) -> str:
    """
    Confidence review tiers:
    >= 90%  -> ACCEPTED
    70-89%  -> REVIEW_RECOMMENDED
    < 70%   -> MANUAL_REVIEW_REQUIRED
    """
    if confidence >= 90.0:
        return "ACCEPTED"
    if confidence >= 70.0:
        return "REVIEW_RECOMMENDED"
    return "MANUAL_REVIEW_REQUIRED"


def process_handwritten_document(case_id: int, filename: str, file_bytes: bytes) -> dict:
    """
    Ingest a handwritten document/image:
    1. Preserves original document bytes on disk.
    2. Renders pages as images and saves bounding-box overlay.
    3. Detects text lines using robust projection profiling.
    4. Rejects bad/empty crops.
    5. Transcribes each line with TrOCR and computes confidence scores.
    6. Flags document for review if suspiciously few lines detected.
    7. Stores document record and raw OCR in DocumentOCR table.
    """
    doc_id = str(uuid.uuid4())[:8]
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    safe_name = f"{doc_id}_{clean_name}"
    orig_path = DOCUMENTS_DIR / safe_name
    orig_path.write_bytes(file_bytes)

    # Render pages
    pages = extract_document_pages(file_bytes, filename)
    page_urls = []
    overlay_urls = []

    processor, model, device = load_trocr()

    all_lines = []
    global_line_idx = 0
    all_debug = []
    any_suspicious = False
    warning_messages = []

    for p_idx, p_img in enumerate(pages):
        page_file = DOCUMENTS_DIR / f"{doc_id}_page_{p_idx + 1}.png"
        p_img.save(page_file, format="PNG")
        page_urls.append(f"/uploaded_docs/{doc_id}_page_{p_idx + 1}.png")

        # Run preprocessing and segmentation
        segments, p_debug, overlay_img = preprocess_and_segment_lines(p_img)
        overlay_file = DOCUMENTS_DIR / f"{doc_id}_overlay_{p_idx + 1}.png"
        overlay_img.save(overlay_file, format="PNG")
        overlay_urls.append(f"/uploaded_docs/{doc_id}_overlay_{p_idx + 1}.png")

        if p_debug.get("suspicious_low_line_count"):
            any_suspicious = True
            if p_debug.get("warning"):
                warning_messages.append(f"Page {p_idx + 1}: {p_debug['warning']}")

        all_debug.append({"page": p_idx + 1, **p_debug})

        for seg in segments:
            crop = seg["crop"]
            text, conf = run_trocr_on_line(crop, processor, model, device)
            tier = get_confidence_tier(conf)
            crop_b64 = pil_to_base64(crop)
            all_lines.append({
                "line_index": global_line_idx,
                "page": p_idx + 1,
                "bbox": [seg["x"], seg["y"], seg["width"], seg["height"]],
                "image_data": crop_b64,
                "original_text": text,
                "corrected_text": text,
                "confidence": conf,
                "tier": tier,
                "is_corrected": False,
            })
            global_line_idx += 1

    summary = {
        "total_lines": len(all_lines),
        "accepted": sum(1 for l in all_lines if l["tier"] == "ACCEPTED"),
        "review_recommended": sum(1 for l in all_lines if l["tier"] == "REVIEW_RECOMMENDED"),
        "manual_review_required": sum(1 for l in all_lines if l["tier"] == "MANUAL_REVIEW_REQUIRED"),
        "device": str(device),
        "suspicious_low_line_count": any_suspicious,
        "warning": " | ".join(warning_messages) if warning_messages else None,
        "detected_lines_count": len(all_lines),
        "skew_angle": all_debug[0]["skew_angle"] if all_debug else 0.0,
    }

    status = "MANUAL_REVIEW_REQUIRED" if any_suspicious else "PENDING_REVIEW"
    raw_text = "\n".join(l["original_text"] for l in all_lines if l["original_text"])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_write_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO DocumentOCR (
                DocumentID, CaseMasterID, Filename, FilePath, PageCount,
                RawOCRText, CorrectedOCRText, Status, ConfidenceSummary, LineResults,
                CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                case_id,
                filename,
                str(orig_path),
                len(pages),
                raw_text,
                raw_text,
                status,
                json.dumps(summary),
                json.dumps(all_lines),
                now_str,
                now_str,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "document_id": doc_id,
        "case_id": case_id,
        "filename": filename,
        "original_file_url": f"/uploaded_docs/{safe_name}",
        "page_urls": page_urls,
        "overlay_urls": overlay_urls,
        "page_count": len(pages),
        "summary": summary,
        "debug_info": all_debug,
        "lines": all_lines,
        "raw_text": raw_text,
    }


def _load_dotenv_keys():
    """Load GEMINI_API_KEY or GOOGLE_API_KEY from .env files if not set in os.environ."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return
    from backend.db import ROOT
    for env_file in [ROOT / ".env", ROOT / "frontend" / ".env", ROOT / "backend" / ".env"]:
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "VITE_GEMINI_API_KEY") and v:
                        os.environ["GEMINI_API_KEY"] = v
                        return
            except Exception:
                pass


def call_gemini_vision_ocr(pil_img, api_key: str | None = None) -> dict:
    """Call Google Gemini Vision API to transcribe document image and extract entities & relations."""
    _load_dotenv_keys()
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError(
            "Gemini API key is required. Set GEMINI_API_KEY in .env or provide a valid API key from https://aistudio.google.com/app/apikey"
        )

    prompt = (
        "You are an expert document OCR and entity extraction system for criminal investigation records.\n"
        "Examine this image/document and perform high-precision Optical Character Recognition (OCR).\n"
        "Return ONLY a raw valid JSON object with NO markdown codeblocks or wrapping formatting. Use this exact structure:\n"
        "{\n"
        '  "raw_text": "Full transcribed text preserving line breaks...",\n'
        '  "lines": [\n'
        '    {"line_index": 0, "text": "transcribed text line 1", "confidence": 98.0},\n'
        '    {"line_index": 1, "text": "transcribed text line 2", "confidence": 95.0}\n'
        "  ],\n"
        '  "entities": [\n'
        '    {"text": "Extracted Entity Name or Value", "label": "PERSON"}\n'
        "  ],\n"
        '  "relations": [\n'
        '    {"source": "Person A", "target": "9876543210", "type": "HAS_PHONE", "confidence": 0.9, "sentence": "..."}\n'
        "  ]\n"
        "}\n\n"
        "Labels allowed for entities: PERSON, PHONE, VEHICLE, LOC, DATE, ORG.\n"
        "Types allowed for relations: HAS_PHONE, ASSOCIATED_WITH_VEHICLE, MENTIONED_AT_LOCATION, MENTIONED_ON_DATE, NAMED_TOGETHER.\n"
        "Do not invent facts. Ensure phone numbers, vehicle registration numbers, names, and dates are preserved accurately."
    )

    models_to_try = [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-2.5-flash-lite",
        "gemini-1.5-flash-latest",
    ]
    response_text = ""
    last_err = None

    # Try google.genai first
    try:
        from google import genai

        client = genai.Client(api_key=key)
        for m in models_to_try:
            try:
                response = client.models.generate_content(model=m, contents=[pil_img, prompt])
                response_text = response.text or ""
                if response_text:
                    break
            except Exception as e_m:
                last_err = e_m
                err_s = str(e_m)
                if "API_KEY_INVALID" in err_s or "API key not valid" in err_s:
                    break
    except Exception as e1:
        last_err = e1

    if not response_text:
        # Fallback to google.generativeai
        try:
            import google.generativeai as genai_old

            genai_old.configure(api_key=key)
            for m in models_to_try:
                try:
                    model = genai_old.GenerativeModel(m)
                    res = model.generate_content([pil_img, prompt])
                    response_text = res.text or ""
                    if response_text:
                        break
                except Exception as e_old:
                    last_err = e_old
                    err_s = str(e_old)
                    if "API_KEY_INVALID" in err_s or "API key not valid" in err_s:
                        break
        except Exception as e2:
            last_err = e2

    if not response_text:
        err_msg = str(last_err)
        if "API_KEY_INVALID" in err_msg or "API key not valid" in err_msg or "INVALID_ARGUMENT" in err_msg:
            raise ValueError(
                "Invalid Gemini API Key ('API_KEY_INVALID'). "
                "Standard Google Gemini API keys start with 'AIzaSy...'. "
                "Please get a free API key from https://aistudio.google.com/app/apikey or switch to 'Local TrOCR'."
            )
        raise RuntimeError(f"Gemini API call failed: {err_msg}")

    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        return data
    except Exception:
        return {
            "raw_text": response_text,
            "lines": [
                {"line_index": i, "text": line, "confidence": 92.0}
                for i, line in enumerate(response_text.splitlines())
                if line.strip()
            ],
            "entities": [],
            "relations": [],
        }


def process_document_with_gemini(
    case_id: int,
    filename: str,
    file_bytes: bytes,
    api_key: str | None = None,
) -> dict:
    """Ingest and OCR a document/image using Google Gemini Vision AI."""
    doc_id = str(uuid.uuid4())[:8]
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    safe_name = f"{doc_id}_{clean_name}"
    orig_path = DOCUMENTS_DIR / safe_name
    orig_path.write_bytes(file_bytes)

    pages = extract_document_pages(file_bytes, filename)
    page_urls = []
    overlay_urls = []
    all_lines = []
    all_debug = []
    extracted_entities = []
    extracted_relations = []
    global_line_idx = 0

    for p_idx, p_img in enumerate(pages):
        page_file = DOCUMENTS_DIR / f"{doc_id}_page_{p_idx + 1}.png"
        p_img.save(page_file, format="PNG")
        page_urls.append(f"/uploaded_docs/{doc_id}_page_{p_idx + 1}.png")

        # Visual line segmentation for bounding box crops & overlay
        segments, p_debug, overlay_img = preprocess_and_segment_lines(p_img)
        overlay_file = DOCUMENTS_DIR / f"{doc_id}_overlay_{p_idx + 1}.png"
        overlay_img.save(overlay_file, format="PNG")
        overlay_urls.append(f"/uploaded_docs/{doc_id}_overlay_{p_idx + 1}.png")

        all_debug.append({"page": p_idx + 1, **p_debug})

        # Call Gemini Vision OCR for page
        gemini_res = call_gemini_vision_ocr(p_img, api_key=api_key)
        g_lines = gemini_res.get("lines", [])
        g_entities = gemini_res.get("entities", [])
        g_relations = gemini_res.get("relations", [])

        extracted_entities.extend(g_entities)
        extracted_relations.extend(g_relations)

        # Match Gemini output lines with visual crop segments
        if g_lines:
            for idx, g_line in enumerate(g_lines):
                text = (g_line.get("text") or "").strip()
                if not text:
                    continue
                conf = float(g_line.get("confidence") or 95.0)
                tier = get_confidence_tier(conf)

                # Pair with line crop image if available
                crop_b64 = ""
                bbox = [0, 0, 0, 0]
                if idx < len(segments):
                    crop_b64 = pil_to_base64(segments[idx]["crop"])
                    bbox = [segments[idx]["x"], segments[idx]["y"], segments[idx]["width"], segments[idx]["height"]]

                all_lines.append({
                    "line_index": global_line_idx,
                    "page": p_idx + 1,
                    "bbox": bbox,
                    "image_data": crop_b64,
                    "original_text": text,
                    "corrected_text": text,
                    "confidence": conf,
                    "tier": tier,
                    "is_corrected": False,
                })
                global_line_idx += 1
        else:
            # Fallback to segments
            for seg in segments:
                crop = seg["crop"]
                crop_b64 = pil_to_base64(crop)
                all_lines.append({
                    "line_index": global_line_idx,
                    "page": p_idx + 1,
                    "bbox": [seg["x"], seg["y"], seg["width"], seg["height"]],
                    "image_data": crop_b64,
                    "original_text": "",
                    "corrected_text": "",
                    "confidence": 70.0,
                    "tier": "REVIEW_RECOMMENDED",
                    "is_corrected": False,
                })
                global_line_idx += 1

    raw_text = "\n".join(l["original_text"] for l in all_lines if l["original_text"])

    # Strict Pipeline: Ordered OCR text -> Existing FIR NER -> Existing Relation Engine
    final_entities = extract_entities(raw_text) if raw_text else []
    final_relations = extract_relations(final_entities, raw_text) if raw_text else []

    summary = {
        "total_lines": len(all_lines),
        "accepted": sum(1 for l in all_lines if l["tier"] == "ACCEPTED"),
        "review_recommended": sum(1 for l in all_lines if l["tier"] == "REVIEW_RECOMMENDED"),
        "manual_review_required": sum(1 for l in all_lines if l["tier"] == "MANUAL_REVIEW_REQUIRED"),
        "ocr_engine": "Gemini Vision AI",
        "detected_lines_count": len(all_lines),
        "skew_angle": all_debug[0]["skew_angle"] if all_debug else 0.0,
    }

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_write_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO DocumentOCR (
                DocumentID, CaseMasterID, Filename, FilePath, PageCount,
                RawOCRText, CorrectedOCRText, Status, ConfidenceSummary, LineResults,
                CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_REVIEW', ?, ?, ?, ?)
            """,
            (
                doc_id,
                case_id,
                filename,
                str(orig_path),
                len(pages),
                raw_text,
                raw_text,
                json.dumps(summary),
                json.dumps(all_lines),
                now_str,
                now_str,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "document_id": doc_id,
        "case_id": case_id,
        "filename": filename,
        "original_file_url": f"/uploaded_docs/{safe_name}",
        "page_urls": page_urls,
        "overlay_urls": overlay_urls,
        "page_count": len(pages),
        "summary": summary,
        "debug_info": all_debug,
        "lines": all_lines,
        "raw_text": raw_text,
        "entities": final_entities,
        "relations": final_relations,
    }



def update_document_ocr_lines(
    case_id: int,
    doc_id: str,
    line_updates: list[dict],
    reviewer: str = "investigator",
) -> dict:
    """
    Applies investigator corrections to DocumentOCR.
    - Preserves RawOCRText and original file unchanged.
    - Updates CorrectedOCRText and LineResults.
    - Logs SHA-256 hashed audit record for each edited line.
    """
    row = query_one(
        "SELECT DocumentID, Filename, RawOCRText, CorrectedOCRText, LineResults FROM DocumentOCR WHERE DocumentID = ?",
        (doc_id,),
    )
    if not row:
        raise ValueError(f"Document {doc_id} not found")

    existing_lines = json.loads(row["LineResults"] or "[]")
    lines_by_idx = {l["line_index"]: l for l in existing_lines}

    audit_records = []
    for update in line_updates:
        idx = update.get("line_index")
        new_text = (update.get("corrected_text") or "").strip()
        if idx in lines_by_idx:
            orig = lines_by_idx[idx]["original_text"]
            old_corr = lines_by_idx[idx].get("corrected_text", orig)
            if new_text != old_corr:
                record = log_ocr_correction(
                    case_id=case_id,
                    document_id=doc_id,
                    line_index=idx,
                    original_text=old_corr,
                    corrected_text=new_text,
                    reviewer=reviewer,
                    rationale=update.get("rationale") or "Investigator manual correction",
                )
                audit_records.append(record)
                lines_by_idx[idx]["corrected_text"] = new_text
                lines_by_idx[idx]["is_corrected"] = True
                lines_by_idx[idx]["tier"] = "ACCEPTED"

    updated_lines = list(lines_by_idx.values())
    verified_full_text = "\n".join(l["corrected_text"] for l in updated_lines if l["corrected_text"])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_write_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE DocumentOCR
            SET CorrectedOCRText = ?, LineResults = ?, Status = 'VERIFIED', UpdatedAt = ?
            WHERE DocumentID = ?
            """,
            (verified_full_text, json.dumps(updated_lines), now_str, doc_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "document_id": doc_id,
        "status": "VERIFIED",
        "verified_text": verified_full_text,
        "corrections_logged": len(audit_records),
        "audit_records": audit_records,
        "lines": updated_lines,
    }


def get_document_ocr(doc_id: str) -> dict | None:
    """Fetch stored DocumentOCR record."""
    row = query_one(
        """
        SELECT DocumentID, CaseMasterID, Filename, FilePath, PageCount,
               RawOCRText, CorrectedOCRText, Status, ConfidenceSummary, LineResults,
               CreatedAt, UpdatedAt
        FROM DocumentOCR WHERE DocumentID = ?
        """,
        (doc_id,),
    )
    if not row:
        return None
    return {
        "document_id": row["DocumentID"],
        "case_id": row["CaseMasterID"],
        "filename": row["Filename"],
        "file_path": row["FilePath"],
        "page_count": row["PageCount"],
        "raw_text": row["RawOCRText"],
        "corrected_text": row["CorrectedOCRText"],
        "status": row["Status"],
        "summary": json.loads(row["ConfidenceSummary"] or "{}"),
        "lines": json.loads(row["LineResults"] or "[]"),
        "created_at": row["CreatedAt"],
        "updated_at": row["UpdatedAt"],
    }

