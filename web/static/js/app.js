/**
 * DrawMind3D - Main application logic.
 */

class DrawMindApp {
    constructor() {
        this.viewer3d = new Viewer3D('three-canvas');
        this.pdfViewer = new PDFViewer('pdf-canvas', 'annotation-overlay');
        this.annotationsPanel = new AnnotationsPanel('matches-tbody');
        this.jobId = null;
        this.data = null;

        this._bindEvents();

        // Make globally accessible for cross-component communication
        window.drawMindApp = this;
    }

    _bindEvents() {
        const form = document.getElementById('upload-form');
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this._handleUpload();
        });

        // Link table selection to viewers
        this.annotationsPanel.onSelect = (match) => {
            // Highlight in 3D viewer
            if (match.feature_id) {
                this.viewer3d.highlightFeature(match.feature_id);
            }
            // Navigate to correct PDF page and highlight annotation
            if (match.annotation_id) {
                const ann = this.data?.annotations?.find(a => a.id === match.annotation_id);
                if (ann && ann.bbox && this.pdfViewer.pdfDoc) {
                    const annPage = (ann.bbox.page || 0) + 1;
                    if (annPage !== this.pdfViewer.currentPage) {
                        this.pdfViewer.renderPage(annPage).then(() => {
                            this.pdfViewer.highlightAnnotation(match.annotation_id);
                        });
                    } else {
                        this.pdfViewer.highlightAnnotation(match.annotation_id);
                    }
                } else {
                    this.pdfViewer.highlightAnnotation(match.annotation_id);
                }
            }
        };
    }

    async _handleUpload() {
        const pdfInput = document.getElementById('pdf-file');
        const stepInput = document.getElementById('step-file');
        const useLlm = document.getElementById('use-llm').checked;
        const btn = document.getElementById('analyze-btn');
        const statusBar = document.getElementById('status-bar');
        const statusText = document.getElementById('status-text');

        if (!pdfInput.files[0] || !stepInput.files[0]) {
            alert('Please select both a PDF and a STEP file.');
            return;
        }

        // Show loading state
        btn.disabled = true;
        statusBar.classList.remove('hidden');
        statusText.textContent = 'Uploading files...';

        try {
            // Upload files
            const formData = new FormData();
            formData.append('pdf', pdfInput.files[0]);
            formData.append('step', stepInput.files[0]);

            const uploadResp = await fetch('/api/upload', {
                method: 'POST',
                body: formData,
            });
            const uploadData = await uploadResp.json();
            this.jobId = uploadData.job_id;

            // Run analysis
            statusText.textContent = 'Analyzing... (this may take a moment)';

            const analyzeResp = await fetch(
                `/api/analyze/${this.jobId}?use_llm=${useLlm}`,
                { method: 'POST' }
            );
            const analyzeData = await analyzeResp.json();

            if (analyzeData.status === 'complete') {
                statusText.textContent = 'Loading results...';
                await this._loadResults();
            } else {
                statusText.textContent = `Error: ${analyzeData.error || 'Unknown error'}`;
            }

        } catch (e) {
            console.error('Upload/analyze failed:', e);
            statusText.textContent = `Error: ${e.message}`;
        } finally {
            btn.disabled = false;
        }
    }

    async _loadResults() {
        const resp = await fetch(`/api/results/${this.jobId}`);
        this.data = await resp.json();

        // Update summary
        const summary = this.data.summary;
        document.getElementById('stat-annotations').textContent = summary.annotations_found;
        document.getElementById('stat-holes').textContent = summary.holes_found;
        document.getElementById('stat-matched').textContent = summary.matched;
        document.getElementById('stat-confidence').textContent =
            (summary.avg_confidence * 100).toFixed(0) + '%';

        // Show results section
        document.getElementById('results-section').classList.remove('hidden');
        document.getElementById('status-bar').classList.add('hidden');

        // Resize viewer now that section is visible
        this.viewer3d._onResize();

        // Load 3D model
        try {
            await this.viewer3d.loadModel(`/api/model/${this.jobId}`);
            this.viewer3d.addFeatureMarkers(this.data.holes, this.data.matches);
        } catch (e) {
            console.error('Failed to load 3D model:', e);
        }

        // Load PDF
        try {
            await this.pdfViewer.loadPDF(`/api/pdf/${this.jobId}`);
            this.pdfViewer.setAnnotations(this.data.annotations, this.data.matches);
        } catch (e) {
            console.error('Failed to load PDF:', e);
        }

        // Populate matches table
        this.annotationsPanel.setMatches(this.data.matches);
    }

    selectAnnotation(annotationId) {
        // Find match for this annotation
        const match = this.data?.matches?.find(m => m.annotation_id === annotationId);
        if (match) {
            this.annotationsPanel.selectMatch(match.id);
        }
    }
}

