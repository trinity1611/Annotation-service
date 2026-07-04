"""
Terminology Automation Gateway
===============================
Two-tier resolution strategy:
  1. Local static dictionaries for UCUM units, SNOMED-CT conditions/allergies/
     care-plan activities, LOINC observation codes, and encounter class codes.
  2. Live HTTP lookup against the public NLM RxNorm REST API for medication
     concepts (no API key required).

All local lookups use case-insensitive fuzzy substring matching so that
partial doctor input like "diab" finds "Type 2 diabetes mellitus".
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. UCUM Unit Map (Local)
# ---------------------------------------------------------------------------

UCUM_LOCAL_MAP: dict[str, dict[str, str]] = {
    "celsius": {"code": "Cel", "system": "http://unitsofmeasure.org", "display": "°C"},
    "fahrenheit": {"code": "[degF]", "system": "http://unitsofmeasure.org", "display": "°F"},
    "days": {"code": "d", "system": "http://unitsofmeasure.org", "display": "days"},
    "hours": {"code": "h", "system": "http://unitsofmeasure.org", "display": "hours"},
    "minutes": {"code": "min", "system": "http://unitsofmeasure.org", "display": "minutes"},
    "seconds": {"code": "s", "system": "http://unitsofmeasure.org", "display": "seconds"},
    "weeks": {"code": "wk", "system": "http://unitsofmeasure.org", "display": "weeks"},
    "months": {"code": "mo", "system": "http://unitsofmeasure.org", "display": "months"},
    "years": {"code": "a", "system": "http://unitsofmeasure.org", "display": "years"},
    "mg": {"code": "mg", "system": "http://unitsofmeasure.org", "display": "mg"},
    "mg/dl": {"code": "mg/dL", "system": "http://unitsofmeasure.org", "display": "mg/dL"},
    "g": {"code": "g", "system": "http://unitsofmeasure.org", "display": "g"},
    "g/dl": {"code": "g/dL", "system": "http://unitsofmeasure.org", "display": "g/dL"},
    "kg": {"code": "kg", "system": "http://unitsofmeasure.org", "display": "kg"},
    "ml": {"code": "mL", "system": "http://unitsofmeasure.org", "display": "mL"},
    "l": {"code": "L", "system": "http://unitsofmeasure.org", "display": "L"},
    "per mg": {"code": "/mg", "system": "http://unitsofmeasure.org", "display": "/mg"},
    "mmhg": {"code": "mm[Hg]", "system": "http://unitsofmeasure.org", "display": "mmHg"},
    "mmol/l": {"code": "mmol/L", "system": "http://unitsofmeasure.org", "display": "mmol/L"},
    "bpm": {"code": "/min", "system": "http://unitsofmeasure.org", "display": "beats/min"},
    "beats/min": {"code": "/min", "system": "http://unitsofmeasure.org", "display": "beats/min"},
    "breaths/min": {"code": "/min", "system": "http://unitsofmeasure.org", "display": "breaths/min"},
    "%": {"code": "%", "system": "http://unitsofmeasure.org", "display": "%"},
    "percent": {"code": "%", "system": "http://unitsofmeasure.org", "display": "%"},
    "cm": {"code": "cm", "system": "http://unitsofmeasure.org", "display": "cm"},
    "m": {"code": "m", "system": "http://unitsofmeasure.org", "display": "m"},
    "in": {"code": "[in_i]", "system": "http://unitsofmeasure.org", "display": "in"},
    "lbs": {"code": "[lb_av]", "system": "http://unitsofmeasure.org", "display": "lbs"},
    "iu/l": {"code": "[iU]/L", "system": "http://unitsofmeasure.org", "display": "IU/L"},
    "u/l": {"code": "U/L", "system": "http://unitsofmeasure.org", "display": "U/L"},
    "cells/ul": {"code": "10*3/uL", "system": "http://unitsofmeasure.org", "display": "cells/µL"},
    "meq/l": {"code": "meq/L", "system": "http://unitsofmeasure.org", "display": "mEq/L"},
}

# ---------------------------------------------------------------------------
# 2. SNOMED-CT Condition Map (Local)
# ---------------------------------------------------------------------------

SNOMED_CONDITION_MAP: dict[str, dict[str, str]] = {
    "type 2 diabetes mellitus": {"code": "44054006", "system": "http://snomed.info/sct", "display": "Type 2 diabetes mellitus"},
    "type 1 diabetes mellitus": {"code": "46635009", "system": "http://snomed.info/sct", "display": "Type 1 diabetes mellitus"},
    "diabetes": {"code": "73211009", "system": "http://snomed.info/sct", "display": "Diabetes mellitus"},
    "hypertension": {"code": "38341003", "system": "http://snomed.info/sct", "display": "Hypertensive disorder"},
    "essential hypertension": {"code": "59621000", "system": "http://snomed.info/sct", "display": "Essential hypertension"},
    "fever": {"code": "386661006", "system": "http://snomed.info/sct", "display": "Fever"},
    "cough": {"code": "49727002", "system": "http://snomed.info/sct", "display": "Cough"},
    "headache": {"code": "25064002", "system": "http://snomed.info/sct", "display": "Headache"},
    "migraine": {"code": "37796009", "system": "http://snomed.info/sct", "display": "Migraine"},
    "asthma": {"code": "195967001", "system": "http://snomed.info/sct", "display": "Asthma"},
    "pneumonia": {"code": "233604007", "system": "http://snomed.info/sct", "display": "Pneumonia"},
    "bronchitis": {"code": "32398004", "system": "http://snomed.info/sct", "display": "Bronchitis"},
    "chest pain": {"code": "29857009", "system": "http://snomed.info/sct", "display": "Chest pain"},
    "abdominal pain": {"code": "21522001", "system": "http://snomed.info/sct", "display": "Abdominal pain"},
    "back pain": {"code": "161891005", "system": "http://snomed.info/sct", "display": "Back pain"},
    "nausea": {"code": "422587007", "system": "http://snomed.info/sct", "display": "Nausea"},
    "vomiting": {"code": "422400008", "system": "http://snomed.info/sct", "display": "Vomiting"},
    "diarrhea": {"code": "62315008", "system": "http://snomed.info/sct", "display": "Diarrhea"},
    "constipation": {"code": "14760008", "system": "http://snomed.info/sct", "display": "Constipation"},
    "anemia": {"code": "271737000", "system": "http://snomed.info/sct", "display": "Anemia"},
    "anxiety": {"code": "48694002", "system": "http://snomed.info/sct", "display": "Anxiety"},
    "depression": {"code": "35489007", "system": "http://snomed.info/sct", "display": "Depressive disorder"},
    "obesity": {"code": "414916001", "system": "http://snomed.info/sct", "display": "Obesity"},
    "hypothyroidism": {"code": "40930008", "system": "http://snomed.info/sct", "display": "Hypothyroidism"},
    "hyperthyroidism": {"code": "34486009", "system": "http://snomed.info/sct", "display": "Hyperthyroidism"},
    "urinary tract infection": {"code": "68566005", "system": "http://snomed.info/sct", "display": "Urinary tract infection"},
    "uti": {"code": "68566005", "system": "http://snomed.info/sct", "display": "Urinary tract infection"},
    "covid-19": {"code": "840539006", "system": "http://snomed.info/sct", "display": "COVID-19"},
    "tuberculosis": {"code": "56717001", "system": "http://snomed.info/sct", "display": "Tuberculosis"},
    "malaria": {"code": "61462000", "system": "http://snomed.info/sct", "display": "Malaria"},
    "dengue": {"code": "38362002", "system": "http://snomed.info/sct", "display": "Dengue fever"},
    "typhoid": {"code": "4834000", "system": "http://snomed.info/sct", "display": "Typhoid fever"},
    "jaundice": {"code": "18165001", "system": "http://snomed.info/sct", "display": "Jaundice"},
    "hepatitis": {"code": "128241005", "system": "http://snomed.info/sct", "display": "Hepatitis"},
    "kidney disease": {"code": "90708001", "system": "http://snomed.info/sct", "display": "Kidney disease"},
    "chronic kidney disease": {"code": "709044004", "system": "http://snomed.info/sct", "display": "Chronic kidney disease"},
    "heart failure": {"code": "84114007", "system": "http://snomed.info/sct", "display": "Heart failure"},
    "myocardial infarction": {"code": "22298006", "system": "http://snomed.info/sct", "display": "Myocardial infarction"},
    "stroke": {"code": "230690007", "system": "http://snomed.info/sct", "display": "Cerebrovascular accident"},
    "epilepsy": {"code": "84757009", "system": "http://snomed.info/sct", "display": "Epilepsy"},
    "arthritis": {"code": "3723001", "system": "http://snomed.info/sct", "display": "Arthritis"},
    "osteoporosis": {"code": "64859006", "system": "http://snomed.info/sct", "display": "Osteoporosis"},
    "fracture": {"code": "125605004", "system": "http://snomed.info/sct", "display": "Fracture of bone"},
    "skin rash": {"code": "271807003", "system": "http://snomed.info/sct", "display": "Skin rash"},
    "eczema": {"code": "43116000", "system": "http://snomed.info/sct", "display": "Eczema"},
    "psoriasis": {"code": "9014002", "system": "http://snomed.info/sct", "display": "Psoriasis"},
    "conjunctivitis": {"code": "9826008", "system": "http://snomed.info/sct", "display": "Conjunctivitis"},
    "sinusitis": {"code": "36971009", "system": "http://snomed.info/sct", "display": "Sinusitis"},
    "tonsillitis": {"code": "90176007", "system": "http://snomed.info/sct", "display": "Tonsillitis"},
    "gastritis": {"code": "4556007", "system": "http://snomed.info/sct", "display": "Gastritis"},
    "appendicitis": {"code": "74400008", "system": "http://snomed.info/sct", "display": "Appendicitis"},
    "chickenpox": {"code": "38907003", "system": "http://snomed.info/sct", "display": "Chickenpox"},
    "measles": {"code": "14189004", "system": "http://snomed.info/sct", "display": "Measles"},
    "shortness of breath": {"code": "267036007", "system": "http://snomed.info/sct", "display": "Dyspnea"},
    "dyspnea": {"code": "267036007", "system": "http://snomed.info/sct", "display": "Dyspnea"},
    "fatigue": {"code": "84229001", "system": "http://snomed.info/sct", "display": "Fatigue"},
    "dizziness": {"code": "404640003", "system": "http://snomed.info/sct", "display": "Dizziness"},
    "swelling": {"code": "65124004", "system": "http://snomed.info/sct", "display": "Swelling"},
    "edema": {"code": "267038008", "system": "http://snomed.info/sct", "display": "Edema"},
    "weight loss": {"code": "89362005", "system": "http://snomed.info/sct", "display": "Weight loss"},
    "weight gain": {"code": "8943002", "system": "http://snomed.info/sct", "display": "Weight gain"},
    "insomnia": {"code": "193462001", "system": "http://snomed.info/sct", "display": "Insomnia"},
    "sore throat": {"code": "162397003", "system": "http://snomed.info/sct", "display": "Sore throat"},
}

# ---------------------------------------------------------------------------
# 3. SNOMED-CT Allergy Substance / Manifestation Map (Local)
# ---------------------------------------------------------------------------

SNOMED_ALLERGY_MAP: dict[str, dict[str, str]] = {
    "penicillin": {"code": "91936005", "system": "http://snomed.info/sct", "display": "Allergy to penicillin"},
    "sulfa": {"code": "294505002", "system": "http://snomed.info/sct", "display": "Allergy to sulfonamide"},
    "sulfonamide": {"code": "294505002", "system": "http://snomed.info/sct", "display": "Allergy to sulfonamide"},
    "aspirin": {"code": "293586001", "system": "http://snomed.info/sct", "display": "Allergy to aspirin"},
    "peanut": {"code": "91935009", "system": "http://snomed.info/sct", "display": "Allergy to peanut"},
    "peanuts": {"code": "91935009", "system": "http://snomed.info/sct", "display": "Allergy to peanut"},
    "shellfish": {"code": "417532002", "system": "http://snomed.info/sct", "display": "Allergy to shellfish"},
    "latex": {"code": "300916003", "system": "http://snomed.info/sct", "display": "Allergy to latex"},
    "ibuprofen": {"code": "293862004", "system": "http://snomed.info/sct", "display": "Allergy to ibuprofen"},
    "dust": {"code": "232350006", "system": "http://snomed.info/sct", "display": "Allergy to house dust mite"},
    "pollen": {"code": "418689008", "system": "http://snomed.info/sct", "display": "Allergy to grass pollen"},
    "egg": {"code": "91930004", "system": "http://snomed.info/sct", "display": "Allergy to egg"},
    "milk": {"code": "782555009", "system": "http://snomed.info/sct", "display": "Allergy to cow milk protein"},
    "soy": {"code": "714035009", "system": "http://snomed.info/sct", "display": "Allergy to soy protein"},
    "wheat": {"code": "420174000", "system": "http://snomed.info/sct", "display": "Allergy to wheat"},
    "codeine": {"code": "293660002", "system": "http://snomed.info/sct", "display": "Allergy to codeine"},
    "morphine": {"code": "293780006", "system": "http://snomed.info/sct", "display": "Allergy to morphine"},
    "nsaid": {"code": "293862004", "system": "http://snomed.info/sct", "display": "Allergy to NSAID"},
    "amoxicillin": {"code": "294505002", "system": "http://snomed.info/sct", "display": "Allergy to amoxicillin"},
    "bee sting": {"code": "424213003", "system": "http://snomed.info/sct", "display": "Allergy to bee venom"},
    "contrast dye": {"code": "293637006", "system": "http://snomed.info/sct", "display": "Allergy to contrast media"},
    "no known allergies": {"code": "716186003", "system": "http://snomed.info/sct", "display": "No known allergy"},
}

# Allergy reaction / manifestation codes
SNOMED_REACTION_MAP: dict[str, dict[str, str]] = {
    "rash": {"code": "271807003", "system": "http://snomed.info/sct", "display": "Skin rash"},
    "hives": {"code": "126485001", "system": "http://snomed.info/sct", "display": "Urticaria"},
    "urticaria": {"code": "126485001", "system": "http://snomed.info/sct", "display": "Urticaria"},
    "anaphylaxis": {"code": "39579001", "system": "http://snomed.info/sct", "display": "Anaphylaxis"},
    "swelling": {"code": "65124004", "system": "http://snomed.info/sct", "display": "Swelling"},
    "itching": {"code": "418290006", "system": "http://snomed.info/sct", "display": "Itching"},
    "nausea": {"code": "422587007", "system": "http://snomed.info/sct", "display": "Nausea"},
    "vomiting": {"code": "422400008", "system": "http://snomed.info/sct", "display": "Vomiting"},
    "breathing difficulty": {"code": "267036007", "system": "http://snomed.info/sct", "display": "Dyspnea"},
}

# ---------------------------------------------------------------------------
# 4. LOINC Observation / Vitals Map (Local)
# ---------------------------------------------------------------------------

LOINC_OBSERVATION_MAP: dict[str, dict[str, str]] = {
    "blood pressure": {"code": "85354-9", "system": "http://loinc.org", "display": "Blood pressure panel"},
    "systolic blood pressure": {"code": "8480-6", "system": "http://loinc.org", "display": "Systolic blood pressure"},
    "diastolic blood pressure": {"code": "8462-4", "system": "http://loinc.org", "display": "Diastolic blood pressure"},
    "heart rate": {"code": "8867-4", "system": "http://loinc.org", "display": "Heart rate"},
    "pulse": {"code": "8867-4", "system": "http://loinc.org", "display": "Heart rate"},
    "respiratory rate": {"code": "9279-1", "system": "http://loinc.org", "display": "Respiratory rate"},
    "body temperature": {"code": "8310-5", "system": "http://loinc.org", "display": "Body temperature"},
    "temperature": {"code": "8310-5", "system": "http://loinc.org", "display": "Body temperature"},
    "oxygen saturation": {"code": "2708-6", "system": "http://loinc.org", "display": "Oxygen saturation"},
    "spo2": {"code": "59408-5", "system": "http://loinc.org", "display": "Oxygen saturation in arterial blood by pulse oximetry"},
    "body weight": {"code": "29463-7", "system": "http://loinc.org", "display": "Body weight"},
    "weight": {"code": "29463-7", "system": "http://loinc.org", "display": "Body weight"},
    "body height": {"code": "8302-2", "system": "http://loinc.org", "display": "Body height"},
    "height": {"code": "8302-2", "system": "http://loinc.org", "display": "Body height"},
    "bmi": {"code": "39156-5", "system": "http://loinc.org", "display": "Body mass index"},
    "body mass index": {"code": "39156-5", "system": "http://loinc.org", "display": "Body mass index"},
    "blood glucose": {"code": "2339-0", "system": "http://loinc.org", "display": "Glucose [Mass/volume] in blood"},
    "fasting blood sugar": {"code": "1558-6", "system": "http://loinc.org", "display": "Fasting glucose [Mass/volume] in serum/plasma"},
    "fbs": {"code": "1558-6", "system": "http://loinc.org", "display": "Fasting glucose [Mass/volume] in serum/plasma"},
    "hba1c": {"code": "4548-4", "system": "http://loinc.org", "display": "Hemoglobin A1c/Hemoglobin.total in blood"},
    "hemoglobin": {"code": "718-7", "system": "http://loinc.org", "display": "Hemoglobin [Mass/volume] in blood"},
    "hb": {"code": "718-7", "system": "http://loinc.org", "display": "Hemoglobin [Mass/volume] in blood"},
    "wbc": {"code": "6690-2", "system": "http://loinc.org", "display": "Leukocytes [#/volume] in blood"},
    "white blood cell count": {"code": "6690-2", "system": "http://loinc.org", "display": "Leukocytes [#/volume] in blood"},
    "rbc": {"code": "789-8", "system": "http://loinc.org", "display": "Erythrocytes [#/volume] in blood"},
    "red blood cell count": {"code": "789-8", "system": "http://loinc.org", "display": "Erythrocytes [#/volume] in blood"},
    "platelet count": {"code": "777-3", "system": "http://loinc.org", "display": "Platelets [#/volume] in blood"},
    "creatinine": {"code": "2160-0", "system": "http://loinc.org", "display": "Creatinine [Mass/volume] in serum/plasma"},
    "serum creatinine": {"code": "2160-0", "system": "http://loinc.org", "display": "Creatinine [Mass/volume] in serum/plasma"},
    "bun": {"code": "3094-0", "system": "http://loinc.org", "display": "Urea nitrogen [Mass/volume] in serum/plasma"},
    "blood urea nitrogen": {"code": "3094-0", "system": "http://loinc.org", "display": "Urea nitrogen [Mass/volume] in serum/plasma"},
    "alt": {"code": "1742-6", "system": "http://loinc.org", "display": "Alanine aminotransferase [Enzymatic activity/volume] in serum/plasma"},
    "sgpt": {"code": "1742-6", "system": "http://loinc.org", "display": "Alanine aminotransferase [Enzymatic activity/volume] in serum/plasma"},
    "ast": {"code": "1920-8", "system": "http://loinc.org", "display": "Aspartate aminotransferase [Enzymatic activity/volume] in serum/plasma"},
    "sgot": {"code": "1920-8", "system": "http://loinc.org", "display": "Aspartate aminotransferase [Enzymatic activity/volume] in serum/plasma"},
    "total cholesterol": {"code": "2093-3", "system": "http://loinc.org", "display": "Cholesterol [Mass/volume] in serum/plasma"},
    "cholesterol": {"code": "2093-3", "system": "http://loinc.org", "display": "Cholesterol [Mass/volume] in serum/plasma"},
    "ldl": {"code": "2089-1", "system": "http://loinc.org", "display": "LDL Cholesterol"},
    "hdl": {"code": "2085-9", "system": "http://loinc.org", "display": "HDL Cholesterol"},
    "triglycerides": {"code": "2571-8", "system": "http://loinc.org", "display": "Triglycerides [Mass/volume] in serum/plasma"},
    "tsh": {"code": "3016-3", "system": "http://loinc.org", "display": "Thyrotropin [Units/volume] in serum/plasma"},
    "t3": {"code": "3053-6", "system": "http://loinc.org", "display": "Triiodothyronine (T3) [Mass/volume] in serum/plasma"},
    "t4": {"code": "3026-2", "system": "http://loinc.org", "display": "Thyroxine (T4) [Mass/volume] in serum/plasma"},
    "sodium": {"code": "2951-2", "system": "http://loinc.org", "display": "Sodium [Moles/volume] in serum/plasma"},
    "potassium": {"code": "2823-3", "system": "http://loinc.org", "display": "Potassium [Moles/volume] in serum/plasma"},
    "calcium": {"code": "17861-6", "system": "http://loinc.org", "display": "Calcium [Mass/volume] in serum/plasma"},
    "uric acid": {"code": "3084-1", "system": "http://loinc.org", "display": "Uric acid [Mass/volume] in serum/plasma"},
    "esr": {"code": "4537-7", "system": "http://loinc.org", "display": "Erythrocyte sedimentation rate"},
    "crp": {"code": "1988-5", "system": "http://loinc.org", "display": "C reactive protein [Mass/volume] in serum/plasma"},
    "covid test": {"code": "94500-6", "system": "http://loinc.org", "display": "SARS-CoV-2 RNA NAA+probe Ql (Resp)"},
    "urinalysis": {"code": "24356-8", "system": "http://loinc.org", "display": "Urinalysis complete panel"},
    "cbc": {"code": "58410-2", "system": "http://loinc.org", "display": "CBC panel"},
    "complete blood count": {"code": "58410-2", "system": "http://loinc.org", "display": "CBC panel"},
    "lipid panel": {"code": "57698-3", "system": "http://loinc.org", "display": "Lipid panel"},
    "liver function test": {"code": "24325-3", "system": "http://loinc.org", "display": "Hepatic function panel"},
    "lft": {"code": "24325-3", "system": "http://loinc.org", "display": "Hepatic function panel"},
    "kidney function test": {"code": "24362-6", "system": "http://loinc.org", "display": "Renal function panel"},
    "kft": {"code": "24362-6", "system": "http://loinc.org", "display": "Renal function panel"},
    "thyroid panel": {"code": "34529-0", "system": "http://loinc.org", "display": "Thyroid function panel"},
}

# ---------------------------------------------------------------------------
# 5. SNOMED-CT CarePlan Activity Map (Local)
# ---------------------------------------------------------------------------

SNOMED_CAREPLAN_MAP: dict[str, dict[str, str]] = {
    "follow up": {"code": "390906007", "system": "http://snomed.info/sct", "display": "Follow-up encounter"},
    "follow-up": {"code": "390906007", "system": "http://snomed.info/sct", "display": "Follow-up encounter"},
    "referral": {"code": "3457005", "system": "http://snomed.info/sct", "display": "Patient referral"},
    "refer to specialist": {"code": "3457005", "system": "http://snomed.info/sct", "display": "Patient referral"},
    "diet counseling": {"code": "11816003", "system": "http://snomed.info/sct", "display": "Diet education"},
    "exercise": {"code": "229065009", "system": "http://snomed.info/sct", "display": "Exercise therapy"},
    "physiotherapy": {"code": "91251008", "system": "http://snomed.info/sct", "display": "Physical therapy"},
    "blood test": {"code": "396550006", "system": "http://snomed.info/sct", "display": "Blood test"},
    "imaging": {"code": "363679005", "system": "http://snomed.info/sct", "display": "Imaging"},
    "x-ray": {"code": "168537006", "system": "http://snomed.info/sct", "display": "Plain X-ray"},
    "ct scan": {"code": "77477000", "system": "http://snomed.info/sct", "display": "Computerized axial tomography"},
    "mri": {"code": "113091000", "system": "http://snomed.info/sct", "display": "Magnetic resonance imaging"},
    "ultrasound": {"code": "16310003", "system": "http://snomed.info/sct", "display": "Diagnostic ultrasonography"},
    "ecg": {"code": "29303009", "system": "http://snomed.info/sct", "display": "Electrocardiographic procedure"},
    "echocardiogram": {"code": "40701008", "system": "http://snomed.info/sct", "display": "Echocardiography"},
    "admission": {"code": "32485007", "system": "http://snomed.info/sct", "display": "Hospital admission"},
    "surgery": {"code": "387713003", "system": "http://snomed.info/sct", "display": "Surgical procedure"},
    "biopsy": {"code": "86273004", "system": "http://snomed.info/sct", "display": "Biopsy"},
    "vaccination": {"code": "33879002", "system": "http://snomed.info/sct", "display": "Vaccination"},
    "wound care": {"code": "225358003", "system": "http://snomed.info/sct", "display": "Wound care"},
    "smoking cessation": {"code": "710081004", "system": "http://snomed.info/sct", "display": "Smoking cessation therapy"},
    "counseling": {"code": "409063005", "system": "http://snomed.info/sct", "display": "Counseling"},
    "monitoring": {"code": "122869004", "system": "http://snomed.info/sct", "display": "Monitoring procedure"},
    "discharge": {"code": "58000006", "system": "http://snomed.info/sct", "display": "Patient discharge"},
    "home care": {"code": "385763009", "system": "http://snomed.info/sct", "display": "Home health care"},
    "bed rest": {"code": "225408003", "system": "http://snomed.info/sct", "display": "Bed rest"},
    "review medication": {"code": "182836005", "system": "http://snomed.info/sct", "display": "Review of medication"},
}

# ---------------------------------------------------------------------------
# 6. Encounter Class Map (Local – FHIR v3 ActCode)
# ---------------------------------------------------------------------------

ENCOUNTER_CLASS_MAP: dict[str, dict[str, str]] = {
    "ambulatory": {"code": "AMB", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Ambulatory"},
    "outpatient": {"code": "AMB", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Ambulatory"},
    "opd": {"code": "AMB", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Ambulatory"},
    "emergency": {"code": "EMER", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Emergency"},
    "er": {"code": "EMER", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Emergency"},
    "inpatient": {"code": "IMP", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Inpatient encounter"},
    "ipd": {"code": "IMP", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Inpatient encounter"},
    "virtual": {"code": "VR", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Virtual"},
    "teleconsultation": {"code": "VR", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Virtual"},
    "telemedicine": {"code": "VR", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Virtual"},
    "home visit": {"code": "HH", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Home health"},
    "field": {"code": "FLD", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "display": "Field"},
}

# ---------------------------------------------------------------------------
# 7. Administrative Gender Map
# ---------------------------------------------------------------------------

GENDER_MAP: dict[str, str] = {
    "male": "male",
    "m": "male",
    "female": "female",
    "f": "female",
    "other": "other",
    "unknown": "unknown",
}

# ===================================================================
#  PUBLIC GATEWAY FUNCTIONS
# ===================================================================


def _fuzzy_search(query: str, lookup: dict[str, dict[str, str]], limit: int = 10) -> list[dict[str, Any]]:
    """Return all entries whose key contains *query* as a substring."""
    q = query.lower().strip()
    if not q:
        return []
    results = [v for k, v in lookup.items() if q in k]
    return results[:limit]


def search_unit(text: str) -> dict[str, str] | None:
    """Resolve a human-readable unit string to a UCUM code."""
    normalized = text.lower().strip()
    return UCUM_LOCAL_MAP.get(normalized)


def search_condition(text: str) -> list[dict[str, str]]:
    return _fuzzy_search(text, SNOMED_CONDITION_MAP)


def search_observation(text: str) -> list[dict[str, str]]:
    return _fuzzy_search(text, LOINC_OBSERVATION_MAP)


def search_allergy(text: str) -> list[dict[str, str]]:
    return _fuzzy_search(text, SNOMED_ALLERGY_MAP)


def search_reaction(text: str) -> list[dict[str, str]]:
    return _fuzzy_search(text, SNOMED_REACTION_MAP)


def search_careplan(text: str) -> list[dict[str, str]]:
    return _fuzzy_search(text, SNOMED_CAREPLAN_MAP)


def search_encounter_class(text: str) -> list[dict[str, str]]:
    return _fuzzy_search(text, ENCOUNTER_CLASS_MAP)


def resolve_gender(text: str) -> str:
    return GENDER_MAP.get(text.lower().strip(), "unknown")


def search_medication_rxnorm(text: str) -> list[dict[str, str]]:
    """
    Query the public NLM RxNorm REST API for approximate drug-name matches.
    Falls back to a local mini-map if the API is unreachable.
    """
    LOCAL_MEDICATION_MAP: dict[str, dict[str, str]] = {
        "paracetamol": {"code": "161", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen"},
        "acetaminophen": {"code": "161", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Acetaminophen"},
        "ibuprofen": {"code": "5640", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Ibuprofen"},
        "amoxicillin": {"code": "723", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Amoxicillin"},
        "metformin": {"code": "6809", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Metformin"},
        "aspirin": {"code": "1191", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Aspirin"},
        "atorvastatin": {"code": "83367", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Atorvastatin"},
        "amlodipine": {"code": "17767", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Amlodipine"},
        "losartan": {"code": "52175", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Losartan"},
        "omeprazole": {"code": "7646", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Omeprazole"},
        "pantoprazole": {"code": "40790", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Pantoprazole"},
        "ciprofloxacin": {"code": "2551", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Ciprofloxacin"},
        "azithromycin": {"code": "18631", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Azithromycin"},
        "cetirizine": {"code": "20610", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Cetirizine"},
        "montelukast": {"code": "88249", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Montelukast"},
        "salbutamol": {"code": "435", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Albuterol"},
        "albuterol": {"code": "435", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Albuterol"},
        "prednisolone": {"code": "8638", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Prednisolone"},
        "prednisone": {"code": "8640", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Prednisone"},
        "insulin": {"code": "5856", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Insulin"},
        "clopidogrel": {"code": "32968", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Clopidogrel"},
        "warfarin": {"code": "11289", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Warfarin"},
        "diclofenac": {"code": "3355", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Diclofenac"},
        "ranitidine": {"code": "9143", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Ranitidine"},
        "doxycycline": {"code": "3640", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Doxycycline"},
        "levothyroxine": {"code": "10582", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Levothyroxine"},
        "lisinopril": {"code": "29046", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Lisinopril"},
        "hydrochlorothiazide": {"code": "5487", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Hydrochlorothiazide"},
        "furosemide": {"code": "4603", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Furosemide"},
        "gabapentin": {"code": "25480", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": "Gabapentin"},
    }

    q = text.lower().strip()
    if not q:
        return []

    # Check local map first for instant results
    local_hits = [v for k, v in LOCAL_MEDICATION_MAP.items() if q in k]
    if local_hits:
        return local_hits[:10]

    # Try the public RxNorm API
    try:
        url = f"{settings.rxnorm_api_base}/approximateTerm.json"
        resp = requests.get(url, params={"term": text, "maxEntries": 10}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("approximateGroup", {}).get("candidate", [])
            results = []
            for c in candidates[:10]:
                rxcui = c.get("rxcui", "")
                name = c.get("name", text)
                results.append({
                    "code": rxcui,
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "display": name,
                })
            if results:
                return results
    except Exception as exc:
        logger.warning("RxNorm API call failed: %s — falling back to local map", exc)

    return [{"code": "UNKNOWN", "system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": text}]


def search_terminology(text: str, resource_type: str) -> list[dict[str, str]]:
    """
    Unified dispatcher: given free text and a FHIR resource_type,
    route to the correct terminology search function.
    """
    dispatch = {
        "Condition": search_condition,
        "Observation": search_observation,
        "AllergyIntolerance": search_allergy,
        "MedicationRequest": search_medication_rxnorm,
        "CarePlan": search_careplan,
        "Encounter": search_encounter_class,
    }
    fn = dispatch.get(resource_type)
    if fn:
        return fn(text)
    return [{"code": "UNKNOWN", "system": "UNKNOWN", "display": text}]
