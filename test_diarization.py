import sys
import os

# Add the project root to sys.path so backend module can be found
sys.path.append(os.path.abspath('.'))

import traceback
import logging
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from backend.app.services.transcription import transcribe_audio

def test_pipeline():
    audio_path = r"..\wav\2006763.wav"
    print(f"Testing with file: {audio_path}")
    
    try:
        print("Running transcribe_audio with GT mapping...")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
            
        results = transcribe_audio(audio_bytes=audio_bytes, filename="2006763.wav")
        print("Success! Processed results length:", len(results.get("diarized_output", [])))
        print("First utterance example:")
        if results.get("diarized_output"):
            print(json.dumps(results["diarized_output"][0], indent=2))
    except Exception as e:
        print("\n=== ERROR TRACEBACK ===")
        traceback.print_exc()

if __name__ == "__main__":
    test_pipeline()
