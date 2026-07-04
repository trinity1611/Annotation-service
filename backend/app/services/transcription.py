"""
Audio Transcription & Translation Service
==========================================
When SARVAM_API_KEY is configured, uses the Sarvam API to transcribe
clinical audio (supports Hindi, English, Hinglish). Otherwise falls back to
a built-in simulation engine that returns realistic sample clinical notes for
demo and testing purposes.

Supports .wav, .mp3, .m4a, .webm, .ogg, and other common audio formats.
Returns both the original-language transcript and an English translation
when the source language is non-English (e.g., Hindi/Hinglish).
"""

from __future__ import annotations

import io
import logging
import mimetypes
from typing import Any, BinaryIO

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MIME type mapping for audio formats
# ---------------------------------------------------------------------------

_MIME_MAP: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma",
    ".opus": "audio/opus",
}


def _get_mime_type(filename: str) -> str:
    """Resolve the correct MIME type for an audio file by extension."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    return _MIME_MAP.get(ext, "audio/mpeg")


# ---------------------------------------------------------------------------
# Simulated clinical transcripts for demo mode
# ---------------------------------------------------------------------------

_DEMO_TRANSCRIPTS = [
    (
        "Patient is a 45-year-old male named Ramesh Kumar presenting with complaints of "
        "persistent fever for 3 days, temperature recorded at 101.2 degrees Fahrenheit. "
        "He also reports headache and body aches. Patient has a known history of Type 2 "
        "diabetes mellitus, currently on Metformin 500 mg twice daily. Blood pressure is "
        "130/85 mmHg, heart rate 92 beats per minute, oxygen saturation 97 percent. "
        "He is allergic to Penicillin which causes skin rash. Lab results show hemoglobin "
        "12.5 g/dL, fasting blood sugar 180 mg/dL, and HbA1c at 8.2 percent. "
        "Assessment: Viral fever with uncontrolled diabetes. Plan: Prescribe Paracetamol "
        "650 mg three times a day for 5 days. Continue Metformin. Advise CBC and thyroid "
        "panel. Follow up in one week. Encounter type: OPD."
    ),
    (
        "Female patient aged 32, Priya Sharma. Chief complaint: severe cough for one week "
        "with greenish sputum, shortness of breath. No known drug allergies. Vitals: "
        "temperature 99.8 Fahrenheit, blood pressure 118/76 mmHg, respiratory rate 22 "
        "breaths per minute, SpO2 94 percent. History of asthma since childhood. "
        "Currently taking Salbutamol inhaler as needed. Chest X-ray shows bilateral "
        "infiltrates. Diagnosis: Pneumonia with acute asthma exacerbation. Plan: Start "
        "Azithromycin 500 mg once daily for 5 days, nebulization with Salbutamol, "
        "Prednisolone 40 mg daily tapering over 7 days. Refer for pulmonology consult. "
        "Follow-up in 3 days. Visit type: Emergency."
    ),
    (
        "Patient Anil Verma, 58-year-old male. Presenting with chest pain radiating to "
        "left arm, sweating, and nausea for 2 hours. Known case of hypertension and "
        "hyperlipidemia on Amlodipine 5 mg and Atorvastatin 20 mg. Allergic to Aspirin "
        "causing breathing difficulty. Vitals: BP 160/100 mmHg, HR 110 bpm, SpO2 96%. "
        "ECG shows ST elevation in leads II, III, aVF. Troponin I elevated. Lab: "
        "Total cholesterol 260 mg/dL, LDL 180 mg/dL, creatinine 1.2 mg/dL. "
        "Diagnosis: Acute inferior STEMI (myocardial infarction). Plan: Emergency "
        "cardiology referral, start Clopidogrel 300 mg loading then 75 mg daily, "
        "IV Heparin, prepare for angiography. Admit to ICU. Encounter: Inpatient."
    ),
]

# Demo Hindi transcripts for Hindi-mode demo
_DEMO_TRANSCRIPTS_HINDI = [
    (
        "मरीज का नाम रामेश कुमार है, उम्र 45 साल, पुरुष। पिछले 3 दिनों से लगातार बुखार "
        "की शिकायत है, तापमान 101.2 डिग्री फ़ारेनहाइट दर्ज किया गया। सिरदर्द और शरीर में "
        "दर्द की भी शिकायत है। मरीज को टाइप 2 डायबिटीज मेलिटस की पुरानी बीमारी है, "
        "वर्तमान में मेटफॉर्मिन 500 mg दिन में दो बार ले रहे हैं। ब्लड प्रेशर 130/85 mmHg, "
        "हृदय गति 92 प्रति मिनट, ऑक्सीजन सैचुरेशन 97 प्रतिशत। पेनिसिलिन से एलर्जी है "
        "जिससे त्वचा पर चकत्ते हो जाते हैं। जांच: हीमोग्लोबिन 12.5 g/dL, फास्टिंग शुगर "
        "180 mg/dL, HbA1c 8.2 प्रतिशत। निदान: वायरल बुखार और अनियंत्रित डायबिटीज। "
        "उपचार योजना: पैरासिटामॉल 650 mg दिन में तीन बार 5 दिन के लिए। मेटफॉर्मिन जारी "
        "रखें। CBC और थायराइड पैनल की सलाह। एक हफ्ते में फॉलो-अप। OPD विज़िट।"
    ),
    (
        "महिला मरीज, उम्र 32 साल, प्रिया शर्मा। मुख्य शिकायत: एक हफ्ते से गंभीर खांसी "
        "हरे रंग के बलगम के साथ, सांस लेने में तकलीफ़। कोई ज्ञात दवा एलर्जी नहीं। "
        "तापमान 99.8 फ़ारेनहाइट, ब्लड प्रेशर 118/76 mmHg, श्वसन दर 22 प्रति मिनट, "
        "SpO2 94 प्रतिशत। बचपन से अस्थमा की बीमारी। वर्तमान में ज़रूरत पड़ने पर "
        "सालबुटामोल इनहेलर ले रही हैं। छाती का एक्स-रे दोनों तरफ़ इन्फ़िल्ट्रेट दिखाता है। "
        "निदान: निमोनिया और तीव्र अस्थमा। उपचार: एज़िथ्रोमाइसिन 500 mg दिन में एक बार "
        "5 दिन, सालबुटामोल नेबुलाइज़ेशन, प्रेडनिसोलोन 40 mg। पल्मोनोलॉजी रेफ़रल। "
        "3 दिन में फॉलो-अप। आपातकालीन विज़िट।"
    ),
]

_demo_index = 0
_demo_hindi_index = 0


def _get_demo_transcript() -> dict[str, Any]:
    """Cycle through the demo transcripts, returning both English text."""
    global _demo_index
    transcript = _DEMO_TRANSCRIPTS[_demo_index % len(_DEMO_TRANSCRIPTS)]
    _demo_index += 1
    return {
        "transcript": transcript,
        "original_transcript": transcript,
        "language": "en",
    }


def _get_demo_transcript_hindi() -> dict[str, Any]:
    """Cycle through Hindi demo transcripts with English translations."""
    global _demo_hindi_index, _demo_index
    hindi_text = _DEMO_TRANSCRIPTS_HINDI[_demo_hindi_index % len(_DEMO_TRANSCRIPTS_HINDI)]
    english_text = _DEMO_TRANSCRIPTS[_demo_hindi_index % len(_DEMO_TRANSCRIPTS)]
    _demo_hindi_index += 1
    return {
        "transcript": english_text,
        "original_transcript": hindi_text,
        "language": "hi",
    }



# Sarvam AI API transcription
# ---------------------------------------------------------------------------

def _transcribe_with_sarvam(audio_bytes: bytes, filename: str, language_hint: str) -> dict[str, Any]:
    """
    Call the Sarvam AI Speech-to-Text API.
    
    Step 1: Transcribe to get the raw transcript.
    Step 2: If language is Hindi (or unknown), also translate to English for NLP.
    """
    import requests as _requests

    headers = {"api-subscription-key": settings.sarvam_api_key}
    mime_type = _get_mime_type(filename)
    
    # Map hint to Sarvam language-code format
    language_code = "hi-IN" if language_hint == "hi" else "en-IN" if language_hint == "en" else None

    # Step 1: Transcribe in original language
    files_transcribe = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}
    data_transcribe = {
        "model": "saaras:v3",
        "mode": "transcribe",
    }
    if language_code:
        data_transcribe["language-code"] = language_code

    resp = _requests.post(
        "https://api.sarvam.ai/speech-to-text",
        headers=headers,
        files=files_transcribe,
        data=data_transcribe,
        timeout=120,
    )
    resp.raise_for_status()
    original_text = resp.json().get("transcript", "").strip()

    # Step 2: Translate to English if it's Hindi or unknown
    if language_hint != "en":
        files_translate = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}
        data_translate = {
            "model": "saaras:v3",
            "mode": "translate",
        }
        if language_code:
            data_translate["language-code"] = language_code
            
        resp_trans = _requests.post(
            "https://api.sarvam.ai/speech-to-text",
            headers=headers,
            files=files_translate,
            data=data_translate,
            timeout=120,
        )
        if resp_trans.status_code == 200:
            english_text = resp_trans.json().get("transcript", "").strip()
        else:
            english_text = original_text
    else:
        english_text = original_text

    return {
        "transcript": english_text,
        "original_transcript": original_text,
        "language": language_hint if language_hint else "en",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language_hint: str = "",
) -> dict[str, Any]:
    """
    Transcribe raw clinical audio to text, supporting both English and Hindi.

    Returns a dict:
        - transcript: English text (used for NLP entity extraction)
        - original_transcript: text in the original spoken language
        - language: detected language code ('en', 'hi', etc.)

    Strategy:
        1. If SARVAM_API_KEY is configured → call the Sarvam API.
        2. Otherwise → return the next demo clinical transcript.
    """
    if settings.sarvam_api_key:
        logger.info("Transcribing via Sarvam AI API (%d bytes, file=%s)", len(audio_bytes), filename)
        try:
            return _transcribe_with_sarvam(audio_bytes, filename, language_hint)
        except Exception as exc:
            logger.error("Sarvam transcription failed: %s – falling back to demo", exc)
            if language_hint == "hi":
                return _get_demo_transcript_hindi()
            return _get_demo_transcript()

    else:
        logger.info("No API keys configured – returning demo transcript")
        if language_hint == "hi":
            return _get_demo_transcript_hindi()
        return _get_demo_transcript()
