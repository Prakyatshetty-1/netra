"""Centrality, community detection, and call-burst flags."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import networkx as nx

from backend.db import node_key
from backend.services.graph_service import case_graph


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def betweenness(G: nx.Graph) -> dict[str, float]:
    if G.number_of_nodes() == 0:
        return {}
    raw = nx.betweenness_centrality(G, weight=None)
    return {k: round(v, 4) for k, v in raw.items()}


def communities(G: nx.Graph) -> dict[str, int]:
    """Louvain if available, otherwise greedy modularity — both are explainable."""
    if G.number_of_nodes() == 0:
        return {}
    try:
        parts = nx.community.louvain_communities(G, seed=42)
    except Exception:
        parts = list(nx.community.greedy_modularity_communities(G))
    mapping: dict[str, int] = {}
    for idx, group in enumerate(parts):
        for node in group:
            mapping[node] = idx
    return mapping


def call_bursts(edge_rows: list[dict[str, Any]]) -> set[int]:
    """Flag CALLED edges that sit in a person-pair window of ≥5 calls / 72h."""
    by_pair: dict[tuple[int, int], list[tuple[datetime, int]]] = defaultdict(list)
    for e in edge_rows:
        if e["RelationType"] != "CALLED":
            continue
        dt = _parse_dt(e["EventDateTime"])
        if dt is None:
            continue
        a, b = sorted((int(e["SourceEntityID"]), int(e["TargetEntityID"])))
        by_pair[(a, b)].append((dt, int(e["EdgeID"])))

    burst_ids: set[int] = set()
    window = timedelta(hours=72)
    for events in by_pair.values():
        events.sort(key=lambda x: x[0])
        times = [t for t, _ in events]
        ids = [i for _, i in events]
        n = len(events)
        j = 0
        for i in range(n):
            while j < n and times[j] - times[i] <= window:
                j += 1
            if j - i >= 5:
                burst_ids.update(ids[i:j])
    return burst_ids


def enrich_case_graph(case_id: int) -> dict[str, Any]:
    """Attach centrality, community, and burst flags to the serializable graph."""
    G, edge_rows, nodes = case_graph(case_id)
    cent = betweenness(G)
    comm = communities(G)
    bursts = call_bursts(edge_rows)

    node_out = []
    for key, n in nodes.items():
        node_out.append(
            {
                "id": key,
                "type": n["type"],
                "label": n.get("label", key),
                "centrality": cent.get(key, 0.0),
                "community": comm.get(key),
                "highlighted": False,
            }
        )

    edge_out = []
    for e in edge_rows:
        src = node_key(e["SourceEntityType"], e["SourceEntityID"])
        tgt = node_key(e["TargetEntityType"], e["TargetEntityID"])
        edge_out.append(
            {
                "id": e["EdgeID"],
                "source": src,
                "target": tgt,
                "relation": e["RelationType"],
                "time": str(e["EventDateTime"]) if e["EventDateTime"] else None,
                "source_type": e["SourceType"],
                "confidence": float(e["ConfidenceScore"]) if e["ConfidenceScore"] is not None else None,
                "burst": e["EdgeID"] in bursts,
                "highlighted": False,
            }
        )

    return {
        "case_id": case_id,
        "nodes": node_out,
        "edges": edge_out,
        "matched_node": None,
        "_nx": G,
        "_edge_rows": edge_rows,
        "_nodes": nodes,
        "_bursts": bursts,
    }
