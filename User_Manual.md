# User Manual: FHIR Clinical Workspace

Welcome to the **FHIR Clinical Workspace** — an intelligent platform designed to simplify clinical documentation. This system automatically extracts meaning from your clinical notes or audio dictations (in English or Hindi) and converts them into structured HL7 FHIR R4 formats, applying standard medical codes without any manual lookup.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard Overview](#2-dashboard-overview)
3. [Step-by-Step Workflow](#3-step-by-step-workflow)
4. [Understanding the FHIR Output](#4-understanding-the-fhir-output)
5. [Where Are My Files Saved?](#5-where-are-my-files-saved)
6. [Supported Audio Formats & Languages](#6-supported-audio-formats--languages)
7. [Troubleshooting](#7-troubleshooting)
8. [FAQ](#8-faq)

---

## 1. Getting Started

### Starting the Application

1. Open a terminal/command prompt
2. Navigate to the `Micro-Service` project folder
3. Run the server:

   **Windows (CMD)**:
   ```cmd
   set PYTHONPATH=.
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   **Windows (PowerShell)**:
   ```powershell
   $env:PYTHONPATH = "."; uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   **Mac/Linux**:
   ```bash
   PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Open your web browser and go to **http://localhost:8000**

You should see the FHIRBridge clinical workspace dashboard.

---

## 2. Dashboard Overview

The interface is divided into two panels:

### Left Panel — Clinical Notes Input
- **Audio Capture**: Record or upload audio files
- **Language Selector**: Choose between Auto-detect, English, or Hindi
- **Original Transcript**: Shows the Hindi transcript (only appears when Hindi audio is detected)
- **Clinical Transcript (English)**: The English text used for entity extraction
- **Quick Stats**: Shows count of extracted Conditions, Vitals/Labs, Medications, and Allergies

### Right Panel — Clinical Summary Form
Seven editable sections that auto-populate from your clinical notes:
1. **Demographics** (Patient) — Name, Age, Gender, Phone, Patient ID
2. **Visit Context** (Encounter) — Encounter type, Reason for visit
3. **Diagnoses & Symptoms** (Condition) — with SNOMED-CT autocomplete
4. **Vitals & Lab Results** (Observation) — with LOINC autocomplete and UCUM units
5. **Allergies & Reactions** (AllergyIntolerance) — with SNOMED-CT autocomplete
6. **Prescriptions** (MedicationRequest) — with RxNorm autocomplete
7. **Treatment & Next Steps** (CarePlan) — with SNOMED-CT autocomplete

---

## 3. Step-by-Step Workflow

### Step 1: Enter Patient ID

At the top of the right panel under **Demographics**, enter the patient's **Patient ID** (e.g., MRN number like `100`, `MRN-12345`).

> **Important**: The Patient ID determines the folder name where the FHIR bundle will be saved. If you use the same ID across multiple visits, all bundles for that patient are grouped together.

### Step 2: Provide Clinical Notes

You have **four ways** to input clinical notes:

#### Option A: Record Audio
1. Select the **Audio Language** (Auto-detect, English, or Hindi)
2. Click the **Record** button (microphone icon)
3. Speak your clinical notes into the microphone
4. Click **Stop** when finished
5. The system will transcribe the audio and auto-populate the form

#### Option B: Upload an Audio File
1. Select the **Audio Language** if known
2. Click the **Upload** button
3. Select a `.wav`, `.mp3`, `.m4a`, `.webm`, `.ogg`, or `.flac` file from your computer
4. The system will transcribe and extract entities automatically

#### Option C: Type or Paste Text
1. Type or paste your clinical notes into the **Clinical Transcript (English)** text area
2. Click the **Extract Entities** button
3. The form will auto-populate with extracted data

#### Option D: Load a Demo Note
1. Click the **Demo Note** button
2. A sample clinical scenario will be loaded automatically
3. This is useful for testing the system without real audio

### Step 3: Review & Edit Extracted Data

After extraction, review each section of the form:

- **Check for accuracy**: The NLP engine uses pattern matching and may not capture everything perfectly
- **Edit any incorrect values**: Click on any field to modify it
- **Add missing entries**: Click the **+ Add** button in any section to add new rows
- **Remove wrong entries**: Click the **✕** button on any row to remove it

### Step 4: Terminology Auto-Coding

As you type or edit entries, the system provides **real-time terminology autocomplete**:

- Start typing at least **2 characters** in any coded field
- A dropdown will appear with matching medical codes
- Click on a result to lock in the official code
- A **small colored tag** next to the field confirms the code was linked

The following terminologies are used:

| Field Type | Terminology | Example |
|-----------|-------------|---------|
| Conditions & Symptoms | SNOMED-CT | "Diabetes" → `44054006` |
| Allergies | SNOMED-CT | "Penicillin" → `91936005` |
| Observations & Vitals | LOINC | "Heart rate" → `8867-4` |
| Units | UCUM | "mmHg" → `mm[Hg]` |
| Medications | RxNorm | "Metformin" → `6809` |
| Encounter Type | HL7 v3-ActCode | "Emergency" → `EMER` |

### Step 5: Generate the FHIR Bundle

1. Ensure the **Patient Name** is filled in (required)
2. Click the **Generate FHIR Bundle** button at the bottom
3. A modal window will appear showing:
   - **Resource count summary**: e.g., 1 Patient, 1 Encounter, 3 Conditions, 4 Observations
   - **Save location**: The path where the JSON was saved (`FHIR_gt/<patient_id>/`)
   - **Full JSON payload**: Syntax-highlighted and scrollable

### Step 6: Export the Bundle

From the modal, you can:
- **Copy JSON**: Copies the entire JSON to your clipboard
- **Download**: Saves the JSON as a `.json` file to your Downloads folder
- **Close**: Click ✕ or press Escape to close the modal

The bundle is **automatically saved** to the server — no extra action needed.

---

## 4. Understanding the FHIR Output

Each generated bundle is a **FHIR R4 Transaction Bundle** containing interconnected resources:

```
Bundle (type: "transaction")
│
├── Patient           → Name, gender, age, phone, MRN
├── Encounter         → Visit type (OPD/Emergency/IPD), reason
├── Condition (×N)    → Each diagnosis/symptom with SNOMED code
├── Observation (×N)  → Each vital/lab result with LOINC code + value + UCUM unit
├── AllergyIntolerance (×N) → Allergy substance + reaction
├── MedicationRequest (×N)  → Drug name (RxNorm) + dose + frequency
└── CarePlan          → Follow-up, referrals, tests ordered
```

All resources are linked together:
- Every Condition, Observation, Medication, etc. references the **Patient** and **Encounter**
- This ensures the bundle is **relationally consistent** and can be submitted to any FHIR-compliant server

---

## 5. Where Are My Files Saved?

Generated FHIR bundles are saved in **two places**:

### A. On Disk (FHIR_gt folder)

Location: `Micro-Service/FHIR_gt/<patient_id>/`

```
FHIR_gt/
├── 100/                                    ← Patient ID "100"
│   ├── fhir_bundle_20260704_111548.json    ← First visit
│   └── fhir_bundle_20260704_120030.json    ← Second visit
├── MRN-12345/                              ← Patient ID "MRN-12345"
│   └── fhir_bundle_20260704_170000.json
└── Ramesh Kumar/                           ← Falls back to name if no ID given
    └── fhir_bundle_20260705_090000.json
```

**Rules**:
- If you enter a Patient ID → folder is named after the Patient ID
- If no Patient ID is given → folder is named after the Patient Name
- If neither is provided → folder is named `anonymous`
- Multiple bundles for the same patient go into the **same folder**

### B. In the Database

Location: `Micro-Service/fhir_bundles.db` (SQLite)

This database can be queried with any SQLite tool (e.g., DB Browser for SQLite) to search bundles by patient ID, name, or date.

---

## 6. Supported Audio Formats & Languages

### Audio Formats

| Format | Extension | Works? |
|--------|-----------|--------|
| WAV (Waveform Audio) | `.wav` | ✅ Yes |
| MP3 | `.mp3` | ✅ Yes |
| M4A (AAC) | `.m4a` | ✅ Yes |
| WebM | `.webm` | ✅ Yes |
| OGG Vorbis | `.ogg` | ✅ Yes |
| FLAC (Lossless) | `.flac` | ✅ Yes |
| AAC | `.aac` | ✅ Yes |

### Languages

| Language | Support | Notes |
|----------|---------|-------|
| English | ✅ Full | Direct transcription |
| Hindi (हिन्दी) | ✅ Full | Transcribed in Hindi + translated to English |
| Hinglish | ✅ Auto-detected | Mixed Hindi-English treated as Hindi |

> **Note**: Without a Sarvam API key, the system runs in **demo mode** — uploading any audio file returns pre-built sample transcripts (both English and Hindi demos are available). To enable real transcription, set the `SARVAM_API_KEY` environment variable before starting the server.

---

## 7. Troubleshooting

### "Bundle generation failed: HTTP 500"
- **Cause**: Usually a stale database file with an outdated schema
- **Fix**: Stop the server, delete `fhir_bundles.db`, and restart. The database will be recreated automatically

### Microphone Access Denied
- **Cause**: Browser doesn't have permission to use your microphone
- **Fix**: Click the lock/info icon in the browser address bar → Allow microphone access → Refresh the page

### No Autocomplete Options Appearing
- **Cause**: You haven't typed enough characters, or the term isn't in the local dictionary
- **Fix**: Type at least 2 characters. If still no results, the specific term may not exist in the local mappings — you can type the full name and proceed without a code

### Audio Upload Shows No Transcript
- **Cause**: No `SARVAM_API_KEY` configured (running in demo mode)
- **Fix**: The demo mode returns sample transcripts regardless of the uploaded file. To transcribe real audio, set the API key

### "The filename, directory name, or volume label syntax is incorrect"
- **Cause**: Running PowerShell commands (`$env:`) in CMD, or wrong directory
- **Fix**: Make sure you're in the `Micro-Service/Micro-Service/` directory (not the parent), and use the correct syntax for your shell (see [Getting Started](#1-getting-started))

### Server Won't Start
- **Cause**: Missing Python dependencies
- **Fix**: Run `pip install fastapi uvicorn python-multipart requests pydantic pydantic-settings aiofiles sqlalchemy httpx`

---

## 8. FAQ

**Q: Do I need an internet connection?**
A: Only for two things: (1) Real audio transcription via Sarvam AI API, and (2) Medication lookups via the NLM RxNorm API. Everything else works offline — NLP extraction, terminology mapping (SNOMED, LOINC, UCUM), and FHIR generation all use local data.

**Q: Can I use the system without a Sarvam API key?**
A: Yes! The system runs in demo mode — it returns realistic sample clinical transcripts when you upload audio or click "Demo Note". This is perfect for testing and evaluation.

**Q: What happens if I enter the same Patient ID multiple times?**
A: All bundles are grouped together in the same folder under `FHIR_gt/<patient_id>/`. Each visit generates a new timestamped JSON file within that folder.

**Q: Can I submit these bundles to a real FHIR server?**
A: Yes — the bundles are valid FHIR R4 Transaction Bundles with proper `POST` requests in each entry. They can be submitted to any FHIR-compliant server (HAPI FHIR, Azure FHIR, Google Healthcare API, etc.).

**Q: Is the NLP extraction perfect?**
A: No — it uses regex patterns, not machine learning. It may miss some entities or extract incorrect values. The form is designed for the **doctor to review and correct** the extracted data before generating the final FHIR bundle.

**Q: What medical terminologies are supported?**
A: Four international standards:
- **SNOMED-CT** — Conditions, allergies, reactions, care plan activities
- **LOINC** — Laboratory tests and vital signs
- **RxNorm** — Medications and drug names
- **UCUM** — Units of measure (mg, mmHg, °C, etc.)
