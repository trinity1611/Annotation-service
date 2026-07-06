"""
Audio Transcription & Diarization Service
==========================================
Uses the local GPU-accelerated DiarizationPipeline (faster-whisper + pyannote)
to transcribe, translate, and diarize clinical audio.

Runs entirely on local GPU (CUDA) with no external API calls.
Supports .wav, .mp3, .m4a, .webm, .ogg, and other common audio formats.
Returns speaker-diarized, timestamped, English-translated utterances in
GT format alongside flat transcripts for backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.services.diarization import DiarizationPipeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_hint: str = "",
) -> dict[str, Any]:
    """
    Transcribe and diarize raw clinical audio using local GPU models.

    Returns a dict:
        - transcript: str — flat English text (for NLP entity extraction)
        - original_transcript: str — flat source-language text
        - language: str — detected language code ('en', 'hi', etc.)
        - diarized_output: list[dict] — GT-format speaker-attributed utterances
          Each dict contains:
            - utterance_id, speaker_id, speaker_role
            - start_time, end_time
            - original_text, translated_text

    Pipeline:
        1. Preprocess audio → 16kHz mono
        2. Whisper transcribe (original language with word timestamps)
        3. Whisper translate (to English with word timestamps)
        4. Pyannote speaker diarization
        5. Align whisper words to diarization segments
    """
    logger.info(
        "Processing audio: %s (%d bytes, language_hint=%s)",
        filename, len(audio_bytes), language_hint or "auto",
    )

    pipeline = DiarizationPipeline.get_instance()
    result = pipeline.process(audio_bytes, filename, language_hint=language_hint)

    logger.info(
        "Transcription complete: %d utterances, %d chars English, %d chars original",
        len(result.get("diarized_output", [])),
        len(result.get("transcript", "")),
        len(result.get("original_transcript", "")),
    )

    return result