// Tab Navigation
function initTabs() {
    const navBtns = document.querySelectorAll('.header-nav .nav-btn');
    const analyzeEls = [
        document.getElementById('upload-section'),
        document.getElementById('results-section'),
    ];
    const evalSection = document.getElementById('evaluation-section');
    const testcasesSection = document.getElementById('testcases-section');

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            navBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            if (btn.dataset.tab === 'evaluation') {
                analyzeEls.forEach(el => el.style.display = 'none');
                testcasesSection.classList.add('hidden');
                evalSection.classList.remove('hidden');
                loadEvaluation();
            } else if (btn.dataset.tab === 'testcases') {
                analyzeEls.forEach(el => el.style.display = 'none');
                evalSection.classList.add('hidden');
                testcasesSection.classList.remove('hidden');
                loadTestCases();
            } else {
                evalSection.classList.add('hidden');
                testcasesSection.classList.add('hidden');
                analyzeEls.forEach(el => el.style.display = '');
            }
        });
    });

    // Eval mode toggle (LLM / no LLM)
    document.querySelectorAll('.eval-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.eval-mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const mode = btn.dataset.mode;
            updateEvalChart(mode, currentEvalFilter);
            renderEvalTable(mode, currentEvalFilter);
        });
    });

    // Eval data filter (All / CTC / FTC / Synthetic)
    document.querySelectorAll('.eval-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.eval-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentEvalFilter = btn.dataset.filter;
            const activeMode = document.querySelector('.eval-mode-btn.active')?.dataset.mode || 'llm';
            updateEvalChart(activeMode, currentEvalFilter);
            renderEvalTable(activeMode, currentEvalFilter);
        });
    });

    // Presentation chart filter (All / NIST / Synthetic)
    document.querySelectorAll('.pres-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.pres-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const suffix = btn.dataset.pfilter;
            document.querySelectorAll('.pres-chart').forEach(img => {
                img.src = `/api/evaluation/chart/${img.dataset.base}${suffix}.svg`;
            });
        });
    });
}

let evalData = null;
let currentEvalFilter = 'all';

async function loadEvaluation() {
    if (evalData) return;
    try {
        const resp = await fetch('/api/evaluation');
        evalData = await resp.json();
        renderEvalTable('llm', currentEvalFilter);
    } catch (e) {
        document.getElementById('eval-table-container').innerHTML =
            '<p style="color:#f87171">No evaluation data. Run: uv run python scripts/evaluate.py</p>';
    }
}

function updateEvalChart(mode, filter) {
    const chartSuffix = filter === 'all' ? '' : `_${filter}`;
    document.getElementById('eval-chart-main').src =
        `/api/evaluation/chart/evaluation_chart_${mode}${chartSuffix}.svg`;
}

function filterEvalData(data, filter) {
    if (filter === 'all') return data;
    if (filter === 'ctc') return data.filter(r => r.test_case.startsWith('CTC'));
    if (filter === 'ftc') return data.filter(r => r.test_case.startsWith('FTC'));
    if (filter === 'syn') return data.filter(r => r.test_case.startsWith('SYN'));
    return data;
}

