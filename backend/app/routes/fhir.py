"""
FHIR Bundle Routes
===================
POST /api/fhir/bundle – compile the clinical form into a FHIR Transaction Bundle,
                        save to database and to FHIR_gt/<patient_id>/<bundle>.json
GET  /api/fhir/bundles – list saved FHIR bundles from FHIR_gt directory
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any
from sqlalchemy.orm import Session

from backend.app.services.fhir_bundler import build_fhir_bundle
from backend.app.database import get_db
from backend.app.models import FHIRBundleRecord

router = APIRouter(prefix="/api/fhir", tags=["FHIR"])

# ---------------------------------------------------------------------------
# FHIR ground-truth output directory
# ---------------------------------------------------------------------------

# Resolve FHIR_gt relative to the project root (where the server is run from)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # Micro-Service/
FHIR_GT_DIR = _PROJECT_ROOT / "FHIR_gt"


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters that are invalid in filenames."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = sanitized.strip('. ')
    return sanitized or "unknown"


def _save_fhir_to_filesystem(bundle: dict[str, Any], patient_id: str, patient_name: str) -> str:
    """
    Save the FHIR bundle JSON to FHIR_gt/<identifier>/<timestamped-bundle>.json.

    Uses patient_id if available, otherwise falls back to patient_name.
    Returns the path where the file was saved.
    """
    # Determine folder name: prefer patient_id, fall back to patient_name
    folder_name = _sanitize_filename(patient_id) if patient_id and patient_id != "Unknown" else _sanitize_filename(patient_name)
    if not folder_name or folder_name == "unknown":
        folder_name = "anonymous"

    patient_dir = FHIR_GT_DIR / folder_name
    patient_dir.mkdir(parents=True, exist_ok=True)

    # Generate a timestamped filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"fhir_bundle_{timestamp}.json"
    filepath = patient_dir / filename

    # Handle potential filename collision
    counter = 1
    while filepath.exists():
        filename = f"fhir_bundle_{timestamp}_{counter}.json"
        filepath = patient_dir / filename
        counter += 1

    # Write the JSON bundle
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)

    return str(filepath)


class FHIRBundleRequest(BaseModel):
    demographics: dict[str, Any] = {}
    encounter: dict[str, Any] = {}
    conditions: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    allergies: list[dict[str, Any]] = []
    medications: list[dict[str, Any]] = []
    carePlan: list[dict[str, Any]] = []


class FHIRBundleResponse(BaseModel):
    bundle: dict[str, Any]
    saved_path: str
    patient_id: str


@router.post("/bundle", response_model=FHIRBundleResponse)
async def create_bundle(form_data: FHIRBundleRequest, db: Session = Depends(get_db)):
    """
    Accept the full clinical summary form and return a FHIR R4
    Transaction Bundle JSON with inter-resource references.

    The bundle is:
    1. Saved to the SQLite database for querying.
    2. Saved as a JSON file under FHIR_gt/<patient_id>/<bundle>.json
    """
    data = form_data.model_dump()
    bundle = build_fhir_bundle(data)

    patient_id = data.get("demographics", {}).get("patient_id", "Unknown")
    patient_name = data.get("demographics", {}).get("name", "Unknown")

    # Save to database
    db_record = FHIRBundleRecord(
        patient_id=patient_id,
        patient_name=patient_name,
        encounter_reason=data.get("encounter", {}).get("reason", ""),
        bundle_json=bundle
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    # Save to filesystem under FHIR_gt/
    saved_path = _save_fhir_to_filesystem(bundle, patient_id, patient_name)

    return FHIRBundleResponse(
        bundle=bundle,
        saved_path=saved_path,
        patient_id=patient_id if patient_id != "Unknown" else patient_name,
    )


@router.get("/bundles")
async def list_bundles():
    """
    List all saved FHIR bundles from the FHIR_gt directory.
    Returns a summary of each patient folder and bundle count.
    """
    if not FHIR_GT_DIR.exists():
        return {"patients": [], "total_bundles": 0}

    patients = []
    total = 0
    for patient_dir in sorted(FHIR_GT_DIR.iterdir()):
        if patient_dir.is_dir():
            bundle_files = sorted(patient_dir.glob("*.json"))
            total += len(bundle_files)
            patients.append({
                "patient_id": patient_dir.name,
                "bundle_count": len(bundle_files),
                "bundles": [
                    {
                        "filename": f.name,
                        "size_bytes": f.stat().st_size,
                        "created_at": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
                    }
                    for f in bundle_files
                ],
            })

    return {"patients": patients, "total_bundles": total}
