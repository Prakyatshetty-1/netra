"""Identity-candidate listing with an explicit merge threshold."""

from __future__ import annotations

from backend.db import query

RESOLVE_THRESHOLD = 0.85


def identity_candidates(case_id: int) -> list[dict]:
    """Return ER pairs that touch any person in this case. Never auto-merge below 0.85."""
    rows = query(
        """
        SELECT ic.CandidateID, ic.RawNameVariant, ic.PersonID_A, ic.PersonID_B,
               ic.NameSimilarity, ic.ModelConfidence, ic.GroundTruthIsSamePerson,
               pa.FullName AS NameA, pb.FullName AS NameB,
               pa.CaseMasterID AS CaseA, pb.CaseMasterID AS CaseB
        FROM IdentityCandidate ic
        JOIN Person pa ON pa.PersonID = ic.PersonID_A
        JOIN Person pb ON pb.PersonID = ic.PersonID_B
        WHERE pa.CaseMasterID = ? OR pb.CaseMasterID = ?
        ORDER BY ic.ModelConfidence DESC
        """,
        (case_id, case_id),
    )
    out = []
    for r in rows:
        conf = float(r["ModelConfidence"] or 0)
        if conf > RESOLVE_THRESHOLD:
            status = "RESOLVED"
        else:
            status = "UNRESOLVED — Candidate A/B"
        out.append(
            {
                "candidate_id": r["CandidateID"],
                "raw_name_variant": r["RawNameVariant"],
                "person_id_a": r["PersonID_A"],
                "person_id_b": r["PersonID_B"],
                "name_a": r["NameA"],
                "name_b": r["NameB"],
                "case_a": r["CaseA"],
                "case_b": r["CaseB"],
                "name_similarity": float(r["NameSimilarity"]) if r["NameSimilarity"] is not None else None,
                "model_confidence": round(conf, 3),
                "status": status,
                "ground_truth_same": bool(r["GroundTruthIsSamePerson"]),
            }
        )
    return out
