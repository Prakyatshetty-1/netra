"""
Build a NetworkX graph from GraphEdge rows for one case.

PHONE IDs are dynamically normalized.

The graph supports both:

1. Real PhoneNumber.PhoneID values.
2. Legacy PDF-upload PHONE entity IDs that actually point
   to EvidenceIndependenceGroup.GroupID values.

No case-specific IDs are hardcoded.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
from rapidfuzz import fuzz, process

from backend.db import node_key, query

from backend.services.phone_resolution_service import (
    resolve_phone_node,
)


UNDIRECTED_RELATIONS = {
    "CO_LOCATED",
    "NAMED_TOGETHER_IN_FIR",
    "CO_ACCUSED",
}


# ============================================================
# PHONE GRAPH EDGE NORMALIZATION
# ============================================================

def _normalize_phone_edge(
    case_id: int,
    edge: dict[str, Any],
) -> dict[str, Any]:

    result = dict(edge)

    # Only PHONE targets need dynamic resolution.
    if (
        edge.get("TargetEntityType")
        != "PHONE"
    ):
        return result

    graph_phone_id = edge.get(
        "TargetEntityID"
    )

    if graph_phone_id is None:
        return result

    try:

        resolution = resolve_phone_node(
            case_id=int(case_id),
            graph_phone_id=int(
                graph_phone_id
            ),
        )

        # Replace graph-facing ID with actual
        # PhoneNumber.PhoneID.
        result[
            "TargetEntityID"
        ] = int(
            resolution["phone_id"]
        )

        # Keep provenance for UI / XAI.
        result[
            "_phone_resolution"
        ] = resolution

    except Exception:

        # If resolution is impossible, preserve the
        # original graph entity instead of breaking
        # the entire case graph.
        result[
            "_phone_resolution"
        ] = {
            "resolved": False,
            "graph_phone_id": graph_phone_id,
        }

    return result


def _normalize_case_edges(
    case_id: int,
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    normalized = []

    for edge in edges:

        normalized.append(
            _normalize_phone_edge(
                case_id,
                edge,
            )
        )

    return normalized


# ============================================================
# LABELS
# ============================================================

def _fetch_labels(
    nodes: dict[str, dict[str, Any]]
) -> None:

    # --------------------------------------------------------
    # PERSONS
    # --------------------------------------------------------

    persons = [
        n["entity_id"]
        for n in nodes.values()
        if n["type"] == "PERSON"
    ]

    if persons:

        placeholders = ",".join(
            "?"
            for _ in persons
        )

        rows = query(
            f"""
            SELECT
                PersonID,
                FullName,
                SourceRole
            FROM Person
            WHERE PersonID IN (
                {placeholders}
            )
            """,
            persons,
        )

        for row in rows:

            key = node_key(
                "PERSON",
                row["PersonID"],
            )

            if key in nodes:

                nodes[key]["label"] = (
                    row["FullName"]
                )

                nodes[key]["role"] = (
                    row["SourceRole"]
                )

    # --------------------------------------------------------
    # ACCOUNTS
    # --------------------------------------------------------

    accounts = [
        n["entity_id"]
        for n in nodes.values()
        if n["type"] == "ACCOUNT"
    ]

    if accounts:

        placeholders = ",".join(
            "?"
            for _ in accounts
        )

        rows = query(
            f"""
            SELECT
                AccountID,
                AccountNumber,
                BankName
            FROM BankAccount
            WHERE AccountID IN (
                {placeholders}
            )
            """,
            accounts,
        )

        for row in rows:

            key = node_key(
                "ACCOUNT",
                row["AccountID"],
            )

            if key in nodes:

                bank = (
                    row["BankName"]
                    or "Bank"
                )

                nodes[key]["label"] = (
                    f"{bank} "
                    f"{row['AccountNumber']}"
                )

    # --------------------------------------------------------
    # VEHICLES
    # --------------------------------------------------------

    vehicles = [
        n["entity_id"]
        for n in nodes.values()
        if n["type"] == "VEHICLE"
    ]

    if vehicles:

        placeholders = ",".join(
            "?"
            for _ in vehicles
        )

        rows = query(
            f"""
            SELECT
                VehicleID,
                RegistrationNumber,
                VehicleType
            FROM VehicleRegistration
            WHERE VehicleID IN (
                {placeholders}
            )
            """,
            vehicles,
        )

        for row in rows:

            key = node_key(
                "VEHICLE",
                row["VehicleID"],
            )

            if key in nodes:

                kind = (
                    row["VehicleType"]
                    or "Vehicle"
                )

                nodes[key]["label"] = (
                    f"{kind} "
                    f"{row['RegistrationNumber']}"
                )

    # --------------------------------------------------------
    # PHONES
    # --------------------------------------------------------

    phones = [
        n["entity_id"]
        for n in nodes.values()
        if n["type"] == "PHONE"
    ]

    if phones:

        placeholders = ",".join(
            "?"
            for _ in phones
        )

        rows = query(
            f"""
            SELECT
                PhoneID,
                PhoneNumber
            FROM PhoneNumber
            WHERE PhoneID IN (
                {placeholders}
            )
            """,
            phones,
        )

        found_phone_ids = set()

        for row in rows:

            phone_id = int(
                row["PhoneID"]
            )

            found_phone_ids.add(
                phone_id
            )

            key = node_key(
                "PHONE",
                phone_id,
            )

            if key in nodes:

                nodes[key]["label"] = (
                    str(
                        row["PhoneNumber"]
                    )
                )

        # ----------------------------------------------------
        # Legacy PHONE fallback
        #
        # If a graph node still could not be found
        # in PhoneNumber, try EvidenceIndependenceGroup.
        # ----------------------------------------------------

        unresolved = [
            phone_id
            for phone_id in phones
            if int(phone_id)
            not in found_phone_ids
        ]

        if unresolved:

            placeholders = ",".join(
                "?"
                for _ in unresolved
            )

            group_rows = query(
                f"""
                SELECT
                    GroupID,
                    EventDescription
                FROM EvidenceIndependenceGroup
                WHERE GroupID IN (
                    {placeholders}
                )
                """,
                unresolved,
            )

            for row in group_rows:

                key = node_key(
                    "PHONE",
                    row["GroupID"],
                )

                if (
                    key in nodes
                    and row["EventDescription"]
                ):

                    nodes[key]["label"] = (
                        row["EventDescription"]
                    )

    # --------------------------------------------------------
    # OTHER EVIDENCE GROUP TYPES
    # --------------------------------------------------------

    group_types = (
        "LOCATION",
        "DATE",
        "ORG",
        "VEHICLE",
    )

    group_ids = [
        n["entity_id"]
        for n in nodes.values()
        if (
            n["type"]
            in group_types
        )
        and n["entity_id"]
    ]

    if group_ids:

        placeholders = ",".join(
            "?"
            for _ in group_ids
        )

        rows = query(
            f"""
            SELECT
                GroupID,
                EventDescription
            FROM EvidenceIndependenceGroup
            WHERE GroupID IN (
                {placeholders}
            )
            """,
            group_ids,
        )

        for row in rows:

            for kind in group_types:

                key = node_key(
                    kind,
                    row["GroupID"],
                )

                if (
                    key in nodes
                    and row["EventDescription"]
                ):

                    nodes[key]["label"] = (
                        row["EventDescription"]
                    )

    # --------------------------------------------------------
    # LOCATION FALLBACK
    # --------------------------------------------------------

    for node in nodes.values():

        if (
            node["type"] == "LOCATION"
            and (
                node.get("label")
                == node["id"]
                or not node.get("label")
            )
        ):

            node["label"] = (
                "Incident scene"
                if node["entity_id"] == 0
                else node.get("label")
                or node["id"]
            )


# ============================================================
# FETCH EDGES
# ============================================================

def fetch_case_edges(
    case_id: int,
) -> list[dict[str, Any]]:

    edges = query(
        """
        SELECT
            EdgeID,
            CaseMasterID,
            SourceEntityType,
            SourceEntityID,
            TargetEntityType,
            TargetEntityID,
            RelationType,
            EventDateTime,
            SourceType,
            SourceRecordID,
            ConfidenceScore,
            IndependenceGroupID
        FROM GraphEdge
        WHERE CaseMasterID = ?
        ORDER BY EventDateTime
        """,
        (case_id,),
    )

    return _normalize_case_edges(
        case_id,
        edges,
    )


# ============================================================
# COLLECT NODES
# ============================================================

def collect_nodes(
    edge_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:

    nodes: dict[
        str,
        dict[str, Any],
    ] = {}

    for edge in edge_rows:

        for kind, entity_id in (
            (
                edge["SourceEntityType"],
                edge["SourceEntityID"],
            ),
            (
                edge["TargetEntityType"],
                edge["TargetEntityID"],
            ),
        ):

            key = node_key(
                kind,
                entity_id,
            )

            if key not in nodes:

                nodes[key] = {
                    "id": key,
                    "type": kind,
                    "entity_id": entity_id,
                    "label": key,
                }

    _fetch_labels(
        nodes
    )

    return nodes


# ============================================================
# CASE PERSON NODES
# ============================================================

def collect_case_person_nodes(
    case_id: int,
    nodes: dict[str, dict[str, Any]],
) -> None:

    rows = query(
        """
        SELECT
            PersonID,
            FullName,
            SourceRole
        FROM Person
        WHERE CaseMasterID = ?
        ORDER BY PersonID
        """,
        (case_id,),
    )

    for row in rows:

        key = node_key(
            "PERSON",
            row["PersonID"],
        )

        if key not in nodes:

            nodes[key] = {
                "id": key,
                "type": "PERSON",
                "entity_id": row["PersonID"],
                "label": row["FullName"],
                "role": row["SourceRole"],
            }

        else:

            nodes[key]["label"] = (
                row["FullName"]
            )

            nodes[key]["role"] = (
                row["SourceRole"]
            )


# ============================================================
# NETWORKX GRAPH
# ============================================================

def build_nx_graph(
    edge_rows: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]] | None = None,
) -> nx.Graph:

    graph = nx.Graph()

    if nodes is None:

        nodes = collect_nodes(
            edge_rows
        )

    for key, data in nodes.items():

        graph.add_node(
            key,
            **data,
        )

    for edge in edge_rows:

        source = node_key(
            edge["SourceEntityType"],
            edge["SourceEntityID"],
        )

        target = node_key(
            edge["TargetEntityType"],
            edge["TargetEntityID"],
        )

        if source == target:
            continue

        if graph.has_edge(
            source,
            target,
        ):

            graph[source][target][
                "weight"
            ] = (
                graph[source][target].get(
                    "weight",
                    1,
                )
                + 1
            )

        else:

            graph.add_edge(
                source,
                target,
                weight=1,
                relation=edge[
                    "RelationType"
                ],
            )

    return graph


# ============================================================
# COMPLETE CASE GRAPH
# ============================================================

def case_graph(
    case_id: int,
) -> tuple[
    nx.Graph,
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:

    edges = fetch_case_edges(
        case_id
    )

    nodes = collect_nodes(
        edges
    )

    collect_case_person_nodes(
        case_id,
        nodes,
    )

    _fetch_labels(
        nodes
    )

    graph = build_nx_graph(
        edges,
        nodes,
    )

    return (
        graph,
        edges,
        nodes,
    )


# ============================================================
# NAME SEARCH / HIGHLIGHT
# ============================================================

def highlight_from_name(
    payload: dict[str, Any],
    name: str,
) -> dict[str, Any]:

    graph: nx.Graph = payload[
        "_nx"
    ]

    people = [
        node
        for node in payload["nodes"]
        if node["type"] == "PERSON"
    ]

    if (
        not people
        or not name.strip()
    ):
        return payload

    choices = {
        node["id"]: node["label"]
        for node in people
    }

    match = process.extractOne(
        name,
        choices,
        scorer=fuzz.WRatio,
    )

    if (
        not match
        or match[1] < 45
    ):
        return payload

    matched_id = match[2]

    reachable = set()

    if graph.has_node(
        matched_id
    ):

        reachable = set(
            nx.bfs_tree(
                graph,
                matched_id,
            ).nodes()
        )

        reachable.add(
            matched_id
        )

    for node in payload["nodes"]:

        node["highlighted"] = (
            node["id"]
            in reachable
        )

    for edge in payload["edges"]:

        edge["highlighted"] = (
            edge["source"]
            in reachable
            and edge["target"]
            in reachable
        )

    payload[
        "matched_node"
    ] = matched_id

    return payload