"""
FHIR Terminology Mapping Microservice – Main Application
==========================================================
Entry point for the FastAPI server.  Mounts all route modules and
serves the frontend static files.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.config import settings
from backend.app.routes import audio, nlp, terminology, fhir
from backend.app.database import engine
from backend.app import models

# Create database tables
models.Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "A microservice platform that bridges clinicians and complex FHIR data schemas. "
        "Upload clinical audio → get an English transcript → auto-extract entities → "
        "auto-code with SNOMED-CT / LOINC / RxNorm / UCUM → generate a FHIR Transaction Bundle."
    ),
)

# CORS – allow frontend served from same origin or dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.include_router(audio.router)
app.include_router(nlp.router)
app.include_router(terminology.router)
app.include_router(fhir.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.app_title,
        "version": settings.app_version,
    }


# ---------------------------------------------------------------------------
# Mount frontend static files
# ---------------------------------------------------------------------------

_frontend_path = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_path), html=True), name="frontend")
