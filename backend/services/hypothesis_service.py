"""H1–H4 competing hypotheses: labeled rows if present, else explainable heuristics."""

from __future__ import annotations

from backend.db import node_key, query, query_one
from backend.services.graph_service import case_graph
from backend.services.intelligence_service import call_bursts

H_TYPES = ("INTERMEDIARY", "LEGITIMATE", "ALT_LINK", "COINCIDENCE")

TEMPLATES = {
    "INTERMEDIARY": "Candidate sits on communication paths (call burst / high degree) with no independent alibi.",
    "LEGITIMATE": "Shared workplace, family, or FIR co-naming may explain the contact without criminal intent.",
    "ALT_LINK": "A shared vehicle or account may better explain the connection than this person as a broker.",
    "COINCIDENCE": "Sparse, low-confidence contact — the overlap may be incidental.",
}


def _heuristic_scores(case_id: int, person_id: int) -> dict[str, float]:
    G, edge_rows, _nodes = case_graph(case_id)
    key = node_key("PERSON", person_id)
    degree = G.degree(key) if G.has_node(key) else 0
    bursts = call_bursts(edge_rows)
    person_edges = [
        e
        for e in edge_rows
        if (e["SourceEntityType"] == "PERSON" and e["SourceEntityID"] == person_id)
        or (e["TargetEntityType"] == "PERSON" and e["TargetEntityID"] == person_id)
    ]
    in_burst = any(e["EdgeID"] in bursts for e in person_edges)
    has_fir = any(e["RelationType"] == "NAMED_TOGETHER_IN_FIR" for e in person_edges)
    has_asset = any(
        n.startswith("ACCOUNT:") or n.startswith("VEHICLE:")
        for n in (G.neighbors(key) if G.has_node(key) else [])
    )

    occ = query_one("SELECT BriefFacts FROM Inv_OccuranceTime WHERE CaseMasterID = ?", (case_id,))
    facts = (occ["BriefFacts"] or "").lower() if occ else ""
    legit_text = any(
        w in facts
        for w in ("family", "brother", "sister", "employer", "colleague", "workplace", "wife", "husband", "relative")
    )

    scores = {
        "INTERMEDIARY": 0.20 + (0.35 if in_burst else 0) + min(degree, 6) * 0.04,
        "LEGITIMATE": 0.15 + (0.30 if legit_text or has_fir else 0),
        "ALT_LINK": 0.15 + (0.30 if has_asset else 0),
        "COINCIDENCE": 0.25 + (0.30 if degree <= 1 else 0) - (0.15 if in_burst else 0),
    }
    for k in scores:
        scores[k] = max(0.05, scores[k])
    total = sum(scores.values())
    return {k: round(v / total, 3) for k, v in scores.items()}


def hypotheses_for_person(case_id: int, person_id: int) -> list[dict]:
    rows = query(
        """
        SELECT HypothesisType, NarrativeText, ModelScore, GroundTruthLabel
        FROM CompetingHypothesis
        WHERE CaseMasterID = ? AND CandidatePersonID = ?
        """,
        (case_id, person_id),
    )
    if rows:
        out = []
        for r in rows:
            out.append(
                {
                    "type": r["HypothesisType"],
                    "narrative": r["NarrativeText"] or TEMPLATES.get(r["HypothesisType"], ""),
                    "score": round(float(r["ModelScore"] or 0), 3),
                    "ground_truth": bool(r["GroundTruthLabel"]),
                    "generated": False,
                }
            )
        # Ensure all four types are present for the UI
        have = {h["type"] for h in out}
        for t in H_TYPES:
            if t not in have:
                out.append(
                    {
                        "type": t,
                        "narrative": TEMPLATES[t],
                        "score": 0.0,
                        "ground_truth": False,
                        "generated": True,
                    }
                )
        out.sort(key=lambda h: h["score"], reverse=True)
        return out

    scores = _heuristic_scores(case_id, person_id)
    out = [
        {
            "type": t,
            "narrative": TEMPLATES[t],
            "score": scores[t],
            "ground_truth": None,
            "generated": True,
        }
        for t in H_TYPES
    ]
    out.sort(key=lambda h: h["score"], reverse=True)
    return out
