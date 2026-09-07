"""Interpretable 4-channel Case DNA + cosine similarity (not a trained embedding)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np

from backend.db import query, query_one
from backend.services.graph_service import case_graph
from backend.services.intelligence_service import betweenness, _parse_dt

CHANNELS = ("topology", "temporal", "financial", "roles")
CHANNEL_SLICES = {
    "topology": slice(0, 3),
    "temporal": slice(3, 5),
    "financial": slice(5, 7),
    "roles": slice(7, 9),
}

_vector_cache: dict[int, np.ndarray] | None = None
_raw_cache: dict[int, list[float]] | None = None


def _max_calls_72h(edge_rows: list[dict[str, Any]]) -> int:
    times = sorted(t for t in (_parse_dt(e["EventDateTime"]) for e in edge_rows if e["RelationType"] == "CALLED") if t)
    if not times:
        return 0
    window = timedelta(hours=72)
    best = 1
    j = 0
    for i, start in enumerate(times):
        while j < len(times) and times[j] - start <= window:
            j += 1
        best = max(best, j - i)
    return best


def _raw_vector(case_id: int) -> list[float]:
    G, edge_rows, nodes = case_graph(case_id)
    cent = betweenness(G)
    max_bet = max(cent.values()) if cent else 0.0

    occ = query_one(
        "SELECT IncidentFromDate FROM Inv_OccuranceTime WHERE CaseMasterID = ?",
        (case_id,),
    )
    incident = _parse_dt(occ["IncidentFromDate"]) if occ else None
    first_edge = None
    for e in edge_rows:
        dt = _parse_dt(e["EventDateTime"])
        if dt and (first_edge is None or dt < first_edge):
            first_edge = dt
    if incident and first_edge:
        days_to_incident = abs((incident - first_edge).days)
    else:
        days_to_incident = 0

    txns = query(
        "SELECT Amount, HopSequence FROM FinancialTransaction WHERE CaseMasterID = ?",
        (case_id,),
    )
    hops = max((int(t["HopSequence"] or 0) for t in txns), default=0)
    total_amt = float(sum(float(t["Amount"] or 0) for t in txns))

    n_person = sum(1 for n in nodes.values() if n["type"] == "PERSON")
    n_asset = sum(1 for n in nodes.values() if n["type"] in ("ACCOUNT", "VEHICLE"))

    return [
        float(G.number_of_nodes()),
        float(len(edge_rows)),
        float(max_bet),
        float(_max_calls_72h(edge_rows)),
        float(days_to_incident),
        float(hops),
        total_amt,
        float(n_person),
        float(n_asset),
    ]


def _all_case_ids() -> list[int]:
    return [r["CaseMasterID"] for r in query("SELECT CaseMasterID FROM CaseMaster ORDER BY CaseMasterID")]


def _minmax_normalize(raw: dict[int, list[float]]) -> dict[int, np.ndarray]:
    mat = np.array([raw[i] for i in raw], dtype=float)
    lo = mat.min(axis=0)
    hi = mat.max(axis=0)
    span = np.where(hi - lo == 0, 1.0, hi - lo)
    normed = (mat - lo) / span
    keys = list(raw.keys())
    return {keys[i]: normed[i] for i in range(len(keys))}


def _ensure_cache() -> dict[int, np.ndarray]:
    global _vector_cache, _raw_cache
    if _vector_cache is not None:
        return _vector_cache
    raw = {cid: _raw_vector(cid) for cid in _all_case_ids()}
    _raw_cache = raw
    _vector_cache = _minmax_normalize(raw)
    return _vector_cache


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def related_cases(case_id: int, top_k: int = 5) -> list[dict]:
    vectors = _ensure_cache()
    if case_id not in vectors:
        return []
    target = vectors[case_id]
    scored = []
    for other_id, vec in vectors.items():
        if other_id == case_id:
            continue
        overall = cosine(target, vec)
        channels = {
            ch: round(cosine(target[sl], vec[sl]), 4) for ch, sl in CHANNEL_SLICES.items()
        }
        scored.append((overall, other_id, channels))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]
    if not top:
        return []
    ids = [t[1] for t in top]
    placeholders = ",".join("?" * len(ids))
    meta = {
        r["CaseMasterID"]: r
        for r in query(
            f"""
            SELECT c.CaseMasterID, c.CrimeNo, csh.CrimeHeadName
            FROM CaseMaster c
            LEFT JOIN CrimeSubHead csh ON csh.CrimeSubHeadID = c.CrimeMinorHeadID
            WHERE c.CaseMasterID IN ({placeholders})
            """,
            ids,
        )
    }
    out = []
    for overall, oid, channels in top:
        m = meta.get(oid, {})
        out.append(
            {
                "case_id": oid,
                "crime_no": m.get("CrimeNo", str(oid)),
                "crime_head": m.get("CrimeHeadName"),
                "overall": round(overall, 4),
                "channels": channels,
            }
        )
    return out
