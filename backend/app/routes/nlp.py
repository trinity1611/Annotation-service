"""
Clinical NLP Extraction Routes
================================
POST /api/nlp/extract – extract clinical entities from text
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.nlp_engine import extract_clinical_entities

router = APIRouter(prefix="/api/nlp", tags=["NLP"])


class NLPRequest(BaseModel):
    text: str


@router.post("/extract")
async def extract(body: NLPRequest):
    """Extract clinical entities from free-text clinical notes."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text input")

    return extract_clinical_entities(body.text)
