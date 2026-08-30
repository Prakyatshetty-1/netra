from fastapi import APIRouter

from backend.services.identity_service import identity_candidates

router = APIRouter(tags=["identity"])


@router.get("/cases/{case_id}/identity-candidates")
def get_identity(case_id: int):
    return {"candidates": identity_candidates(case_id)}
