# Technical Architecture Report

## 1. Overview

The FHIR Terminology-Mapping Microservice is a full-stack application that converts unstructured clinical narratives (spoken or typed) into structured, standards-compliant HL7 FHIR R4 Transaction Bundles. The system supports **bilingual audio input** (English and Hindi), uses a **regex-based NLP engine** for entity extraction, and maps extracted concepts to four international medical terminologies: **SNOMED-CT**, **LOINC**, **RxNorm**, and **UCUM**.

### Design Philosophy
- **Zero ML dependency** for NLP: Uses lightweight regex patterns instead of heavy machine learning models, keeping the service fast and dependency-free
- **Local-first terminology**: In-memory dictionaries for sub-millisecond lookups, with HTTP fallback to NLM's RxNorm API only for medications
- **Dual persistence**: Every generated FHIR bundle is saved to both a SQLite database (for querying) and the filesystem as a JSON file (for portability and ground-truth datasets)

---

## 2. System Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Browser)                        │
│   ┌──────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│   │  Audio   │  │  Transcript  │  │  Clinical Summary Form     │ │
│   │ Recorder │  │  Display     │  │  (7 editable sections)     │ │
│   │ + Upload │  │  EN / HI     │  │  with terminology          │ │
│   └────┬─────┘  └──────────────┘  │  autocomplete              │ │
│        │                          └─────────────┬──────────────┘ │
└────────┼────────────────────────────────────────┼────────────────┘
         │ POST /api/audio/transcribe             │ POST /api/fhir/bundle
         ▼                                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI / Python)                    │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ Transcription│  │   NLP Engine │  │  Terminology Gateway    │  │
