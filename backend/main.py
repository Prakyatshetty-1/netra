"""NETRA prototype API — evidence-centric investigator dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import (
    cases,
    casedna,
    contradiction,
    copilot,
    counterfactual,
    decisions,
    extraction,
    graph,
    hypothesis,
    identity,
    entity_intelligence,
    digilocker,
)

from backend.identity_store import init_identity_db


FRONTEND = (
    Path(__file__).resolve().parent.parent
    / "frontend"
)


app = FastAPI(
    title="NETRA Prototype",
    description=(
        "Evidence-centric criminal-network "
        "analysis dashboard."
    ),
    version="0.2.0",
)


# ------------------------------------------------------------
# CORS
# ------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ------------------------------------------------------------
# STARTUP
# ------------------------------------------------------------

@app.on_event("startup")
def startup():
    """
    Initialise the separate identity-verification
    database.

    The original NETRA simulation database is not
    modified by this function.
    """

    init_identity_db()


# ------------------------------------------------------------
# ROUTERS
# ------------------------------------------------------------

app.include_router(
    cases.router
)

app.include_router(
    graph.router
)

app.include_router(
    identity.router
)

# Existing DigiLocker OAuth / mock system.
app.include_router(
    digilocker.router
)

# New Entity Intelligence system.
app.include_router(
    entity_intelligence.router
)

app.include_router(
    casedna.router
)

app.include_router(
    hypothesis.router
)

app.include_router(
    contradiction.router
)

app.include_router(
    counterfactual.router
)

app.include_router(
    copilot.router
)

app.include_router(
    decisions.router
)

app.include_router(
    extraction.router
)


# ------------------------------------------------------------
# FRONTEND
# ------------------------------------------------------------

app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND
    ),
    name="static",
)


@app.get("/")
def index():
    return FileResponse(
        FRONTEND / "index.html"
    )