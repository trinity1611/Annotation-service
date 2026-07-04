import pytest
from backend.app.services.terminology_gateway import (
    search_unit,
    search_condition,
    search_medication_rxnorm
)
from backend.app.services.nlp_engine import extract_clinical_entities
from backend.app.services.fhir_bundler import build_fhir_bundle

def test_unit_mapping():
    # Test UCUM local map
    res = search_unit("celsius")
    assert res is not None
    assert res["code"] == "Cel"
    assert res["system"] == "http://unitsofmeasure.org"

    res2 = search_unit("mg")
    assert res2 is not None
    assert res2["code"] == "mg"

def test_condition_search():
    # Fuzzy match diabetes
    res = search_condition("diab")
    assert len(res) > 0
    # Should include Type 2 diabetes
    codes = [r["code"] for r in res]
    assert "44054006" in codes  # Type 2 DM

def test_medication_local_fallback():
    # Test local dictionary match for medications (RxNorm fallback)
    res = search_medication_rxnorm("paracetamol")
    assert len(res) > 0
    assert res[0]["code"] == "161"

def test_nlp_extraction():
    # Test the regex extraction engine
    text = "Patient John Doe, 50 years old male. Complains of fever and headache. Known case of diabetes. Vitals: temperature 101 Fahrenheit, blood pressure 130/85 mmHg. Prescribe Metformin 500 mg twice daily. Advise blood test."
    
    extracted = extract_clinical_entities(text)
    
    assert extracted["demographics"]["name"] == "John Doe"
    assert extracted["demographics"]["age"] == 50
    assert extracted["demographics"]["gender"] == "male"
    
    conditions = [c["name"].lower() for c in extracted["conditions"]]
    assert "diabetes" in conditions
    assert "fever" in conditions
    assert "headache" in conditions
    
    vitals = {v["name"]: v for v in extracted["observations"]}
    assert "temperature" in vitals
    assert vitals["temperature"]["value"] == "101"
    assert vitals["temperature"]["unit"].lower() == "fahrenheit"
    
    assert "blood pressure" in vitals
    assert vitals["blood pressure"]["value"] == "130/85"
    
    meds = [m["name"].lower() for m in extracted["medications"]]
    assert "metformin" in meds
    
    cp = [c["activity"].lower() for c in extracted["carePlan"]]
    assert "advise blood test" in cp

def test_fhir_bundle_generation():
    # Test the bundler outputs valid relational JSON
    form_data = {
        "demographics": {"name": "Test Patient", "age": 30, "gender": "female"},
        "encounter": {"class": "ambulatory", "reason": "Routine checkup"},
        "conditions": [{"name": "Asthma", "code": "195967001", "system": "http://snomed.info/sct"}],
        "observations": [{"name": "Heart Rate", "value": "80", "unit": "bpm"}],
        "allergies": [],
        "medications": [{"name": "Albuterol", "dose": "100 mcg", "frequency": "as needed"}],
        "carePlan": []
    }
    
    bundle = build_fhir_bundle(form_data)
    
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    
    entries = bundle["entry"]
    assert len(entries) == 5  # Patient, Encounter, Condition, Observation, MedicationRequest
    
    # Extract Patient ID
    patient_entry = next(e for e in entries if e["resource"]["resourceType"] == "Patient")
    patient_url = patient_entry["fullUrl"]
    
    # Verify Condition references patient correctly
    condition_entry = next(e for e in entries if e["resource"]["resourceType"] == "Condition")
    assert condition_entry["resource"]["subject"]["reference"] == patient_url
    assert condition_entry["resource"]["code"]["coding"][0]["code"] == "195967001"


def test_transcription_service_returns_dict():
    """Test that transcription service returns the new dict format."""
    from backend.app.services.transcription import transcribe_audio
    
    # Without API key, should return demo transcript as a dict
    result = transcribe_audio(b"fake audio data", "test.wav")
    
    assert isinstance(result, dict)
    assert "transcript" in result
    assert "original_transcript" in result
    assert "language" in result
    assert result["language"] in ("en", "hi")
    assert len(result["transcript"]) > 0


def test_fhir_gt_filesystem_save():
    """Test that FHIR bundles are saved to the FHIR_gt directory."""
    import json
    import shutil
    from pathlib import Path
    from backend.app.routes.fhir import _save_fhir_to_filesystem, FHIR_GT_DIR

    test_bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [],
    }

    # Save the bundle
    saved_path = _save_fhir_to_filesystem(test_bundle, "TEST-MRN-001", "Test Patient")

    try:
        # Verify file exists
        assert Path(saved_path).exists()

        # Verify it's under the correct directory
        assert "FHIR_gt" in saved_path
        assert "TEST-MRN-001" in saved_path

        # Verify JSON content
        with open(saved_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["resourceType"] == "Bundle"
        assert loaded["type"] == "transaction"
    finally:
        # Cleanup: remove the test directory
        test_dir = FHIR_GT_DIR / "TEST-MRN-001"
        if test_dir.exists():
            shutil.rmtree(test_dir)
