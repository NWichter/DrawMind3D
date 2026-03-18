/**
 * DrawMind3D - Main application logic.
 */

// ---- Internationalization (i18n) ----
const I18N = {
  en: {
    // Nav
    nav_analyze: "Analyze",
    nav_evaluation: "Evaluation",
    nav_testcases: "Test Cases",
    subtitle: "PDF Drawing Annotations \u2194 3D CAD Features",
    // Upload section
    upload_title: "Upload Files",
    upload_desc:
      "Upload your own PDF + STEP files, or use the <strong>Test Cases</strong> tab to analyze built-in NIST and synthetic examples.",
    label_pdf: "Technical Drawing (PDF)",
    label_step: "3D Model (STEP/STP)",
    enable_llm: "Enable LLM Enhancement",
    btn_analyze: "Analyze",
    // Status messages
    uploading: "Uploading files...",
    starting_analysis: "Starting analysis...",
    loading_results: "Loading results...",
    processing: "Processing...",
    analyzing: "Analyzing...",
    converting_step: "Converting STEP to 3D view...",
    // Summary stats
    stat_annotations: "Annotations",
    stat_holes: "3D Holes",
    stat_matched: "Matched",
    stat_matches: "Matches",
    stat_confidence: "Avg Confidence",
    // Viewers
    viewer_3d_title:
      '3D Model <span style="color: #64748b; font-size: 0.65rem; font-weight: 400">(drag to rotate, scroll to zoom, right-click to pan)</span>',
    viewer_pdf_title: "Technical Drawing",
    viewer_pdf_title_full: "Technical Drawing (PDF)",
    // Tables
    matched_features: "Matched Features",
    th_annotation: "Annotation",
    th_type: "Type",
    th_3d_feature: "3D Feature",
    th_drawing_spec: "Drawing Spec",
    th_3d_actual: "3D Actual",
    th_confidence: "Confidence",
    // Evaluation
    eval_title: "Evaluation Results",
    eval_desc:
      "Tested on 21 cases: 5 NIST CTC, 6 NIST FTC, 5 NIST D2MI industrial cases, and 5 synthetic test cases with ground truth.",
    eval_metrics: "Evaluation Metrics",
    pres_charts: "Presentation Charts",
    // Test cases
    tc_title: "Test Cases",
    tc_desc:
      'Browse and analyze all 21 built-in test cases. Click a test case to preview the PDF and 3D model, then click <strong style="color: #22c55e">Analyze</strong> to run the full pipeline and see matched annotations.',
    tc_preview_hint:
      'Preview the PDF and 3D model below. Click <strong style="color: #22c55e">Analyze</strong> to run the pipeline &mdash; matched annotations and confidence scores will appear at the bottom.',
    btn_back: "&larr; Back",
    // Alerts
    alert_select_files: "Please select both a PDF and a STEP file.",
  },
  de: {
    nav_analyze: "Analyse",
    nav_evaluation: "Auswertung",
    nav_testcases: "Testf\u00e4lle",
    subtitle: "PDF-Zeichnungsannotationen \u2194 3D-CAD-Merkmale",
    upload_title: "Dateien hochladen",
    upload_desc:
      "Laden Sie Ihre eigenen PDF- und STEP-Dateien hoch oder nutzen Sie den Reiter <strong>Testf\u00e4lle</strong>, um integrierte NIST- und synthetische Beispiele zu analysieren.",
    label_pdf: "Technische Zeichnung (PDF)",
    label_step: "3D-Modell (STEP/STP)",
    enable_llm: "LLM-Unterst\u00fctzung aktivieren",
    btn_analyze: "Analysieren",
    uploading: "Dateien werden hochgeladen...",
    starting_analysis: "Analyse wird gestartet...",
    loading_results: "Ergebnisse werden geladen...",
    processing: "Verarbeitung...",
    analyzing: "Wird analysiert...",
    converting_step: "STEP wird in 3D-Ansicht konvertiert...",
    stat_annotations: "Annotationen",
    stat_holes: "3D-Bohrungen",
    stat_matched: "Zugeordnet",
    stat_matches: "Zuordnungen",
    stat_confidence: "\u00d8 Konfidenz",
    viewer_3d_title:
      '3D-Modell <span style="color: #64748b; font-size: 0.65rem; font-weight: 400">(Ziehen zum Drehen, Scrollen zum Zoomen, Rechtsklick zum Verschieben)</span>',
    viewer_pdf_title: "Technische Zeichnung",
    viewer_pdf_title_full: "Technische Zeichnung (PDF)",
    matched_features: "Zugeordnete Merkmale",
    th_annotation: "Annotation",
    th_type: "Typ",
    th_3d_feature: "3D-Merkmal",
    th_drawing_spec: "Zeichnungs-Soll",
    th_3d_actual: "3D-Ist",
    th_confidence: "Konfidenz",
    eval_title: "Auswertungsergebnisse",
    eval_desc:
      "Getestet an 21 F\u00e4llen: 5 NIST CTC, 6 NIST FTC, 5 NIST D2MI Industrief\u00e4lle und 5 synthetische Testf\u00e4lle mit Ground Truth.",
    eval_metrics: "Evaluierungsmetriken",
    pres_charts: "Pr\u00e4sentationsdiagramme",
    tc_title: "Testf\u00e4lle",
    tc_desc:
      'Durchsuchen und analysieren Sie alle 21 integrierten Testf\u00e4lle. Klicken Sie auf einen Testfall, um PDF und 3D-Modell anzuzeigen, dann klicken Sie auf <strong style="color: #22c55e">Analysieren</strong>, um die vollst\u00e4ndige Pipeline auszuf\u00fchren.',
    tc_preview_hint:
      'Vorschau von PDF und 3D-Modell unten. Klicken Sie auf <strong style="color: #22c55e">Analysieren</strong>, um die Pipeline auszuf\u00fchren &mdash; zugeordnete Annotationen und Konfidenzwerte erscheinen unten.',
    btn_back: "&larr; Zur\u00fcck",
    alert_select_files:
      "Bitte w\u00e4hlen Sie sowohl eine PDF- als auch eine STEP-Datei aus.",
  },
};

