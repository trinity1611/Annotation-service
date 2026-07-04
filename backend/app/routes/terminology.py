"""
Terminology Search Routes
==========================
GET /api/terminology/search  – fuzzy search by resource type
GET /api/terminology/map-unit – local UCUM unit lookup
"""

from fastapi import APIRouter, HTTPException, Query

from backend.app.services.terminology_gateway import search_terminology, search_unit

router = APIRouter(prefix="/api/terminology", tags=["Terminology"])


@router.get("/search")
async def terminology_search(
    text: str = Query(..., description="Search query text"),
    resource_type: str = Query(..., description="FHIR resource type: Condition, Observation, AllergyIntolerance, MedicationRequest, CarePlan, Encounter, Unit"),
):
    """
    Search the terminology gateway for matching clinical concepts.
    Returns a list of {code, system, display} matches.
    """
    if not text.strip():
        return []

    if resource_type.lower() == "unit":
        result = search_unit(text)
        if result:
            return [result]
        return []

    results = search_terminology(text, resource_type)
    return results


@router.get("/map-unit")
async def map_unit(
    unit_text: str = Query(..., description="Human-readable unit string (e.g., 'celsius', 'mg', 'mmhg')"),
):
    """
    Resolve a human-readable unit string to its official UCUM code.
    Returns {code, system, display} or 404 if not found.
    """
    result = search_unit(unit_text)
    if result:
        return result
    raise HTTPException(status_code=404, detail=f"Unit '{unit_text}' not found in UCUM local map")
