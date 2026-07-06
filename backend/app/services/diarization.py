"""
GPU-Accelerated Speaker Diarization Pipeline
=============================================
Combines faster-whisper (transcription + translation) with pyannote.audio
(speaker diarization) to produce GT-format speaker-attributed, timestamped,
English-translated utterances.

Runs entirely on local GPU (CUDA). No external API calls required.

Models loaded once at startup (singleton), kept in GPU memory for fast
subsequent requests.

RTX 4060 (8GB VRAM) budget:
  - Whisper large-v3 ≈ 3 GB
  - pyannote segmentation ≈ 1 GB
  - Total ≈ 4 GB (well within 8 GB)
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import soundfile as sf
import scipy.signal
import torch

from backend.app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DiarizedUtterance:
    """A single speaker-attributed, timestamped utterance."""
    utterance_id: str       # e.g., "audio_0001"
    speaker_id: str         # e.g., "spk0"
    speaker_role: str       # e.g., "Speaker 1" (user can rename in UI)
    start_time: float       # seconds
    end_time: float         # seconds
    original_text: str      # Hindi / source-language text
    translated_text: str    # English translation

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Audio preprocessing
# ---------------------------------------------------------------------------

def _preprocess_audio(audio_bytes: bytes, filename: str) -> tuple[np.ndarray, int]:
    """
    Convert audio bytes to 16kHz mono float32 numpy array.
    Returns (audio_array, sample_rate=16000).
    """
    data, samplerate = sf.read(io.BytesIO(audio_bytes))

    # Convert to mono if stereo
    if len(data.shape) > 1 and data.shape[1] > 1:
        data = np.mean(data, axis=1)

    # Resample to 16kHz if needed
    target_sr = 16000
    if samplerate != target_sr:
        num_samples = int(round(len(data) * float(target_sr) / samplerate))
        data = scipy.signal.resample(data, num_samples)
        samplerate = target_sr

    # Ensure float32
    data = data.astype(np.float32)

    return data, samplerate


# ---------------------------------------------------------------------------
# Singleton GPU Pipeline
# ---------------------------------------------------------------------------

class DiarizationPipeline:
    """
    Singleton class that holds Whisper and pyannote models in GPU memory.
    Loaded once at first use, reused across all requests.
    """

    _instance: Optional[DiarizationPipeline] = None

    def __init__(self):
        self._whisper_model = None
        self._diarization_pipeline = None
        self._device = settings.device
        self._loaded = False

    @classmethod
    def get_instance(cls) -> DiarizationPipeline:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self):
        """Lazy-load models on first request."""
        if self._loaded:
            return

        logger.info("Loading GPU models (first request)...")
        logger.info("Device: %s", self._device)

        if self._device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available, falling back to CPU")
            self._device = "cpu"

        # ── Load faster-whisper ──
        from faster_whisper import WhisperModel

        compute_type = "float16" if self._device == "cuda" else "int8"
        logger.info("Loading Whisper model: %s (compute_type=%s)", settings.whisper_model, compute_type)

        self._whisper_model = WhisperModel(
            settings.whisper_model,
            device=self._device,
            compute_type=compute_type,
        )
        logger.info("Whisper model loaded successfully")

        # ── Load pyannote diarization ──
        if settings.hf_token:
            from pyannote.audio import Pipeline as PyannotePipeline

            logger.info("Loading pyannote speaker-diarization-3.1...")
            self._diarization_pipeline = PyannotePipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=settings.hf_token,
            )
            if self._device == "cuda":
                self._diarization_pipeline = self._diarization_pipeline.to(
                    torch.device("cuda")
                )
            logger.info("Pyannote diarization pipeline loaded successfully")
        else:
            logger.warning(
                "HF_TOKEN not set — pyannote diarization disabled. "
                "All speech will be attributed to a single speaker."
            )
            self._diarization_pipeline = None

        self._loaded = True
        logger.info("All GPU models loaded and ready")

    # -----------------------------------------------------------------------
    # Core processing
    # -----------------------------------------------------------------------

    def process(
        self,
        audio_bytes: bytes,
        filename: str,
        language_hint: str = "",
    ) -> dict:
        """
        Full pipeline: preprocess → transcribe → diarize → align.

        Returns dict with:
          - diarized_output: list[dict] (GT-format utterances)
          - transcript: str (flat English text for NLP)
          - original_transcript: str (flat source-language text)
          - language: str
        """
        self._ensure_loaded()

        # 1. Preprocess audio
        logger.info("Preprocessing audio: %s (%d bytes)", filename, len(audio_bytes))
        audio_array, sr = _preprocess_audio(audio_bytes, filename)
        duration = len(audio_array) / sr
        logger.info("Audio: %.1f seconds, %d Hz", duration, sr)

        # 2. Transcribe with Whisper (original language)
        logger.info("Running Whisper transcription (task=transcribe)...")
        original_segments = self._transcribe(audio_array, language_hint, task="transcribe")

        # 3. Translate with Whisper (to English)
        logger.info("Running Whisper translation (task=translate)...")
        translated_segments = self._transcribe(audio_array, language_hint, task="translate")

        # 4. Diarize with pyannote
        logger.info("Running speaker diarization...")
        speaker_segments = self._diarize(audio_array, sr)

        # 5. Align: map whisper words onto diarization segments
        logger.info("Aligning transcription with diarization...")
        utterances = self._align(
            original_segments,
            translated_segments,
            speaker_segments,
            base_id=os.path.splitext(os.path.basename(filename))[0] or "audio",
        )

        # 6. Build flat transcripts for backward compatibility
        flat_english = " ".join(u.translated_text for u in utterances if u.translated_text)
        flat_original = " ".join(u.original_text for u in utterances if u.original_text)

        # Detect language from whisper
        detected_lang = "hi" if language_hint == "hi" else ("en" if language_hint == "en" else "hi")

        return {
            "diarized_output": [u.to_dict() for u in utterances],
            "transcript": flat_english,
            "original_transcript": flat_original,
            "language": detected_lang,
        }

    # -----------------------------------------------------------------------
    # Whisper transcription
    # -----------------------------------------------------------------------

    def _transcribe(
        self,
        audio_array: np.ndarray,
        language_hint: str,
        task: str = "transcribe",
    ) -> list[dict]:
        """
        Run faster-whisper and return word-level segments.

        Returns list of dicts: [{"start": float, "end": float, "text": str}, ...]
        """
        language = language_hint if language_hint in ("hi", "en") else None

        segments, info = self._whisper_model.transcribe(
            audio_array,
            language=language,
            task=task,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )

        word_segments = []
        for segment in segments:
            if segment.words:
                for word in segment.words:
                    word_segments.append({
                        "start": word.start,
                        "end": word.end,
                        "text": word.word,
                    })
            else:
                # Fallback: use segment-level if word timestamps unavailable
                word_segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                })

        logger.info(
            "Whisper %s: %d word segments, detected language: %s (prob=%.2f)",
            task, len(word_segments),
            info.language, info.language_probability,
        )
        return word_segments

    # -----------------------------------------------------------------------
    # Pyannote diarization
    # -----------------------------------------------------------------------

    def _diarize(
        self,
        audio_array: np.ndarray,
        sr: int,
    ) -> list[dict]:
        """
        Run pyannote speaker diarization.

        Returns list of dicts: [{"start": float, "end": float, "speaker": str}, ...]
        sorted by start time.
        """
        if self._diarization_pipeline is None:
            # No diarization available — treat entire audio as single speaker
            duration = len(audio_array) / sr
            return [{"start": 0.0, "end": duration, "speaker": "spk0"}]

        # Pyannote accepts a dict for in-memory audio when torchcodec fails
        waveform = torch.from_numpy(audio_array).float()
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        audio_in_memory = {"waveform": waveform, "sample_rate": sr}

        diarization_output = self._diarization_pipeline(audio_in_memory)
        if hasattr(diarization_output, "speaker_diarization"):
            diarization = diarization_output.speaker_diarization
        else:
            diarization = diarization_output

        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker,
            })

        # Sort by start time
        speaker_segments.sort(key=lambda x: x["start"])

        logger.info("Diarization: %d speaker segments found", len(speaker_segments))
        return speaker_segments

    # -----------------------------------------------------------------------
    # Alignment: whisper words × diarization segments → GT-format utterances
    # -----------------------------------------------------------------------

    def _align(
        self,
        original_words: list[dict],
        translated_words: list[dict],
        speaker_segments: list[dict],
        base_id: str,
    ) -> list[DiarizedUtterance]:
        """
        For each diarization segment, find the whisper words whose midpoint
        falls within the segment. Concatenate them into speaker utterances.

        Merges consecutive segments from the same speaker if gap < 0.5s.
        """
        if not speaker_segments:
            return []

        # Merge adjacent segments from the same speaker with small gap
        merged_segments = self._merge_speaker_segments(speaker_segments, max_gap=0.5)

        # Build a unique speaker-id to role mapping
        unique_speakers = []
        for seg in merged_segments:
            if seg["speaker"] not in unique_speakers:
                unique_speakers.append(seg["speaker"])

        speaker_role_map = {}
        for idx, spk in enumerate(unique_speakers):
            speaker_role_map[spk] = f"Speaker {idx + 1}"

        utterances = []
        utt_counter = 0

        for seg in merged_segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            speaker = seg["speaker"]

            # Find original words in this segment
            orig_text = self._collect_words_in_range(original_words, seg_start, seg_end)
            trans_text = self._collect_words_in_range(translated_words, seg_start, seg_end)

            # Skip empty segments
            if not orig_text.strip() and not trans_text.strip():
                continue

            utt_counter += 1
            utterances.append(DiarizedUtterance(
                utterance_id=f"{base_id}_{utt_counter:04d}",
                speaker_id=speaker,
                speaker_role=speaker_role_map.get(speaker, "Unknown"),
                start_time=round(seg_start, 3),
                end_time=round(seg_end, 3),
                original_text=orig_text.strip(),
                translated_text=trans_text.strip(),
            ))

        logger.info(
            "Alignment complete: %d utterances, %d unique speakers",
            len(utterances), len(unique_speakers),
        )
        return utterances

    @staticmethod
    def _collect_words_in_range(
        words: list[dict],
        range_start: float,
        range_end: float,
    ) -> str:
        """Collect words whose midpoint falls within [range_start, range_end]."""
        collected = []
        for w in words:
            midpoint = (w["start"] + w["end"]) / 2.0
            if range_start <= midpoint <= range_end:
                collected.append(w["text"])
        return " ".join(collected)

    @staticmethod
    def _merge_speaker_segments(
        segments: list[dict],
        max_gap: float = 0.5,
    ) -> list[dict]:
        """Merge consecutive segments from the same speaker if gap < max_gap."""
        if not segments:
            return []

        merged = [segments[0].copy()]
        for seg in segments[1:]:
            prev = merged[-1]
            if (
                seg["speaker"] == prev["speaker"]
                and (seg["start"] - prev["end"]) < max_gap
            ):
                # Extend previous segment
                prev["end"] = seg["end"]
            else:
                merged.append(seg.copy())

        return merged
