"""Live counterfactual: drop a person node and recompute connectivity."""

from __future__ import annotations

import networkx as nx

from backend.db import node_key, query_one
from backend.services.graph_service import case_graph
from backend.services.intelligence_service import betweenness


def _metrics(G: nx.Graph) -> dict[str, float]:
    n = G.number_of_nodes()
    m = G.number_of_edges()
    components = nx.number_connected_components(G) if n else 0
    if n <= 1:
        reachable_pairs = 0
        avg_path = 0.0
        max_bet = 0.0
    else:
        reachable_pairs = 0
        path_sum = 0.0
        path_n = 0
        for _src, lengths in nx.all_pairs_shortest_path_length(G):
            for dist in lengths.values():
                if dist > 0:
                    reachable_pairs += 1
                    path_sum += dist
                    path_n += 1
        reachable_pairs //= 2
        avg_path = (path_sum / path_n) if path_n else 0.0
        max_bet = max(betweenness(G).values()) if n else 0.0
    return {
        "nodes": float(n),
        "edges": float(m),
        "components": float(components),
        "reachable_pairs": float(reachable_pairs),
        "avg_shortest_path": round(avg_path, 4),
        "max_betweenness": round(max_bet, 4),
    }


def _pct(before: float, after: float) -> float:
    if before == 0:
        return 0.0 if after == 0 else 100.0
    return round(100.0 * (after - before) / before, 2)


def counterfactual(case_id: int, person_id: int) -> dict:
    G, _edges, nodes = case_graph(case_id)
    key = node_key("PERSON", person_id)
    person = query_one("SELECT FullName FROM Person WHERE PersonID = ?", (person_id,))
    label = person["FullName"] if person else key

    before = _metrics(G)
    H = G.copy()
    if H.has_node(key):
        H.remove_node(key)
    after = _metrics(H)
    return {
        "person_id": person_id,
        "person_label": label,
        "removed_node": key,
        "node_existed": key in nodes,
        "before": before,
        "after": after,
        "percent_change": {k: _pct(before[k], after[k]) for k in before},
    }
