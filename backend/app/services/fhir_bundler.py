"""
FHIR Transaction Bundle Builder
=================================
Accepts the clinical summary form state and assembles a fully compliant
FHIR R4 Transaction Bundle containing 7 interconnected resource types:

    Patient, Encounter, Condition, Observation, AllergyIntolerance,
    MedicationRequest, CarePlan

Every resource that requires a subject or encounter reference is wired to the
generated Patient and Encounter UUIDs so the bundle is relationally consistent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.app.services.terminology_gateway import (
    ENCOUNTER_CLASS_MAP,
    resolve_gender,
    search_condition,
    search_observation,
    search_allergy,
    search_careplan,
    search_medication_rxnorm,
    search_unit,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_entry(resource: dict[str, Any], resource_type: str, full_url: str) -> dict[str, Any]:
    """Wrap a FHIR resource in a Bundle.entry with a POST request."""
    return {
        "fullUrl": full_url,
        "resource": resource,
        "request": {
            "method": "POST",
            "url": resource_type,
        },
    }


# ---------------------------------------------------------------------------
# Individual resource builders
# ---------------------------------------------------------------------------

def _build_patient(data: dict[str, Any], patient_id: str) -> dict[str, Any]:
    """Build a FHIR Patient resource."""
    name_parts = data.get("name", "").split()
    family = name_parts[-1] if name_parts else ""
    given = name_parts[:-1] if len(name_parts) > 1 else name_parts

    patient: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"use": "official", "family": family, "given": given}],
        "gender": resolve_gender(data.get("gender", "")),
    }

    if data.get("patient_id"):
        patient["identifier"] = [{"system": "http://hospital.org/fhir/patient-ids", "value": data["patient_id"]}]

    if data.get("age"):
        try:
            birth_year = datetime.now().year - int(data["age"])
            patient["birthDate"] = f"{birth_year}-01-01"
        except (ValueError, TypeError):
            pass

    if data.get("phone"):
        patient["telecom"] = [{"system": "phone", "value": data["phone"], "use": "mobile"}]

    return patient


def _build_encounter(data: dict[str, Any], encounter_id: str, patient_ref: str) -> dict[str, Any]:
    """Build a FHIR Encounter resource."""
    enc_class_key = data.get("class", "ambulatory").lower().strip()
    enc_coding = ENCOUNTER_CLASS_MAP.get(enc_class_key, ENCOUNTER_CLASS_MAP["ambulatory"])

    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "finished",
        "class": {
            "system": enc_coding["system"],
            "code": enc_coding["code"],
            "display": enc_coding["display"],
        },
        "subject": {"reference": patient_ref},
        "period": {
            "start": _now_iso(),
        },
    }

    reason = data.get("reason", "")
    if reason:
        encounter["reasonCode"] = [{
            "text": reason,
        }]

    return encounter


def _build_condition(item: dict[str, Any], patient_ref: str, encounter_ref: str) -> dict[str, Any]:
    """Build a FHIR Condition resource from a single condition entry."""
    name = item.get("name", "")
    coding_results = search_condition(name)
    coding = coding_results[0] if coding_results else {"code": "UNKNOWN", "system": "http://snomed.info/sct", "display": name}

    # Use pre-resolved codes if present in form data
    if item.get("code") and item.get("system"):
        coding = {"code": item["code"], "system": item["system"], "display": item.get("display", name)}

    return {
        "resourceType": "Condition",
        "id": _uuid(),
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}],
        },
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}],
        },
        "code": {
            "coding": [coding],
            "text": coding.get("display", name),
        },
        "subject": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "recordedDate": _now_iso(),
    }


def _build_observation(item: dict[str, Any], patient_ref: str, encounter_ref: str) -> dict[str, Any]:
    """Build a FHIR Observation resource."""
    name = item.get("name", "")
    value = item.get("value", "")
    unit_text = item.get("unit", "")

    # Resolve LOINC code
    loinc_results = search_observation(name)
    loinc = loinc_results[0] if loinc_results else {"code": "UNKNOWN", "system": "http://loinc.org", "display": name}

    if item.get("code") and item.get("system"):
        loinc = {"code": item["code"], "system": item["system"], "display": item.get("display", name)}

    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "id": _uuid(),
        "status": "final",
        "code": {
            "coding": [loinc],
            "text": loinc.get("display", name),
        },
        "subject": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "effectiveDateTime": _now_iso(),
    }

    # Handle blood pressure specially (systolic/diastolic component)
    if "/" in str(value) and "blood pressure" in name.lower():
        parts = str(value).split("/")
        if len(parts) == 2:
            obs["component"] = [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]},
                    "valueQuantity": {"value": float(parts[0].strip()), "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}]},
                    "valueQuantity": {"value": float(parts[1].strip()), "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                },
            ]
            return obs

    # Regular numeric value
    try:
        numeric_val = float(value)
        quantity: dict[str, Any] = {"value": numeric_val}

        if unit_text:
            ucum = search_unit(unit_text)
            if ucum:
                quantity.update({"unit": ucum["display"], "system": ucum["system"], "code": ucum["code"]})
            else:
                quantity["unit"] = unit_text

        obs["valueQuantity"] = quantity
    except (ValueError, TypeError):
        if value:
            obs["valueString"] = str(value)

    return obs


def _build_allergy(item: dict[str, Any], patient_ref: str, encounter_ref: str) -> dict[str, Any]:
    """Build a FHIR AllergyIntolerance resource."""
    substance = item.get("substance", "")
    reaction_text = item.get("reaction", "")

    allergy_results = search_allergy(substance)
    allergy_coding = allergy_results[0] if allergy_results else {"code": "UNKNOWN", "system": "http://snomed.info/sct", "display": substance}

    if item.get("code") and item.get("system"):
        allergy_coding = {"code": item["code"], "system": item["system"], "display": item.get("display", substance)}

    ai: dict[str, Any] = {
        "resourceType": "AllergyIntolerance",
        "id": _uuid(),
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}],
        },
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "confirmed"}],
        },
        "type": "allergy",
        "category": ["medication"],
        "code": {
            "coding": [allergy_coding],
            "text": allergy_coding.get("display", substance),
        },
        "patient": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "recordedDate": _now_iso(),
    }

    if reaction_text:
        from backend.app.services.terminology_gateway import search_reaction
        reaction_results = search_reaction(reaction_text)
        reaction_coding = reaction_results[0] if reaction_results else None

        reaction_entry: dict[str, Any] = {"description": reaction_text}
        if reaction_coding:
            reaction_entry["manifestation"] = [{
                "coding": [reaction_coding],
                "text": reaction_coding.get("display", reaction_text),
            }]
        else:
            reaction_entry["manifestation"] = [{"text": reaction_text}]

        ai["reaction"] = [reaction_entry]

    return ai


def _build_medication_request(item: dict[str, Any], patient_ref: str, encounter_ref: str) -> dict[str, Any]:
    """Build a FHIR MedicationRequest resource."""
    drug_name = item.get("name", "")
    dose = item.get("dose", "")
    frequency = item.get("frequency", "")

    rxnorm_results = search_medication_rxnorm(drug_name)
    med_coding = rxnorm_results[0] if rxnorm_results else {"code": "UNKNOWN", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": drug_name}

    if item.get("code") and item.get("system"):
        med_coding = {"code": item["code"], "system": item["system"], "display": item.get("display", drug_name)}

    mr: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "id": _uuid(),
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [med_coding],
            "text": med_coding.get("display", drug_name),
        },
        "subject": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "authoredOn": _now_iso(),
    }

    if dose or frequency:
        dosage: dict[str, Any] = {}
        if dose:
            dosage["text"] = dose
            # Try to parse numeric dose
            import re
            m = re.match(r"(\d+\.?\d*)\s*(\w+)", dose)
            if m:
                dose_val = float(m.group(1))
                dose_unit = m.group(2)
                ucum = search_unit(dose_unit)
                quantity: dict[str, Any] = {"value": dose_val}
                if ucum:
                    quantity.update({"unit": ucum["display"], "system": ucum["system"], "code": ucum["code"]})
                else:
                    quantity["unit"] = dose_unit
                dosage["doseAndRate"] = [{"doseQuantity": quantity}]

        if frequency:
            dosage["text"] = f"{dose} {frequency}".strip() if dose else frequency

        mr["dosageInstruction"] = [dosage]

    return mr


def _build_careplan(items: list[dict[str, Any]], patient_ref: str, encounter_ref: str) -> dict[str, Any]:
    """Build a FHIR CarePlan resource from care plan activities."""
    activities = []
    for item in items:
        activity_text = item.get("activity", "")
        cp_results = search_careplan(activity_text)
        cp_coding = cp_results[0] if cp_results else None

        if item.get("code") and item.get("system"):
            cp_coding = {"code": item["code"], "system": item["system"], "display": item.get("display", activity_text)}

        detail: dict[str, Any] = {
            "status": "scheduled",
            "description": activity_text,
        }

        if cp_coding:
            detail["code"] = {
                "coding": [cp_coding],
                "text": cp_coding.get("display", activity_text),
            }

        activities.append({"detail": detail})

    return {
        "resourceType": "CarePlan",
        "id": _uuid(),
        "status": "active",
        "intent": "plan",
        "subject": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "created": _now_iso(),
        "activity": activities,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_fhir_bundle(form_data: dict[str, Any]) -> dict[str, Any]:
    """
    Accept the complete clinical summary form and produce a FHIR R4
    Transaction Bundle with inter-resource references.

    Expected form_data structure::

        {
            "demographics": {"name": "...", "age": 45, "gender": "male", "phone": "..."},
            "encounter":    {"class": "ambulatory", "reason": "..."},
            "conditions":   [{"name": "...", "code": "...", "system": "..."}],
            "observations": [{"name": "...", "value": "...", "unit": "..."}],
            "allergies":    [{"substance": "...", "reaction": "..."}],
            "medications":  [{"name": "...", "dose": "...", "frequency": "..."}],
            "carePlan":     [{"activity": "..."}],
        }
    """
    patient_id = _uuid()
    encounter_id = _uuid()

    patient_url = f"urn:uuid:{patient_id}"
    encounter_url = f"urn:uuid:{encounter_id}"

    entries: list[dict[str, Any]] = []

    # 1. Patient
    patient_resource = _build_patient(form_data.get("demographics", {}), patient_id)
    entries.append(_make_entry(patient_resource, "Patient", patient_url))

    # 2. Encounter
    encounter_resource = _build_encounter(form_data.get("encounter", {}), encounter_id, patient_url)
    entries.append(_make_entry(encounter_resource, "Encounter", encounter_url))

    # 3. Conditions
    for cond in form_data.get("conditions", []):
        resource = _build_condition(cond, patient_url, encounter_url)
        entries.append(_make_entry(resource, "Condition", f"urn:uuid:{resource['id']}"))

    # 4. Observations
    for obs in form_data.get("observations", []):
        resource = _build_observation(obs, patient_url, encounter_url)
        entries.append(_make_entry(resource, "Observation", f"urn:uuid:{resource['id']}"))

    # 5. Allergies
    for allergy in form_data.get("allergies", []):
        resource = _build_allergy(allergy, patient_url, encounter_url)
        entries.append(_make_entry(resource, "AllergyIntolerance", f"urn:uuid:{resource['id']}"))

    # 6. Medication Requests
    for med in form_data.get("medications", []):
        resource = _build_medication_request(med, patient_url, encounter_url)
        entries.append(_make_entry(resource, "MedicationRequest", f"urn:uuid:{resource['id']}"))

    # 7. CarePlan
    careplan_items = form_data.get("carePlan", [])
    if careplan_items:
        resource = _build_careplan(careplan_items, patient_url, encounter_url)
        entries.append(_make_entry(resource, "CarePlan", f"urn:uuid:{resource['id']}"))

    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "timestamp": _now_iso(),
        "entry": entries,
    }
