"""NETRA prototype API — evidence-centric investigator dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import (
    cases,
    casedna,
    cctv,
    contradiction,
    copilot,
    counterfactual,
    decisions,
    extraction,
    graph,
    hypothesis,
    identity,
    image_upload,
)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ANNOTATED_DIR = FRONTEND / "annotated"
ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)
CROPS_DIR = FRONTEND / "crops"
CROPS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="NETRA Prototype",
    description="Evidence-centric criminal-network analysis dashboard (SIH PS 26189).",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(cases.router)
app.include_router(graph.router)
app.include_router(identity.router)
app.include_router(casedna.router)
app.include_router(hypothesis.router)
app.include_router(contradiction.router)
app.include_router(counterfactual.router)
app.include_router(copilot.router)
app.include_router(decisions.router)
app.include_router(extraction.router)
app.include_router(image_upload.router)
app.include_router(cctv.router)


from backend.db import DOCUMENTS_DIR
from backend.services.cctv_service import CCTV_DIR

app.mount("/annotated", StaticFiles(directory=ANNOTATED_DIR), name="annotated")
app.mount("/static/crops", StaticFiles(directory=CROPS_DIR), name="static_crops")
app.mount("/crops", StaticFiles(directory=CROPS_DIR), name="crops")
app.mount("/uploaded_docs/cctv", StaticFiles(directory=CCTV_DIR), name="uploaded_cctv")
app.mount("/uploaded_docs", StaticFiles(directory=DOCUMENTS_DIR), name="uploaded_docs")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")



@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")

