"""PDF upload → extract draft → human confirm into GraphEdge."""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.routers.graph import _public
from backend.services.extraction_service import (
    confirm_extraction,
    extract_entities,
    extract_relations,
    extract_text,
)
from backend.services.intelligence_service import enrich_case_graph

router = APIRouter(tags=["extraction"])


class EntityDraft(BaseModel):
    text: str
    label: str
    start: int = 0
    included: bool = True


class RelationDraft(BaseModel):
    source: str
    target: str
    type: str
    confidence: float = 0.6
    sentence: str = ""
    included: bool = True


class ConfirmBody(BaseModel):
    entities: list[EntityDraft] = Field(default_factory=list)
    relations: list[RelationDraft] = Field(default_factory=list)


@router.post("/cases/{case_id}/upload-pdf")
async def upload_pdf(case_id: int, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF file")
    raw = await file.read()
    text, ocr_required, error_msg = extract_text(raw)
    if error_msg:
        raise HTTPException(500, error_msg)
    entities = extract_entities(text) if text else []
    relations = extract_relations(entities, text) if text else []
    return {
        "filename": file.filename,
        "raw_text_preview": text[:500],
        "entities": entities,
        "relations": relations,
        "ocr_required": ocr_required,
    }


@router.post("/cases/{case_id}/upload-pdf/confirm")
def confirm_pdf(case_id: int, body: ConfirmBody):
    summary = confirm_extraction(
        case_id,
        [e.model_dump() for e in body.entities],
        [r.model_dump() for r in body.relations],
    )
    graph = _public(enrich_case_graph(case_id))
    return {**summary, "graph": graph}
