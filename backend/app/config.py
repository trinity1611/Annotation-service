"""
Application configuration using Pydantic Settings.
Reads environment variables with sensible defaults.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the FHIR Terminology Mapping Microservice."""

    app_title: str = "FHIR Terminology Mapping Microservice"
    app_version: str = "1.0.0"
    debug: bool = True

    # Hugging Face token for gated models (pyannote diarization)
    hf_token: str = Field(default="", alias="HF_TOKEN")

    # Whisper model size for faster-whisper (tiny, base, small, medium, large-v3)
    whisper_model: str = Field(default="large-v3", alias="WHISPER_MODEL")

    # Device for GPU inference (cuda or cpu)
    device: str = Field(default="cuda", alias="DEVICE")

    # Public RxNorm REST API base URL (no key needed)
    rxnorm_api_base: str = "https://rxnav.nlm.nih.gov/REST"

    # Static files directory (frontend)
    frontend_dir: str = "frontend"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
