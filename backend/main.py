"""NETRA prototype API — evidence-centric investigator dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.identity_store import init_identity_db

from backend.routers import (
    cases,
    casedna,
    contradiction,
    copilot,
    counterfactual,
    decisions,
    digilocker,
    extraction,
    graph,
    hypothesis,
    identity,
)


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


app = FastAPI(
    title="NETRA Prototype",
    description="Evidence-centric criminal-network analysis dashboard (SIH PS 26189).",
    version="0.1.0",
)


# ---------------------------------------------------------------------
# Identity database initialization
# ---------------------------------------------------------------------
#
# This creates netra_identity.db if it does not already exist.
#
# It is kept separate from netra_sim.db so the existing investigation
# dataset is not modified.
#

init_identity_db()


# ---------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ---------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------

app.include_router(cases.router)

app.include_router(graph.router)

app.include_router(identity.router)

# DigiLocker identity verification
app.include_router(digilocker.router)

app.include_router(casedna.router)

app.include_router(hypothesis.router)

app.include_router(contradiction.router)

app.include_router(counterfactual.router)

app.include_router(copilot.router)

app.include_router(decisions.router)

app.include_router(extraction.router)


# ---------------------------------------------------------------------
# Frontend static files
# ---------------------------------------------------------------------

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND),
    name="static",
)


# ---------------------------------------------------------------------
# Root page
# ---------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(
        FRONTEND / "index.html"
    )