let currentLang = localStorage.getItem("drawmind3d-lang") || "en";

function t(key) {
  return (I18N[currentLang] && I18N[currentLang][key]) || I18N.en[key] || key;
}

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("drawmind3d-lang", lang);

  // Update toggle buttons
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === lang);
  });

  // Update all data-i18n elements (textContent)
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    const val = t(key);
    if (val) el.textContent = val;
  });

  // Update all data-i18n-html elements (innerHTML — for strings with HTML tags)
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    const val = t(key);
    if (val) el.innerHTML = val;
  });

  // Update html lang attribute
  document.documentElement.lang = lang;
}

function initLanguageToggle() {
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyLanguage(btn.dataset.lang);
    });
  });
  // Apply saved language on init
  applyLanguage(currentLang);
}

class DrawMindApp {
  constructor() {
    this.viewer3d = new Viewer3D("three-canvas");
    this.pdfViewer = new PDFViewer("pdf-canvas", "annotation-overlay");
    this.annotationsPanel = new AnnotationsPanel("matches-tbody");
    this.jobId = null;
    this.data = null;

    this._bindEvents();

    // Make globally accessible for cross-component communication
    window.drawMindApp = this;
  }

  _bindEvents() {
    const form = document.getElementById("upload-form");
    form.addEventListener("submit", (e) => {
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
        const ann = this.data?.annotations?.find(
          (a) => a.id === match.annotation_id,
        );
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

  _updateProgress(statusText, statusStep, progressFill, data) {
    if (data.progress) {
      const p = data.progress;
      statusText.textContent = p.message;
      if (p.total > 0) {
        statusStep.textContent = `Step ${p.step}/${p.total}`;
      }
      progressFill.style.width = p.percent + "%";
    }
  }

  async _pollStatus(jobId, statusText, statusStep, progressFill) {
    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const resp = await fetch(`/api/status/${jobId}`);
          const data = await resp.json();
          this._updateProgress(statusText, statusStep, progressFill, data);

          if (data.status === "complete") {
            resolve(data);
          } else if (data.status === "error") {
            reject(new Error(data.error || "Analysis failed"));
          } else {
            setTimeout(poll, 500);
          }
        } catch (e) {
          reject(e);
        }
      };
      setTimeout(poll, 300);
    });
  }

  async _handleUpload() {
    const pdfInput = document.getElementById("pdf-file");
    const stepInput = document.getElementById("step-file");
    const useLlm = document.getElementById("use-llm").checked;
    const btn = document.getElementById("analyze-btn");
    const statusBar = document.getElementById("status-bar");
    const statusText = document.getElementById("status-text");
    const statusStep = document.getElementById("status-step");
    const progressFill = document.getElementById("progress-fill");

    if (!pdfInput.files[0] || !stepInput.files[0]) {
      alert(t("alert_select_files"));
      return;
    }

    // Show loading state
    btn.disabled = true;
    statusBar.classList.remove("hidden");
    statusText.textContent = t("uploading");
    statusStep.textContent = "";
    progressFill.style.width = "0%";

    try {
      // Upload files
      const formData = new FormData();
      formData.append("pdf", pdfInput.files[0]);
      formData.append("step", stepInput.files[0]);

      const uploadResp = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const uploadData = await uploadResp.json();
      this.jobId = uploadData.job_id;

      // Start analysis (returns immediately)
      statusText.textContent = t("starting_analysis");
      progressFill.style.width = "2%";

      await fetch(`/api/analyze/${this.jobId}?use_llm=${useLlm}`, {
        method: "POST",
      });

      // Poll for progress
      await this._pollStatus(this.jobId, statusText, statusStep, progressFill);

      statusText.textContent = t("loading_results");
      progressFill.style.width = "100%";
      await this._loadResults();
    } catch (e) {
      console.error("Upload/analyze failed:", e);
      statusText.textContent = `Error: ${e.message}`;
      progressFill.style.width = "0%";
    } finally {
      btn.disabled = false;
    }
  }

  async _loadResults() {
    const resp = await fetch(`/api/results/${this.jobId}`);
    this.data = await resp.json();

    // Update summary
    const summary = this.data.summary;
    document.getElementById("stat-annotations").textContent =
      summary.annotations_found;
    document.getElementById("stat-holes").textContent = summary.holes_found;
    document.getElementById("stat-matched").textContent = summary.matched;
    document.getElementById("stat-confidence").textContent =
      (summary.avg_confidence * 100).toFixed(0) + "%";

    // Update LLM mode badge
    const useLlm = document.getElementById("use-llm").checked;
    const llmBadge = document.getElementById("llm-mode-badge");
    if (llmBadge) {
      llmBadge.textContent = useLlm ? "LLM Enhanced" : "Without LLM";
      llmBadge.className =
        "llm-badge " + (useLlm ? "llm-badge-on" : "llm-badge-off");
    }

    // Show results section
    document.getElementById("results-section").classList.remove("hidden");
    document.getElementById("status-bar").classList.add("hidden");

    // Resize viewer now that section is visible
    this.viewer3d._onResize();

    // Load 3D model
    try {
      await this.viewer3d.loadModel(`/api/model/${this.jobId}`);
      this.viewer3d.addFeatureMarkers(this.data.holes, this.data.matches);
    } catch (e) {
      console.error("Failed to load 3D model:", e);
    }

    // Load PDF
    try {
      await this.pdfViewer.loadPDF(`/api/pdf/${this.jobId}`);
      this.pdfViewer.setAnnotations(this.data.annotations, this.data.matches);
    } catch (e) {
      console.error("Failed to load PDF:", e);
    }

    // Populate matches table
    this.annotationsPanel.setMatches(this.data.matches);

    // Scroll to results
    requestAnimationFrame(() => {
      document
        .getElementById("results-section")
        .scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  selectAnnotation(annotationId) {
    // Find match for this annotation
    const match = this.data?.matches?.find(
      (m) => m.annotation_id === annotationId,
    );
    if (match) {
      this.annotationsPanel.selectMatch(match.id);
    }
  }
}

// Tab Navigation
function initTabs() {
  const navBtns = document.querySelectorAll(".header-nav .nav-btn");
  const analyzeEls = [
    document.getElementById("upload-section"),
    document.getElementById("results-section"),
  ];
  const evalSection = document.getElementById("evaluation-section");
  const testcasesSection = document.getElementById("testcases-section");

  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      navBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      if (btn.dataset.tab === "evaluation") {
        analyzeEls.forEach((el) => (el.style.display = "none"));
        testcasesSection.classList.add("hidden");
        evalSection.classList.remove("hidden");
        loadEvaluation();
      } else if (btn.dataset.tab === "testcases") {
        analyzeEls.forEach((el) => (el.style.display = "none"));
        evalSection.classList.add("hidden");
        testcasesSection.classList.remove("hidden");
        loadTestCases();
      } else {
        evalSection.classList.add("hidden");
        testcasesSection.classList.add("hidden");
        analyzeEls.forEach((el) => (el.style.display = ""));
      }
    });
  });

  // Eval mode toggle (LLM / no LLM)
  document.querySelectorAll(".eval-mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".eval-mode-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.mode;
      updateEvalChart(mode, currentEvalFilter);
      renderEvalTable(mode, currentEvalFilter);
    });
  });

  // Eval data filter (All / CTC / FTC / Synthetic)
  document.querySelectorAll(".eval-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".eval-filter-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentEvalFilter = btn.dataset.filter;
      const activeMode =
        document.querySelector(".eval-mode-btn.active")?.dataset.mode || "llm";
      updateEvalChart(activeMode, currentEvalFilter);
      renderEvalTable(activeMode, currentEvalFilter);
    });
  });

  // Presentation chart filter (All / NIST / Synthetic)
  document.querySelectorAll(".pres-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".pres-filter-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const suffix = btn.dataset.pfilter;
      document.querySelectorAll(".pres-chart").forEach((img) => {
        img.src = `/api/evaluation/chart/${img.dataset.base}${suffix}.svg`;
      });
    });
  });
}

