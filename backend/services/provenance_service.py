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
