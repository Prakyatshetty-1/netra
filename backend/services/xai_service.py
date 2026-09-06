"""Explainable evidence scoring for NETRA entity intelligence.

The service is deliberately deterministic and rule-based for auditability. It does not
make a criminality determination; it explains why records are associated and why
identity fields match or conflict.
"""
from __future__ import annotations

from typing import Any
from rapidfuzz import fuzz


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def name_similarity(a: Any, b: Any) -> float:
    if not a or not b:
        return 0.0
    return round(fuzz.token_set_ratio(norm(a), norm(b)) / 100.0, 3)


def field_match(field: str, police: Any, government: Any) -> dict[str, Any]:
    if police in (None, "") or government in (None, ""):
        return {"field": field, "police_value": police, "government_value": government,
                "status": "NOT_AVAILABLE", "score": 0.0,
                "reason": "One or both evidence sources do not contain this field."}

    if field == "name":
        score = name_similarity(police, government)
        if score >= 0.90:
            status = "MATCH"
        elif score >= 0.70:
            status = "PARTIAL_MATCH"
        else:
            status = "MISMATCH"
        reason = f"Token-aware name similarity is {score:.3f}."
    else:
        p, g = norm(police), norm(government)
        score = 1.0 if p == g else (0.8 if p in g or g in p else 0.0)
        if score == 1.0:
            status = "MATCH"
            reason = "Normalized values are identical."
        elif score == 0.8:
            status = "PARTIAL_MATCH"
            reason = "One normalized value contains the other."
        else:
            status = "MISMATCH"
            reason = "Normalized values differ."
    return {"field": field, "police_value": police, "government_value": government,
            "status": status, "score": round(score, 3), "reason": reason}


def explain_association(signal_type: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not evidence:
        return {"signal": signal_type, "score": 0.0, "level": "LOW",
                "explanation": "No supporting records were found."}
    scores = [float(x.get("confidence", x.get("score", 0.0)) or 0.0) for x in evidence]
    score = round(max(scores), 3)
    level = "HIGH" if score >= 0.85 else "MEDIUM" if score >= 0.60 else "LOW"
    reasons = [x.get("reason") for x in evidence if x.get("reason")]
    return {"signal": signal_type, "score": score, "level": level,
            "explanation": " ".join(reasons[:4]) or f"{len(evidence)} supporting record(s) found."}


def identity_explanation(fields: list[dict[str, Any]], government_verified: bool) -> dict[str, Any]:
    usable = [f for f in fields if f["status"] != "NOT_AVAILABLE"]
    exact = sum(f["status"] == "MATCH" for f in usable)
    partial = sum(f["status"] == "PARTIAL_MATCH" for f in usable)
    mismatch = sum(f["status"] == "MISMATCH" for f in usable)
    if not government_verified:
        status = "NOT_VERIFIED"
    elif mismatch:
        status = "MISMATCH" if exact == 0 else "REVIEW_REQUIRED"
    elif partial:
        status = "VERIFIED_WITH_PARTIAL_MATCH"
    else:
        status = "VERIFIED_HIGH_CONFIDENCE"
    score = 0.0
    if usable:
        score = round(sum(float(f["score"]) for f in usable) / len(usable), 3)
    reasons = [f"{exact} exact field match(es)", f"{partial} partial match(es)", f"{mismatch} mismatch(es)"]
    if government_verified:
        reasons.append("Government-document data was supplied by the authorized verification provider.")
    else:
        reasons.append("Government-document verification has not been completed.")
    return {"status": status, "score": score, "reasons": reasons,
            "human_review_required": status in {"MISMATCH", "REVIEW_REQUIRED", "VERIFIED_WITH_PARTIAL_MATCH"}}
