from fastapi import APIRouter

from backend.services.counterfactual_service import counterfactual

router = APIRouter(tags=["counterfactual"])


@router.post("/cases/{case_id}/counterfactual/{person_id}")
def run_counterfactual(case_id: int, person_id: int):
    return counterfactual(case_id, person_id)
