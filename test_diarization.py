import sys
import os

# Add the project root to sys.path so backend module can be found
sys.path.append(os.path.abspath('.'))

import traceback
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.app.services.diarization import DiarizationPipeline
from backend.app.config import settings

def test_pipeline():
    audio_path = r"..\wav\2006763.wav"
    print(f"Testing with file: {audio_path}")
    print(f"HF_TOKEN: {settings.hf_token[:10]}...")
    
    try:
        pipeline = DiarizationPipeline.get_instance()
        print("Pipeline instance retrieved. Running process...")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        results = pipeline.process(audio_bytes=audio_bytes, filename="2006763.wav")
        print("Success! Processed results length:", len(results.get("diarized_output", [])))
    except Exception as e:
        print("\n=== ERROR TRACEBACK ===")
        traceback.print_exc()

if __name__ == "__main__":
    test_pipeline()
