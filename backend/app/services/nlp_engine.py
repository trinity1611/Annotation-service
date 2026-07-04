"""
Clinical NLP Extraction Engine
===============================
Lightweight, rule-based clinical entity extractor.  Parses free-text English
clinical notes and maps keywords to the 7 FHIR-aligned form sections:

    1. Patient demographics
    2. Encounter context
    3. Conditions / diagnoses
    4. Observations (vitals & labs)
    5. Allergies & reactions
    6. Medications (prescriptions)
    7. Care plan activities

Uses regex patterns rather than heavy ML models so the service stays fast
and dependency-free.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Internal pattern helpers
# ---------------------------------------------------------------------------

def _find_all(pattern: str, text: str, flags: int = re.IGNORECASE) -> list[str]:
    """Return all unique matches for the pattern in *text*."""
    return list(dict.fromkeys(re.findall(pattern, text, flags)))


def _find_first(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Section extractors
# ---------------------------------------------------------------------------

def _extract_demographics(text: str) -> dict[str, Any]:
    """Extract patient name, age, gender from clinical notes."""
    name = _find_first(
        r"(?:patient(?:\s+is)?|patient\s+named?|named?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
        text,
    )
    if not name:
        name = _find_first(r"(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text)

    age_match = _find_first(r"(\d{1,3})\s*[-–]?\s*year[s]?\s*[-–]?\s*old", text)
    age = int(age_match) if age_match else None

    gender = None
    if re.search(r"\b(?:male|man|boy)\b", text, re.IGNORECASE):
        gender = "male"
    elif re.search(r"\b(?:female|woman|girl)\b", text, re.IGNORECASE):
        gender = "female"

    phone = _find_first(r"(?:phone|mobile|contact)[:\s]*(\+?\d[\d\s\-]{8,14})", text)

    return {
        "name": name or "",
        "age": age,
        "gender": gender or "",
        "phone": phone or "",
    }


def _extract_encounter(text: str) -> dict[str, Any]:
    """Determine the encounter class from keywords."""
    text_lower = text.lower()
    encounter_class = "ambulatory"  # default
    if any(k in text_lower for k in ["emergency", "er ", "casualty", "accident"]):
        encounter_class = "emergency"
    elif any(k in text_lower for k in ["inpatient", "ipd", "admit", "icu", "ward"]):
        encounter_class = "inpatient"
    elif any(k in text_lower for k in ["virtual", "teleconsult", "telemedicine", "video"]):
        encounter_class = "virtual"
    elif any(k in text_lower for k in ["home visit", "domiciliary"]):
        encounter_class = "home visit"

    reason = _find_first(
        r"(?:chief\s+complaint|presenting\s+with|complain(?:t|s)\s+of)[:\s]*(.+?)(?:\.|$)",
        text,
    )

    return {
        "class": encounter_class,
        "reason": reason or "",
    }


def _extract_conditions(text: str) -> list[dict[str, str]]:
    """Find diagnosis and symptom terms."""
    CONDITION_PATTERNS = [
        r"(?:diagnosis|diagnosed|assessment|impression)[:\s]*(.+?)(?:\.|;|$)",
        r"(?:history\s+of|known\s+case\s+of|h/o)\s+(.+?)(?:\.|,|;|$)",
    ]
    raw: list[str] = []
    for pat in CONDITION_PATTERNS:
        raw.extend(_find_all(pat, text))

    # Also look for well-known keywords directly
    KNOWN_CONDITIONS = [
        "diabetes", "hypertension", "asthma", "pneumonia", "fever", "cough",
        "headache", "migraine", "bronchitis", "tuberculosis", "malaria",
        "dengue", "typhoid", "covid", "arthritis", "epilepsy", "obesity",
        "anemia", "depression", "anxiety", "hypothyroidism", "hyperthyroidism",
        "heart failure", "myocardial infarction", "stroke", "kidney disease",
        "chest pain", "abdominal pain", "back pain", "nausea", "vomiting",
        "diarrhea", "constipation", "shortness of breath", "dyspnea",
        "jaundice", "hepatitis", "sinusitis", "tonsillitis", "conjunctivitis",
        "eczema", "psoriasis", "urinary tract infection", "uti",
        "skin rash", "sore throat", "fatigue", "dizziness", "insomnia",
        "edema", "swelling", "weight loss", "weight gain", "fracture",
    ]
    text_lower = text.lower()
    for cond in KNOWN_CONDITIONS:
        if cond in text_lower and cond not in [r.lower() for r in raw]:
            raw.append(cond.title())

    return [{"name": c.strip()} for c in raw if c.strip()]


def _extract_observations(text: str) -> list[dict[str, Any]]:
    """Extract vitals and lab results with values and units."""
    results: list[dict[str, Any]] = []

    # Vitals patterns
    VITAL_PATTERNS = [
        (r"(?:temperature|temp)[:\s]*(\d+\.?\d*)\s*(fahrenheit|celsius|°?[FC]|degrees?\s*(?:fahrenheit|celsius))", "temperature"),
        (r"(?:blood\s+pressure|bp)[:\s]*(\d{2,3}\s*/\s*\d{2,3})\s*(mmhg|mm\s*hg)?", "blood pressure"),
        (r"(?:heart\s+rate|pulse|hr)[:\s]*(\d{2,3})\s*(bpm|beats?\s*(?:per|/)\s*min(?:ute)?)?", "heart rate"),
        (r"(?:respiratory\s+rate|rr)[:\s]*(\d{1,2})\s*(breaths?\s*(?:per|/)\s*min(?:ute)?)?", "respiratory rate"),
        (r"(?:oxygen\s+saturation|spo2|sp\s*o\s*2|o2\s+sat)[:\s]*(\d{2,3})\s*(%|percent)?", "oxygen saturation"),
        (r"(?:body\s+)?weight[:\s]*(\d+\.?\d*)\s*(kg|lbs?|pounds?)?", "weight"),
        (r"(?:body\s+)?height[:\s]*(\d+\.?\d*)\s*(cm|m|ft|feet|in(?:ches)?)?", "height"),
        (r"(?:bmi|body\s+mass\s+index)[:\s]*(\d+\.?\d*)", "bmi"),
    ]
    for pat, obs_name in VITAL_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            entry: dict[str, Any] = {"name": obs_name, "value": m.group(1).strip()}
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                entry["unit"] = m.group(2).strip()
            results.append(entry)

    # Lab result patterns
    LAB_PATTERNS = [
        (r"(?:hemoglobin|hb)[:\s]*(\d+\.?\d*)\s*(g/dl|g/l)?", "hemoglobin"),
        (r"(?:fasting\s+blood\s+sugar|fbs|fasting\s+glucose)[:\s]*(\d+\.?\d*)\s*(mg/dl)?", "fasting blood sugar"),
        (r"(?:blood\s+glucose|glucose)[:\s]*(\d+\.?\d*)\s*(mg/dl|mmol/l)?", "blood glucose"),
        (r"(?:hba1c|hb\s*a1c|glycated\s+hemoglobin)[:\s]*(\d+\.?\d*)\s*(%|percent)?", "hba1c"),
        (r"(?:creatinine|serum\s+creatinine)[:\s]*(\d+\.?\d*)\s*(mg/dl)?", "creatinine"),
        (r"(?:total\s+cholesterol|cholesterol)[:\s]*(\d+\.?\d*)\s*(mg/dl)?", "total cholesterol"),
        (r"(?:ldl)[:\s]*(\d+\.?\d*)\s*(mg/dl)?", "ldl"),
        (r"(?:hdl)[:\s]*(\d+\.?\d*)\s*(mg/dl)?", "hdl"),
        (r"(?:triglycerides?)[:\s]*(\d+\.?\d*)\s*(mg/dl)?", "triglycerides"),
        (r"(?:wbc|white\s+blood\s+cell)[:\s]*(\d+\.?\d*)\s*(cells/ul|/ul)?", "wbc"),
        (r"(?:platelet\s+count|platelets)[:\s]*(\d+\.?\d*)", "platelet count"),
        (r"(?:troponin)[:\s]*(\w+)", "troponin"),
    ]
    for pat, lab_name in LAB_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            entry = {"name": lab_name, "value": m.group(1).strip()}
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                entry["unit"] = m.group(2).strip()
            results.append(entry)

    return results


def _extract_allergies(text: str) -> list[dict[str, Any]]:
    """Extract allergy substances and reactions."""
    results: list[dict[str, Any]] = []
    text_lower = text.lower()

    if "no known" in text_lower and "allerg" in text_lower:
        return [{"substance": "No Known Allergies", "reaction": ""}]

    # Pattern: "allergic to X causing Y" / "allergy to X"
    allergy_matches = re.finditer(
        r"(?:allergic?\s+to|allergy\s+to)\s+([A-Za-z\s]+?)(?:\s+(?:causing|which\s+causes|with)\s+(.+?))?(?:\.|,|;|$)",
        text, re.IGNORECASE,
    )
    for m in allergy_matches:
        substance = m.group(1).strip().rstrip(" and")
        reaction = m.group(2).strip() if m.group(2) else ""
        results.append({"substance": substance, "reaction": reaction})

    return results


def _extract_medications(text: str) -> list[dict[str, Any]]:
    """Extract medication names, doses, and frequencies."""
    results: list[dict[str, Any]] = []

    # Pattern: drug name + dose + frequency
    med_patterns = [
        r"(?:prescribe|start|give|take|taking|on|administer)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(\d+\.?\d*)\s*(mg|g|ml|mcg|IU)\s*(?:,?\s*(.+?))?(?:\.|;|$)",
        r"([A-Z][a-z]+(?:cillin|mycin|pril|sartan|statin|prazole|olol|dipine|formin|amol|phen|sone|lone))\s+(\d+\.?\d*)\s*(mg|g|ml|mcg)\s*(?:,?\s*(.+?))?(?:\.|;|$)",
        r"(?:currently\s+(?:on|taking))\s+([A-Z][a-z]+(?:\s+\w+)?)\s+(\d+\.?\d*)\s*(mg|g|ml|mcg)\s*(?:,?\s*(.+?))?(?:\.|;|$)",
    ]
    seen_drugs: set[str] = set()
    for pat in med_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            drug = m.group(1).strip()
            if drug.lower() in seen_drugs:
                continue
            seen_drugs.add(drug.lower())
            dose = m.group(2).strip()
            unit = m.group(3).strip()
            freq = m.group(4).strip() if m.group(4) else ""
            results.append({
                "name": drug,
                "dose": f"{dose} {unit}",
                "frequency": freq,
            })

    return results


def _extract_careplan(text: str) -> list[dict[str, str]]:
    """Extract care plan / next-step activities."""
    activities: list[str] = []
    text_lower = text.lower()

    # Explicit plan section
    plan_section = _find_first(r"(?:plan|treatment|next\s+steps?)[:\s]*(.+?)(?:encounter|visit\s+type|$)", text)
    if plan_section:
        # Split on periods/semicolons
        parts = re.split(r"[.;]", plan_section)
        activities.extend([p.strip() for p in parts if len(p.strip()) > 3])

    # Known activity keywords
    ACTIVITY_KEYWORDS = [
        "follow up", "follow-up", "referral", "refer", "blood test",
        "x-ray", "ct scan", "mri", "ultrasound", "ecg", "echocardiogram",
        "physiotherapy", "counseling", "diet", "exercise", "admit",
        "discharge", "surgery", "biopsy", "vaccination", "monitoring",
        "smoking cessation", "review medication", "bed rest",
    ]
    for kw in ACTIVITY_KEYWORDS:
        if kw in text_lower and kw.title() not in activities:
            # Try to get surrounding context
            m = re.search(rf"([^.;]*{re.escape(kw)}[^.;]*)", text, re.IGNORECASE)
            if m:
                activities.append(m.group(1).strip())

    return [{"activity": a} for a in dict.fromkeys(activities) if a]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract_clinical_entities(text: str) -> dict[str, Any]:
    """
    Parse free-text clinical notes and return a structured dict suitable for
    pre-filling the 7-section clinical summary form.
    """
    return {
        "demographics": _extract_demographics(text),
        "encounter": _extract_encounter(text),
        "conditions": _extract_conditions(text),
        "observations": _extract_observations(text),
        "allergies": _extract_allergies(text),
        "medications": _extract_medications(text),
        "carePlan": _extract_careplan(text),
    }
