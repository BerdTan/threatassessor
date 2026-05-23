// ThreatAssessor Dashboard - Main Controller

class Dashboard {
    constructor() {
        this.analysisData = null;
        this.currentTab = 'overview';
        this.sseClient = null;

        this.init();
    }

    init() {
        // Initialize tab navigation
        this.initTabs();

        // Initialize upload form
        this.initUpload();

        // Initialize right pane
        this.initRightPane();

        // Load theme preference
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.body.className = `${savedTheme}-theme`;
    }

    initRightPane() {
        const closeBtn = document.getElementById('right-pane-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hideRightPane());
        }
    }

    showRightPane(title, content) {
        const rightPane = document.getElementById('right-pane');
        const rightPaneContent = document.getElementById('right-pane-content');

        rightPaneContent.innerHTML = `
            <h3>${title}</h3>
            ${content}
        `;

        rightPane.classList.add('visible');
    }

    hideRightPane() {
        const rightPane = document.getElementById('right-pane');
        rightPane.classList.remove('visible');
    }

    initTabs() {
        const navTabs = document.querySelectorAll('.nav-tab');
        navTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                this.switchTab(tabName);
            });
        });
    }

    switchTab(tabName) {
        // Update nav tabs
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab panes
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.dataset.tab === tabName);
        });

        this.currentTab = tabName;

        // Load tab-specific data if analysis is complete
        if (this.analysisData) {
            this.loadTabData(tabName);
        }
    }

    initUpload() {
        const uploadForm = document.getElementById('upload-form');
        const uploadBtn = document.getElementById('upload-btn');
        const fileInput = document.getElementById('file-input');
        const dropZone = document.getElementById('drop-zone');

        // Upload button click
        uploadBtn.addEventListener('click', () => {
            fileInput.click();
        });

        // Form submit
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.startAnalysis();
        });

        // Drag and drop
        dropZone.addEventListener('click', () => {
            fileInput.click();
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#3498db';
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.style.borderColor = '';
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '';

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                uploadForm.dispatchEvent(new Event('submit'));
            }
        });
    }

    async startAnalysis() {
        const fileInput = document.getElementById('file-input');
        const includeValidation = document.getElementById('include-validation').checked;

        if (!fileInput.files.length) {
            alert('Please select an architecture file');
            return;
        }

        const file = fileInput.files[0];
        if (!file.name.endsWith('.mmd')) {
            alert('Please select a .mmd file');
            return;
        }

        // Hide upload form, show analysis view
        document.getElementById('upload-form-container').style.display = 'none';
        document.getElementById('tab-content').style.display = 'block';

        // Reset progress
        this.updateProgress(0, 'Starting analysis...');

        // Start SSE connection
        const formData = new FormData();
        formData.append('architecture_file', file);
        formData.append('include_validation', includeValidation);

        this.sseClient = new SSEClient('/api/v1/analyze-stream', formData);
        this.sseClient.on('progress', (data) => this.handleProgress(data));
        this.sseClient.on('patterns_detected', (data) => this.handlePatternsDetected(data));
        this.sseClient.on('threat_scores', (data) => this.handleThreatScores(data));
        this.sseClient.on('attack_path', (data) => this.handleAttackPath(data));
        this.sseClient.on('complete', (data) => this.handleComplete(data));
        this.sseClient.on('error', (data) => this.handleError(data));

        await this.sseClient.connect();
    }

    handleProgress(data) {
        const { stage, progress, message, eta_seconds, patterns_active } = data;

        // Update progress bar
        this.updateProgress(progress, message, eta_seconds);

        // Update stage indicators
        this.updateStages(stage);

        // Show AI/ML stage if active
        if (patterns_active && patterns_active.includes('ai_ml_arc')) {
            document.getElementById('ai-ml-stage').style.display = 'inline';
            document.getElementById('ai-ml-arrow').style.display = 'inline';
        }
    }

    handlePatternsDetected(data) {
        const { patterns } = data;

        // Update pattern badges in header
        const badgesContainer = document.getElementById('pattern-badges');
        badgesContainer.innerHTML = '';

        patterns.forEach(pattern => {
            const badge = document.createElement('span');
            badge.className = `badge badge-${this.getPatternClass(pattern.pattern_id)}`;
            badge.textContent = pattern.name.split(' + ')[0]; // Short name
            badge.title = pattern.name;
            badgesContainer.appendChild(badge);
        });

        // Show AI/ML tab if detected
        const hasAIML = patterns.some(p => p.pattern_id === 'ai_ml_arc');
        if (hasAIML) {
            document.querySelector('.nav-tab[data-tab="ai-ml"]').style.display = 'block';
        }

        // Store patterns
        this.patterns = patterns;
    }

    handleThreatScores(data) {
        // Store threat scores for visualization
        this.threatScores = data;

        // If on overview tab, update chart immediately
        if (this.currentTab === 'overview') {
            this.renderThreatChart();
        }
    }

    handleAttackPath(data) {
        // Store attack path
        if (!this.attackPaths) {
            this.attackPaths = [];
        }
        this.attackPaths.push(data);
    }

    handleComplete(data) {
        this.analysisData = data.data;

        // Update status
        this.updateProgress(100, 'Analysis complete!', 0);
        this.updateStages('complete');

        // Load current tab data
        this.loadTabData(this.currentTab);
    }

    handleError(data) {
        const { message, detail } = data;
        alert(`Analysis failed: ${message}\n\n${detail || ''}`);

        // Reset to upload form
        document.getElementById('upload-form-container').style.display = 'block';
        document.getElementById('tab-content').style.display = 'none';
        this.updateProgress(0, 'Ready to analyze architecture');
    }

    updateProgress(percent, message, eta = null) {
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');
        const statusMessage = document.getElementById('status-message');

        progressFill.style.width = `${percent}%`;
        progressText.textContent = `${percent}%`;

        let statusText = message;
        if (eta && eta > 0) {
            statusText += ` (ETA: ${eta}s)`;
        }
        statusMessage.textContent = statusText;
    }

    updateStages(currentStage) {
        const stages = document.querySelectorAll('.stage');
        const stageOrder = ['parsing', 'mitre', 'rapids', 'ai_ml', 'validation'];

        stages.forEach(stageEl => {
            const stageName = stageEl.dataset.stage;
            const stageIndex = stageOrder.indexOf(stageName);
            const currentIndex = stageOrder.indexOf(currentStage);

            if (stageIndex < currentIndex || currentStage === 'complete') {
                // Completed
                stageEl.classList.add('complete');
                stageEl.classList.remove('active');
            } else if (stageName === currentStage) {
                // Active
                stageEl.classList.add('active');
                stageEl.classList.remove('complete');
            } else {
                // Pending
                stageEl.classList.remove('active', 'complete');
            }
        });
    }

    loadTabData(tabName) {
        switch (tabName) {
            case 'overview':
                this.loadOverviewTab();
                break;
            case 'patterns':
                this.loadPatternsTab();
                break;
            case 'attacks':
                this.loadAttacksTab();
                break;
            case 'controls':
                this.loadControlsTab();
                break;
            case 'mitre':
                this.loadMitreTab();
                break;
            case 'ai-ml':
                this.loadAIMLTab();
                break;
            case 'reports':
                this.loadReportsTab();
                break;
            case 'raw-data':
                this.loadRawDataTab();
                break;
        }
    }

    loadOverviewTab() {
        this.renderThreatChart();
        // Architecture diagram rendering would go here (requires Mermaid.js)
    }

    renderThreatChart() {
        if (!this.threatScores) return;

        const canvas = document.getElementById('threat-chart');
        if (!canvas) return;

        const rapidsScores = this.threatScores.rapids || {};
        const labels = Object.keys(rapidsScores).filter(k => k !== '_metadata');
        const risks = labels.map(label => rapidsScores[label]?.risk || 0);

        if (window.threatChartInstance) {
            window.threatChartInstance.destroy();
        }

        window.threatChartInstance = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels.map(l => l.replace(/_/g, ' ').toUpperCase()),
                datasets: [{
                    label: 'Risk Score',
                    data: risks,
                    backgroundColor: risks.map(r =>
                        r >= 70 ? '#e74c3c' : r >= 50 ? '#f39c12' : '#3498db'
                    )
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: { display: true, text: 'Risk Score' }
                    }
                }
            }
        });
    }

    loadPatternsTab() {
        if (!this.patterns) return;

        const container = document.getElementById('patterns-list');
        container.innerHTML = '';

        this.patterns.forEach(pattern => {
            const card = this.createPatternCard(pattern);
            container.appendChild(card);
        });
    }

    createPatternCard(pattern) {
        const div = document.createElement('div');
        div.className = `pattern-card ${pattern.pattern_id.replace('_', '-')}`;

        const statusClass = pattern.status === 'applied' ? 'applied' : 'partial';
        const statusText = pattern.status === 'applied' ? '✓ Applied' : '⚠ Partial';

        div.innerHTML = `
            <h3>${pattern.name}</h3>
            <div class="pattern-meta">
                <span class="pattern-status ${statusClass}">${statusText}</span>
                <p><strong>Scope:</strong> ${pattern.scope}</p>
                <p><strong>Source:</strong> ${pattern.technique_source}</p>
                ${pattern.trigger ? `<p><strong>Trigger:</strong> ${pattern.trigger}</p>` : ''}
            </div>
            <p>${pattern.description}</p>
            ${pattern.limitations ? `
                <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(243, 156, 18, 0.1); border-left: 3px solid #f39c12; border-radius: 4px;">
                    <strong>Limitations:</strong>
                    <ul style="margin: 0.5rem 0 0 1.5rem;">
                        ${pattern.limitations.map(lim => `<li>${lim}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
        `;

        return div;
    }

    loadAttacksTab() {
        // Attack paths visualization
        if (!this.attackPaths || !this.analysisData) return;

        const listContainer = document.getElementById('attack-paths-list');

        // Sort attack paths by ID numerically
        const sortedPaths = [...this.attackPaths].sort((a, b) => {
            const numA = parseInt(a.id.replace('AP-', ''));
            const numB = parseInt(b.id.replace('AP-', ''));
            return numA - numB;
        });

        listContainer.innerHTML = `
            <h4>Attack Paths Discovered: ${sortedPaths.length}</h4>
            <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 1rem;">
                Click on a path to see detailed traversal through the architecture
            </p>
        `;

        sortedPaths.forEach((path, index) => {
            const item = document.createElement('div');
            item.className = 'list-item';

            const criticalityColor =
                path.criticality_tier === 'HIGH' ? 'var(--danger-color)' :
                path.criticality_tier === 'MEDIUM' ? 'var(--warning-color)' :
                'var(--secondary-color)';

            item.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="font-size: 1.125rem;">${path.id}</strong>
                        <div style="color: var(--text-secondary); margin-top: 0.25rem;">
                            ${path.entry} → ${path.target}
                        </div>
                        <div style="font-size: 0.875rem; color: var(--text-tertiary); margin-top: 0.25rem;">
                            ${path.hop_count} hops · ${path.techniques?.length || 0} techniques
                        </div>
                    </div>
                    <div style="padding: 0.25rem 0.75rem; background: ${criticalityColor}22; color: ${criticalityColor}; border-radius: 8px; font-weight: 700; font-size: 0.75rem;">
                        ${path.criticality_tier || 'MEDIUM'}
                    </div>
                </div>
            `;
            item.addEventListener('click', () => {
                // Remove active class from all items
                listContainer.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                item.classList.add('active');
                this.showAttackPathDetail(path);
            });
            listContainer.appendChild(item);
        });
    }

    showAttackPathDetail(path) {
        // Show in right pane
        const pathHtml = `
            <div style="margin-bottom: 1.5rem;">
                <div style="font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem;">${path.id}</div>
                <div style="padding: 0.5rem 1rem; background: ${
                    path.criticality_tier === 'HIGH' ? 'var(--danger-color)22' :
                    path.criticality_tier === 'MEDIUM' ? 'var(--warning-color)22' :
                    'var(--secondary-color)22'
                }; border-left: 4px solid ${
                    path.criticality_tier === 'HIGH' ? 'var(--danger-color)' :
                    path.criticality_tier === 'MEDIUM' ? 'var(--warning-color)' :
                    'var(--secondary-color)'
                }; border-radius: 4px;">
                    <strong>Criticality:</strong> ${path.criticality_tier || 'MEDIUM'}
                </div>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">Attack Path Traversal</h4>
                <div style="padding: 1rem; background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border-color);">
                    ${path.path.map((node, idx) => `
                        <div style="display: flex; align-items: center; margin-bottom: ${idx < path.path.length - 1 ? '0.75rem' : '0'};">
                            <div style="background: var(--primary-color); color: black; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.875rem; margin-right: 0.75rem;">
                                ${idx + 1}
                            </div>
                            <div style="flex: 1; padding: 0.5rem 1rem; background: ${idx === 0 ? 'var(--danger-color)22' : idx === path.path.length - 1 ? 'var(--warning-color)22' : 'var(--nav-hover-bg)'}; border-radius: 6px;">
                                <strong>${node}</strong>
                                ${idx === 0 ? ' <span style="color: var(--danger-color);">(Entry)</span>' : ''}
                                ${idx === path.path.length - 1 ? ' <span style="color: var(--warning-color);">(Target)</span>' : ''}
                            </div>
                        </div>
                        ${idx < path.path.length - 1 ? '<div style="margin-left: 14px; width: 2px; height: 20px; background: var(--border-color);"></div>' : ''}
                    `).join('')}
                </div>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">MITRE ATT&CK Techniques (${path.techniques?.length || 0})</h4>
                <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                    ${(path.techniques || []).map(t => `
                        <span style="padding: 0.375rem 0.75rem; background: var(--nav-active-bg); border: 1px solid var(--border-color); border-radius: 6px; font-size: 0.875rem; font-family: monospace;">
                            ${t}
                        </span>
                    `).join('')}
                </div>
            </div>

            ${path.rationale ? `
                <div style="margin-bottom: 1.5rem;">
                    <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">Analysis</h4>
                    <div style="padding: 1rem; background: var(--code-bg); border-radius: 8px; border-left: 4px solid var(--primary-color); font-size: 0.875rem; line-height: 1.6;">
                        ${path.rationale}
                    </div>
                </div>
            ` : ''}
        `;

        this.showRightPane(`Attack Path: ${path.entry} → ${path.target}`, pathHtml);
    }

    loadControlsTab() {
        // Controls table - simplified for now
        const tableContainer = document.getElementById('controls-table');
        tableContainer.innerHTML = '<p>Controls analysis available in complete analysis results</p>';
    }

    loadMitreTab() {
        // MITRE matrix - simplified for now
        const matrixContainer = document.getElementById('mitre-matrix');
        matrixContainer.innerHTML = '<p>MITRE technique matrix available in complete analysis results</p>';
    }

    loadAIMLTab() {
        // AI/ML risks - check if available
        const aiRisks = this.threatScores?.ai_ml;
        if (!aiRisks) {
            document.getElementById('ai-risk-chart').parentElement.innerHTML = '<p>No AI/ML risks detected</p>';
            return;
        }

        // Render AI/ML risk chart (similar to threat chart)
    }

    loadReportsTab() {
        // Reports list - simplified for now
        const listContainer = document.getElementById('reports-list');
        listContainer.innerHTML = '<p>Generated reports will be listed here</p>';
    }

    loadRawDataTab() {
        // Show raw JSON data
        const listContainer = document.getElementById('artifacts-list');
        listContainer.innerHTML = '';

        const artifacts = [
            { name: 'ground_truth.json', data: this.analysisData }
        ];

        artifacts.forEach(artifact => {
            const item = document.createElement('div');
            item.className = 'list-item';
            item.textContent = artifact.name;
            item.addEventListener('click', () => this.showArtifact(artifact));
            listContainer.appendChild(item);
        });
    }

    showArtifact(artifact) {
        const jsonStr = JSON.stringify(artifact.data, null, 2);
        const content = `
            <div style="padding: 1rem; background: var(--code-bg); border-radius: 8px; border: 1px solid var(--border-color); overflow-x: auto;">
                <pre style="margin: 0;"><code class="language-json">${this.escapeHtml(jsonStr)}</code></pre>
            </div>
        `;
        this.showRightPane(artifact.name, content);

        // Apply syntax highlighting
        if (window.hljs) {
            const rightPane = document.getElementById('right-pane-content');
            const codeBlock = rightPane.querySelector('code');
            if (codeBlock) {
                hljs.highlightElement(codeBlock);
            }
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getPatternClass(patternId) {
        const classMap = {
            'rapids': 'primary',
            'ai_ml_arc': 'ai',
            'cloud_generic': 'cloud'
        };
        return classMap[patternId] || 'primary';
    }
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});
