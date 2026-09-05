"""FastAPI router for CCTV Video Ingestion & YOLO Detection."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.services.cctv_service import get_cctv_video_details, process_cctv_video

router = APIRouter(tags=["cctv"])


@router.post("/cases/{case_id}/cctv/upload")
async def upload_cctv_video(
    case_id: int,
    file: UploadFile = File(...),
    sample_rate_sec: float = Form(1.0),
    confidence_threshold: float = Form(0.50),
):
    """Upload CCTV video evidence, extract metadata, sample frames, and run YOLO object detection."""
    if not file.filename:
        raise HTTPException(400, "Filename missing")

    allowed_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    low = file.filename.lower()
    if not any(low.endswith(ext) for ext in allowed_exts):
        raise HTTPException(
            400, f"Unsupported video format. Allowed formats: {', '.join(sorted(allowed_exts))}"
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "Uploaded video file is empty")

    try:
        result = process_cctv_video(
            case_id=case_id,
            filename=file.filename,
            file_bytes=raw_bytes,
            sample_rate_sec=sample_rate_sec,
            confidence_threshold=confidence_threshold,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"CCTV Video processing failed: {str(e)}")


@router.get("/cases/{case_id}/cctv/{video_id}")
def get_cctv_video(case_id: int, video_id: str):
    """Retrieve CCTV video evidence record and detection results."""
    details = get_cctv_video_details(video_id)
    if not details or details["case_id"] != case_id:
        raise HTTPException(404, "CCTV video record not found")
    return details
