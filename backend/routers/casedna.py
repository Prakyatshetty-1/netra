from fastapi import APIRouter

from backend.services.casedna_service import related_cases

router = APIRouter(tags=["casedna"])


@router.get("/cases/{case_id}/related-cases")
def get_related(case_id: int):
    return {"related": related_cases(case_id)}
