from fastapi import APIRouter

from backend.models import AskBody
from backend.services.copilot_service import answer_question

router = APIRouter(tags=["copilot"])


@router.post("/cases/{case_id}/ask")
def ask(case_id: int, body: AskBody):
    return answer_question(case_id, body.question)
