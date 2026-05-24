// ThreatAssessor Dashboard - Main Controller

class Dashboard {
    constructor() {
        this.analysisData = null;
        this.currentTab = 'overview';
        this.sseClient = null;
        this.uploadedFile = null;
        this.techniqueNamesCache = {}; // Cache for technique names

        this.init();
    }

    init() {
        // Initialize tab navigation
        this.initTabs();

        // Initialize upload form
        this.initUpload();

        // Initialize settings
        this.initSettings();

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

    initSettings() {
        const settingsBtn = document.getElementById('settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => this.showSettings());
        }
    }

    async showSettings() {
        const currentKey = localStorage.getItem('tm_api_key');
        const hasKey = currentKey ? '✅ Saved' : '❌ Not Set';

        const newKey = prompt(
            '🔑 ThreatAssessor API Settings\n\n' +
            `Current API Key: ${hasKey}\n\n` +
            'Enter new API key (or leave empty to keep current):\n\n' +
            'Get your API key from the .env file:\n' +
            'grep "^API_KEY=" .env | cut -d\'=\' -f2',
            currentKey || ''
        );

        if (newKey !== null && newKey.trim() !== '') {
            localStorage.setItem('tm_api_key', newKey.trim());
            alert('✅ API key saved!\n\nYou can now upload architectures for analysis.');
        } else if (newKey === '') {
            // User wants to clear the key
            const confirmClear = confirm('Clear saved API key?');
            if (confirmClear) {
                localStorage.removeItem('tm_api_key');
                alert('API key cleared. You will be prompted again on next upload.');
            }
        }
    }

    initRightPane() {
        const closeBtn = document.getElementById('right-pane-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hideRightPane());
        }
    }

    initOverviewSubtabs() {
        const subtabs = document.querySelectorAll('.overview-subtab');
        subtabs.forEach(subtab => {
            subtab.addEventListener('click', async () => {
                const subtabName = subtab.dataset.subtab;

                // Update button styles
                subtabs.forEach(btn => {
                    const isActive = btn.dataset.subtab === subtabName;
                    btn.style.background = isActive ? 'var(--primary-color)' : 'transparent';
                    btn.style.color = isActive ? 'var(--button-text-color)' : 'var(--text-color)';
                    btn.style.borderBottom = isActive ? 'none' : '2px solid transparent';
                    btn.classList.toggle('active', isActive);
                });

                // Update content visibility
                document.querySelectorAll('.overview-subtab-content').forEach(content => {
                    const isActive = content.id === `overview-${subtabName}`;
                    content.style.display = isActive ? 'block' : 'none';
                });

                // Render architecture diagram when switched to (if not already rendered)
                if (subtabName === 'arch-diagram' && this.uploadedFile && !this.diagramRendered) {
                    await this.renderArchitectureDiagram();
                    this.diagramRendered = true;
                }
            });
        });
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
        if (rightPane) {
            rightPane.classList.remove('visible');
            // Reset inline styles that may have been set by resize
            rightPane.style.width = '';
        }
    }

    initTabs() {
        const navTabs = document.querySelectorAll('.nav-tab');
        navTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                this.switchTab(tabName);
            });
        });

        // Initialize overview subtabs
        this.initOverviewSubtabs();
    }

    switchTab(tabName) {
        // Hide right pane when switching tabs
        this.hideRightPane();

        // Update nav tabs
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab panes
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.dataset.tab === tabName);
        });

        this.currentTab = tabName;

        // Update status message
        const tabNames = {
            'overview': 'Overview',
            'attacks': 'Threat Paths',
            'controls': 'Mitigations',
            'hardening': 'Visualise',
            'expert-review': 'Expert Review',
            'reports': 'Reports',
            'raw-data': 'Raw Data'
        };
        this.updateStatusMessage(`📂 Viewing ${tabNames[tabName] || tabName}`);

        // Load tab-specific data if analysis is complete
        if (this.analysisData) {
            this.loadTabData(tabName);
        }
    }

    initUpload() {
        const uploadForm = document.getElementById('upload-form');
        const uploadBtn = document.getElementById('upload-btn');
        const newAnalysisBtn = document.getElementById('new-analysis-btn');
        const fileInput = document.getElementById('file-input');
        const dropZone = document.getElementById('drop-zone');

        // Upload button click
        uploadBtn.addEventListener('click', () => {
            fileInput.click();
        });

        // New analysis button click
        if (newAnalysisBtn) {
            newAnalysisBtn.addEventListener('click', () => {
                this.resetForNewAnalysis();
            });
        }

        // Refresh dashboard button click
        const refreshDashboardBtn = document.getElementById('refresh-dashboard-btn');
        if (refreshDashboardBtn) {
            refreshDashboardBtn.addEventListener('click', () => {
                this.refreshDashboard();
            });
        }

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
        console.log('[DEBUG] startAnalysis() called');
        const fileInput = document.getElementById('file-input');

        console.log('[DEBUG] File input:', fileInput);
        console.log('[DEBUG] Files:', fileInput.files);

        if (!fileInput.files.length) {
            alert('Please select an architecture file');
            return;
        }

        const file = fileInput.files[0];
        console.log('[DEBUG] Selected file:', file.name);

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
        formData.append('include_validation', 'true');

        console.log('[DEBUG] Creating SSEClient for /api/v1/analyze-stream');
        this.sseClient = new SSEClient('/api/v1/analyze-stream', formData);
        this.sseClient.on('progress', (data) => this.handleProgress(data));
        this.sseClient.on('patterns_detected', (data) => this.handlePatternsDetected(data));
        this.sseClient.on('threat_scores', (data) => this.handleThreatScores(data));
        this.sseClient.on('attack_path', (data) => this.handleAttackPath(data));
        this.sseClient.on('complete', async (data) => await this.handleComplete(data));
        this.sseClient.on('error', (data) => this.handleError(data));

        console.log('[DEBUG] Connecting to SSE stream...');
        await this.sseClient.connect();
        console.log('[DEBUG] SSE connection complete');
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

    async handleComplete(data) {
        this.analysisData = data.data;
        console.log('[DEBUG] handleComplete - data.data:', this.analysisData);
        console.log('[DEBUG] handleComplete - architecture_name:', this.analysisData.architecture_name);

        // Use complete attack paths from final analysis data (not just streamed 3)
        if (this.analysisData.analysis && this.analysisData.analysis.expected_attack_paths) {
            this.attackPaths = this.analysisData.analysis.expected_attack_paths;
            console.log(`✅ Loaded ${this.attackPaths.length} complete attack paths`);
        }

        // Fetch original MMD content from Reports API (before.mmd)
        const archName = this.analysisData.architecture_name || this.analysisData.architecture;
        console.log('[DEBUG] Resolved architecture name:', archName);

        if (archName) {
            try {
                console.log('[DEBUG] Fetching before.mmd from Reports API...');
                const response = await fetch(`/api/v1/reports/${archName}/files/before.mmd`);
                console.log('[DEBUG] Fetch response status:', response.status);
                if (response.ok) {
                    this.originalMmdContent = await response.text();
                    console.log('[DEBUG] Original MMD content loaded:', this.originalMmdContent.length, 'characters');
                } else {
                    console.error('[DEBUG] Failed to fetch before.mmd:', response.status);
                }
            } catch (err) {
                console.error('[DEBUG] Error fetching before.mmd:', err);
            }
        } else {
            console.error('[DEBUG] No architecture name found in analysisData');
        }

        // Update status
        this.updateProgress(100, 'Analysis complete!', 0);
        this.updateStages('complete');

        // Show "New Analysis" button, hide "Upload" button
        const uploadBtn = document.getElementById('upload-btn');
        const newAnalysisBtn = document.getElementById('new-analysis-btn');
        if (uploadBtn) uploadBtn.style.display = 'none';
        if (newAnalysisBtn) newAnalysisBtn.style.display = 'inline-block';

        // Show Expert Review tab if MoE data exists for this architecture
        if (archName) {
            fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`, { method: 'HEAD' })
                .then(r => {
                    if (r.ok) {
                        const tab = document.querySelector('.nav-tab[data-tab="expert-review"]');
                        if (tab) tab.style.display = 'block';
                    }
                })
                .catch(() => {});
        }

        // Load current tab data
        this.loadTabData(this.currentTab);
    }

    resetForNewAnalysis() {
        // Reset state
        this.analysisData = null;
        this.uploadedFile = null;
        this.threatScores = null;
        this.attackPaths = null;
        this.patterns = null;

        // Hide results, show upload form
        document.getElementById('upload-form-container').style.display = 'block';
        document.getElementById('tab-content').style.display = 'none';

        // Reset buttons
        const uploadBtn = document.getElementById('upload-btn');
        const newAnalysisBtn = document.getElementById('new-analysis-btn');
        if (uploadBtn) uploadBtn.style.display = 'inline-block';
        if (newAnalysisBtn) newAnalysisBtn.style.display = 'none';

        // Reset progress
        this.updateProgress(0, 'Ready to analyze architecture');
        this.updateStages('parsing');

        // Reset file input
        const fileInput = document.getElementById('file-input');
        if (fileInput) fileInput.value = '';

        // Reset pattern badges
        const patternBadges = document.getElementById('pattern-badges');
        if (patternBadges) {
            patternBadges.innerHTML = '<span class="badge badge-disabled">No analysis yet</span>';
        }

        // Hide Expert Review tab until MoE data confirmed
        const expertReviewTab = document.querySelector('.nav-tab[data-tab="expert-review"]');
        if (expertReviewTab) expertReviewTab.style.display = 'none';

        // Hide right pane
        this.hideRightPane();
    }

    refreshDashboard() {
        // Clear browser cache and reload page
        if (confirm('This will clear the dashboard cache and reload. Any unsaved work will be lost. Continue?')) {
            // Clear localStorage
            localStorage.clear();

            // Clear sessionStorage
            sessionStorage.clear();

            // Force reload from server (bypass cache)
            window.location.reload(true);
        }
    }

    handleError(data) {
        const { message, detail } = data;

        // Check if it's an API key error
        const isApiKeyError = message.includes('API key') ||
                             message.includes('401') ||
                             message.includes('Unauthorized') ||
                             detail?.includes('Invalid API key');

        if (isApiKeyError) {
            const retry = confirm(
                '❌ API Key Error\n\n' +
                (detail || message) + '\n\n' +
                'Would you like to update your API key now?'
            );

            if (retry) {
                this.showSettings();
                // Don't reset form - let user retry after setting key
                return;
            }
        } else {
            alert(`❌ Analysis Failed\n\n${message}\n\n${detail || ''}`);
        }

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

    updateStatusMessage(message) {
        const statusMessage = document.getElementById('status-message');
        if (statusMessage) {
            statusMessage.textContent = message;
        }
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
            case 'attacks':
                this.loadAttacksTab();
                break;
            case 'controls':
                this.loadControlsTab();
                break;
            case 'hardening':
                this.loadHardeningTab();
                break;
            case 'expert-review':
                this.loadExpertReviewTab();
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
        // Don't render architecture diagram immediately - it's in a hidden tab
        // Will render on first click to Architecture Diagram subtab
        this.diagramRendered = false;
    }

    async renderArchitectureDiagram() {
        const container = document.getElementById('arch-diagram');
        if (!container || !this.uploadedFile) return;

        try {
            // Read uploaded file
            const reader = new FileReader();
            reader.onload = async (e) => {
                let mmdContent = e.target.result;
                this.originalMmdContent = mmdContent; // Store original

                // Create container for mermaid
                container.innerHTML = `
                    <div style="margin-bottom: 0.5rem; display: flex; gap: 0.5rem; justify-content: flex-start; align-items: center; flex-wrap: wrap;">
                        <div style="display: flex; gap: 0.25rem;">
                            <button id="zoom-in" class="btn-icon" title="Zoom In">🔍+</button>
                            <button id="zoom-out" class="btn-icon" title="Zoom Out">🔍−</button>
                            <button id="zoom-reset" class="btn-icon" title="Reset Zoom">↺</button>
                        </div>
                        <div style="width: 1px; height: 24px; background: var(--border-color);"></div>
                        <div style="display: flex; gap: 0.25rem;">
                            <button id="orient-tb" class="btn-icon" title="Top to Bottom (Portrait)">⬇️ TB</button>
                            <button id="orient-lr" class="btn-icon" title="Left to Right (Landscape)">➡️ LR</button>
                        </div>
                        <div style="width: 1px; height: 24px; background: var(--border-color);"></div>
                        <div style="display: flex; gap: 0.25rem;">
                            <button id="fit-width" class="btn-icon" title="Fit to Width">↔️</button>
                            <button id="fit-height" class="btn-icon" title="Fit to Height">↕️</button>
                        </div>
                    </div>
                    <div id="mermaid-container" style="overflow: auto; max-height: calc(100vh - 280px); width: 100%; padding: 1rem; background: var(--code-bg); border-radius: 8px; border: 1px solid var(--border-color);">
                        <div class="mermaid" id="mermaid-diagram">${mmdContent}</div>
                    </div>
                `;

                // Render mermaid
                if (window.mermaid) {
                    await mermaid.run({
                        querySelector: '#mermaid-container .mermaid'
                    });

                    // Auto-fit diagram to 50% initial size for better visibility
                    setTimeout(() => {
                        const mermaidContainer = document.getElementById('mermaid-container');
                        const svg = mermaidContainer.querySelector('svg');
                        if (svg) {
                            // Store original dimensions
                            this.originalSvgWidth = svg.getAttribute('width') || svg.getBBox().width;
                            this.originalSvgHeight = svg.getAttribute('height') || svg.getBBox().height;

                            // Set SVG to 50% of original size initially
                            svg.setAttribute('width', this.originalSvgWidth * 0.5);
                            svg.setAttribute('height', this.originalSvgHeight * 0.5);
                            svg.style.maxWidth = 'none';
                            svg.style.display = 'block';
                        }
                    }, 100);

                    // Controls
                    let scale = 0.5; // Start at 50%
                    const mermaidContainer = document.getElementById('mermaid-container');
                    // After mermaid.run(), the diagram might be SVG or in the .mermaid div
                    const getDiagram = () => mermaidContainer.querySelector('svg') || mermaidContainer.querySelector('.mermaid');

                    // Zoom controls
                    const zoomInBtn = document.getElementById('zoom-in');
                    const zoomOutBtn = document.getElementById('zoom-out');
                    const zoomResetBtn = document.getElementById('zoom-reset');

                    if (zoomInBtn) {
                        zoomInBtn.addEventListener('click', () => {
                            scale = Math.min(scale + 0.2, 3);
                            const svg = getDiagram();
                            if (svg && this.originalSvgWidth) {
                                svg.setAttribute('width', this.originalSvgWidth * scale);
                                svg.setAttribute('height', this.originalSvgHeight * scale);
                            }
                        });
                    }

                    if (zoomOutBtn) {
                        zoomOutBtn.addEventListener('click', () => {
                            scale = Math.max(scale - 0.2, 0.3);
                            const svg = getDiagram();
                            if (svg && this.originalSvgWidth) {
                                svg.setAttribute('width', this.originalSvgWidth * scale);
                                svg.setAttribute('height', this.originalSvgHeight * scale);
                            }
                        });
                    }

                    if (zoomResetBtn) {
                        zoomResetBtn.addEventListener('click', () => {
                            scale = 0.5; // Reset to 50%
                            const svg = getDiagram();
                            if (svg && this.originalSvgWidth) {
                                svg.setAttribute('width', this.originalSvgWidth * scale);
                                svg.setAttribute('height', this.originalSvgHeight * scale);
                            }
                            mermaidContainer.scrollTop = 0;
                            mermaidContainer.scrollLeft = 0;
                        });
                    }

                    // Orientation controls
                    const orientTB = document.getElementById('orient-tb');
                    const orientLR = document.getElementById('orient-lr');

                    if (orientTB) {
                        orientTB.addEventListener('click', async () => {
                            await this.changeDiagramOrientation('TB');
                        });
                    }

                    if (orientLR) {
                        orientLR.addEventListener('click', async () => {
                            await this.changeDiagramOrientation('LR');
                        });
                    }

                    // Fit controls
                    const fitWidth = document.getElementById('fit-width');
                    const fitHeight = document.getElementById('fit-height');

                    if (fitWidth) {
                        fitWidth.addEventListener('click', () => {
                            const svg = getDiagram();
                            if (svg && this.originalSvgWidth) {
                                const containerWidth = mermaidContainer.clientWidth - 32;
                                scale = containerWidth / this.originalSvgWidth;
                                svg.setAttribute('width', this.originalSvgWidth * scale);
                                svg.setAttribute('height', this.originalSvgHeight * scale);
                            }
                        });
                    }

                    if (fitHeight) {
                        fitHeight.addEventListener('click', () => {
                            const svg = getDiagram();
                            if (svg && this.originalSvgHeight) {
                                const containerHeight = mermaidContainer.clientHeight - 32;
                                scale = containerHeight / this.originalSvgHeight;
                                svg.setAttribute('width', this.originalSvgWidth * scale);
                                svg.setAttribute('height', this.originalSvgHeight * scale);
                            }
                        });
                    }
                }
            };

            reader.readAsText(this.uploadedFile);
        } catch (error) {
            console.error('Error rendering architecture diagram:', error);
            container.innerHTML = '<p class="placeholder">Failed to render architecture diagram</p>';
        }
    }

    async changeDiagramOrientation(direction) {
        const container = document.getElementById('mermaid-container');
        if (!container || !this.originalMmdContent) return;

        // Modify mermaid content to change direction
        let mmdContent = this.originalMmdContent;

        // Replace flowchart direction
        if (mmdContent.includes('graph TD') || mmdContent.includes('graph TB')) {
            mmdContent = mmdContent.replace(/graph (TD|TB|LR|RL)/g, `graph ${direction}`);
        } else if (mmdContent.includes('flowchart TD') || mmdContent.includes('flowchart TB') || mmdContent.includes('flowchart LR')) {
            mmdContent = mmdContent.replace(/flowchart (TD|TB|LR|RL)/g, `flowchart ${direction}`);
        } else {
            // If no direction specified, add it
            mmdContent = mmdContent.replace(/^(graph|flowchart)/, `$1 ${direction}`);
        }

        // Update container with new orientation
        container.innerHTML = `<div class="mermaid" id="mermaid-diagram">${mmdContent}</div>`;

        // Re-render
        if (window.mermaid) {
            await mermaid.run({
                querySelector: '#mermaid-container .mermaid'
            });
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
                        r >= 70 ? '#e74c3c' : r >= 50 ? '#f39c12' : '#f1c40f'
                    ),
                    borderColor: risks.map(r =>
                        r >= 70 ? '#c0392b' : r >= 50 ? '#d68910' : '#d4ac0d'
                    ),
                    borderWidth: 2
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
                                { text: 'High Risk (70-100)', fillStyle: '#e74c3c', strokeStyle: '#e74c3c', fontColor: isDark ? '#ffffff' : '#000000' },
                                { text: 'Medium Risk (50-69)', fillStyle: '#f39c12', strokeStyle: '#f39c12', fontColor: isDark ? '#ffffff' : '#000000' },
                                { text: 'Low Risk (0-49)', fillStyle: '#f1c40f', strokeStyle: '#f1c40f', fontColor: isDark ? '#ffffff' : '#000000' }
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
                            color: isDark ? '#d0d0d0' : '#4a4a4a',
                            font: {
                                size: 12,
                                weight: '500'
                            }
                        },
                        grid: {
                            color: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.1)',
                            lineWidth: 1
                        }
                    },
                    x: {
                        ticks: {
                            color: isDark ? '#d0d0d0' : '#4a4a4a',
                            font: {
                                size: 12,
                                weight: '500'
                            }
                        },
                        grid: {
                            color: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.1)',
                            lineWidth: 1
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
            <div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 8px; margin-bottom: 1rem;">
                <h5 style="margin-bottom: 0.5rem; font-size: 0.875rem; font-weight: 700;">📖 Legend</h5>
                <div style="font-size: 0.8125rem; line-height: 1.6;">
                    <div><strong style="color: var(--danger-color);">HIGH</strong> - Severity score &gt; 0.7 (critical paths requiring immediate attention)</div>
                    <div><strong style="color: var(--warning-color);">MEDIUM</strong> - Severity score 0.4-0.7 (significant threats)</div>
                    <div><strong style="color: #f1c40f;">LOW</strong> - Severity score &lt; 0.4 (monitor and harden)</div>
                    <div style="margin-top: 0.5rem; color: var(--text-tertiary);">
                        <em>Severity is based on hop count, techniques, and attack surface exposure</em>
                    </div>
                </div>
            </div>
            <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 1rem;">
                Click on a path to see summary. Click "View Step-by-Step Details" to see full analysis.
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
                        <div style="padding: 0.25rem 0.75rem; background: ${criticalityColor}22; color: ${criticalityColor}; border-radius: 8px; font-weight: 700; font-size: 0.75rem;" title="Severity score: ${path.criticality_score ? path.criticality_score.toFixed(2) : 'N/A'}">
                            ${path.criticality_tier || 'MEDIUM'} SEVERITY
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

            // Click anywhere on header to show details in right pane
            const header = item.querySelector('.path-header');
            const summary = item.querySelector('.path-summary');
            const expandIcon = item.querySelector('.expand-icon');

            header.addEventListener('click', (e) => {
                // Remove active class from all items
                listContainer.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                item.classList.add('active');

                // Show details in right pane
                this.showAttackPathDetail(path);
            });

            // Keep button for explicit action (same as clicking header)
            const detailBtn = item.querySelector('.btn-primary');
            detailBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                header.click(); // Trigger same behavior as header click
            });

            listContainer.appendChild(item);
        });
    }

    async showAttackPathDetail(path) {
        // Get per-node techniques
        const perNodeTechniques = path.per_node_techniques || {};

        // Fetch technique names
        const allTechniques = path.techniques || [];
        const techniqueNames = await this.fetchTechniqueNames(allTechniques);

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
                        <div style="background: var(--primary-color); color: var(--button-text-color); width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1rem; margin-right: 0.75rem; flex-shrink: 0;">
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
                            ${stepTechniques.map(tech => {
                                const techName = techniqueNames[tech] || 'Loading...';
                                return `
                                <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; border-left: 3px solid var(--primary-color);">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem; margin-bottom: 0.5rem;">
                                        <div style="flex: 1;">
                                            <div>
                                                <code style="font-weight: 700; color: var(--primary-color); font-size: 0.875rem;">${tech}</code>
                                                <span style="margin-left: 0.5rem; color: var(--text-color); font-size: 0.875rem; font-weight: 600;">- ${techName}</span>
                                            </div>
                                        </div>
                                        <a href="https://attack.mitre.org/techniques/${tech}/" target="_blank" class="btn-icon" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; text-decoration: none; flex-shrink: 0;">
                                            🔗 MITRE
                                        </a>
                                    </div>
                                    <div style="font-size: 0.8125rem; color: var(--text-secondary);">
                                        Click MITRE link for full details and mitigation recommendations
                                    </div>
                                </div>
                            `;
                            }).join('')}
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
                    <strong>Severity:</strong> ${path.criticality_tier || 'MEDIUM'}
                </div>
            </div>

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
        const tableContainer = document.getElementById('controls-table');

        if (!this.analysisData) {
            tableContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        // Extract control recommendations from nested analysis object
        const analysis = this.analysisData.analysis || {};
        const controlRecs = analysis.control_recommendations || [];

        if (controlRecs.length === 0) {
            tableContainer.innerHTML = `
                <p class="placeholder">
                    No control recommendations available in current analysis data.
                </p>
            `;
            return;
        }

        // Render control recommendations with checkbox filter and legend
        tableContainer.innerHTML = `
            <div style="margin-bottom: 1rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <label style="font-size: 0.875rem; font-weight: 600; color: var(--text-color);">Filter by Priority:</label>
                    <div style="display: flex; gap: 0.5rem;">
                        <button id="select-all-filter" style="padding: 0.375rem 0.75rem; border-radius: 6px; background: var(--secondary-color)22; color: var(--secondary-color); border: 1px solid var(--secondary-color); cursor: pointer; font-size: 0.8125rem; font-weight: 600;">
                            Select All
                        </button>
                        <button id="reset-filter" style="padding: 0.375rem 0.75rem; border-radius: 6px; background: var(--warning-color)22; color: var(--warning-color); border: 1px solid var(--warning-color); cursor: pointer; font-size: 0.8125rem; font-weight: 600;">
                            Clear All
                        </button>
                    </div>
                </div>
                <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; font-size: 0.875rem;">
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" class="priority-checkbox" value="critical" checked style="cursor: pointer;">
                        <span style="color: var(--danger-color); font-weight: 600;">CRITICAL</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" class="priority-checkbox" value="high" checked style="cursor: pointer;">
                        <span style="color: var(--warning-color); font-weight: 600;">HIGH</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" class="priority-checkbox" value="medium" checked style="cursor: pointer;">
                        <span style="color: var(--primary-color); font-weight: 600;">MEDIUM</span>
                    </label>
                </div>
                <div style="margin-top: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">
                    Showing <strong id="control-count">${controlRecs.length}</strong> of ${controlRecs.length} controls
                </div>
            </div>
            <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid var(--primary-color);">
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem; color: var(--primary-color);">📖 Legend - Mitigation Priority</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; font-size: 0.875rem;">
                    <div>
                        <strong style="color: var(--danger-color);">CRITICAL</strong> - Addresses high-risk threats (immediate action required)
                    </div>
                    <div>
                        <strong style="color: var(--warning-color);">HIGH</strong> - Important security improvements (high priority)
                    </div>
                    <div>
                        <strong style="color: var(--primary-color);">MEDIUM</strong> - Recommended enhancements (plan for deployment)
                    </div>
                </div>
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
                    <strong style="color: var(--text-color);">Score:</strong> <span style="color: var(--text-secondary);">Combined metric from threat severity (RAPIDS), attack path coverage, and technique count</span>
                </div>
                <div style="margin-top: 0.5rem;">
                    <strong style="color: var(--text-color);">Implementation:</strong> <span style="color: var(--text-secondary);">Shown when control has specific technical implementation details (Type, Layer, Placement). Generic controls show rationale only.</span>
                </div>
                <div style="margin-top: 0.5rem;">
                    <strong style="color: var(--text-color);">Click any control</strong> <span style="color: var(--text-secondary);">to view detailed rationale, affected nodes, MITRE mappings in right pane</span>
                </div>
            </div>
            <div id="controls-list"></div>
        `;

        const controlsList = tableContainer.querySelector('#controls-list');

        const renderControls = (selectedPriorities = ['critical', 'high', 'medium']) => {
            controlsList.innerHTML = '';

            const filteredControls = controlRecs.filter(c => selectedPriorities.includes(c.priority));

            // Update count
            document.getElementById('control-count').textContent = filteredControls.length;

            filteredControls.forEach(control => {
                const priorityColor =
                    control.priority === 'critical' ? 'var(--danger-color)' :
                    control.priority === 'high' ? 'var(--warning-color)' :
                    'var(--primary-color)';

                const card = document.createElement('div');
                card.className = 'list-item';
                card.dataset.priority = control.priority;
                card.style.cssText = `
                    padding: 1rem;
                    margin-bottom: 0.75rem;
                    background: var(--card-bg);
                    border-radius: 8px;
                    border-left: 4px solid ${priorityColor};
                    cursor: pointer;
                    transition: all 0.2s;
                `;

                card.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                                <strong style="font-size: 1rem; color: var(--primary-color);">${control.control}</strong>
                                <span style="padding: 0.25rem 0.75rem; background: ${priorityColor}22; color: ${priorityColor}; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">
                                    ${control.priority}
                                </span>
                            </div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
                                ${control.rationale}
                            </div>
                            <div style="display: flex; gap: 1rem; font-size: 0.8125rem; color: var(--text-tertiary); margin-bottom: 0.5rem;">
                                <span>📍 ${control.attack_paths ? control.attack_paths.length : 0} attack paths</span>
                                <span>🎯 ${control.techniques ? control.techniques.length : 0} techniques</span>
                                <span>🛡️ ${control.mitigations ? control.mitigations.length : 0} MITRE mitigations</span>
                            </div>
                            ${control.control_type ? `
                                <div style="font-size: 0.8125rem; color: var(--text-tertiary); padding-top: 0.5rem; border-top: 1px solid var(--border-color);">
                                    <strong>Implementation:</strong> ${control.control_type}${control.layer ? ` | ${control.layer}` : ''}${control.placement ? ` | ${control.placement}` : ''}
                                </div>
                            ` : ''}
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.25rem; font-weight: 700; color: ${priorityColor};">
                                ${control.score ? control.score.toFixed(1) : 'N/A'}
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">
                                score
                            </div>
                        </div>
                    </div>
                `;

                card.addEventListener('click', () => {
                    // Remove active from all
                    controlsList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                    card.classList.add('active');
                    this.showControlDetail(control);
                });

                controlsList.appendChild(card);
            });
        };

        // Initial render
        renderControls(['critical', 'high', 'medium']);

        // Add checkbox listeners
        const checkboxes = tableContainer.querySelectorAll('.priority-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                const selected = Array.from(checkboxes)
                    .filter(cb => cb.checked)
                    .map(cb => cb.value);
                renderControls(selected);
            });
        });

        // Add button listeners
        const selectAllBtn = tableContainer.querySelector('#select-all-filter');
        selectAllBtn.addEventListener('click', () => {
            checkboxes.forEach(cb => cb.checked = true);
            renderControls(['critical', 'high', 'medium']);
        });

        const resetBtn = tableContainer.querySelector('#reset-filter');
        resetBtn.addEventListener('click', () => {
            checkboxes.forEach(cb => cb.checked = false);
            renderControls([]);
        });
    }

    async showControlDetail(control) {
        const rightPane = document.getElementById('right-pane');
        const rightPaneContent = document.getElementById('right-pane-content');

        if (!rightPane || !rightPaneContent) return;

        const priorityColor =
            control.priority === 'critical' ? 'var(--danger-color)' :
            control.priority === 'high' ? 'var(--warning-color)' :
            'var(--primary-color)';

        // Fetch technique names
        const techniqueNames = await this.fetchTechniqueNames(control.techniques || []);

        rightPaneContent.innerHTML = `
            <h3 style="color: ${priorityColor};">${control.control}</h3>
            <div style="margin-bottom: 1.5rem;">
                <span style="padding: 0.25rem 0.75rem; background: ${priorityColor}22; color: ${priorityColor}; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">
                    ${control.priority} PRIORITY
                </span>
                <span style="margin-left: 0.5rem; padding: 0.25rem 0.75rem; background: var(--nav-hover-bg); border-radius: 12px; font-size: 0.75rem;">
                    Score: ${control.score ? control.score.toFixed(1) : 'N/A'}
                </span>
            </div>

            <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid ${priorityColor};">
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem;">📋 Rationale</h4>
                <p style="margin-bottom: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">
                    ${control.rationale}
                </p>
                ${control.detailed_rationale ? `
                    <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
                        ${control.detailed_rationale.map(r => `
                            <div style="font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
                                • ${r}
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem; color: var(--warning-color);">🎯 Attack Paths Affected</h4>
                ${control.attack_paths && control.attack_paths.length > 0 ? `
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        ${control.attack_paths.map(pathIdx => `
                            <span style="padding: 0.5rem 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; font-size: 0.875rem;">
                                AP-${pathIdx + 1}
                            </span>
                        `).join('')}
                    </div>
                    <p style="margin-top: 0.75rem; font-size: 0.8125rem; color: var(--text-tertiary);">
                        This control addresses vulnerabilities in ${control.attack_paths.length} attack path${control.attack_paths.length > 1 ? 's' : ''}
                    </p>
                ` : '<p style="color: var(--text-tertiary); font-style: italic;">No specific paths mapped</p>'}
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem; color: var(--primary-color);">🔬 MITRE ATT&CK Techniques</h4>
                ${control.techniques && control.techniques.length > 0 ? `
                    ${control.techniques.map(tech => `
                        <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; border-left: 3px solid var(--primary-color);">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem;">
                                <div style="flex: 1;">
                                    <code style="font-weight: 700; color: var(--primary-color); font-size: 0.875rem;">${tech}</code>
                                    <span style="margin-left: 0.5rem; color: var(--text-color); font-size: 0.875rem; font-weight: 600;">- ${techniqueNames[tech] || tech}</span>
                                </div>
                                <a href="https://attack.mitre.org/techniques/${tech}/" target="_blank" class="btn-icon" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; text-decoration: none; flex-shrink: 0;">
                                    🔗 MITRE
                                </a>
                            </div>
                        </div>
                    `).join('')}
                ` : '<p style="color: var(--text-tertiary); font-style: italic;">No techniques mapped</p>'}
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem; color: var(--secondary-color);">🛡️ MITRE Mitigations</h4>
                ${control.mitigations && control.mitigations.length > 0 ? `
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        ${control.mitigations.map(mit => `
                            <a href="https://attack.mitre.org/mitigations/${mit}/" target="_blank" style="padding: 0.5rem 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; text-decoration: none; color: var(--secondary-color); font-size: 0.875rem; font-weight: 600; border: 1px solid var(--border-color); transition: all 0.2s;" onmouseover="this.style.borderColor='var(--secondary-color)'" onmouseout="this.style.borderColor='var(--border-color)'">
                                ${mit}
                            </a>
                        `).join('')}
                    </div>
                ` : '<p style="color: var(--text-tertiary); font-style: italic;">No mitigations mapped</p>'}
            </div>
        `;

        rightPane.classList.add('visible');
    }

    loadHardeningTab() {
        const listContainer = document.getElementById('hardening-paths-list');

        if (!this.analysisData) {
            listContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const analysis = this.analysisData.analysis || {};
        const attackPaths = analysis.expected_attack_paths || [];
        const controlRecs = analysis.control_recommendations || [];

        if (attackPaths.length === 0) {
            listContainer.innerHTML = '<p class="placeholder">No attack paths available</p>';
            return;
        }

        listContainer.innerHTML = `
            <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid var(--primary-color);">
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem; color: var(--primary-color);">🔒 What is "Visualize"?</h4>
                <p style="color: var(--text-secondary); margin-bottom: 0.75rem; font-size: 0.875rem;">
                    Shows side-by-side comparison of your architecture BEFORE and AFTER applying security controls:
                </p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; font-size: 0.875rem;">
                    <div style="padding: 0.75rem; background: var(--code-bg); border-radius: 6px; border: 2px solid var(--danger-color);">
                        <strong style="color: var(--danger-color);">⚠️ BEFORE</strong>
                        <div style="color: var(--text-secondary); margin-top: 0.5rem;">
                            Attack path nodes highlighted in RED showing vulnerability
                        </div>
                    </div>
                    <div style="padding: 0.75rem; background: var(--code-bg); border-radius: 6px; border: 2px solid var(--secondary-color);">
                        <strong style="color: var(--secondary-color);">✅ AFTER</strong>
                        <div style="color: var(--text-secondary); margin-top: 0.5rem;">
                            Protected nodes highlighted in GREEN with controls applied
                        </div>
                    </div>
                </div>
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color); font-size: 0.875rem;">
                    💡 Click <strong style="color: var(--primary-color);">Visualize →</strong> on any attack path to see control placement<br>
                    ⚠️ <strong style="color: var(--warning-color);">0 controls = Residual Risk</strong> - Path has no available mitigations and represents accepted/residual risk
                </div>
            </div>
        `;

        // Sort attack paths by control count (most controls first), then by criticality
        const sortedPaths = [...attackPaths].sort((a, b) => {
            const aIndex = attackPaths.indexOf(a);
            const bIndex = attackPaths.indexOf(b);
            const aControls = controlRecs.filter(c => c.attack_paths && c.attack_paths.includes(aIndex)).length;
            const bControls = controlRecs.filter(c => c.attack_paths && c.attack_paths.includes(bIndex)).length;

            // Sort by control count descending
            if (bControls !== aControls) return bControls - aControls;

            // Then by criticality
            const tierOrder = { 'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1 };
            return (tierOrder[b.criticality_tier] || 0) - (tierOrder[a.criticality_tier] || 0);
        });

        sortedPaths.forEach(path => {
            // Find controls that apply to this path using array position (not AP- number)
            const pathIndex = attackPaths.indexOf(path);
            const pathControls = controlRecs.filter(c =>
                c.attack_paths && c.attack_paths.includes(pathIndex)
            );

            // POINT 3: Skip attack paths with no controls (nothing to visualize)
            if (pathControls.length === 0) {
                console.log(`[DEBUG] Skipping ${path.id} - no controls to visualize`);
                return;
            }

            const criticalityColor =
                path.criticality_tier === 'CRITICAL' ? 'var(--danger-color)' :
                path.criticality_tier === 'HIGH' ? 'var(--warning-color)' :
                'var(--secondary-color)';

            const card = document.createElement('div');
            card.className = 'list-item';
            card.style.cssText = `
                padding: 1rem;
                margin-bottom: 0.75rem;
                background: var(--card-bg);
                border-radius: 8px;
                border-left: 4px solid ${criticalityColor};
                cursor: pointer;
                transition: all 0.2s;
            `;

            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                            <strong style="font-size: 1rem; color: var(--primary-color);">${path.id}</strong>
                            <span style="padding: 0.25rem 0.75rem; background: ${criticalityColor}22; color: ${criticalityColor}; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">
                                ${path.criticality_tier}
                            </span>
                        </div>
                        <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
                            ${path.entry} → ${path.target} (${path.hop_count} hops)
                        </div>
                        <div style="display: flex; gap: 1rem; font-size: 0.8125rem; color: var(--text-tertiary);">
                            <span>🛡️ ${pathControls.length} control${pathControls.length !== 1 ? 's' : ''}</span>
                            <span>🎯 ${path.techniques ? path.techniques.length : 0} techniques</span>
                        </div>
                    </div>
                    <button class="btn-primary" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                        Visualize →
                    </button>
                </div>
            `;

            card.addEventListener('click', async () => {
                listContainer.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                card.classList.add('active');

                // Update status message
                this.updateStatusMessage(`🔒 Generating hardening visualization for ${path.id}...`);

                await this.visualizePathHardening(path, pathControls);

                // Update status message after completion
                this.updateStatusMessage(`✅ ${path.id} hardening visualization complete`);
            });

            listContainer.appendChild(card);
        });
    }

    async visualizePathHardening(path, controls) {
        console.log('[DEBUG] visualizePathHardening called for', path.id);

        // Use center pane instead of right pane for better visibility
        const centerPane = document.getElementById('hardening-paths-list');

        if (!centerPane) {
            console.error('[DEBUG] Center pane not found');
            return;
        }

        if (!this.originalMmdContent) {
            console.error('[DEBUG] No original MMD content available');
            centerPane.innerHTML = `
                <div style="padding: 2rem; text-align: center;">
                    <h3 style="color: var(--danger-color);">⚠️ Cannot Visualize</h3>
                    <p style="color: var(--text-secondary);">
                        Architecture diagram not available. Please re-analyze the architecture.
                    </p>
                </div>
            `;
            return;
        }

        // Use stored original mermaid content
        console.log('[DEBUG] Generating diagrams from stored MMD content');
        const originalMmd = this.originalMmdContent;

        // Generate before/after diagrams (simplified - just show nodes in path)
        const beforeMmd = this.generateSimpleBeforeDiagram(originalMmd, path);
        const afterMmd = this.generateSimpleAfterDiagram(originalMmd, path, controls);
        console.log('[DEBUG] Diagrams generated, updating center pane');

        // Group controls by node they protect
        const controlsByNode = this.groupControlsByNode(controls, path);

        // Get nodes with controls
        const nodesWithControls = Object.keys(controlsByNode);

        // Generate attack path diagram (showing only the path)
        const attackPathMmd = this.generateAttackPathDiagram(path);

        centerPane.innerHTML = `
                <!-- POINT 2: Back button to return to attack path list -->
                <div style="margin-bottom: 1rem;">
                    <button id="back-to-paths" class="btn-secondary" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                        ← Back to Attack Paths
                    </button>
                </div>

                <h3 style="color: var(--primary-color);">${path.id}: Control Placement</h3>
                <p style="color: var(--text-secondary); margin-bottom: 1.5rem; font-size: 0.875rem;">
                    ${path.entry} → ${path.target}
                </p>

                <!-- Tabbed view for Before/After/Full -->
                <div style="display: flex; gap: 0.5rem; border-bottom: 2px solid var(--border-color); margin-bottom: 1rem; align-items: center;">
                    <button class="visualize-subtab active" data-subtab="before" style="padding: 0.75rem 1.5rem; background: var(--danger-color); color: white; border: none; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: 600; font-size: 0.875rem;">
                        ⚠️ Before Hardening
                    </button>
                    <button class="visualize-subtab" data-subtab="after" style="padding: 0.75rem 1.5rem; background: transparent; color: var(--text-color); border: none; cursor: pointer; font-weight: 600; font-size: 0.875rem;">
                        ✅ After Hardening
                    </button>
                    <button class="visualize-subtab" data-subtab="full" style="padding: 0.75rem 1.5rem; background: transparent; color: var(--text-color); border: none; cursor: pointer; font-weight: 600; font-size: 0.875rem;">
                        🏗️ Full Architecture
                    </button>

                    <!-- POINT 4: Criticality filter (only show in After tab) -->
                    <div id="criticality-filter" style="margin-left: auto; display: none; gap: 0.5rem; align-items: center;">
                        <span style="font-size: 0.8125rem; color: var(--text-secondary);">Filter:</span>
                        <button class="criticality-btn active" data-tier="all" style="padding: 0.25rem 0.75rem; background: var(--primary-color); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: 600;">All</button>
                        <button class="criticality-btn" data-tier="CRITICAL" style="padding: 0.25rem 0.75rem; background: transparent; color: var(--text-color); border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: 600;">🔴 Critical</button>
                        <button class="criticality-btn" data-tier="HIGH" style="padding: 0.25rem 0.75rem; background: transparent; color: var(--text-color); border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: 600;">🟡 High</button>
                        <button class="criticality-btn" data-tier="MEDIUM" style="padding: 0.25rem 0.75rem; background: transparent; color: var(--text-color); border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: 600;">🔵 Medium</button>
                    </div>
                </div>

                <!-- Before View -->
                <div id="visualize-before" class="visualize-subtab-content" style="display: block;">
                    <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--danger-color)15; border-radius: 8px; border-left: 4px solid var(--danger-color);">
                        <h4 style="margin-bottom: 0.75rem; color: var(--danger-color);">Attack Path Nodes (Click to View)</h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                            ${path.path.map((node, idx) => `
                                <button class="vulnerable-node-btn" data-node="${node}" data-idx="${idx}" style="padding: 0.5rem 0.75rem; background: var(--danger-color)22; border: 2px solid var(--danger-color); border-radius: 8px; color: var(--text-color); cursor: pointer; transition: all 0.2s; font-weight: 600;" onmouseover="this.style.background='var(--danger-color)44'" onmouseout="this.style.background='var(--danger-color)22'">
                                    <strong>${idx + 1}.</strong> ${node}
                                </button>
                            `).join('')}
                        </div>
                        <p style="margin-top: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">
                            These ${path.path.length} nodes form the attack path. <strong>Click any node</strong> to view the attack path diagram.
                        </p>
                    </div>

                    <!-- Diagram controls -->
                    <div style="margin-bottom: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap;">
                        <button id="before-zoom-in" class="btn-icon" title="Zoom In">🔍+</button>
                        <button id="before-zoom-out" class="btn-icon" title="Zoom Out">🔍−</button>
                        <button id="before-zoom-reset" class="btn-icon" title="Reset Zoom">↺</button>
                        <div style="width: 1px; height: 24px; background: var(--border-color); margin: 0 0.25rem;"></div>
                        <button id="before-fit-width" class="btn-icon" title="Fit to Width">↔️</button>
                        <button id="before-fit-height" class="btn-icon" title="Fit to Height">↕️</button>
                    </div>

                    <div id="before-diagram-container" style="padding: 1rem; background: var(--code-bg); border-radius: 8px; overflow: auto; max-height: 500px; border: 2px solid var(--danger-color);">
                        <div class="mermaid" id="before-diagram">${attackPathMmd}</div>
                    </div>
                    <p style="margin-top: 0.5rem; font-size: 0.8125rem; color: var(--text-tertiary); font-style: italic;">
                        Attack path diagram showing traversal from entry to target
                    </p>
                </div>

                <!-- After View -->
                <div id="visualize-after" class="visualize-subtab-content" style="display: none;">
                    ${nodesWithControls.length > 0 ? `
                        <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--secondary-color)15; border-radius: 8px; border-left: 4px solid var(--secondary-color);">
                            <h4 style="margin-bottom: 0.75rem; color: var(--secondary-color);">Hardened Nodes (Click to View Controls)</h4>
                            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                                ${nodesWithControls.map(node => `
                                    <button class="hardened-node-btn" data-node="${node}" style="padding: 0.5rem 0.75rem; background: var(--secondary-color)22; border: 2px solid var(--secondary-color); border-radius: 8px; color: var(--text-color); cursor: pointer; transition: all 0.2s; font-weight: 600;" onmouseover="this.style.background='var(--secondary-color)44'" onmouseout="this.style.background='var(--secondary-color)22'">
                                        🛡️ ${node}
                                    </button>
                                `).join('')}
                            </div>
                            <p style="margin-top: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">
                                <strong>${nodesWithControls.length}</strong> out of <strong>${path.path.length}</strong> nodes hardened. <strong>Click any node</strong> to see controls in detail pane.
                            </p>
                        </div>
                    ` : `
                        <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--warning-color)15; border-radius: 8px; border-left: 4px solid var(--warning-color);">
                            <h4 style="margin-bottom: 0.75rem; color: var(--warning-color);">⚠️ No Controls Applied</h4>
                            <p style="font-size: 0.875rem; color: var(--text-secondary);">
                                This attack path has no security controls. This represents <strong>residual risk</strong>.
                            </p>
                        </div>
                    `}

                    <!-- Diagram controls -->
                    <div style="margin-bottom: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap;">
                        <button id="after-zoom-in" class="btn-icon" title="Zoom In">🔍+</button>
                        <button id="after-zoom-out" class="btn-icon" title="Zoom Out">🔍−</button>
                        <button id="after-zoom-reset" class="btn-icon" title="Reset Zoom">↺</button>
                        <div style="width: 1px; height: 24px; background: var(--border-color); margin: 0 0.25rem;"></div>
                        <button id="after-fit-width" class="btn-icon" title="Fit to Width">↔️</button>
                        <button id="after-fit-height" class="btn-icon" title="Fit to Height">↕️</button>
                    </div>

                    <div id="after-diagram-container" style="padding: 1rem; background: var(--code-bg); border-radius: 8px; overflow: auto; max-height: 500px; border: 2px solid var(--secondary-color);">
                        <div class="mermaid" id="after-diagram">${afterMmd}</div>
                    </div>
                    <p style="margin-top: 0.5rem; font-size: 0.8125rem; color: var(--text-tertiary); font-style: italic;">
                        Attack path diagram with hardened nodes highlighted
                    </p>
                </div>

                <!-- Full Architecture View -->
                <div id="visualize-full" class="visualize-subtab-content" style="display: none;">
                    <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--primary-color)15; border-radius: 8px; border-left: 4px solid var(--primary-color);">
                        <h4 style="margin-bottom: 0.75rem; color: var(--primary-color);">Complete System Architecture with All Controls</h4>
                        <p style="font-size: 0.875rem; color: var(--text-secondary);">
                            This shows the complete architecture from <code>after.mmd</code> with all recommended security controls integrated.
                        </p>
                    </div>

                    <!-- Diagram controls -->
                    <div style="margin-bottom: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap;">
                        <button id="full-zoom-in" class="btn-icon" title="Zoom In">🔍+</button>
                        <button id="full-zoom-out" class="btn-icon" title="Zoom Out">🔍−</button>
                        <button id="full-zoom-reset" class="btn-icon" title="Reset Zoom">↺</button>
                        <div style="width: 1px; height: 24px; background: var(--border-color); margin: 0 0.25rem;"></div>
                        <button id="full-fit-width" class="btn-icon" title="Fit to Width">↔️</button>
                        <button id="full-fit-height" class="btn-icon" title="Fit to Height">↕️</button>
                    </div>

                    <div id="full-diagram-container" style="padding: 1rem; background: var(--code-bg); border-radius: 8px; overflow: auto; max-height: 600px; border: 2px solid var(--primary-color);">
                        <div class="mermaid" id="full-diagram"></div>
                    </div>
                    <p style="margin-top: 0.5rem; font-size: 0.8125rem; color: var(--text-tertiary); font-style: italic;">
                        Full architecture with all security controls and connections
                    </p>
                </div>
        `;

        // Store path and controls for later use
        this.currentVisualizePath = path;
        this.currentVisualizeControls = controls;
        this.currentVisualizeControlsByNode = controlsByNode;

        // Add event listeners for vulnerable nodes (Before view)
        centerPane.querySelectorAll('.vulnerable-node-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const node = btn.dataset.node;
                const idx = btn.dataset.idx;
                this.showVulnerableNodeDetail(node, idx, path);
            });
        });

        // Add event listeners for hardened nodes (After view)
        centerPane.querySelectorAll('.hardened-node-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const node = btn.dataset.node;
                this.showHardenedNodeDetail(node, controlsByNode[node], path);
            });
        });

        // Add visualize subtab switching
        const visualizeSubtabs = centerPane.querySelectorAll('.visualize-subtab');
        visualizeSubtabs.forEach(subtab => {
            subtab.addEventListener('click', () => {
                const subtabName = subtab.dataset.subtab;

                // Update button styles
                visualizeSubtabs.forEach(btn => {
                    const isActive = btn.dataset.subtab === subtabName;
                    if (isActive) {
                        const bgColor = subtabName === 'before' ? 'var(--danger-color)' :
                                       subtabName === 'after' ? 'var(--secondary-color)' :
                                       'var(--primary-color)';
                        btn.style.background = bgColor;
                        btn.style.color = 'white';
                    } else {
                        btn.style.background = 'transparent';
                        btn.style.color = 'var(--text-color)';
                    }
                });

                // Update content visibility
                centerPane.querySelectorAll('.visualize-subtab-content').forEach(content => {
                    const isActive = content.id === `visualize-${subtabName}`;
                    content.style.display = isActive ? 'block' : 'none';
                });

                // Render the Full Architecture diagram when switching to Full tab
                if (subtabName === 'full') {
                    setTimeout(async () => {
                        const fullElement = document.querySelector('#full-diagram');
                        if (!fullElement) {
                            console.error('[DEBUG] Full diagram element not found');
                            return;
                        }

                        // Check if already rendered
                        const existingSvg = fullElement.querySelector('svg');
                        if (existingSvg && existingSvg.getAttribute('width') !== '16') {
                            console.log('[DEBUG] Full diagram already rendered properly');
                            return;
                        }

                        // Fetch after.mmd from Reports API
                        if (this.analysisData && this.analysisData.architecture_name) {
                            try {
                                console.log('[DEBUG] Fetching after.mmd from Reports API...');
                                const response = await fetch(`/api/v1/reports/${this.analysisData.architecture_name}/files/after.mmd`);
                                if (response.ok) {
                                    const afterMmdFull = await response.text();
                                    console.log('[DEBUG] after.mmd loaded:', afterMmdFull.length, 'characters');

                                    // Render diagram
                                    fullElement.innerHTML = '';
                                    fullElement.textContent = afterMmdFull;
                                    fullElement.removeAttribute('data-processed');
                                    fullElement.classList.add('mermaid');

                                    await mermaid.run({ nodes: [fullElement] });
                                    console.log('[DEBUG] Full architecture diagram rendered successfully');

                                    // Setup zoom
                                    this.setupDiagramZoom('full');
                                } else {
                                    console.error('[DEBUG] Failed to fetch after.mmd:', response.status);
                                    fullElement.innerHTML = '<p style="color: var(--danger-color);">Failed to load full architecture diagram</p>';
                                }
                            } catch (err) {
                                console.error('[DEBUG] Error fetching after.mmd:', err);
                                fullElement.innerHTML = '<p style="color: var(--danger-color);">Error: ' + err.message + '</p>';
                            }
                        } else {
                            console.error('[DEBUG] No architecture name available');
                        }
                    }, 200);
                }

                // Render the After diagram when switching to After tab (fixes 16x16 size issue)
                if (subtabName === 'after') {
                    setTimeout(async () => {
                        const afterElement = document.querySelector('#after-diagram');
                        if (!afterElement) {
                            console.error('[DEBUG] After diagram element not found');
                            return;
                        }

                        // Check if already rendered properly (has SVG with good size)
                        const existingSvg = afterElement.querySelector('svg');
                        if (existingSvg) {
                            const width = existingSvg.getAttribute('width');
                            const height = existingSvg.getAttribute('height');
                            console.log('[DEBUG] After diagram already rendered, size:', width, 'x', height);

                            // If size is tiny (16x16), need to re-render
                            if (width === '16' || width === '16px') {
                                console.log('[DEBUG] After diagram too small (16x16), re-rendering...');
                            } else {
                                console.log('[DEBUG] After diagram size is good, skipping re-render');
                                return;
                            }
                        }

                        // Get the diagram content from the element's text or data attribute
                        let diagramContent = afterElement.getAttribute('data-diagram-content');
                        if (!diagramContent) {
                            diagramContent = afterElement.textContent.trim();
                        }

                        if (diagramContent && diagramContent.startsWith('flowchart')) {
                            console.log('[DEBUG] Rendering After diagram now that tab is visible');
                            console.log('[DEBUG] Diagram content length:', diagramContent.length);

                            try {
                                // Clear element and set fresh content
                                afterElement.innerHTML = '';
                                afterElement.textContent = diagramContent;
                                afterElement.removeAttribute('data-processed');
                                afterElement.classList.add('mermaid');

                                // Render with mermaid
                                await mermaid.run({ nodes: [afterElement] });
                                console.log('[DEBUG] After diagram rendered successfully');

                                // Check final size
                                const svg = afterElement.querySelector('svg');
                                if (svg) {
                                    console.log('[DEBUG] After diagram SVG size:', svg.getAttribute('width'), 'x', svg.getAttribute('height'));
                                } else {
                                    console.error('[DEBUG] No SVG created after render');
                                }
                            } catch (err) {
                                console.error('[DEBUG] After diagram render failed:', err);
                                console.error('[DEBUG] Error details:', err.message);
                            }
                        } else {
                            console.error('[DEBUG] No valid diagram content found for After diagram');
                        }
                    }, 200);
                }
            });
        });

        // Render mermaid diagrams
        if (window.mermaid) {
            console.log('[DEBUG] Rendering mermaid diagrams');
            try {
                // Important: Mermaid needs a small delay to properly attach to DOM
                await new Promise(resolve => setTimeout(resolve, 100));

                const beforeElement = document.querySelector('#before-diagram');
                const afterElement = document.querySelector('#after-diagram');

                if (beforeElement && beforeElement.textContent) {
                    const beforeContent = beforeElement.textContent.trim();
                    console.log('[DEBUG] Before diagram content length:', beforeContent.length);
                    console.log('[DEBUG] Before diagram preview:', beforeContent.substring(0, 100));

                    if (beforeContent.length > 0) {
                        try {
                            await mermaid.run({
                                nodes: [beforeElement]
                            });
                            console.log('[DEBUG] Before diagram rendered successfully');
                        } catch (err) {
                            console.error('[DEBUG] Before diagram render failed:', err);
                            // Show raw text as fallback
                            beforeElement.innerHTML = `<pre style="color: var(--danger-color); white-space: pre-wrap; font-size: 0.75rem;">${beforeContent}</pre>`;
                        }
                    }
                } else {
                    console.error('[DEBUG] Before diagram element not found or empty');
                }

                if (afterElement && afterElement.textContent) {
                    const afterContent = afterElement.textContent.trim();
                    console.log('[DEBUG] After diagram content length:', afterContent.length);
                    console.log('[DEBUG] After diagram preview:', afterContent.substring(0, 100));

                    // Store diagram content for later re-render when tab becomes visible
                    afterElement.setAttribute('data-diagram-content', afterContent);
                    console.log('[DEBUG] Stored After diagram content in data attribute');

                    // Don't render it yet (it's hidden, will be 16x16)
                    // It will be rendered when user clicks the After tab
                    console.log('[DEBUG] Skipping initial After diagram render (will render on tab click)');
                } else {
                    console.error('[DEBUG] After diagram element not found or empty');
                }

                console.log('[DEBUG] Mermaid rendering complete');

                // Setup zoom controls for both diagrams
                await new Promise(resolve => setTimeout(resolve, 100));
                this.setupDiagramZoom('before');
                this.setupDiagramZoom('after');

                // POINT 1: Re-attach zoom controls after tab switch
                centerPane.querySelectorAll('.visualize-subtab').forEach(btn => {
                    btn.addEventListener('click', () => {
                        setTimeout(() => {
                            this.setupDiagramZoom('before');
                            this.setupDiagramZoom('after');
                        }, 300);
                    });
                });
            } catch (error) {
                console.error('[DEBUG] Mermaid rendering failed:', error);
                console.error('[DEBUG] Error details:', error.message, error.stack);
            }
        } else {
            console.error('[DEBUG] Mermaid library not loaded');
        }

        // POINT 2: Setup Back button to return to attack path list
        const backBtn = document.getElementById('back-to-paths');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                console.log('[DEBUG] Back button clicked, reloading Visualise tab');
                this.loadHardeningTab();
            });
        }

        // POINT 4: Setup criticality filter (show when After tab is active, hide for Before/Full)
        const filterDiv = document.getElementById('criticality-filter');
        centerPane.querySelectorAll('.visualize-subtab').forEach(btn => {
            btn.addEventListener('click', () => {
                const subtab = btn.getAttribute('data-subtab');
                if (filterDiv) {
                    filterDiv.style.display = subtab === 'after' ? 'flex' : 'none';
                }
            });
        });

        // POINT 4: Criticality filter functionality
        this.setupCriticalityFilter(centerPane, path, controls);

        // Scroll to top of center pane
        centerPane.scrollTop = 0;
    }

    setupCriticalityFilter(centerPane, path, allControls) {
        const filterButtons = centerPane.querySelectorAll('.criticality-btn');
        let currentFilter = 'all';

        filterButtons.forEach(btn => {
            btn.addEventListener('click', async () => {
                // Update active state
                filterButtons.forEach(b => {
                    b.classList.remove('active');
                    b.style.background = 'transparent';
                    b.style.color = 'var(--text-color)';
                    b.style.border = '1px solid var(--border-color)';
                });
                btn.classList.add('active');
                btn.style.background = 'var(--primary-color)';
                btn.style.color = 'white';
                btn.style.border = 'none';

                // Get selected tier
                currentFilter = btn.getAttribute('data-tier');
                console.log('[DEBUG] Criticality filter changed to:', currentFilter);

                // POINT 4: Filter controls by criticality (case-insensitive)
                const filteredControls = currentFilter === 'all'
                    ? allControls
                    : allControls.filter(c => (c.priority || '').toUpperCase() === currentFilter);

                console.log('[DEBUG] Filtered controls:', filteredControls.length, 'of', allControls.length);

                // Regenerate After diagram with filtered controls
                const afterMmd = this.generateSimpleAfterDiagram(this.originalMmdContent, path, filteredControls);

                // Update After diagram content
                const afterElement = document.querySelector('#after-diagram');
                if (afterElement) {
                    afterElement.setAttribute('data-diagram-content', afterMmd);
                    afterElement.innerHTML = '';
                    afterElement.textContent = afterMmd;
                    afterElement.removeAttribute('data-processed');
                    afterElement.classList.add('mermaid');

                    try {
                        await mermaid.run({ nodes: [afterElement] });
                        console.log('[DEBUG] After diagram re-rendered with filter:', currentFilter);
                        this.setupDiagramZoom('after');
                    } catch (err) {
                        console.error('[DEBUG] Failed to re-render After diagram:', err);
                    }
                }
            });
        });
    }

    setupDiagramZoom(prefix) {
        let scale = 0.5; // Start at 50%
        const container = document.getElementById(`${prefix}-container`);
        const getDiagram = () => container?.querySelector('svg');

        const zoomInBtn = document.getElementById(`${prefix}-zoom-in`);
        const zoomOutBtn = document.getElementById(`${prefix}-zoom-out`);
        const zoomResetBtn = document.getElementById(`${prefix}-zoom-reset`);
        const fitWidthBtn = document.getElementById(`${prefix}-fit-width`);
        const fitHeightBtn = document.getElementById(`${prefix}-fit-height`);

        console.log('[DEBUG] setupDiagramZoom:', prefix, 'Container:', !!container, 'Buttons:', {in:!!zoomInBtn, out:!!zoomOutBtn, reset:!!zoomResetBtn});

        if (!container) return;

        // Store original dimensions after first render
        setTimeout(() => {
            const svg = getDiagram();
            if (svg) {
                const bbox = svg.getBBox();
                const currentWidth = svg.getAttribute('width');
                const currentHeight = svg.getAttribute('height');

                console.log('[DEBUG] SVG dimensions - width:', currentWidth, 'height:', currentHeight, 'bbox:', bbox.width, 'x', bbox.height);

                this[`${prefix}OriginalWidth`] = bbox.width || parseFloat(currentWidth) || 800;
                this[`${prefix}OriginalHeight`] = bbox.height || parseFloat(currentHeight) || 600;

                console.log('[DEBUG] Stored original dimensions:', this[`${prefix}OriginalWidth`], 'x', this[`${prefix}OriginalHeight`]);

                // Set initial 50% size
                svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);

                console.log('[DEBUG] Set initial size to:', this[`${prefix}OriginalWidth`] * scale, 'x', this[`${prefix}OriginalHeight`] * scale);
            } else {
                console.error('[DEBUG] SVG not found in container for:', prefix);
            }
        }, 100);

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => {
                scale = Math.min(scale + 0.2, 3);
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
            });
        }

        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => {
                scale = Math.max(scale - 0.2, 0.3);
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
            });
        }

        if (zoomResetBtn) {
            zoomResetBtn.addEventListener('click', () => {
                scale = 0.5;
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
                container.scrollTop = 0;
                container.scrollLeft = 0;
            });
        }

        if (fitWidthBtn) {
            fitWidthBtn.addEventListener('click', () => {
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    const containerWidth = container.clientWidth - 32;
                    scale = containerWidth / this[`${prefix}OriginalWidth`];
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
            });
        }

        if (fitHeightBtn) {
            fitHeightBtn.addEventListener('click', () => {
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalHeight`]) {
                    const containerHeight = container.clientHeight - 32;
                    scale = containerHeight / this[`${prefix}OriginalHeight`];
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
            });
        }
    }

    generateAttackPathDiagram(path) {
        // Generate simple linear attack path diagram
        console.log('[DEBUG] Generating attack path diagram for:', path.id);
        console.log('[DEBUG] Path nodes:', path.path);

        const nodes = path.path.map((node, idx) => {
            // Sanitize node name for mermaid
            const sanitized = node.replace(/[[\](){}]/g, '');
            return `${sanitized}["${node}"]`;
        }).join(' --> ');

        const diagram = `flowchart LR\n    ${nodes}\n    style ${path.path[0].replace(/[[\](){}]/g, '')} fill:#ff6b8a,stroke:#ff0033,stroke-width:3px\n    style ${path.path[path.path.length - 1].replace(/[[\](){}]/g, '')} fill:#f39c12,stroke:#d68910,stroke-width:3px`;
        console.log('[DEBUG] Generated diagram:', diagram);
        return diagram;
    }

    showVulnerableNodeDetail(node, idx, path) {
        const rightPane = document.getElementById('right-pane');
        const rightPaneContent = document.getElementById('right-pane-content');

        const position = parseInt(idx) === 0 ? 'Entry Point' :
                        parseInt(idx) === path.path.length - 1 ? 'Target' :
                        'Traversal Node';

        rightPaneContent.innerHTML = `
            <h3 style="color: var(--danger-color);">⚠️ Vulnerable Node</h3>
            <div style="padding: 1rem; background: var(--danger-color)15; border-radius: 8px; border-left: 4px solid var(--danger-color); margin-bottom: 1.5rem;">
                <h4 style="font-size: 1.125rem; margin-bottom: 0.5rem;">${node}</h4>
                <div style="font-size: 0.875rem; color: var(--text-secondary);">
                    <div><strong>Position:</strong> Step ${parseInt(idx) + 1} of ${path.path.length}</div>
                    <div><strong>Role:</strong> ${position}</div>
                    <div><strong>Path:</strong> ${path.id}</div>
                </div>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem;">🎯 Attack Context</h4>
                <p style="color: var(--text-secondary); font-size: 0.875rem; line-height: 1.6;">
                    ${position === 'Entry Point' ?
                        `This is the <strong>entry point</strong> where the attacker gains initial access to the system. Securing this node is critical to preventing the entire attack chain.` :
                    position === 'Target' ?
                        `This is the <strong>target</strong> of the attack. The attacker's goal is to reach this node to exfiltrate data, cause damage, or achieve their objective.` :
                        `This is a <strong>traversal node</strong> in the attack path. The attacker uses this node to move closer to their target.`
                    }
                </p>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem;">🛡️ Protection Status</h4>
                <div style="padding: 1rem; background: var(--warning-color)15; border-radius: 8px; border-left: 4px solid var(--warning-color);">
                    <p style="color: var(--text-secondary); font-size: 0.875rem;">
                        <strong>No controls applied</strong> - This node is currently vulnerable in this attack path.
                        Switch to "After Hardening" view to see which nodes have been protected.
                    </p>
                </div>
            </div>

            <div>
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem;">📍 Path Sequence</h4>
                <div style="padding: 1rem; background: var(--code-bg); border-radius: 8px;">
                    ${path.path.map((n, i) => `
                        <div style="padding: 0.5rem; margin-bottom: 0.5rem; ${i === parseInt(idx) ? 'background: var(--danger-color)22; border-left: 4px solid var(--danger-color);' : 'background: var(--nav-hover-bg);'} border-radius: 6px;">
                            <strong>${i + 1}.</strong> ${n} ${i === parseInt(idx) ? '← You are here' : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        rightPane.classList.add('visible');
    }

    showHardenedNodeDetail(node, nodeControls, path) {
        const rightPane = document.getElementById('right-pane');
        const rightPaneContent = document.getElementById('right-pane-content');

        rightPaneContent.innerHTML = `
            <h3 style="color: var(--secondary-color);">🛡️ Hardened Node</h3>
            <div style="padding: 1rem; background: var(--secondary-color)15; border-radius: 8px; border-left: 4px solid var(--secondary-color); margin-bottom: 1.5rem;">
                <h4 style="font-size: 1.125rem; margin-bottom: 0.5rem;">${node}</h4>
                <div style="font-size: 0.875rem; color: var(--text-secondary);">
                    <div><strong>Controls Applied:</strong> ${nodeControls.length}</div>
                    <div><strong>Path:</strong> ${path.id}</div>
                </div>
            </div>

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem;">🛡️ Applied Controls</h4>
                ${nodeControls.map(control => {
                    const priorityColor =
                        control.priority === 'critical' ? 'var(--danger-color)' :
                        control.priority === 'high' ? 'var(--warning-color)' :
                        'var(--primary-color)';

                    return `
                        <div style="margin-bottom: 1rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid ${priorityColor};">
                            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem;">
                                <strong style="font-size: 1rem; color: var(--primary-color);">${control.control}</strong>
                                <span style="padding: 0.25rem 0.75rem; background: ${priorityColor}22; color: ${priorityColor}; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">
                                    ${control.priority}
                                </span>
                            </div>
                            <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.75rem;">
                                ${control.rationale}
                            </p>
                            ${control.techniques && control.techniques.length > 0 ? `
                                <div style="font-size: 0.8125rem; color: var(--text-tertiary);">
                                    <strong>Mitigates:</strong> ${control.techniques.length} MITRE technique${control.techniques.length > 1 ? 's' : ''}
                                </div>
                            ` : ''}
                        </div>
                    `;
                }).join('')}
            </div>

            <div>
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem;">📊 Control Summary</h4>
                <div style="padding: 1rem; background: var(--code-bg); border-radius: 8px;">
                    <div style="margin-bottom: 0.5rem;">
                        <strong>Total Controls:</strong> ${nodeControls.length}
                    </div>
                    <div style="margin-bottom: 0.5rem;">
                        <strong>Priority Breakdown:</strong>
                    </div>
                    <div style="padding-left: 1rem; font-size: 0.875rem;">
                        ${['critical', 'high', 'medium'].map(priority => {
                            const count = nodeControls.filter(c => c.priority === priority).length;
                            return count > 0 ? `<div>${priority.toUpperCase()}: ${count}</div>` : '';
                        }).join('')}
                    </div>
                </div>
            </div>
        `;

        rightPane.classList.add('visible');
    }

    getPathIndex(path) {
        const attackPaths = (this.analysisData?.analysis || {}).expected_attack_paths || [];
        return attackPaths.indexOf(path);
    }

    groupControlsByNode(controls, path) {
        const grouped = {};
        const pathIndex = this.getPathIndex(path);

        console.log('[DEBUG] groupControlsByNode - controls count:', controls.length);
        console.log('[DEBUG] groupControlsByNode - pathIndex:', pathIndex);

        controls.forEach(control => {
            const hopAnalysis = control._layered_defense?.hop_analysis || [];
            console.log('[DEBUG] control:', control.control, 'has hop_analysis:', hopAnalysis.length > 0);

            const pathHops = hopAnalysis.filter(hop => hop.path_id === pathIndex);

            if (pathHops.length > 0) {
                pathHops.forEach(hop => {
                    const node = hop.target_label || hop.source_label;
                    if (node) {
                        if (!grouped[node]) {
                            grouped[node] = [];
                        }
                        // Avoid duplicates
                        if (!grouped[node].some(c => c.control === control.control)) {
                            grouped[node].push(control);
                        }
                    }
                });
            }
        });

        return grouped;
    }

    generateSimpleBeforeDiagram(originalMmd, path) {
        // Generate attack path diagram (not full architecture)
        return this.generateAttackPathDiagram(path);
    }

    normalizeNodeName(nodeName) {
        // Normalize node names for comparison (remove spaces, lowercase, handle common variations)
        return nodeName
            .toLowerCase()
            .replace(/\s+/g, '')
            .replace(/[_-]/g, '')
            .replace(/with.+$/, '') // Remove "with WAF" etc.
            .trim();
    }

    findMatchingPathNode(hardenedNode, pathNodes) {
        // Find a path node that matches the hardened node
        const normalizedHardened = this.normalizeNodeName(hardenedNode);

        for (const pathNode of pathNodes) {
            const normalizedPath = this.normalizeNodeName(pathNode);

            // Check if names match after normalization
            if (normalizedPath === normalizedHardened ||
                normalizedPath.includes(normalizedHardened) ||
                normalizedHardened.includes(normalizedPath)) {
                return pathNode;
            }
        }

        return null;
    }

    generateSimpleAfterDiagram(originalMmd, path, controls) {
        // Generate attack path diagram WITH control nodes connected
        console.log('[DEBUG] generateSimpleAfterDiagram - controls count:', controls.length);
        console.log('[DEBUG] generateSimpleAfterDiagram - path:', path.id);

        const controlsByNode = this.groupControlsByNode(controls, path);
        console.log('[DEBUG] generateSimpleAfterDiagram - controlsByNode:', controlsByNode);

        const hardenedNodes = Object.keys(controlsByNode);
        console.log('[DEBUG] generateSimpleAfterDiagram - hardenedNodes:', hardenedNodes);

        // Build attack path nodes
        const pathNodes = path.path.map((node, idx) => {
            const sanitized = node.replace(/[[\](){}]/g, '');
            return `${sanitized}["${node}"]`;
        }).join(' --> ');

        let diagram = `flowchart LR\n    ${pathNodes}\n`;

        // Add control nodes and connections
        const addedControls = new Set(); // Track to avoid duplicates

        hardenedNodes.forEach(hardenedNode => {
            const matchingPathNode = this.findMatchingPathNode(hardenedNode, path.path);
            console.log('[DEBUG] Hardened node:', hardenedNode, '→ matched path node:', matchingPathNode);

            if (matchingPathNode) {
                const nodeControls = controlsByNode[hardenedNode];
                const sanitizedPathNode = matchingPathNode.replace(/[[\](){}]/g, '');

                // POINT 4: Sort controls by criticality (CRITICAL first, then HIGH, MEDIUM)
                const tierOrder = { 'CRITICAL': 0, 'critical': 0, 'HIGH': 1, 'high': 1, 'MEDIUM': 2, 'medium': 2, 'BASELINE': 3, 'baseline': 3 };
                const sortedControls = [...nodeControls].sort((a, b) => {
                    return (tierOrder[a.priority] || 99) - (tierOrder[b.priority] || 99);
                });

                // Add all controls for this node (prioritizing higher criticality)
                sortedControls.forEach(control => {
                    const controlKey = control.control.replace(/\s+/g, '');

                    if (!addedControls.has(controlKey)) {
                        // Add control node definition
                        const controlLabel = control.control;

                        // FIX: Use 'priority' field, not 'criticality_tier'
                        const tier = (control.priority || 'baseline').toUpperCase();
                        console.log('[DEBUG] Control:', controlLabel, 'Priority:', control.priority, '→ Tier:', tier);

                        const tierIcon =
                            tier === 'CRITICAL' ? '🔴' :
                            tier === 'HIGH' ? '🟡' :
                            tier === 'MEDIUM' ? '🔵' : '🟢';

                        diagram += `    ${controlKey}["${tierIcon} ${controlLabel}"]\n`;
                        addedControls.add(controlKey);
                    }

                    // Add dotted edge from control to protected node
                    diagram += `    ${controlKey} -.->|protects| ${sanitizedPathNode}\n`;
                });
            }
        });

        // Build style directives
        let styles = '\n';

        // Entry point (red)
        styles += `    style ${path.path[0].replace(/[[\](){}]/g, '')} fill:#ff6b8a,stroke:#ff0033,stroke-width:3px\n`;

        // Target (orange)
        styles += `    style ${path.path[path.path.length - 1].replace(/[[\](){}]/g, '')} fill:#f39c12,stroke:#d68910,stroke-width:3px\n`;

        // Protected nodes (green) - nodes that have controls
        hardenedNodes.forEach(hardenedNode => {
            const matchingPathNode = this.findMatchingPathNode(hardenedNode, path.path);
            if (matchingPathNode) {
                styles += `    style ${matchingPathNode.replace(/[[\](){}]/g, '')} fill:#5fd49c,stroke:#00aa55,stroke-width:4px\n`;
            }
        });

        // POINT 5: Control node styles (by criticality) with better contrast
        addedControls.forEach(controlKey => {
            const control = controls.find(c => c.control.replace(/\s+/g, '') === controlKey);
            if (control) {
                // FIX: Use 'priority' field, not 'criticality_tier'
                const tier = (control.priority || 'baseline').toUpperCase();
                console.log('[DEBUG] Styling control:', controlKey, 'Priority:', control.priority, '→ Tier:', tier);

                // Use appropriate text colors for each background for maximum readability
                const styleMap = {
                    'CRITICAL': 'fill:#c92a2a,stroke:#a61e1e,stroke-width:3px,color:#ffffff',  // Dark red bg, white text
                    'HIGH': 'fill:#fd7e14,stroke:#e8590c,stroke-width:3px,color:#000000',      // Bright orange bg, black text
                    'MEDIUM': 'fill:#339af0,stroke:#1c7ed6,stroke-width:2px,color:#000000',    // Bright blue bg, black text
                    'BASELINE': 'fill:#9775fa,stroke:#845ef7,stroke-width:2px,color:#000000'   // Bright purple bg, black text
                };
                const style = styleMap[tier] || styleMap['BASELINE'];
                styles += `    style ${controlKey} ${style}\n`;
                console.log('[DEBUG] Applied style for', controlKey, ':', style);
            } else {
                console.error('[DEBUG] Control not found for styling:', controlKey);
            }
        });

        const fullDiagram = diagram + styles;
        console.log('[DEBUG] Full After diagram:');
        console.log('[DEBUG] - Path nodes:', path.path.length);
        console.log('[DEBUG] - Control nodes added:', addedControls.size);
        console.log('[DEBUG] - Diagram length:', fullDiagram.length);
        console.log('[DEBUG] Full diagram content:\n', fullDiagram);
        return fullDiagram;
    }

    getControlPlacementForPath(control, path) {
        const hopAnalysis = control._layered_defense?.hop_analysis || [];
        const pathIndex = this.getPathIndex(path);

        const hopsInPath = hopAnalysis.filter(hop => hop.path_id === pathIndex);

        if (hopsInPath.length === 0) {
            return `Applied to ${path.id}`;
        }

        const nodes = [...new Set(hopsInPath.flatMap(hop => [hop.source_label, hop.target_label]))];
        return `Protects: ${nodes.map(n => n.replace(/"/g, '')).join(' → ')}`;
    }

    async loadMitreTab() {
        const matrixContainer = document.getElementById('mitre-matrix');

        if (!this.analysisData) {
            matrixContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const analysis = this.analysisData.analysis || {};
        const attackPaths = analysis.expected_attack_paths || [];

        // Collect all unique techniques from attack paths
        const techniques = new Set();
        attackPaths.forEach(path => {
            (path.techniques || []).forEach(t => techniques.add(t));
        });

        if (techniques.size === 0) {
            matrixContainer.innerHTML = '<p class="placeholder">No MITRE techniques identified in attack paths</p>';
            return;
        }

        // Fetch technique names
        const techniqueNames = await this.fetchTechniqueNames(Array.from(techniques));

        matrixContainer.innerHTML = `
            <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                ${techniques.size} MITRE ATT&CK techniques identified across ${attackPaths.length} attack paths
            </p>
        `;

        // Group by attack path
        attackPaths.forEach(path => {
            const pathTechniques = path.techniques || [];
            if (pathTechniques.length === 0) return;

            const criticalityColor =
                path.criticality_tier === 'CRITICAL' ? 'var(--danger-color)' :
                path.criticality_tier === 'HIGH' ? 'var(--warning-color)' :
                'var(--primary-color)';

            const section = document.createElement('div');
            section.style.cssText = `
                margin-bottom: 1.5rem;
                padding: 1rem;
                background: var(--card-bg);
                border-radius: 8px;
                border-left: 4px solid ${criticalityColor};
            `;

            section.innerHTML = `
                <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;">
                    <strong style="font-size: 1rem; color: var(--primary-color);">${path.id}</strong>
                    <span style="font-size: 0.875rem; color: var(--text-secondary);">
                        ${path.entry} → ${path.target}
                    </span>
                    <span style="margin-left: auto; padding: 0.25rem 0.75rem; background: ${criticalityColor}22; color: ${criticalityColor}; border-radius: 12px; font-size: 0.75rem; font-weight: 700;">
                        ${pathTechniques.length} techniques
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 0.5rem;">
                    ${pathTechniques.map(tech => `
                        <a href="https://attack.mitre.org/techniques/${tech}/" target="_blank"
                           style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; text-decoration: none; color: var(--text-color); border: 1px solid var(--border-color); transition: all 0.2s;"
                           onmouseover="this.style.borderColor='var(--primary-color)'; this.style.background='var(--list-hover-bg)'"
                           onmouseout="this.style.borderColor='var(--border-color)'; this.style.background='var(--nav-hover-bg)'">
                            <div style="flex: 1;">
                                <code style="font-weight: 700; color: var(--primary-color); font-size: 0.875rem;">${tech}</code>
                                <div style="font-size: 0.8125rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                    ${techniqueNames[tech] || 'Loading...'}
                                </div>
                            </div>
                            <span style="font-size: 0.75rem; color: var(--text-tertiary);">🔗</span>
                        </a>
                    `).join('')}
                </div>
            `;

            matrixContainer.appendChild(section);
        });
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
        const listContainer = document.getElementById('reports-list');

        if (!this.analysisData) {
            listContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const archName = this.analysisData.architecture_name;
        const reportPaths = this.analysisData.report_paths;

        // Check if reports were generated during analysis
        if (reportPaths && reportPaths.executive) {
            // Reports generated! Show them
            this.renderGeneratedReports(reportPaths, archName);
            this.updateStatusMessage(`✅ ${archName} reports ready`);
            return;
        }

        // Try to fetch reports from API (fallback for CLI-generated reports)
        listContainer.innerHTML = '<p class="placeholder">Loading reports...</p>';
        this.updateStatusMessage(`📄 Loading reports for ${archName}...`);

        try {
            const response = await fetch(`/api/v1/reports/${archName}`);
            if (!response.ok) {
                if (response.status === 404) {
                    // Architecture not found - reports not generated
                    listContainer.innerHTML = `
                        <div style="padding: 2rem; text-align: center;">
                            <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
                            <h3 style="color: var(--warning-color); margin-bottom: 1rem;">Reports Not Available</h3>
                            <p style="color: var(--text-secondary); margin-bottom: 1rem; font-size: 0.875rem;">
                                <strong>📊 All analysis data is available in the dashboard tabs:</strong>
                            </p>
                            <ul style="color: var(--text-secondary); font-size: 0.875rem; margin-left: 1.5rem; margin-bottom: 1.5rem; line-height: 1.8;">
                                <li><strong>📊 Overview</strong> - Threat heat map and architecture diagram</li>
                                <li><strong>🎯 Attack Paths</strong> - Step-by-step attack traversal with techniques</li>
                                <li><strong>🛡️ Controls</strong> - Security control recommendations with priorities</li>
                                <li><strong>🔒 Visualise</strong> - Before/after control placement visualization</li>
                                <li><strong>📋 MITRE</strong> - Complete technique coverage matrix</li>
                                <li><strong>💾 Raw Data</strong> - Complete JSON analysis (download via browser)</li>
                            </ul>
                            <div style="padding: 1rem; background: var(--warning-color)15; border-left: 4px solid var(--warning-color); border-radius: 8px; margin-bottom: 1rem;">
                                <h5 style="color: var(--warning-color); margin-bottom: 0.5rem;">🚧 Coming Soon: Downloadable Reports</h5>
                                <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem;">
                                    Automatic generation of Executive Dashboard, Technical Report, and Action Plan will be added in the next update.
                                </p>
                                <p style="color: var(--text-tertiary); font-size: 0.8125rem;">
                                    <em>Currently, these reports must be generated separately via CLI. This will be integrated into the web analysis flow soon for better UX.</em>
                                </p>
                            </div>
                            <p style="padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; color: var(--text-secondary); font-size: 0.875rem;">
                                💡 <strong>For now, to generate downloadable markdown reports:</strong><br>
                                Run: <code style="color: var(--primary-color);">python3 -m chatbot.main --gen-arch-truth your_architecture.mmd</code><br>
                                Reports saved to: <code>report/your_architecture/</code>
                            </p>
                        </div>
                    `;
                    return;
                }

                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const data = await response.json();
            this.renderReportsList(data);
            this.updateStatusMessage(`✅ Loaded ${data.count || 0} reports for ${archName}`);
        } catch (error) {
            console.error('Error loading reports:', error);
            listContainer.innerHTML = `
                <div style="padding: 2rem;">
                    <p style="color: var(--danger-color); margin-bottom: 1rem;">
                        ⚠️ Failed to load reports
                    </p>
                    <p style="color: var(--text-secondary); font-size: 0.875rem;">
                        ${error.message}
                    </p>
                </div>
            `;
        }
    }

    async fetchTechniqueNames(techniqueIds) {
        if (!techniqueIds || techniqueIds.length === 0) {
            return {};
        }

        // Check cache first
        const uncachedIds = techniqueIds.filter(id => !this.techniqueNamesCache[id]);

        if (uncachedIds.length === 0) {
            // All names are cached
            return techniqueIds.reduce((acc, id) => {
                acc[id] = this.techniqueNamesCache[id];
                return acc;
            }, {});
        }

        // Fetch uncached names
        try {
            const url = `/api/v1/techniques?technique_ids=${uncachedIds.join(',')}`;
            console.log('Fetching technique names:', url);

            // Show loading indicator in status
            if (uncachedIds.length > 5) {
                this.updateStatusMessage(`🔄 Loading ${uncachedIds.length} MITRE technique names...`);
            }

            const response = await fetch(url);
            if (!response.ok) {
                console.error('Failed to fetch technique names:', response.status, response.statusText);
                // Return IDs as fallback
                return techniqueIds.reduce((acc, id) => {
                    acc[id] = this.techniqueNamesCache[id] || id;
                    return acc;
                }, {});
            }

            const data = await response.json();
            const names = data.techniques || {};
            console.log('Fetched technique names:', names);

            // Update cache
            Object.assign(this.techniqueNamesCache, names);

            // Return all requested names (cached + newly fetched)
            return techniqueIds.reduce((acc, id) => {
                acc[id] = this.techniqueNamesCache[id] || id;
                return acc;
            }, {});
        } catch (error) {
            console.error('Error fetching technique names:', error);
            // Return IDs as fallback
            return techniqueIds.reduce((acc, id) => {
                acc[id] = id;
                return acc;
            }, {});
        }
    }

    renderGeneratedReports(reportPaths, archName) {
        const listContainer = document.getElementById('reports-list');

        const reports = [
            {
                id: 'executive',
                name: '01_executive_summary.md',
                title: 'Executive Summary',
                icon: '📊',
                description: 'High-level threat overview for executives and CISOs',
                path: reportPaths.executive,
                color: 'var(--primary-color)',
                type: 'markdown'
            },
            {
                id: 'technical',
                name: '02_technical_report.md',
                title: 'Technical Report',
                icon: '🔧',
                description: 'Detailed technical analysis with MITRE mappings',
                path: reportPaths.technical,
                color: 'var(--secondary-color)',
                type: 'markdown'
            },
            {
                id: 'action',
                name: '03_action_plan.md',
                title: 'Action Plan',
                icon: '✅',
                description: 'Prioritized recommendations and implementation steps',
                path: reportPaths.action_plan,
                color: 'var(--warning-color)',
                type: 'markdown'
            },
            {
                id: 'before-diagram',
                name: 'before.mmd',
                title: 'Before Diagram',
                icon: '⚠️',
                description: 'Original architecture diagram (before hardening)',
                path: reportPaths.before_diagram,
                color: 'var(--danger-color)',
                type: 'mermaid'
            },
            {
                id: 'after-diagram',
                name: 'after.mmd',
                title: 'After Diagram',
                icon: '🛡️',
                description: 'Hardened architecture with recommended controls',
                path: reportPaths.after_diagram,
                color: 'var(--secondary-color)',
                type: 'mermaid'
            }
        ];

        // Store reports for later access
        this.availableReports = reports;
        this.selectedReports = ['executive']; // Default to Executive
        this.activeReportTab = 'executive';
        this.reportContents = {}; // Cache loaded reports

        listContainer.innerHTML = `
            <!-- Filter Controls -->
            <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <label style="font-size: 0.875rem; font-weight: 600; color: var(--text-color);">Select Reports to View:</label>
                    <div style="display: flex; gap: 0.5rem;">
                        <button id="select-all-reports" style="padding: 0.375rem 0.75rem; border-radius: 6px; background: var(--secondary-color)22; color: var(--secondary-color); border: 1px solid var(--secondary-color); cursor: pointer; font-size: 0.8125rem; font-weight: 600;">
                            View All
                        </button>
                        <button id="clear-all-reports" style="padding: 0.375rem 0.75rem; border-radius: 6px; background: var(--warning-color)22; color: var(--warning-color); border: 1px solid var(--warning-color); cursor: pointer; font-size: 0.8125rem; font-weight: 600;">
                            Clear All
                        </button>
                    </div>
                </div>
                <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
                    ${reports.map(report => `
                        <label style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; background: var(--card-bg); border: 2px solid var(--border-color); border-radius: 8px; cursor: pointer; transition: all 0.2s;" class="report-filter-label" data-report-id="${report.id}">
                            <input type="checkbox" class="report-checkbox" value="${report.id}" ${report.id === 'executive' ? 'checked' : ''} style="cursor: pointer; width: 18px; height: 18px;">
                            <span style="font-size: 1.25rem;">${report.icon}</span>
                            <span style="font-weight: 600; color: var(--text-color);">${report.title}</span>
                        </label>
                    `).join('')}
                </div>
                <div style="margin-top: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">
                    <strong id="report-count">1</strong> report(s) selected
                </div>
            </div>

            <!-- Report Tabs (shown when multiple selected) -->
            <div id="report-tabs-container" style="display: none; margin-bottom: 1rem;">
                <div id="report-tabs" style="display: flex; gap: 0.5rem; border-bottom: 2px solid var(--border-color); padding-bottom: 0.5rem; overflow-x: auto;">
                </div>
            </div>

            <!-- Report Viewer -->
            <div id="report-viewer" style="background: var(--card-bg); border-radius: 8px; padding: 1.5rem; min-height: 500px;">
                <p style="color: var(--text-secondary); text-align: center; padding: 2rem;">
                    Loading report...
                </p>
            </div>

            <!-- Download Section -->
            <div style="margin-top: 1.5rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                <div style="flex: 1;">
                    <p style="color: var(--text-secondary); font-size: 0.875rem;">
                        Reports saved to: <code style="color: var(--primary-color);">report/${archName}/</code>
                    </p>
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    <button id="download-current-report" class="btn-primary" style="padding: 0.5rem 1rem; font-size: 0.875rem;">
                        ⬇ Download Current
                    </button>
                </div>
            </div>
        `;

        // Setup event listeners
        this.setupReportFilters(archName);

        // Load initial report
        this.loadSelectedReports(archName);
    }

    setupReportFilters(archName) {
        // Get filter elements
        const checkboxes = document.querySelectorAll('.report-checkbox');
        const selectAllBtn = document.getElementById('select-all-reports');
        const clearAllBtn = document.getElementById('clear-all-reports');
        const reportCount = document.getElementById('report-count');

        // Handle checkbox changes
        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                // Update selected reports array
                this.selectedReports = Array.from(checkboxes)
                    .filter(cb => cb.checked)
                    .map(cb => cb.value);

                // Update UI
                reportCount.textContent = this.selectedReports.length;

                // Update visual state of labels
                const label = checkbox.closest('.report-filter-label');
                if (checkbox.checked) {
                    label.style.borderColor = 'var(--primary-color)';
                    label.style.background = 'var(--primary-color)15';
                } else {
                    label.style.borderColor = 'var(--border-color)';
                    label.style.background = 'var(--card-bg)';
                }

                // Reload reports with new selection
                this.loadSelectedReports(archName);
            });

            // Set initial label state
            const label = checkbox.closest('.report-filter-label');
            if (checkbox.checked) {
                label.style.borderColor = 'var(--primary-color)';
                label.style.background = 'var(--primary-color)15';
            }
        });

        // Handle "View All" button
        selectAllBtn.addEventListener('click', () => {
            checkboxes.forEach(cb => {
                cb.checked = true;
                const label = cb.closest('.report-filter-label');
                label.style.borderColor = 'var(--primary-color)';
                label.style.background = 'var(--primary-color)15';
            });

            this.selectedReports = Array.from(checkboxes).map(cb => cb.value);
            reportCount.textContent = this.selectedReports.length;
            this.loadSelectedReports(archName);
        });

        // Handle "Clear All" button
        clearAllBtn.addEventListener('click', () => {
            checkboxes.forEach(cb => {
                cb.checked = false;
                const label = cb.closest('.report-filter-label');
                label.style.borderColor = 'var(--border-color)';
                label.style.background = 'var(--card-bg)';
            });

            this.selectedReports = [];
            reportCount.textContent = '0';

            // Show message in viewer
            const viewer = document.getElementById('report-viewer');
            viewer.innerHTML = `
                <p style="color: var(--text-secondary); text-align: center; padding: 2rem;">
                    Select at least one report to view
                </p>
            `;

            // Hide tabs
            document.getElementById('report-tabs-container').style.display = 'none';
        });
    }

    async loadSelectedReports(archName) {
        const viewer = document.getElementById('report-viewer');
        const tabsContainer = document.getElementById('report-tabs-container');
        const tabsDiv = document.getElementById('report-tabs');

        // No reports selected
        if (this.selectedReports.length === 0) {
            viewer.innerHTML = `
                <p style="color: var(--text-secondary); text-align: center; padding: 2rem;">
                    Select at least one report to view
                </p>
            `;
            tabsContainer.style.display = 'none';
            return;
        }

        // Single report selected - show directly (no tabs)
        if (this.selectedReports.length === 1) {
            tabsContainer.style.display = 'none';
            this.activeReportTab = this.selectedReports[0];
            await this.renderReportInViewer(this.activeReportTab, archName);
            return;
        }

        // Multiple reports selected - show tabs
        tabsContainer.style.display = 'block';

        // Render tabs
        tabsDiv.innerHTML = this.selectedReports.map(reportId => {
            const report = this.availableReports.find(r => r.id === reportId);
            const isActive = reportId === this.activeReportTab;

            return `
                <button class="report-tab ${isActive ? 'active' : ''}" data-report-id="${reportId}" style="
                    padding: 0.5rem 1rem;
                    background: ${isActive ? 'var(--primary-color)' : 'transparent'};
                    color: ${isActive ? 'var(--button-text-color)' : 'var(--text-color)'};
                    border: 2px solid ${isActive ? 'var(--primary-color)' : 'var(--border-color)'};
                    border-bottom: none;
                    border-radius: 8px 8px 0 0;
                    cursor: pointer;
                    font-weight: 600;
                    font-size: 0.875rem;
                    transition: all 0.2s;
                    white-space: nowrap;
                ">
                    ${report.icon} ${report.title}
                </button>
            `;
        }).join('');

        // Add tab click handlers
        tabsDiv.querySelectorAll('.report-tab').forEach(tab => {
            tab.addEventListener('click', async () => {
                const reportId = tab.dataset.reportId;
                this.activeReportTab = reportId;

                // Update tab styles
                tabsDiv.querySelectorAll('.report-tab').forEach(t => {
                    const isActive = t.dataset.reportId === reportId;
                    t.classList.toggle('active', isActive);
                    t.style.background = isActive ? 'var(--primary-color)' : 'transparent';
                    t.style.color = isActive ? 'var(--button-text-color)' : 'var(--text-color)';
                    t.style.borderColor = isActive ? 'var(--primary-color)' : 'var(--border-color)';
                });

                // Load report content
                await this.renderReportInViewer(reportId, archName);
            });
        });

        // Load initial tab content
        await this.renderReportInViewer(this.activeReportTab, archName);
    }

    async renderReportInViewer(reportId, archName) {
        const viewer = document.getElementById('report-viewer');
        const report = this.availableReports.find(r => r.id === reportId);

        if (!report) {
            viewer.innerHTML = '<p style="color: var(--danger-color);">Report not found</p>';
            return;
        }

        // Check if already cached (but skip cache for mermaid diagrams - they need re-rendering)
        if (this.reportContents[reportId] && report.type !== 'mermaid') {
            viewer.innerHTML = this.reportContents[reportId];
            this.applyCodeHighlighting(viewer);
            return;
        }

        // Show loading state
        viewer.innerHTML = `
            <div style="text-align: center; padding: 3rem; color: var(--text-secondary);">
                <div style="font-size: 2rem; margin-bottom: 1rem;">${report.icon}</div>
                <h4 style="margin-bottom: 0.5rem; color: var(--text-color);">Loading ${report.title}...</h4>
                <p style="font-size: 0.875rem;">Fetching markdown content</p>
            </div>
        `;

        try {
            // Fetch content
            const response = await fetch(`/api/v1/reports/${archName}/files/${report.name}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const content = await response.text();
            let htmlContent;

            // Handle mermaid diagrams differently
            if (report.type === 'mermaid') {
                htmlContent = `
                    <!-- Diagram controls -->
                    <div style="margin-bottom: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap;">
                        <button id="report-diagram-zoom-in" class="btn-icon" title="Zoom In">🔍+</button>
                        <button id="report-diagram-zoom-out" class="btn-icon" title="Zoom Out">🔍−</button>
                        <button id="report-diagram-zoom-reset" class="btn-icon" title="Reset Zoom">↺</button>
                        <div style="width: 1px; height: 24px; background: var(--border-color); margin: 0 0.25rem;"></div>
                        <button id="report-diagram-fit-width" class="btn-icon" title="Fit to Width">↔️</button>
                        <button id="report-diagram-fit-height" class="btn-icon" title="Fit to Height">↕️</button>
                    </div>
                    <div id="report-diagram-container" style="padding: 1rem; background: var(--code-bg); border-radius: 8px; overflow: auto; max-height: 600px; border: 2px solid ${report.color};">
                        <div class="mermaid" id="report-diagram">${content}</div>
                    </div>
                `;
            } else {
                // Convert markdown to HTML
                htmlContent = window.marked ? marked.parse(content) : `<pre>${content}</pre>`;
            }

            // Build full HTML with header and content
            const fullHtml = `
                <div style="margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 2px solid var(--border-color);">
                    <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                        <span style="font-size: 2rem;">${report.icon}</span>
                        <h3 style="margin: 0; color: ${report.color};">${report.title}</h3>
                    </div>
                    <p style="color: var(--text-secondary); font-size: 0.875rem; margin: 0;">
                        ${report.description}
                    </p>
                </div>
                <div class="${report.type === 'mermaid' ? '' : 'markdown-content'}" style="line-height: 1.7; color: var(--text-color);">
                    ${htmlContent}
                </div>
            `;

            // Cache and display (don't cache mermaid diagrams - they need fresh rendering)
            if (report.type !== 'mermaid') {
                this.reportContents[reportId] = fullHtml;
            }
            viewer.innerHTML = fullHtml;

            // Render mermaid if diagram
            if (report.type === 'mermaid' && window.mermaid) {
                try {
                    // Wait for DOM to be ready
                    await new Promise(resolve => setTimeout(resolve, 100));

                    const diagramElement = document.querySelector('#report-diagram');
                    if (diagramElement) {
                        await mermaid.run({
                            nodes: [diagramElement]
                        });
                        console.log('[DEBUG] Report diagram rendered successfully');

                        // Setup zoom controls after render
                        await new Promise(resolve => setTimeout(resolve, 100));
                        this.setupDiagramZoom('report-diagram');
                        console.log('[DEBUG] Zoom controls attached for report diagram');
                    } else {
                        console.error('[DEBUG] Report diagram element not found');
                    }
                } catch (error) {
                    console.error('Mermaid rendering failed:', error);
                }
            } else {
                // Apply syntax highlighting for markdown
                this.applyCodeHighlighting(viewer);
            }

            // Update download button
            this.updateDownloadButton(report, archName);

        } catch (error) {
            console.error('Error loading report:', error);
            viewer.innerHTML = `
                <div style="padding: 2rem; text-align: center;">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
                    <h4 style="color: var(--danger-color); margin-bottom: 0.5rem;">Failed to Load Report</h4>
                    <p style="color: var(--text-secondary); font-size: 0.875rem;">${error.message}</p>
                    <button onclick="window.location.reload()" class="btn-primary" style="margin-top: 1rem;">
                        🔄 Retry
                    </button>
                </div>
            `;
        }
    }

    applyCodeHighlighting(container) {
        // Apply syntax highlighting to code blocks if hljs available
        if (window.hljs) {
            container.querySelectorAll('pre code').forEach(block => {
                hljs.highlightBlock(block);
            });
        }
    }

    updateDownloadButton(report, archName) {
        const downloadBtn = document.getElementById('download-current-report');
        if (downloadBtn) {
            downloadBtn.onclick = () => {
                window.open(`/api/v1/reports/${archName}/files/${report.name}`, '_blank');
            };
        }
    }

    async viewGeneratedReport(report, archName) {
        const rightPaneContent = document.getElementById('right-pane-content');
        const rightPane = document.getElementById('right-pane');

        try {
            // Show loading state
            rightPaneContent.innerHTML = `
                <h3>${report.title}</h3>
                <p style="color: var(--text-secondary); margin-bottom: 1rem;">Loading report...</p>
            `;
            rightPane.classList.add('visible');

            // Fetch the markdown file
            const response = await fetch(`/api/v1/reports/${archName}/files/${report.name}`);
            if (!response.ok) {
                throw new Error(`Failed to load report: ${response.statusText}`);
            }

            const markdown = await response.text();

            // Render markdown to HTML
            const htmlContent = window.marked ? marked.parse(markdown) : markdown;

            rightPaneContent.innerHTML = `
                <div style="margin-bottom: 1rem;">
                    <a href="/api/v1/reports/${archName}/files/${report.name}" download="${report.name}" class="btn-primary" style="display: inline-block; text-decoration: none; padding: 0.5rem 1rem;">
                        ⬇ Download ${report.name}
                    </a>
                </div>
                <div style="padding: 1.5rem; background: var(--code-bg); border-radius: 8px; max-height: 70vh; overflow-y: auto; line-height: 1.6;">
                    ${htmlContent}
                </div>
            `;

            // Apply syntax highlighting if available
            if (window.hljs) {
                rightPaneContent.querySelectorAll('pre code').forEach(block => {
                    hljs.highlightBlock(block);
                });
            }

        } catch (error) {
            console.error('Error loading report:', error);
            rightPaneContent.innerHTML = `
                <h3>${report.title}</h3>
                <div style="padding: 1rem; background: var(--danger-color)15; border-left: 4px solid var(--danger-color); border-radius: 8px; margin-top: 1rem;">
                    <p style="color: var(--danger-color); font-weight: 600;">⚠️ Failed to load report</p>
                    <p style="color: var(--text-secondary); font-size: 0.875rem; margin-top: 0.5rem;">${error.message}</p>
                </div>
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
        const mmdFiles = data.reports.filter(r => r.type === 'mermaid');
        const mdReports = data.reports.filter(r => r.type === 'markdown');
        const jsonFiles = data.reports.filter(r => r.type === 'json');
        const otherFiles = data.reports.filter(r => r.type === 'text');

        // Render mermaid diagrams
        if (mmdFiles.length > 0) {
            const section = document.createElement('div');
            section.style.marginBottom = '1.5rem';
            section.innerHTML = '<h5 style="margin-bottom: 0.75rem; color: var(--primary-color);">🏗️ Architecture Diagrams</h5>';

            mmdFiles.forEach(report => {
                const item = this.createReportItem(report, data.architecture);
                section.appendChild(item);
            });

            listContainer.appendChild(section);
        }

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
                    report.type === 'json' ? '📊' :
                    report.type === 'mermaid' ? '🏗️' : '📄';

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

    async loadExpertReviewTab() {
        const container = document.getElementById('expert-review-content');
        if (!this.analysisData) {
            container.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const archName = this.analysisData.architecture_name || this.analysisData.architecture;
        if (!archName) {
            container.innerHTML = '<p class="placeholder">Architecture name not found</p>';
            return;
        }

        container.innerHTML = '<p class="placeholder">Loading expert review data...</p>';

        try {
            const response = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (!response.ok) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 3rem 2rem;">
                        <div style="font-size: 3rem; margin-bottom: 1rem;">🧑‍🏫</div>
                        <h3 style="color: var(--text-color); margin-bottom: 0.75rem;">Expert Review Not Run</h3>
                        <p style="color: var(--text-secondary); max-width: 400px; margin: 0 auto 1.5rem;">
                            The expert panel (Architecture Review, Coverage Audit, Exploit Analysis) has not reviewed this assessment yet.
                            Running it increases confidence from the Foundation Score and unlocks the Improvement Roadmap.
                        </p>
                        <p style="color: var(--text-tertiary); font-size: 0.875rem;">
                            Expert Review is currently available via CLI: <code>./demo_expert_llm.sh ${archName}.mmd</code>
                        </p>
                    </div>`;
                return;
            }

            const moe = await response.json();
            const confidence = moe.confidence || {};
            const expertValidations = moe.expert_validations || {};
            const consensusRecs = moe.consensus_recommendations || [];

            const expertDefs = [
                { key: 'architect', icon: '🏛️', label: 'Architecture Review', role: 'Design quality & threat completeness' },
                { key: 'tester',    icon: '🔬', label: 'Coverage Audit',       role: 'MITRE mapping accuracy' },
                { key: 'red_team',  icon: '🎯', label: 'Exploit Analysis',     role: 'Control effectiveness under attack' },
            ];

            const statusColor = {
                'PASS': 'var(--secondary-color)',
                'MINOR_GAPS': 'var(--warning-color)',
                'MAJOR_GAPS': 'var(--danger-color)',
                'FAIL': 'var(--danger-color)',
            };

            const finalConf = (confidence.final || 0).toFixed(1);
            const baseConf  = (confidence.base  || 99.5).toFixed(1);
            const interp    = confidence.interpretation || '';

            container.innerHTML = `
                <!-- Confidence Waterfall -->
                <div style="background: var(--card-bg); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid var(--border-color);">
                    <h3 style="margin: 0 0 1rem; color: var(--text-color); font-size: 1rem;">Confidence Progression</h3>
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        <div style="text-align: center; min-width: 80px;">
                            <div style="font-size: 1.25rem; font-weight: 700; color: var(--secondary-color);">${baseConf}%</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">Foundation</div>
                        </div>
                        ${expertDefs.map(e => {
                            const v = expertValidations[e.key];
                            if (!v) return '';
                            const adj = ((v.confidence_adjustment || 0) * 100).toFixed(1);
                            const sign = adj >= 0 ? '+' : '';
                            return `
                                <div style="color: var(--text-tertiary); font-size: 1.25rem;">→</div>
                                <div style="text-align: center; min-width: 80px;">
                                    <div style="font-size: 1rem; font-weight: 600; color: var(--warning-color);">${sign}${adj}%</div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">${e.label}</div>
                                </div>`;
                        }).join('')}
                        <div style="color: var(--text-tertiary); font-size: 1.25rem;">→</div>
                        <div style="text-align: center; min-width: 80px;">
                            <div style="font-size: 1.25rem; font-weight: 700; color: var(--primary-color);">${finalConf}%</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">Validated</div>
                        </div>
                    </div>
                    ${interp ? `<p style="margin: 0.75rem 0 0; font-size: 0.875rem; color: var(--text-secondary);">${interp}</p>` : ''}
                </div>

                <!-- Expert Panels -->
                <div style="display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.5rem;">
                    ${expertDefs.map(e => {
                        const v = expertValidations[e.key];
                        if (!v) return '';
                        const adj = ((v.confidence_adjustment || 0) * 100).toFixed(1);
                        const sign = adj >= 0 ? '+' : '';
                        const status = v.validation_status || 'UNKNOWN';
                        const color = statusColor[status] || 'var(--text-secondary)';
                        const gaps = v.gaps || [];
                        return `
                        <div style="background: var(--card-bg); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden;">
                            <div style="padding: 1rem 1.25rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color);">
                                <div style="display: flex; align-items: center; gap: 0.75rem;">
                                    <span style="font-size: 1.5rem;">${e.icon}</span>
                                    <div>
                                        <div style="font-weight: 700; color: var(--text-color);">${e.label}</div>
                                        <div style="font-size: 0.8125rem; color: var(--text-secondary);">${e.role}</div>
                                    </div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 1.125rem; font-weight: 700; color: var(--warning-color);">${sign}${adj}%</div>
                                    <div style="font-size: 0.75rem; font-weight: 600; color: ${color};">${status.replace('_', ' ')}</div>
                                </div>
                            </div>
                            ${gaps.length > 0 ? `
                            <div style="padding: 1rem 1.25rem;">
                                <div style="font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.75rem;">${gaps.length} finding${gaps.length > 1 ? 's' : ''}</div>
                                ${gaps.map(g => `
                                    <div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid ${g.severity === 'HIGH' || g.severity === 'CRITICAL' ? 'var(--danger-color)' : 'var(--warning-color)'};">
                                        <div style="font-size: 0.8125rem; font-weight: 600; color: var(--text-color); margin-bottom: 0.25rem;">${g.category ? g.category.replace(/_/g, ' ').toUpperCase() : ''} · <span style="color: ${g.severity === 'HIGH' || g.severity === 'CRITICAL' ? 'var(--danger-color)' : 'var(--warning-color)'};">${g.severity || ''}</span></div>
                                        <div style="font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.5rem;">${g.description || ''}</div>
                                        ${g.recommendation ? `<div style="font-size: 0.8125rem; color: var(--secondary-color);">→ ${g.recommendation}</div>` : ''}
                                    </div>`).join('')}
                            </div>` : ''}
                        </div>`;
                    }).join('')}
                </div>

                <!-- Consensus -->
                ${consensusRecs.length > 0 ? `
                <div style="background: var(--card-bg); border-radius: 10px; padding: 1.25rem; border: 1px solid var(--border-color);">
                    <h3 style="margin: 0 0 1rem; color: var(--text-color); font-size: 1rem;">Consensus Recommendations</h3>
                    <p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0 0 1rem;">Items all three experts agree on — highest confidence to act on first.</p>
                    ${consensusRecs.map(r => `
                        <div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--secondary-color);">
                            <div style="font-size: 0.875rem; color: var(--text-color);">${typeof r === 'string' ? r : (r.recommendation || r.description || JSON.stringify(r))}</div>
                        </div>`).join('')}
                </div>` : ''}
            `;
        } catch (err) {
            container.innerHTML = `<p class="placeholder">Error loading expert review: ${err.message}</p>`;
        }
    }

    loadRawDataTab() {
        const listContainer = document.getElementById('artifacts-list');

        if (!this.analysisData) {
            listContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const analysis = this.analysisData.analysis || {};

        // Build comprehensive artifact list
        const artifacts = [
            { name: 'ground_truth.json', data: analysis, description: 'Complete analysis results' },
            { name: 'architecture_name', data: { architecture_name: this.analysisData.architecture_name }, description: 'Architecture identifier' },
            { name: 'confidence', data: { confidence: this.analysisData.confidence }, description: 'Analysis confidence score' },
            { name: 'patterns_applied', data: { patterns_applied: this.analysisData.patterns_applied }, description: 'Threat patterns detected' }
        ];

        // Add individual components if they exist
        if (analysis.controls_present || analysis.controls_missing) {
            artifacts.push({
                name: 'controls',
                data: {
                    controls_present: analysis.controls_present || [],
                    controls_missing: analysis.controls_missing || []
                },
                description: 'Present and missing security controls'
            });
        }

        if (analysis.expected_attack_paths) {
            artifacts.push({
                name: 'attack_paths',
                data: { expected_attack_paths: analysis.expected_attack_paths },
                description: `${analysis.expected_attack_paths.length} attack paths identified`
            });
        }

        if (analysis.control_recommendations) {
            artifacts.push({
                name: 'control_recommendations',
                data: { control_recommendations: analysis.control_recommendations },
                description: `${analysis.control_recommendations.length} control recommendations`
            });
        }

        if (analysis.threats) {
            artifacts.push({
                name: 'rapids_threats',
                data: { threats: analysis.threats },
                description: 'RAPIDS threat assessment scores'
            });
        }

        if (analysis.ai_ml_risks) {
            artifacts.push({
                name: 'ai_ml_risks',
                data: { ai_ml_risks: analysis.ai_ml_risks },
                description: 'AI/ML risk analysis (ARC Framework)'
            });
        }

        listContainer.innerHTML = `
            <p style="margin-bottom: 1rem; color: var(--text-secondary); font-size: 0.875rem;">
                ${artifacts.length} artifacts available · Click to view JSON data
            </p>
        `;

        artifacts.forEach(artifact => {
            const item = document.createElement('div');
            item.className = 'list-item';
            item.style.cssText = 'padding: 1rem; cursor: pointer;';

            const sizeKB = (JSON.stringify(artifact.data).length / 1024).toFixed(1);

            item.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 600; margin-bottom: 0.25rem;">📊 ${artifact.name}</div>
                        <div style="font-size: 0.8125rem; color: var(--text-secondary);">
                            ${artifact.description} · ${sizeKB} KB
                        </div>
                    </div>
                    <span style="color: var(--primary-color);">→</span>
                </div>
            `;

            item.addEventListener('click', () => {
                listContainer.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                item.classList.add('active');
                this.showArtifact(artifact);
            });

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
