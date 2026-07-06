/* ===================================================================
   FHIR Clinical Workspace – Application Logic
   Handles audio recording, custom player, speaker diarization display,
   transcription, NLP extraction, terminology autocomplete, form
   management, and FHIR bundle generation.
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

    // Custom player elements
    const audioPlayback = $('#audio-playback');
    const playbackContainer = $('#audio-playback-container');
    const playerPlayBtn = $('#player-play-btn');
    const playIcon = $('#play-icon');
    const pauseIcon = $('#pause-icon');
    const playerSlider = $('#player-slider');
    const playerTime = $('#player-time');
    const volumeBtn = $('#volume-btn');
    const volumeSlider = $('#volume-slider');

    // Diarization elements
    const diarizationTimeline = $('#diarization-timeline');
    const diarizationEmpty = $('#diarization-empty');
    const diarizationStats = $('#diarization-stats');
    const btnLangToggle = $('#btn-lang-toggle');
    const btnDownloadGT = $('#btn-download-gt');

    // ── State ─────────────────────────────────────────────────────────
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let timerInterval = null;
    let timerSeconds = 0;
    let currentBundle = null;
    let autocompleteTimeout = null;
    let currentUtterances = [];
    let showEnglishFirst = true;
    let isSeeking = false;

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

    function formatTimestamp(seconds) {
        const m = String(Math.floor(seconds / 60)).padStart(2, '0');
        const s = String(Math.floor(seconds % 60)).padStart(2, '0');
        const ms = String(Math.floor((seconds % 1) * 100)).padStart(2, '0');
        return `${m}:${s}.${ms}`;
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

    // ===================================================================
    //  CUSTOM AUDIO PLAYER
    // ===================================================================

    function initCustomPlayer(blob) {
        audioPlayback.src = URL.createObjectURL(blob);
        playbackContainer.style.display = 'block';

        // Reset state
        playerSlider.value = 0;
        playerTime.textContent = '00:00 / 00:00';
        playIcon.style.display = '';
        pauseIcon.style.display = 'none';
        playerPlayBtn.classList.remove('playing');
    }

    // Play/Pause
    playerPlayBtn.addEventListener('click', () => {
        if (audioPlayback.paused) {
            audioPlayback.play();
            playIcon.style.display = 'none';
            pauseIcon.style.display = '';
            playerPlayBtn.classList.add('playing');
        } else {
            audioPlayback.pause();
            playIcon.style.display = '';
            pauseIcon.style.display = 'none';
            playerPlayBtn.classList.remove('playing');
        }
    });

    // Time update → slider + time display + active utterance
    audioPlayback.addEventListener('timeupdate', () => {
        if (isSeeking) return;
        const dur = audioPlayback.duration || 0;
        const cur = audioPlayback.currentTime || 0;
        if (dur > 0) {
            playerSlider.value = (cur / dur) * 100;
            // Update slider gradient for progress
            const pct = (cur / dur) * 100;
            playerSlider.style.background = `linear-gradient(to right, var(--accent-indigo) 0%, var(--accent-violet) ${pct}%, rgba(255,255,255,0.1) ${pct}%)`;
        }
        playerTime.textContent = `${formatTime(Math.floor(cur))} / ${formatTime(Math.floor(dur))}`;
        updateActiveUtterance(cur);
    });

    // Slider seek
    playerSlider.addEventListener('input', () => {
        isSeeking = true;
        const dur = audioPlayback.duration || 0;
        const seekTime = (playerSlider.value / 100) * dur;
        audioPlayback.currentTime = seekTime;
        const pct = playerSlider.value;
        playerSlider.style.background = `linear-gradient(to right, var(--accent-indigo) 0%, var(--accent-violet) ${pct}%, rgba(255,255,255,0.1) ${pct}%)`;
    });

    playerSlider.addEventListener('change', () => {
        isSeeking = false;
    });

    // Audio ended
    audioPlayback.addEventListener('ended', () => {
        playIcon.style.display = '';
        pauseIcon.style.display = 'none';
        playerPlayBtn.classList.remove('playing');
    });

    // Loaded metadata
    audioPlayback.addEventListener('loadedmetadata', () => {
        playerTime.textContent = `00:00 / ${formatTime(Math.floor(audioPlayback.duration))}`;
    });

    // Volume
    volumeSlider.addEventListener('input', () => {
        audioPlayback.volume = parseFloat(volumeSlider.value);
    });

    volumeBtn.addEventListener('click', () => {
        if (audioPlayback.muted) {
            audioPlayback.muted = false;
            volumeSlider.value = audioPlayback.volume || 1;
        } else {
            audioPlayback.muted = true;
            volumeSlider.value = 0;
        }
    });

    // ===================================================================
    //  DIARIZATION TIMELINE
    // ===================================================================

    function renderDiarizedOutput(utterances) {
        currentUtterances = utterances || [];

        if (!currentUtterances.length) {
            diarizationTimeline.innerHTML = '';
            diarizationTimeline.appendChild(diarizationEmpty);
            diarizationEmpty.style.display = '';
            diarizationStats.style.display = 'none';
            return;
        }

        // Hide empty state
        diarizationEmpty.style.display = 'none';

        // Build unique speaker list for consistent color assignment
        const speakerIds = [];
        currentUtterances.forEach(u => {
            if (!speakerIds.includes(u.speaker_id)) speakerIds.push(u.speaker_id);
        });

        // Clear timeline
        diarizationTimeline.innerHTML = '';

        // Render each utterance row
        currentUtterances.forEach((u, idx) => {
            const speakerColorIdx = speakerIds.indexOf(u.speaker_id) % 5;
            const row = document.createElement('div');
            row.className = 'utterance-row';
            row.dataset.index = idx;
            row.dataset.start = u.start_time;
            row.dataset.end = u.end_time;

            const primaryText = showEnglishFirst ? u.translated_text : u.original_text;
            const secondaryText = showEnglishFirst ? u.original_text : u.translated_text;

            row.innerHTML = `
                <div class="utterance-speaker-bar speaker-bar-${speakerColorIdx}"></div>
                <div class="utterance-content">
                    <div class="utterance-header">
                        <span class="speaker-badge speaker-color-${speakerColorIdx}">${escapeHtml(u.speaker_role)}</span>
                        <span class="timestamp-badge">${formatTimestamp(u.start_time)} → ${formatTimestamp(u.end_time)}</span>
                    </div>
                    <div class="utterance-text-primary">${escapeHtml(primaryText || '—')}</div>
                    ${secondaryText ? `<div class="utterance-text-secondary">${escapeHtml(secondaryText)}</div>` : ''}
                </div>
                <span class="utterance-seek-icon">▶</span>
            `;

            // Click to seek
            row.addEventListener('click', () => {
                seekToTime(u.start_time);
            });

            diarizationTimeline.appendChild(row);
        });

        // Show stats
        const totalDuration = currentUtterances.length > 0
            ? currentUtterances[currentUtterances.length - 1].end_time
            : 0;

        diarizationStats.innerHTML = `
            <span class="diarization-stat"><strong>${currentUtterances.length}</strong>utterances</span>
            <span class="diarization-stat"><strong>${speakerIds.length}</strong>speakers</span>
            <span class="diarization-stat"><strong>${formatTime(Math.floor(totalDuration))}</strong>duration</span>
        `;
        diarizationStats.style.display = 'flex';
    }

    function seekToTime(startTime) {
        if (audioPlayback.src) {
            audioPlayback.currentTime = startTime;
            if (audioPlayback.paused) {
                audioPlayback.play();
                playIcon.style.display = 'none';
                pauseIcon.style.display = '';
                playerPlayBtn.classList.add('playing');
            }
        }
    }

    function updateActiveUtterance(currentTime) {
        const rows = diarizationTimeline.querySelectorAll('.utterance-row');
        let activeRow = null;

        rows.forEach(row => {
            const start = parseFloat(row.dataset.start);
            const end = parseFloat(row.dataset.end);
            if (currentTime >= start && currentTime <= end) {
                row.classList.add('active');
                activeRow = row;
            } else {
                row.classList.remove('active');
            }
        });

        // Auto-scroll to active row
        if (activeRow) {
            const container = diarizationTimeline;
            const rowTop = activeRow.offsetTop - container.offsetTop;
            const rowBottom = rowTop + activeRow.offsetHeight;
            const scrollTop = container.scrollTop;
            const containerHeight = container.clientHeight;

            if (rowTop < scrollTop || rowBottom > scrollTop + containerHeight) {
                container.scrollTo({
                    top: rowTop - containerHeight / 3,
                    behavior: 'smooth',
                });
            }
        }
    }

    // Language toggle
    btnLangToggle.addEventListener('click', () => {
        showEnglishFirst = !showEnglishFirst;
        btnLangToggle.textContent = showEnglishFirst ? 'English ↔ Original' : 'Original ↔ English';
        renderDiarizedOutput(currentUtterances);
    });

    // Download GT Format
    if (btnDownloadGT) {
        btnDownloadGT.addEventListener('click', () => {
            if (!currentUtterances || currentUtterances.length === 0) {
                showToast('No diarization output to download.', 'error');
                return;
            }
            
            let tsvContent = '';
            currentUtterances.forEach(u => {
                const fileId = u.utterance_id.split('_')[0] || 'audio';
                const start = Number(u.start_time).toFixed(3);
                const end = Number(u.end_time).toFixed(3);
                // GT typically uses original language text
                const text = u.original_text || u.translated_text || '';
                tsvContent += `${fileId}\t${u.utterance_id}\t${u.speaker_id}\t${u.speaker_role}\t${start}\t${end}\t${text}\n`;
            });
            
            const blob = new Blob([tsvContent], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const fileId = currentUtterances[0].utterance_id.split('_')[0] || 'audio';
            a.download = `${fileId}_GT.txt`;
            a.click();
            URL.revokeObjectURL(url);
            showToast('GT output downloaded!', 'success');
        });
    }

    // ===================================================================
    //  AUDIO RECORDING
    // ===================================================================

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

    // ===================================================================
    //  AUDIO UPLOAD & TRANSCRIPTION
    // ===================================================================

    audioUpload.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setStatus('Uploading audio…', 'busy');
        await uploadAudio(file, file.name);
        audioUpload.value = '';
    });

    async function uploadAudio(blob, filename) {
        try {
            // Init custom player
            initCustomPlayer(blob);

            // Show processing state in diarization timeline
            diarizationTimeline.innerHTML = `
                <div class="processing-overlay">
                    <div class="processing-spinner"></div>
                    <div class="processing-text">Processing audio on GPU…</div>
                    <div class="processing-subtext">Running Whisper transcription + pyannote diarization</div>
                </div>
            `;
            diarizationStats.style.display = 'none';

            const formData = new FormData();
            formData.append('file', blob, filename);

            // Pass language hint if user selected one
            const langSelect = document.getElementById('language-select');
            if (langSelect && langSelect.value) {
                formData.append('language', langSelect.value);
            }

            setStatus('Processing audio on GPU…', 'busy');

            const resp = await fetch(`${API}/api/audio/transcribe`, {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                let errorMsg = `HTTP ${resp.status}`;
                try {
                    const errData = await resp.json();
                    errorMsg = errData.detail || errorMsg;
                } catch(e) {}
                throw new Error(errorMsg);
            }

            const data = await resp.json();

            // Render diarized output
            if (data.diarized_output && data.diarized_output.length > 0) {
                renderDiarizedOutput(data.diarized_output);
            } else {
                renderDiarizedOutput([]);
            }

            // Show English transcript in the text area (for NLP / manual editing)
            transcriptArea.value = data.transcript;

            // Update language badge
            const langBadge = document.getElementById('detected-language');
            if (langBadge) {
                const langNames = { 'en': 'English', 'hi': 'Hindi' };
                langBadge.textContent = langNames[data.language] || data.language;
                langBadge.style.display = 'inline-block';
            }

            populateForm(data.extracted);
            setStatus('Ready');
            showToast('Diarization complete! Speaker segments extracted.', 'success');
        } catch (err) {
            console.error('Transcription failed:', err);
            setStatus('Error', 'error');
            showToast('Processing failed: ' + err.message, 'error');
            // Reset diarization area
            renderDiarizedOutput([]);
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

    // ===================================================================
    //  EXTRACT ENTITIES (Text)
    // ===================================================================

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

            // Render diarization if available
            if (data.diarized_output && data.diarized_output.length > 0) {
                renderDiarizedOutput(data.diarized_output);
            }

            populateForm(data.extracted);
            setStatus('Ready');
            showToast('Demo note loaded!', 'info');
        } catch (err) {
            console.error('Demo load failed:', err);
            setStatus('Error', 'error');
            showToast('Demo load failed: ' + err.message, 'error');
        }
    });

    // ===================================================================
    //  POPULATE FORM FROM EXTRACTED DATA
    // ===================================================================

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

    // ===================================================================
    //  REPEATER ROW BUILDERS
    // ===================================================================

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

    // ===================================================================
    //  COLLECT FORM DATA
    // ===================================================================

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

    // ===================================================================
    //  GENERATE FHIR BUNDLE
    // ===================================================================

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

    // ===================================================================
    //  MODAL CONTROLS
    // ===================================================================

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

    // ===================================================================
    //  CLEAR FORM
    // ===================================================================

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

        // Reset diarization
        renderDiarizedOutput([]);

        // Reset player
        playbackContainer.style.display = 'none';
        audioPlayback.src = '';

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
    console.log('FHIRBridge Clinical Workspace initialized (GPU diarization mode).');

})();
