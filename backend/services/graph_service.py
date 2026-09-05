"""Build a NetworkX graph from GraphEdge rows for one case."""

from __future__ import annotations

from typing import Any

import networkx as nx
from rapidfuzz import fuzz, process

from backend.db import node_key, query

# Relation types that should be treated as undirected for layout/metrics
UNDIRECTED_RELATIONS = {"CO_LOCATED", "NAMED_TOGETHER_IN_FIR", "CO_ACCUSED"}


def _fetch_labels(nodes: dict[str, dict[str, Any]]) -> None:
    """Fill human-readable labels for PERSON / ACCOUNT / VEHICLE / LOCATION."""
    persons = [n["entity_id"] for n in nodes.values() if n["type"] == "PERSON"]
    accounts = [n["entity_id"] for n in nodes.values() if n["type"] == "ACCOUNT"]
    vehicles = [n["entity_id"] for n in nodes.values() if n["type"] == "VEHICLE"]

    if persons:
        placeholders = ",".join("?" * len(persons))
        for row in query(
            f"SELECT PersonID, FullName, SourceRole FROM Person WHERE PersonID IN ({placeholders})",
            persons,
        ):
            key = node_key("PERSON", row["PersonID"])
            if key in nodes:
                nodes[key]["label"] = row["FullName"]
                nodes[key]["role"] = row["SourceRole"]

    if accounts:
        placeholders = ",".join("?" * len(accounts))
        for row in query(
            f"SELECT AccountID, AccountNumber, BankName FROM BankAccount WHERE AccountID IN ({placeholders})",
            accounts,
        ):
            key = node_key("ACCOUNT", row["AccountID"])
            if key in nodes:
                bank = row["BankName"] or "Bank"
                nodes[key]["label"] = f"{bank} {row['AccountNumber']}"

    if vehicles:
        placeholders = ",".join("?" * len(vehicles))
        for row in query(
            f"SELECT VehicleID, RegistrationNumber, VehicleType FROM VehicleRegistration WHERE VehicleID IN ({placeholders})",
            vehicles,
        ):
            key = node_key("VEHICLE", row["VehicleID"])
            if key in nodes:
                kind = row["VehicleType"] or "Vehicle"
                nodes[key]["label"] = f"{kind} {row['RegistrationNumber']}"

    phones = [n["entity_id"] for n in nodes.values() if n["type"] == "PHONE"]
    if phones:
        placeholders = ",".join("?" * len(phones))
        for row in query(
            f"SELECT PhoneID, PhoneNumber FROM PhoneNumber WHERE PhoneID IN ({placeholders})",
            phones,
        ):
            key = node_key("PHONE", row["PhoneID"])
            if key in nodes:
                nodes[key]["label"] = row["PhoneNumber"]

    group_types = ("LOCATION", "DATE", "ORG", "PHONE", "VEHICLE", "EVIDENCE_GROUP", "PHOTO")
    group_ids = [n["entity_id"] for n in nodes.values() if n["type"] in group_types and n["entity_id"]]
    if group_ids:
        placeholders = ",".join("?" * len(group_ids))
        for row in query(
            f"SELECT GroupID, EventDescription FROM EvidenceIndependenceGroup WHERE GroupID IN ({placeholders})",
            group_ids,
        ):
            for kind in group_types:
                key = node_key(kind, row["GroupID"])
                if key in nodes and row["EventDescription"]:
                    nodes[key]["label"] = row["EventDescription"]

    for n in nodes.values():
        if n["type"] == "LOCATION" and (n.get("label") == n["id"] or not n.get("label")):
            n["label"] = "Incident scene" if n["entity_id"] == 0 else n.get("label") or n["id"]
        if n["type"] == "PHOTO" and not n.get("label"):
            n["label"] = f"Photo #{n['entity_id']}"
        if n["type"] == "EVIDENCE_GROUP" and not n.get("label"):
            n["label"] = f"Evidence #{n['entity_id']}"


def fetch_case_edges(case_id: int) -> list[dict[str, Any]]:
    return query(
        """
        SELECT EdgeID, CaseMasterID, SourceEntityType, SourceEntityID,
               TargetEntityType, TargetEntityID, RelationType, EventDateTime,
               SourceType, SourceRecordID, ConfidenceScore, IndependenceGroupID
        FROM GraphEdge
        WHERE CaseMasterID = ?
        ORDER BY EventDateTime
        """,
        (case_id,),
    )


def collect_nodes(edge_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for e in edge_rows:
        for kind, eid in (
            (e["SourceEntityType"], e["SourceEntityID"]),
            (e["TargetEntityType"], e["TargetEntityID"]),
        ):
            key = node_key(kind, eid)
            if key not in nodes:
                nodes[key] = {
                    "id": key,
                    "type": kind,
                    "entity_id": eid,
                    "label": key,
                }
    _fetch_labels(nodes)
    return nodes


def build_nx_graph(
    edge_rows: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]] | None = None,
) -> nx.Graph:
    """Undirected simple graph used for centrality, communities, counterfactuals."""
    G = nx.Graph()
    if nodes is None:
        nodes = collect_nodes(edge_rows)
    for key, data in nodes.items():
        G.add_node(key, **data)
    for e in edge_rows:
        src = node_key(e["SourceEntityType"], e["SourceEntityID"])
        tgt = node_key(e["TargetEntityType"], e["TargetEntityID"])
        if src == tgt:
            continue
        if G.has_edge(src, tgt):
            G[src][tgt]["weight"] = G[src][tgt].get("weight", 1) + 1
        else:
            G.add_edge(src, tgt, weight=1, relation=e["RelationType"])
    return G


def case_graph(case_id: int) -> tuple[nx.Graph, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    edges = fetch_case_edges(case_id)
    nodes = collect_nodes(edges)
    G = build_nx_graph(edges, nodes)
    return G, edges, nodes


def highlight_from_name(payload: dict[str, Any], name: str) -> dict[str, Any]:
    """Fuzzy-match a person name, BFS from that node, flag reachable subgraph."""

    G: nx.Graph = payload["_nx"]
    people = [n for n in payload["nodes"] if n["type"] == "PERSON"]
    if not people or not name.strip():
        return payload

    choices = {n["id"]: n["label"] for n in people}
    match = process.extractOne(name, choices, scorer=fuzz.WRatio)
    if not match or match[1] < 45:
        return payload
    matched_id = match[2]

    reachable = set()
    if G.has_node(matched_id):
        reachable = set(nx.bfs_tree(G, matched_id).nodes())
        reachable.add(matched_id)

    for n in payload["nodes"]:
        n["highlighted"] = n["id"] in reachable
    for e in payload["edges"]:
        e["highlighted"] = e["source"] in reachable and e["target"] in reachable
    payload["matched_node"] = matched_id
    return payload