let evalData = null;
let currentEvalFilter = "all";

async function loadEvaluation() {
  if (evalData) return;
  try {
    const resp = await fetch("/api/evaluation");
    evalData = await resp.json();
    renderEvalTable("llm", currentEvalFilter);
  } catch (e) {
    document.getElementById("eval-table-container").innerHTML =
      '<p style="color:#f87171">No evaluation data. Run: uv run python scripts/evaluate.py</p>';
  }
}

function updateEvalChart(mode, filter) {
  const chartSuffix = filter === "all" ? "" : `_${filter}`;
  const chartImg = document.getElementById("eval-chart-main");
  const newSrc = `/api/evaluation/chart/evaluation_chart_${mode}${chartSuffix}.svg`;
  chartImg.onerror = () => {
    chartImg.style.display = "none";
  };
  chartImg.onload = () => {
    chartImg.style.display = "";
  };
  chartImg.src = newSrc;
}

function filterEvalData(data, filter) {
  if (filter === "all") return data;
  if (filter === "ctc")
    return data.filter((r) => r.test_case.startsWith("CTC"));
  if (filter === "ftc")
    return data.filter((r) => r.test_case.startsWith("FTC"));
  if (filter === "d2mi")
    return data.filter((r) => r.test_case.startsWith("D2MI"));
  if (filter === "syn")
    return data.filter((r) => r.test_case.startsWith("SYN"));
  return data;
}