function renderEvalTable(mode, filter = 'all') {
    const rawData = evalData?.[mode];
    if (!rawData) return;

    const data = filterEvalData(rawData, filter);
    const container = document.getElementById('eval-table-container');

    if (data.length === 0) {
        container.innerHTML = '<p style="color:#888; padding:16px 0;">No test cases match this filter.</p>';
        return;
    }

    let html = '<table><thead><tr><th>Test Case</th><th>Precision</th><th>Recall</th><th>F1</th><th>Linking</th><th>Confidence</th></tr></thead><tbody>';

    let totP = 0, totR = 0, totF = 0, totL = 0, totC = 0;
    for (const r of data) {
        const p = r.extraction.precision, rc = r.extraction.recall, f1 = r.extraction.f1;
        const link = r.linking.linking_accuracy, conf = r.avg_confidence;
        totP += p; totR += rc; totF += f1; totL += link; totC += conf;

        const f1Class = f1 >= 0.8 ? 'confidence-high' : f1 >= 0.5 ? 'confidence-mid' : 'confidence-low';
        const lClass = link >= 0.8 ? 'confidence-high' : link >= 0.5 ? 'confidence-mid' : 'confidence-low';
        let catClass;
        if (r.test_case.startsWith('CTC')) catClass = 'ctc';
        else if (r.test_case.startsWith('FTC')) catClass = 'ftc';
        else catClass = 'syn';

        html += `<tr>
            <td><a href="#" class="eval-tc-link" data-tc-id="${r.test_case}"><strong>${r.test_case}</strong></a>
                <span class="category-tag ${catClass}">${catClass}</span></td>
            <td>${(p*100).toFixed(1)}%</td>
            <td>${(rc*100).toFixed(1)}%</td>
            <td class="${f1Class}"><strong>${(f1*100).toFixed(1)}%</strong></td>
            <td class="${lClass}"><strong>${(link*100).toFixed(1)}%</strong></td>
            <td>${(conf*100).toFixed(1)}%</td>
        </tr>`;
    }

    const n = data.length;
    html += `<tr class="avg-row">
        <td><strong>Average</strong></td>
        <td><strong>${(totP/n*100).toFixed(1)}%</strong></td>
        <td><strong>${(totR/n*100).toFixed(1)}%</strong></td>
        <td><strong>${(totF/n*100).toFixed(1)}%</strong></td>
        <td><strong>${(totL/n*100).toFixed(1)}%</strong></td>
        <td><strong>${(totC/n*100).toFixed(1)}%</strong></td>
    </tr>`;

    html += '</tbody></table>';
    container.innerHTML = html;
}

// ---- Test Cases ----
let testCasesData = null;
let currentTcFilter = 'all';
let tcViewer3d = null;
let tcPdfViewer = null;
let currentTcId = null;

async function loadTestCases() {
    if (testCasesData) {
        renderTestCasesTable(currentTcFilter);
        return;
    }
    try {
        const resp = await fetch('/api/testcases');
        testCasesData = await resp.json();
        renderTestCasesTable(currentTcFilter);
    } catch (e) {
        document.getElementById('tc-table-container').innerHTML =
            '<p style="color:#f87171">Failed to load test cases.</p>';
    }
}

function filterTestCases(data, filter) {
    if (filter === 'all') return data;
    return data.filter(tc => tc.category.toLowerCase() === filter);
}

