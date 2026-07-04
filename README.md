# FHIR Terminology-Mapping Microservice

A microservice platform that bridges the gap between clinicians and complex HL7 FHIR data schemas. Doctors dictate or type natural clinical narratives in **English or Hindi**, and the service automatically extracts entities, maps them to standard medical terminologies (SNOMED-CT, LOINC, RxNorm, UCUM), and outputs a valid **FHIR R4 Transaction Bundle** — saved both to a database and as JSON files on disk.

---

## Key Features

- **Multilingual Audio Transcription**: Upload `.wav`, `.mp3`, `.m4a`, `.webm`, `.ogg`, or `.flac` audio files in English or Hindi — the system transcribes and translates to English automatically
- **Clinical NLP Extraction**: Regex-based engine that parses free-text notes to extract demographics, conditions, vitals, labs, medications, allergies, and care plans
- **Terminology Auto-Coding**: Automatic mapping to SNOMED-CT, LOINC, RxNorm, and UCUM via local dictionaries + live NLM RxNorm API
- **FHIR R4 Bundle Generation**: Produces valid Transaction Bundles with 7 interlinked resource types (Patient, Encounter, Condition, Observation, AllergyIntolerance, MedicationRequest, CarePlan)
- **Persistent Storage**: Bundles saved to SQLite database AND to `FHIR_gt/<patient_id>/` as JSON files

---

## Project Structure

```
Micro-Service/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # App settings (env vars, API keys)
│   │   ├── database.py          # SQLAlchemy engine & session
│   │   ├── models.py            # ORM model (FHIRBundleRecord)
│   │   ├── routes/
│   │   │   ├── audio.py         # POST /api/audio/transcribe
│   │   │   ├── nlp.py           # POST /api/nlp/extract
│   │   │   ├── terminology.py   # GET  /api/terminology/search
│   │   │   └── fhir.py          # POST /api/fhir/bundle
│   │   └── services/
│   │       ├── transcription.py       # Whisper API + demo fallback
│   │       ├── nlp_engine.py          # Regex-based entity extraction
│   │       ├── terminology_gateway.py # SNOMED/LOINC/RxNorm/UCUM lookups
│   │       └── fhir_bundler.py        # FHIR R4 Transaction Bundle builder
│   └── tests/
│       └── test_logic.py        # Unit tests (7 tests)
├── frontend/
│   ├── index.html               # Single-page clinical workspace UI
│   ├── css/styles.css           # Glassmorphism design system
│   └── js/app.js                # Audio recording, form logic, API calls
├── FHIR_gt/                     # Generated FHIR bundles (auto-created)
│   └── <patient_id>/
│       └── fhir_bundle_<timestamp>.json
├── fhir_bundles.db              # SQLite database (auto-created)
├── environment.yml              # Conda environment dependencies
├── README.md                    # This file
├── Technical_Report.md          # Architecture & design details
└── User_Manual.md               # End-user guide for clinicians
```

---

## Setup Instructions

### Prerequisites
- **Python 3.10+** installed (via [Miniconda](https://docs.anaconda.com/free/miniconda/index.html), Anaconda, or standalone)
- A web browser (Chrome, Firefox, Edge)

### Option A: Using Conda (Recommended)

```bash
# 1. Navigate to the project root
cd Micro-Service

# 2. Create the environment
conda env create -f environment.yml

# 3. Activate it
conda activate fhir_microservice
```

### Option B: Using pip directly

```bash
# 1. Navigate to the project root
cd Micro-Service

# 2. Install dependencies
pip install fastapi uvicorn python-multipart requests pydantic pydantic-settings aiofiles sqlalchemy httpx pytest
```

---

## Running the Server

### On Windows (CMD)
```cmd
cd Micro-Service
set PYTHONPATH=.
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### On Windows (PowerShell)
```powershell
cd Micro-Service
$env:PYTHONPATH = "."; uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### On Mac/Linux
```bash
cd Micro-Service
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open **http://localhost:8000** in your browser.

---

## Enable Real Audio Transcription (Optional)

By default, the app runs in **demo mode** — uploading any audio file returns realistic sample clinical transcripts. To use real Sarvam AI transcription for actual `.wav` files:

### Windows (CMD)
```cmd
set SARVAM_API_KEY=your-api-key
```

### Windows (PowerShell)
```powershell
$env:SARVAM_API_KEY = "your-api-key"
```

### Mac/Linux
```bash
export SARVAM_API_KEY="your-api-key"
```

Set this **before** running the `uvicorn` command.

---

## Running Tests

```bash
cd Micro-Service
set PYTHONPATH=.
python -m pytest backend/tests/test_logic.py -v
```

Expected output: **7 tests passed** (unit mapping, condition search, medication lookup, NLP extraction, FHIR bundle generation, transcription service, filesystem save).

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/audio/transcribe` | Upload audio file → get transcript + extracted entities |
| `POST` | `/api/audio/transcribe-text` | Send text → get extracted entities |
| `POST` | `/api/nlp/extract` | Extract clinical entities from free text |
| `GET`  | `/api/terminology/search` | Search terminology (SNOMED, LOINC, RxNorm, UCUM) |
| `GET`  | `/api/terminology/map-unit` | Resolve a unit string to UCUM code |
| `POST` | `/api/fhir/bundle` | Generate FHIR R4 Transaction Bundle |
| `GET`  | `/api/fhir/bundles` | List all saved FHIR bundles from FHIR_gt/ |
| `GET`  | `/api/health` | Health check |

---

## FHIR Output

Generated bundles are saved in two places:
1. **SQLite Database** (`fhir_bundles.db`) — for querying
2. **Filesystem** (`FHIR_gt/<patient_id>/fhir_bundle_<timestamp>.json`) — for portability

If the same Patient ID is used multiple times, all bundles are stored inside the same patient folder:
```
FHIR_gt/
├── MRN-12345/
│   ├── fhir_bundle_20260704_160530.json
│   └── fhir_bundle_20260704_161200.json
└── MRN-67890/
    └── fhir_bundle_20260704_170000.json
```

---

## Supported Audio Formats

| Format | Extension | MIME Type |
|--------|-----------|-----------|
| WAV | `.wav` | `audio/wav` |
| MP3 | `.mp3` | `audio/mpeg` |
| M4A | `.m4a` | `audio/mp4` |
| WebM | `.webm` | `audio/webm` |
| OGG | `.ogg` | `audio/ogg` |
| FLAC | `.flac` | `audio/flac` |
| AAC | `.aac` | `audio/aac` |

**Supported Languages**: English, Hindi (हिन्दी), Hinglish (auto-detected)

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend Framework | FastAPI (Python) |
| Audio Transcription | Sarvam AI API / Demo fallback |
| NLP Engine | Regex-based (no ML dependencies) |
| Terminology Mapping | Local dictionaries + NLM RxNorm REST API |
| Database | SQLite via SQLAlchemy ORM |
| Frontend | Vanilla HTML/CSS/JS (glassmorphism design) |
| FHIR Standard | HL7 FHIR R4 |