function renderEvalTable(mode, filter = "all") {
  const rawData = evalData?.[mode];
  if (!rawData) return;

  const data = filterEvalData(rawData, filter);
  const container = document.getElementById("eval-table-container");

  if (data.length === 0) {
    container.innerHTML =
      '<p style="color:#888; padding:16px 0;">No test cases match this filter.</p>';
    return;
  }

  let html = `<table><thead><tr>
        <th>Test Case</th>
        <th>Precision<span class="metric-hint">Avoids false positives</span></th>
        <th>Recall<span class="metric-hint">Catches most annotations</span></th>
        <th>F1<span class="metric-hint">Balanced accuracy metric</span></th>
        <th>Linking<span class="metric-hint">Correct 3D-to-annotation matching</span></th>
        <th>Confidence</th>
    </tr></thead><tbody>`;

  let totP = 0,
    totR = 0,
    totF = 0,
    totL = 0,
    totC = 0;
  for (const r of data) {
    const p = r.extraction.precision,
      rc = r.extraction.recall,
      f1 = r.extraction.f1;
    const link = r.linking.linking_accuracy,
      conf = r.avg_confidence;
    totP += p;
    totR += rc;
    totF += f1;
    totL += link;
    totC += conf;

    const f1Class =
      f1 >= 0.8
        ? "confidence-high"
        : f1 >= 0.5
          ? "confidence-mid"
          : "confidence-low";
    const lClass =
      link >= 0.8
        ? "confidence-high"
        : link >= 0.5
          ? "confidence-mid"
          : "confidence-low";
    const confClass =
      conf >= 0.8
        ? "confidence-high"
        : conf >= 0.6
          ? "confidence-mid"
          : "confidence-low";
    let catClass;
    if (r.test_case.startsWith("CTC")) catClass = "ctc";
    else if (r.test_case.startsWith("FTC")) catClass = "ftc";
    else catClass = "syn";

    const isDemo = DEMO_TEST_CASES.includes(r.test_case);
    const demoBadge = isDemo ? '<span class="demo-badge">Demo</span>' : "";
    html += `<tr>
            <td><a href="#" class="eval-tc-link" data-tc-id="${r.test_case}"><strong>${r.test_case}</strong></a>
                <span class="category-tag ${catClass}">${catClass}</span>${demoBadge}</td>
            <td>${(p * 100).toFixed(1)}%</td>
            <td>${(rc * 100).toFixed(1)}%</td>
            <td class="${f1Class}"><strong>${(f1 * 100).toFixed(1)}%</strong></td>
            <td class="${lClass}"><strong>${(link * 100).toFixed(1)}%</strong></td>
            <td class="${confClass}"><strong>${(conf * 100).toFixed(1)}%</strong></td>
        </tr>`;
  }

  const n = data.length;
  html += `<tr class="avg-row">
        <td><strong>Average</strong></td>
        <td><strong>${((totP / n) * 100).toFixed(1)}%</strong></td>
        <td><strong>${((totR / n) * 100).toFixed(1)}%</strong></td>
        <td><strong>${((totF / n) * 100).toFixed(1)}%</strong></td>
        <td><strong>${((totL / n) * 100).toFixed(1)}%</strong></td>
        <td><strong>${((totC / n) * 100).toFixed(1)}%</strong></td>
    </tr>`;

  html += "</tbody></table>";
  container.innerHTML = html;
}

