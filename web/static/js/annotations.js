/**
 * Annotations panel: matches table and linking logic.
 */

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

            const diameter = match.feature_3d_ref?.primary_diameter_mm;
            const diameterStr = diameter ? `${diameter.toFixed(2)} mm` : '-';

            tr.innerHTML = `
                <td>${index + 1}</td>
                <td><code>${this._escapeHtml(match.annotation_text)}</code></td>
                <td>${type}</td>
                <td>${match.feature_id}</td>
                <td>${diameterStr}</td>
                <td class="${confClass}">${(match.confidence * 100).toFixed(0)}%</td>
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

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}
