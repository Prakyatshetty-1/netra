import os
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.routers.graph import _public
from backend.services.extraction_service import (
    confirm_extraction,
    extract_entities,
    extract_relations,
    extract_text,
    get_document_ocr,
    process_document_with_gemini,
    process_handwritten_document,
    update_document_ocr_lines,
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


class LineCorrection(BaseModel):
    line_index: int
    corrected_text: str
    rationale: str = ""


class VerifyOCRBody(BaseModel):
    document_id: str
    lines: list[LineCorrection] = Field(default_factory=list)
    reviewer: str = "investigator"


@router.post("/cases/{case_id}/upload-pdf")
async def upload_pdf(case_id: int, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "Provide a valid file")
    raw = await file.read()
    low = file.filename.lower()
    if low.endswith(".pdf"):
        text, ocr_required, error_msg = extract_text(raw)
        if error_msg:
            raise HTTPException(500, error_msg)
    else:
        text, ocr_required = "", True

    entities = extract_entities(text) if text else []
    relations = extract_relations(entities, text) if text else []
    return {
        "filename": file.filename,
        "raw_text_preview": text[:500],
        "entities": entities,
        "relations": relations,
        "ocr_required": ocr_required,
    }


@router.post("/cases/{case_id}/ocr/upload")
async def upload_ocr_document(
    case_id: int,
    file: UploadFile = File(...),
    use_gemini: bool = Form(True),
    api_key: str | None = Form(None),
    x_gemini_key: str | None = Header(None, alias="X-Gemini-API-Key"),
):
    """Upload document/image, preserve original, run Gemini Vision AI or TrOCR line detection."""
    if not file.filename:
        raise HTTPException(400, "Filename missing")
    allowed_exts = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
    low = file.filename.lower()
    if not any(low.endswith(ext) for ext in allowed_exts):
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(allowed_exts)}")

    raw = await file.read()
    key = api_key or x_gemini_key
    try:
        if use_gemini or key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            try:
                result = process_document_with_gemini(case_id, file.filename, raw, api_key=key)
                return result
            except ValueError as val_err:
                if use_gemini or key:
                    raise HTTPException(400, str(val_err))
            except Exception as gemini_err:
                if use_gemini or key:
                    raise HTTPException(500, f"Gemini Vision OCR failed: {str(gemini_err)}")

        result = process_handwritten_document(case_id, file.filename, raw)
        if result["raw_text"]:
            entities = extract_entities(result["raw_text"])
            relations = extract_relations(entities, result["raw_text"])
            result["entities"] = entities
            result["relations"] = relations
        else:
            result["entities"] = []
            result["relations"] = []
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"OCR processing failed: {str(e)}")


@router.post("/cases/{case_id}/ocr/verify")
def verify_ocr(case_id: int, body: VerifyOCRBody):
    """Save human-corrected OCR lines, preserve raw OCR and original doc, and log audit event."""
    try:
        line_dicts = [l.model_dump() for l in body.lines]
        res = update_document_ocr_lines(
            case_id=case_id,
            doc_id=body.document_id,
            line_updates=line_dicts,
            reviewer=body.reviewer,
        )
        # Re-extract entities and relations from verified text
        verified_text = res.get("verified_text", "")
        entities = extract_entities(verified_text) if verified_text else []
        relations = extract_relations(entities, verified_text) if verified_text else []
        return {
            **res,
            "entities": entities,
            "relations": relations,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Verification failed: {str(e)}")


@router.get("/cases/{case_id}/ocr/documents/{doc_id}")
def get_ocr_doc(case_id: int, doc_id: str):
    """Retrieve document OCR record and line results."""
    doc = get_document_ocr(doc_id)
    if not doc or doc["case_id"] != case_id:
        raise HTTPException(404, "Document OCR record not found")
    return doc


@router.post("/cases/{case_id}/upload-pdf/confirm")
def confirm_pdf(case_id: int, body: ConfirmBody):
    summary = confirm_extraction(
        case_id,
        [e.model_dump() for e in body.entities],
        [r.model_dump() for r in body.relations],
    )
    graph = _public(enrich_case_graph(case_id))
    return {**summary, "graph": graph}