// ---- Test Cases ----
let testCasesData = null;
let currentTcFilter = "all";
let tcViewer3d = null;
let tcPdfViewer = null;
let currentTcId = null;
let tcAnalysisData = null;

// Helper functions for test case matches rendering
function _inferMatchType(match) {
  const text = match.annotation_text || "";
  if (text.match(/^M\d/i)) return "Thread";
  if (text.match(/[⌀Øø∅]/)) return "Diameter";
  if (text.match(/depth|tiefe/i)) return "Depth";
  if (text.match(/thru/i)) return "Through";
  return "Dimension";
}

function _escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadTestCases() {
  if (testCasesData) {
    renderTestCasesTable(currentTcFilter);
    return;
  }
  try {
    const resp = await fetch("/api/testcases");
    testCasesData = await resp.json();
    renderTestCasesTable(currentTcFilter);
  } catch (e) {
    document.getElementById("tc-table-container").innerHTML =
      '<p style="color:#f87171">Failed to load test cases.</p>';
  }
}

function filterTestCases(data, filter) {
  if (filter === "all") return data;
  return data.filter((tc) => tc.category.toLowerCase() === filter);
}

const DEMO_TEST_CASES = ["SYN-05-ManyHoles", "FTC-07", "FTC-09"];

function renderTestCasesTable(filter) {
  const data = filterTestCases(testCasesData || [], filter);
  const container = document.getElementById("tc-table-container");

  if (!data.length) {
    container.innerHTML =
      '<p style="color:#888; padding:16px 0;">No test cases match this filter.</p>';
    return;
  }

  let html =
    "<table><thead><tr><th>Test Case</th><th>Category</th><th>PDF</th><th>STEP</th><th>F1 (LLM)</th><th>Linking</th><th></th></tr></thead><tbody>";

  for (const tc of data) {
    const evalLlm = tc.evaluation?.llm;
    const f1 = evalLlm ? (evalLlm.f1 * 100).toFixed(1) + "%" : "-";
    const link = evalLlm
      ? (evalLlm.linking_accuracy * 100).toFixed(1) + "%"
      : "-";
    const f1Class = evalLlm
      ? evalLlm.f1 >= 0.8
        ? "confidence-high"
        : evalLlm.f1 >= 0.5
          ? "confidence-mid"
          : "confidence-low"
      : "";
    const lClass = evalLlm
      ? evalLlm.linking_accuracy >= 0.8
        ? "confidence-high"
        : evalLlm.linking_accuracy >= 0.5
          ? "confidence-mid"
          : "confidence-low"
      : "";

    let catClass;
    if (tc.category === "CTC") catClass = "ctc";
    else if (tc.category === "FTC") catClass = "ftc";
    else if (tc.category === "D2MI") catClass = "ftc";
    else catClass = "syn";

    const isDemo = DEMO_TEST_CASES.includes(tc.id);
    const demoBadge = isDemo ? '<span class="demo-badge">Demo</span>' : "";

    html += `<tr class="tc-row" data-tc-id="${tc.id}">
            <td><strong>${tc.id}</strong>${demoBadge}</td>
            <td><span class="category-tag ${catClass}">${tc.category}</span></td>
            <td>${tc.has_pdf ? "&#10003;" : "&#10007;"}</td>
            <td>${tc.has_step ? "&#10003;" : "&#10007;"}</td>
            <td class="${f1Class}"><strong>${f1}</strong></td>
            <td class="${lClass}"><strong>${link}</strong></td>
            <td><button class="nav-btn" style="padding:4px 12px;font-size:0.75rem;" data-tc-id="${tc.id}">View</button></td>
        </tr>`;
  }

  html += "</tbody></table>";
  container.innerHTML = html;

  container.querySelectorAll(".tc-row").forEach((row) => {
    row.addEventListener("click", () => showTestCaseDetail(row.dataset.tcId));
  });
}

