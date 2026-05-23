// ThreatAssessor Dashboard - Main Controller

class Dashboard {
    constructor() {
        this.analysisData = null;
        this.currentTab = 'overview';
        this.sseClient = null;
        this.uploadedFile = null;

        this.init();
    }

    init() {
        // Initialize tab navigation
        this.initTabs();

        // Initialize upload form
        this.initUpload();

        // Initialize right pane
        this.initRightPane();

        // Initialize Mermaid
        if (window.mermaid) {
            mermaid.initialize({
                startOnLoad: false,
                theme: document.body.classList.contains('dark-theme') ? 'dark' : 'default',
                securityLevel: 'loose',
                flowchart: { useMaxWidth: false }
            });
        }

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

        // Store uploaded file for diagram rendering
        this.uploadedFile = file;

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

    async loadOverviewTab() {
        this.renderThreatChart();
        await this.renderArchitectureDiagram();
    }

    async renderArchitectureDiagram() {
        const container = document.getElementById('arch-diagram');
        if (!container || !this.uploadedFile) return;

        try {
            // Read uploaded file
            const reader = new FileReader();
            reader.onload = async (e) => {
                const mmdContent = e.target.result;

                // Create container for mermaid
                container.innerHTML = `
                    <div style="text-align: center; margin-bottom: 0.5rem;">
                        <button id="zoom-in" class="btn-icon" style="margin: 0 0.25rem;">🔍+</button>
                        <button id="zoom-out" class="btn-icon" style="margin: 0 0.25rem;">🔍−</button>
                        <button id="zoom-reset" class="btn-icon" style="margin: 0 0.25rem;">↺</button>
                    </div>
                    <div id="mermaid-container" style="overflow: auto; max-height: calc(100vh - 280px); padding: 1rem; background: var(--code-bg); border-radius: 8px;">
                        <div class="mermaid">${mmdContent}</div>
                    </div>
                `;

                // Render mermaid
                if (window.mermaid) {
                    await mermaid.run({
                        querySelector: '#mermaid-container .mermaid'
                    });

                    // Add zoom controls
                    let scale = 1;
                    const mermaidContainer = document.getElementById('mermaid-container');

                    document.getElementById('zoom-in').addEventListener('click', () => {
                        scale = Math.min(scale + 0.2, 3);
                        mermaidContainer.querySelector('.mermaid').style.transform = `scale(${scale})`;
                    });

                    document.getElementById('zoom-out').addEventListener('click', () => {
                        scale = Math.max(scale - 0.2, 0.5);
                        mermaidContainer.querySelector('.mermaid').style.transform = `scale(${scale})`;
                    });

                    document.getElementById('zoom-reset').addEventListener('click', () => {
                        scale = 1;
                        mermaidContainer.querySelector('.mermaid').style.transform = `scale(1)`;
                    });
                }
            };

            reader.readAsText(this.uploadedFile);
        } catch (error) {
            console.error('Error rendering architecture diagram:', error);
            container.innerHTML = '<p class="placeholder">Failed to render architecture diagram</p>';
        }
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

        const isDark = document.body.classList.contains('dark-theme');

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
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            color: isDark ? '#ffffff' : '#000000',
                            generateLabels: () => [
                                { text: 'High Risk (70-100)', fillStyle: '#e74c3c', strokeStyle: '#e74c3c' },
                                { text: 'Medium Risk (50-69)', fillStyle: '#f39c12', strokeStyle: '#f39c12' },
                                { text: 'Low Risk (0-49)', fillStyle: '#3498db', strokeStyle: '#3498db' }
                            ]
                        }
                    },
                    tooltip: {
                        backgroundColor: isDark ? '#1a1a1a' : '#ffffff',
                        titleColor: isDark ? '#ffffff' : '#000000',
                        bodyColor: isDark ? '#ffffff' : '#000000',
                        borderColor: isDark ? '#00d4ff' : '#0066cc',
                        borderWidth: 1
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: {
                            display: true,
                            text: 'Risk Score',
                            color: isDark ? '#ffffff' : '#000000'
                        },
                        ticks: {
                            color: isDark ? '#b0b0b0' : '#4a4a4a'
                        },
                        grid: {
                            color: isDark ? '#333333' : '#e0e0e0'
                        }
                    },
                    x: {
                        ticks: {
                            color: isDark ? '#b0b0b0' : '#4a4a4a'
                        },
                        grid: {
                            color: isDark ? '#333333' : '#e0e0e0'
                        }
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
                Click on a path to see summary. Click steps in detail pane to see techniques.
            </p>
        `;

        sortedPaths.forEach((path, index) => {
            const item = document.createElement('div');
            item.className = 'list-item';
            item.dataset.pathId = path.id;

            const criticalityColor =
                path.criticality_tier === 'HIGH' ? 'var(--danger-color)' :
                path.criticality_tier === 'MEDIUM' ? 'var(--warning-color)' :
                'var(--secondary-color)';

            // Create summary section (collapsed by default)
            const summaryId = `summary-${path.id}`;

            item.innerHTML = `
                <div class="path-header" style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;">
                    <div style="flex: 1;">
                        <strong style="font-size: 1.125rem;">${path.id}</strong>
                        <div style="color: var(--text-secondary); margin-top: 0.25rem;">
                            ${path.entry} → ${path.target}
                        </div>
                        <div style="font-size: 0.875rem; color: var(--text-tertiary); margin-top: 0.25rem;">
                            ${path.hop_count} hops · ${path.techniques?.length || 0} techniques
                        </div>
                    </div>
                    <div style="display: flex; gap: 0.5rem; align-items: center;">
                        <div style="padding: 0.25rem 0.75rem; background: ${criticalityColor}22; color: ${criticalityColor}; border-radius: 8px; font-weight: 700; font-size: 0.75rem;">
                            ${path.criticality_tier || 'MEDIUM'}
                        </div>
                        <span class="expand-icon" style="font-size: 1.25rem; transition: transform 0.2s;">▼</span>
                    </div>
                </div>
                <div id="${summaryId}" class="path-summary" style="display: none; margin-top: 1rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid ${criticalityColor};">
                    <h5 style="margin-bottom: 0.75rem; color: var(--primary-color);">Path Summary</h5>
                    <div style="margin-bottom: 0.75rem;">
                        <strong>Route:</strong> ${path.path.join(' → ')}
                    </div>
                    ${path.rationale ? `
                        <div style="margin-bottom: 0.75rem;">
                            <strong>Analysis:</strong><br>
                            <span style="color: var(--text-secondary); font-size: 0.875rem;">${path.rationale}</span>
                        </div>
                    ` : ''}
                    <button class="btn-primary" style="margin-top: 0.5rem; font-size: 0.875rem;">
                        View Step-by-Step Details →
                    </button>
                </div>
            `;

            // Toggle summary on header click
            const header = item.querySelector('.path-header');
            const summary = item.querySelector('.path-summary');
            const expandIcon = item.querySelector('.expand-icon');

            header.addEventListener('click', (e) => {
                if (e.target.closest('.btn-primary')) return; // Don't toggle if clicking button

                const isExpanded = summary.style.display === 'block';
                summary.style.display = isExpanded ? 'none' : 'block';
                expandIcon.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(180deg)';
            });

            // Show details on button click
            const detailBtn = item.querySelector('.btn-primary');
            detailBtn.addEventListener('click', (e) => {
                e.stopPropagation();

                // Remove active class from all items
                listContainer.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                item.classList.add('active');

                this.showAttackPathDetail(path);
            });

            listContainer.appendChild(item);
        });
    }

    showAttackPathDetail(path) {
        // Get per-node techniques
        const perNodeTechniques = path.per_node_techniques || {};

        // Build step-by-step HTML with clickable steps
        const stepsHtml = path.path.map((node, idx) => {
            const stepTechniques = perNodeTechniques[node] || [];
            const stepId = `step-${path.id}-${idx}`;

            return `
                <div class="attack-step" data-step="${idx}" style="margin-bottom: 0.75rem;">
                    <div class="step-header" style="display: flex; align-items: center; cursor: pointer; padding: 0.75rem; background: ${
                        idx === 0 ? 'var(--danger-color)15' :
                        idx === path.path.length - 1 ? 'var(--warning-color)15' :
                        'var(--nav-hover-bg)'
                    }; border-radius: 8px; border-left: 4px solid ${
                        idx === 0 ? 'var(--danger-color)' :
                        idx === path.path.length - 1 ? 'var(--warning-color)' :
                        'var(--primary-color)'
                    }; transition: all 0.2s;" onmouseover="this.style.background='var(--list-hover-bg)'" onmouseout="this.style.background='${
                        idx === 0 ? 'var(--danger-color)15' :
                        idx === path.path.length - 1 ? 'var(--warning-color)15' :
                        'var(--nav-hover-bg)'
                    }'">
                        <div style="background: var(--primary-color); color: black; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1rem; margin-right: 0.75rem; flex-shrink: 0;">
                            ${idx + 1}
                        </div>
                        <div style="flex: 1;">
                            <strong style="font-size: 1rem;">${node}</strong>
                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                ${stepTechniques.length} technique${stepTechniques.length !== 1 ? 's' : ''}
                                ${idx === 0 ? ' · <span style="color: var(--danger-color);">Entry Point</span>' : ''}
                                ${idx === path.path.length - 1 ? ' · <span style="color: var(--warning-color);">Target</span>' : ''}
                            </div>
                        </div>
                        <span class="expand-arrow" style="font-size: 1.25rem; color: var(--primary-color); transition: transform 0.2s;">▶</span>
                    </div>
                    <div id="${stepId}" class="step-details" style="display: none; margin-top: 0.5rem; padding: 1rem; background: var(--code-bg); border-radius: 8px; border: 1px solid var(--border-color);">
                        ${stepTechniques.length > 0 ? `
                            <h5 style="margin-bottom: 0.75rem; color: var(--primary-color); font-size: 0.9375rem;">Techniques Used at This Step:</h5>
                            ${stepTechniques.map(tech => `
                                <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; border-left: 3px solid var(--primary-color);">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                        <code style="font-weight: 700; color: var(--primary-color); font-size: 0.875rem;">${tech}</code>
                                        <a href="https://attack.mitre.org/techniques/${tech}/" target="_blank" class="btn-icon" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; text-decoration: none;">
                                            🔗 MITRE
                                        </a>
                                    </div>
                                    <div style="font-size: 0.875rem; color: var(--text-secondary);">
                                        Click "MITRE" link to view full technique details on MITRE ATT&CK website
                                    </div>
                                </div>
                            `).join('')}
                        ` : `
                            <p style="color: var(--text-tertiary); font-style: italic; font-size: 0.875rem;">
                                No specific techniques mapped to this step
                            </p>
                        `}
                    </div>
                </div>
                ${idx < path.path.length - 1 ? '<div style="margin-left: 16px; width: 2px; height: 16px; background: var(--border-color);"></div>' : ''}
            `;
        }).join('');

        const pathHtml = `
            <div style="margin-bottom: 1.5rem;">
                <div style="font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem;">${path.id}</div>
                <div style="padding: 0.75rem 1rem; background: ${
                    path.criticality_tier === 'HIGH' ? 'var(--danger-color)22' :
                    path.criticality_tier === 'MEDIUM' ? 'var(--warning-color)22' :
                    'var(--secondary-color)22'
                }; border-left: 4px solid ${
                    path.criticality_tier === 'HIGH' ? 'var(--danger-color)' :
                    path.criticality_tier === 'MEDIUM' ? 'var(--warning-color)' :
                    'var(--secondary-color)'
                }; border-radius: 6px;">
                    <strong>Criticality:</strong> ${path.criticality_tier || 'MEDIUM'}
                </div>
            </div>

            ${path.rationale ? `
                <div style="margin-bottom: 1.5rem;">
                    <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">Overall Analysis</h4>
                    <div style="padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid var(--primary-color); font-size: 0.875rem; line-height: 1.6;">
                        ${path.rationale}
                    </div>
                </div>
            ` : ''}

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">Step-by-Step Traversal</h4>
                <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1rem;">
                    Click on each step to see the techniques used
                </p>
                ${stepsHtml}
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">All Techniques (${path.techniques?.length || 0})</h4>
                <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                    ${(path.techniques || []).map(t => `
                        <span style="padding: 0.375rem 0.75rem; background: var(--nav-active-bg); border: 1px solid var(--border-color); border-radius: 6px; font-size: 0.875rem; font-family: monospace;">
                            ${t}
                        </span>
                    `).join('')}
                </div>
            </div>
        `;

        this.showRightPane(`Attack Path: ${path.entry} → ${path.target}`, pathHtml);

        // Add click handlers for steps
        setTimeout(() => {
            const steps = document.querySelectorAll('.attack-step');
            steps.forEach(step => {
                const header = step.querySelector('.step-header');
                const details = step.querySelector('.step-details');
                const arrow = step.querySelector('.expand-arrow');

                header.addEventListener('click', () => {
                    const isExpanded = details.style.display === 'block';
                    details.style.display = isExpanded ? 'none' : 'block';
                    arrow.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(90deg)';
                });
            });
        }, 100);
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

    async loadReportsTab() {
        if (!this.analysisData) return;

        const archName = this.analysisData.architecture_name;
        const listContainer = document.getElementById('reports-list');

        listContainer.innerHTML = '<p class="placeholder">Loading reports...</p>';

        try {
            const response = await fetch(`/api/v1/reports/${archName}`);
            if (!response.ok) {
                throw new Error('Failed to load reports');
            }

            const data = await response.json();
            this.renderReportsList(data);
        } catch (error) {
            console.error('Error loading reports:', error);
            listContainer.innerHTML = `
                <p class="placeholder" style="color: var(--danger-color);">
                    Failed to load reports: ${error.message}
                </p>
            `;
        }
    }

    renderReportsList(data) {
        const listContainer = document.getElementById('reports-list');

        if (!data.reports || data.reports.length === 0) {
            listContainer.innerHTML = '<p class="placeholder">No reports generated yet</p>';
            return;
        }

        listContainer.innerHTML = `
            <h4>Generated Reports (${data.count})</h4>
            <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 1rem;">
                Click on a report to view contents
            </p>
        `;

        // Group reports by type
        const mdReports = data.reports.filter(r => r.type === 'markdown');
        const jsonFiles = data.reports.filter(r => r.type === 'json');
        const otherFiles = data.reports.filter(r => r.type === 'text');

        // Render markdown reports
        if (mdReports.length > 0) {
            const section = document.createElement('div');
            section.style.marginBottom = '1.5rem';
            section.innerHTML = '<h5 style="margin-bottom: 0.75rem; color: var(--primary-color);">📄 Analysis Reports</h5>';

            mdReports.forEach(report => {
                const item = this.createReportItem(report, data.architecture);
                section.appendChild(item);
            });

            listContainer.appendChild(section);
        }

        // Render JSON files
        if (jsonFiles.length > 0) {
            const section = document.createElement('div');
            section.style.marginBottom = '1.5rem';
            section.innerHTML = '<h5 style="margin-bottom: 0.75rem; color: var(--primary-color);">📊 Data Files</h5>';

            jsonFiles.forEach(report => {
                const item = this.createReportItem(report, data.architecture);
                section.appendChild(item);
            });

            listContainer.appendChild(section);
        }
    }

    createReportItem(report, archName) {
        const item = document.createElement('div');
        item.className = 'list-item';

        const sizeKB = (report.size / 1024).toFixed(1);
        const icon = report.type === 'markdown' ? '📝' :
                    report.type === 'json' ? '📊' : '📄';

        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-weight: 600;">${icon} ${report.filename}</div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem;">
                        ${sizeKB} KB · ${report.type}
                    </div>
                </div>
                <button class="btn-icon" style="padding: 0.25rem 0.5rem;" title="Download">
                    ⬇
                </button>
            </div>
        `;

        item.addEventListener('click', async (e) => {
            // Remove active from all items
            document.querySelectorAll('#reports-list .list-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');

            await this.loadReportContent(archName, report);
        });

        // Download button
        const downloadBtn = item.querySelector('.btn-icon');
        downloadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            window.open(report.url, '_blank');
        });

        return item;
    }

    async loadReportContent(archName, report) {
        // Determine if file is large (needs streaming)
        const isLarge = report.size > 50000; // 50KB threshold
        const sizeKB = (report.size / 1024).toFixed(1);

        try {
            // Show right pane with loading state first
            const loadingContent = `
                <div style="margin-bottom: 1rem;">
                    <a href="${report.url}" target="_blank" class="btn-primary" style="display: inline-block; text-decoration: none;">
                        ⬇ Download ${report.type === 'json' ? 'JSON' : 'Report'}
                    </a>
                    <span style="margin-left: 1rem; color: var(--text-secondary); font-size: 0.875rem;">
                        ${sizeKB} KB ${isLarge ? '(Streaming...)' : ''}
                    </span>
                </div>
                <div id="streaming-container" style="
                    padding: 1rem;
                    background: var(--code-bg);
                    border-radius: 8px;
                    border: 1px solid var(--border-color);
                    max-height: 70vh;
                    overflow-y: auto;
                ">
                </div>
            `;

            this.showRightPane(report.filename, loadingContent);

            // Fetch content
            const response = await fetch(`/api/v1/reports/${archName}/files/${report.filename}`);
            if (!response.ok) {
                throw new Error('Failed to load report content');
            }

            // Initialize streaming renderer
            const renderer = new StreamingRenderer('streaming-container');

            if (report.type === 'json') {
                const data = await response.json();

                if (isLarge) {
                    // Stream large JSON line-by-line
                    await renderer.streamJSON(data, 5);
                } else {
                    // Render small JSON immediately
                    const jsonStr = JSON.stringify(data, null, 2);
                    const container = document.getElementById('streaming-container');
                    container.innerHTML = `<pre style="margin: 0;"><code class="language-json">${this.escapeHtml(jsonStr)}</code></pre>`;

                    if (window.hljs) {
                        const codeBlock = container.querySelector('code');
                        if (codeBlock) hljs.highlightElement(codeBlock);
                    }
                }
            } else {
                // Markdown
                const text = await response.text();

                if (isLarge) {
                    // Stream large markdown
                    await renderer.streamMarkdown(text, true);
                } else {
                    // Render small markdown immediately
                    const container = document.getElementById('streaming-container');
                    container.style.padding = '1.5rem';
                    container.style.background = 'var(--card-bg)';

                    if (window.marked) {
                        container.innerHTML = marked.parse(text);
                    } else {
                        container.innerHTML = `<pre style="white-space: pre-wrap; word-wrap: break-word;">${this.escapeHtml(text)}</pre>`;
                    }
                }
            }
        } catch (error) {
            console.error('Error loading report content:', error);
            this.showRightPane('Error', `<p style="color: var(--danger-color);">Failed to load report: ${error.message}</p>`);
        }
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

    async showArtifact(artifact) {
        const jsonStr = JSON.stringify(artifact.data, null, 2);
        const sizeKB = (jsonStr.length / 1024).toFixed(1);
        const isLarge = jsonStr.length > 50000;

        // Show right pane with container
        const content = `
            <div style="margin-bottom: 1rem;">
                <span style="color: var(--text-secondary); font-size: 0.875rem;">
                    ${sizeKB} KB ${isLarge ? '(Streaming...)' : ''}
                </span>
            </div>
            <div id="streaming-container" style="
                padding: 1rem;
                background: var(--code-bg);
                border-radius: 8px;
                border: 1px solid var(--border-color);
                overflow-x: auto;
                max-height: 70vh;
                overflow-y: auto;
            ">
            </div>
        `;
        this.showRightPane(artifact.name, content);

        // Initialize streaming renderer
        const renderer = new StreamingRenderer('streaming-container');

        if (isLarge) {
            // Stream large JSON
            await renderer.streamJSON(artifact.data, 5);
        } else {
            // Render small JSON immediately
            const container = document.getElementById('streaming-container');
            container.innerHTML = `<pre style="margin: 0;"><code class="language-json">${this.escapeHtml(jsonStr)}</code></pre>`;

            if (window.hljs) {
                const codeBlock = container.querySelector('code');
                if (codeBlock) hljs.highlightElement(codeBlock);
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
