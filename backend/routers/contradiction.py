from fastapi import APIRouter

from backend.services.contradiction_service import find_contradictions

router = APIRouter(tags=["contradiction"])


@router.get("/cases/{case_id}/contradictions/{person_id}")
def get_contradictions(case_id: int, person_id: int):
    return {"contradictions": find_contradictions(case_id, person_id)}