async function showTestCaseDetail(tcId) {
  const listView = document.getElementById("tc-list-view");
  const detailView = document.getElementById("tc-detail-view");

  const tc = (testCasesData || []).find((t) => t.id === tcId);
  if (!tc) return;

  currentTcId = tcId;
  document.getElementById("tc-analysis-results").classList.add("hidden");
  document.getElementById("tc-analyze-status").classList.add("hidden");

  // Update header
  document.getElementById("tc-detail-title").textContent = tcId;
  let catTag;
  if (tc.category === "CTC")
    catTag = '<span style="color:#f59e0b;">NIST CTC</span>';
  else if (tc.category === "FTC")
    catTag = '<span style="color:#fb923c;">NIST FTC</span>';
  else if (tc.category === "D2MI")
    catTag = '<span style="color:#38bdf8;">NIST D2MI</span>';
  else catTag = '<span style="color:#a78bfa;">Synthetic</span>';
  document.getElementById("tc-detail-category").innerHTML = catTag;

  // Switch views
  listView.classList.add("hidden");
  detailView.classList.remove("hidden");

  // Load PDF
  if (tc.has_pdf) {
    if (!tcPdfViewer) {
      tcPdfViewer = new PDFViewer("tc-pdf-canvas", "tc-annotation-overlay");
      // Wire up page navigation buttons
      const tcPdfPanel = document
        .getElementById("tc-pdf-container")
        .closest(".viewer-panel");
      const prevBtn = tcPdfPanel.querySelector(".pdf-prev-btn");
      const nextBtn = tcPdfPanel.querySelector(".pdf-next-btn");
      if (prevBtn)
        prevBtn.addEventListener("click", () => tcPdfViewer.prevPage());
      if (nextBtn)
        nextBtn.addEventListener("click", () => tcPdfViewer.nextPage());
    }
    try {
      await tcPdfViewer.loadPDF(`/api/testcases/${tcId}/pdf`);
    } catch (e) {
      console.error("Failed to load test case PDF:", e);
    }
  }

  // Load 3D model
  if (tc.has_step) {
    const loadingEl = document.getElementById("tc-model-loading");
    loadingEl.classList.remove("hidden");

    if (!tcViewer3d) {
      tcViewer3d = new Viewer3D("tc-three-canvas");
    } else {
      tcViewer3d.clearModel();
      tcViewer3d._onResize();
    }

    try {
      await tcViewer3d.loadModel(`/api/testcases/${tcId}/model`);
    } catch (e) {
      console.error("Failed to load test case model:", e);
    }
    loadingEl.classList.add("hidden");
  }

  // Render metrics
  renderDetailMetrics(tc);
}

