"""
Audio Transcription & Diarization Routes
==========================================
POST /api/audio/transcribe      – upload audio file (.wav, .mp3, etc.), get diarized
                                   speaker-attributed output + NLP extraction
POST /api/audio/transcribe-text – send raw text (for testing), get NLP extraction
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel
from typing import Optional

from backend.app.services.transcription import transcribe_audio
from backend.app.services.nlp_engine import extract_clinical_entities

router = APIRouter(prefix="/api/audio", tags=["Audio"])


class UtteranceItem(BaseModel):
    """A single speaker-diarized utterance in GT format."""
    utterance_id: str
    speaker_id: str
    speaker_role: str
    start_time: float
    end_time: float
    original_text: str
    translated_text: str


class TranscriptionResponse(BaseModel):
    transcript: str                         # Flat English text (for NLP)
    original_transcript: str                # Flat source-language text
    language: str
    extracted: dict                         # NLP-extracted clinical entities
    diarized_output: list[UtteranceItem]    # GT-format speaker-diarized utterances


class TextInputRequest(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = Form(default=""),
):
    """
    Accept a raw audio file (wav, mp3, m4a, webm, etc.) and return:
    1. Speaker-diarized utterances with timestamps & English translation
    2. Flat English transcript (for NLP entity extraction)
    3. Flat original-language transcript
    4. Pre-extracted clinical entities mapped to the 7 form sections

    All processing runs on local GPU (faster-whisper + pyannote.audio).
    Supported audio formats: .wav, .mp3, .m4a, .webm, .ogg, .flac, .aac
    Supported languages: English (en), Hindi (hi), Hinglish
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Validate file extension for common audio types
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_extensions = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac", ".aac", ".wma", ".opus"}
    if ext and ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. Supported formats: {', '.join(sorted(allowed_extensions))}"
        )

    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # Transcribe + diarize with local GPU pipeline
    result = transcribe_audio(audio_bytes, file.filename, language_hint=language or "")

    # Extract clinical entities from the English transcript
    extracted = extract_clinical_entities(result["transcript"])

    return TranscriptionResponse(
        transcript=result["transcript"],
        original_transcript=result["original_transcript"],
        language=result["language"],
        extracted=extracted,
        diarized_output=[
            UtteranceItem(**u) for u in result.get("diarized_output", [])
        ],
    )


@router.post("/transcribe-text", response_model=TranscriptionResponse)
async def transcribe_text(body: TextInputRequest):
    """
    Accept raw clinical text (for testing without audio).
    Returns the same pre-extracted clinical entities.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text input")

    extracted = extract_clinical_entities(body.text)
    return TranscriptionResponse(
        transcript=body.text,
        original_transcript=body.text,
        language="en",
        extracted=extracted,
        diarized_output=[],
    )
