// Visualizations for ThreatAssessor Dashboard

// Chart.js helper functions
function createThreatChart(canvasId, data, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            ...options
        }
    });
}

// Color helpers
function getRiskColor(score) {
    if (score >= 70) return '#e74c3c'; // Red (High)
    if (score >= 50) return '#f39c12'; // Orange (Medium)
    if (score >= 30) return '#f1c40f'; // Yellow (Low)
    return '#3498db'; // Blue (Very Low)
}

function getDefensibilityColor(score) {
    if (score >= 70) return '#2ecc71'; // Green (Strong)
    if (score >= 50) return '#f1c40f'; // Yellow (Moderate)
    if (score >= 30) return '#f39c12'; // Orange (Weak)
    return '#e74c3c'; // Red (Very Weak)
}

// Export for global access
window.chartHelpers = {
    createThreatChart,
    getRiskColor,
    getDefensibilityColor
};
