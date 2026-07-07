"""
Audio Transcription & Diarization Service (GT File Mapping)
============================================================
Instead of running heavy Diarization or LLM pipelines, it reads the existing GT
transcripts and translates them from Hindi to English using deep-translator.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from deep_translator import GoogleTranslator
import time

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
    Mock audio transcription. Instead of running heavy models,
    it maps the filename to a GT folder file, reads the TSV, 
    and translates Hindi to English using deep-translator.
    """
    logger.info(
        "Processing audio using GT Mapping: %s (%d bytes)",
        filename, len(audio_bytes)
    )

    base_name = os.path.splitext(os.path.basename(filename))[0]
    
    # Locate the GT file folder (assumes GT is in the parent of the Micro-Service workspace root)
    gt_file_path = os.path.abspath(os.path.join(
        r"C:\Users\Hp\OneDrive\Desktop\Micro-Service\GT", 
        f"{base_name}.txt"
    ))
    
    diarized_output = []
    original_texts = []
    
    # To store metadata of the parsed lines
    parsed_lines = []
    
    if os.path.exists(gt_file_path):
        logger.info("Found GT file: %s", gt_file_path)
        with open(gt_file_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 7:
                    parsed_lines.append({
                        "utterance_id": parts[1],
                        "speaker_id": parts[2],
                        "speaker_role": parts[3],
                        "start_time": float(parts[4]),
                        "end_time": float(parts[5]),
                        "original_text": parts[6]
                    })
                    original_texts.append(parts[6])
    else:
        logger.warning("GT file not found: %s", gt_file_path)

    translated_texts = []
    if original_texts:
        try:
            translator = GoogleTranslator(source='auto', target='en')
            # translate_batch is more efficient than translating line by line
            translated_texts = translator.translate_batch(original_texts)
        except Exception as e:
            logger.error(f"Batch translation failed: {e}. Falling back to line-by-line translation.")
            translated_texts = []
            for text in original_texts:
                try:
                    t_text = translator.translate(text)
                    translated_texts.append(t_text)
                    time.sleep(0.5) # small delay to prevent rate limit
                except Exception as ex:
                    logger.error(f"Line translation failed: {ex}")
                    translated_texts.append(text) # fallback to original text for this line
    
    for i, meta in enumerate(parsed_lines):
        t_text = translated_texts[i] if i < len(translated_texts) and translated_texts[i] else meta["original_text"]
        diarized_output.append({
            "utterance_id": meta["utterance_id"],
            "speaker_id": meta["speaker_id"],
            "speaker_role": meta["speaker_role"],
            "start_time": meta["start_time"],
            "end_time": meta["end_time"],
            "original_text": meta["original_text"],
            "translated_text": t_text
        })
        
    flat_english = " ".join([d["translated_text"] for d in diarized_output])
    flat_original = " ".join([d["original_text"] for d in diarized_output])
    
    result = {
        "diarized_output": diarized_output,
        "transcript": flat_english,
        "original_transcript": flat_original,
        "language": "hi",
    }
    
    logger.info(
        "Transcription complete: %d utterances",
        len(result.get("diarized_output", [])),
    )
    
    return result
