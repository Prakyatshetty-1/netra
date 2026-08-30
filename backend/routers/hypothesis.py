from fastapi import APIRouter

from backend.services.hypothesis_service import hypotheses_for_person

router = APIRouter(tags=["hypothesis"])


@router.get("/cases/{case_id}/hypotheses/{person_id}")
def get_hypotheses(case_id: int, person_id: int):
    return {"person_id": person_id, "hypotheses": hypotheses_for_person(case_id, person_id)}
