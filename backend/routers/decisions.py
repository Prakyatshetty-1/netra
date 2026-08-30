from fastapi import APIRouter

from backend.models import DecisionBody
from backend.services.provenance_service import log_decision

router = APIRouter(tags=["decisions"])


@router.post("/cases/{case_id}/decisions")
def record_decision(case_id: int, body: DecisionBody):
    return log_decision(case_id, body.decision, body.reviewer, body.rationale)
