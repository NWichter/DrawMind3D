/**
 * PDF.js Viewer with annotation overlay and match-color sync.
 */

class PDFViewer {
    constructor(canvasId, overlayId) {
        this.canvas = document.getElementById(canvasId);
        this.overlay = overlayId ? document.getElementById(overlayId) : null;
        this.ctx = this.canvas.getContext('2d');
        this.pdfDoc = null;
        this.currentPage = 1;
        this.scale = 1.0;
        this.annotations = [];
        this.matches = [];
        this.selectedAnnotationId = null;

        // Configure PDF.js worker
        if (typeof pdfjsLib !== 'undefined') {
            pdfjsLib.GlobalWorkerOptions.workerSrc =
                'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        }
    }

    get totalPages() {
        return this.pdfDoc ? this.pdfDoc.numPages : 0;
    }

    async loadPDF(url) {
        try {
            this.pdfDoc = await pdfjsLib.getDocument(url).promise;
            await this.renderPage(1);
            this._updatePageNav();
        } catch (e) {
            console.error('Failed to load PDF:', e);
        }
    }

    async nextPage() {
        if (this.pdfDoc && this.currentPage < this.pdfDoc.numPages) {
            await this.renderPage(this.currentPage + 1);
            this._updatePageNav();
        }
    }

    async prevPage() {
        if (this.pdfDoc && this.currentPage > 1) {
            await this.renderPage(this.currentPage - 1);
            this._updatePageNav();
        }
    }

    _updatePageNav() {
        const container = this.canvas.closest('.viewer-panel') || this.canvas.parentElement;
        const pageInfo = container.querySelector('.pdf-page-info');
        if (pageInfo && this.pdfDoc) {
            pageInfo.textContent = `Page ${this.currentPage} / ${this.pdfDoc.numPages}`;
        }
        const prevBtn = container.querySelector('.pdf-prev-btn');
        const nextBtn = container.querySelector('.pdf-next-btn');
        if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
        if (nextBtn) nextBtn.disabled = !this.pdfDoc || this.currentPage >= this.pdfDoc.numPages;
        const nav = container.querySelector('.pdf-page-nav');
        if (nav && this.pdfDoc) {
            nav.style.display = this.pdfDoc.numPages > 1 ? 'flex' : 'none';
        }
    }

    async renderPage(pageNum) {
        if (!this.pdfDoc) return;

        const page = await this.pdfDoc.getPage(pageNum);
        const container = this.canvas.parentElement;
        const containerWidth = container.clientWidth;

        const viewport = page.getViewport({ scale: 1 });
        this.scale = (containerWidth - 20) / viewport.width;
        const scaledViewport = page.getViewport({ scale: this.scale });

        this.canvas.width = scaledViewport.width;
        this.canvas.height = scaledViewport.height;

        if (this.overlay) {
            this.overlay.style.width = scaledViewport.width + 'px';
            this.overlay.style.height = scaledViewport.height + 'px';
            this.overlay.setAttribute('viewBox', `0 0 ${scaledViewport.width} ${scaledViewport.height}`);
        }

        await page.render({
            canvasContext: this.ctx,
            viewport: scaledViewport,
        }).promise;

        this.currentPage = pageNum;
        this._renderAnnotationOverlays();
    }

    setAnnotations(annotations, matches) {
        this.annotations = annotations;
        this.matches = matches || [];
        this._renderAnnotationOverlays();
    }

    _renderAnnotationOverlays() {
        if (!this.overlay) return;
        while (this.overlay.firstChild) {
            this.overlay.removeChild(this.overlay.firstChild);
        }

        if (!this.annotations.length) return;

        // Build match lookup: annotation_id → {match, matchIndex}
        // matchIndex is the position in the matches array (same as table row & 3D marker)
        const matchByAnnotationId = {};
        this.matches.forEach((m, idx) => {
            matchByAnnotationId[m.annotation_id] = { match: m, idx };
        });

        // Use shared palette from MATCH_PALETTE (defined in annotations.js)
        const palette = typeof MATCH_PALETTE !== 'undefined' ? MATCH_PALETTE : [
            '#60a5fa', '#4ade80', '#facc15', '#f87171',
            '#a78bfa', '#fb923c', '#2dd4bf', '#f472b6',
        ];

        this.annotations.forEach((ann) => {
            const bbox = ann.bbox;
            if (!bbox || bbox.page !== this.currentPage - 1) return;

            const matchInfo = matchByAnnotationId[ann.id];
            const color = matchInfo ? palette[matchInfo.idx % palette.length] : '#555';

            const x = bbox.x0 * this.scale;
            const y = bbox.y0 * this.scale;
            const w = (bbox.x1 - bbox.x0) * this.scale;
            const h = (bbox.y1 - bbox.y0) * this.scale;

            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', x - 2);
            rect.setAttribute('y', y - 2);
            rect.setAttribute('width', w + 4);
            rect.setAttribute('height', h + 4);
            rect.setAttribute('fill', color + '25');
            rect.setAttribute('stroke', color);
            rect.setAttribute('stroke-width', matchInfo ? '2' : '1');
            rect.setAttribute('rx', '3');
            rect.classList.add('annotation-rect');
            rect.dataset.annotationId = ann.id;

            if (ann.id === this.selectedAnnotationId) {
                rect.classList.add('active');
            }

            // Tooltip with match info
            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            if (matchInfo) {
                title.textContent = `${ann.raw_text} → ${matchInfo.match.feature_id} (${(matchInfo.match.confidence * 100).toFixed(0)}%)`;
            } else {
                title.textContent = `${ann.raw_text} (${ann.annotation_type}) — unmatched`;
            }
            rect.appendChild(title);

            // Click handler
            rect.style.pointerEvents = 'all';
            rect.style.cursor = 'pointer';
            rect.addEventListener('click', () => {
                if (window.drawMindApp) {
                    window.drawMindApp.selectAnnotation(ann.id);
                }
            });

            this.overlay.appendChild(rect);
        });
    }

    highlightAnnotation(annotationId) {
        this.selectedAnnotationId = annotationId;
        this._renderAnnotationOverlays();

        if (!this.overlay) return;
        const rect = this.overlay.querySelector(`[data-annotation-id="${annotationId}"]`);
        if (rect) {
            rect.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}
