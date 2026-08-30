"""Template-grounded copilot: every sentence is a claim with source + tag."""

from __future__ import annotations

import re

from backend.db import query, query_one
from backend.services.casedna_service import related_cases
from backend.services.hypothesis_service import hypotheses_for_person
from backend.services.identity_service import identity_candidates
from backend.services.intelligence_service import enrich_case_graph


def _fmt(claim: str, tag: str, source_type: str, confidence: float | None, timestamp: str | None) -> dict:
    conf_txt = f"{confidence:.3f}" if confidence is not None else "n/a"
    ts_txt = timestamp or "n/a"
    formatted = f"{claim} — {tag} (Source: {source_type}, confidence {conf_txt}, {ts_txt})"
    return {
        "claim": claim,
        "tag": tag,
        "source_type": source_type,
        "confidence": confidence,
        "timestamp": timestamp,
        "formatted": formatted,
    }


def _person_by_name(case_id: int, name: str) -> dict | None:
    rows = query(
        "SELECT PersonID, FullName FROM Person WHERE CaseMasterID = ?",
        (case_id,),
    )
    if not rows:
        return None
    needle = name.lower().strip()
    for r in rows:
        if needle and needle in r["FullName"].lower():
            return r
    return None


def answer_question(case_id: int, question: str) -> dict:
    q = question.strip()
    ql = q.lower()
    claims: list[dict] = []

    case = query_one(
        """
        SELECT c.CaseMasterID, c.CrimeNo, csh.CrimeHeadName, o.BriefFacts
        FROM CaseMaster c
        LEFT JOIN CrimeSubHead csh ON csh.CrimeSubHeadID = c.CrimeMinorHeadID
        LEFT JOIN Inv_OccuranceTime o ON o.CaseMasterID = c.CaseMasterID
        WHERE c.CaseMasterID = ?
        """,
        (case_id,),
    )
    if not case:
        return {"answer": "Case not found.", "claims": []}

    # Pattern: why is <name> flagged
    m = re.search(r"why is ([a-z .'-]+) flagged", ql)
    if not m:
        m = re.search(r"who is ([a-z .'-]+)", ql)

    graph = enrich_case_graph(case_id)
    burst_edges = [e for e in graph["edges"] if e["burst"]]

    person = None
    if m:
        person = _person_by_name(case_id, m.group(1))

    if person:
        hyps = hypotheses_for_person(case_id, person["PersonID"])
        top = hyps[0] if hyps else None
        person_bursts = [
            e
            for e in burst_edges
            if e["source"] == f"PERSON:{person['PersonID']}" or e["target"] == f"PERSON:{person['PersonID']}"
        ]
        if person_bursts:
            e0 = person_bursts[0]
            claims.append(
                _fmt(
                    f"{person['FullName']} participates in a ≥5-call / 72h burst",
                    "DIRECTLY_OBSERVED",
                    e0["source_type"] or "CDR",
                    e0["confidence"],
                    e0["time"],
                )
            )
        person_edges = [
            e
            for e in graph["edges"]
            if e["source"] == f"PERSON:{person['PersonID']}" or e["target"] == f"PERSON:{person['PersonID']}"
        ]
        if person_edges:
            e0 = max(person_edges, key=lambda e: e["confidence"] or 0)
            claims.append(
                _fmt(
                    f"{person['FullName']} has a {e0['relation']} link in this case",
                    "DIRECTLY_OBSERVED",
                    e0["source_type"] or "FIR",
                    e0["confidence"],
                    e0["time"],
                )
            )
        if top:
            claims.append(
                _fmt(
                    f"Leading hypothesis for {person['FullName']} is {top['type']} (score {top['score']})",
                    "INFERRED",
                    "HYPOTHESIS",
                    top["score"],
                    None,
                )
            )
    elif "match" in ql or "related" in ql or "dna" in ql:
        related = related_cases(case_id, top_k=3)
        for rel in related:
            claims.append(
                _fmt(
                    f"Case {rel['crime_no']} is similar (overall {rel['overall']:.2f}; "
                    f"topology {rel['channels']['topology']:.2f})",
                    "INFERRED",
                    "CASE_DNA",
                    rel["overall"],
                    None,
                )
            )
    elif "identity" in ql or "same person" in ql or "duplicate" in ql:
        cands = identity_candidates(case_id)[:3]
        for c in cands:
            claims.append(
                _fmt(
                    f"Identity pair {c['name_a']} / {c['name_b']} is {c['status']}",
                    "INFERRED",
                    "IDENTITY",
                    c["model_confidence"],
                    None,
                )
            )
    else:
        # Default: case snapshot from graph + FIR text
        if burst_edges:
            e0 = burst_edges[0]
            claims.append(
                _fmt(
                    f"Temporal analysis flagged {len(burst_edges)} burst call edges",
                    "DIRECTLY_OBSERVED",
                    e0["source_type"] or "CDR",
                    e0["confidence"],
                    e0["time"],
                )
            )
        top_nodes = sorted(graph["nodes"], key=lambda n: n["centrality"], reverse=True)[:2]
        for n in top_nodes:
            claims.append(
                _fmt(
                    f"{n['label']} has betweenness centrality {n['centrality']}",
                    "INFERRED",
                    "GRAPH",
                    n["centrality"],
                    None,
                )
            )
        if case.get("BriefFacts"):
            snippet = str(case["BriefFacts"])[:180].rstrip() + "…"
            claims.append(
                _fmt(
                    snippet,
                    "DIRECTLY_OBSERVED",
                    "FIR",
                    1.0,
                    None,
                )
            )

    if not claims:
        claims.append(
            _fmt(
                f"Case {case['CrimeNo']} ({case.get('CrimeHeadName') or 'unknown head'}) has "
                f"{len(graph['nodes'])} nodes and {len(graph['edges'])} edges",
                "DIRECTLY_OBSERVED",
                "GRAPH",
                1.0,
                None,
            )
        )

    answer = "\n".join(c["formatted"] for c in claims)
    return {"answer": answer, "claims": claims}