function renderTestCasesTable(filter) {
    const data = filterTestCases(testCasesData || [], filter);
    const container = document.getElementById('tc-table-container');

    if (!data.length) {
        container.innerHTML = '<p style="color:#888; padding:16px 0;">No test cases match this filter.</p>';
        return;
    }

    let html = '<table><thead><tr><th>Test Case</th><th>Category</th><th>PDF</th><th>STEP</th><th>F1 (LLM)</th><th>Linking</th><th></th></tr></thead><tbody>';

    for (const tc of data) {
        const evalLlm = tc.evaluation?.llm;
        const f1 = evalLlm ? (evalLlm.f1 * 100).toFixed(1) + '%' : '-';
        const link = evalLlm ? (evalLlm.linking_accuracy * 100).toFixed(1) + '%' : '-';
        const f1Class = evalLlm ? (evalLlm.f1 >= 0.8 ? 'confidence-high' : evalLlm.f1 >= 0.5 ? 'confidence-mid' : 'confidence-low') : '';
        const lClass = evalLlm ? (evalLlm.linking_accuracy >= 0.8 ? 'confidence-high' : evalLlm.linking_accuracy >= 0.5 ? 'confidence-mid' : 'confidence-low') : '';

        let catClass;
        if (tc.category === 'CTC') catClass = 'ctc';
        else if (tc.category === 'FTC') catClass = 'ftc';
        else if (tc.category === 'D2MI') catClass = 'ftc';
        else catClass = 'syn';

        html += `<tr class="tc-row" data-tc-id="${tc.id}">
            <td><strong>${tc.id}</strong></td>
            <td><span class="category-tag ${catClass}">${tc.category}</span></td>
            <td>${tc.has_pdf ? '&#10003;' : '&#10007;'}</td>
            <td>${tc.has_step ? '&#10003;' : '&#10007;'}</td>
            <td class="${f1Class}"><strong>${f1}</strong></td>
            <td class="${lClass}"><strong>${link}</strong></td>
            <td><button class="nav-btn" style="padding:4px 12px;font-size:0.75rem;" data-tc-id="${tc.id}">View</button></td>
        </tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html;

    container.querySelectorAll('.tc-row').forEach(row => {
        row.addEventListener('click', () => showTestCaseDetail(row.dataset.tcId));
    });
}

async function showTestCaseDetail(tcId) {
    const listView = document.getElementById('tc-list-view');
    const detailView = document.getElementById('tc-detail-view');

    const tc = (testCasesData || []).find(t => t.id === tcId);
    if (!tc) return;

    currentTcId = tcId;
    document.getElementById('tc-analysis-results').classList.add('hidden');
    document.getElementById('tc-analyze-status').classList.add('hidden');

    // Update header
    document.getElementById('tc-detail-title').textContent = tcId;
    let catTag;
    if (tc.category === 'CTC') catTag = '<span style="color:#f59e0b;">NIST CTC</span>';
    else if (tc.category === 'FTC') catTag = '<span style="color:#fb923c;">NIST FTC</span>';
    else if (tc.category === 'D2MI') catTag = '<span style="color:#38bdf8;">NIST D2MI</span>';
    else catTag = '<span style="color:#a78bfa;">Synthetic</span>';
    document.getElementById('tc-detail-category').innerHTML = catTag;

    // Switch views
    listView.classList.add('hidden');
    detailView.classList.remove('hidden');

    // Load PDF
    if (tc.has_pdf) {
        if (!tcPdfViewer) {
            tcPdfViewer = new PDFViewer('tc-pdf-canvas', 'tc-annotation-overlay');
            // Wire up page navigation buttons
            const tcPdfPanel = document.getElementById('tc-pdf-container').closest('.viewer-panel');
            const prevBtn = tcPdfPanel.querySelector('.pdf-prev-btn');
            const nextBtn = tcPdfPanel.querySelector('.pdf-next-btn');
            if (prevBtn) prevBtn.addEventListener('click', () => tcPdfViewer.prevPage());
            if (nextBtn) nextBtn.addEventListener('click', () => tcPdfViewer.nextPage());
        }
        try {
            await tcPdfViewer.loadPDF(`/api/testcases/${tcId}/pdf`);
        } catch (e) {
            console.error('Failed to load test case PDF:', e);
        }
    }

    // Load 3D model
    if (tc.has_step) {
        const loadingEl = document.getElementById('tc-model-loading');
        loadingEl.classList.remove('hidden');

        if (!tcViewer3d) {
            tcViewer3d = new Viewer3D('tc-three-canvas');
        } else {
            tcViewer3d.clearModel();
            tcViewer3d._onResize();
        }

        try {
            await tcViewer3d.loadModel(`/api/testcases/${tcId}/model`);
        } catch (e) {
            console.error('Failed to load test case model:', e);
        }
        loadingEl.classList.add('hidden');
    }

    // Render metrics
    renderDetailMetrics(tc);
}

function renderDetailMetrics(tc) {
    const container = document.getElementById('tc-metrics-content');
    const evalLlm = tc.evaluation?.llm;
    const evalNollm = tc.evaluation?.nollm;

    if (!evalLlm && !evalNollm) {
        container.innerHTML = '<p style="color:#888;">No evaluation data available.</p>';
        return;
    }

    let html = '<table><thead><tr><th>Mode</th><th>Precision</th><th>Recall</th><th>F1</th><th>Linking</th><th>Confidence</th></tr></thead><tbody>';

    for (const [label, data] of [['With LLM', evalLlm], ['Without LLM', evalNollm]]) {
        if (!data) continue;
        const f1Class = data.f1 >= 0.8 ? 'confidence-high' : data.f1 >= 0.5 ? 'confidence-mid' : 'confidence-low';
        const lClass = data.linking_accuracy >= 0.8 ? 'confidence-high' : data.linking_accuracy >= 0.5 ? 'confidence-mid' : 'confidence-low';
        html += `<tr>
            <td><strong>${label}</strong></td>
            <td>${(data.precision * 100).toFixed(1)}%</td>
            <td>${(data.recall * 100).toFixed(1)}%</td>
            <td class="${f1Class}"><strong>${(data.f1 * 100).toFixed(1)}%</strong></td>
            <td class="${lClass}"><strong>${(data.linking_accuracy * 100).toFixed(1)}%</strong></td>
            <td>${(data.avg_confidence * 100).toFixed(1)}%</td>
        </tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

async function analyzeTestCase(tcId) {
    const btn = document.getElementById('tc-analyze-btn');
    const statusBar = document.getElementById('tc-analyze-status');
    const statusText = document.getElementById('tc-analyze-text');
    const resultsDiv = document.getElementById('tc-analysis-results');
    const useLlm = document.getElementById('tc-use-llm').checked;

    btn.disabled = true;
    statusBar.classList.remove('hidden');
    resultsDiv.classList.add('hidden');
    statusText.textContent = 'Analyzing... (this may take 30-60 seconds with LLM)';

    try {
        const resp = await fetch(`/api/testcases/${tcId}/analyze?use_llm=${useLlm}`, {
            method: 'POST',
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `Server error ${resp.status}`);
        }
        const data = await resp.json();

        if (data.status === 'complete') {
            // Load full results
            const resultsResp = await fetch(`/api/results/${data.job_id}`);
            const results = await resultsResp.json();

            // Update summary stats
            const s = results.summary || data.summary;
            document.getElementById('tc-stat-annotations').textContent = s.annotations_found;
            document.getElementById('tc-stat-holes').textContent = s.holes_found;
            document.getElementById('tc-stat-matched').textContent = s.matched;
            document.getElementById('tc-stat-confidence').textContent =
                (s.avg_confidence * 100).toFixed(0) + '%';

            // Populate matches table
            const tbody = document.getElementById('tc-matches-tbody');
            const matches = results.matches || [];
            tbody.innerHTML = matches.map(m => {
                const confClass = m.confidence >= 0.8 ? 'confidence-high' :
                    m.confidence >= 0.6 ? 'confidence-mid' : 'confidence-low';
                const ref = m.feature_3d_ref || {};
                const diam = ref.primary_diameter_mm ? ref.primary_diameter_mm.toFixed(2) + 'mm' : '-';
                return `<tr>
                    <td title="${(m.annotation_text || '').replace(/"/g, '&quot;')}">${(m.annotation_text || '').substring(0, 30)}</td>
                    <td>${ref.hole_type || '-'}</td>
                    <td>\u00d8${diam}</td>
                    <td class="${confClass}"><strong>${(m.confidence * 100).toFixed(0)}%</strong></td>
                </tr>`;
            }).join('');

            if (!matches.length) {
                tbody.innerHTML = '<tr><td colspan="4" style="color:#888;">No matches found.</td></tr>';
            }

            // Update 3D viewer with match highlights
            if (tcViewer3d && results.holes && results.matches) {
                tcViewer3d.addFeatureMarkers(results.holes, results.matches);
            }

            // Update PDF viewer with annotation overlays
            if (tcPdfViewer && results.annotations && results.matches) {
                tcPdfViewer.setAnnotations(results.annotations, results.matches);
            }

            statusBar.classList.add('hidden');
            resultsDiv.classList.remove('hidden');
        } else {
            statusText.textContent = `Error: ${data.detail || data.error || 'Unknown error'}`;
        }
    } catch (e) {
        statusText.textContent = `Error: ${e.message}`;
    } finally {
        btn.disabled = false;
    }
}

function initTestCases() {
    // Back button
    document.getElementById('tc-back-btn').addEventListener('click', () => {
        document.getElementById('tc-detail-view').classList.add('hidden');
        document.getElementById('tc-list-view').classList.remove('hidden');
        document.getElementById('tc-analysis-results').classList.add('hidden');
        document.getElementById('tc-analyze-status').classList.add('hidden');
    });

    // Analyze button
    document.getElementById('tc-analyze-btn').addEventListener('click', () => {
        if (currentTcId) analyzeTestCase(currentTcId);
    });


    // Filter buttons
    document.querySelectorAll('.tc-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tc-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTcFilter = btn.dataset.filter;
            renderTestCasesTable(currentTcFilter);
        });
    });

    // Eval table -> test case detail navigation
    document.getElementById('eval-table-container').addEventListener('click', (e) => {
        const link = e.target.closest('.eval-tc-link');
        if (!link) return;
        e.preventDefault();
        const tcId = link.dataset.tcId;

        // Switch to Test Cases tab
        document.querySelectorAll('.header-nav .nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelector('.header-nav .nav-btn[data-tab="testcases"]').classList.add('active');

        document.getElementById('evaluation-section').classList.add('hidden');
        document.getElementById('upload-section').style.display = 'none';
        document.getElementById('results-section').style.display = 'none';
        document.getElementById('testcases-section').classList.remove('hidden');

        loadTestCases().then(() => showTestCaseDetail(tcId));
    });
}

// Navigate to test case detail from anywhere
function navigateToTestCase(tcId) {
    document.querySelectorAll('.header-nav .nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.header-nav .nav-btn[data-tab="testcases"]').classList.add('active');

    document.getElementById('evaluation-section').classList.add('hidden');
    document.getElementById('upload-section').style.display = 'none';
    document.getElementById('results-section').style.display = 'none';
    document.getElementById('testcases-section').classList.remove('hidden');

    loadTestCases().then(() => showTestCaseDetail(tcId));
}

// Lightbox for chart images
function initLightbox() {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');

    document.addEventListener('click', (e) => {
        const img = e.target.closest('#eval-charts img, .eval-gallery img');
        if (img) {
            lightboxImg.src = img.src;
            lightbox.classList.add('active');
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            lightbox.classList.remove('active');
        }
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new DrawMindApp();
    initTabs();
    initTestCases();
    initLightbox();
});
