/**
 * Annotations panel: matches table with color-coded linking.
 */

// Shared match color palette (hex strings) — must match Viewer3D.MATCH_COLORS
const MATCH_PALETTE = [
    '#60a5fa', '#4ade80', '#facc15', '#f87171',
    '#a78bfa', '#fb923c', '#2dd4bf', '#f472b6',
    '#38bdf8', '#a3e635', '#e879f9', '#22d3ee',
];

class AnnotationsPanel {
    constructor(tableBodyId) {
        this.tbody = document.getElementById(tableBodyId);
        this.matches = [];
        this.selectedMatchId = null;
        this.onSelect = null; // Callback: (match) => {}
    }

    setMatches(matches) {
        this.matches = matches;
        this._render();
    }

    _render() {
        this.tbody.innerHTML = '';

        this.matches.forEach((match, index) => {
            const tr = document.createElement('tr');
            tr.dataset.matchId = match.id;

            if (match.id === this.selectedMatchId) {
                tr.classList.add('selected');
            }

            // Confidence color class
            let confClass = 'confidence-low';
            if (match.confidence >= 0.8) confClass = 'confidence-high';
            else if (match.confidence >= 0.5) confClass = 'confidence-mid';

            // Parse type from annotation
            const type = match.parsed_interpretation?.thread_type
                || match.parsed_interpretation?.type
                || this._inferType(match);

            const feat = match.feature_3d_ref;
            const feat_dia = feat?.primary_diameter_mm;
            const feat_depth = feat?.total_depth_mm;

            // Drawing spec (from annotation parsed data)
            const parsed = match.parsed_interpretation || {};
            const annDia = parsed.value || parsed.nominal_diameter;
            const drawSpec = annDia ? `\u00d8${annDia.toFixed(2)}` : this._escapeHtml(match.annotation_text?.substring(0, 15) || '-');

            // 3D actual (from feature)
            let actualSpec = feat_dia ? `\u00d8${feat_dia.toFixed(2)}` : '-';
            if (feat_depth) actualSpec += ` \u00d7 ${feat_depth.toFixed(1)}`;

            // Color dot for match pair identification
            const color = MATCH_PALETTE[index % MATCH_PALETTE.length];

            tr.innerHTML = `
                <td><span class="match-color-dot" style="background:${color}"></span> ${index + 1}</td>
                <td><code>${this._escapeHtml(match.annotation_text)}</code></td>
                <td>${type}</td>
                <td>${match.feature_id}</td>
                <td>${drawSpec}</td>
                <td>${actualSpec}</td>
                <td class="${confClass}" title="${this._breakdownTooltip(match)}">${(match.confidence * 100).toFixed(0)}%</td>
            `;

            tr.addEventListener('click', () => this.selectMatch(match.id));
            this.tbody.appendChild(tr);
        });
    }

    _inferType(match) {
        const text = match.annotation_text || '';
        if (text.match(/^M\d/i)) return 'Thread';
        if (text.match(/[⌀Øø∅]/)) return 'Diameter';
        if (text.match(/depth|tiefe/i)) return 'Depth';
        if (text.match(/thru/i)) return 'Through';
        return 'Dimension';
    }

    selectMatch(matchId) {
        this.selectedMatchId = matchId;
        this._render();

        const match = this.matches.find(m => m.id === matchId);
        if (match && this.onSelect) {
            this.onSelect(match);
        }
    }

    _breakdownTooltip(match) {
        const bd = match.scoring_breakdown;
        if (!bd) return '';
        return Object.entries(bd)
            .map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`)
            .join(' | ');
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}
