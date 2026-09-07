"""Append-only hashed JSON-lines audit log (prototype 'ledger')."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from backend.db import AUDIT_LOG_PATH


def log_decision(case_id: int, decision: str, reviewer: str, rationale: str) -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "case_id": case_id,
        "decision": decision,
        "reviewer": reviewer,
        "rationale": rationale,
        "timestamp": timestamp,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    record = {**payload, "hash": digest}
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def log_ocr_correction(
    case_id: int,
    document_id: str,
    line_index: int,
    original_text: str,
    corrected_text: str,
    reviewer: str = "investigator",
    rationale: str = "OCR line transcription correction",
) -> dict:
    """Record an investigator's edit/verification to an OCR transcription line."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "event_type": "OCR_CORRECTION",
        "case_id": case_id,
        "document_id": document_id,
        "line_index": line_index,
        "original_text": original_text,
        "corrected_text": corrected_text,
        "reviewer": reviewer,
        "rationale": rationale,
        "timestamp": timestamp,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    record = {**payload, "hash": digest}
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record