│  │   Service   │  │  (Regex-based)│  │  (SNOMED/LOINC/UCUM    │  │
│  │ Whisper API │  │              │  │   + RxNorm HTTP API)    │  │
│  │ / Demo Mode │  │              │  │                         │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬──────────────┘  │
│         │                │                      │                 │
│         └────────────────┴──────────────────────┘                 │
│                           │                                       │
│                    ┌──────▼───────┐                                │
│                    │ FHIR Bundler │                                │
│                    │ (R4 Builder) │                                │
│                    └──────┬───────┘                                │
│                           │                                       │
│              ┌────────────┴────────────┐                          │
│              ▼                         ▼                          │
│  ┌──────────────────┐    ┌──────────────────────┐                 │
│  │   SQLite DB      │    │   FHIR_gt/ Folder    │                 │
│  │ (fhir_bundles.db)│    │ <patient_id>/*.json  │                 │
│  └──────────────────┘    └──────────────────────┘                 │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Details

### 3.1 Frontend (Vanilla HTML / CSS / JavaScript)

**Files**: `frontend/index.html`, `frontend/css/styles.css`, `frontend/js/app.js`

- **Stateless SPA**: Single HTML page with no build tools or frameworks (React, Vue, etc.)
- **Glassmorphism Design System**: Modern UI with semi-transparent cards, gradient accents, and smooth animations
- **Audio Recording**: Uses the native browser `MediaRecorder` API to capture audio in `audio/webm` format
- **Audio Upload**: Accepts `.wav`, `.mp3`, `.m4a`, `.webm`, `.ogg`, `.flac`, `.aac` files
- **Language Selector**: Dropdown to choose between Auto-detect, English, or Hindi — passed as a form field to the backend
- **Bilingual Transcript Display**: When Hindi audio is detected, the original Hindi transcript is shown in a separate card above the English translation
- **Terminology Autocomplete**: Real-time AJAX requests to `GET /api/terminology/search` with 300ms debounce — results appear as a dropdown with code + display name
- **FHIR Bundle Modal**: Syntax-highlighted JSON viewer with Copy and Download buttons, resource count summary, and save location indicator

### 3.2 Audio Transcription Service

**File**: `backend/app/services/transcription.py`

**Strategy**: Two-tier approach:

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Sarvam API** | `SARVAM_API_KEY` env var is set | Calls Sarvam AI API in two steps: (1) `transcribe` to get original-language text, (2) `translate` to get English text if source is non-English |
| **Demo Mode** | No API key configured | Cycles through 3 pre-built English demo transcripts and 2 Hindi demo transcripts |

**MIME Type Resolution**: The service maps file extensions to correct MIME types before sending to the API. This is critical because the API rejects files with incorrect content types:

| Extension | MIME Type |
|-----------|-----------|
| `.wav` | `audio/wav` |
| `.mp3` | `audio/mpeg` |
| `.m4a` | `audio/mp4` |
| `.webm` | `audio/webm` |

**Return Contract**:
```json
{
  "transcript": "English text (used for NLP extraction)",
  "original_transcript": "Original language text (Hindi/English)",
  "language": "en | hi"
}
```

### 3.3 Clinical NLP Engine

**File**: `backend/app/services/nlp_engine.py`

A **rule-based, regex-powered** clinical entity extractor. No ML models or external NLP libraries — the service stays fast (<5ms per extraction) and dependency-free.

**Extraction Sections** (mapped to FHIR resource types):

| Section | FHIR Resource | Regex Examples |
|---------|--------------|----------------|
| Demographics | Patient | `"Patient named <Name>"`, `"<N>-year-old <gender>"` |
| Encounter | Encounter | Keywords: `emergency`, `inpatient`, `OPD`, `virtual` |
| Conditions | Condition | `"diagnosis: ..."`, `"known case of ..."`, + 50+ known condition keywords |
| Observations | Observation | `"temperature 101 F"`, `"BP 130/85 mmHg"`, `"hemoglobin 12.5 g/dL"` |
| Allergies | AllergyIntolerance | `"allergic to <substance> causing <reaction>"` |
| Medications | MedicationRequest | `"prescribe <drug> <dose> <unit> <frequency>"` |
| Care Plan | CarePlan | `"plan: ..."`, keywords like `follow up`, `referral`, `X-ray` |

**Known Limitations**:
- Compound diagnoses (e.g., "viral fever with uncontrolled diabetes") map to `UNKNOWN` — the doctor should split or correct these in the form
- Name extraction can grab wrong words from certain sentence structures
- These are expected to be corrected by the clinician before FHIR generation

### 3.4 Terminology Gateway

**File**: `backend/app/services/terminology_gateway.py`

**Two-tier resolution strategy**:

1. **Local In-Memory Dictionaries** (sub-millisecond lookups):
   - **SNOMED-CT**: ~60 conditions, ~20 allergies, ~15 allergy reactions, ~20 care plan activities
   - **LOINC**: ~25 observation/lab codes
   - **UCUM**: ~30 unit mappings
   - **Encounter Classes**: ambulatory, emergency, inpatient, virtual, home visit (v3-ActCode)
   - **Fuzzy matching**: Case-insensitive substring search (typing "diab" finds "Type 2 diabetes mellitus")

2. **Live HTTP API** (NLM RxNorm REST):
   - Used for **medications only** when local dictionary doesn't match
   - Endpoint: `https://rxnav.nlm.nih.gov/REST/drugs.json?name=<drug>`
   - No API key required (public government API)
   - Falls back to local medication dictionary (~20 common drugs) if the API is unreachable

### 3.5 FHIR Transaction Bundle Builder

**File**: `backend/app/services/fhir_bundler.py`

Constructs a fully compliant **FHIR R4 Transaction Bundle** with 7 resource types:

```
Bundle (type: "transaction")
├── Patient           ── identifier, name, gender, birthDate, telecom
├── Encounter         ── class (v3-ActCode), reasonCode, period, subject→Patient
├── Condition[]       ── code (SNOMED), clinicalStatus, subject→Patient, encounter→Encounter
├── Observation[]     ── code (LOINC), valueQuantity (UCUM), subject→Patient, encounter→Encounter
├── AllergyIntolerance[] ── code (SNOMED), reaction.manifestation, patient→Patient
├── MedicationRequest[]  ── medicationCodeableConcept (RxNorm), dosageInstruction, subject→Patient
└── CarePlan          ── activity[].detail.description, subject→Patient, encounter→Encounter
```

**Referential Integrity**: All resources are linked via `urn:uuid:` references. The Patient and Encounter UUIDs are generated first, and every subsequent resource references them through `subject.reference` and `encounter.reference`.

**Bundle Request Method**: Each entry uses `"method": "POST"` so the bundle can be submitted to any FHIR server as a transaction.

### 3.6 FHIR Persistence Layer

**Files**: `backend/app/routes/fhir.py`, `backend/app/database.py`, `backend/app/models.py`

Every generated bundle is persisted in **two locations**:

#### A. SQLite Database (`fhir_bundles.db`)
- **ORM**: SQLAlchemy with `FHIRBundleRecord` model
- **Fields**: `id` (PK), `patient_id`, `patient_name`, `encounter_reason`, `created_at`, `bundle_json`
- **Use Case**: Quick lookup and querying of past bundles

#### B. Filesystem (`FHIR_gt/` directory)
- **Path pattern**: `FHIR_gt/<patient_id>/fhir_bundle_<YYYYMMDD_HHMMSS>.json`
- **Folder naming priority**: Uses `patient_id` (MRN) if provided → falls back to `patient_name` → defaults to `anonymous`
- **Collision handling**: If the same timestamp produces a duplicate filename, a counter suffix is appended (`_1`, `_2`, etc.)
- **Use Case**: Building ground-truth datasets, sharing bundles as portable files, archival

**Same Patient ID reuse**: When the same `patient_id` (e.g., `100`) is used across multiple encounters, all generated bundles accumulate in the same subfolder:

```
FHIR_gt/
└── 100/
    ├── fhir_bundle_20260704_111548.json   ← First encounter
    ├── fhir_bundle_20260704_120030.json   ← Second encounter
    └── fhir_bundle_20260705_090000.json   ← Next day follow-up
```

---

## 4. API Specification

### POST `/api/audio/transcribe`
- **Input**: `multipart/form-data` with `file` (audio) and optional `language` hint (`en`, `hi`)
- **Output**: `{transcript, original_transcript, language, extracted}`
- **Process**: Audio → Whisper transcription → NLP entity extraction → structured response

### POST `/api/audio/transcribe-text`
- **Input**: `{"text": "clinical notes..."}`
- **Output**: Same as above (no audio processing, direct NLP extraction)

### POST `/api/fhir/bundle`
- **Input**: Structured form data (demographics, encounter, conditions, observations, allergies, medications, carePlan)
- **Output**: `{bundle, saved_path, patient_id}`
- **Side Effects**: Saves to SQLite + writes JSON to FHIR_gt/

### GET `/api/fhir/bundles`
- **Output**: List of all patient folders and their bundle files from FHIR_gt/

### GET `/api/terminology/search`
- **Query Params**: `text` (search query), `resource_type` (Condition, Observation, AllergyIntolerance, MedicationRequest, CarePlan, Encounter, Unit)
- **Output**: Array of `{code, system, display}` matches

### GET `/api/terminology/map-unit`
- **Query Params**: `unit_text` (e.g., "celsius", "mg", "mmhg")
- **Output**: `{code, system, display}` or 404

### GET `/api/health`
- **Output**: `{status, service, version}`

---

## 5. Data Flow (End-to-End)

```
Doctor speaks/uploads audio (.wav/.mp3)
        │
        ▼
   [Whisper API / Demo Mode]
        │ Transcribes to text
        │ Auto-detects Hindi → translates to English
        ▼
   [NLP Engine]
        │ Regex extracts: demographics, conditions, vitals, meds, allergies, care plan
        ▼
   [Frontend Form]
        │ Doctor reviews + corrects extracted data
        │ Terminology autocomplete resolves codes (SNOMED, LOINC, RxNorm, UCUM)
        ▼
   [FHIR Bundler]
        │ Builds R4 Transaction Bundle with urn:uuid references
        ▼
   [Persistence]
        ├── SQLite DB (fhir_bundles.db)
        └── JSON file (FHIR_gt/<patient_id>/fhir_bundle_<timestamp>.json)
```

---

## 6. Testing

**Test File**: `backend/tests/test_logic.py`

| Test | What It Verifies |
|------|-----------------|
| `test_unit_mapping` | UCUM local map resolves "celsius" → `Cel`, "mg" → `mg` |
| `test_condition_search` | Fuzzy search "diab" returns SNOMED code `44054006` (Type 2 DM) |
| `test_medication_local_fallback` | "paracetamol" resolves to RxNorm `161` |
| `test_nlp_extraction` | Full regex extraction pipeline: name, age, gender, conditions, vitals, meds, care plan |
| `test_fhir_bundle_generation` | Bundle has correct resource types, referential integrity, SNOMED codes |
| `test_transcription_service_returns_dict` | Demo transcription returns `{transcript, original_transcript, language}` |
| `test_fhir_gt_filesystem_save` | JSON file is created at `FHIR_gt/<patient_id>/` with valid content |

---

## 7. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| FastAPI | ≥0.111 | REST API framework |
| Uvicorn | ≥0.30 | ASGI server |
| Pydantic | ≥2.7 | Data validation & settings |
| pydantic-settings | ≥2.0 | Environment variable management |
| SQLAlchemy | latest | ORM for SQLite |
| Requests | ≥2.32 | HTTP client (RxNorm API, Whisper API) |
| python-multipart | ≥0.0.9 | File upload parsing |
| aiofiles | ≥23.2 | Async file serving |
| pytest | ≥8.2 | Testing framework |
| httpx | ≥0.27 | Async HTTP client |
