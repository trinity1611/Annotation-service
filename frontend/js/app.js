/* ===================================================================
   FHIR Clinical Workspace – Application Logic
   Handles audio recording, transcription, NLP extraction,
   terminology autocomplete, form management, and FHIR bundle generation.
   =================================================================== */

(() => {
    'use strict';

    // ── API Base ──────────────────────────────────────────────────────
    const API = '';

    // ── DOM References ────────────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const statusDot = $('#status-dot');
    const statusText = $('#status-text');
    const btnRecord = $('#btn-record');
    const audioUpload = $('#audio-upload');
    const recordingTimer = $('#recording-timer');
    const timerText = $('#timer-text');
    const transcriptArea = $('#transcript-area');
    const btnExtract = $('#btn-extract');
    const btnDemo = $('#btn-demo');
    const btnGenerateBundle = $('#btn-generate-bundle');
    const btnClearForm = $('#btn-clear-form');
    const modalOverlay = $('#modal-overlay');
    const jsonContent = $('#json-content');
    const modalStats = $('#modal-stats');
    const btnCopyBundle = $('#btn-copy-bundle');
    const btnDownloadBundle = $('#btn-download-bundle');
    const btnCloseModal = $('#btn-close-modal');
    const visualizerCanvas = $('#visualizer-canvas');
    const toastContainer = $('#toast-container');

    // Info counters
    const infoConditions = $('#info-conditions');
    const infoObservations = $('#info-observations');
    const infoMedications = $('#info-medications');
    const infoAllergies = $('#info-allergies');

    // ── State ─────────────────────────────────────────────────────────
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let timerInterval = null;
    let timerSeconds = 0;
    let currentBundle = null;
    let autocompleteTimeout = null;

    // ── Utilities ─────────────────────────────────────────────────────
    function setStatus(text, type = 'ready') {
        statusText.textContent = text;
        statusDot.className = 'status-dot';
        if (type === 'busy') statusDot.classList.add('busy');
        else if (type === 'error') statusDot.classList.add('error');
    }

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.animation = 'toast-out 0.3s ease-in forwards';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    function formatTime(seconds) {
        const m = String(Math.floor(seconds / 60)).padStart(2, '0');
        const s = String(seconds % 60).padStart(2, '0');
        return `${m}:${s}`;
    }

    function updateInfoCounters() {
        infoConditions.textContent = $$('#repeater-conditions .repeater-row').length;
        infoObservations.textContent = $$('#repeater-observations .repeater-row').length;
        infoMedications.textContent = $$('#repeater-medications .repeater-row').length;
        infoAllergies.textContent = $$('#repeater-allergies .repeater-row').length;
    }

    // ── JSON Syntax Highlighting ──────────────────────────────────────
    function highlightJSON(json) {
        const str = JSON.stringify(json, null, 2);
        return str.replace(
            /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
            (match) => {
                let cls = 'json-number';
                if (/^"/.test(match)) {
                    cls = /:$/.test(match) ? 'json-key' : 'json-string';
                } else if (/true|false/.test(match)) {
                    cls = 'json-bool';
                } else if (/null/.test(match)) {
                    cls = 'json-null';
                }
                return `<span class="${cls}">${match}</span>`;
            }
        );
    }

    // ── Audio Recording ───────────────────────────────────────────────
    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            audioChunks = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                stream.getTracks().forEach(t => t.stop());
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                await uploadAudio(blob, 'recording.webm');
            };

            mediaRecorder.start(250);
            isRecording = true;
            btnRecord.classList.add('recording');
            btnRecord.querySelector('.record-label').textContent = 'Stop';
            recordingTimer.style.display = 'flex';
            timerSeconds = 0;
            timerText.textContent = '00:00';
            timerInterval = setInterval(() => {
                timerSeconds++;
                timerText.textContent = formatTime(timerSeconds);
            }, 1000);

            // Visualizer
            setupVisualizer(stream);
            setStatus('Recording…', 'busy');
        } catch (err) {
            console.error('Mic access failed:', err);
            showToast('Microphone access denied. Please allow access.', 'error');
        }
    }

    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            btnRecord.classList.remove('recording');
            btnRecord.querySelector('.record-label').textContent = 'Record';
            recordingTimer.style.display = 'none';
            clearInterval(timerInterval);
            setStatus('Processing audio…', 'busy');
        }
    }

    btnRecord.addEventListener('click', () => {
        if (isRecording) stopRecording();
        else startRecording();
    });

    // ── Audio Upload ──────────────────────────────────────────────────
    audioUpload.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setStatus('Uploading audio…', 'busy');
        await uploadAudio(file, file.name);
        audioUpload.value = '';
    });

    async function uploadAudio(blob, filename) {
        try {
            const formData = new FormData();
            formData.append('file', blob, filename);

            // Pass language hint if user selected one
            const langSelect = document.getElementById('language-select');
            if (langSelect && langSelect.value) {
                formData.append('language', langSelect.value);
            }

            const resp = await fetch(`${API}/api/audio/transcribe`, {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const data = await resp.json();

            // Show English transcript in the main area
            transcriptArea.value = data.transcript;

            // Show original transcript (Hindi/other) if different
            const origArea = document.getElementById('original-transcript-area');
            const origCard = document.getElementById('original-transcript-card');
            if (data.language && data.language !== 'en' && data.original_transcript !== data.transcript) {
                if (origArea) origArea.value = data.original_transcript;
                if (origCard) origCard.style.display = 'block';
            } else {
                if (origCard) origCard.style.display = 'none';
            }

            // Update language badge
            const langBadge = document.getElementById('detected-language');
            if (langBadge) {
                const langNames = { 'en': 'English', 'hi': 'Hindi' };
                langBadge.textContent = langNames[data.language] || data.language;
                langBadge.style.display = 'inline-block';
            }

            populateForm(data.extracted);
            setStatus('Ready');
            showToast('Transcription complete! Entities extracted.', 'success');
        } catch (err) {
            console.error('Transcription failed:', err);
            setStatus('Error', 'error');
            showToast('Transcription failed: ' + err.message, 'error');
        }
    }

    // ── Audio Visualizer ──────────────────────────────────────────────
    function setupVisualizer(stream) {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const analyser = audioCtx.createAnalyser();
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        analyser.fftSize = 64;

        const ctx = visualizerCanvas.getContext('2d');
        const bufLen = analyser.frequencyBinCount;
        const dataArr = new Uint8Array(bufLen);

        function draw() {
            if (!isRecording) {
                ctx.clearRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);
                return;
            }
            requestAnimationFrame(draw);
            analyser.getByteFrequencyData(dataArr);

            ctx.clearRect(0, 0, visualizerCanvas.width, visualizerCanvas.height);
            const barW = (visualizerCanvas.width / bufLen) * 1.5;
            let x = 0;
            for (let i = 0; i < bufLen; i++) {
                const h = (dataArr[i] / 255) * visualizerCanvas.height;
                const gradient = ctx.createLinearGradient(0, visualizerCanvas.height, 0, visualizerCanvas.height - h);
                gradient.addColorStop(0, 'rgba(99,102,241,0.3)');
                gradient.addColorStop(1, 'rgba(139,92,246,0.8)');
                ctx.fillStyle = gradient;
                ctx.fillRect(x, visualizerCanvas.height - h, barW - 1, h);
                x += barW;
            }
        }
        draw();
    }

    // ── Extract Entities (Text) ───────────────────────────────────────
    btnExtract.addEventListener('click', async () => {
        const text = transcriptArea.value.trim();
        if (!text) {
            showToast('Please enter or paste clinical notes first.', 'error');
            return;
        }

        setStatus('Extracting entities…', 'busy');
        try {
            const resp = await fetch(`${API}/api/audio/transcribe-text`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text }),
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const data = await resp.json();
            populateForm(data.extracted);
            setStatus('Ready');
            showToast('Entities extracted successfully!', 'success');
        } catch (err) {
            console.error('Extraction failed:', err);
            setStatus('Error', 'error');
            showToast('Extraction failed: ' + err.message, 'error');
        }
    });

    // ── Demo Note ─────────────────────────────────────────────────────
    btnDemo.addEventListener('click', async () => {
        setStatus('Loading demo…', 'busy');
        try {
            const resp = await fetch(`${API}/api/audio/transcribe`, {
                method: 'POST',
                body: (() => {
                    const fd = new FormData();
                    fd.append('file', new Blob(['demo'], { type: 'audio/wav' }), 'demo.wav');
                    return fd;
                })(),
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const data = await resp.json();
            transcriptArea.value = data.transcript;
            populateForm(data.extracted);
            setStatus('Ready');
            showToast('Demo note loaded!', 'info');
        } catch (err) {
            console.error('Demo load failed:', err);
            setStatus('Error', 'error');
            showToast('Demo load failed: ' + err.message, 'error');
        }
    });

    // ── Populate Form from Extracted Data ─────────────────────────────
    function populateForm(extracted) {
        // Demographics
        const d = extracted.demographics || {};
        $('#patient-name').value = d.name || '';
        $('#patient-age').value = d.age || '';
        $('#patient-gender').value = d.gender || '';
        $('#patient-phone').value = d.phone || '';

        // Encounter
        const enc = extracted.encounter || {};
        $('#encounter-class').value = enc.class || '';
        $('#encounter-reason').value = enc.reason || '';

        // Conditions
        const condRepeater = $('#repeater-conditions');
        condRepeater.innerHTML = '';
        (extracted.conditions || []).forEach(c => addConditionRow(c.name));

        // Observations
        const obsRepeater = $('#repeater-observations');
        obsRepeater.innerHTML = '';
        (extracted.observations || []).forEach(o => addObservationRow(o.name, o.value, o.unit));

        // Allergies
        const algRepeater = $('#repeater-allergies');
        algRepeater.innerHTML = '';
        (extracted.allergies || []).forEach(a => addAllergyRow(a.substance, a.reaction));

        // Medications
        const medRepeater = $('#repeater-medications');
        medRepeater.innerHTML = '';
        (extracted.medications || []).forEach(m => addMedicationRow(m.name, m.dose, m.frequency));

        // Care Plan
        const cpRepeater = $('#repeater-careplan');
        cpRepeater.innerHTML = '';
        (extracted.carePlan || []).forEach(cp => addCarePlanRow(cp.activity));

        updateInfoCounters();
    }

    // ── Repeater Row Builders ─────────────────────────────────────────

    function createRemoveBtn(row) {
        const btn = document.createElement('button');
        btn.className = 'btn-remove';
        btn.title = 'Remove';
        btn.innerHTML = '✕';
        btn.addEventListener('click', () => {
            row.style.animation = 'toast-out 0.2s ease-in forwards';
            setTimeout(() => { row.remove(); updateInfoCounters(); }, 200);
        });
        return btn;
    }

    function createAutocompleteInput(placeholder, resourceType, row, codeTagEl) {
        const wrapper = document.createElement('div');
        wrapper.className = 'autocomplete-wrapper';

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = placeholder;
        input.autocomplete = 'off';

        const dropdown = document.createElement('div');
        dropdown.className = 'autocomplete-dropdown';

        wrapper.appendChild(input);
        wrapper.appendChild(dropdown);

        input.addEventListener('input', () => {
            clearTimeout(autocompleteTimeout);
            const query = input.value.trim();
            if (query.length < 2) {
                dropdown.classList.remove('visible');
                return;
            }
            autocompleteTimeout = setTimeout(async () => {
                try {
                    const resp = await fetch(`${API}/api/terminology/search?text=${encodeURIComponent(query)}&resource_type=${encodeURIComponent(resourceType)}`);
                    if (!resp.ok) return;
                    const results = await resp.json();
                    renderDropdown(dropdown, results, input, codeTagEl);
                } catch (e) { console.error('Autocomplete error:', e); }
            }, 300);
        });

        input.addEventListener('blur', () => {
            setTimeout(() => dropdown.classList.remove('visible'), 200);
        });

        return { wrapper, input };
    }

    function renderDropdown(dropdown, results, input, codeTagEl) {
        dropdown.innerHTML = '';
        if (!results.length) {
            dropdown.classList.remove('visible');
            return;
        }
        results.forEach(r => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            item.innerHTML = `
                <span class="item-display">${escapeHtml(r.display || r.code)}</span>
                <span class="item-code">${escapeHtml(r.code)}</span>
            `;
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                input.value = r.display || r.code;
                input.dataset.code = r.code;
                input.dataset.system = r.system;
                input.dataset.display = r.display || '';
                dropdown.classList.remove('visible');
                if (codeTagEl) {
                    codeTagEl.textContent = `${r.code}`;
                    codeTagEl.classList.add('resolved');
                    codeTagEl.title = `${r.system} | ${r.code}`;
                }
            });
            dropdown.appendChild(item);
        });
        dropdown.classList.add('visible');
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Condition row
    function addConditionRow(name = '') {
        const repeater = $('#repeater-conditions');
        const row = document.createElement('div');
        row.className = 'repeater-row';

        const codeTag = document.createElement('span');
        codeTag.className = 'code-tag';
        codeTag.textContent = '—';

        const fg = document.createElement('div');
        fg.className = 'field-group';
        const label = document.createElement('span');
        label.className = 'field-label';
        label.textContent = 'Condition / Symptom';
        const { wrapper, input } = createAutocompleteInput('e.g., Diabetes, Fever', 'Condition', row, codeTag);
        input.value = name;
        fg.appendChild(label);
        fg.appendChild(wrapper);

        row.appendChild(fg);
        row.appendChild(codeTag);
        row.appendChild(createRemoveBtn(row));
        repeater.appendChild(row);

        // Auto-resolve if name provided
        if (name) autoResolve(input, 'Condition', codeTag);

        updateInfoCounters();
    }

    // Observation row
    function addObservationRow(name = '', value = '', unit = '') {
        const repeater = $('#repeater-observations');
        const row = document.createElement('div');
        row.className = 'repeater-row';

        const codeTag = document.createElement('span');
        codeTag.className = 'code-tag';
        codeTag.textContent = '—';

        const fg1 = document.createElement('div');
        fg1.className = 'field-group';
        const l1 = document.createElement('span'); l1.className = 'field-label'; l1.textContent = 'Test / Vital';
        const { wrapper, input } = createAutocompleteInput('e.g., Blood Pressure', 'Observation', row, codeTag);
        input.value = name;
        fg1.appendChild(l1);
        fg1.appendChild(wrapper);

        const fg2 = document.createElement('div');
        fg2.className = 'field-group narrow';
        const l2 = document.createElement('span'); l2.className = 'field-label'; l2.textContent = 'Value';
        const inp2 = document.createElement('input');
        inp2.type = 'text'; inp2.placeholder = '120/80'; inp2.value = value;
        fg2.appendChild(l2); fg2.appendChild(inp2);

        const fg3 = document.createElement('div');
        fg3.className = 'field-group narrow';
        const l3 = document.createElement('span'); l3.className = 'field-label'; l3.textContent = 'Unit';
        const { wrapper: unitWrapper, input: inp3 } = createAutocompleteInput('mmHg', 'Unit', row, null);
        inp3.value = unit;
        fg3.appendChild(l3); fg3.appendChild(unitWrapper);

        row.appendChild(fg1);
        row.appendChild(fg2);
        row.appendChild(fg3);
        row.appendChild(codeTag);
        row.appendChild(createRemoveBtn(row));
        repeater.appendChild(row);

        if (name) autoResolve(input, 'Observation', codeTag);
        if (unit) autoResolve(inp3, 'Unit', null);
        updateInfoCounters();
    }

    // Allergy row
    function addAllergyRow(substance = '', reaction = '') {
        const repeater = $('#repeater-allergies');
        const row = document.createElement('div');
        row.className = 'repeater-row';

        const codeTag = document.createElement('span');
        codeTag.className = 'code-tag';
        codeTag.textContent = '—';

        const fg1 = document.createElement('div');
        fg1.className = 'field-group';
        const l1 = document.createElement('span'); l1.className = 'field-label'; l1.textContent = 'Substance';
        const { wrapper, input } = createAutocompleteInput('e.g., Penicillin', 'AllergyIntolerance', row, codeTag);
        input.value = substance;
        fg1.appendChild(l1); fg1.appendChild(wrapper);

        const fg2 = document.createElement('div');
        fg2.className = 'field-group';
        const l2 = document.createElement('span'); l2.className = 'field-label'; l2.textContent = 'Reaction';
        const inp2 = document.createElement('input');
        inp2.type = 'text'; inp2.placeholder = 'e.g., Rash, Anaphylaxis'; inp2.value = reaction;
        fg2.appendChild(l2); fg2.appendChild(inp2);

        row.appendChild(fg1);
        row.appendChild(fg2);
        row.appendChild(codeTag);
        row.appendChild(createRemoveBtn(row));
        repeater.appendChild(row);

        if (substance) autoResolve(input, 'AllergyIntolerance', codeTag);
        updateInfoCounters();
    }

    // Medication row
    function addMedicationRow(name = '', dose = '', frequency = '') {
        const repeater = $('#repeater-medications');
        const row = document.createElement('div');
        row.className = 'repeater-row';

        const codeTag = document.createElement('span');
        codeTag.className = 'code-tag';
        codeTag.textContent = '—';

        const fg1 = document.createElement('div');
        fg1.className = 'field-group';
        const l1 = document.createElement('span'); l1.className = 'field-label'; l1.textContent = 'Drug Name';
        const { wrapper, input } = createAutocompleteInput('e.g., Metformin', 'MedicationRequest', row, codeTag);
        input.value = name;
        fg1.appendChild(l1); fg1.appendChild(wrapper);

        const fg2 = document.createElement('div');
        fg2.className = 'field-group narrow';
        const l2 = document.createElement('span'); l2.className = 'field-label'; l2.textContent = 'Dose';
        const inp2 = document.createElement('input');
        inp2.type = 'text'; inp2.placeholder = '500 mg'; inp2.value = dose;
        fg2.appendChild(l2); fg2.appendChild(inp2);

        const fg3 = document.createElement('div');
        fg3.className = 'field-group';
        const l3 = document.createElement('span'); l3.className = 'field-label'; l3.textContent = 'Frequency';
        const inp3 = document.createElement('input');
        inp3.type = 'text'; inp3.placeholder = 'e.g., twice daily'; inp3.value = frequency;
        fg3.appendChild(l3); fg3.appendChild(inp3);

        row.appendChild(fg1);
        row.appendChild(fg2);
        row.appendChild(fg3);
        row.appendChild(codeTag);
        row.appendChild(createRemoveBtn(row));
        repeater.appendChild(row);

        if (name) autoResolve(input, 'MedicationRequest', codeTag);
        updateInfoCounters();
    }

    // CarePlan row
    function addCarePlanRow(activity = '') {
        const repeater = $('#repeater-careplan');
        const row = document.createElement('div');
        row.className = 'repeater-row';

        const codeTag = document.createElement('span');
        codeTag.className = 'code-tag';
        codeTag.textContent = '—';

        const fg = document.createElement('div');
        fg.className = 'field-group';
        const label = document.createElement('span');
        label.className = 'field-label';
        label.textContent = 'Activity / Next Step';
        const { wrapper, input } = createAutocompleteInput('e.g., Follow up, X-ray', 'CarePlan', row, codeTag);
        input.value = activity;
        fg.appendChild(label); fg.appendChild(wrapper);

        row.appendChild(fg);
        row.appendChild(codeTag);
        row.appendChild(createRemoveBtn(row));
        repeater.appendChild(row);

        if (activity) autoResolve(input, 'CarePlan', codeTag);
        updateInfoCounters();
    }

    // Auto-resolve: fire a terminology search immediately for pre-filled values
    async function autoResolve(input, resourceType, codeTagEl) {
        const query = input.value.trim();
        if (query.length < 2) return;
        try {
            const resp = await fetch(`${API}/api/terminology/search?text=${encodeURIComponent(query)}&resource_type=${encodeURIComponent(resourceType)}`);
            if (!resp.ok) return;
            const results = await resp.json();
            if (results.length > 0) {
                const best = results[0];
                input.dataset.code = best.code;
                input.dataset.system = best.system;
                input.dataset.display = best.display || '';
                if (codeTagEl) {
                    codeTagEl.textContent = best.code;
                    codeTagEl.classList.add('resolved');
                    codeTagEl.title = `${best.system} | ${best.code}`;
                }
            }
        } catch (e) { /* silent */ }
    }

    // ── Add Buttons ───────────────────────────────────────────────────
    $('#btn-add-condition').addEventListener('click', () => addConditionRow());
    $('#btn-add-observation').addEventListener('click', () => addObservationRow());
    $('#btn-add-allergy').addEventListener('click', () => addAllergyRow());
    $('#btn-add-medication').addEventListener('click', () => addMedicationRow());
    $('#btn-add-careplan').addEventListener('click', () => addCarePlanRow());

    // ── Encounter class autocomplete ──────────────────────────────────
    const encInput = $('#encounter-class');
    const encDropdown = $('#dropdown-encounter-class');

    encInput.addEventListener('input', () => {
        clearTimeout(autocompleteTimeout);
        const q = encInput.value.trim();
        if (q.length < 1) { encDropdown.classList.remove('visible'); return; }
        autocompleteTimeout = setTimeout(async () => {
            try {
                const resp = await fetch(`${API}/api/terminology/search?text=${encodeURIComponent(q)}&resource_type=Encounter`);
                if (!resp.ok) return;
                const results = await resp.json();
                encDropdown.innerHTML = '';
                results.forEach(r => {
                    const item = document.createElement('div');
                    item.className = 'autocomplete-item';
                    item.innerHTML = `<span class="item-display">${escapeHtml(r.display)}</span><span class="item-code">${escapeHtml(r.code)}</span>`;
                    item.addEventListener('mousedown', (e) => {
                        e.preventDefault();
                        encInput.value = r.display;
                        encInput.dataset.code = r.code;
                        encInput.dataset.system = r.system;
                        encDropdown.classList.remove('visible');
                    });
                    encDropdown.appendChild(item);
                });
                if (results.length) encDropdown.classList.add('visible');
                else encDropdown.classList.remove('visible');
            } catch (e) { /* */ }
        }, 250);
    });

    encInput.addEventListener('blur', () => {
        setTimeout(() => encDropdown.classList.remove('visible'), 200);
    });

    // ── Collect Form Data ─────────────────────────────────────────────
    function collectFormData() {
        // Demographics
        const demographics = {
            patient_id: $('#patient-id').value.trim(),
            name: $('#patient-name').value.trim(),
            age: parseInt($('#patient-age').value) || null,
            gender: $('#patient-gender').value,
            phone: $('#patient-phone').value.trim(),
        };

        // Encounter
        const encounter = {
            class: $('#encounter-class').value.trim(),
            reason: $('#encounter-reason').value.trim(),
        };

        // Conditions
        const conditions = [];
        $$('#repeater-conditions .repeater-row').forEach(row => {
            const input = row.querySelector('.autocomplete-wrapper input');
            if (input && input.value.trim()) {
                conditions.push({
                    name: input.value.trim(),
                    code: input.dataset.code || '',
                    system: input.dataset.system || '',
                    display: input.dataset.display || input.value.trim(),
                });
            }
        });

        // Observations
        const observations = [];
        $$('#repeater-observations .repeater-row').forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (inputs[0] && inputs[0].value.trim()) {
                observations.push({
                    name: inputs[0].value.trim(),
                    value: inputs[1] ? inputs[1].value.trim() : '',
                    unit: inputs[2] ? inputs[2].value.trim() : '',
                    code: inputs[0].dataset.code || '',
                    system: inputs[0].dataset.system || '',
                    display: inputs[0].dataset.display || inputs[0].value.trim(),
                });
            }
        });

        // Allergies
        const allergies = [];
        $$('#repeater-allergies .repeater-row').forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (inputs[0] && inputs[0].value.trim()) {
                allergies.push({
                    substance: inputs[0].value.trim(),
                    reaction: inputs[1] ? inputs[1].value.trim() : '',
                    code: inputs[0].dataset.code || '',
                    system: inputs[0].dataset.system || '',
                    display: inputs[0].dataset.display || inputs[0].value.trim(),
                });
            }
        });

        // Medications
        const medications = [];
        $$('#repeater-medications .repeater-row').forEach(row => {
            const inputs = row.querySelectorAll('input');
            if (inputs[0] && inputs[0].value.trim()) {
                medications.push({
                    name: inputs[0].value.trim(),
                    dose: inputs[1] ? inputs[1].value.trim() : '',
                    frequency: inputs[2] ? inputs[2].value.trim() : '',
                    code: inputs[0].dataset.code || '',
                    system: inputs[0].dataset.system || '',
                    display: inputs[0].dataset.display || inputs[0].value.trim(),
                });
            }
        });

        // CarePlan
        const carePlan = [];
        $$('#repeater-careplan .repeater-row').forEach(row => {
            const input = row.querySelector('.autocomplete-wrapper input');
            if (input && input.value.trim()) {
                carePlan.push({
                    activity: input.value.trim(),
                    code: input.dataset.code || '',
                    system: input.dataset.system || '',
                    display: input.dataset.display || input.value.trim(),
                });
            }
        });

        return { demographics, encounter, conditions, observations, allergies, medications, carePlan };
    }

    // ── Generate FHIR Bundle ──────────────────────────────────────────
    btnGenerateBundle.addEventListener('click', async () => {
        const formData = collectFormData();

        if (!formData.demographics.name) {
            showToast('Please enter patient name before generating bundle.', 'error');
            return;
        }

        setStatus('Generating FHIR Bundle…', 'busy');
        btnGenerateBundle.disabled = true;

        try {
            const resp = await fetch(`${API}/api/fhir/bundle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const responseData = await resp.json();
            currentBundle = responseData.bundle;
            const savedPath = responseData.saved_path;
            const patientId = responseData.patient_id;

            // Stats
            const entries = currentBundle.entry || [];
            const resourceCounts = {};
            entries.forEach(e => {
                const rt = e.resource?.resourceType || 'Unknown';
                resourceCounts[rt] = (resourceCounts[rt] || 0) + 1;
            });

            let statsHtml = Object.entries(resourceCounts).map(
                ([k, v]) => `<span class="stat-chip"><strong>${v}</strong>${k}</span>`
            ).join('');

            // Show saved location info
            if (savedPath) {
                statsHtml += `<div class="save-info" style="margin-top: 8px; padding: 8px 12px; background: rgba(34,197,94,0.1); border-radius: 8px; font-size: 0.82rem; color: #22c55e; border: 1px solid rgba(34,197,94,0.2);">`;
                statsHtml += `<strong>💾 Saved to:</strong> FHIR_gt/${escapeHtml(patientId)}/`;
                statsHtml += `</div>`;
            }

            modalStats.innerHTML = statsHtml;

            // Render JSON
            jsonContent.innerHTML = highlightJSON(currentBundle);

            // Show modal
            modalOverlay.style.display = 'flex';
            setStatus('Ready');
            showToast(`FHIR Bundle generated with ${entries.length} resources! Saved to FHIR_gt/`, 'success');
        } catch (err) {
            console.error('Bundle generation failed:', err);
            setStatus('Error', 'error');
            showToast('Bundle generation failed: ' + err.message, 'error');
        } finally {
            btnGenerateBundle.disabled = false;
        }
    });

    // ── Modal Controls ────────────────────────────────────────────────
    btnCloseModal.addEventListener('click', () => { modalOverlay.style.display = 'none'; });
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) modalOverlay.style.display = 'none';
    });

    btnCopyBundle.addEventListener('click', () => {
        if (!currentBundle) return;
        navigator.clipboard.writeText(JSON.stringify(currentBundle, null, 2))
            .then(() => showToast('JSON copied to clipboard!', 'success'))
            .catch(() => showToast('Copy failed', 'error'));
    });

    btnDownloadBundle.addEventListener('click', () => {
        if (!currentBundle) return;
        const blob = new Blob([JSON.stringify(currentBundle, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `fhir-bundle-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('JSON file downloaded!', 'success');
    });

    // ── Clear Form ────────────────────────────────────────────────────
    btnClearForm.addEventListener('click', () => {
        $('#patient-id').value = '';
        $('#patient-name').value = '';
        $('#patient-age').value = '';
        $('#patient-gender').value = '';
        $('#patient-phone').value = '';
        $('#encounter-class').value = '';
        $('#encounter-reason').value = '';
        transcriptArea.value = '';

        ['conditions', 'observations', 'allergies', 'medications', 'careplan'].forEach(id => {
            $(`#repeater-${id}`).innerHTML = '';
        });

        updateInfoCounters();
        showToast('Form cleared.', 'info');
    });

    // ── Keyboard shortcut: Escape closes modal ───────────────────────
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modalOverlay.style.display === 'flex') {
            modalOverlay.style.display = 'none';
        }
    });

    // ── Initial state ─────────────────────────────────────────────────
    updateInfoCounters();
    console.log('FHIRBridge Clinical Workspace initialized.');

})();
