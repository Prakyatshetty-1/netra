"""Graph JSON + name search highlight."""

from fastapi import APIRouter, HTTPException, Query

from backend.services.graph_service import highlight_from_name
from backend.services.intelligence_service import enrich_case_graph

router = APIRouter(tags=["graph"])


def _public(payload: dict) -> dict:
    return {
        "case_id": payload["case_id"],
        "nodes": payload["nodes"],
        "edges": payload["edges"],
        "matched_node": payload.get("matched_node"),
    }


@router.get("/cases/{case_id}/graph")
def get_graph(case_id: int):
    payload = enrich_case_graph(case_id)
    if not payload["nodes"] and not payload["edges"]:
        # still valid — some cases may have no edges
        pass
    return _public(payload)


@router.get("/cases/{case_id}/graph/search")
def search_graph(case_id: int, name: str = Query(..., min_length=1)):
    payload = enrich_case_graph(case_id)
    if not payload["nodes"]:
        raise HTTPException(404, "No graph for this case")
    return _public(highlight_from_name(payload, name))