function renderDetailMetrics(tc) {
  const container = document.getElementById("tc-metrics-content");
  const evalLlm = tc.evaluation?.llm;
  const evalNollm = tc.evaluation?.nollm;

  if (!evalLlm && !evalNollm) {
    container.innerHTML =
      '<p style="color:#888;">No evaluation data available.</p>';
    return;
  }

  let html = `<table><thead><tr>
        <th>Mode</th>
        <th>Precision<span class="metric-hint">Avoids false positives</span></th>
        <th>Recall<span class="metric-hint">Catches most annotations</span></th>
        <th>F1<span class="metric-hint">Balanced accuracy metric</span></th>
        <th>Linking<span class="metric-hint">Correct 3D-to-annotation matching</span></th>
        <th>Confidence</th>
    </tr></thead><tbody>`;

  for (const [label, data] of [
    ["With LLM", evalLlm],
    ["Without LLM", evalNollm],
  ]) {
    if (!data) continue;
    const f1Class =
      data.f1 >= 0.8
        ? "confidence-high"
        : data.f1 >= 0.5
          ? "confidence-mid"
          : "confidence-low";
    const lClass =
      data.linking_accuracy >= 0.8
        ? "confidence-high"
        : data.linking_accuracy >= 0.5
          ? "confidence-mid"
          : "confidence-low";
    const cClass =
      data.avg_confidence >= 0.8
        ? "confidence-high"
        : data.avg_confidence >= 0.6
          ? "confidence-mid"
          : "confidence-low";
    const pClass =
      data.precision >= 0.8
        ? "confidence-high"
        : data.precision >= 0.6
          ? "confidence-mid"
          : "confidence-low";
    const rClass =
      data.recall >= 0.8
        ? "confidence-high"
        : data.recall >= 0.6
          ? "confidence-mid"
          : "confidence-low";
    html += `<tr>
            <td><strong>${label}</strong></td>
            <td class="${pClass}"><strong>${(data.precision * 100).toFixed(1)}%</strong></td>
            <td class="${rClass}"><strong>${(data.recall * 100).toFixed(1)}%</strong></td>
            <td class="${f1Class}"><strong>${(data.f1 * 100).toFixed(1)}%</strong></td>
            <td class="${lClass}"><strong>${(data.linking_accuracy * 100).toFixed(1)}%</strong></td>
            <td class="${cClass}"><strong>${(data.avg_confidence * 100).toFixed(1)}%</strong></td>
        </tr>`;
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

async function analyzeTestCase(tcId) {
  const btn = document.getElementById("tc-analyze-btn");
  const statusBar = document.getElementById("tc-analyze-status");
  const statusText = document.getElementById("tc-analyze-text");
  const statusStep = document.getElementById("tc-status-step");
  const progressFill = document.getElementById("tc-progress-fill");
  const resultsDiv = document.getElementById("tc-analysis-results");
  const useLlm = document.getElementById("tc-use-llm").checked;

  btn.disabled = true;
  statusBar.classList.remove("hidden");
  resultsDiv.classList.add("hidden");
  statusText.textContent = t("starting_analysis");
  statusStep.textContent = "";
  progressFill.style.width = "0%";

  try {
    const resp = await fetch(
      `/api/testcases/${tcId}/analyze?use_llm=${useLlm}`,
      {
        method: "POST",
      },
    );
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${resp.status}`);
    }
    const data = await resp.json();

    // Poll for progress until complete
    const jobId = data.job_id;
    await window.drawMindApp._pollStatus(
      jobId,
      statusText,
      statusStep,
      progressFill,
    );

    {
      // Load full results
      const resultsResp = await fetch(`/api/results/${jobId}`);
      const results = await resultsResp.json();

      // Update LLM badge
      const tcLlmBadge = document.getElementById("tc-llm-mode-badge");
      if (tcLlmBadge) {
        tcLlmBadge.textContent = useLlm ? "LLM Enhanced" : "Without LLM";
        tcLlmBadge.className =
          "llm-badge " + (useLlm ? "llm-badge-on" : "llm-badge-off");
      }

      // Update summary stats
      const s = results.summary || data.summary;
      document.getElementById("tc-stat-annotations").textContent =
        s.annotations_found;
      document.getElementById("tc-stat-holes").textContent = s.holes_found;
      document.getElementById("tc-stat-matched").textContent = s.matched;
      document.getElementById("tc-stat-confidence").textContent =
        (s.avg_confidence * 100).toFixed(0) + "%";

      // Populate matches table (rich format like Analyze tab)
      const tbody = document.getElementById("tc-matches-tbody");
      const matches = results.matches || [];
      tcAnalysisData = results;

      tbody.innerHTML = matches
        .map((m, index) => {
          const confClass =
            m.confidence >= 0.8
              ? "confidence-high"
              : m.confidence >= 0.5
                ? "confidence-mid"
                : "confidence-low";
          const color = MATCH_PALETTE[index % MATCH_PALETTE.length];

          // Type inference
          const type =
            m.parsed_interpretation?.thread_type ||
            m.parsed_interpretation?.type ||
            _inferMatchType(m);

          // Drawing spec
          const parsed = m.parsed_interpretation || {};
          const annDia = parsed.value || parsed.nominal_diameter;
          const drawSpec = annDia
            ? `\u00d8${annDia.toFixed(2)}`
            : _escapeHtml((m.annotation_text || "").substring(0, 15));

          // 3D actual
          const feat = m.feature_3d_ref || {};
          const featDia = feat.primary_diameter_mm;
          const featDepth = feat.total_depth_mm;
          let actualSpec = featDia ? `\u00d8${featDia.toFixed(2)}` : "-";
          if (featDepth) actualSpec += ` \u00d7 ${featDepth.toFixed(1)}`;

          // Scoring breakdown tooltip
          const bd = m.scoring_breakdown;
          const tooltip = bd
            ? Object.entries(bd)
                .map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`)
                .join(" | ")
            : "";

          return `<tr data-match-index="${index}" data-annotation-id="${m.annotation_id || ""}" data-feature-id="${m.feature_id || ""}">
                    <td><span class="match-color-dot" style="background:${color}"></span> ${index + 1}</td>
                    <td><code>${_escapeHtml(m.annotation_text || "")}</code></td>
                    <td>${type}</td>
                    <td>${m.feature_id || "-"}</td>
                    <td>${drawSpec}</td>
                    <td>${actualSpec}</td>
                    <td class="${confClass}" title="${tooltip}"><strong>${(m.confidence * 100).toFixed(0)}%</strong></td>
                </tr>`;
        })
        .join("");

      if (!matches.length) {
        tbody.innerHTML =
          '<tr><td colspan="7" style="color:#888;">No matches found.</td></tr>';
      }

      // Add cross-linking: click row → highlight in 3D + PDF
      tbody.querySelectorAll("tr[data-match-index]").forEach((row) => {
        row.style.cursor = "pointer";
        row.addEventListener("click", () => {
          // Deselect all, select this
          tbody
            .querySelectorAll("tr")
            .forEach((r) => r.classList.remove("selected"));
          row.classList.add("selected");
          const featureId = row.dataset.featureId;
          const annotationId = row.dataset.annotationId;
          if (featureId && tcViewer3d) tcViewer3d.highlightFeature(featureId);
          if (annotationId && tcPdfViewer) {
            const ann = results.annotations?.find((a) => a.id === annotationId);
            if (ann && ann.bbox && tcPdfViewer.pdfDoc) {
              const annPage = (ann.bbox.page || 0) + 1;
              if (annPage !== tcPdfViewer.currentPage) {
                tcPdfViewer.renderPage(annPage).then(() => {
                  tcPdfViewer.highlightAnnotation(annotationId);
                });
              } else {
                tcPdfViewer.highlightAnnotation(annotationId);
              }
            } else {
              tcPdfViewer.highlightAnnotation(annotationId);
            }
          }
        });
      });

      // Update 3D viewer with match highlights
      if (tcViewer3d && results.holes && results.matches) {
        tcViewer3d.addFeatureMarkers(results.holes, results.matches);
      }

      // Update PDF viewer with annotation overlays
      if (tcPdfViewer && results.annotations && results.matches) {
        tcPdfViewer.setAnnotations(results.annotations, results.matches);
      }

      statusBar.classList.add("hidden");
      resultsDiv.classList.remove("hidden");

      // Scroll to results after DOM update
      requestAnimationFrame(() => {
        setTimeout(() => {
          const el = document.getElementById("tc-analysis-results");
          if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 50);
      });
    }
  } catch (e) {
    statusText.textContent = `Error: ${e.message}`;
    progressFill.style.width = "0%";
  } finally {
    btn.disabled = false;
  }
}

function initTestCases() {
  // Back button
  document.getElementById("tc-back-btn").addEventListener("click", () => {
    document.getElementById("tc-detail-view").classList.add("hidden");
    document.getElementById("tc-list-view").classList.remove("hidden");
    document.getElementById("tc-analysis-results").classList.add("hidden");
    document.getElementById("tc-analyze-status").classList.add("hidden");
  });

  // Analyze button
  document.getElementById("tc-analyze-btn").addEventListener("click", () => {
    if (currentTcId) analyzeTestCase(currentTcId);
  });

  // Filter buttons
  document.querySelectorAll(".tc-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".tc-filter-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentTcFilter = btn.dataset.filter;
      renderTestCasesTable(currentTcFilter);
    });
  });

  // Eval table -> test case detail navigation
  document
    .getElementById("eval-table-container")
    .addEventListener("click", (e) => {
      const link = e.target.closest(".eval-tc-link");
      if (!link) return;
      e.preventDefault();
      const tcId = link.dataset.tcId;

      // Switch to Test Cases tab
      document
        .querySelectorAll(".header-nav .nav-btn")
        .forEach((b) => b.classList.remove("active"));
      document
        .querySelector('.header-nav .nav-btn[data-tab="testcases"]')
        .classList.add("active");

      document.getElementById("evaluation-section").classList.add("hidden");
      document.getElementById("upload-section").style.display = "none";
      document.getElementById("results-section").style.display = "none";
      document.getElementById("testcases-section").classList.remove("hidden");

      loadTestCases().then(() => showTestCaseDetail(tcId));
    });
}

// Navigate to test case detail from anywhere
function navigateToTestCase(tcId) {
  document
    .querySelectorAll(".header-nav .nav-btn")
    .forEach((b) => b.classList.remove("active"));
  document
    .querySelector('.header-nav .nav-btn[data-tab="testcases"]')
    .classList.add("active");

  document.getElementById("evaluation-section").classList.add("hidden");
  document.getElementById("upload-section").style.display = "none";
  document.getElementById("results-section").style.display = "none";
  document.getElementById("testcases-section").classList.remove("hidden");

  loadTestCases().then(() => showTestCaseDetail(tcId));
}

// Lightbox for chart images
function initLightbox() {
  const lightbox = document.getElementById("lightbox");
  const lightboxImg = document.getElementById("lightbox-img");

  document.addEventListener("click", (e) => {
    const img = e.target.closest("#eval-charts img, .eval-gallery img");
    if (img) {
      lightboxImg.src = img.src;
      lightbox.classList.add("active");
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      lightbox.classList.remove("active");
    }
  });
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  initLanguageToggle();
  new DrawMindApp();
  initTabs();
  initTestCases();
  initLightbox();
});
