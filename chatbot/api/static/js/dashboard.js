// ThreatAssessor Dashboard - Main Controller

class Dashboard {
    constructor() {
        this.analysisData = null;
        this.currentTab = 'overview';
        this.sseClient = null;
        this.uploadedFile = null;
        this.techniqueNamesCache = {};
        this.sspProfile = 'low_risk_cloud'; // updated from selector at submit time

        // Expert Review in-progress state — persists across tab switches
        this._erpState = null;

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

        // Poll /health until MITRE cache is ready (typically <1s after server start)
        this._pollReadiness();

        // Populate architecture history dropdown from existing reports
        this._loadArchHistory();

        // Pre-load config tab only if authenticated (key present)
        if (localStorage.getItem('tm_api_key')) {
            this.loadConfigTab();
        }
    }

    _pollReadiness() {
        const uploadBtn = document.getElementById('upload-btn');
        const dropZone  = document.getElementById('drop-zone');

        const check = async () => {
            try {
                const res = await fetch('/health');
                if (!res.ok) return scheduleNext();
                const data = await res.json();
                if (data?.services?.mitre_cache === 'ready') {
                    // Re-enable upload controls
                    if (uploadBtn) {
                        uploadBtn.disabled = false;
                        uploadBtn.title = '';
                        if (uploadBtn.dataset.warmup) {
                            uploadBtn.textContent = uploadBtn.dataset.origLabel || 'Analyze';
                            delete uploadBtn.dataset.warmup;
                        }
                    }
                    if (dropZone) dropZone.classList.remove('warmup-pending');
                    this.updateProgress(0, 'Ready to analyze architecture');
                } else {
                    // Cache still loading — disable upload and show hint
                    if (uploadBtn && !uploadBtn.dataset.warmup) {
                        uploadBtn.dataset.warmup = '1';
                        uploadBtn.dataset.origLabel = uploadBtn.textContent;
                        uploadBtn.disabled = true;
                        uploadBtn.title = 'Initializing threat database…';
                    }
                    if (dropZone) dropZone.classList.add('warmup-pending');
                    this.updateProgress(0, 'Initializing threat database…');
                    scheduleNext();
                }
            } catch (_) {
                scheduleNext();
            }
        };

        const scheduleNext = () => setTimeout(check, 500);
        check();
    }

    initSettings() {
        const settingsBtn = document.getElementById('settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => this.showSettings());
        }
        // Show/hide config tab based on whether an API key is already stored
        this._syncConfigTabVisibility();
    }

    _syncConfigTabVisibility() {
        const tab = document.getElementById('config-nav-tab');
        if (!tab) return;
        const hasKey = !!localStorage.getItem('tm_api_key');
        tab.style.display = hasKey ? '' : 'none';
        // If the config tab is currently active and the key was just removed, go home
        if (!hasKey && this.currentTab === 'config') {
            this.switchTab('overview');
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
            this._syncConfigTabVisibility();
            alert('✅ API key saved!\n\nYou can now upload architectures for analysis.\nThe Configuration tab is now unlocked.');
        } else if (newKey === '') {
            const confirmClear = confirm('Clear saved API key?\n\nThis will also hide the Configuration tab.');
            if (confirmClear) {
                localStorage.removeItem('tm_api_key');
                this._syncConfigTabVisibility();
                alert('API key cleared.');
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

    // Tabs that require a completed analysis to be meaningful
    _contentTabs() {
        return ['attacks', 'controls', 'hardening', 'expert-review', 'threat-model', 'reports', 'raw-data'];
    }

    _setContentTabsDisabled(disabled) {
        this._contentTabs().forEach(name => {
            const tab = document.querySelector(`.nav-tab[data-tab="${name}"]`);
            if (!tab) return;
            if (disabled) {
                tab.classList.add('disabled');
            } else {
                tab.classList.remove('disabled');
            }
        });
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

        const isConfig = tabName === 'config';
        const uploadContainer = document.getElementById('upload-form-container');
        const tabContent      = document.getElementById('tab-content');
        const configWrapper   = document.getElementById('config-pane-wrapper');

        if (isConfig) {
            // Config takes the full main pane — hide everything else
            if (uploadContainer) uploadContainer.style.display = 'none';
            if (tabContent)      tabContent.style.display      = 'none';
            if (configWrapper)   { configWrapper.style.display = 'flex'; configWrapper.style.flexDirection = 'column'; }
        } else {
            if (configWrapper) configWrapper.style.display = 'none';
            // Restore the correct non-config pane
            if (this.analysisData) {
                if (tabContent) tabContent.style.display = 'block';
                document.querySelectorAll('.tab-pane').forEach(pane => {
                    pane.classList.toggle('active', pane.dataset.tab === tabName);
                });
            } else {
                if (uploadContainer) uploadContainer.style.display = 'block';
            }
        }

        this.currentTab = tabName;

        // Update status message
        const tabNames = {
            'overview': 'Overview',
            'attacks': 'Threat Paths',
            'controls': 'Mitigations',
            'hardening': 'Visualise',
            'expert-review': 'Expert Review',
            'reports': 'Reports',
            'raw-data': 'Raw Data',
            'config': 'Configuration'
        };
        this.updateStatusMessage(`📂 Viewing ${tabNames[tabName] || tabName}`);

        if (isConfig) {
            this.loadConfigTab();
        } else if (this.analysisData) {
            this.loadTabData(tabName);
        }
    }

    initUpload() {
        const uploadForm = document.getElementById('upload-form');
        const uploadBtn = document.getElementById('upload-btn');
        const newAnalysisBtn = document.getElementById('new-analysis-btn');
        const fileInput = document.getElementById('file-input');
        const dropZone = document.getElementById('drop-zone');

        // Header upload button — shows file picker when no analysis is active
        uploadBtn.addEventListener('click', () => {
            fileInput.click();
        });

        // New analysis button click (header, shown after analysis)
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

        // Form-level action buttons: Clear · Upload · Analyse
        const clearFileBtn = document.getElementById('clear-file-btn');
        const pickFileBtn  = document.getElementById('pick-file-btn');

        if (clearFileBtn) {
            clearFileBtn.addEventListener('click', () => {
                fileInput.value = '';
                const label = document.getElementById('drop-zone-label');
                if (label) label.textContent = 'Drag & drop .mmd file here or click to browse';
            });
        }

        if (pickFileBtn) {
            pickFileBtn.addEventListener('click', () => {
                fileInput.click();
            });
        }

        // Update drop-zone label when a file is selected via any path
        fileInput.addEventListener('change', () => {
            const label = document.getElementById('drop-zone-label');
            if (label && fileInput.files.length) {
                label.textContent = `📄 ${fileInput.files[0].name}`;
            }
        });

        // Form submit
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.startAnalysis();
        });

        // Drag and drop — clicking drop zone now only opens picker if no dedicated button clicked
        dropZone.addEventListener('click', (e) => {
            if (!e.target.closest('button')) fileInput.click();
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
                const dt = new DataTransfer();
                dt.items.add(files[0]);
                fileInput.files = dt.files;
                const label = document.getElementById('drop-zone-label');
                if (label) label.textContent = `📄 ${files[0].name}`;
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

        // Grey out content tabs while analysis is in progress
        this._setContentTabsDisabled(true);

        // Reset progress
        this.updateProgress(0, 'Starting analysis...');

        // Capture SSP profile from selector
        const sspSelect = document.getElementById('ssp-profile-select');
        this.sspProfile = sspSelect ? sspSelect.value : 'low_risk_cloud';
        this._updateSspBadge();

        // Start SSE connection
        const formData = new FormData();
        formData.append('architecture_file', file);
        formData.append('include_validation', 'true');
        formData.append('ssp_profile', this.sspProfile);
        formData.append('enable_ssp', 'true');

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

        // If on overview tab, update chart and dashboard immediately
        if (this.currentTab === 'overview') {
            this.renderThreatChart();
            this.renderOverviewDashboard();
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

        // Always show Expert Review tab when analysis is loaded (tab shows Run button if MoE not run yet)
        const expertReviewTab = document.querySelector('.nav-tab[data-tab="expert-review"]');
        if (expertReviewTab) expertReviewTab.style.display = 'block';

        // Show Threat Model tab when analysis is loaded
        const tmNavTab = document.getElementById('threat-model-nav-tab');
        if (tmNavTab) tmNavTab.style.display = 'block';

        // Enable content tabs now that analysis data is available
        this._setContentTabsDisabled(false);

        // Show analysis status bar
        this._updateAnalysisStatusBar();

        // Refresh history dropdown so new analysis appears at the top
        this._loadArchHistory();

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

        // Reset file input and drop-zone label
        const fileInput = document.getElementById('file-input');
        if (fileInput) fileInput.value = '';
        const dropZoneLabel = document.getElementById('drop-zone-label');
        if (dropZoneLabel) dropZoneLabel.textContent = 'Drag & drop .mmd file here or click to browse';

        // Reset analysis status bar
        const statusBar = document.getElementById('analysis-status-bar');
        if (statusBar) statusBar.style.display = 'none';
        const statusPlaceholder = document.getElementById('pattern-badges-placeholder');
        if (statusPlaceholder) statusPlaceholder.style.display = 'flex';
        const patternBadges = document.getElementById('pattern-badges');
        if (patternBadges) patternBadges.innerHTML = '';
        const moeEl = document.getElementById('status-moe');
        if (moeEl) moeEl.style.display = 'none';

        // Hide Expert Review tab until MoE data confirmed
        const expertReviewTab = document.querySelector('.nav-tab[data-tab="expert-review"]');
        if (expertReviewTab) expertReviewTab.style.display = 'none';
        // Hide Threat Model tab on reset
        const tmNavTabReset = document.getElementById('threat-model-nav-tab');
        if (tmNavTabReset) tmNavTabReset.style.display = 'none';

        // Grey out content tabs — no data to show
        this._setContentTabsDisabled(true);

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

        // Stop any in-progress animated tick
        if (this._progressTickTimer) {
            clearInterval(this._progressTickTimer);
            this._progressTickTimer = null;
        }

        this._lastReportedPct = percent;
        // Store the base message (without % and ETA) for the tick to update
        this._lastProgressMessage = message;
        this._lastProgressEta = eta && eta > 0 ? eta : null;

        progressFill.style.width = `${percent}%`;
        progressText.textContent = `${percent}%`;

        // Replace inline % in message with live value and append live ETA
        const _buildStatusText = (pct, msg, etaSecs) => {
            // Replace "[STAGE] N% -" pattern with current pct
            let text = msg.replace(/(\[\w+\/?\w*\])\s*\d+%/, `$1 ${Math.round(pct)}%`);
            if (etaSecs && etaSecs > 0) text += ` (${Math.round(etaSecs)}s)`;
            return text;
        };
        statusMessage.textContent = _buildStatusText(percent, message, this._lastProgressEta);

        // Animated tick: bar inches forward between SSE events; message % + ETA also update
        if (percent > 0 && percent < 99) {
            const ceiling = Math.min(percent + 12, 99);
            let tickEta = this._lastProgressEta;
            this._progressTickTimer = setInterval(() => {
                const fill = document.getElementById('progress-fill');
                const pctEl = document.getElementById('progress-text');
                const statusEl = document.getElementById('status-message');
                if (!fill) { clearInterval(this._progressTickTimer); return; }
                const cur = parseFloat(fill.style.width) || percent;
                if (cur >= ceiling) {
                    // Bar frozen at ceiling — keep ETA counting down only
                    if (tickEta !== null) {
                        tickEta = Math.max(0, tickEta - 0.6);
                        if (statusEl && this._lastProgressMessage) {
                            statusEl.textContent = _buildStatusText(ceiling, this._lastProgressMessage, tickEta);
                        }
                    }
                    return;
                }
                const next = Math.min(cur + 0.4, ceiling);
                fill.style.width = next + '%';
                if (pctEl) pctEl.textContent = Math.round(next) + '%';
                // Estimate ETA: count down proportionally as bar advances
                if (tickEta !== null) tickEta = Math.max(0, tickEta - 0.6);
                if (statusEl && this._lastProgressMessage) {
                    statusEl.textContent = _buildStatusText(next, this._lastProgressMessage, tickEta);
                }
            }, 600);
        }
    }

    updateStatusMessage(message) {
        const statusMessage = document.getElementById('status-message');
        if (statusMessage) {
            statusMessage.textContent = message;
        }
    }

    updateStages(currentStage) {
        const stages = document.querySelectorAll('.stage');
        const stageOrder = ['parsing', 'rapids', 'ai_ml', 'validation'];

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
            case 'threat-model':
                this.loadThreatModelTab();
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
        this.diagramRendered = false;
        this.renderOverviewDashboard();
    }

    async renderOverviewDashboard() {
        const container = document.getElementById('overview-dashboard');
        if (!container) return;

        if (!this.analysisData) {
            container.innerHTML = '';
            return;
        }

        const analysis = this.analysisData.analysis || {};
        const risk = analysis.expected_risk_score ?? this.analysisData.expected_risk_score ?? 0;
        const def  = analysis.expected_defensibility ?? this.analysisData.expected_defensibility ?? 0;
        const archName = this.analysisData.architecture_name || this.analysisData.architecture || '';
        const attackPaths = analysis.expected_attack_paths || [];
        const controlRecs = analysis.control_recommendations || [];
        const controlsPresent = analysis.controls_present || [];
        const residualRisks = analysis.residual_risks || {};
        const perThreat = residualRisks.per_threat || {};
        const residualBefore = analysis.residual_risks_before || {};
        const residualAfter  = analysis.residual_risks_after  || {};
        const beforeScore = residualBefore.overall_residual ?? risk;
        const afterScore  = residualAfter.overall_residual  ?? (risk * 0.1);
        const riskReductionPct = beforeScore > 0 ? Math.round((beforeScore - afterScore) / beforeScore * 100) : 0;

        // ROI calculation matching threat_report.py logic
        const BREACH_COST = 420;
        const implCost = risk >= 70 ? 50 : risk >= 40 ? 30 : 15;
        const roi = implCost > 0 ? (BREACH_COST / implCost).toFixed(1) : 0;

        // Risk colour
        const riskColor = risk >= 70 ? 'var(--danger-color)' : risk >= 40 ? 'var(--warning-color)' : 'var(--secondary-color)';
        const defColor  = def  >= 60 ? 'var(--secondary-color)' : def >= 30 ? 'var(--warning-color)' : 'var(--danger-color)';

        // Confidence (try MoE, fall back to foundation)
        const foundationConf = (this.analysisData.confidence ?? 0.995) * 100;
        let validatedConf = null;
        let moeInterp = '';
        let moeImprovTiers = {};
        let moeKnownFindings = [];
        let moeSynthComment = '';
        // Expert validation signals collected from MoE and Red Team critique files
        // expertEndorsedControls: control names where ≥1 expert explicitly recommended them
        // expertWeakenedControls: control names flagged as insufficient or UNSURE-only
        let expertEndorsedControls = new Set();
        let expertWeakenedControls = new Set();
        // Full text corpus from MoE recs — used for substring matching against control names
        let moeKnownText = '';
        let moeUnsureText = '';
        try {
            const moeResp = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (moeResp.ok) {
                const moe = await moeResp.json();
                validatedConf = (moe.confidence?.final ?? null);
                moeInterp = moe.confidence?.interpretation ?? '';
                moeImprovTiers = moe.improvement_options || {};
                moeSynthComment = (moe.consensus_recommendations || {}).confidence_commentary || '';
                const cr = moe.consensus_recommendations || {};
                const allFinds = [...(cr.critical || []), ...(cr.high || [])];
                moeKnownFindings = allFinds.filter(r =>
                    r.confidence_label === 'KNOWN' || (r.source && r.source.includes('+'))
                ).slice(0, 3);
                // Build text corpus from KNOWN vs UNSURE recs for substring matching
                for (const rec of allFinds) {
                    if (rec.confidence_label === 'KNOWN' || (rec.source && rec.source.includes('+'))) {
                        moeKnownText += ' ' + (rec.description || rec.recommendation || '');
                    }
                }
                for (const rec of (cr.review || [])) {
                    moeUnsureText += ' ' + (rec.description || rec.recommendation || '');
                }
                // Also collect names from improvement tier items (control names appear here)
                for (const tierData of Object.values(moe.improvement_options || {})) {
                    for (const item of (tierData.items || [])) {
                        expertEndorsedControls.add(item.toUpperCase().trim());
                    }
                }
            }
        } catch (_) {}

        // Also pull Red Team roadmap requirements (most reliable control name source)
        try {
            const rtResp = await fetch(`/api/v1/reports/${archName}/files/06_red_team_critique.json`);
            if (rtResp.ok) {
                const rt = await rtResp.json();
                const roadmap = (rt.breakdown || {}).exploit_mitigation_roadmap || [];
                for (const tier of roadmap) {
                    for (const req of (tier.requirements || [])) {
                        expertEndorsedControls.add(req.toUpperCase().trim());
                    }
                }
            }
        } catch (_) {}

        // Top 5 controls ranked by composite score:
        //   base = path_count × risk_score
        //   ×1.4 boost if expert-endorsed (exact name in RT roadmap / tier items, or mentioned in KNOWN text)
        //   ×0.8 penalty if mentioned only in UNSURE text (and not in endorsed set)
        const priorityWeight = { critical: 100, high: 75, medium: 50, low: 25 };
        const top3 = [...controlRecs]
            .filter(c => c.attack_paths && c.attack_paths.length > 0)
            .map(c => {
                const paths = c.attack_paths?.length || 0;
                const riskScore = c.score ?? (priorityWeight[c.priority?.toLowerCase()] ?? 25);
                const baseName = (c.control || '').toUpperCase().trim();
                // Check exact set membership (Red Team roadmap requirements + tier items)
                const exactEndorsed = expertEndorsedControls.has(baseName);
                // Check if control name appears in KNOWN expert text (partial match)
                const textEndorsed = moeKnownText.toUpperCase().includes(baseName);
                const textUnsure   = !exactEndorsed && !textEndorsed && moeUnsureText.toUpperCase().includes(baseName);
                const expertBoost = (exactEndorsed || textEndorsed) ? 1.4 : textUnsure ? 0.8 : 1.0;
                const expertSource = exactEndorsed ? 'roadmap' : textEndorsed ? 'known-text' : textUnsure ? 'unsure-text' : null;
                return { ...c, _impact: paths * riskScore * expertBoost, _expertBoost: expertBoost, _expertSource: expertSource };
            })
            .sort((a, b) => b._impact - a._impact)
            .slice(0, 5);

        // Per-threat exposure rows
        const threatLabels = {
            ransomware: 'Ransomware', application_vulns: 'App Vulnerabilities',
            phishing: 'Phishing', insider_threat: 'Insider Threat',
            dos: 'DoS / Availability', supply_chain: 'Supply Chain'
        };
        const threatIcons = {
            ransomware: '🔒', application_vulns: '🐛', phishing: '🎣',
            insider_threat: '👤', dos: '💥', supply_chain: '📦'
        };

        // before = existing controls only, after = with all recommendations applied
        const beforePerThreat = residualBefore.per_threat || {};
        const afterPerThreat  = residualAfter.per_threat  || {};
        const sourceKeys = Object.keys(beforePerThreat).length ? Object.keys(beforePerThreat)
                         : Object.keys(afterPerThreat).length  ? Object.keys(afterPerThreat)
                         : Object.keys(perThreat);

        const maxInitial = Math.max(...sourceKeys.map(k =>
            (beforePerThreat[k] || afterPerThreat[k] || perThreat[k] || {}).initial_risk || 0
        ), 1);

        const residualRows = sourceKeys
            .sort((a, b) => {
                const ia = (beforePerThreat[a] || afterPerThreat[a] || perThreat[a] || {}).initial_risk || 0;
                const ib = (beforePerThreat[b] || afterPerThreat[b] || perThreat[b] || {}).initial_risk || 0;
                return ib - ia;
            })
            .map(key => {
                const tb = beforePerThreat[key] || {};
                const ta = afterPerThreat[key]  || perThreat[key] || {};
                const initial  = tb.initial_risk  ?? ta.initial_risk  ?? 0;
                const current  = tb.residual_risk ?? initial;   // after existing controls
                const target   = ta.residual_risk ?? current;   // after all recommendations
                const existingControls = (tb.controls || []).map(c => c.name);
                const allControls      = (ta.controls || []).map(c => c.name);
                const newControls      = allControls.filter(n => !existingControls.includes(n));

                // Bar widths as % of maxInitial (so bars are comparable across threats)
                const barWidth   = (initial / maxInitial) * 100;   // total bar extent
                const pExisting  = (Math.max(initial - current, 0) / maxInitial) * 100;  // covered by existing
                const pRecs      = (Math.max(current - target,  0) / maxInitial) * 100;  // closed by recs
                const pResidual  = (target / maxInitial) * 100;                          // always-remaining

                // Tier marker positions on the bar (approximate: quick=1st rec, rec=half recs, max=all recs)
                // Position = pExisting + fraction of pRecs
                const nRecs = newControls.length;
                const quickPos   = nRecs > 0 ? pExisting + pRecs * (1 / Math.max(nRecs, 1))         : null;
                const recPos     = nRecs > 1 ? pExisting + pRecs * (Math.ceil(nRecs/2) / nRecs)     : null;
                const maxPos     = nRecs > 0 ? pExisting + pRecs                                     : null;

                // Status of current (before recs) drives urgency label
                const urgency = tb.status === 'MITIGATE' ? { label: 'Action needed', color: 'var(--danger-color)' }
                              : tb.status === 'MONITOR'  ? { label: 'Monitor',       color: 'var(--warning-color)' }
                              :                            { label: 'Managed',        color: 'var(--secondary-color)' };

                return `
            <div style="margin-bottom:1rem;">
                <!-- Threat label + control counts + urgency -->
                <div style="display:flex; align-items:center; gap:0.625rem; margin-bottom:0.375rem;">
                    <span style="font-size:0.875rem;">${threatIcons[key] || '⚠️'}</span>
                    <span style="font-size:0.8125rem; font-weight:600; color:var(--text-color); flex:1;">${threatLabels[key] || key}</span>
                    <span style="font-size:0.72rem; color:var(--text-secondary);">
                        ${existingControls.length} control${existingControls.length !== 1 ? 's' : ''} active
                        ${newControls.length > 0 ? `· <span style="color:var(--warning-color); font-weight:600;">+${newControls.length} recommended</span>` : ''}
                    </span>
                    <span style="padding:0.1rem 0.4rem; border-radius:4px; font-size:0.7rem; font-weight:700;
                          background:${urgency.color}22; color:${urgency.color};">${urgency.label}</span>
                </div>

                <!-- Stacked bar with tier markers -->
                <div style="position:relative; margin-left:0; margin-bottom:0.375rem;">
                    <div style="display:flex; height:12px; border-radius:6px; overflow:hidden; background:var(--nav-hover-bg); width:100%;">
                        <!-- Existing controls segment (muted green) -->
                        <div style="width:${pExisting}%; background:var(--secondary-color); opacity:0.4; flex-shrink:0;" title="Covered by ${existingControls.length} existing control${existingControls.length !== 1 ? 's' : ''}"></div>
                        <!-- Recommendations segment (bright green) -->
                        <div style="width:${pRecs}%; background:var(--secondary-color); opacity:0.85; flex-shrink:0;" title="${newControls.length} recommended control${newControls.length !== 1 ? 's' : ''} close this gap"></div>
                        <!-- Residual segment (always amber — never truly zero) -->
                        <div style="width:${Math.max(pResidual, pResidual > 0 ? 0 : 0.8)}%; background:var(--warning-color); opacity:0.7; flex-shrink:0;" title="Residual exposure (implementation gaps, misconfig, human error)"></div>
                    </div>
                    <!-- Tier tick marks -->
                    ${quickPos !== null ? `<div style="position:absolute; top:-3px; left:${quickPos}%; transform:translateX(-50%); width:2px; height:18px; background:var(--text-color); opacity:0.5;" title="⚡ Quick Win"></div>` : ''}
                    ${recPos   !== null ? `<div style="position:absolute; top:-3px; left:${recPos}%;   transform:translateX(-50%); width:2px; height:18px; background:var(--primary-color); opacity:0.8;" title="⭐ Recommended"></div>` : ''}
                    ${maxPos   !== null ? `<div style="position:absolute; top:-3px; left:${maxPos}%;   transform:translateX(-50%); width:2px; height:18px; background:var(--secondary-color);" title="🔒 Maximum"></div>` : ''}
                </div>

                <!-- Below-bar text -->
                <div style="display:flex; justify-content:space-between; font-size:0.7rem; color:var(--text-tertiary);">
                    <span>Exposure: <strong style="color:var(--text-color);">${initial}</strong>
                      → after controls: <strong style="color:var(--secondary-color);">${current}</strong>
                      ${newControls.length > 0 ? `→ with recs: <strong style="color:var(--secondary-color);">${target}</strong>` : ''}
                    </span>
                    <span style="color:var(--warning-color); font-style:italic;">~${Math.max(target, Math.round(initial * 0.05))} residual</span>
                </div>
            </div>`;
            }).join('');

        // Detect implausibly optimistic per-threat "after" values
        // Flags categories where after=0 but initial_risk was high (≥40) — suggests model assumed
        // full deployment of all recommended controls with no implementation failure.
        const implausibleThreats = sourceKeys.filter(key => {
            const ta = afterPerThreat[key] || {};
            const tb = beforePerThreat[key] || {};
            const initial = tb.initial_risk ?? ta.initial_risk ?? 0;
            const afterResidual = ta.residual_risk ?? null;
            return afterResidual !== null && afterResidual === 0 && initial >= 40;
        });
        const residualQualityWarning = implausibleThreats.length > 0
            ? '<div style="margin-top:0.5rem; padding:0.625rem 0.875rem; background:var(--warning-color)0d; border:1px solid var(--warning-color)44; border-radius:6px; font-size:0.75rem; color:var(--text-secondary); line-height:1.6;">'
              + '🔁 <strong style="color:var(--warning-color);">Re-run recommended:</strong> '
              + implausibleThreats.map(k => k.replace(/_/g, ' ')).join(', ')
              + ' show residual = 0, which indicates this report was generated before the 10% residual floor was applied. '
              + 'Re-running the analysis will produce corrected figures. '
              + 'Current risk reduction of <strong>' + riskReductionPct + '%</strong> is overstated.'
              + '</div>'
            : '';

        // Honest residual note
        const residualNote = `
            <div style="margin-top:0.75rem; padding:0.625rem 0.875rem; background:var(--warning-color)11; border:1px solid var(--warning-color)44; border-radius:6px; font-size:0.75rem; color:var(--text-secondary); line-height:1.6;">
                ⚠️ <strong style="color:var(--text-color);">Controls reduce risk — they do not eliminate it.</strong>
                Residual exposure persists due to implementation gaps, misconfigurations, human error, and technical bypasses.
                The goal is risk-informed management, not false certainty. Review quarterly.
            </div>` + residualQualityWarning;

        // Improvement tier cards — use real MoE data if available, fall back to generic estimates
        const hasMoe = validatedConf !== null;
        // Map MoE tier keys to display config
        const tierMoeKey = { 'Quick Wins': 'quick_wins', 'Recommended': 'recommended', 'Maximum': 'maximum' };
        const tiers = [
            { icon: '⚡', label: 'Quick Wins',     timeline: '1–2 weeks',   cost: 'Expert estimate pending',  file: '08a_quick_wins.mmd' },
            { icon: '⭐', label: 'Recommended',    timeline: '1–3 months',  cost: 'Expert estimate pending',  file: '08b_recommended_target.mmd', recommended: true },
            { icon: '🔒', label: 'Maximum',        timeline: '6–12 months', cost: 'Expert estimate pending',  file: '08c_maximum_security.mmd' },
        ];
        const tierCards = tiers.map(t => {
            const moeKey = tierMoeKey[t.label];
            const mT = (hasMoe && moeKey) ? (moeImprovTiers[moeKey] || {}) : {};
            const costText = mT.cost || t.cost;
            const effortText = mT.effort ? 'Effort: ' + mT.effort : t.timeline;
            // Strip parenthetical explanations from LLM-generated risk text (e.g. "50 → 45 (based on...)")
            const riskTextRaw = mT.risk_reduction || '';
            const riskText = riskTextRaw.replace(/\s*\(.*\)/, '').trim();
            const border = t.recommended ? '2px solid var(--secondary-color)' : '1px solid var(--border-color)';
            const moeItems = (mT.items && Array.isArray(mT.items)) ? mT.items : [];
            return `
            <div style="flex:1; min-width:160px; background:var(--card-bg); border:${border}; border-radius:10px; padding:1rem; position:relative;">
                ${t.recommended ? `<div style="position:absolute; top:-10px; left:50%; transform:translateX(-50%); background:var(--secondary-color); color:#000; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:10px;">RECOMMENDED</div>` : ''}
                <div style="font-size:1.5rem; margin-bottom:0.5rem;">${t.icon}</div>
                <div style="font-weight:700; color:var(--text-color); margin-bottom:0.25rem;">${t.label}</div>
                <div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:0.15rem;">${effortText}</div>
                <div style="font-size:0.8125rem; color:${hasMoe ? 'var(--text-color)' : 'var(--text-tertiary)'}; font-weight:${hasMoe ? '600' : '400'}; margin-bottom:${riskText ? '0.15rem' : '0.75rem'};">${costText}</div>
                ${riskText ? `<div style="font-size:0.75rem; color:var(--secondary-color); margin-bottom:0.25rem;">Attacker score: ${riskText} ↓</div><div style="font-size:0.65rem; color:var(--text-tertiary); margin-bottom:0.75rem;">lower = harder for attacker</div>` : ''}
                ${hasMoe
                    ? `<button class="btn-secondary tier-diagram-btn" data-file="${t.file}" style="width:100%; padding:0.375rem; font-size:0.8125rem; cursor:pointer;">View Diagram →</button>`
                    : `<div style="font-size:0.75rem; color:var(--text-tertiary); font-style:italic;">Run Expert Review to unlock roadmap</div>`
                }
                ${this._renderSspTierUpgradeDelta(moeItems, t.label)}
            </div>`;
        }).join('');

        // Build Expert Review synthesis summary for Overview (items 2 & 5)
        let moeOverviewSummary = '';
        if (hasMoe) {
            let knownList = '';
            for (const f of moeKnownFindings) {
                knownList += '<li style="margin-bottom:0.25rem;">' + (f.description || f.recommendation || '') + '</li>';
            }
            const knownBlock = knownList
                ? '<ul style="margin:0.5rem 0 0; padding-left:1.25rem; font-size:0.8125rem; color:var(--text-color);">' + knownList + '</ul>'
                : '';
            const commentBlock = moeSynthComment
                ? '<div style="font-size:0.8125rem; color:var(--text-secondary); font-style:italic; margin-top:0.5rem;">' + moeSynthComment + '</div>'
                : '';
            moeOverviewSummary = '<div style="background:var(--primary-color)0e; border:1px solid var(--primary-color)44; border-radius:8px; padding:0.75rem 1rem; margin-bottom:1.25rem;">'
                + '<div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem;">'
                + '<span style="font-size:0.9375rem;">🧑‍🏫</span>'
                + '<span style="font-size:0.8125rem; font-weight:700; color:var(--primary-color);">Expert Review validated — ' + validatedConf.toFixed(1) + '% confidence</span>'
                + '</div>'
                + (moeKnownFindings.length > 0
                    ? '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:0.25rem;">Key KNOWN findings (' + moeKnownFindings.length + ' confirmed by multiple experts):</div>' + knownBlock
                    : '<div style="font-size:0.8125rem; color:var(--secondary-color);">No critical multi-expert findings — strong posture.</div>')
                + commentBlock
                + '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.5rem;">Full details → <strong style="cursor:pointer; color:var(--primary-color);" onclick="window.dashboard?.switchTab(\'expert-review\')">Expert Review tab</strong></div>'
                + '</div>';
        }

        container.innerHTML = `
        ${moeOverviewSummary}
        <!-- Confidence + Scores Row -->
        ${(() => {
            const confDelta = validatedConf !== null ? (validatedConf - foundationConf).toFixed(1) : null;
            const confDeltaLabel = confDelta !== null
                ? (parseFloat(confDelta) >= 0
                    ? `<div style="font-size:0.75rem; color:var(--secondary-color); font-weight:600;">Expert validated: ${validatedConf.toFixed(1)}% (+${confDelta}%)</div>`
                    : `<div style="font-size:0.75rem; color:var(--warning-color); font-weight:600;">Expert validated: ${validatedConf.toFixed(1)}% (${confDelta}%)</div>`)
                : `<div style="font-size:0.75rem; color:var(--text-tertiary);">how complete this analysis is · run Expert Review to validate</div>`;
            return `<div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.25rem;">
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Current Risk ↓</div>
                <div style="font-size:2rem; font-weight:700; color:${riskColor};">${risk}<span style="font-size:1rem; color:var(--text-secondary);">/100</span></div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">baseline · lower = safer</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Recommended Tier ↓</div>
                <div style="font-size:2rem; font-weight:700; color:var(--secondary-color);">${riskReductionPct}<span style="font-size:1rem;">%</span><span style="font-size:0.8rem; color:var(--text-secondary);"> risk reduction</span></div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">\$${implCost}K est. · ${roi}x ROI</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Defensibility ↑</div>
                <div style="font-size:2rem; font-weight:700; color:${defColor};">${def}<span style="font-size:1rem; color:var(--text-secondary);">/100</span></div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">${controlsPresent.length} controls · higher = better</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Threat Paths</div>
                <div style="font-size:2rem; font-weight:700; color:var(--text-color);">${attackPaths.length}</div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">active attack routes</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Analysis Confidence</div>
                <div style="font-size:2rem; font-weight:700; color:var(--secondary-color);">${foundationConf.toFixed(1)}<span style="font-size:1rem;">%</span></div>
                ${confDeltaLabel}
            </div>
        </div>`;
        })()}

        <!-- Two-column: Residual Risk + Top Actions -->
        <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.25rem;">
            <!-- Threat Exposure Breakdown -->
            <div style="flex:2; min-width:300px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1.25rem;">
                <div style="display:flex; align-items:baseline; justify-content:space-between; margin-bottom:0.375rem; flex-wrap:wrap; gap:0.5rem;">
                    <h3 style="margin:0; font-size:0.9375rem; color:var(--text-color);">Threat Exposure by Category</h3>
                    <span style="font-size:0.7rem; color:var(--text-tertiary);">bar width = relative initial exposure</span>
                </div>
                <!-- Legend -->
                <div style="display:flex; gap:0.75rem; font-size:0.7rem; color:var(--text-secondary); margin-bottom:1rem; flex-wrap:wrap; align-items:center;">
                    <span style="display:flex; align-items:center; gap:0.25rem;"><span style="display:inline-block; width:14px; height:7px; background:var(--secondary-color); opacity:0.4; border-radius:2px;"></span>Existing controls</span>
                    <span style="display:flex; align-items:center; gap:0.25rem;"><span style="display:inline-block; width:14px; height:7px; background:var(--secondary-color); opacity:0.85; border-radius:2px;"></span>Recommended controls</span>
                    <span style="display:flex; align-items:center; gap:0.25rem;"><span style="display:inline-block; width:14px; height:7px; background:var(--warning-color); opacity:0.7; border-radius:2px;"></span>Residual (always present)</span>
                    <span style="display:flex; align-items:center; gap:0.25rem; margin-left:auto;">
                        <span style="display:inline-block; width:2px; height:12px; background:var(--text-secondary); opacity:0.5;"></span>⚡
                        <span style="display:inline-block; width:2px; height:12px; background:var(--primary-color); opacity:0.8;"></span>⭐
                        <span style="display:inline-block; width:2px; height:12px; background:var(--secondary-color);"></span>🔒
                        <span style="color:var(--text-tertiary);">investment tiers</span>
                    </span>
                </div>
                ${residualRows || '<div style="color:var(--text-tertiary); font-size:0.875rem; padding:0.5rem 0;">Run analysis to see threat breakdown</div>'}
                ${residualNote}
                <!-- Bridge to action plan -->
                <div style="margin-top:0.875rem; padding:0.625rem 0.875rem; background:var(--primary-color)11; border-left:3px solid var(--primary-color); border-radius:0 6px 6px 0; font-size:0.8rem; color:var(--text-secondary);">
                    The <strong style="color:var(--text-color);">Top Actions</strong> on the right are the highest-leverage controls to close these gaps.
                    See <strong style="color:var(--primary-color); cursor:pointer;" onclick="window.dashboard?.switchTab('controls')">Mitigations tab</strong> for the full prioritised list.
                </div>
            </div>
            <!-- Top Actions by Risk Impact -->
            <div style="flex:1; min-width:240px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1.25rem;">
                <h3 style="margin:0 0 0.2rem; font-size:0.9375rem; color:var(--text-color);">⚡ Highest Impact Controls</h3>
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:1rem;">Ranked by paths covered × risk score${validatedConf !== null ? ' · expert-validated boost applied' : ''}</div>
                ${top3.length > 0 ? top3.map((c, i) => {
                    const priColor = c.priority === 'critical' ? 'var(--danger-color)' : c.priority === 'high' ? 'var(--warning-color)' : 'var(--primary-color)';
                    const riskScore = c.score ?? null;
                    const paths = c.attack_paths?.length || 0;
                    const expertTag = c._expertBoost > 1
                        ? `<span style="font-size:0.65rem; font-weight:700; color:var(--secondary-color); background:var(--secondary-color)18; border:1px solid var(--secondary-color)44; border-radius:3px; padding:1px 4px;">✓ Expert validated</span>`
                        : c._expertBoost < 1
                        ? `<span style="font-size:0.65rem; font-weight:700; color:var(--warning-color); background:var(--warning-color)18; border:1px solid var(--warning-color)44; border-radius:3px; padding:1px 4px;">⚠ Expert uncertain</span>`
                        : '';
                    const sspCtx = c.ssp_context;
                    let sspMiniPill = '';
                    if (sspCtx && sspCtx.primary) {
                        const lbp = sspCtx.primary.levels_by_profile || {};
                        const sl = lbp[this.sspProfile] ?? sspCtx.primary.level;
                        const sc = sl === 0 ? 'var(--danger-color)' : sl === 1 ? 'var(--warning-color)' : 'var(--text-tertiary)';
                        sspMiniPill = `<span style="padding:1px 4px; background:${sc}15; border:1px solid ${sc}44; border-radius:3px; font-size:0.62rem; font-weight:700; color:${sc};" title="${sspCtx.primary.title}">🏛 L${sl}</span>`;
                    }
                    return `
                <div style="padding:0.625rem 0; border-bottom:1px solid var(--border-color);">
                    <div style="display:flex; align-items:flex-start; gap:0.5rem;">
                        <div style="width:20px; height:20px; border-radius:50%; background:${priColor}; color:#fff; font-size:0.7rem; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0; margin-top:1px;">${i+1}</div>
                        <div style="flex:1;">
                            <div style="font-weight:600; color:var(--text-color); font-size:0.8125rem; text-transform:uppercase;">${c.control}</div>
                            <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap; margin-top:0.2rem;">
                                <span style="font-size:0.7rem; color:var(--text-secondary);">${paths} path${paths !== 1 ? 's' : ''}</span>
                                ${riskScore !== null ? `<span style="font-size:0.7rem; color:var(--text-tertiary);">·</span><span style="font-size:0.7rem; color:${priColor}; font-weight:600;">risk ${riskScore}/100</span>` : ''}
                                ${expertTag}
                                ${sspMiniPill}
                                <span style="margin-left:auto; padding:0.1rem 0.3rem; background:${priColor}22; color:${priColor}; border-radius:3px; font-size:0.65rem; font-weight:700;">${c.priority}</span>
                            </div>
                        </div>
                    </div>
                </div>`}).join('') : '<div style="color:var(--text-tertiary); font-size:0.875rem;">No critical actions identified</div>'}
                ${top3.length > 0 ? `
                <div style="margin-top:0.75rem; font-size:0.75rem; color:var(--text-tertiary); font-style:italic;">
                    Full prioritised list →
                    <strong style="color:var(--primary-color); cursor:pointer;" onclick="window.dashboard?.switchTab('controls')">Mitigations tab</strong>
                </div>` : ''}
            </div>
        </div>

        <!-- Improvement Tiers -->
        <div style="background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1.25rem; margin-bottom:0.5rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.375rem; flex-wrap:wrap; gap:0.5rem;">
                <h3 style="margin:0; font-size:0.9375rem; color:var(--text-color);">Investment Tiers — What Each Level Achieves</h3>
                ${!hasMoe ? `<span style="font-size:0.8125rem; color:var(--text-tertiary);">Run Expert Review to unlock diagrams</span>` : `<span style="font-size:0.8125rem; color:var(--secondary-color);">✅ Validated ${validatedConf ? validatedConf.toFixed(1) + '%' : ''}</span>`}
            </div>
            <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:1rem;">The tier markers on the bars above show where each investment level lands per threat category.</div>
            <div style="display:flex; gap:1rem; flex-wrap:wrap;">${tierCards}</div>
        </div>
        `;

        // Wire tier diagram buttons → Visualise tab
        container.querySelectorAll('.tier-diagram-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const file = btn.dataset.file;
                this.switchTab('hardening');
                // Signal the hardening tab to open this scenario diagram
                this._pendingScenarioDiagram = file;
            });
        });
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
        const perNodeTechniques = path.per_node_techniques || {};
        const allTechniques = path.techniques || [];

        // Fetch technique names + per-technique mitigations in parallel
        const [techniqueNames, tmData] = await Promise.all([
            this.fetchTechniqueNames(allTechniques),
            allTechniques.length > 0
                ? fetch(`/api/v1/technique-mitigations?technique_ids=${allTechniques.join(',')}`)
                    .then(r => r.ok ? r.json() : { mappings: {} })
                    .catch(() => ({ mappings: {} }))
                : Promise.resolve({ mappings: {} })
        ]);
        const techMitMappings = tmData.mappings || {};

        // Collect all unique mitigation IDs to resolve names
        const allMitIds = [...new Set(Object.values(techMitMappings).flat())];
        const mitigationNames = await this.fetchMitigationNames(allMitIds);

        // Build step-by-step HTML with clickable steps
        const stepsHtml = path.path.map((node, idx) => {
            const stepTechniques = perNodeTechniques[node] || [];
            const stepId = `step-${path.id}-${idx}`;
            const bgColor = idx === 0 ? 'var(--danger-color)15' : idx === path.path.length - 1 ? 'var(--warning-color)15' : 'var(--nav-hover-bg)';
            const borderColor = idx === 0 ? 'var(--danger-color)' : idx === path.path.length - 1 ? 'var(--warning-color)' : 'var(--primary-color)';

            return `
                <div class="attack-step" data-step="${idx}" style="margin-bottom: 0.75rem;">
                    <div class="step-header" style="display: flex; align-items: center; cursor: pointer; padding: 0.75rem; background: ${bgColor}; border-radius: 8px; border-left: 4px solid ${borderColor}; transition: all 0.2s;">
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
                            ${stepTechniques.map(tech => {
                                const techName = techniqueNames[tech] || tech;
                                const mits = techMitMappings[tech] || [];
                                return `
                                <div style="margin-bottom: 0.875rem; padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; border-left: 3px solid var(--primary-color);">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem; margin-bottom: ${mits.length > 0 ? '0.625rem' : '0'};">
                                        <div>
                                            <code style="font-weight: 700; color: var(--primary-color); font-size: 0.875rem;">${tech}</code>
                                            <span style="margin-left: 0.5rem; color: var(--text-color); font-size: 0.875rem; font-weight: 600;">${techName !== tech ? `· ${techName}` : ''}</span>
                                        </div>
                                        <a href="https://attack.mitre.org/techniques/${tech}/" target="_blank" class="btn-icon" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; text-decoration: none; flex-shrink: 0;">🔗</a>
                                    </div>
                                    ${mits.length > 0 ? `
                                        <div style="padding-top: 0.5rem; border-top: 1px solid var(--border-color);">
                                            <div style="font-size: 0.6875rem; color: var(--text-tertiary); font-weight: 600; margin-bottom: 0.375rem; text-transform: uppercase; letter-spacing: 0.05em;">Mitigations</div>
                                            <div style="display: flex; flex-wrap: wrap; gap: 0.25rem;">
                                                ${mits.map(m => `
                                                    <a href="https://attack.mitre.org/mitigations/${m}/" target="_blank" style="display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.25rem 0.5rem; background: var(--secondary-color)12; border: 1px solid var(--secondary-color)44; border-radius: 4px; text-decoration: none; font-size: 0.75rem;" title="${mitigationNames[m] || m}">
                                                        <code style="color: var(--secondary-color); font-weight: 700;">${m}</code>
                                                        <span style="color: var(--text-secondary); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${mitigationNames[m] ? `· ${mitigationNames[m]}` : ''}</span>
                                                    </a>
                                                `).join('')}
                                            </div>
                                        </div>
                                    ` : ''}
                                </div>
                            `}).join('')}
                        ` : `
                            <p style="color: var(--text-tertiary); font-style: italic; font-size: 0.875rem;">No techniques mapped to this step</p>
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

    async loadControlsTab() {
        const tableContainer = document.getElementById('controls-table');

        if (!this.analysisData) {
            tableContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        // Extract control recommendations from nested analysis object
        const analysis = this.analysisData.analysis || {};
        const rawControls = analysis.control_recommendations || [];

        // Build expert endorsement sets (same logic as loadOverviewTab) for sort ordering
        let endorsedControls = new Set();
        let knownText = '';
        let unsureText = '';
        const archName = this.analysisData?.architecture_name || this.currentArchName;
        try {
            const moeResp = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (moeResp.ok) {
                const moe = await moeResp.json();
                const cr = moe.consensus_recommendations || {};
                const allFinds = [...(cr.critical || []), ...(cr.high || [])];
                for (const rec of allFinds) {
                    if (rec.confidence_label === 'KNOWN' || (rec.source && rec.source.includes('+'))) {
                        knownText += ' ' + (rec.description || rec.recommendation || '');
                    }
                }
                for (const rec of (cr.review || [])) {
                    unsureText += ' ' + (rec.description || rec.recommendation || '');
                }
                for (const tierData of Object.values(moe.improvement_options || {})) {
                    for (const item of (tierData.items || [])) {
                        endorsedControls.add(item.toUpperCase().trim());
                    }
                }
            }
        } catch (_) {}
        try {
            const rtResp = await fetch(`/api/v1/reports/${archName}/files/06_red_team_critique.json`);
            if (rtResp.ok) {
                const rt = await rtResp.json();
                const roadmap = (rt.breakdown || {}).exploit_mitigation_roadmap || [];
                for (const tier of roadmap) {
                    for (const req of (tier.requirements || [])) {
                        endorsedControls.add(req.toUpperCase().trim());
                    }
                }
            }
        } catch (_) {}

        // Sort by same _impact formula used in Overview top controls
        const priorityWeight = { critical: 100, high: 75, medium: 50, low: 25 };
        const controlRecs = [...rawControls].map(c => {
            const paths = (c.attack_paths || []).length;
            const riskScore = c.score ?? (priorityWeight[c.priority?.toLowerCase()] ?? 25);
            const baseName = (c.control || '').toUpperCase().trim();
            const exactEndorsed = endorsedControls.has(baseName);
            const textEndorsed = knownText.toUpperCase().includes(baseName);
            const textUnsure = !exactEndorsed && !textEndorsed && unsureText.toUpperCase().includes(baseName);
            const expertBoost = (exactEndorsed || textEndorsed) ? 1.4 : textUnsure ? 0.8 : 1.0;
            return { ...c, _impact: paths * riskScore * expertBoost, _expertBoost: expertBoost };
        }).sort((a, b) => {
            // Primary: priority tier (critical > high > medium > low)
            const pw = { critical: 3, high: 2, medium: 1, low: 0 };
            const pDiff = (pw[b.priority] ?? 0) - (pw[a.priority] ?? 0);
            if (pDiff !== 0) return pDiff;
            // Secondary: _impact score
            return b._impact - a._impact;
        });

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
            <div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 8px;">
                <div style="margin-bottom: 0.4rem; font-size: 0.875rem; font-weight: 700;">📖 Legend</div>
                <div style="font-size: 0.8125rem; line-height: 1.6;">
                    <div><strong style="color: var(--danger-color);">CRITICAL</strong> - High-risk threats requiring immediate action</div>
                    <div><strong style="color: var(--warning-color);">HIGH</strong> - Important improvements, prioritise soon</div>
                    <div><strong style="color: var(--primary-color);">MEDIUM</strong> - Recommended enhancements, plan for deployment</div>
                    <div style="margin-top:0.5rem; display:flex; gap:0.75rem; flex-wrap:wrap; align-items:center;">
                        <span style="padding:1px 6px; background:var(--primary-color)18; border:1px solid var(--primary-color)55; border-radius:4px; font-size:0.7rem; font-weight:700; color:var(--primary-color);">RAPIDS</span>
                        <span style="font-size:0.75rem; color:var(--text-tertiary);">MITRE Enterprise ATT&CK — 6 threat categories (ransomware, app vulns, phishing, insider, DoS, supply chain)</span>
                    </div>
                    <div style="display:flex; gap:0.75rem; flex-wrap:wrap; align-items:center; margin-top:0.2rem;">
                        <span style="padding:1px 6px; background:#7c3aed18; border:1px solid #7c3aed55; border-radius:4px; font-size:0.7rem; font-weight:700; color:#a78bfa;">ARC+ATLAS</span>
                        <span style="font-size:0.75rem; color:var(--text-tertiary);">MITRE ATLAS AI/ML techniques — ARC Framework (9 categories, 46 risks, 88 controls). Only shown for AI/agentic architectures.</span>
                    </div>
                    <div style="margin-top:0.4rem; padding:0.5rem 0.75rem; background:#0891b20a; border:1px solid #0891b233; border-radius:6px;">
                        <div style="font-size:0.7rem; font-weight:700; color:#06b6d4; margin-bottom:0.35rem;">🏛 Singapore Government SSP Baseline Levels</div>
                        <div style="display:flex; flex-direction:column; gap:0.2rem;">
                            <div style="display:flex; align-items:baseline; gap:0.5rem;">
                                <span style="padding:1px 5px; background:var(--danger-color)18; border:1px solid var(--danger-color)44; border-radius:3px; font-size:0.68rem; font-weight:700; color:var(--danger-color); flex-shrink:0; min-width:2.4rem; text-align:center;">L0</span>
                                <span style="font-size:0.72rem; color:var(--text-secondary);"><strong>Cardinal — mandatory.</strong> Deviation requires <strong>HQ approval</strong>. Non-negotiable foundational governance.</span>
                            </div>
                            <div style="display:flex; align-items:baseline; gap:0.5rem;">
                                <span style="padding:1px 5px; background:var(--warning-color)18; border:1px solid var(--warning-color)44; border-radius:3px; font-size:0.68rem; font-weight:700; color:var(--warning-color); flex-shrink:0; min-width:2.4rem; text-align:center;">L1</span>
                                <span style="font-size:0.72rem; color:var(--text-secondary);"><strong>Basic Hygiene — baseline.</strong> Deviation requires <strong>Steering Committee (SC) risk acceptance</strong>.</span>
                            </div>
                            <div style="display:flex; align-items:baseline; gap:0.5rem;">
                                <span style="padding:1px 5px; background:var(--text-tertiary)18; border:1px solid var(--text-tertiary)44; border-radius:3px; font-size:0.68rem; font-weight:700; color:var(--text-tertiary); flex-shrink:0; min-width:2.4rem; text-align:center;">L2</span>
                                <span style="font-size:0.72rem; color:var(--text-secondary);"><strong>Best Practice — conditional.</strong> Recommended for enhanced posture; risk-owner acceptance sufficient.</span>
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 0.4rem; color: var(--text-tertiary);"><em>Score: threat severity × path coverage × technique depth. Click any control for full details.</em></div>
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
                // Detect control source: ATLAS technique IDs start with "AML.", ARC rationale has "AI/ML (ARC):"
                const isArc = (control.techniques || []).some(t => t.startsWith('AML.'))
                           || (control.rationale || '').includes('AI/ML (ARC)');
                const isRapids = !isArc || (control.rapids_threats || []).some(t => !t.startsWith('AI/ML'));
                // Extract ARC categories from rationale ("AI/ML (ARC): Safety, Privacy") and annotate with arc_id
                const arcCatMatch = (control.rationale || '').match(/AI\/ML \(ARC\):\s*([^|]+)/);
                const arcCats = arcCatMatch ? this._formatArcCats(arcCatMatch[1].trim()) : '';
                const sourceTag = isArc
                    ? `<span style="padding:1px 5px; background:#7c3aed18; border:1px solid #7c3aed55; border-radius:3px; font-size:0.65rem; font-weight:700; color:#a78bfa; flex-shrink:0;">ARC+ATLAS</span>`
                    : `<span style="padding:1px 5px; background:var(--primary-color)18; border:1px solid var(--primary-color)44; border-radius:3px; font-size:0.65rem; font-weight:700; color:var(--primary-color); flex-shrink:0;">RAPIDS</span>`;

                // SSP badge — combines policy label and level pill into a single pill
                const sspCtx = control.ssp_context;
                let sspBadge = '';
                if (sspCtx && sspCtx.primary) {
                    const lbp = sspCtx.primary.levels_by_profile || {};
                    const currentLevel = lbp[this.sspProfile] ?? sspCtx.primary.level;
                    const levelColor = currentLevel === 0 ? 'var(--danger-color)' : currentLevel === 1 ? 'var(--warning-color)' : 'var(--text-tertiary)';
                    const levelLabel = { 0: 'L0', 1: 'L1', 2: 'L2' }[currentLevel] ?? `L${currentLevel}`;
                    const govTip = {
                        0: 'L0 Cardinal — MANDATORY. Deviation requires HQ approval.',
                        1: 'L1 Basic Hygiene — BASELINE. Deviation requires SC risk acceptance.',
                        2: 'L2 Best Practice — CONDITIONAL. Risk-owner acceptance sufficient.',
                    }[currentLevel] ?? '';
                    const title = `${(sspCtx.primary.title || '')} · ${govTip}`;
                    sspBadge = `<span style="padding:1px 6px; background:#0891b218; border:1px solid #0891b244; border-radius:3px; font-size:0.65rem; font-weight:700; color:#06b6d4; flex-shrink:0; cursor:help;" title="${title}">`
                        + `${sspCtx.label} <span style="padding:0 3px; background:${levelColor}22; border-radius:2px; color:${levelColor};">${levelLabel}</span>`
                        + `</span>`;
                }

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
                            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; flex-wrap:wrap;">
                                <strong style="font-size: 1rem; color: var(--primary-color);">${control.control}</strong>
                                <span style="padding: 0.2rem 0.6rem; background: ${priorityColor}22; color: ${priorityColor}; border-radius: 10px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;">${control.priority}</span>
                                ${sourceTag}
                                ${sspBadge}
                            </div>
                            ${arcCats ? `<div style="font-size:0.75rem; color:#a78bfa; margin-bottom:0.35rem;">ARC categories: ${arcCats}</div>` : ''}
                            <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
                                ${control.rationale}
                            </div>
                            <div style="display: flex; gap: 1rem; font-size: 0.8125rem; color: var(--text-tertiary); margin-bottom: 0.5rem; flex-wrap:wrap;">
                                <span>📍 ${control.attack_paths ? control.attack_paths.length : 0} paths</span>
                                <span>🎯 ${control.techniques ? control.techniques.length : 0} ${isArc ? 'ATLAS' : 'Enterprise'} techniques</span>
                                <span>🛡️ ${control.mitigations ? control.mitigations.length : 0} mitigations</span>
                            </div>
                            ${control.control_type ? `
                                <div style="font-size: 0.8125rem; color: var(--text-tertiary); padding-top: 0.5rem; border-top: 1px solid var(--border-color);">
                                    <strong>Implementation:</strong> ${control.control_type}${control.layer ? ` | ${control.layer}` : ''}${control.placement ? ` | ${control.placement}` : ''}
                                </div>
                            ` : ''}
                        </div>
                        <div style="text-align: right; min-width: 72px;">
                            <div style="font-size: 1.1rem; font-weight: 700; color: ${priorityColor}; white-space:nowrap;">
                                ${control.score ? control.score.toFixed(1) : 'N/A'}<span style="font-size:0.7rem; font-weight:400; color:var(--text-tertiary);"> / 100</span>
                            </div>
                            <div style="margin: 3px 0; height: 4px; background: var(--border-color); border-radius: 2px; overflow:hidden;">
                                <div style="height:100%; width:${Math.min(100, (control.score || 0))}%; background:${priorityColor}; border-radius:2px;"></div>
                            </div>
                            <div style="font-size: 0.68rem; color: var(--text-tertiary); white-space:nowrap;">
                                ${(control.score || 0) >= 20 ? 'high impact' : (control.score || 0) >= 10 ? 'medium impact' : 'lower impact'}
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

    // Convert "Safety, Accountability" → arc_id-annotated badges
    _formatArcCats(catStr) {
        const ARC_IDS = {
            integrity: 'INT', safety: 'SAF', security: 'SEC', privacy: 'PRIV',
            transparency: 'TRANS', accountability: 'ACC', fairness: 'FAIR',
            resilience: 'RES', societal_impact: 'SOC'
        };
        const cats = catStr.split(',').map(s => s.trim()).filter(Boolean);
        const badges = cats.map(cat => {
            const key = cat.toLowerCase().replace(/\s+/g, '_');
            const id = ARC_IDS[key];
            return id
                ? `<span style="display:inline-flex; align-items:center; gap:0.2rem; padding:1px 5px; background:#7c3aed18; border:1px solid #7c3aed44; border-radius:4px; font-size:0.68rem; font-weight:700; color:#a78bfa;"><span style="opacity:0.7;">${id}</span> ${cat}</span>`
                : `<span style="font-size:0.75rem; color:#a78bfa;">${cat}</span>`;
        });
        return badges.length ? `<span style="display:inline-flex; gap:0.3rem; flex-wrap:wrap; align-items:center;">ARC: ${badges.join('')}</span>` : '';
    }

    // SSP profile upgrade order — each entry lists what comes ABOVE it (higher bars only)
    // Cloud and on-prem are separate tracks; specialist profiles are standalone.
    _sspUpgradeChain(profile) {
        const chains = {
            'low_risk_cloud':              ['medium_risk_cloud', 'high_risk_cloud_cii'],
            'medium_risk_cloud':           ['high_risk_cloud_cii'],
            'high_risk_cloud_cii':         [],
            'low_risk_onprem':             [],
            'generative_ai':               [],
            'digital_services_others':     ['digital_services_high_impact'],
            'digital_services_high_impact': [],
            'sandbox':                     [],
        };
        return chains[profile] || [];
    }

    // Update the header SSP profile badge (legacy — now driven by _updateAnalysisStatusBar)
    _updateSspBadge() {
        const label = document.getElementById('ssp-profile-badge-label');
        if (!label) return;
        label.textContent = this._sspProfileLabel(this.sspProfile);
    }

    // Populate the analysis status bar in header-right after analysis completes
    _updateAnalysisStatusBar(moeConf) {
        const bar = document.getElementById('analysis-status-bar');
        const placeholder = document.getElementById('pattern-badges-placeholder');
        if (!bar || !this.analysisData) return;

        // Architecture name
        const archName = this.analysisData.architecture_name || this.analysisData.architecture || '';
        const nameEl = document.getElementById('status-arch-name');
        if (nameEl) { nameEl.textContent = archName; nameEl.title = archName; }

        // SSP pill
        this._updateSspBadge();

        // Foundation confidence pill
        const confEl = document.getElementById('status-confidence');
        if (confEl) {
            const confPct = ((this.analysisData.confidence ?? 0.995) * 100).toFixed(1);
            confEl.textContent = confPct + '% confidence';
            confEl.style.display = 'inline-flex';
        }

        // MoE pill — updated when MoE completes; hidden until then
        this._updateMoePill(moeConf);

        // Show bar, hide placeholder
        bar.style.display = 'flex';
        if (placeholder) placeholder.style.display = 'none';
    }

    // Call after MoE completes to update the MoE status pill with final confidence + mode
    _updateMoePill(moeData) {
        const moeEl = document.getElementById('status-moe');
        if (!moeEl) return;
        if (!moeData) { moeEl.style.display = 'none'; return; }
        const finalConf = typeof moeData === 'number' ? moeData.toFixed(1)
            : (moeData.confidence?.final ?? 0).toFixed(1);
        const mode = typeof moeData === 'number' ? '' : (moeData.critic_mode || '');
        const modeLabel = mode === 'sequential' ? 'seq' : mode === 'parallel' ? 'par' : mode === 'partial_parallel' ? 'auto' : mode;
        moeEl.textContent = '🧠 MoE ' + finalConf + '%' + (modeLabel ? ' · ' + modeLabel : '');
        moeEl.style.display = 'inline-flex';
    }

    // Toggle the custom arch history dropdown panel
    _toggleArchDropdown() {
        const panel   = document.getElementById('arch-history-panel');
        const chevron = document.getElementById('arch-history-chevron');
        if (!panel) return;
        const open = panel.style.display !== 'none';
        panel.style.display = open ? 'none' : 'block';
        if (chevron) chevron.textContent = open ? '▼' : '▲';
        if (!open) {
            // Refresh list from server every time the dropdown opens so deleted
            // or newly added analyses are immediately reflected.
            const list = document.getElementById('arch-history-list');
            if (list) list.innerHTML = '<div style="padding:0.75rem 1rem; font-size:0.8rem; color:var(--text-tertiary);">Refreshing…</div>';
            this._loadArchHistory().then(() => this._initArchPanelScroll());
        }
    }

    // Close dropdown when clicking outside
    _closeArchDropdown() {
        const panel   = document.getElementById('arch-history-panel');
        const chevron = document.getElementById('arch-history-chevron');
        if (panel) panel.style.display = 'none';
        if (chevron) chevron.textContent = '▼';
    }

    // Wire an intersection observer on the "older" items so they reveal one-by-one on scroll
    _initArchPanelScroll() {
        const list = document.getElementById('arch-history-list');
        if (!list) return;
        const hidden = list.querySelectorAll('.arch-item-lazy');
        if (!hidden.length) return;
        const obs = new IntersectionObserver(entries => {
            entries.forEach(e => {
                if (e.isIntersecting) {
                    e.target.style.opacity = '1';
                    e.target.style.transform = 'translateY(0)';
                    obs.unobserve(e.target);
                }
            });
        }, { root: list, threshold: 0.1 });
        hidden.forEach(el => obs.observe(el));
    }

    // Load architecture history dropdown from /api/v1/reports (newest first)
    async _loadArchHistory() {
        try {
            const resp = await fetch('/api/v1/reports');
            if (!resp.ok) return;
            const data = await resp.json();
            const archs = data.architectures || [];

            const wrap = document.getElementById('arch-history-wrap');
            const list = document.getElementById('arch-history-list');
            if (!wrap || !list) return;

            if (!archs.length) {
                list.innerHTML = '<div style="padding:0.75rem 1rem; font-size:0.8rem; color:var(--text-tertiary); font-style:italic;">No analyses yet</div>';
                wrap.style.display = 'none';
                return;
            }

            // "Recent" = last 7 days
            const now = new Date();
            const sevenDaysAgoMs = now.getTime() - 7 * 24 * 60 * 60 * 1000;

            const recent = archs.filter(a => !a.analysed_at || (a.analysed_at * 1000) >= sevenDaysAgoMs);
            const older  = archs.filter(a =>  a.analysed_at && (a.analysed_at * 1000)  < sevenDaysAgoMs);

            const itemStyle = `display:flex; align-items:center; gap:0.6rem; padding:0.55rem 0.9rem; cursor:pointer; transition:background 0.15s; font-size:0.8rem; color:#e8e8e8;`;
            const hoverOn  = e => e.currentTarget.style.background = '#4da6ff18';
            const hoverOff = e => e.currentTarget.style.background = 'transparent';

            const iconBtnStyle = `background:transparent; border:none; cursor:pointer; padding:2px 5px; border-radius:4px; font-size:0.85rem; color:#94a3b8; flex-shrink:0; line-height:1; transition:color 0.15s, background 0.15s;`;

            const makeItem = (a, lazy) => {
                const dt = a.analysed_at
                    ? new Date(a.analysed_at * 1000).toLocaleString('en-GB', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })
                    : '';
                const profilePill = a.ssp_profile
                    ? `<span style="padding:1px 5px; background:#0891b218; border:1px solid #0891b244; border-radius:3px; font-size:0.65rem; font-weight:700; color:#06b6d4; flex-shrink:0;">${this._sspProfileLabel(a.ssp_profile)}</span>`
                    : '';
                const div = document.createElement('div');
                div.style.cssText = itemStyle + (lazy ? 'opacity:0; transform:translateY(6px); transition:opacity 0.25s, transform 0.25s, background 0.15s;' : '');
                if (lazy) div.classList.add('arch-item-lazy');
                div.innerHTML = `<span style="font-size:0.9rem; flex-shrink:0;">📄</span>`
                    + `<span style="flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:600;">${a.name}</span>`
                    + `<span style="font-size:0.72rem; color:#94a3b8; flex-shrink:0;">${dt}</span>`
                    + profilePill
                    + `<button class="arch-item-reload" title="View previous analysis" style="${iconBtnStyle}">👁</button>`
                    + `<button class="arch-item-rerun" title="Re-run analysis" style="${iconBtnStyle}">▶</button>`
                    + `<button class="arch-item-delete" title="Delete report folder" style="${iconBtnStyle}">🗑</button>`;
                div.addEventListener('mouseover', hoverOn);
                div.addEventListener('mouseout',  hoverOff);

                // Click on row body → load previous analysis
                div.addEventListener('click', async (e) => {
                    if (e.target.closest('.arch-item-reload') || e.target.closest('.arch-item-rerun') || e.target.closest('.arch-item-delete')) return;
                    document.getElementById('arch-history-btn-label').textContent = `📄 ${a.name}`;
                    this._closeArchDropdown();
                    await this._loadArchFromReports(a.name);
                });

                // Reload icon → same as row click
                div.querySelector('.arch-item-reload').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    document.getElementById('arch-history-btn-label').textContent = `📄 ${a.name}`;
                    this._closeArchDropdown();
                    await this._loadArchFromReports(a.name);
                });

                // Re-analysis icon → fetch saved before.mmd and trigger fresh analysis
                div.querySelector('.arch-item-rerun').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    this._closeArchDropdown();
                    await this._rerunArchAnalysis(a.name, a.ssp_profile);
                });

                // Delete icon → confirm then DELETE via API
                div.querySelector('.arch-item-delete').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (!confirm(`Delete report folder for "${a.name}"?\n\nThis cannot be undone.`)) return;
                    try {
                        const r = await fetch(`/api/v1/reports/${encodeURIComponent(a.name)}`, { method: 'DELETE', headers: { 'TM-API-KEY': localStorage.getItem('tm_api_key') || '' } });
                        if (!r.ok) throw new Error(`Server returned ${r.status}`);
                        div.remove();
                    } catch (err) {
                        alert(`Failed to delete "${a.name}": ${err.message}`);
                    }
                });

                return div;
            };

            list.innerHTML = '';

            // Recent section header
            if (recent.length) {
                const hdr = document.createElement('div');
                hdr.style.cssText = 'padding:0.3rem 0.9rem 0.2rem; font-size:0.65rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:#64748b;';
                hdr.textContent = 'Recent';
                list.appendChild(hdr);
                recent.forEach(a => list.appendChild(makeItem(a, false)));
            }

            // Older section — collapsible, items revealed on scroll
            if (older.length) {
                const sep = document.createElement('div');
                sep.style.cssText = 'display:flex; align-items:center; gap:0.5rem; padding:0.45rem 0.9rem; cursor:pointer; border-top:1px solid #4da6ff22; margin-top:0.25rem; font-size:0.72rem; font-weight:700; color:#64748b; user-select:none;';
                sep.innerHTML = '<span id="older-chevron" style="font-size:0.6rem;">▶</span> Past analysis';

                const olderGroup = document.createElement('div');
                olderGroup.style.display = 'none';
                older.forEach(a => olderGroup.appendChild(makeItem(a, true)));

                sep.addEventListener('click', () => {
                    const open = olderGroup.style.display !== 'none';
                    olderGroup.style.display = open ? 'none' : 'block';
                    sep.querySelector('#older-chevron').textContent = open ? '▶' : '▼';
                    if (!open) this._initArchPanelScroll();
                });

                list.appendChild(sep);
                list.appendChild(olderGroup);
            }

            wrap.style.display = 'block';

            // Close on outside click
            document.addEventListener('click', e => {
                const wrap2 = document.getElementById('arch-history-wrap');
                if (wrap2 && !wrap2.contains(e.target)) this._closeArchDropdown();
            }, { capture: true, once: false });

        } catch (e) {
            // Non-critical — silently ignore
        }
    }

    // Load a previously analysed architecture from the reports folder into the dashboard
    async _loadArchFromReports(archName) {
        try {
            const resp = await fetch(`/api/v1/reports/${archName}/files/ground_truth.json`);
            if (!resp.ok) throw new Error('ground_truth.json not found');
            const gt = await resp.json();

            // Derive sspProfile from metadata if available
            this.sspProfile = (gt.metadata || {}).ssp_profile || 'low_risk_cloud';

            // Wrap in the same shape the analysis SSE result produces
            this.analysisData = {
                success: true,
                architecture_name: archName,
                analysis: gt,
                ssp_profile: this.sspProfile,
            };

            // Show tab content, hide upload form
            document.getElementById('upload-form-container').style.display = 'none';
            document.getElementById('tab-content').style.display = 'block';
            this._setContentTabsDisabled(false);
            const expertReviewTab = document.querySelector('.nav-tab[data-tab="expert-review"]');
            if (expertReviewTab) expertReviewTab.style.display = 'block';
            const tmNavTabLoad = document.getElementById('threat-model-nav-tab');
            if (tmNavTabLoad) tmNavTabLoad.style.display = 'block';

            // Show "New Analysis" button
            const uploadBtn = document.getElementById('upload-btn');
            const newAnalysisBtn = document.getElementById('new-analysis-btn');
            if (uploadBtn) uploadBtn.style.display = 'none';
            if (newAnalysisBtn) newAnalysisBtn.style.display = 'inline-block';

            // Update status bar (fetch moe json for pill if it exists)
            this._updateAnalysisStatusBar();
            fetch(`/api/v1/reports/${encodeURIComponent(archName)}/files/07_moe_orchestrator.json`)
                .then(r => r.ok ? r.json() : null).then(m => { if (m) this._updateMoePill(m); }).catch(() => {});

            this.loadTabData(this.currentTab);
        } catch (e) {
            console.warn('[ArchHistory] Failed to load', archName, e);
        }
    }

    // Re-run analysis for an architecture by fetching its saved before.mmd
    async _rerunArchAnalysis(archName, sspProfile) {
        try {
            const resp = await fetch(`/api/v1/reports/${archName}/files/before.mmd`);
            if (!resp.ok) throw new Error('before.mmd not found');
            const mmdText = await resp.text();

            // Build a File object from the saved content so startAnalysis can use it
            const blob = new Blob([mmdText], { type: 'text/plain' });
            const file = new File([blob], `${archName}.mmd`, { type: 'text/plain' });

            // Pre-fill state then trigger analysis
            this.resetForNewAnalysis();

            // Set SSP profile if known
            if (sspProfile) {
                const sspSelect = document.getElementById('ssp-profile-select');
                if (sspSelect) sspSelect.value = sspProfile;
            }

            // Inject file into the input and submit
            const fileInput = document.getElementById('file-input');
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;

            await this.startAnalysis();
        } catch (e) {
            console.warn('[ArchHistory] Re-analysis failed for', archName, e);
            this.updateStatusMessage(`⚠️ Could not reload ${archName} for re-analysis`);
        }
    }

    // Profile display label
    _sspProfileLabel(key) {
        const labels = {
            'low_risk_cloud':              'Low Risk — Cloud',
            'medium_risk_cloud':           'Medium Risk — Cloud',
            'high_risk_cloud_cii':         'High Risk — Cloud / CII',
            'low_risk_onprem':             'Low Risk — On-Premises',
            'generative_ai':               'Generative AI',
            'digital_services_others':     'Digital Services (under 1M/yr)',
            'digital_services_high_impact':'Digital Services (1M+/yr)',
            'sandbox':                     'Sandbox / Pilot',
        };
        return labels[key] || key;
    }

    // Build the SSP section HTML for a control's detail pane.
    // Shows the matched baseline control + upgrade deltas for higher profiles.
    _renderSspDetailSection(control) {
        const ssp = control.ssp_context;
        if (!ssp || !ssp.primary) return '';

        const p = ssp.primary;
        const profileLabel = this._sspProfileLabel(this.sspProfile || ssp.profile);
        // Always use the level for the currently-selected profile, not the analysis-time level
        const resolvedLevel = (p.levels_by_profile || {})[this.sspProfile] ?? p.level;
        const levelColor = resolvedLevel === 0 ? 'var(--danger-color)' : resolvedLevel === 1 ? 'var(--warning-color)' : 'var(--primary-color)';

        // Baseline block (wrapped in a collapsible <details> element)
        let html = `
        <details style="margin-bottom:1.5rem;">
          <summary style="cursor:pointer; list-style:none; display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.875rem; background:#0891b20e; border:1px solid #0891b244; border-radius:8px; font-size:0.8125rem; font-weight:700; color:#06b6d4; user-select:none;">
            <span>🏛</span>
            <span>SSP Baseline — ${p.id}: ${p.title}</span>
            <span style="padding:1px 5px; background:${levelColor}18; border:1px solid ${levelColor}44; border-radius:3px; font-size:0.68rem; font-weight:700; color:${levelColor};">${{ 0:'L0 — Cardinal', 1:'L1 — Basic Hygiene', 2:'L2 — Best Practice' }[resolvedLevel] ?? `L${resolvedLevel}`}</span>
            <span style="margin-left:auto; font-size:0.75rem; color:var(--text-tertiary);">▼ expand</span>
          </summary>
          <div style="padding:1rem; background:#0891b20e; border:1px solid #0891b244; border-top:none; border-radius:0 0 8px 8px;">
            <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.6rem; flex-wrap:wrap;">
                <span style="font-size:0.9375rem; font-weight:700; color:#06b6d4;">🏛 Singapore Government SSP Baseline</span>
                <span style="margin-left:auto; font-size:0.75rem; color:var(--text-tertiary);">Profile: ${profileLabel}</span>
            </div>
            <div style="font-size:0.875rem; font-weight:700; color:var(--text-color); margin-bottom:0.5rem;">${p.id} — ${p.title}</div>
            ${(() => {
                const resolvedLevelLabel = { 0:'L0 — Cardinal', 1:'L1 — Basic Hygiene', 2:'L2 — Best Practice' }[resolvedLevel] ?? `L${resolvedLevel}`;
                const govImplication = resolvedLevel === 0
                    ? { icon: '🔴', label: 'Cardinal — Mandatory', detail: 'Deviation requires <strong>HQ approval</strong>. This control is non-negotiable for your system profile.', bg: 'var(--danger-color)', }
                    : resolvedLevel === 1
                    ? { icon: '🟡', label: 'Basic Hygiene — Baseline', detail: 'Deviation requires <strong>Steering Committee (SC) risk acceptance</strong>. Should be implemented as standard practice.', bg: 'var(--warning-color)', }
                    : { icon: '⚪', label: 'Best Practice — Conditional', detail: 'Risk-owner acceptance is sufficient to defer. Recommended for enhanced security posture.', bg: 'var(--text-tertiary)', };
                return `<div style="margin-bottom:0.75rem; padding:0.5rem 0.75rem; background:${govImplication.bg}10; border:1px solid ${govImplication.bg}44; border-radius:6px; display:flex; align-items:flex-start; gap:0.5rem;">
                    <span style="font-size:1rem; flex-shrink:0;">${govImplication.icon}</span>
                    <div>
                        <div style="font-size:0.8rem; font-weight:700; color:${govImplication.bg};">${govImplication.label}</div>
                        <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.15rem; line-height:1.5;">${govImplication.detail}</div>
                    </div>
                    <span style="padding:2px 7px; background:${levelColor}18; border:1px solid ${levelColor}44; border-radius:4px; font-size:0.7rem; font-weight:700; color:${levelColor}; flex-shrink:0; margin-left:auto;">${resolvedLevelLabel}</span>
                </div>`;
            })()}
            ${p.statement ? `<div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:0.5rem; font-style:italic;">${p.statement}</div>` : ''}
            ${p.risk_statement ? `
            <div style="margin-top:0.5rem; padding:0.5rem 0.75rem; background:#dc262612; border-left:3px solid var(--danger-color); border-radius:0 4px 4px 0;">
                <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; color:var(--text-tertiary); margin-bottom:0.2rem;">Why it matters</div>
                <div style="font-size:0.8125rem; color:var(--text-secondary);">${p.risk_statement}</div>
            </div>` : ''}
            ${p.recommendation ? `
            <div style="margin-top:0.5rem; padding:0.5rem 0.75rem; background:#0891b212; border-left:3px solid #06b6d4; border-radius:0 4px 4px 0;">
                <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; color:var(--text-tertiary); margin-bottom:0.2rem;">How to implement</div>
                <div style="font-size:0.8125rem; color:var(--text-secondary);">${p.recommendation}</div>
            </div>` : ''}
            ${(() => {
                const secs = ssp.secondaries || [];
                if (!secs.length) return '';
                const _lc = l => l === 0 ? 'var(--danger-color)' : l === 1 ? 'var(--warning-color)' : 'var(--text-tertiary)';
                const _ll = { 0: 'L0', 1: 'L1', 2: 'L2' };
                const rows = secs.map(s => {
                    const lc = _lc(s.level); const ll = _ll[s.level] ?? `L${s.level}`;
                    return `<div style="padding:0.5rem 0.625rem; background:var(--nav-hover-bg); border:1px solid var(--border-color); border-radius:5px; margin-bottom:0.3rem;">
                        <div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:0.2rem; flex-wrap:wrap;">
                            <span style="font-size:0.8rem; font-weight:700; color:#06b6d4;">${s.id}</span>
                            <span style="padding:1px 4px; background:${lc}18; border:1px solid ${lc}44; border-radius:3px; font-size:0.65rem; font-weight:700; color:${lc};">${ll}</span>
                            <span style="font-size:0.78rem; font-weight:600; color:var(--text-color);">${s.title}</span>
                        </div>
                        ${s.statement ? `<div style="font-size:0.75rem; color:var(--text-secondary); font-style:italic; margin-bottom:0.15rem;">${s.statement}</div>` : ''}
                        ${s.risk_statement ? `<div style="font-size:0.72rem; color:var(--text-tertiary);">⚠ ${s.risk_statement}</div>` : ''}
                    </div>`;
                }).join('');
                return `<details style="margin-top:0.6rem;">
                    <summary style="cursor:pointer; list-style:none; font-size:0.75rem; font-weight:600; color:var(--text-tertiary); padding:0.3rem 0; user-select:none;">
                        +${secs.length} related SSP control${secs.length !== 1 ? 's' : ''} also apply ▼
                    </summary>
                    <div style="margin-top:0.4rem;">${rows}</div>
                </details>`;
            })()}
          </div>`;

        // Upgrade delta — only show profiles ABOVE the selected one
        const upgrades = this._sspUpgradeChain(ssp.profile);
        if (upgrades.length === 0) { html += `</details>`; return html; }

        // Now that levels_by_profile is in p, we can show the exact level change per profile.
        const levelsByProfile = p.levels_by_profile || {};
        const levelAtCurrent  = levelsByProfile[ssp.profile] ?? p.level;

        const sspLevelColor = l => l === 0 ? 'var(--danger-color)' : l === 1 ? 'var(--warning-color)' : 'var(--text-tertiary)';
        const _LEVEL_LABELS = { 0: 'L0 — Cardinal', 1: 'L1 — Basic Hygiene', 2: 'L2 — Best Practice' };
        const _detailPill = (text, lvl) =>
            `<span style="padding:1px 5px; background:${sspLevelColor(lvl)}12; border:1px solid ${sspLevelColor(lvl)}44; border-radius:3px; font-size:0.68rem; font-weight:700; color:${sspLevelColor(lvl)};">${text}</span>`;
        const _DETAIL_LEVEL = { 0: 'L0 — Cardinal', 1: 'L1 — Basic Hygiene', 2: 'L2 — Best Practice' };

        let upgradeHtml = '';
        for (const nextProfile of upgrades) {
            const levelAtNext = levelsByProfile[nextProfile];
            // Only show profiles where the level actually escalates (lower number = stricter).
            // Skip: not listed, same level, or becomes less mandatory — all noise.
            if (levelAtNext === undefined || levelAtNext === null) continue;
            if (levelAtNext >= levelAtCurrent) continue;

            upgradeHtml += `
            <div style="display:flex; align-items:center; gap:0.5rem; padding:0.5rem 0.75rem; background:var(--warning-color)08; border:1px solid var(--warning-color)44; border-radius:6px; margin-bottom:0.4rem; flex-wrap:wrap;">
                <span style="font-size:0.8rem;">⚠</span>
                <div style="flex:1; min-width:180px;">
                    <div style="font-size:0.8125rem; font-weight:700; color:var(--text-color);">${this._sspProfileLabel(nextProfile)}</div>
                    <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.15rem;">Escalates from ${_DETAIL_LEVEL[levelAtCurrent] || `L${levelAtCurrent}`} → ${_DETAIL_LEVEL[levelAtNext] || `L${levelAtNext}`} — becomes <strong>more mandatory</strong> at this profile.</div>
                </div>
                <div style="display:flex; align-items:center; gap:0.35rem; flex-shrink:0;">
                    ${_detailPill(_DETAIL_LEVEL[levelAtCurrent] || `L${levelAtCurrent}`, levelAtCurrent)}
                    <span style="font-size:0.75rem; color:var(--text-secondary);">→</span>
                    ${_detailPill(_DETAIL_LEVEL[levelAtNext] || `L${levelAtNext}`, levelAtNext)}
                </div>
            </div>`;
        }

        if (upgradeHtml) {
            html += `
            <div style="margin-bottom:1.5rem; padding:0.75rem 1rem 0.25rem;">
                <div style="font-size:0.8125rem; font-weight:700; color:var(--text-color); margin-bottom:0.5rem;">⚠ Escalates at stricter profiles</div>
                <div style="font-size:0.75rem; color:var(--text-tertiary); margin-bottom:0.6rem;">This control becomes more mandatory if the system is classified at a stricter profile.</div>
                ${upgradeHtml}
            </div>`;
        }

        html += `</details>`;
        return html;
    }

    // Build an SSP upgrade delta block for a tier card (Overview + Expert Review tiers).
    //
    // For EACH profile in the upgrade chain we partition SSP-mapped recommendations into
    // three buckets per profile:
    //
    //   ESCALATED  — control already exists at current profile at level X,
    //                but at the higher profile it's at a LOWER level number (stricter).
    //                e.g. AC-1 is L2 at low_risk_cloud → L1 at medium_risk_cloud.
    //                "This control becomes Basic Hygiene (was Best Practice)"
    //
    //   NEW        — control has no level entry at the current profile at all,
    //                but IS required at the higher profile.
    //                Genuinely additional controls the user hasn't been asked to implement.
    //
    //   SAME / LOWER priority — no change or control becomes less important: skip entirely.
    //
    // Within the SAME profile (no chain step needed): controls in OTHER tiers whose SSP level
    // matches THIS tier's level but whose level escalates to a LOWER number at a higher profile
    // are already captured by the per-profile loop above. Nothing extra to show within the same
    // profile that isn't already visible in the recommendation list.
    //
    // Only profiles ABOVE the selected one are shown (never lower).
    //
    // tierLabel: string like "Quick Wins", "Recommended", "Maximum"
    // tierItems: string[] of control names in this tier (from MoE improvement_options)
    _renderSspTierUpgradeDelta(tierItems, tierLabel) {
        if (!this.analysisData) return '';
        const analysis = this.analysisData.analysis || {};
        const recs = analysis.control_recommendations || [];
        const currentProfile = this.sspProfile || 'medium_risk_cloud';
        const upgradeProfiles = this._sspUpgradeChain(currentProfile);
        if (upgradeProfiles.length === 0) return '';

        const tierItemsUpper = (tierItems || []).map(i => i.toUpperCase().trim());

        // Level label constants (mirrors backend _LEVEL_LABELS)
        const _LEVEL_LABELS = { 0: 'L0 — Cardinal', 1: 'L1 — Basic Hygiene', 2: 'L2 — Best Practice' };
        const levelColor = l => l === 0 ? 'var(--danger-color)' : l === 1 ? 'var(--warning-color)' : 'var(--text-tertiary)';
        const _pill = (text, bg, border, color) =>
            `<span style="padding:1px 5px; background:${bg}; border:1px solid ${border}; border-radius:3px; font-size:0.68rem; font-weight:700; color:${color}; white-space:nowrap;">${text}</span>`;

        // Build per-profile delta.
        // Structure: { profile: { escalated: [], new_controls: [] } }
        const deltaByProfile = {};

        for (const nextProfile of upgradeProfiles) {
            const escalated = [];
            const newControls = [];

            for (const rec of recs) {
                const ssp = rec.ssp_context;
                if (!ssp || !ssp.primary) continue;

                const p = ssp.primary;
                const levelsByProfile = p.levels_by_profile || {};
                const levelAtCurrent = levelsByProfile[currentProfile] ?? p.level;   // level at selected profile
                const levelAtNext    = levelsByProfile[nextProfile];                 // level at higher profile (may be undefined)

                const controlId   = p.id;
                const controlName = rec.control || rec.name || '';
                const entry = { name: controlName, id: controlId, title: p.title, label: ssp.label };

                if (levelAtNext === undefined || levelAtNext === null) {
                    // Not required at the higher profile at all — skip
                    continue;
                }

                if (levelAtCurrent === undefined || levelAtCurrent === null) {
                    // Not required at current profile → genuinely NEW at the higher profile
                    newControls.push({ ...entry, levelAtNext, levelLabelNext: _LEVEL_LABELS[levelAtNext] || `L${levelAtNext}` });
                } else if (levelAtNext < levelAtCurrent) {
                    // ESCALATED: same control becomes MORE mandatory (lower level number = stricter)
                    escalated.push({
                        ...entry,
                        levelAtCurrent,
                        levelAtNext,
                        levelLabelCurrent: _LEVEL_LABELS[levelAtCurrent] || `L${levelAtCurrent}`,
                        levelLabelNext:    _LEVEL_LABELS[levelAtNext]    || `L${levelAtNext}`,
                    });
                }
                // levelAtNext >= levelAtCurrent: no change or relaxed — skip
            }

            if (escalated.length > 0 || newControls.length > 0) {
                deltaByProfile[nextProfile] = { escalated, newControls };
            }
        }

        if (Object.keys(deltaByProfile).length === 0) return '';

        // Compact summary: one line per upgrade profile showing escalated + new counts
        let summaryLines = '';
        for (const [profile, { escalated, newControls }] of Object.entries(deltaByProfile)) {
            const parts = [];
            if (escalated.length > 0) parts.push(`${escalated.length} escalate`);
            if (newControls.length > 0) parts.push(`${newControls.length} new`);
            if (!parts.length) continue;
            summaryLines += `<div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:0.2rem; font-size:0.72rem; flex-wrap:wrap;">
                <span style="color:var(--text-secondary); font-weight:600;">${this._sspProfileLabel(profile)}:</span>
                ${parts.map(p => `<span style="padding:1px 5px; background:#0891b215; border:1px solid #0891b244; border-radius:3px; color:#06b6d4; font-weight:700;">${p}</span>`).join('')}
                <span style="color:var(--text-tertiary);">controls become more mandatory</span>
            </div>`;
        }

        if (!summaryLines) return '';

        const html = `<div style="margin-top:0.875rem; padding:0.5rem 0.75rem; background:#0891b20a; border:1px solid #0891b233; border-radius:6px;">
            <div style="font-size:0.68rem; font-weight:700; color:#06b6d4; margin-bottom:0.35rem; text-transform:uppercase; letter-spacing:.04em;">🏛 SSP at stricter profiles</div>
            ${summaryLines}
        </div>`;
        return html;
    }

    async showControlDetail(control) {
        const rightPane = document.getElementById('right-pane');
        const rightPaneContent = document.getElementById('right-pane-content');

        if (!rightPane || !rightPaneContent) return;

        const priorityColor =
            control.priority === 'critical' ? 'var(--danger-color)' :
            control.priority === 'high' ? 'var(--warning-color)' :
            'var(--primary-color)';

        // Fetch technique names + per-technique mitigations in parallel
        const techs = control.techniques || [];
        const [techniqueNames, tmData] = await Promise.all([
            this.fetchTechniqueNames(techs),
            techs.length > 0
                ? fetch(`/api/v1/technique-mitigations?technique_ids=${techs.join(',')}`)
                    .then(r => r.ok ? r.json() : { mappings: {} })
                    .catch(() => ({ mappings: {} }))
                : Promise.resolve({ mappings: {} })
        ]);
        const techMitMappings = tmData.mappings || {};
        const allMitIds = [...new Set(Object.values(techMitMappings).flat())];
        const mitigationNames = await this.fetchMitigationNames(allMitIds);

        // Coverage count: how many of this control's techniques each mitigation addresses
        const mitCoverage = {};
        for (const mits of Object.values(techMitMappings)) {
            for (const m of mits) { mitCoverage[m] = (mitCoverage[m] || 0) + 1; }
        }
        // Return mitigation list sorted by coverage desc
        const sortedMits = (mits) => [...mits].sort((a, b) => (mitCoverage[b] || 0) - (mitCoverage[a] || 0));

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
                            <div style="font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.5rem;">• ${r}</div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>

            ${this._renderSspDetailSection(control)}

            <div style="margin-bottom: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem; color: var(--warning-color);">🎯 Attack Paths Affected</h4>
                ${control.attack_paths && control.attack_paths.length > 0 ? `
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        ${control.attack_paths.map(pathIdx => `
                            <span style="padding: 0.5rem 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; font-size: 0.875rem;">AP-${pathIdx + 1}</span>
                        `).join('')}
                    </div>
                    <p style="margin-top: 0.75rem; font-size: 0.8125rem; color: var(--text-tertiary);">
                        Addresses vulnerabilities in ${control.attack_paths.length} attack path${control.attack_paths.length > 1 ? 's' : ''}
                    </p>
                ` : '<p style="color: var(--text-tertiary); font-style: italic;">No specific paths mapped</p>'}
            </div>

            <div style="margin-bottom: 1.5rem;">
                ${(() => {
                    const isArcCtrl = techs.some(t => t.startsWith('AML.'));
                    const arcCatM = (control.rationale || '').match(/AI\/ML \(ARC\):\s*([^|]+)/);
                    const arcCatsStr = arcCatM ? this._formatArcCats(arcCatM[1].trim()) : '';
                    if (!isArcCtrl) return '';
                    return `<div style="margin-bottom:0.75rem; padding:0.625rem 0.875rem; background:#7c3aed12; border:1px solid #7c3aed44; border-radius:8px;">
                        <div style="font-size:0.8125rem; font-weight:700; color:#a78bfa; margin-bottom:0.2rem;">🤖 ARC Framework + MITRE ATLAS</div>
                        <div style="font-size:0.8125rem; color:var(--text-secondary);">This control was recommended by the <strong>ARC Framework</strong> (AI Risk & Control) for AI/agentic architectures, mapped to <strong>MITRE ATLAS</strong> AI/ML adversarial techniques — not covered by standard MITRE Enterprise ATT&CK.</div>
                        ${arcCatsStr ? `<div style="font-size:0.75rem; color:#a78bfa; margin-top:0.35rem;">${arcCatsStr}</div>` : ''}
                    </div>`;
                })()}
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem; color: var(--primary-color);">🔬 Techniques & Mitigations</h4>
                ${techs.length > 0 ? `
                    ${techs.map(tech => {
                        const isAtlas = tech.startsWith('AML.');
                        const techColor = isAtlas ? '#a78bfa' : 'var(--primary-color)';
                        const techBadge = isAtlas
                            ? `<span style="padding:1px 5px; background:#7c3aed18; border:1px solid #7c3aed55; border-radius:3px; font-size:0.65rem; font-weight:700; color:#a78bfa; margin-left:0.4rem;">ATLAS</span>`
                            : `<span style="padding:1px 5px; background:var(--primary-color)18; border:1px solid var(--primary-color)44; border-radius:3px; font-size:0.65rem; font-weight:700; color:var(--primary-color); margin-left:0.4rem;">ATT&CK</span>`;
                        const atlasUrl = isAtlas
                            ? `https://atlas.mitre.org/techniques/${tech}/`
                            : `https://attack.mitre.org/techniques/${tech}/`;
                        const techName = techniqueNames[tech] || tech;
                        const mits = sortedMits(techMitMappings[tech] || []);
                        const mitBodyId = `mit-body-${tech.replace(/\./g, '_')}`;
                        return `
                        <div style="margin-bottom: 0.75rem; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden;">
                            <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--nav-hover-bg); border-left: 3px solid ${techColor}; cursor:pointer; user-select:none;"
                                 onclick="(function(h){var b=document.getElementById('${mitBodyId}');var c=h.querySelector('.tech-chevron');if(!b)return;var open=b.style.display!=='none';b.style.display=open?'none':'block';c.textContent=open?'›':'⌄';})(this)">
                                <div style="display:flex; align-items:center; flex-wrap:wrap; gap:0.25rem;">
                                    <code style="font-weight: 700; color: ${techColor}; font-size: 0.875rem;">${tech}</code>
                                    ${techBadge}
                                    ${techName !== tech ? `<span style="margin-left: 0.25rem; color: var(--text-color); font-size: 0.875rem; font-weight: 600;">· ${techName}</span>` : ''}
                                    ${mits.length > 0 ? `<span style="font-size:0.7rem; color:var(--text-tertiary); margin-left:0.25rem;">${mits.length} mitigation${mits.length !== 1 ? 's' : ''}</span>` : ''}
                                </div>
                                <div style="display:flex; align-items:center; gap:0.5rem; flex-shrink:0;">
                                    <a href="${atlasUrl}" target="_blank" class="btn-icon" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; text-decoration: none;" onclick="event.stopPropagation()">🔗</a>
                                    <span class="tech-chevron" style="font-size:1rem; color:var(--text-tertiary); min-width:0.75rem; text-align:center;">›</span>
                                </div>
                            </div>
                            <div id="${mitBodyId}" style="display:none;">
                            ${mits.length > 0 ? `
                                <div style="background: var(--card-bg); border-top: 1px solid var(--border-color);">
                                    <div style="padding: 0.375rem 0.75rem; font-size: 0.6875rem; color: var(--text-tertiary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border-color);">
                                        ${mits.length} Mitigation${mits.length !== 1 ? 's' : ''} — broadest coverage first
                                    </div>
                                    ${mits.map((m, idx) => {
                                        const cov = mitCoverage[m] || 1;
                                        const covLabel = techs.length > 1 ? `covers ${cov}/${techs.length} technique${cov !== 1 ? 's' : ''}` : '';
                                        const isAtlasMit = m.startsWith('AML.');
                                        const mitUrl = isAtlasMit
                                            ? `https://atlas.mitre.org/mitigations/${m}/`
                                            : `https://attack.mitre.org/mitigations/${m}/`;
                                        const mitColor = isAtlasMit ? '#a78bfa' : 'var(--secondary-color)';
                                        return `
                                        <a href="${mitUrl}" target="_blank"
                                           style="display:flex; align-items:center; gap:0.5rem; padding:0.5rem 0.75rem; border-bottom:${idx < mits.length - 1 ? '1px solid var(--border-color)' : 'none'}; text-decoration:none; transition:background 0.15s;"
                                           onmouseover="this.style.background='var(--nav-hover-bg)'" onmouseout="this.style.background='transparent'">
                                            <code style="color:${mitColor}; font-weight:700; font-size:0.8125rem; flex-shrink:0;">${m}</code>
                                            <span style="color:var(--text-secondary); font-size:0.8125rem; flex:1;">${mitigationNames[m] || ''}</span>
                                            ${isAtlasMit ? `<span style="padding:1px 4px; background:#7c3aed18; border:1px solid #7c3aed44; border-radius:3px; font-size:0.6rem; font-weight:700; color:#a78bfa; flex-shrink:0;">ATLAS</span>` : ''}
                                            ${covLabel ? `<span style="font-size:0.7rem; color:var(--text-tertiary); flex-shrink:0; white-space:nowrap;">${covLabel}</span>` : ''}
                                            <span style="font-size:0.7rem; color:var(--text-tertiary); flex-shrink:0;">↗</span>
                                        </a>
                                    `}).join('')}
                                </div>
                            ` : `<div style="padding:0.5rem 0.75rem; background:var(--card-bg); border-top:1px solid var(--border-color); font-size:0.75rem; color:var(--text-tertiary); font-style:italic;">No mitigations mapped for this technique</div>`}
                            </div>
                        </div>`;
                    }).join('')}
                ` : '<p style="color: var(--text-tertiary); font-style: italic;">No techniques mapped</p>'}
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
                                        🛡️ ${this._nodeLabelMap?.[node] || node}
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
                                    await new Promise(r => setTimeout(r, 100));
                                    this[`fullScale`] = undefined; // reset so auto-fit runs fresh
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
                                await new Promise(r => setTimeout(r, 100));
                                this[`afterScale`] = undefined; // reset so auto-fit runs fresh
                                this.setupDiagramZoom('after');
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

                // Setup zoom for before diagram only — after/full are set up post-render
                await new Promise(resolve => setTimeout(resolve, 100));
                this.setupDiagramZoom('before');
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
        // Container naming: try exact id, then "{prefix}-diagram-container", then "{prefix}-container"
        const container =
            document.getElementById(`${prefix}-diagram-container`) ||
            document.getElementById(`${prefix}-container`) ||
            document.getElementById(prefix);

        if (!container) return;

        const getSvg = () => container.querySelector('svg');

        // Capture/refresh original dimensions from the live SVG.
        // Called here and again after deferred renders so zoom math is always correct.
        const captureSize = () => {
            const svg = getSvg();
            if (!svg) return false;
            const bbox = svg.getBBox ? svg.getBBox() : {};
            const w = parseFloat(svg.getAttribute('width'))  || bbox.width  || 800;
            const h = parseFloat(svg.getAttribute('height')) || bbox.height || 600;
            if (w > 1 && h > 1) {
                this[`${prefix}OriginalWidth`]  = w;
                this[`${prefix}OriginalHeight`] = h;
                return true;
            }
            return false;
        };

        // Scale state lives on the instance so re-calls share state (not accumulate).
        if (this[`${prefix}Scale`] === undefined) this[`${prefix}Scale`] = 1;
        const getScale = ()  => this[`${prefix}Scale`];
        const setScale = (v) => { this[`${prefix}Scale`] = v; };

        const applyScale = (s) => {
            const svg = getSvg();
            if (!svg) return;
            if (!this[`${prefix}OriginalWidth`]) { if (!captureSize()) return; }
            setScale(s);
            svg.setAttribute('width',  this[`${prefix}OriginalWidth`]  * s);
            svg.setAttribute('height', this[`${prefix}OriginalHeight`] * s);
            svg.style.maxWidth = 'none';
        };

        // Auto-fit on first setup — wait for Mermaid to finish rendering.
        setTimeout(() => {
            if (!captureSize()) return;
            const containerWidth = container.clientWidth - 32;
            const fitScale = containerWidth < this[`${prefix}OriginalWidth`]
                ? containerWidth / this[`${prefix}OriginalWidth`]
                : 1;
            applyScale(fitScale);
        }, 200);

        // Replace each button with a fresh clone to remove any previous listeners.
        const wire = (id, handler) => {
            const old = document.getElementById(id);
            if (!old) return;
            const fresh = old.cloneNode(true);
            old.parentNode.replaceChild(fresh, old);
            fresh.addEventListener('click', handler);
        };

        wire(`${prefix}-zoom-in`,   () => applyScale(Math.min(getScale() + 0.2, 4)));
        wire(`${prefix}-zoom-out`,  () => applyScale(Math.max(getScale() - 0.2, 0.1)));
        wire(`${prefix}-zoom-reset`, () => {
            if (!this[`${prefix}OriginalWidth`]) { captureSize(); }
            const containerWidth = container.clientWidth - 32;
            const fitScale = Math.min(1, containerWidth / (this[`${prefix}OriginalWidth`] || 800));
            applyScale(fitScale);
            container.scrollTop  = 0;
            container.scrollLeft = 0;
        });
        wire(`${prefix}-fit-width`, () => {
            if (!this[`${prefix}OriginalWidth`]) { captureSize(); }
            applyScale((container.clientWidth - 32) / (this[`${prefix}OriginalWidth`] || 800));
        });
        wire(`${prefix}-fit-height`, () => {
            if (!this[`${prefix}OriginalHeight`]) { captureSize(); }
            applyScale((container.clientHeight - 32) / (this[`${prefix}OriginalHeight`] || 600));
        });
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

        const diagram = `flowchart LR\n    ${nodes}\n    style ${path.path[0].replace(/[[\](){}]/g, '')} fill:#ff6b8a,stroke:#ff0033,stroke-width:3px,color:#000000\n    style ${path.path[path.path.length - 1].replace(/[[\](){}]/g, '')} fill:#f39c12,stroke:#d68910,stroke-width:3px,color:#000000`;
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
                <h4 style="font-size: 1.125rem; margin-bottom: 0.5rem;">${this._nodeLabelMap?.[node] || node}</h4>
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
        this._nodeLabelMap = {};  // nodeId → human-readable label, populated as a side-effect
        const pathIndex = this.getPathIndex(path);

        // Controls that are only applicable to specific node layer types.
        // Controls NOT listed here are considered broadly applicable (e.g. least privilege, logging, mfa).
        // 'unknown' is always permissive — unrecognised nodes could be any type.
        const CONTROL_LAYER_RESTRICTIONS = {
            // Host-agent controls — valid on any node that runs a real OS/process.
            // Excluded from: data (managed storage like S3/RDS), network (managed LB/firewall appliances).
            'edr':                ['device', 'application', 'identity', 'unknown'],
            'antivirus':          ['device', 'identity', 'unknown'],
            'device hardening':   ['device', 'identity', 'unknown'],

            // Code-deployment controls — meaningful anywhere software artifacts are built/deployed.
            // Excluded from: network (LBs/firewalls are not code deployment targets), data (storage buckets).
            'code signing':       ['application', 'device', 'identity', 'unknown'],
            'container scanning': ['application', 'device', 'identity', 'network', 'unknown'],

            // Patching — any node running patchable software (OS, runtime, gateway).
            // Excluded from: data (cloud providers manage S3/RDS patching).
            'patching':           ['device', 'application', 'identity', 'network', 'unknown'],
            'patch management':   ['device', 'application', 'identity', 'network', 'unknown'],

            // HTTP/API layer controls — valid on any node that handles HTTP traffic.
            // Excluded from: data (storage layer, no HTTP endpoint), device (bare OS host layer).
            'waf':                ['network', 'application', 'identity', 'unknown'],
            'input validation':   ['application', 'identity', 'network', 'unknown'],

            // Data-layer-only controls — only meaningful on storage/database nodes.
            'database firewall':  ['data'],
            'data masking':       ['data'],
            'query monitoring':   ['data'],
        };

        console.log('[DEBUG] groupControlsByNode - controls count:', controls.length);
        console.log('[DEBUG] groupControlsByNode - pathIndex:', pathIndex);

        controls.forEach(control => {
            const hopAnalysis = control._layered_defense?.hop_analysis || [];
            console.log('[DEBUG] control:', control.control, 'has hop_analysis:', hopAnalysis.length > 0);

            const pathHops = hopAnalysis.filter(hop => hop.path_id === pathIndex);

            if (pathHops.length > 0) {
                pathHops.forEach(hop => {
                    // Key by node ID (matches path.path entries exactly) for diagram wiring
                    const nodeKey = hop.target_id || hop.source_id || hop.target_label || hop.source_label;
                    const nodeLabel = hop.target_label || hop.source_label || nodeKey;
                    if (nodeKey) {
                        // Store human label for display (node IDs like "OnPremApp" → "Legacy Application")
                        if (nodeLabel && nodeLabel !== nodeKey) {
                            this._nodeLabelMap[nodeKey] = nodeLabel;
                        }
                        // Skip controls that are not applicable to this node's layer type
                        const controlName = (control.control || '').toLowerCase();
                        const hopLayer = hop.layer || 'unknown';
                        const allowedLayers = CONTROL_LAYER_RESTRICTIONS[controlName];
                        if (allowedLayers && !allowedLayers.includes(hopLayer)) {
                            console.log(`[DEBUG] Skipping "${controlName}" for ${nodeKey} (layer: ${hopLayer}) — not applicable to this node type`);
                            return;
                        }

                        if (!grouped[nodeKey]) {
                            grouped[nodeKey] = [];
                        }
                        // Avoid duplicates
                        if (!grouped[nodeKey].some(c => c.control === control.control)) {
                            grouped[nodeKey].push(control);
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
        // Exact match first (hardenedNode is now keyed by node ID, same as pathNodes)
        if (pathNodes.includes(hardenedNode)) {
            return hardenedNode;
        }

        // Fallback: fuzzy normalized match (handles legacy data where key is a label)
        const normalizedHardened = this.normalizeNodeName(hardenedNode);
        for (const pathNode of pathNodes) {
            const normalizedPath = this.normalizeNodeName(pathNode);
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
        styles += `    style ${path.path[0].replace(/[[\](){}]/g, '')} fill:#ff6b8a,stroke:#ff0033,stroke-width:3px,color:#000000\n`;

        // Target (orange)
        styles += `    style ${path.path[path.path.length - 1].replace(/[[\](){}]/g, '')} fill:#f39c12,stroke:#d68910,stroke-width:3px,color:#000000\n`;

        // Protected nodes (green) - nodes that have controls
        hardenedNodes.forEach(hardenedNode => {
            const matchingPathNode = this.findMatchingPathNode(hardenedNode, path.path);
            if (matchingPathNode) {
                styles += `    style ${matchingPathNode.replace(/[[\](){}]/g, '')} fill:#5fd49c,stroke:#00aa55,stroke-width:4px,color:#000000\n`;
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

    async loadThreatModelTab() {
        const gt = this.analysisData && this.analysisData.analysis;
        const placeholder = document.getElementById('tm-placeholder');
        if (!gt || !gt.threat_model) {
            if (placeholder) placeholder.style.display = 'block';
            return;
        }
        if (placeholder) placeholder.style.display = 'none';

        const tm = gt.threat_model || {};
        const aps = gt.expected_attack_paths || [];
        const adrs = gt.architecture_decision_records || [];
        const bh = gt.blackhat_critique || null;
        const rrs = tm.residual_risk_summary || {};

        // TLDR
        const tldr = document.getElementById('tm-tldr');
        const tldrText = document.getElementById('tm-tldr-text');
        if (tldr && tldrText && tm.highest_risk_scenario) {
            const rs = tm.highest_risk_scenario;
            tldrText.textContent = `${rs.threat_actor || '?'} targeting ${rs.targeted_asset || '?'} via ${rs.exploited_vulnerability || '?'} → ${rs.impact || '?'}`;
            tldr.style.display = 'block';
        }

        // Legend
        const legend = document.getElementById('tm-legend');
        if (legend) legend.style.display = 'flex';

        // Overview
        const tmOverview = document.getElementById('tm-overview');
        const tmOverviewContent = document.getElementById('tm-overview-content');
        if (tmOverview && tmOverviewContent) {
            const boundaries = (tm.trust_boundaries_at_risk || []).map(n => `<code>${n}</code>`).join(', ') || '—';
            tmOverviewContent.innerHTML =
                `<b>Architecture type:</b> ${tm.architecture_type || '?'}<br>` +
                `<b>Primary threat actor:</b> ${tm.primary_threat_actor || '?'}<br>` +
                `<b>Bottleneck node:</b> <code>${tm.architecture_weakness || '?'}</code><br>` +
                `<b>Trust boundaries at risk (no detection):</b> ${boundaries}<br>` +
                `<br><i>${tm.summary || ''}</i><br>` +
                (rrs.overall_before ? `<br><b>Overall risk delta:</b> ${rrs.overall_before} → ${rrs.overall_after_controls} (${rrs.status_after}) | Δ −${rrs.risk_reduction_pct}%` : '');
            tmOverview.style.display = 'block';
        }

        // Per-AP sections
        const apContainer = document.getElementById('tm-ap-sections');
        if (apContainer) {
            const tierOrder = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1};
            const sortedAps = [...aps].sort((a, b) =>
                (tierOrder[b.criticality_tier] || 0) - (tierOrder[a.criticality_tier] || 0)
            );
            const tierColor = {CRITICAL: '#DC143C', HIGH: '#FF8C00', MEDIUM: '#cc9900', LOW: '#32CD32'};
            const adrMap = {};
            adrs.forEach(adr => { adrMap[adr.adr_id] = adr; });

            apContainer.innerHTML = sortedAps.map(ap => {
                const tier = ap.criticality_tier || 'UNKNOWN';
                const color = tierColor[tier] || '#888';
                const path = (ap.path || [ap.entry, ap.target]).slice(0, 5).join(' → ');
                const rs = ap.risk_scenario || {};
                const apAdrs = ap.adr_ids || [];
                const perApR = (rrs.per_ap_residual || []).find(r => r.ap_id === ap.id) || {};

                const rsHtml = rs.threat_actor ? `
                    <div style="font-size:0.84rem; line-height:1.6; padding:0.5rem 0;">
                        🎭 <b>Actor:</b> ${rs.threat_actor}<br>
                        🎯 <b>Asset:</b> ${rs.targeted_asset}<br>
                        ⚡ <b>Vulnerability:</b> ${rs.exploited_vulnerability}<br>
                        💥 <b>Impact:</b> ${rs.impact}
                    </div>` : '<div style="color:var(--text-tertiary);font-size:0.82rem;">Run /generate-narratives to populate risk scenario.</div>';

                const adrHtml = apAdrs.length ? apAdrs.map(adrId => {
                    const adr = adrMap[adrId];
                    if (!adr) return '';
                    const c = adr.consequences || {};
                    return `<span style="display:inline-block;margin:0.2rem 0.3rem 0.2rem 0;padding:0.15rem 0.5rem;background:#1E90FF22;border:1px solid #1E90FF55;border-radius:4px;font-size:0.76rem;">` +
                        `<b>${adrId}</b> ${adr.control} · ${adr.priority} · ${c.residual_risk_before}→${c.residual_risk_after}</span>`;
                }).join('') : '<span style="font-size:0.8rem; color:var(--text-tertiary);">No ADRs linked</span>';

                const residualLine = perApR.residual_after_adrs !== undefined
                    ? `<div style="font-size:0.8rem; margin-top:0.4rem; color:var(--text-tertiary);">Residual after ADRs: <b>${perApR.residual_after_adrs}</b></div>`
                    : '';

                return `<details style="margin-bottom:0.6rem; border:1px solid var(--border-color); border-radius:6px; overflow:hidden;">
                    <summary style="cursor:pointer; padding:0.65rem 1rem; font-weight:600; font-size:0.9rem; background:var(--card-bg); border-left:4px solid ${color};">
                        ${ap.id} [${tier}]: ${path}
                    </summary>
                    <div style="padding:0.75rem 1rem; font-size:0.87rem;">
                        ${rsHtml}
                        <div style="margin-top:0.5rem;"><b>ADRs:</b> ${adrHtml}</div>
                        ${residualLine}
                    </div>
                </details>`;
            }).join('');
        }

        // Blackhat section
        const bhEl = document.getElementById('tm-blackhat');
        const bhContent = document.getElementById('tm-blackhat-content');
        if (bh && bhEl && bhContent) {
            const chains = bh.chained_exploit_findings || [];
            const gaps = bh.mitigation_gaps_for_chains || [];
            const unique = (bh.uniqueness_vs_critics || {}).new_findings_not_in_redteam || [];
            bhContent.innerHTML =
                `<b>Cross-chain score:</b> ${bh.score}/100 (${bh.rating})<br>` +
                `<b>Stealth score:</b> ${bh.stealth_score} technique(s) — ${(bh.stealthy_techniques || []).join(', ') || 'none'}<br>` +
                (chains.length ? `<br><b>Chains:</b><ul style="margin:0.3rem 0;padding-left:1.2rem;">${chains.slice(0,5).map(c=>`<li>${c}</li>`).join('')}</ul>` : '') +
                (gaps.length ? `<b>Mitigation gaps:</b><ul style="margin:0.3rem 0;padding-left:1.2rem;">${gaps.slice(0,5).map(g=>`<li>${g}</li>`).join('')}</ul>` : '') +
                (unique.length ? `<b>New vs Red Team:</b><ul style="margin:0.3rem 0;padding-left:1.2rem;">${unique.slice(0,3).map(f=>`<li>${f}</li>`).join('')}</ul>` : '');
            bhEl.style.display = 'block';
        }

        // 11_final.mmd inline render
        const archName = (this.analysisData || {}).architecture_name;
        if (archName) {
            const diagWrapper = document.getElementById('tm-diagram-wrapper');
            const diagEl = document.getElementById('tm-diagram');
            if (diagWrapper && diagEl) {
                try {
                    const resp = await fetch(`/api/v1/reports/${encodeURIComponent(archName)}/files/11_final.mmd`);
                    if (resp.ok) {
                        const mmdText = await resp.text();
                        diagEl.innerHTML = mmdText;
                        diagEl.removeAttribute('data-processed');
                        if (window.mermaid) {
                            try { await window.mermaid.run({ nodes: [diagEl] }); } catch(e) { /* ignore render errors */ }
                        }
                        diagWrapper.style.display = 'block';
                    }
                } catch(e) { /* diagram not yet generated */ }
            }
        }
    }

    async loadReportsTab() {
        const listContainer = document.getElementById('reports-list');

        if (!this.analysisData) {
            listContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const archName = this.analysisData.architecture_name;
        listContainer.innerHTML = '<p class="placeholder" style="padding: 2rem;">Loading reports...</p>';
        this.updateStatusMessage(`📄 Loading reports for ${archName}...`);

        try {
            const response = await fetch(`/api/v1/reports/${archName}`);
            if (!response.ok) {
                if (response.status === 404) {
                    listContainer.innerHTML = `
                        <div style="padding: 2rem; text-align: center;">
                            <div style="font-size: 3rem; margin-bottom: 1rem;">📂</div>
                            <h3 style="color: var(--text-secondary); margin-bottom: 1rem;">No Reports Yet</h3>
                            <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 1.5rem;">
                                Reports are generated during analysis. Run a full analysis to generate downloadable reports.
                            </p>
                            <p style="color: var(--text-tertiary); font-size: 0.8125rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px;">
                                CLI: <code style="color: var(--primary-color);">python3 -m chatbot.main --gen-arch-truth your_architecture.mmd</code>
                            </p>
                        </div>
                    `;
                    return;
                }
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const data = await response.json();
            this.renderReportsPanel(archName, data.reports || []);
            this.updateStatusMessage(`✅ ${archName} reports ready`);
        } catch (error) {
            console.error('Error loading reports:', error);
            listContainer.innerHTML = `
                <div style="padding: 2rem;">
                    <p style="color: var(--danger-color);">⚠️ Failed to load reports: ${error.message}</p>
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

    async fetchMitigationNames(mitigationIds) {
        if (!mitigationIds || mitigationIds.length === 0) return {};

        if (!this.mitigationNamesCache) this.mitigationNamesCache = {};
        const uncachedIds = mitigationIds.filter(id => !this.mitigationNamesCache[id]);

        if (uncachedIds.length === 0) {
            return mitigationIds.reduce((acc, id) => {
                acc[id] = this.mitigationNamesCache[id];
                return acc;
            }, {});
        }

        try {
            const response = await fetch(`/api/v1/mitigations?mitigation_ids=${uncachedIds.join(',')}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            Object.assign(this.mitigationNamesCache, data.mitigations || {});
            return mitigationIds.reduce((acc, id) => {
                acc[id] = this.mitigationNamesCache[id] || id;
                return acc;
            }, {});
        } catch (error) {
            console.error('Error fetching mitigation names:', error);
            return mitigationIds.reduce((acc, id) => { acc[id] = id; return acc; }, {});
        }
    }

    renderReportsPanel(archName, allFiles) {
        const listContainer = document.getElementById('reports-list');
        this.reportContents = {};

        // Reports tab shows markdown and mermaid only — JSON lives in Raw Data tab
        const REPORT_CATALOGUE = {
            '01_executive_summary.md':    { id: 'executive',   title: 'Executive Summary',   icon: '📊', desc: 'High-level threat overview for leadership and CISOs', audience: 'stakeholder', type: 'markdown' },
            '03_action_plan.md':          { id: 'action',      title: 'Action Plan',          icon: '✅', desc: 'Prioritised recommendations with implementation steps', audience: 'stakeholder', type: 'markdown' },
            '08_improvement_summary.md':  { id: 'improvement', title: 'Improvement Summary',  icon: '🗺️', desc: 'Roadmap across Quick Win, Recommended, and Maximum tiers', audience: 'stakeholder', type: 'markdown' },
            'before.mmd':                 { id: 'before',      title: 'Current Architecture', icon: '⚠️', desc: 'Architecture before hardening controls are applied', audience: 'stakeholder', type: 'mermaid', color: 'var(--danger-color)' },
            'after.mmd':                  { id: 'after',       title: 'Hardened Architecture',icon: '🛡️', desc: 'Architecture with all recommended controls applied', audience: 'stakeholder', type: 'mermaid', color: 'var(--secondary-color)' },
            '02_technical_report.md':     { id: 'technical',   title: 'Technical Report',     icon: '🔧', desc: 'Full MITRE ATT&CK technique mappings and control analysis', audience: 'technical', type: 'markdown' },
            '08a_quick_wins.mmd':         { id: 'tier-a',      title: 'Quick Wins Diagram',   icon: '⚡', desc: 'Architecture diagram with Quick Win controls highlighted', audience: 'technical', type: 'mermaid', color: 'var(--secondary-color)' },
            '08b_recommended_target.mmd': { id: 'tier-b',      title: 'Recommended Diagram',  icon: '📈', desc: 'Architecture diagram with Recommended controls highlighted', audience: 'technical', type: 'mermaid', color: 'var(--primary-color)' },
            '08c_maximum_security.mmd':   { id: 'tier-c',      title: 'Maximum Coverage',     icon: '🔒', desc: 'Architecture diagram with Maximum controls highlighted', audience: 'technical', type: 'mermaid', color: 'var(--warning-color)' },
        };

        // Skip JSON and README — JSON belongs in Raw Data, README is noise
        const SKIP_EXTS = new Set(['.json']);
        const SKIP_FILES = new Set(['README.md']);

        const byAudience = { stakeholder: [], technical: [] };
        const fileMap = {};
        allFiles.forEach(f => fileMap[f.filename] = f);

        Object.entries(REPORT_CATALOGUE).forEach(([filename, meta]) => {
            if (fileMap[filename]) {
                byAudience[meta.audience].push({ ...meta, filename, url: fileMap[filename].url, size: fileMap[filename].size });
            }
        });

        // Any unrecognised non-JSON files not skipped go to technical
        allFiles.forEach(f => {
            const ext = f.filename.includes('.') ? '.' + f.filename.split('.').pop() : '';
            if (!REPORT_CATALOGUE[f.filename] && !SKIP_EXTS.has(ext) && !SKIP_FILES.has(f.filename)) {
                byAudience.technical.push({
                    id: f.filename, title: f.filename,
                    icon: f.type === 'mermaid' ? '🏗️' : '📄',
                    desc: '', audience: 'technical', type: f.type,
                    filename: f.filename, url: f.url, size: f.size
                });
            }
        });

        listContainer.innerHTML = `
            <!-- Download packs -->
            <div style="display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; align-items: center;">
                <span style="font-size: 0.8125rem; color: var(--text-secondary); font-weight: 600;">Download:</span>
                <a href="/api/v1/reports/${archName}/download?pack=stakeholder" download="${archName}_stakeholder.zip"
                   class="btn-primary" style="padding: 0.5rem 1rem; font-size: 0.8125rem; font-weight: 600; text-decoration: none;">
                    ⬇ Stakeholder Pack
                </a>
                <a href="/api/v1/reports/${archName}/download?pack=reports" download="${archName}_reports.zip"
                   style="padding: 0.5rem 1rem; font-size: 0.8125rem; font-weight: 600; background: transparent; color: var(--text-color); border: 1.5px solid var(--border-color); border-radius: 6px; text-decoration: none;">
                    ⬇ All Reports
                </a>
                <span style="font-size: 0.75rem; color: var(--text-tertiary); margin-left: auto;">
                    Click any card to preview · ⬇ on card to download · JSON data → Raw Data tab
                </span>
            </div>

            <!-- Section: For Stakeholders -->
            ${byAudience.stakeholder.length > 0 ? `
            <div class="report-section" style="margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
                    <span style="font-size: 1.125rem;">👔</span>
                    <h4 style="margin: 0; color: var(--text-color); font-size: 0.9375rem;">For Stakeholders</h4>
                    <span style="font-size: 0.75rem; color: var(--text-tertiary); padding: 0.125rem 0.5rem; background: var(--nav-hover-bg); border-radius: 10px;">Decision-driving</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.625rem;">
                    ${byAudience.stakeholder.map(r => this._reportCard(r, archName)).join('')}
                </div>
            </div>` : ''}

            <!-- Section: For Technical Teams -->
            ${byAudience.technical.length > 0 ? `
            <div class="report-section" style="margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
                    <span style="font-size: 1.125rem;">🔧</span>
                    <h4 style="margin: 0; color: var(--text-color); font-size: 0.9375rem;">For Technical Teams</h4>
                    <span style="font-size: 0.75rem; color: var(--text-tertiary); padding: 0.125rem 0.5rem; background: var(--nav-hover-bg); border-radius: 10px;">Implementation depth</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.625rem;">
                    ${byAudience.technical.map(r => this._reportCard(r, archName)).join('')}
                </div>
            </div>` : ''}
        `;

        const allReports = [...byAudience.stakeholder, ...byAudience.technical];
        listContainer.querySelectorAll('[data-report-id]').forEach(card => {
            card.addEventListener('click', () => {
                listContainer.querySelectorAll('[data-report-id]').forEach(c => {
                    c.style.borderColor = 'var(--border-color)';
                    c.style.background = 'var(--card-bg)';
                });
                card.style.borderColor = 'var(--primary-color)';
                card.style.background = 'var(--primary-color)12';
                const report = allReports.find(r => r.id === card.dataset.reportId);
                if (report) this._renderReportInRightPane(report, archName);
            });
        });
    }

    _reportCard(report, archName) {
        return `
            <div data-report-id="${report.id}" style="
                padding: 0.875rem 1rem;
                background: var(--card-bg);
                border: 1.5px solid var(--border-color);
                border-radius: 8px;
                cursor: pointer;
                transition: border-color 0.2s, background 0.2s;
            ">
                <div style="display: flex; align-items: flex-start; gap: 0.5rem;">
                    <span style="font-size: 1.25rem; flex-shrink: 0; margin-top: 0.1rem;">${report.icon}</span>
                    <div style="min-width: 0;">
                        <div style="font-weight: 600; font-size: 0.875rem; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${report.title}</div>
                        ${report.desc ? `<div style="font-size: 0.75rem; color: var(--text-tertiary); margin-top: 0.125rem; line-height: 1.3;">${report.desc}</div>` : ''}
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
                    <span style="font-size: 0.6875rem; color: var(--text-tertiary);">${report.type.toUpperCase()}</span>
                    <a href="/api/v1/reports/${archName}/files/${report.filename}" target="_blank"
                       style="font-size: 0.75rem; color: var(--primary-color); text-decoration: none; padding: 0.125rem 0.375rem; border: 1px solid var(--primary-color); border-radius: 4px;"
                       onclick="event.stopPropagation()">⬇</a>
                </div>
            </div>
        `;
    }

    async _renderReportInRightPane(report, archName) {
        // Show right pane with loading state immediately
        const downloadLink = `<a href="/api/v1/reports/${archName}/files/${report.filename}" download="${report.filename}" class="btn-primary" style="display: inline-block; text-decoration: none; padding: 0.375rem 0.875rem; font-size: 0.8125rem; margin-bottom: 1rem;">⬇ Download ${report.filename}</a>`;

        this.showRightPane(`${report.icon} ${report.title}`, `
            ${downloadLink}
            <div id="rp-content-area" style="color: var(--text-secondary); font-size: 0.875rem;">Loading...</div>
        `);

        // Serve from cache (not mermaid — needs fresh render each time)
        if (this.reportContents[report.id] && report.type !== 'mermaid') {
            const area = document.getElementById('rp-content-area');
            if (area) {
                area.innerHTML = this.reportContents[report.id];
                this.applyCodeHighlighting(area);
            }
            return;
        }

        try {
            const response = await fetch(`/api/v1/reports/${archName}/files/${report.filename}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            let htmlContent;
            if (report.type === 'mermaid') {
                const content = await response.text();
                const borderColor = report.color || 'var(--border-color)';
                htmlContent = `
                    <div style="display: flex; gap: 0.25rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
                        <button id="rp-diagram-zoom-in" class="btn-icon" title="Zoom In">🔍+</button>
                        <button id="rp-diagram-zoom-out" class="btn-icon" title="Zoom Out">🔍−</button>
                        <button id="rp-diagram-zoom-reset" class="btn-icon" title="Fit to Width">↺</button>
                        <button id="rp-diagram-fit-width" class="btn-icon" title="Fit to Width">↔️</button>
                        <button id="rp-diagram-fit-height" class="btn-icon" title="Fit to Height">↕️</button>
                    </div>
                    <div id="rp-diagram-container" style="padding: 1rem; background: var(--code-bg); overflow: auto; max-height: 70vh; border: 2px solid ${borderColor}; border-radius: 8px;">
                        <div class="mermaid" id="rp-diagram">${content}</div>
                    </div>
                `;
            } else if (report.type === 'json') {
                const data = await response.json();
                const jsonStr = JSON.stringify(data, null, 2);
                htmlContent = `
                    <div style="padding: 1rem; background: var(--code-bg); overflow: auto; max-height: 70vh; border-radius: 8px;">
                        <pre style="margin: 0; font-size: 0.8125rem;"><code class="language-json">${this.escapeHtml(jsonStr)}</code></pre>
                    </div>
                `;
            } else {
                const text = await response.text();
                const rendered = window.marked ? marked.parse(text) : `<pre style="white-space: pre-wrap;">${this.escapeHtml(text)}</pre>`;
                htmlContent = `<div class="markdown-content" style="line-height: 1.7; color: var(--text-color);">${rendered}</div>`;
            }

            if (report.type !== 'mermaid') this.reportContents[report.id] = htmlContent;

            const area = document.getElementById('rp-content-area');
            if (!area) return;
            area.innerHTML = htmlContent;

            if (report.type === 'mermaid' && window.mermaid) {
                await new Promise(r => setTimeout(r, 100));
                const el = document.getElementById('rp-diagram');
                if (el) {
                    await mermaid.run({ nodes: [el] });
                    await new Promise(r => setTimeout(r, 100));
                    this.setupDiagramZoom('rp-diagram');
                }
            } else {
                this.applyCodeHighlighting(area);
            }
        } catch (error) {
            console.error('Report render error:', error);
            const area = document.getElementById('rp-content-area');
            if (area) area.innerHTML = `<div style="color: var(--danger-color);">⚠️ Failed to load: ${error.message}</div>`;

        }
    }

    applyCodeHighlighting(container) {
        if (window.hljs) {
            container.querySelectorAll('pre code').forEach(block => {
                hljs.highlightBlock(block);
            });
        }
    }

    // Return the button-row HTML for a given ERP state: 'idle' | 'running' | 'paused'
    _erpButtonRowHtml(archName, erpState) {
        if (erpState === 'running') {
            return `<div id="erp-btn-row" style="display:inline-flex; align-items:center; gap:0.6rem; margin-bottom:1.5rem; flex-wrap:wrap; justify-content:center;">
                <button id="run-expert-review-btn" disabled
                    style="background:var(--primary-color); color:#fff; border:none; border-radius:8px;
                           padding:0.75rem 1.75rem; font-size:0.9375rem; font-weight:600; cursor:default; opacity:0.6;">
                    Running…
                </button>
                <button id="pause-expert-review-btn" onclick="window.dashboard._pauseExpertReview()"
                    style="background:transparent; color:var(--warning-color); border:1px solid var(--warning-color);
                           border-radius:6px; padding:0.35rem 0.9rem; font-size:0.8125rem; font-weight:600; cursor:pointer;">
                    ⏸ Pause
                </button>
                <button id="cancel-expert-review-btn" onclick="window.dashboard._cancelExpertReview()"
                    style="background:transparent; color:var(--danger-color); border:1px solid var(--danger-color);
                           border-radius:6px; padding:0.35rem 0.9rem; font-size:0.8125rem; font-weight:600; cursor:pointer;">
                    ✕ Cancel
                </button>
            </div>`;
        }
        if (erpState === 'paused') {
            return `<div id="erp-btn-row" style="display:inline-flex; align-items:center; gap:0.6rem; margin-bottom:1.5rem; flex-wrap:wrap; justify-content:center;">
                <button id="run-expert-review-btn" onclick="window.dashboard._resumeExpertReview()"
                    style="background:var(--primary-color); color:#fff; border:none; border-radius:8px;
                           padding:0.75rem 1.75rem; font-size:0.9375rem; font-weight:600; cursor:pointer;">
                    ▶ Resume
                </button>
                <button id="cancel-expert-review-btn" onclick="window.dashboard._cancelExpertReview()"
                    style="background:transparent; color:var(--danger-color); border:1px solid var(--danger-color);
                           border-radius:6px; padding:0.35rem 0.9rem; font-size:0.8125rem; font-weight:600; cursor:pointer;">
                    ✕ Cancel
                </button>
            </div>`;
        }
        // idle
        return `<div id="erp-btn-row" style="display:flex; flex-direction:column; align-items:center; gap:0.75rem; margin-bottom:1.5rem;">
            <div style="display:flex; align-items:center; gap:0.5rem; font-size:0.8125rem; color:var(--text-secondary);">
                <label for="erp-mode-select" style="font-weight:600; white-space:nowrap;">Critic Mode:</label>
                <select id="erp-mode-select"
                    style="background:#1e1e2e; color:#e2e8f0; border:1px solid var(--border-color);
                           border-radius:6px; padding:0.3rem 0.6rem; font-size:0.8125rem; cursor:pointer;"
                    onchange="window.dashboard._erpShowModeHint(this.value)">
                    <option value="sequential" selected style="background:#1e1e2e; color:#e2e8f0;">Sequential (Recommended)</option>
                    <option value="auto" style="background:#1e1e2e; color:#e2e8f0;">Auto (Complexity-Adaptive)</option>
                    <option value="parallel" style="background:#1e1e2e; color:#e2e8f0;">Parallel (Fast)</option>
                </select>
                <div id="erp-mode-hint" style="max-width:380px; margin-top:0.5rem; padding:0.5rem 0.75rem; border-radius:6px;
                     background:var(--nav-hover-bg); border:1px solid var(--border-color); font-size:0.75rem; color:var(--text-secondary); text-align:left;"></div>
            </div>
            <div style="display:inline-flex; align-items:center; gap:0.6rem; flex-wrap:wrap; justify-content:center;">
                <button id="run-expert-review-btn" onclick="window.dashboard.runExpertReview('${archName}')"
                    style="background:var(--primary-color); color:#fff; border:none; border-radius:8px;
                           padding:0.75rem 1.75rem; font-size:0.9375rem; font-weight:600; cursor:pointer;">
                    Run Expert Review (~90 s)
                </button>
            </div>
        </div>`;
    }

    // Swap the button row in-place without re-rendering the whole shell
    _syncErpButtons(archName, erpState) {
        const row = document.getElementById('erp-btn-row');
        if (row) row.outerHTML = this._erpButtonRowHtml(archName, erpState);
    }

    // Build the progress UI shell — idle / running / paused states
    _erpProgressShell(archName, erpState) {
        const isActive = erpState === 'running' || erpState === 'paused';
        const heading = erpState === 'running' ? 'Expert Review Running…'
                      : erpState === 'paused'  ? 'Expert Review Paused'
                      : 'Expert Review Not Run';
        const subtitle = erpState === 'running' ? 'Analysis is in progress. Results appear as each critic finishes.'
                       : erpState === 'paused'  ? 'Analysis is paused. Previously completed critics are saved. Resume to continue from where it stopped.'
                       : 'The expert panel (Architecture Review, Coverage Audit, Exploit Analysis) has not reviewed this assessment yet. Running it adjusts confidence from the Foundation Score and unlocks the Improvement Roadmap.';
        const progressDisplay = isActive ? 'block' : 'none';
        // Parallel/auto mode uses per-critic bars instead of a single sequential bar
        const parallelMode = this._erpState && (this._erpState.criticMode === 'parallel' || this._erpState.criticMode === 'auto');
        const progressBarHtml = parallelMode ? `
            <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                <span id="erp-stage-label" style="font-size:0.875rem; color:var(--text-secondary);">Parallel critics running…</span>
                <span id="erp-pct" style="font-size:0.875rem; font-weight:600; color:var(--primary-color);">0%</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:0.35rem; margin-bottom:0.5rem;">
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <span style="font-size:0.7rem; width:58px; color:var(--text-tertiary);">🏛️ Architect</span>
                    <div style="flex:1; background:var(--nav-hover-bg); border-radius:3px; height:5px; overflow:hidden;"><div id="erp-bar-architect" style="height:100%; width:0%; background:var(--primary-color); transition:width 0.4s ease;"></div></div>
                    <span id="erp-pct-architect" style="font-size:0.65rem; width:28px; color:var(--text-tertiary); text-align:right;">0%</span>
                </div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <span style="font-size:0.7rem; width:58px; color:var(--text-tertiary);">🔬 Tester</span>
                    <div style="flex:1; background:var(--nav-hover-bg); border-radius:3px; height:5px; overflow:hidden;"><div id="erp-bar-tester" style="height:100%; width:0%; background:var(--primary-color); transition:width 0.4s ease;"></div></div>
                    <span id="erp-pct-tester" style="font-size:0.65rem; width:28px; color:var(--text-tertiary); text-align:right;">0%</span>
                </div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <span style="font-size:0.7rem; width:58px; color:var(--text-tertiary);">🎯 Red Team</span>
                    <div style="flex:1; background:var(--nav-hover-bg); border-radius:3px; height:5px; overflow:hidden;"><div id="erp-bar-red_team" style="height:100%; width:0%; background:var(--primary-color); transition:width 0.4s ease;"></div></div>
                    <span id="erp-pct-red_team" style="font-size:0.65rem; width:28px; color:var(--text-tertiary); text-align:right;">0%</span>
                </div>
            </div>
            <!-- Single bar stub for synthesis phase (reuses erp-bar id) -->
            <div id="erp-synthesis-bar-row" style="display:none; flex-direction:column; gap:0.2rem; margin-bottom:0.3rem;">
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <span style="font-size:0.7rem; width:58px; color:var(--text-tertiary);">⚙️ Synthesis</span>
                    <div style="flex:1; background:var(--nav-hover-bg); border-radius:3px; height:5px; overflow:hidden;"><div id="erp-bar" style="height:100%; width:0%; background:var(--secondary-color); transition:width 0.4s ease;"></div></div>
                    <span id="erp-pct-synthesis" style="font-size:0.65rem; width:28px; color:var(--text-tertiary); text-align:right;">0%</span>
                </div>
            </div>` : `
            <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                <span id="erp-stage-label" style="font-size:0.875rem; color:var(--text-secondary);">Starting...</span>
                <span id="erp-pct" style="font-size:0.875rem; font-weight:600; color:var(--primary-color);">0%</span>
            </div>
            <div style="background:var(--nav-hover-bg); border-radius:4px; height:6px; overflow:hidden;">
                <div id="erp-bar" style="height:100%; width:0%; background:var(--primary-color); transition:width 0.4s ease;"></div>
            </div>`;
        return `
            <div style="text-align: center; padding: 3rem 2rem;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">🧑‍🏫</div>
                <h3 style="color: var(--text-color); margin-bottom: 0.75rem;">${heading}</h3>
                <p style="color: var(--text-secondary); max-width: 440px; margin: 0 auto 1.5rem;">${subtitle}</p>
                ${this._erpButtonRowHtml(archName, erpState)}
                <div id="expert-review-progress" style="display:${progressDisplay}; max-width: 520px; margin: 0 auto; text-align: left;">
                    <div style="background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border-color); padding: 1rem;">
                        ${progressBarHtml}
                        <div id="erp-message" style="font-size:0.8125rem; color:var(--text-tertiary); margin-top:0.5rem; min-height:1.2em;"></div>
                        <!-- Progressive agent status cards -->
                        <div style="display:flex; gap:0.5rem; margin-top:0.875rem; flex-wrap:wrap;">
                            <div id="erp-card-architect" style="flex:1; min-width:130px; padding:0.5rem 0.75rem; border-radius:6px; border:1px solid var(--border-color); background:var(--nav-hover-bg); opacity:0.45; transition:opacity 0.3s, border-color 0.3s;">
                                <div style="font-size:0.875rem;">🏛️</div>
                                <div style="font-size:0.75rem; font-weight:600; color:var(--text-color); margin-top:0.2rem;">Architect</div>
                                <div id="erp-card-architect-status" style="font-size:0.7rem; color:var(--text-tertiary);">Waiting</div>
                                <div id="erp-card-architect-preview" style="display:none; margin-top:0.35rem; font-size:0.65rem; color:var(--text-tertiary); line-height:1.4;"></div>
                            </div>
                            <div id="erp-card-tester" style="flex:1; min-width:130px; padding:0.5rem 0.75rem; border-radius:6px; border:1px solid var(--border-color); background:var(--nav-hover-bg); opacity:0.45; transition:opacity 0.3s, border-color 0.3s;">
                                <div style="font-size:0.875rem;">🔬</div>
                                <div style="font-size:0.75rem; font-weight:600; color:var(--text-color); margin-top:0.2rem;">Tester</div>
                                <div id="erp-card-tester-status" style="font-size:0.7rem; color:var(--text-tertiary);">Waiting</div>
                                <div id="erp-card-tester-preview" style="display:none; margin-top:0.35rem; font-size:0.65rem; color:var(--text-tertiary); line-height:1.4;"></div>
                            </div>
                            <div id="erp-card-red_team" style="flex:1; min-width:130px; padding:0.5rem 0.75rem; border-radius:6px; border:1px solid var(--border-color); background:var(--nav-hover-bg); opacity:0.45; transition:opacity 0.3s, border-color 0.3s;">
                                <div style="font-size:0.875rem;">🎯</div>
                                <div style="font-size:0.75rem; font-weight:600; color:var(--text-color); margin-top:0.2rem;">Red Team</div>
                                <div id="erp-card-red_team-status" style="font-size:0.7rem; color:var(--text-tertiary);">Waiting</div>
                                <div id="erp-card-red_team-preview" style="display:none; margin-top:0.35rem; font-size:0.65rem; color:var(--text-tertiary); line-height:1.4;"></div>
                            </div>
                            <div id="erp-card-synthesis" style="flex:1; min-width:130px; padding:0.5rem 0.75rem; border-radius:6px; border:1px solid var(--border-color); background:var(--nav-hover-bg); opacity:0.45; transition:opacity 0.3s, border-color 0.3s;">
                                <div style="font-size:0.875rem;">⚙️</div>
                                <div style="font-size:0.75rem; font-weight:600; color:var(--text-color); margin-top:0.2rem;">Synthesis</div>
                                <div id="erp-card-synthesis-status" style="font-size:0.7rem; color:var(--text-tertiary);">Waiting</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div id="expert-review-error" style="display:none; color:var(--danger-color); font-size:0.875rem; margin-top:1rem; max-width:440px; margin-left:auto; margin-right:auto;"></div>
            </div>
            <!-- Progressive critic details rendered here as each critic completes -->
            <div id="erp-live-results" style="max-width:700px; margin:1.5rem auto 0; text-align:left;"></div>`;
    }

    // Re-apply in-progress state to the freshly rendered progress UI cards
    _erpRestoreState() {
        const s = this._erpState;
        if (!s) return;
        const pct = document.getElementById('erp-pct');
        const stageLabel = document.getElementById('erp-stage-label');
        const message = document.getElementById('erp-message');
        const stageMap = { architect: '🏛️ Architect', tester: '🔬 Tester', red_team: '🎯 Red Team', synthesis: '⚙️ Synthesis', complete: '✅ Done' };
        const parallelModeR = s.criticMode === 'parallel' || s.criticMode === 'auto';
        if (parallelModeR) {
            if (pct) pct.textContent = (s.pct || 0) + '%';
            if (stageLabel) stageLabel.textContent = s.stage === 'synthesis' ? '⚙️ Synthesising…' : 'Parallel critics running…';
            // Restore per-critic bars from cardStates
            for (const c of ['architect', 'tester', 'red_team']) {
                const cs = s.cardStates && s.cardStates[c];
                const cBar = document.getElementById('erp-bar-' + c);
                const cPct = document.getElementById('erp-pct-' + c);
                if (cs && cs.isCriticResult) {
                    if (cBar) { cBar.style.width = '100%'; cBar.style.background = cs.statusColor; }
                    if (cPct) { cPct.textContent = '✓'; cPct.style.color = cs.statusColor; }
                } else {
                    if (cBar) cBar.style.width = '5%';
                    if (cPct) cPct.textContent = '5%';
                }
            }
            if (s.stage === 'synthesis') {
                const synthRow = document.getElementById('erp-synthesis-bar-row');
                if (synthRow) synthRow.style.display = 'flex';
                const bar = document.getElementById('erp-bar');
                if (bar) bar.style.width = (s.pct || 0) + '%';
            }
        } else {
            const bar = document.getElementById('erp-bar');
            if (bar) bar.style.width = (s.pct || 0) + '%';
            if (pct) pct.textContent = (s.pct || 0) + '%';
            if (stageLabel) stageLabel.textContent = stageMap[s.stage] || (s.stage || 'Starting...');
        }
        if (message) message.textContent = s.message || '';
        // Restore each critic card from saved cardStates
        const agentOrder = ['architect', 'tester', 'red_team', 'synthesis'];
        for (const agent of agentOrder) {
            const cs = s.cardStates && s.cardStates[agent];
            if (!cs) continue;
            const card = document.getElementById('erp-card-' + agent);
            const statusEl = document.getElementById('erp-card-' + agent + '-status');
            const previewEl = document.getElementById('erp-card-' + agent + '-preview');
            if (!card || !statusEl) continue;
            card.style.opacity = cs.opacity;
            card.style.borderColor = cs.borderColor;
            statusEl.innerHTML = cs.statusHtml;
            statusEl.style.color = cs.statusColor;
            if (previewEl && cs.previewHtml) {
                previewEl.innerHTML = cs.previewHtml;
                previewEl.style.display = 'block';
            }
        }
        // Restore progressive live results
        const liveEl = document.getElementById('erp-live-results');
        if (liveEl && s.liveResults && s.liveResults.length > 0) {
            liveEl.innerHTML = s.liveResults.join('');
        }
    }

    // Pause: abort the SSE stream but keep _erpState so the user can resume
    _pauseExpertReview() {
        const s = this._erpState;
        if (!s || s.status !== 'running') return;
        if (s.abortController) s.abortController.abort();
        s.status = 'paused';
        s.abortController = null;
        s.message = 'Paused — click Resume to continue from where it stopped.';
        this._syncErpButtons(s.archName, 'paused');
        // Update stage label if visible
        const stageLabel = document.getElementById('erp-stage-label');
        if (stageLabel) stageLabel.textContent = '⏸ Paused';
        const msgEl = document.getElementById('erp-message');
        if (msgEl) msgEl.textContent = s.message;
    }

    // Resume: start a new SSE fetch — orchestrator will load saved critics from disk
    _resumeExpertReview() {
        const s = this._erpState;
        if (!s || s.status !== 'paused') return;
        const archName = s.archName;
        // Re-wire a new AbortController and reset status to running
        s.abortController = new AbortController();
        s.status = 'running';
        this._syncErpButtons(archName, 'running');
        // Re-launch the SSE pump — re-uses existing _erpState so card/live state is preserved
        this._launchErpFetch(archName);
    }

    // Cancel: abort the SSE stream AND purge partial files
    async _cancelExpertReview() {
        const s = this._erpState;
        if (!s) return;
        if (s.abortController) s.abortController.abort();
        const archName = s.archName;
        this._clearErpTimers();
        this._erpState = null;

        // Delete partial critic files so a fresh run starts clean
        if (archName) {
            const apiKey = localStorage.getItem('tm_api_key') || '';
            try {
                await fetch(`/api/v1/expert-review/cancel?architecture_name=${encodeURIComponent(archName)}`, {
                    method: 'DELETE',
                    headers: { 'TM-API-KEY': apiKey }
                });
            } catch (_) {}
        }

        // Re-render tab to idle state
        this.loadExpertReviewTab();
    }

    async _rerunMoE(archName, mode) {
        const apiKey = localStorage.getItem('tm_api_key') || '';
        // Purge existing MoE critic + orchestrator files so the pipeline runs fresh
        try {
            await fetch(`/api/v1/expert-review/cancel?architecture_name=${encodeURIComponent(archName)}`, {
                method: 'DELETE',
                headers: { 'TM-API-KEY': apiKey }
            });
        } catch (_) {}
        // Sync the main mode selector if it exists, then kick off the run
        const mainSel = document.getElementById('erp-mode-select');
        if (mainSel) mainSel.value = mode;
        this._erpState = null;
        this.runExpertReview(archName, mode);
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

        // If a run is in-progress or paused for this architecture, restore the progress UI
        if (this._erpState && (this._erpState.status === 'running' || this._erpState.status === 'paused') && this._erpState.archName === archName) {
            container.innerHTML = this._erpProgressShell(archName, this._erpState.status);
            this._erpRestoreState();
            return;
        }

        container.innerHTML = '<p class="placeholder">Loading expert review data...</p>';

        try {
            const response = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (!response.ok) {
                container.innerHTML = this._erpProgressShell(archName, 'idle');
                this._erpShowModeHint('sequential');
                return;
            }

            const moe = await response.json();
            const confidence = moe.confidence || {};
            const expertValidations = moe.expert_validations || {};
            const consensusRecsRaw = moe.consensus_recommendations || {};
            const consensusCritical = Array.isArray(consensusRecsRaw.critical) ? consensusRecsRaw.critical : [];
            const consensusHigh = Array.isArray(consensusRecsRaw.high) ? consensusRecsRaw.high : [];
            const consensusReview = Array.isArray(consensusRecsRaw.review) ? consensusRecsRaw.review : [];
            const blindspots = Array.isArray(consensusRecsRaw.blindspots) ? consensusRecsRaw.blindspots : [];
            const contradictions = Array.isArray(consensusRecsRaw.contradictions) ? consensusRecsRaw.contradictions : [];
            const synthQuality = consensusRecsRaw.synthesis_quality || '';
            const improvTiers = moe.improvement_options || {};
            const synthComment = consensusRecsRaw.confidence_commentary || '';
            const isFallback = synthQuality === 'FALLBACK';
            const synthBorderColor = isFallback ? 'var(--warning-color)' : 'var(--border-color)';
            const runCriticMode = moe.critic_mode || 'sequential';
            const isParallelResult = runCriticMode === 'parallel' || runCriticMode === 'partial_parallel';

            // Build blindspots HTML
            let blindspotsHtml = '';
            if (blindspots.length > 0) {
                let cards = '';
                for (const b of blindspots) {
                    cards += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--primary-color);">'
                        + '<div style="font-size: 0.875rem; font-weight:600; color: var(--text-color);">' + (b.description || '') + '</div>'
                        + (b.why_missed ? '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-top:0.25rem;">Why missed: ' + b.why_missed + '</div>' : '')
                        + (b.recommendation ? '<div style="font-size:0.8125rem; color:var(--secondary-color); margin-top:0.25rem;">→ ' + b.recommendation + '</div>' : '')
                        + '</div>';
                }
                blindspotsHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                    + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">🔍 Blindspots</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">Gaps all three critics structurally could not see — highest priority for human review.</p></div>'
                    + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;">∨</span>'
                    + '</div>'
                    + '<div class="er-panel-body" style="padding: 0 1.25rem 1.25rem;">' + cards + '</div>'
                    + '</div>';
            }

            // Build contradictions HTML — summary cards with right-pane detail on click
            const rootCauseLabel = {
                SCOPE_MISMATCH: '🔭 Scope mismatch',
                DATA_REFERENCE_ERROR: '🗂️ Data reference error',
                CONFIDENCE_DIFFERENCE: '🎲 Confidence difference',
                GENUINE_DISAGREEMENT: '⚔️ Genuine disagreement',
            };
            // Stash contradiction data for right-pane access from onclick
            window._erContradictions = contradictions;

            let contradictionsHtml = '';
            if (contradictions.length > 0) {
                let cards = '';
                for (let ci = 0; ci < contradictions.length; ci++) {
                    const c = contradictions[ci];
                    const causeKey = c.disagreement_root_cause || '';
                    const causeTag = causeKey
                        ? '<span style="font-size:0.7rem; font-weight:700; color:var(--primary-color); background:var(--primary-color)18; border:1px solid var(--primary-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">' + (rootCauseLabel[causeKey] || causeKey) + '</span>'
                        : '';
                    const hasDetail = !!(c.root_cause_explanation || c.human_action);
                    cards += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--warning-color);">'
                        + '<div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem; margin-bottom:0.4rem;">'
                        + '<div style="font-size: 0.875rem; font-weight:600; color: var(--text-color); display:flex; align-items:baseline; flex-wrap:wrap; gap:0.2rem;">' + (c.topic || '') + causeTag + '</div>'
                        + (hasDetail ? '<button onclick="window.dashboard._showContradictionDetail(' + ci + ')" style="flex-shrink:0; font-size:0.75rem; color:var(--primary-color); background:transparent; border:1px solid var(--primary-color)44; border-radius:6px; padding:2px 8px; cursor:pointer; white-space:nowrap;">View analysis →</button>' : '')
                        + '</div>'
                        + '<div style="font-size:0.8125rem; color:var(--text-secondary);">🏛️ Architect/Tester: ' + (c.architect_view || '') + '</div>'
                        + '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-top:0.2rem;">🎯 Red Team: ' + (c.tester_or_redteam_view || '') + '</div>'
                        + '<div style="font-size:0.8125rem; color:var(--warning-color); margin-top:0.35rem; font-style:italic;">' + (c.resolution || 'UNSURE — human review needed') + '</div>'
                        + '</div>';
                }
                contradictionsHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                    + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">⚠️ Expert Disagreements</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">Where critics contradict each other. Click <em>View analysis →</em> for root cause.</p></div>'
                    + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;">∨</span>'
                    + '</div>'
                    + '<div class="er-panel-body" style="padding: 0 1.25rem 1.25rem;">' + cards + '</div>'
                    + '</div>';
            } else {
                if (isParallelResult) {
                    // Parallel mode: contradiction detection is structurally N/A — grey out the panel
                    contradictionsHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden; opacity:0.55;">'
                        + '<div style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center;">'
                        + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-tertiary); font-size: 1rem;">— Expert Disagreements (N/A)</h3>'
                        + '<p style="font-size: 0.875rem; color: var(--text-tertiary); margin: 0;">Not applicable — <strong>' + runCriticMode + '</strong> mode critics ran independently and did not read each other\'s output. Cross-critic disagreement detection requires Sequential mode.</p></div>'
                        + '</div>'
                        + '</div>';
                } else {
                    // Sequential / auto-resolved-sequential: genuine consensus
                    const modeLabel = runCriticMode === 'auto' ? 'Auto (resolved to Sequential)' : 'Sequential';
                    contradictionsHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                        + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                        + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">✅ Expert Disagreements</h3>'
                        + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">No contradictions found.</p></div>'
                        + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;"> ⌄</span>'
                        + '</div>'
                        + '<div class="er-panel-body" style="padding: 0.75rem 1.25rem 1rem;">'
                        + '<div style="padding:0.65rem 1rem; background:var(--secondary-color)14; border:1px solid var(--secondary-color)44; border-radius:8px; font-size:0.875rem; color:var(--secondary-color);">All three critics read each other\'s output and found no conflicting positions — this is genuine consensus.</div>'
                        + '<div style="margin-top:0.5rem; font-size:0.8125rem; color:var(--text-tertiary);">Mode used: <strong>' + modeLabel + '</strong>. Critics did cross-reference each other, so this absence reflects actual agreement.</div>'
                        + '</div></div>';
                }
            }

            // Build synthesis footer outside template literal
            let synthFooterHtml = '';
            if (synthComment || isFallback) {
                synthFooterHtml = '<div style="background: var(--card-bg); border-radius: 10px; padding: 1rem 1.25rem; border: 1px solid ' + synthBorderColor + ';">'
                    + (synthComment ? '<span style="font-size:0.8125rem; color:var(--text-secondary); font-style:italic;">' + synthComment + '</span>' : '')
                    + (isFallback ? '<div style="font-size:0.8125rem; color:var(--warning-color); margin-top:0.25rem;">⚠ Synthesis used fallback — LLM was unavailable. Consensus is a gap union, not a reasoned cross-validation.</div>' : '')
                    + '</div>';
            }

            // Build improvement tier HTML outside template literal to avoid deep nesting
            const tierDefs = [
                { key: 'quick_wins',  label: '⚡ Quick Win',      color: 'var(--secondary-color)' },
                { key: 'recommended', label: '⭐ Recommended',    color: 'var(--primary-color)'   },
                { key: 'maximum',     label: '🔒 Maximum',        color: 'var(--warning-color)'   },
            ];
            let tiersHtml = '';
            if (Object.keys(improvTiers).length > 0) {
                let tierCards = '';
                for (const { key, label, color } of tierDefs) {
                    const t = improvTiers[key];
                    if (!t) continue;
                    const items = Array.isArray(t.items) ? t.items : [];
                    const itemList = items.length > 0
                        ? '<ul style="margin:0.5rem 0 0; padding-left:1.25rem; font-size:0.8125rem; color:var(--text-color);">' + items.map(function(i) { return '<li>' + i + '</li>'; }).join('') + '</ul>'
                        : '';
                    const residualBlock = t.residual
                        ? '<div style="margin-top:0.5rem; padding:0.5rem; background:rgba(255,165,0,0.08); border-radius:4px; font-size:0.8125rem; color:var(--warning-color);">Residual: ' + t.residual + '</div>'
                        : '';
                    const rationaleBlock = t.rationale
                        ? '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:0.5rem; font-style:italic;">' + t.rationale + '</div>'
                        : '';
                    tierCards += '<div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem;">'
                        + '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">'
                        + '<span style="font-weight:700; color:' + color + ';">' + label + '</span>'
                        + '<span style="font-size:0.8125rem; color:var(--text-secondary);">' + (t.practical_verdict ? 'Practical: ' + t.practical_verdict : '') + '</span>'
                        + '</div>'
                        + rationaleBlock
                        + '<div style="display:grid; grid-template-columns:1fr 1fr; gap:0.5rem; font-size:0.8125rem; margin-bottom:0.5rem;">'
                        + '<div><span style="color:var(--text-tertiary);">Cost:</span> ' + (t.cost || 'cost not estimated') + '</div>'
                        + '<div><span style="color:var(--text-tertiary);">Effort:</span> ' + (t.effort || 'not estimated') + '</div>'
                        + '<div><span style="color:var(--text-tertiary);">Attacker score ↓:</span> ' + (t.risk_reduction || '—').replace(/\s*\(.*\)/, '').trim() + ' <span style="font-size:0.7rem; color:var(--text-tertiary);">(lower = harder to exploit)</span></div>'
                        + '</div>'
                        + itemList
                        + residualBlock
                        + this._renderSspTierUpgradeDelta(items, label)
                        + '</div>';
                }
                tiersHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                    + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">📊 Improvement Tiers</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">Cost and effort from Red Team exploit roadmap — not estimated where data is absent.</p></div>'
                    + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;">∨</span>'
                    + '</div>'
                    + '<div class="er-panel-body" style="padding: 0 1.25rem 1.25rem;">' + tierCards + '</div>'
                    + '</div>';
            }

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

            // Legend text and severity helpers
            const statusDesc = {
                'PASS': 'No significant issues — controls and mappings verified',
                'MINOR_GAPS': 'Small gaps found — low exploitability risk',
                'MAJOR_GAPS': 'Significant issues found — high exploitability risk',
                'FAIL': 'Critical failures — immediate action required',
                'UNKNOWN': 'Status unavailable',
            };
            const severityColor = {
                'CRITICAL': 'var(--danger-color)',
                'HIGH':     'var(--danger-color)',
                'MEDIUM':   'var(--warning-color)',
                'MINOR':    'var(--primary-color)',  // blue = slight concern, investigate
                'LOW':      'var(--text-tertiary)',
            };
            const severityLegend = '<div style="display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.75rem; padding:0.5rem 0.75rem; background:var(--nav-hover-bg); border-radius:6px;">'
                + '<span style="font-size:0.7rem; color:var(--text-tertiary); margin-right:0.25rem; align-self:center;">Severity:</span>'
                + '<span style="font-size:0.7rem; color:var(--danger-color);">● CRITICAL — exploitable, act now</span>'
                + '<span style="font-size:0.7rem; color:var(--danger-color); margin-left:0.5rem;">● HIGH — significant risk</span>'
                + '<span style="font-size:0.7rem; color:var(--warning-color); margin-left:0.5rem;">● MEDIUM — moderate concern</span>'
                + '<span style="font-size:0.7rem; color:var(--primary-color); margin-left:0.5rem;">● MINOR — slight concern, investigate</span>'
                + '<span style="font-size:0.7rem; color:var(--text-tertiary); margin-left:0.5rem;">● LOW — informational</span>'
                + '</div>';

            const finalConf = (confidence.final || 0).toFixed(1);
            const baseConf  = (confidence.base  || 99.5).toFixed(1);
            const interp    = confidence.interpretation || '';

            // Build confidence waterfall nodes
            let waterfallNodes = '';
            for (const e of expertDefs) {
                const v = expertValidations[e.key];
                if (!v) continue;
                const adjNum = parseFloat(((v.confidence_adjustment || 0) * 100).toFixed(1));
                const adjWfLabel = adjNum === 0 ? '±0%' : (adjNum > 0 ? '+' : '') + adjNum + '%';
                const adjWfColor = adjNum < 0 ? 'var(--warning-color)' : adjNum === 0 ? 'var(--text-tertiary)' : 'var(--secondary-color)';
                waterfallNodes += '<div style="color: var(--text-tertiary); font-size: 1.25rem;">→</div>'
                    + '<div style="text-align: center; min-width: 80px;">'
                    + '<div style="font-size: 1rem; font-weight: 600; color: ' + adjWfColor + ';">' + adjWfLabel + '</div>'
                    + '<div style="font-size: 0.75rem; color: var(--text-secondary);">' + e.label + '</div>'
                    + '</div>';
            }

            // Build expert panel cards — collapsible, expanded by default
            let expertPanelCards = '';
            for (const e of expertDefs) {
                const v = expertValidations[e.key];
                if (!v) continue;
                const adjNum2 = parseFloat(((v.confidence_adjustment || 0) * 100).toFixed(1));
                const adj = adjNum2 === 0 ? '±0' : (adjNum2 > 0 ? '+' : '') + adjNum2;
                const sign = '';
                const status = v.validation_status || 'UNKNOWN';
                const color = statusColor[status] || 'var(--text-secondary)';
                const gapCount = (v.gaps || []).length;
                const statusText = status.replace(/_/g, ' ') + (status === 'PASS' && gapCount > 0 ? ` (${gapCount} low finding${gapCount > 1 ? 's' : ''})` : '');
                const statusExplain = statusDesc[status] || '';
                const gaps = v.gaps || [];
                let gapItems = '';
                for (const g of gaps) {
                    const sev = (g.severity || '').toUpperCase();
                    const borderCol = severityColor[sev] || 'var(--border-color)';
                    const sevCol = severityColor[sev] || 'var(--text-tertiary)';
                    gapItems += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid ' + borderCol + ';">'
                        + '<div style="font-size: 0.8125rem; font-weight: 600; color: var(--text-color); margin-bottom: 0.25rem;">' + (g.category ? g.category.replace(/_/g, ' ').toUpperCase() : '') + ' · <span style="color: ' + sevCol + ';">' + (g.severity || '') + '</span></div>'
                        + '<div style="font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.5rem;">' + (g.description || '') + '</div>'
                        + (g.recommendation ? '<div style="font-size: 0.8125rem; color: var(--secondary-color);">→ ' + g.recommendation + '</div>' : '')
                        + '</div>';
                }
                // Sub-dimension breakdown (tester only) — compact score chips + gaps-only reasoning
                let breakdownBars = '';
                if (e.key === 'tester' && v.breakdown && Object.keys(v.breakdown).length > 0) {
                    const subLabels = {
                        validation_checks:    'Validation',
                        coverage_metrics:     'Coverage',
                        internal_consistency: 'Consistency',
                        roadmap_validation:   'Roadmap',
                    };
                    // Score chips row
                    let chips = '';
                    let gapNotes = '';
                    for (const [subKey, subData] of Object.entries(v.breakdown)) {
                        if (typeof subData !== 'object' || !subData.max) continue;
                        const pct = Math.round((subData.score / subData.max) * 100);
                        const chipColor = pct < 50 ? 'var(--danger-color)' : pct < 75 ? 'var(--warning-color)' : 'var(--secondary-color)';
                        chips += '<span title="' + (subLabels[subKey] || subKey) + ': ' + subData.score + '/' + subData.max + '" '
                            + 'style="display:inline-flex; align-items:center; gap:0.25rem; font-size:0.75rem; padding:2px 8px; border-radius:10px; background:' + chipColor + '18; border:1px solid ' + chipColor + '44; color:' + chipColor + '; font-weight:600; white-space:nowrap;">'
                            + (subLabels[subKey] || subKey) + ' <span style="color:var(--text-color);">' + subData.score + '/' + subData.max + '</span>'
                            + '</span>';
                        // Only show reasoning for dims that lost points
                        if (pct < 100 && subData.reasoning) {
                            // Extract first sentence — the "why it's not full"
                            const firstSentence = subData.reasoning.split(/\.\s+/)[0].replace(/^(All|No |The )/i, s => s).trim();
                            if (firstSentence.length > 10) {
                                gapNotes += '<div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:0.25rem;">'
                                    + '<span style="color:' + chipColor + '; font-weight:600;">' + (subLabels[subKey] || subKey) + ':</span> '
                                    + firstSentence + (firstSentence.endsWith('.') ? '' : '.')
                                    + '</div>';
                            }
                        }
                    }
                    breakdownBars = '<div style="margin-bottom:0.75rem; padding:0.65rem 0.75rem; background:var(--nav-hover-bg); border-radius:6px;">'
                        + '<div style="display:flex; align-items:center; gap:0.35rem; flex-wrap:wrap; margin-bottom:' + (gapNotes ? '0.5rem' : '0') + ';">'
                        + chips + '</div>'
                        + (gapNotes ? '<div style="border-top:1px solid var(--border-color); padding-top:0.4rem;">' + gapNotes + '</div>' : '')
                        + '</div>';
                }

                const bodyHtml = gaps.length > 0
                    ? '<div class="er-panel-body" style="padding: 1rem 1.25rem;">'
                        + breakdownBars
                        + '<div style="font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.5rem;">' + gaps.length + ' finding' + (gaps.length > 1 ? 's' : '') + '</div>'
                        + severityLegend
                        + '<div style="margin-top:0.75rem;">' + gapItems + '</div>'
                        + '</div>'
                    : '<div class="er-panel-body" style="padding: 0.75rem 1.25rem; font-size:0.8125rem; color:var(--text-tertiary);">'
                        + breakdownBars
                        + 'No findings — criteria passed.</div>';

                expertPanelCards += '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select:none;">'
                    + '<div style="display: flex; align-items: center; gap: 0.75rem;">'
                    + '<span style="font-size: 1.5rem;">' + e.icon + '</span>'
                    + '<div><div style="font-weight: 700; color: var(--text-color);">' + e.label + '</div>'
                    + '<div style="font-size: 0.8125rem; color: var(--text-secondary);">' + e.role + '</div></div>'
                    + '</div>'
                    + '<div style="display:flex; align-items:center; gap:1rem;">'
                    + '<div style="text-align: right;">'
                    + '<div style="font-size: 1.125rem; font-weight: 700; color: ' + (adjNum2 < 0 ? 'var(--warning-color)' : adjNum2 === 0 ? 'var(--text-tertiary)' : 'var(--secondary-color)') + ';">' + sign + adj + '%</div>'
                    + '<div style="font-size: 0.75rem; font-weight: 600; color: ' + color + ';" title="' + statusExplain + '">' + statusText + '</div>'
                    + '</div>'
                    + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;">∨</span>'
                    + '</div></div>'
                    + bodyHtml
                    + '</div>';
            }

            // Collapse-all/expand-all toggle
            const expertPanels = '<div style="display:flex; justify-content:flex-end; margin-bottom:0.5rem;">'
                + '<button id="er-collapse-all-btn" onclick="(function(btn){var panels=document.querySelectorAll(\'.er-panel-body\');var chevrons=document.querySelectorAll(\'.er-chevron\');var allOpen=[].every.call(panels,function(p){return p.style.display!==\'none\';});panels.forEach(function(p,i){p.style.display=allOpen?\'none\':\'block\';chevrons[i].textContent=allOpen?\'›\':\' ⌄\';});btn.textContent=allOpen?\'Expand all\':\'Collapse all\';})(this)" '
                + 'style="font-size:0.8125rem; color:var(--text-tertiary); background:transparent; border:1px solid var(--border-color); border-radius:6px; padding:0.25rem 0.75rem; cursor:pointer;">Collapse all</button>'
                + '</div>'
                + '<div style="display: flex; flex-direction: column; gap: 1rem;">' + expertPanelCards + '</div>';

            // Helper: derive KNOWN/UNSURE from item data (source with '+' = multi-critic = KNOWN)
            function isKnown(r) {
                if (r.confidence_label === 'KNOWN') return true;
                if (r.confidence_label === 'UNSURE') return false;
                // Fallback: source with '+' means multiple critics agreed
                return r.source && r.source.includes('+');
            }

            // Build consensus section — per-item KNOWN/UNSURE badge, not per-group header
            let consensusHtml = '';
            if (consensusCritical.length + consensusHigh.length + consensusReview.length > 0) {
                let inner = '';
                if (consensusCritical.length > 0) {
                    inner += '<div style="font-size:0.8125rem; font-weight:600; color:var(--danger-color); text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.5rem;">Critical</div>';
                    for (const r of consensusCritical) {
                        const known = isKnown(r);
                        const badge = known
                            ? '<span style="font-size:0.7rem; font-weight:700; color:var(--secondary-color); background:var(--secondary-color)18; border:1px solid var(--secondary-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">KNOWN</span>'
                            : '<span style="font-size:0.7rem; font-weight:700; color:var(--warning-color); background:var(--warning-color)18; border:1px solid var(--warning-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">UNSURE</span>';
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--danger-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-color); display:flex; align-items:baseline; flex-wrap:wrap; gap:0.2rem;">' + (r.description || r.recommendation || '') + badge + '</div>'
                            + (r.evidence ? '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.25rem;">Evidence: ' + r.evidence + '</div>' : '')
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary);">Source: ' + r.source + '</div>' : '')
                            + '</div>';
                    }
                }
                if (consensusHigh.length > 0) {
                    inner += '<div style="font-size:0.8125rem; font-weight:600; color:var(--warning-color); text-transform:uppercase; letter-spacing:0.04em; margin: 0.75rem 0 0.5rem;">High</div>';
                    for (const r of consensusHigh) {
                        const known = isKnown(r);
                        const badge = known
                            ? '<span style="font-size:0.7rem; font-weight:700; color:var(--secondary-color); background:var(--secondary-color)18; border:1px solid var(--secondary-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">KNOWN</span>'
                            : '<span style="font-size:0.7rem; font-weight:700; color:var(--warning-color); background:var(--warning-color)18; border:1px solid var(--warning-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">UNSURE</span>';
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--warning-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-color); display:flex; align-items:baseline; flex-wrap:wrap; gap:0.2rem;">' + (r.description || r.recommendation || '') + badge + '</div>'
                            + (r.evidence ? '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.25rem;">Evidence: ' + r.evidence + '</div>' : '')
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary);">Source: ' + r.source + '</div>' : '')
                            + '</div>';
                    }
                }
                if (consensusReview.length > 0) {
                    inner += '<div style="font-size:0.8125rem; font-weight:600; color:var(--text-tertiary); text-transform:uppercase; letter-spacing:0.04em; margin: 0.75rem 0 0.5rem;">For Review</div>';
                    for (const r of consensusReview) {
                        const known = isKnown(r);
                        const badge = known
                            ? '<span style="font-size:0.7rem; font-weight:700; color:var(--secondary-color); background:var(--secondary-color)18; border:1px solid var(--secondary-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">KNOWN</span>'
                            : '<span style="font-size:0.7rem; font-weight:700; color:var(--text-tertiary); background:var(--nav-hover-bg); border:1px solid var(--border-color); border-radius:8px; padding:1px 6px; margin-left:0.4rem;">UNSURE</span>';
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--border-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-secondary); display:flex; align-items:baseline; flex-wrap:wrap; gap:0.2rem;">' + (r.description || r.recommendation || '') + badge + '</div>'
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary);">Raised by: ' + r.source + '</div>' : '')
                            + '</div>';
                    }
                }
                consensusHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                    + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">Cross-Expert Findings</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">KNOWN = ≥2 critics agree. UNSURE = single critic, needs human verification.</p></div>'
                    + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;">∨</span>'
                    + '</div>'
                    + '<div class="er-panel-body" style="padding: 0 1.25rem 1.25rem;">' + inner + '</div>'
                    + '</div>';
            }

            const parallelWarningBanner = isParallelResult
                ? '<div style="background:var(--warning-color)12; border:1px solid var(--warning-color)55; border-radius:8px; padding:0.75rem 1rem; margin-bottom:1rem; display:flex; gap:0.625rem; align-items:flex-start;">'
                    + '<span style="font-size:1rem; flex-shrink:0;">⚠</span>'
                    + '<div style="font-size:0.8125rem; color:var(--text-color);">'
                    + '<strong>Parallel mode tradeoffs:</strong> Critics ran independently — Tester did not validate Architect\'s roadmap, Red Team did not adjust for MITRE mapping errors. '
                    + 'Cross-expert findings below are each critic\'s independent view, not cross-validated conclusions. '
                    + '<span style="color:var(--warning-color);">Re-run with Sequential mode for full cross-referencing.</span>'
                    + '</div></div>'
                : '';

            const rerunRowHtml = '<div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:1rem; padding:0.75rem 1rem; background:var(--card-bg); border:1px solid var(--border-color); border-radius:8px;">'
                + '<span style="font-size:0.8125rem; color:var(--text-secondary); flex:1;">Ran with: <strong style="color:var(--text-color);">'
                + runCriticMode.charAt(0).toUpperCase() + runCriticMode.slice(1)
                + '</strong> mode</span>'
                + '<label for="erp-rerun-mode-select" style="font-size:0.8125rem; font-weight:600; white-space:nowrap; color:var(--text-secondary);">Re-run as:</label>'
                + '<select id="erp-rerun-mode-select" style="font-size:0.8125rem; padding:0.2rem 0.4rem; border-radius:6px; border:1px solid var(--border-color); background:var(--input-bg,var(--card-bg)); color:var(--text-color); cursor:pointer;">'
                + '<option value="sequential"' + (runCriticMode === 'sequential' ? ' selected' : '') + '>Sequential</option>'
                + '<option value="auto"' + (runCriticMode === 'auto' ? ' selected' : '') + '>Auto</option>'
                + '<option value="parallel"' + (runCriticMode === 'parallel' || runCriticMode === 'partial_parallel' ? ' selected' : '') + '>Parallel</option>'
                + '</select>'
                + '<button onclick="(function(){var sel=document.getElementById(\'erp-rerun-mode-select\');var mode=sel?sel.value:\'sequential\';window.dashboard._rerunMoE(\'' + archName + '\',mode);})();"'
                + ' style="font-size:0.8125rem; padding:0.25rem 0.875rem; background:var(--primary-color); color:#fff; border:none; border-radius:6px; cursor:pointer; font-weight:600; white-space:nowrap;">▶ Re-run MoE</button>'
                + '</div>';

            container.innerHTML = ''
                + rerunRowHtml
                + parallelWarningBanner
                + '<div style="background: var(--card-bg); border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid var(--border-color);">'
                + '<h3 style="margin: 0 0 1rem; color: var(--text-color); font-size: 1rem;">Confidence Progression</h3>'
                + '<div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">'
                + '<div style="text-align: center; min-width: 80px;">'
                + '<div style="font-size: 1.25rem; font-weight: 700; color: var(--secondary-color);">' + baseConf + '%</div>'
                + '<div style="font-size: 0.75rem; color: var(--text-secondary);">Foundation</div>'
                + '</div>'
                + waterfallNodes
                + '<div style="color: var(--text-tertiary); font-size: 1.25rem;">→</div>'
                + '<div style="text-align: center; min-width: 80px;">'
                + '<div style="font-size: 1.25rem; font-weight: 700; color: var(--primary-color);">' + finalConf + '%</div>'
                + '<div style="font-size: 0.75rem; color: var(--text-secondary);">Validated</div>'
                + '</div></div>'
                + (interp ? '<p style="margin: 0.75rem 0 0; font-size: 0.875rem; color: var(--text-secondary);">' + interp + '</p>' : '')
                + '</div>'
                + '<div style="margin-bottom: 1.5rem;">' + expertPanels + '</div>'
                + consensusHtml
                + blindspotsHtml
                + contradictionsHtml
                + tiersHtml
                + synthFooterHtml;
        } catch (err) {
            container.innerHTML = `<p class="placeholder">Error loading expert review: ${err.message}</p>`;
        }
    }

    _showContradictionDetail(idx) {
        const c = (window._erContradictions || [])[idx];
        if (!c) return;

        const rootCauseLabel = {
            SCOPE_MISMATCH:        '🔭 Scope mismatch',
            DATA_REFERENCE_ERROR:  '🗂️ Data reference error',
            CONFIDENCE_DIFFERENCE: '🎲 Confidence difference',
            GENUINE_DISAGREEMENT:  '⚔️ Genuine disagreement',
        };
        const causeKey = c.disagreement_root_cause || '';
        const causeLabel = rootCauseLabel[causeKey] || causeKey;

        const content = ''
            + '<div style="margin-bottom:1.25rem;">'
            + '<div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.35rem;">Architect / Tester view</div>'
            + '<div style="font-size:0.875rem; color:var(--text-color); padding:0.6rem 0.75rem; background:var(--nav-hover-bg); border-radius:6px; border-left:3px solid var(--primary-color);">🏛️ ' + (c.architect_view || '') + '</div>'
            + '</div>'
            + '<div style="margin-bottom:1.25rem;">'
            + '<div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.35rem;">Red Team view</div>'
            + '<div style="font-size:0.875rem; color:var(--text-color); padding:0.6rem 0.75rem; background:var(--nav-hover-bg); border-radius:6px; border-left:3px solid var(--warning-color);">🎯 ' + (c.tester_or_redteam_view || '') + '</div>'
            + '</div>'
            + (causeKey ? '<div style="margin-bottom:1.25rem;">'
                + '<div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.35rem;">Root cause</div>'
                + '<div style="font-size:0.875rem; font-weight:600; color:var(--primary-color);">' + causeLabel + '</div>'
                + '</div>' : '')
            + (c.root_cause_explanation ? '<div style="margin-bottom:1.25rem;">'
                + '<div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.35rem;">Why they disagree</div>'
                + '<div style="font-size:0.875rem; color:var(--text-color); line-height:1.6;">' + c.root_cause_explanation + '</div>'
                + '</div>' : '')
            + (c.human_action ? '<div style="margin-bottom:1.25rem; padding:0.75rem; background:var(--secondary-color)12; border:1px solid var(--secondary-color)44; border-radius:8px;">'
                + '<div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; color:var(--secondary-color); margin-bottom:0.35rem;">Recommended human action</div>'
                + '<div style="font-size:0.875rem; color:var(--text-color);">→ ' + c.human_action + '</div>'
                + '</div>' : '')
            + '<div style="padding:0.5rem 0.75rem; background:var(--warning-color)12; border-radius:6px;">'
            + '<div style="font-size:0.8125rem; color:var(--warning-color); font-style:italic;">' + (c.resolution || 'UNSURE — human review needed') + '</div>'
            + '</div>';

        this.showRightPane('⚠️ ' + (c.topic || 'Disagreement'), content);
    }

    // Build a live critic result card HTML from a critic_result SSE event payload
    _buildLiveCriticCard(data) {
        const labels = { architect: '🏛️ Architect', tester: '🔬 Tester', red_team: '🎯 Red Team' };
        const roles  = { architect: 'Architecture Review', tester: 'Coverage Audit', red_team: 'Exploit Analysis' };
        const statusColor = data.status_color || 'var(--secondary-color)';
        const adjPct = parseFloat(data.confidence_adjustment_pct);
        const adjLabel = adjPct === 0 ? 'No adjustment' : (adjPct > 0 ? '+' : '') + adjPct + '% confidence';
        const adjColor = adjPct < 0 ? 'var(--warning-color)' : adjPct === 0 ? 'var(--text-tertiary)' : 'var(--secondary-color)';
        const statusText = (data.validation_status || '').replace(/_/g, ' ');
        const sevColor = { CRITICAL: 'var(--danger-color)', HIGH: 'var(--danger-color)', MEDIUM: 'var(--warning-color)', LOW: 'var(--text-tertiary)' };

        // Gap rows
        let gapRows = '';
        for (const g of (data.top_gaps || [])) {
            const sc = sevColor[(g.severity || '').toUpperCase()] || 'var(--text-tertiary)';
            gapRows += '<div style="padding:0.5rem 0.65rem; background:var(--bg-color); border-radius:5px; margin-bottom:0.35rem; border-left:3px solid ' + sc + ';">'
                + (g.severity ? '<span style="font-size:0.7rem; font-weight:700; color:' + sc + ';">' + g.severity + '</span> ' : '')
                + '<span style="font-size:0.8125rem; color:var(--text-secondary);">' + (g.description || '') + '</span>'
                + '</div>';
        }
        const moreGaps = data.gap_count > (data.top_gaps || []).length
            ? '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.25rem;">+ ' + (data.gap_count - (data.top_gaps || []).length) + ' more — full details after completion</div>'
            : '';

        // Strengths (compact, one line each)
        let strengthRows = '';
        for (const s of (data.top_strengths || [])) {
            strengthRows += '<div style="font-size:0.8rem; color:var(--secondary-color); margin-bottom:0.2rem;">✓ ' + s + '</div>';
        }

        return '<div style="background:var(--card-bg); border:1px solid ' + statusColor + '44; border-left:3px solid ' + statusColor + '; border-radius:8px; padding:0.875rem 1rem; margin-bottom:0.75rem;">'
            + '<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.5rem; flex-wrap:wrap; gap:0.25rem;">'
            + '<div style="font-weight:700; color:var(--text-color); font-size:0.9375rem;">' + (labels[data.critic] || data.critic) + ' <span style="font-weight:400; font-size:0.8125rem; color:var(--text-tertiary);">' + (roles[data.critic] || '') + '</span></div>'
            + '<div style="display:flex; align-items:center; gap:0.75rem; flex-shrink:0;">'
            + '<span style="font-size:0.8125rem; color:var(--text-secondary);">' + data.score + '/100</span>'
            + '<span style="font-size:0.8125rem; font-weight:600; color:' + adjColor + ';">' + adjLabel + '</span>'
            + '<span style="font-size:0.8rem; font-weight:700; color:' + statusColor + '; background:' + statusColor + '18; border:1px solid ' + statusColor + '44; border-radius:6px; padding:1px 7px;">' + statusText + '</span>'
            + '</div></div>'
            + (gapRows ? '<div style="margin-bottom:0.4rem;">' + gapRows + moreGaps + '</div>' : '')
            + (strengthRows ? '<div style="border-top:1px solid var(--border-color); padding-top:0.4rem; margin-top:0.4rem;">' + strengthRows + '</div>' : '')
            + '</div>';
    }

    _erpShowModeHint(mode) {
        const el = document.getElementById('erp-mode-hint');
        if (!el) return;
        const hints = {
            sequential: '<strong style="color:#e2e8f0;">Sequential</strong> — Architect → Tester → Red Team in order. Each critic reads the previous one\'s output, enabling cross-validated reasoning. <span style="color:var(--secondary-color);">Best choice for thorough assessments.</span> Tradeoff: ~90s total.',
            auto:       '<strong style="color:#e2e8f0;">Auto</strong> — Chooses based on architecture complexity. Simple architectures (few nodes/paths) use partial parallel; complex ones fall back to sequential. Balances speed and rigour automatically.',
            parallel:   '<strong style="color:#e2e8f0;">Parallel</strong> — All three critics run simultaneously (~30s faster). <span style="color:var(--warning-color);">Blindspot:</span> Tester cannot validate Architect\'s roadmap; Red Team cannot adjust for invalid MITRE mappings. Use when speed matters more than cross-referencing.',
        };
        el.innerHTML = hints[mode] || '';
    }

    runExpertReview(archName, forcedMode) {
        if (!archName) return;

        // Accept forcedMode (from _rerunMoE), otherwise read the idle-state selector
        const modeEl = document.getElementById('erp-mode-select');
        const criticMode = forcedMode || (modeEl ? modeEl.value : 'sequential');

        // Initialise persistent run state — survives tab switches
        // status: 'running' | 'paused'
        const abortController = new AbortController();
        this._erpState = {
            status: 'running',
            archName,
            criticMode,
            stage: 'architect',
            pct: 0,
            message: 'Starting...',
            cardStates: {},      // keyed by critic name
            liveResults: [],     // ordered array of rendered critic HTML blocks
            abortController,
        };

        // Swap buttons to running state immediately (before any tab switch)
        this._syncErpButtons(archName, 'running');

        // Ensure the progress box is visible
        const progressBox = document.getElementById('expert-review-progress');
        const errorBox = document.getElementById('expert-review-error');
        if (progressBox) progressBox.style.display = 'block';
        if (errorBox) errorBox.style.display = 'none';

        this._launchErpFetch(archName);
    }

    // Apply a progress SSE event to state + DOM
    _erpApplyProgress(data) {
        if (!this._erpState) return;
        const p = data.progress || 0;
        this._erpState.pct = p;
        this._erpState.stage = data.stage || this._erpState.stage;
        this._erpState.message = data.message || '';
        const parallelMode = this._erpState.criticMode === 'parallel' || this._erpState.criticMode === 'auto';
        const msgEl = document.getElementById('erp-message');
        const stageMap = { architect: '🏛️ Architect', tester: '🔬 Tester', red_team: '🎯 Red Team', synthesis: '⚙️ Synthesis', complete: '✅ Done' };
        if (msgEl) msgEl.textContent = data.message || '';

        if (parallelMode) {
            // Per-critic bars: each stage drives its own bar
            const criticStages = ['architect', 'tester', 'red_team'];
            if (data.stage === 'parallel_starting') {
                // Initialise all three critic bars to "started" (5%)
                for (const c of criticStages) {
                    const cBar = document.getElementById('erp-bar-' + c);
                    const cPct = document.getElementById('erp-pct-' + c);
                    if (cBar && cBar.style.width === '0%') { cBar.style.width = '5%'; }
                    if (cPct && cPct.textContent === '0%') cPct.textContent = '5%';
                }
                // Start per-critic elapsed timer — updates card status every second
                if (!this._erpState._parallelElapsed) {
                    this._erpState._parallelElapsed = {};
                    this._erpState._parallelStartTs = Date.now();
                    this._erpParallelTimer = setInterval(() => {
                        if (!this._erpState) { clearInterval(this._erpParallelTimer); return; }
                        const elapsed = Math.round((Date.now() - this._erpState._parallelStartTs) / 1000);
                        const criticLabels = { architect: '🏛️ Architect', tester: '🔬 Coverage Audit', red_team: '🎯 Red Team' };
                        for (const c of ['architect', 'tester', 'red_team']) {
                            const cs = this._erpState.cardStates[c];
                            if (cs && cs.isCriticResult) continue; // already done
                            const statusEl = document.getElementById('erp-card-' + c + '-status');
                            if (statusEl) {
                                statusEl.innerHTML = `<span style="color:var(--primary-color);">⟳ Running… ${elapsed}s</span>`;
                            }
                        }
                    }, 1000);
                }
            } else if (criticStages.includes(data.stage)) {
                const criticBar = document.getElementById('erp-bar-' + data.stage);
                const criticPct = document.getElementById('erp-pct-' + data.stage);
                if (criticBar) criticBar.style.width = p + '%';
                if (criticPct) criticPct.textContent = p + '%';
            } else if (data.stage === 'synthesis') {
                // Switch to synthesis bar row
                const synthRow = document.getElementById('erp-synthesis-bar-row');
                if (synthRow) synthRow.style.display = 'flex';
                const bar = document.getElementById('erp-bar');
                const synthPct = document.getElementById('erp-pct-synthesis');
                if (bar) bar.style.width = p + '%';
                if (synthPct) synthPct.textContent = p + '%';
            }
            // Update overall % label and stage label
            const pctEl = document.getElementById('erp-pct');
            const stageLabel = document.getElementById('erp-stage-label');
            if (pctEl) pctEl.textContent = p + '%';
            if (stageLabel) stageLabel.textContent = data.stage === 'synthesis' ? '⚙️ Synthesising…' : 'Parallel critics running…';
        } else {
            const bar = document.getElementById('erp-bar');
            const pctEl = document.getElementById('erp-pct');
            const stageLabel = document.getElementById('erp-stage-label');
            if (bar) bar.style.width = p + '%';
            if (pctEl) pctEl.textContent = p + '%';
            if (stageLabel) stageLabel.textContent = stageMap[data.stage] || data.stage;
        }

        // Derive a compact synthesis sub-step label from the message for the card status
        const synthSubStepLabel = (() => {
            const m = data.message || '';
            if (m.includes('confidence score'))  return '⚙ Calculating confidence...';
            if (m.includes('LLM synthesising'))  return '⚙ LLM consensus (~20s)...';
            if (m.includes('roadmap'))            return '⚙ Building roadmap...';
            if (m.includes('Saving'))             return '⚙ Saving results...';
            if (m.includes('executive') || m.includes('diagram')) return '⚙ Generating reports...';
            return '⚙ Running...';
        })();

        const agentOrder = ['architect', 'tester', 'red_team', 'synthesis'];
        const currentIdx = agentOrder.indexOf(data.stage);
        // In parallel/auto mode all three critics run concurrently — show them all as
        // "Running…" while the batch is in progress (before any critic_result arrives)
        const criticsDone = ['architect', 'tester', 'red_team'].filter(
            a => this._erpState.cardStates[a] && this._erpState.cardStates[a].isCriticResult
        ).length;
        const totalCritics = 3;
        // Parallel phase: all critics run concurrently until ALL have returned results
        const inParallelPhase = parallelMode && criticsDone < totalCritics && data.stage !== 'synthesis';

        for (let i = 0; i < agentOrder.length; i++) {
            const agent = agentOrder[i];
            if (this._erpState.cardStates[agent] && this._erpState.cardStates[agent].isCriticResult) continue;
            const card = document.getElementById('erp-card-' + agent);
            const statusEl = document.getElementById('erp-card-' + agent + '-status');
            if (!card || !statusEl) continue;
            let cs;
            if (inParallelPhase && agent !== 'synthesis') {
                // Critics running concurrently — show as running until each sends its result
                cs = { opacity: '1', borderColor: 'var(--primary-color)', statusHtml: '⟳ Running (parallel)...', statusColor: 'var(--primary-color)', isCriticResult: false };
            } else if (i < currentIdx) {
                cs = { opacity: '1', borderColor: 'var(--secondary-color)', statusHtml: '✓ Done', statusColor: 'var(--secondary-color)', isCriticResult: false };
            } else if (i === currentIdx) {
                const runningLabel = agent === 'synthesis' ? synthSubStepLabel : 'Running...';
                cs = { opacity: '1', borderColor: 'var(--primary-color)', statusHtml: runningLabel, statusColor: 'var(--primary-color)', isCriticResult: false };
            } else {
                cs = { opacity: '0.35', borderColor: 'var(--border-color)', statusHtml: 'Waiting', statusColor: 'var(--text-tertiary)', isCriticResult: false };
            }
            this._erpState.cardStates[agent] = cs;
            card.style.opacity = cs.opacity;
            card.style.borderColor = cs.borderColor;
            statusEl.innerHTML = cs.statusHtml;
            statusEl.style.color = cs.statusColor;
        }
    }

    // Apply a critic_result SSE event to state + DOM
    _erpApplyCriticResult(data) {
        if (!this._erpState) return;
        const critic = data.critic;
        const statusColor = data.status_color || 'var(--secondary-color)';
        const adjPct2 = parseFloat(data.confidence_adjustment_pct);
        const adjLabel2 = adjPct2 === 0 ? 'No adjustment' : (adjPct2 > 0 ? '+' : '') + adjPct2 + '% conf';
        const statusHtml =
            '<span style="color:' + statusColor + '; font-weight:600;">' + (data.validation_status || '') + '</span>'
            + ' &nbsp;<span style="color:var(--text-tertiary);">' + data.score + '/100</span>';
        let previewHtml = '<div style="color:var(--text-secondary);">'
            + adjLabel2
            + ' &nbsp;&bull;&nbsp; ' + data.gap_count + ' gap' + (data.gap_count !== 1 ? 's' : '')
            + '</div>';
        if (data.top_gaps && data.top_gaps.length > 0) {
            const g = data.top_gaps[0];
            previewHtml += '<div style="margin-top:0.2rem; color:var(--text-tertiary); overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">'
                + (g.severity ? '<b>' + g.severity + '</b>: ' : '')
                + (g.description || '')
                + '</div>';
        }
        this._erpState.cardStates[critic] = { opacity: '1', borderColor: statusColor, statusHtml, statusColor, previewHtml, isCriticResult: true };
        const card = document.getElementById('erp-card-' + critic);
        const statusEl = document.getElementById('erp-card-' + critic + '-status');
        const previewEl = document.getElementById('erp-card-' + critic + '-preview');
        if (card) { card.style.opacity = '1'; card.style.borderColor = statusColor; }
        if (statusEl) { statusEl.innerHTML = statusHtml; statusEl.style.color = statusColor; }
        if (previewEl) { previewEl.innerHTML = previewHtml; previewEl.style.display = 'block'; }
        // In parallel mode: mark this critic's bar as 100% (done) with success colour
        const parallelMode2 = this._erpState.criticMode === 'parallel' || this._erpState.criticMode === 'auto';
        if (parallelMode2 && ['architect', 'tester', 'red_team'].includes(critic)) {
            const cBar = document.getElementById('erp-bar-' + critic);
            const cPct = document.getElementById('erp-pct-' + critic);
            if (cBar) { cBar.style.width = '100%'; cBar.style.background = statusColor; }
            if (cPct) { cPct.textContent = '✓'; cPct.style.color = statusColor; }
        }

        // Stop parallel elapsed timer once all three critics have results
        const allCriticsDone = ['architect', 'tester', 'red_team'].every(
            c => this._erpState.cardStates[c] && this._erpState.cardStates[c].isCriticResult
        );
        if (allCriticsDone && this._erpParallelTimer) {
            clearInterval(this._erpParallelTimer);
            this._erpParallelTimer = null;
        }

        // On resume, the same critic may come back from disk — don't duplicate live cards
        const alreadyShown = this._erpState.liveResults.some(h => h.includes('id="erp-live-' + critic + '"'));
        if (!alreadyShown) {
            const liveCardHtml = this._buildLiveCriticCard(data).replace('<div style="background', '<div id="erp-live-' + critic + '" style="background');
            this._erpState.liveResults.push(liveCardHtml);
        }
        const liveEl = document.getElementById('erp-live-results');
        if (liveEl) liveEl.innerHTML = this._erpState.liveResults.join('');
    }

    _clearErpTimers() {
        if (this._erpParallelTimer) { clearInterval(this._erpParallelTimer); this._erpParallelTimer = null; }
    }

    // Launch (or re-launch for resume) the SSE fetch pump
    _launchErpFetch(archName) {
        const apiKey = localStorage.getItem('tm_api_key') || '';
        const criticMode = (this._erpState && this._erpState.criticMode) || 'auto';
        const url = `/api/v1/expert-review?architecture_name=${encodeURIComponent(archName)}&critic_mode=${encodeURIComponent(criticMode)}`;
        const signal = this._erpState && this._erpState.abortController
            ? this._erpState.abortController.signal : undefined;

        fetch(url, { headers: { 'TM-API-KEY': apiKey }, signal })
            .then(resp => {
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buf = '';

                const pump = () => reader.read().then(({ done, value }) => {
                    if (done) return;
                    buf += decoder.decode(value, { stream: true });
                    const parts = buf.split('\n\n');
                    buf = parts.pop();
                    for (const part of parts) {
                        let evtType = 'message', dataLine = '';
                        for (const line of part.split('\n')) {
                            if (line.startsWith('event: ')) evtType = line.slice(7).trim();
                            else if (line.startsWith('data: ')) dataLine = line.slice(6).trim();
                        }
                        if (!dataLine) continue;
                        try {
                            const data = JSON.parse(dataLine);
                            if (evtType === 'progress') {
                                this._erpApplyProgress(data);
                            } else if (evtType === 'critic_result') {
                                this._erpApplyCriticResult(data);
                            } else if (evtType === 'complete') {
                                this._clearErpTimers();
                                this._erpState = null;
                                // Update header MoE pill with final confidence from the complete event
                                if (data && data.moe_result) this._updateMoePill(data.moe_result);
                                setTimeout(() => {
                                    this.loadExpertReviewTab();
                                    // Fetch moe json to update pill if not in complete payload
                                    const an = this.analysisData && (this.analysisData.architecture_name || this.analysisData.architecture);
                                    if (an) fetch(`/api/v1/reports/${encodeURIComponent(an)}/files/07_moe_orchestrator.json`)
                                        .then(r => r.ok ? r.json() : null).then(m => { if (m) this._updateMoePill(m); }).catch(() => {});
                                }, 600);
                                setTimeout(() => this.loadOverviewTab(), 1200);
                            } else if (evtType === 'error') {
                                const an = this._erpState && this._erpState.archName;
                                this._clearErpTimers();
                                this._erpState = null;
                                this._syncErpButtons(an, 'idle');
                                const errBox = document.getElementById('expert-review-error');
                                if (errBox) {
                                    errBox.textContent = data.detail || data.message || 'Expert Review failed';
                                    errBox.style.display = 'block';
                                }
                            }
                        } catch (_) {}
                    }
                    return pump();
                });
                return pump();
            })
            .catch(err => {
                if (err.name === 'AbortError') return;  // pause or cancel — not an error
                const an = this._erpState && this._erpState.archName;
                this._clearErpTimers();
                this._erpState = null;
                this._syncErpButtons(an, 'idle');
                const errBox = document.getElementById('expert-review-error');
                if (errBox) {
                    errBox.textContent = `Connection error: ${err.message}`;
                    errBox.style.display = 'block';
                }
            });
    }

    async loadRawDataTab() {
        const listContainer = document.getElementById('artifacts-list');

        if (!this.analysisData) {
            listContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const archName = this.analysisData.architecture_name;
        listContainer.innerHTML = '<p class="placeholder" style="padding: 2rem;">Loading JSON data files...</p>';

        // JSON file catalogue — descriptions for known files
        const JSON_CATALOGUE = {
            'ground_truth.json':        { title: 'Ground Truth',         icon: '🏗️', desc: 'Full deterministic analysis output — threats, controls, attack paths, MITRE mappings', group: 'foundation' },
            '04_architect_critique.json': { title: 'Architecture Review', icon: '🏛️', desc: 'Expert assessment of threat model completeness and structural coverage', group: 'expert' },
            '05_tester_critique.json':  { title: 'Coverage Audit',        icon: '🔬', desc: 'MITRE technique coverage and mapping accuracy review', group: 'expert' },
            '06_red_team_critique.json':{ title: 'Exploit Analysis',      icon: '🎯', desc: 'Red team assessment of control weaknesses and exploitable gaps', group: 'expert' },
            '07_moe_orchestrator.json': { title: 'MoE Orchestrator',      icon: '🧠', desc: 'Mixture-of-Experts synthesis — consensus recommendations and confidence waterfall', group: 'expert' },
            '07_orchestrator_report.json': { title: 'Orchestrator Report',icon: '📋', desc: 'Structured expert panel summary with contradiction and action item lists', group: 'expert' },
        };

        let savedFiles = [];
        try {
            const resp = await fetch(`/api/v1/reports/${archName}`);
            if (resp.ok) {
                const data = await resp.json();
                savedFiles = (data.reports || []).filter(f => f.filename.endsWith('.json'));
            }
        } catch (_) { /* server JSON files optional */ }

        // Group into foundation and expert
        const groups = { foundation: [], expert: [] };
        savedFiles.forEach(f => {
            const meta = JSON_CATALOGUE[f.filename];
            const group = meta ? meta.group : 'foundation';
            groups[group].push({
                id: f.filename,
                title: meta ? meta.title : f.filename,
                icon: meta ? meta.icon : '📊',
                desc: meta ? meta.desc : '',
                filename: f.filename,
                size: f.size,
                url: f.url,
                source: 'file'
            });
        });

        // In-memory live session data (not persisted to disk)
        const analysis = this.analysisData.analysis || {};
        const liveArtifacts = [];
        if (analysis.threats) liveArtifacts.push({ name: 'rapids_threats', data: { threats: analysis.threats }, description: 'RAPIDS threat assessment scores' });
        if (analysis.ai_ml_risks) liveArtifacts.push({ name: 'ai_ml_risks', data: { ai_ml_risks: analysis.ai_ml_risks }, description: 'AI/ML risk analysis (ARC Framework)' });
        if (analysis.controls_present || analysis.controls_missing) liveArtifacts.push({ name: 'controls', data: { controls_present: analysis.controls_present || [], controls_missing: analysis.controls_missing || [] }, description: 'Present and missing security controls' });
        if (analysis.expected_attack_paths) liveArtifacts.push({ name: 'attack_paths', data: { expected_attack_paths: analysis.expected_attack_paths }, description: `${analysis.expected_attack_paths.length} attack paths identified` });
        if (analysis.control_recommendations) liveArtifacts.push({ name: 'control_recommendations', data: { control_recommendations: analysis.control_recommendations }, description: `${analysis.control_recommendations.length} control recommendations` });

        const hasFoundation = groups.foundation.length > 0;
        const hasExpert = groups.expert.length > 0;
        const hasLive = liveArtifacts.length > 0;

        const sectionHeader = (icon, label, badge, badgeColor) =>
            `<div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.75rem;">
                <span style="font-size:1.125rem;">${icon}</span>
                <h4 style="margin:0; color:var(--text-color); font-size:0.9375rem;">${label}</h4>
                ${badge ? `<span style="font-size:0.75rem; color:${badgeColor || 'var(--text-tertiary)'}; padding:0.125rem 0.5rem; background:${badgeColor ? badgeColor + '18' : 'var(--nav-hover-bg)'}; border-radius:10px; ${badgeColor ? 'border:1px solid ' + badgeColor + '44;' : ''}">${badge}</span>` : ''}
            </div>`;

        listContainer.innerHTML = `
            <!-- Download all JSON -->
            <div style="display:flex; gap:0.75rem; margin-bottom:1.5rem; flex-wrap:wrap; align-items:center;">
                <span style="font-size:0.8125rem; color:var(--text-secondary); font-weight:600;">Download:</span>
                <a href="/api/v1/reports/${archName}/download?pack=json" download="${archName}_json.zip"
                   class="btn-primary" style="padding:0.5rem 1rem; font-size:0.8125rem; font-weight:600; text-decoration:none;">
                    ⬇ All JSON Files
                </a>
                <span style="font-size:0.75rem; color:var(--text-tertiary); margin-left:auto;">
                    Click any file to inspect · ⬇ on card to download individually · Markdown reports → Reports tab
                </span>
            </div>

            <!-- Foundation JSON -->
            ${hasFoundation ? `
            <div style="margin-bottom:1.5rem;">
                ${sectionHeader('🏗️', 'Foundation Analysis', 'Deterministic engine output', '')}
                <div id="rd-foundation-list" style="display:flex; flex-direction:column; gap:0.5rem;"></div>
            </div>` : ''}

            <!-- Expert Review JSON -->
            ${hasExpert ? `
            <div style="margin-bottom:1.5rem;">
                ${sectionHeader('🧑‍🏫', 'Expert Review', 'Available after Expert Review runs', 'var(--secondary-color)')}
                <div id="rd-expert-list" style="display:flex; flex-direction:column; gap:0.5rem;"></div>
            </div>` : ''}

            <!-- Live session data -->
            ${hasLive ? `
            <div style="margin-bottom:1.5rem;">
                ${sectionHeader('⚡', 'Live Session Data', 'In-memory · not written to disk', '')}
                <div id="rd-live-list" style="display:flex; flex-direction:column; gap:0.5rem;"></div>
            </div>` : ''}

            ${!hasFoundation && !hasExpert && !hasLive ? `
            <div style="padding:2rem; text-align:center; color:var(--text-secondary); font-size:0.875rem;">
                No JSON files found for <strong>${archName}</strong>. Run a full analysis first.
            </div>` : ''}
        `;

        const renderFileCard = (containerId, item) => {
            const container = document.getElementById(containerId);
            if (!container) return;
            const sizeKB = item.size ? (item.size / 1024).toFixed(1) : '?';
            const card = document.createElement('div');
            card.className = 'list-item';
            card.dataset.fileId = item.id;
            card.style.cssText = 'padding:0.875rem 1rem; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:0.75rem;';
            card.innerHTML = `
                <div style="display:flex; align-items:flex-start; gap:0.625rem; min-width:0;">
                    <span style="font-size:1.125rem; flex-shrink:0;">${item.icon}</span>
                    <div style="min-width:0;">
                        <div style="font-weight:600; font-size:0.875rem; color:var(--text-color);">${item.title}</div>
                        ${item.desc ? `<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.125rem; line-height:1.3;">${item.desc}</div>` : ''}
                        <div style="font-size:0.6875rem; color:var(--text-tertiary); margin-top:0.25rem; font-family:monospace;">${item.filename} · ${sizeKB} KB</div>
                    </div>
                </div>
                <a href="${item.url}" download="${item.filename}"
                   style="font-size:0.75rem; color:var(--primary-color); text-decoration:none; padding:0.125rem 0.375rem; border:1px solid var(--primary-color); border-radius:4px; flex-shrink:0;"
                   onclick="event.stopPropagation()">⬇</a>
            `;
            card.addEventListener('click', () => {
                listContainer.querySelectorAll('.list-item').forEach(el => { el.style.borderColor = 'var(--border-color)'; el.style.background = 'var(--card-bg)'; });
                card.style.borderColor = 'var(--primary-color)';
                card.style.background = 'var(--primary-color)12';
                this._showJsonFileInRightPane(item, archName);
            });
            container.appendChild(card);
        };

        const renderLiveCard = (containerId, artifact) => {
            const container = document.getElementById(containerId);
            if (!container) return;
            const sizeKB = (JSON.stringify(artifact.data).length / 1024).toFixed(1);
            const card = document.createElement('div');
            card.className = 'list-item';
            card.dataset.fileId = artifact.name;
            card.style.cssText = 'padding:0.875rem 1rem; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:0.75rem;';
            card.innerHTML = `
                <div style="display:flex; align-items:flex-start; gap:0.625rem; min-width:0;">
                    <span style="font-size:1.125rem; flex-shrink:0;">📊</span>
                    <div style="min-width:0;">
                        <div style="font-weight:600; font-size:0.875rem; color:var(--text-color);">${artifact.name}</div>
                        <div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.125rem;">${artifact.description} · ${sizeKB} KB</div>
                    </div>
                </div>
                <span style="color:var(--primary-color); flex-shrink:0;">→</span>
            `;
            card.addEventListener('click', () => {
                listContainer.querySelectorAll('.list-item').forEach(el => { el.style.borderColor = 'var(--border-color)'; el.style.background = 'var(--card-bg)'; });
                card.style.borderColor = 'var(--primary-color)';
                card.style.background = 'var(--primary-color)12';
                this.showArtifact(artifact);
            });
            container.appendChild(card);
        };

        groups.foundation.forEach(f => renderFileCard('rd-foundation-list', f));
        groups.expert.forEach(f => renderFileCard('rd-expert-list', f));
        liveArtifacts.forEach(a => renderLiveCard('rd-live-list', a));
    }

    async _showJsonFileInRightPane(item, archName) {
        const downloadLink = `<a href="${item.url}" download="${item.filename}" class="btn-primary" style="display:inline-block; text-decoration:none; padding:0.375rem 0.875rem; font-size:0.8125rem; margin-bottom:1rem;">⬇ Download ${item.filename}</a>`;
        this.showRightPane(`${item.icon} ${item.title}`, `
            ${downloadLink}
            <div id="rp-content-area" style="color:var(--text-secondary); font-size:0.875rem;">Loading...</div>
        `);
        try {
            const resp = await fetch(item.url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const jsonStr = JSON.stringify(data, null, 2);
            const isLarge = jsonStr.length > 50000;
            const area = document.getElementById('rp-content-area');
            if (!area) return;
            area.innerHTML = `
                <div style="margin-bottom:0.5rem; font-size:0.8125rem; color:var(--text-secondary);">${(jsonStr.length / 1024).toFixed(1)} KB${isLarge ? ' — large file, rendering…' : ''}</div>
                <div id="streaming-container" style="padding:1rem; background:var(--code-bg); border-radius:8px; border:1px solid var(--border-color); overflow-x:auto; max-height:70vh; overflow-y:auto;"></div>
            `;
            const renderer = new StreamingRenderer('streaming-container');
            if (isLarge) {
                await renderer.streamJSON(data, 5);
            } else {
                document.getElementById('streaming-container').innerHTML =
                    `<pre style="margin:0;"><code class="language-json">${this.escapeHtml(jsonStr)}</code></pre>`;
                if (window.hljs) {
                    const cb = document.querySelector('#streaming-container code');
                    if (cb) hljs.highlightElement(cb);
                }
            }
        } catch (err) {
            const area = document.getElementById('rp-content-area');
            if (area) area.innerHTML = `<p style="color:var(--danger-color);">⚠️ Failed to load: ${err.message}</p>`;
        }
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

    // =========================================================================
    // Configuration Tab
    // =========================================================================

    async loadConfigTab() {
        const container = document.getElementById('config-sections');
        if (!container) return;
        if (!this._configData) {
            container.innerHTML = '<p class="placeholder">Loading configuration…</p>';
        }
        try {
            const apiKey = localStorage.getItem('tm_api_key') || '';
            const resp = await fetch('/api/v1/config', { headers: { 'TM-API-KEY': apiKey } });
            if (resp.status === 401 || resp.status === 422) {
                container.innerHTML = `
                    <div style="padding:1.5rem; text-align:center; color:var(--text-secondary);">
                        <div style="font-size:2rem; margin-bottom:0.75rem;">🔐</div>
                        <div style="font-weight:600; margin-bottom:0.4rem;">API key required</div>
                        <div style="font-size:0.85rem;">Enter your TM-API-KEY in Settings (⚙ top-right) to access the configuration panel.</div>
                    </div>`;
                return;
            }
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            this._configData = await resp.json();
            container.innerHTML = this._renderAllConfigSections(this._configData);
            this._attachConfigListeners();
            // Restore previously-active filter (default 'quick')
            this._filterConfig(this._cfgFilter || 'patterns');
        } catch (err) {
            container.innerHTML = `<p class="placeholder" style="color:var(--danger-color);">Failed to load configuration: ${err.message}</p>`;
        }
    }

    _attachConfigListeners() {
        const saveBtn  = document.getElementById('config-save-btn');
        const resetBtn = document.getElementById('config-reset-btn');
        if (saveBtn)  saveBtn.onclick  = () => this.saveConfig();
        if (resetBtn) resetBtn.onclick = () => this.resetConfig();
        // Filter chips
        document.querySelectorAll('#cfg-filter-chips .cfg-chip').forEach(chip => {
            chip.addEventListener('click', () => this._filterConfig(chip.dataset.filter));
        });
    }

    _filterConfig(filter) {
        this._cfgFilter = filter;
        // Update chip active state
        document.querySelectorAll('#cfg-filter-chips .cfg-chip').forEach(chip => {
            const isActive = chip.dataset.filter === filter;
            chip.style.background = isActive ? '#4da6ff' : 'var(--card-bg)';
            chip.style.color      = isActive ? '#fff'     : 'var(--text-secondary)';
            chip.style.borderColor = isActive ? '#4da6ff' : 'var(--border-color)';
            chip.style.fontWeight  = isActive ? '700'     : '400';
        });

        // Map filter → which section data-cfg-cat values to show
        const showAll = filter === 'all';
        const catMap = {
            'quick':      null,   // special — handled below
            'all':        null,
            'engine':     ['engine'],
            'conf_risk':  ['confidence', 'residual_risk'],
            'moe':        ['moe'],
            'llm_system': ['llm_system'],
            'patterns':   ['patterns'],
            'provider':   ['provider'],
        };

        const showQuick = filter === 'quick';
        const targetCats = catMap[filter] || null;

        // Show/hide the quick-setup card
        const quickCard = document.getElementById('cfg-quick-card');
        if (quickCard) quickCard.style.display = showQuick ? 'block' : 'none';

        // Show/hide section cards
        document.querySelectorAll('#config-sections [data-cfg-cat]').forEach(el => {
            const cat = el.dataset.cfgCat;
            if (showQuick) {
                el.style.display = 'none';           // hide everything except quick card
            } else if (showAll || !targetCats) {
                el.style.display = '';
            } else {
                el.style.display = targetCats.includes(cat) ? '' : 'none';
            }
        });
    }

    async saveConfig() {
        const payload = this._collectConfigFormValues();
        const apiKey = localStorage.getItem('tm_api_key') || '';
        try {
            const resp = await fetch('/api/v1/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'TM-API-KEY': apiKey },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();
            if (!resp.ok) {
                const detail = Array.isArray(data.detail)
                    ? data.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join('; ')
                    : (data.detail || 'Unknown error');
                this._showConfigStatus('error', `Save failed: ${detail}`);
                return;
            }
            this._configData = data.config;
            this._showConfigStatus('success', 'Configuration saved and active in memory. Changes apply to the next analysis run.');
        } catch (err) {
            this._showConfigStatus('error', `Save failed: ${err.message}`);
        }
    }

    async resetConfig() {
        if (!confirm('Reset all settings to built-in defaults?\n\nThis cannot be undone.')) return;
        const apiKey = localStorage.getItem('tm_api_key') || '';
        try {
            const resp = await fetch('/api/v1/config/reset', {
                method: 'POST',
                headers: { 'TM-API-KEY': apiKey }
            });
            const data = await resp.json();
            if (!resp.ok) { this._showConfigStatus('error', 'Reset failed.'); return; }
            this._configData = data.config;
            const container = document.getElementById('config-sections');
            if (container) {
                container.innerHTML = this._renderAllConfigSections(this._configData);
                this._attachConfigListeners();
                this._filterConfig(this._cfgFilter || 'patterns');
            }
            this._showConfigStatus('success', 'All settings reset to defaults.');
        } catch (err) {
            this._showConfigStatus('error', `Reset failed: ${err.message}`);
        }
    }

    _showConfigStatus(type, msg) {
        const el = document.getElementById('config-status');
        if (!el) return;
        const ok = type === 'success';
        el.style.display = 'block';
        el.style.background = ok ? '#0d9f6e18' : '#ef444418';
        el.style.border      = `1px solid ${ok ? '#0d9f6e44' : '#ef444444'}`;
        el.style.color       = ok ? '#0d9f6e' : '#ef4444';
        el.textContent = msg;
        clearTimeout(this._configStatusTimer);
        this._configStatusTimer = setTimeout(() => { el.style.display = 'none'; }, 6000);
    }

    _collectConfigFormValues() {
        // Fields whose values should be sent as numbers (not strings) even from <select>
        const INT_FIELDS = new Set([
            'max_paths','top_n','node_saturation','edge_saturation',
            'complexity_threshold','max_tokens_synthesis','architect_pass_threshold',
            'architect_minor_gap_threshold','architect_major_gap_threshold',
            'tester_pass_threshold','tester_minor_gap_threshold','tester_major_gap_threshold',
            'red_team_hard_threshold','red_team_medium_threshold','red_team_easy_threshold',
            'accept_threshold','monitor_threshold','max_tokens','max_file_size_mb',
            'path_risk_per_path','path_risk_cap',
            // ai_pattern thresholds
            'category_entry_threshold','priority_threshold_integrity','priority_threshold_safety',
            'priority_threshold_security','priority_threshold_privacy',
            'floor_threshold_transparency','floor_threshold_accountability','floor_threshold_resilience',
            // cloud_pattern thresholds
            'base_risk_iam_abuse','base_risk_data_exposure','base_risk_api_abuse',
            'base_risk_compute_abuse','base_risk_network_lateral','base_risk_supply_chain','base_risk_logging_gaps',
            'reduce_mfa','reduce_least_privilege','reduce_privileged_access_management','reduce_iam_audit',
            'reduce_encryption','reduce_bucket_policy','reduce_dlp','reduce_waf','reduce_api_gateway_auth',
            'reduce_network_segmentation','reduce_cloudtrail','reduce_siem',
            'floor_iam_no_mfa_pam','floor_data_no_encryption_policy','floor_logging_no_trail_siem',
            'priority_threshold_iam','priority_threshold_data','priority_threshold_api',
            'priority_threshold_compute','priority_threshold_network','priority_threshold_logging',
        ]);
        const FLOAT_FIELDS = new Set([
            'weight_target','weight_length','weight_control','weight_entry',
            'criticality_critical','criticality_high','criticality_medium',
            'base_confidence_floor','base_confidence_ceiling',
            'node_penalty_factor','edge_penalty_factor','max_complexity_penalty',
            'base_confidence','temperature_synthesis','min_failure_probability','temperature',
            'did_reduction_factor','did_bonus_factor',
        ]);

        const payload = {};
        document.querySelectorAll('#config-sections [data-section][data-field]').forEach(el => {
            const section = el.dataset.section;
            const field   = el.dataset.field;
            const raw     = el.value;
            let value;
            if (el.dataset.vtype === 'int' || INT_FIELDS.has(field))     value = parseInt(raw, 10);
            else if (el.dataset.vtype === 'float' || FLOAT_FIELDS.has(field)) value = parseFloat(raw);
            else value = raw;
            if (!payload[section]) payload[section] = {};
            payload[section][field] = value;
        });
        return payload;
    }

    _renderAllConfigSections(data) {
        const cs = `color:var(--text-secondary); font-size:0.78rem;`;
        const ef = (acc, rel, sen, perf) =>
            `<div style="margin-top:0.45rem; display:flex; flex-wrap:wrap; gap:0.3rem; font-size:0.7rem;">` +
            `<span style="padding:1px 6px; border-radius:3px; background:#4da6ff14; border:1px solid #4da6ff33; color:#4da6ff;">⬡ Accuracy: ${acc}</span>` +
            `<span style="padding:1px 6px; border-radius:3px; background:#0d9f6e14; border:1px solid #0d9f6e33; color:#0d9f6e;">◈ Relevance: ${rel}</span>` +
            `<span style="padding:1px 6px; border-radius:3px; background:#f59e0b14; border:1px solid #f59e0b33; color:#f59e0b;">⚡ Sensitivity: ${sen}</span>` +
            `<span style="padding:1px 6px; border-radius:3px; background:#94a3b814; border:1px solid #94a3b833; color:#94a3b8;">⏱ Perf: ${perf}</span>` +
            `</div>`;

        // ── Field definitions ─────────────────────────────────────────────────
        // vtype options:
        //   'select'  — curated dropdown (options array, value is the raw option string)
        //   'string'  — free-text input
        //   'int'     — number input; recMax = practical recommended upper bound (orange badge if exceeded)
        //   'float'   — same but float step
        const sections = [
          {
            title: '🔍 Analysis Engine',
            subtitle: 'Attack path discovery depth, path scoring weights, and risk calculation factors.',
            fields: [
              { section:'engine', field:'max_paths', label:'Max Attack Paths',
                vtype:'select',
                options:[
                  {v:'5',  label:'5 — Quick scan'},
                  {v:'10', label:'10 — Default (recommended)', rec:true},
                  {v:'15', label:'15 — Deeper coverage'},
                  {v:'25', label:'25 — Thorough (slower BFS)'},
                ],
                desc:'Maximum attack paths explored during BFS graph traversal.',
                effects: ef('Higher = more path coverage','More attack scenarios shown','More verbose results','Higher = slower BFS') },

              { section:'engine', field:'top_n', label:'Top-N Paths Kept',
                vtype:'select',
                options:[
                  {v:'3', label:'3 — Focused (fewest paths)'},
                  {v:'5', label:'5 — Default (recommended)', rec:true},
                  {v:'8', label:'8 — Extended view'},
                  {v:'10',label:'10 — Maximum paths in report'},
                ],
                desc:'Top-N critical paths retained after ranking and deduplication.',
                effects: ef('Neutral (already ranked)','Higher = richer attack view','More paths in report','Minimal') },

              { section:'engine', field:'weight_target', label:'Weight: Target Sensitivity',
                vtype:'select',
                options:[
                  {v:'0.25', label:'0.25 — Low focus on target type'},
                  {v:'0.30', label:'0.30 — Moderate'},
                  {v:'0.35', label:'0.35 — Default (recommended)', rec:true},
                  {v:'0.40', label:'0.40 — Higher crown-jewel focus'},
                ],
                desc:'Composite score weight for target node sensitivity (DB > file > generic). All four weights should sum to ~1.0.',
                effects: ef('Higher = focus on crown-jewel paths','Improves crown-jewel relevance','Neutral','None') },

              { section:'engine', field:'weight_length', label:'Weight: Path Length',
                vtype:'select',
                options:[
                  {v:'0.15', label:'0.15 — Low length preference'},
                  {v:'0.20', label:'0.20 — Moderate'},
                  {v:'0.25', label:'0.25 — Default (recommended)', rec:true},
                  {v:'0.30', label:'0.30 — Strong short-path preference'},
                ],
                desc:'Weight for hop count — shorter paths (easier to exploit) score higher. All four weights should sum to ~1.0.',
                effects: ef('Higher = favours short realistic paths','Short-path bias','May hide indirect paths','None') },

              { section:'engine', field:'weight_control', label:'Weight: Control Coverage',
                vtype:'select',
                options:[
                  {v:'0.15', label:'0.15 — Low defense weighting'},
                  {v:'0.20', label:'0.20 — Moderate'},
                  {v:'0.25', label:'0.25 — Default (recommended)', rec:true},
                  {v:'0.30', label:'0.30 — Strong defense weighting'},
                ],
                desc:'Weight for how well-defended the path is — undefended paths score higher. All four weights should sum to ~1.0.',
                effects: ef('Higher = undefended paths rank worse','Strongly boosts path selection relevance','Raises severity estimates','None') },

              { section:'engine', field:'weight_entry', label:'Weight: Entry Exposure',
                vtype:'select',
                options:[
                  {v:'0.10', label:'0.10 — Low entry focus'},
                  {v:'0.15', label:'0.15 — Default (recommended)', rec:true},
                  {v:'0.20', label:'0.20 — Stronger internet-facing focus'},
                  {v:'0.25', label:'0.25 — Maximum entry focus'},
                ],
                desc:'Weight for entry-point exposure level (internet > user > internal). All four weights should sum to ~1.0.',
                effects: ef('Internet-facing paths more accurate','Higher = internet-facing gets priority','Neutral','None') },

              { section:'engine', field:'criticality_critical', label:'CRITICAL Tier Threshold',
                vtype:'select',
                options:[
                  {v:'0.70', label:'0.70 — Lenient (more CRITICALs)'},
                  {v:'0.75', label:'0.75 — Moderately lenient'},
                  {v:'0.80', label:'0.80 — Default (recommended)', rec:true},
                  {v:'0.85', label:'0.85 — Strict (fewer CRITICALs)'},
                ],
                desc:'Minimum composite score to classify a path as CRITICAL. Must be higher than HIGH threshold.',
                effects: ef('Lower = more CRITICAL findings (may inflate)','CRITICAL label appears more often','Very High','None') },

              { section:'engine', field:'criticality_high', label:'HIGH Tier Threshold',
                vtype:'select',
                options:[
                  {v:'0.50', label:'0.50 — Lenient (more HIGHs)'},
                  {v:'0.55', label:'0.55'},
                  {v:'0.60', label:'0.60 — Default (recommended)', rec:true},
                  {v:'0.65', label:'0.65 — Strict'},
                ],
                desc:'Minimum composite score to classify a path as HIGH. Must be between MEDIUM and CRITICAL thresholds.',
                effects: ef('Affects HIGH tier count','As above','High','None') },

              { section:'engine', field:'criticality_medium', label:'MEDIUM Tier Threshold',
                vtype:'select',
                options:[
                  {v:'0.30', label:'0.30 — Lenient (more MEDIUMs)'},
                  {v:'0.35', label:'0.35'},
                  {v:'0.40', label:'0.40 — Default (recommended)', rec:true},
                  {v:'0.50', label:'0.50 — Strict (more LOWs)'},
                ],
                desc:'Minimum composite score for MEDIUM tier. Paths below this are LOW. Must be lower than HIGH threshold.',
                effects: ef('Affects MEDIUM/LOW split','As above','High','None') },

              { section:'engine', field:'did_reduction_factor', label:'Defence-in-Depth Reduction',
                vtype:'select',
                options:[
                  {v:'25', label:'25 — Conservative (less credit)'},
                  {v:'35', label:'35 — Moderate'},
                  {v:'40', label:'40 — Default (recommended)', rec:true},
                  {v:'50', label:'50 — Generous (more credit for layers)'},
                ],
                desc:'Risk reduction points awarded per defence-in-depth tier. Higher = more credit for layered controls.',
                effects: ef('Lower = more conservative','Lower = higher residual risk shown','High','None') },

              { section:'engine', field:'path_risk_per_path', label:'Risk Pts per Attack Path',
                vtype:'select',
                options:[
                  {v:'1', label:'1 — Minimal path impact'},
                  {v:'2', label:'2 — Low'},
                  {v:'3', label:'3 — Default (recommended)', rec:true},
                  {v:'5', label:'5 — High path impact'},
                ],
                desc:'Risk points added per discovered attack path (subject to the cap below).',
                effects: ef('Lower = paths matter less','Lower impact on overall risk score','Moderate','None') },

              { section:'engine', field:'path_risk_cap', label:'Attack Path Risk Cap',
                vtype:'select',
                options:[
                  {v:'10', label:'10 — Low cap'},
                  {v:'15', label:'15 — Default (recommended)', rec:true},
                  {v:'20', label:'20 — Higher cap'},
                  {v:'25', label:'25 — Maximum allowed'},
                ],
                desc:'Maximum total risk points attributable to all attack paths combined.',
                effects: ef('Lower cap = many paths cannot keep escalating risk','Moderate','Moderate','None') },
            ]
          },
          {
            title: '📊 Confidence Calculation',
            subtitle: 'How architecture complexity penalises base confidence and how thoroughness recovers it.',
            fields: [
              { section:'confidence', field:'base_confidence_floor', label:'Confidence Floor',
                vtype:'select',
                options:[
                  {v:'0.65', label:'0.65 — Conservative floor'},
                  {v:'0.70', label:'0.70 — Moderately conservative'},
                  {v:'0.72', label:'0.72 — Default (recommended)', rec:true},
                  {v:'0.80', label:'0.80 — Optimistic floor'},
                ],
                desc:'Minimum possible base confidence before expert adjustments. Lower = more conservative on complex diagrams.',
                effects: ef('Higher floor = optimistic baseline','Less distinction for complex diagrams','High','None') },

              { section:'confidence', field:'base_confidence_ceiling', label:'Confidence Ceiling',
                vtype:'select',
                options:[
                  {v:'0.95', label:'0.95 — Conservative ceiling'},
                  {v:'0.98', label:'0.98 — Moderately conservative'},
                  {v:'0.995',label:'0.995 — Default (recommended)', rec:true},
                ],
                desc:'Maximum possible base confidence. Lowering this makes all assessments start more conservative.',
                effects: ef('Lower = more conservative maximum','Direct impact on displayed confidence %','Very High','None') },

              { section:'confidence', field:'node_penalty_factor', label:'Node Penalty Factor',
                vtype:'select',
                options:[
                  {v:'0.05', label:'0.05 — Mild node penalty'},
                  {v:'0.10', label:'0.10 — Moderate'},
                  {v:'0.15', label:'0.15 — Default (recommended)', rec:true},
                  {v:'0.20', label:'0.20 — Stronger penalty'},
                ],
                desc:'Confidence penalty weight per unit of node-count complexity. Saturates at the node saturation count.',
                effects: ef('Higher = large diagrams penalised more','Larger diagrams show lower confidence','High','None') },

              { section:'confidence', field:'node_saturation', label:'Node Saturation Count',
                vtype:'select',
                options:[
                  {v:'10', label:'10 — Penalty saturates quickly'},
                  {v:'15', label:'15'},
                  {v:'20', label:'20 — Default (recommended)', rec:true},
                  {v:'30', label:'30 — Penalty kicks in later'},
                  {v:'50', label:'50 — Large-diagram tolerance'},
                ],
                desc:'Node count at which the node complexity penalty is fully applied (linear ramp up to this point).',
                effects: ef('Higher = penalty kicks in later','More optimistic for large graphs','Moderate','None') },

              { section:'confidence', field:'edge_penalty_factor', label:'Edge Penalty Factor',
                vtype:'select',
                options:[
                  {v:'0.05', label:'0.05 — Mild'},
                  {v:'0.10', label:'0.10 — Default (recommended)', rec:true},
                  {v:'0.15', label:'0.15 — Stronger'},
                ],
                desc:'Confidence penalty weight per unit of edge-count complexity. Saturates at the edge saturation count.',
                effects: ef('Higher = dense-edge diagrams penalised more','As above for edge count','Moderate','None') },

              { section:'confidence', field:'edge_saturation', label:'Edge Saturation Count',
                vtype:'select',
                options:[
                  {v:'20', label:'20 — Saturates quickly'},
                  {v:'30', label:'30'},
                  {v:'40', label:'40 — Default (recommended)', rec:true},
                  {v:'60', label:'60 — Tolerates dense graphs'},
                  {v:'80', label:'80 — Very lenient'},
                ],
                desc:'Edge count at which the edge complexity penalty is fully applied.',
                effects: ef('Higher = dense graphs penalised later','Moderate','Moderate','None') },

              { section:'confidence', field:'max_complexity_penalty', label:'Max Complexity Penalty',
                vtype:'select',
                options:[
                  {v:'0.15', label:'0.15 — Low cap (optimistic)'},
                  {v:'0.20', label:'0.20'},
                  {v:'0.25', label:'0.25 — Default (recommended)', rec:true},
                  {v:'0.30', label:'0.30 — Strict cap'},
                ],
                desc:'Cap on the combined node + edge complexity penalty. Prevents very large diagrams from zeroing confidence.',
                effects: ef('Lower cap = more optimistic for large diagrams','Moderate','Moderate','None') },
            ]
          },
          {
            title: '🧑‍🏫 MoE / Expert Review',
            subtitle: 'Mixture-of-Experts pipeline: base confidence, critic execution, LLM settings, and scoring bands.',
            fields: [
              { section:'moe', field:'base_confidence', label:'Base Confidence (%)',
                vtype:'select',
                options:[
                  {v:'95.0', label:'95.0 — Conservative start'},
                  {v:'97.0', label:'97.0 — Moderately conservative'},
                  {v:'99.5', label:'99.5 — Default (recommended)', rec:true},
                ],
                desc:'Starting confidence % before any expert critic adjustments. Critics then apply penalties from this base.',
                effects: ef('Core starting point for displayed confidence %','Direct','Very High','None') },

              { section:'moe', field:'critic_mode', label:'Critic Execution Mode',
                vtype:'select',
                options:[
                  {v:'sequential', label:'sequential — Cross-referenced, most accurate (recommended)', rec:true},
                  {v:'parallel',   label:'parallel — Faster, critics run blind (less accurate)'},
                  {v:'auto',       label:'auto — Decides per complexity score'},
                ],
                desc:'How the three expert critics run. Sequential means each critic sees prior results for cross-referencing.',
                effects: ef('Sequential = more accurate','Sequential = higher quality gaps','High','Parallel = faster') },

              { section:'moe', field:'complexity_threshold', label:'Auto-Mode Complexity Cutoff',
                vtype:'select',
                options:[
                  {v:'40', label:'40 — More architectures go sequential'},
                  {v:'50', label:'50'},
                  {v:'60', label:'60 — Default (recommended)', rec:true},
                  {v:'80', label:'80 — More architectures go parallel'},
                ],
                desc:'In "auto" mode: complexity score ≥ this → sequential; below → parallel. Only relevant when critic_mode is "auto".',
                effects: ef('Lower = more architectures use sequential','Affects when auto mode switches','Moderate','Sequential = slower') },

              { section:'moe', field:'temperature_synthesis', label:'Synthesis Temperature',
                vtype:'select',
                options:[
                  {v:'0.0',  label:'0.0 — Fully deterministic'},
                  {v:'0.1',  label:'0.1 — Near-deterministic'},
                  {v:'0.2',  label:'0.2 — Default (recommended)', rec:true},
                  {v:'0.4',  label:'0.4 — Some variation'},
                ],
                desc:'LLM temperature for the Layer-3 orchestrator synthesis call. Lower = more reproducible output.',
                effects: ef('Lower = more reproducible','Higher = more creative but less consistent','Low','None') },

              { section:'moe', field:'max_tokens_synthesis', label:'Synthesis Max Tokens',
                vtype:'select',
                options:[
                  {v:'2000', label:'2000 — Concise synthesis'},
                  {v:'3000', label:'3000 — Standard'},
                  {v:'4000', label:'4000 — Default (recommended)', rec:true},
                  {v:'6000', label:'6000 — Extended (slower, costlier)'},
                ],
                desc:'Max tokens for the synthesis LLM call. 4000 is already generous — values above increase cost and latency without proportional benefit.',
                effects: ef('Higher = more complete reasoning','Higher = richer executive output','Low','Higher = slower & costlier') },

              { section:'moe', field:'architect_pass_threshold', label:'Architect: PASS Threshold',
                vtype:'select',
                options:[
                  {v:'80', label:'80 — Lenient (easier to PASS)'},
                  {v:'85', label:'85 — Moderate'},
                  {v:'90', label:'90 — Default (recommended)', rec:true},
                  {v:'95', label:'95 — Strict (harder to PASS)'},
                ],
                desc:'Architect critic score ≥ this = PASS (no confidence penalty). Must be above the minor-gap threshold.',
                effects: ef('Higher = stricter architect scoring','Stricter = more gaps flagged','High','None') },

              { section:'moe', field:'architect_minor_gap_threshold', label:'Architect: Minor Gap Cutoff',
                vtype:'select',
                options:[
                  {v:'70', label:'70 — Lenient'},
                  {v:'75', label:'75'},
                  {v:'80', label:'80 — Default (recommended)', rec:true},
                  {v:'85', label:'85 — Strict'},
                ],
                desc:'Architect score ≥ this (but < PASS) = MINOR_GAPS (−2% or −5% penalty). Must be between major-gap and PASS thresholds.',
                effects: ef('Affects MINOR vs MAJOR boundary','Moderate','High','None') },

              { section:'moe', field:'architect_major_gap_threshold', label:'Architect: Major Gap Cutoff',
                vtype:'select',
                options:[
                  {v:'60', label:'60 — Very lenient'},
                  {v:'65', label:'65'},
                  {v:'70', label:'70 — Default (recommended)', rec:true},
                  {v:'75', label:'75 — Strict'},
                ],
                desc:'Architect score < this = MAJOR_GAPS (−10% confidence). Must be below the minor-gap threshold.',
                effects: ef('Lower = more forgiving of architectural gaps','Moderate','High','None') },

              { section:'moe', field:'tester_pass_threshold', label:'Tester: PASS Threshold',
                vtype:'select',
                options:[
                  {v:'75', label:'75 — Lenient'},
                  {v:'80', label:'80 — Moderate'},
                  {v:'85', label:'85 — Default (recommended)', rec:true},
                  {v:'90', label:'90 — Strict'},
                ],
                desc:'Tester score ≥ this = PASS. Higher = stricter MITRE technique validation required.',
                effects: ef('Higher = stricter MITRE mapping','High','High','None') },

              { section:'moe', field:'tester_minor_gap_threshold', label:'Tester: Minor Gap Cutoff',
                vtype:'select',
                options:[
                  {v:'65', label:'65 — Lenient'},
                  {v:'70', label:'70'},
                  {v:'75', label:'75 — Default (recommended)', rec:true},
                  {v:'80', label:'80 — Strict'},
                ],
                desc:'Tester score ≥ this (but < PASS) = MINOR_GAPS. Must be between major-gap and PASS thresholds.',
                effects: ef('Moderate','Moderate','High','None') },

              { section:'moe', field:'tester_major_gap_threshold', label:'Tester: Major Gap Cutoff',
                vtype:'select',
                options:[
                  {v:'55', label:'55 — Very lenient'},
                  {v:'60', label:'60'},
                  {v:'65', label:'65 — Default (recommended)', rec:true},
                  {v:'70', label:'70 — Strict'},
                ],
                desc:'Tester score < this = MAJOR_GAPS (−5% confidence). Must be below the minor-gap threshold.',
                effects: ef('Lower = more forgiving of MITRE gaps','Moderate','High','None') },

              { section:'moe', field:'red_team_hard_threshold', label:'Red Team: Hard-to-Exploit Limit',
                vtype:'select',
                options:[
                  {v:'30', label:'30 — Strict (fewer PASS)'},
                  {v:'35', label:'35'},
                  {v:'40', label:'40 — Default (recommended)', rec:true},
                  {v:'50', label:'50 — Lenient (more PASS)'},
                ],
                desc:'Red Team score ≤ this = PASS (hard to exploit, no penalty). Inverted scale — lower Red Team score = better security.',
                effects: ef('Defines "hard to exploit" boundary','Changes confidence outcome','Very High','None') },

              { section:'moe', field:'red_team_medium_threshold', label:'Red Team: Medium-Exploit Limit',
                vtype:'select',
                options:[
                  {v:'45', label:'45 — Strict'},
                  {v:'50', label:'50'},
                  {v:'55', label:'55 — Default (recommended)', rec:true},
                  {v:'60', label:'60 — Lenient'},
                ],
                desc:'Red Team score ≤ this (but > hard threshold) = MINOR_GAPS (−3% to −6%). Must be between hard and easy thresholds.',
                effects: ef('Moderate','Moderate','Very High','None') },

              { section:'moe', field:'red_team_easy_threshold', label:'Red Team: Easy-Exploit Limit',
                vtype:'select',
                options:[
                  {v:'60', label:'60 — Strict (−10% penalty triggers early)'},
                  {v:'65', label:'65'},
                  {v:'70', label:'70 — Default (recommended)', rec:true},
                  {v:'80', label:'80 — Lenient'},
                ],
                desc:'Red Team score > this = MAJOR_GAPS (−10% confidence). Must be above the medium threshold.',
                effects: ef('Controls when −10% penalty triggers','Controls penalty severity','Very High','None') },
            ]
          },
          {
            title: '🔒 Residual Risk',
            subtitle: 'Minimum risk floor and ACCEPT / MONITOR / MITIGATE decision thresholds.',
            fields: [
              { section:'residual_risk', field:'min_failure_probability', label:'Min Failure Probability',
                vtype:'select',
                options:[
                  {v:'0.05', label:'0.05 — Very optimistic (5% floor)'},
                  {v:'0.08', label:'0.08 — Optimistic'},
                  {v:'0.10', label:'0.10 — Default / NIST standard (recommended)', rec:true},
                  {v:'0.15', label:'0.15 — Conservative (15% floor)'},
                  {v:'0.20', label:'0.20 — Very conservative (20% floor)'},
                ],
                desc:'Minimum residual failure rate — controls can never reduce risk below this floor (NIST principle). 10% is the industry-standard lower bound.',
                effects: ef('Lower = more optimistic (riskier)','Higher = more conservative residual risk','Very High','None') },

              { section:'residual_risk', field:'accept_threshold', label:'ACCEPT Threshold',
                vtype:'select',
                options:[
                  {v:'5',  label:'5 — Very strict (few ACCEPTs)'},
                  {v:'8',  label:'8'},
                  {v:'10', label:'10 — Default (recommended)', rec:true},
                  {v:'15', label:'15 — Lenient (more ACCEPTs)'},
                ],
                desc:'Residual risk score < this → ACCEPT (low risk, quarterly monitoring only).',
                effects: ef('Higher = more findings become ACCEPT','Fewer MONITOR/MITIGATE findings','High','None') },

              { section:'residual_risk', field:'monitor_threshold', label:'MONITOR Threshold',
                vtype:'select',
                options:[
                  {v:'15', label:'15 — Strict (more MITIGATEs)'},
                  {v:'18', label:'18'},
                  {v:'20', label:'20 — Default (recommended)', rec:true},
                  {v:'25', label:'25 — Lenient (more MONITORs)'},
                ],
                desc:'Residual risk score < this (but ≥ ACCEPT) → MONITOR. Above this → MITIGATE. Must be above ACCEPT threshold.',
                effects: ef('Higher = more findings become MONITOR','Fewer MITIGATE findings','High','None') },
            ]
          },
          {
            title: '🤖 LLM & System',
            subtitle: 'Default LLM behaviour, file upload limits, and report storage path.',
            fields: [
              { section:'llm', field:'temperature', label:'LLM Default Temperature',
                vtype:'select',
                options:[
                  {v:'0.3', label:'0.3 — Near-deterministic'},
                  {v:'0.5', label:'0.5 — Moderately deterministic'},
                  {v:'0.7', label:'0.7 — Default (recommended)', rec:true},
                  {v:'1.0', label:'1.0 — More creative / varied output'},
                ],
                desc:'Default LLM sampling temperature for analysis calls (synthesis has its own separate temperature setting above).',
                effects: ef('Lower = more reproducible','Lower = less varied output','Moderate','None') },

              { section:'llm', field:'max_tokens', label:'LLM Default Max Tokens',
                vtype:'select',
                options:[
                  {v:'500',  label:'500 — Brief responses'},
                  {v:'800',  label:'800'},
                  {v:'1000', label:'1000 — Default (recommended)', rec:true},
                  {v:'1500', label:'1500 — Detailed responses'},
                  {v:'2000', label:'2000 — Extended (slower, costlier)'},
                ],
                desc:'Default max tokens per LLM response for non-synthesis calls. 1000 tokens is sufficient for most analysis prompts.',
                effects: ef('Higher = more complete responses','Higher = richer analysis text','Low','Higher = slower') },

              { section:'system', field:'report_dir', label:'Report Output Directory',
                vtype:'string',
                desc:'Path where reports are saved. Use a relative path from the project root (e.g. "report") or an absolute path. Restart not needed — takes effect on next analysis.',
                effects: ef('N/A','Where reports are written and served from','None','I/O location') },

              { section:'system', field:'max_file_size_mb', label:'Max Upload File Size (MB)',
                vtype:'select',
                options:[
                  {v:'5',  label:'5 MB — Small diagrams only'},
                  {v:'10', label:'10 MB — Default (recommended)', rec:true},
                  {v:'20', label:'20 MB — Large diagrams'},
                  {v:'50', label:'50 MB — Very large (validate server memory)'},
                ],
                desc:'Maximum .mmd architecture file size accepted by the API.',
                effects: ef('N/A','Larger = accepts bigger diagrams','None','None') },
            ]
          },
        ];

        // ── Warning banner ────────────────────────────────────────────────────
        const warningBanner = `
            <div style="display:flex; gap:0.9rem; align-items:flex-start; padding:1rem 1.25rem; background:#f59e0b14; border:1px solid #f59e0b44; border-radius:10px; margin-bottom:1.25rem;">
                <span style="font-size:1.4rem; flex-shrink:0; line-height:1.2;">⚠️</span>
                <div style="font-size:0.84rem; color:var(--text-color); line-height:1.65;">
                    <strong style="color:#f59e0b;">Use defaults unless you have a specific reason to change them.</strong><br>
                    These settings affect how threats are scored, how confidence is calculated, and how the expert panel decides what to flag.
                    Wrong values can cause the engine to under-report risks, inflate confidence, or produce inconsistent results.<br>
                    <span style="color:var(--text-secondary); font-size:0.8rem;">
                        Options marked <strong style="color:#0d9f6e;">(recommended)</strong> are the validated production defaults.
                        Use <strong>↺ Reset to Defaults</strong> at any time to undo all changes.
                        Changes take effect on the next analysis — not retroactively on existing reports.
                    </span>
                </div>
            </div>`;

        // ── Provider chain status block ───────────────────────────────────────
        const pc = data._provider_chain || {};
        const creds = pc.credentials || {};
        const notes = pc.notes || {};
        const flagHtml = (val) => {
            if (val === 'not_used') return `<span style="color:#64748b; font-size:0.82rem;">— not in chain</span>`;
            return val === 'set'
                ? `<span style="color:#0d9f6e; font-weight:700;">✅ Set</span>`
                : `<span style="color:#ef4444; font-weight:700;">❌ Not set</span>`;
        };
        const providerBodyId = 'cfg-section-body-provider';
        const providerHtml = `
            <div class="card" style="margin-bottom:1rem;">
                <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1.1rem; cursor:pointer; user-select:none;"
                     onclick="(function(el){var b=document.getElementById('${providerBodyId}');var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.cfg-chev').textContent=open?'▶':'▼';})(this)">
                    <div>
                        <span style="font-weight:700; font-size:0.95rem;">🔑 LLM Provider Chain</span>
                        <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">Read-only — configure in .env</span>
                    </div>
                    <span class="cfg-chev" style="font-size:0.7rem; color:var(--text-secondary);">▼</span>
                </div>
                <div id="${providerBodyId}" style="border-top:1px solid var(--border-color); padding:0.9rem 1.1rem;">
                    <table style="width:100%; border-collapse:collapse; font-size:0.84rem;">
                        <tr style="border-bottom:1px solid var(--border-color);">
                            <td style="padding:0.4rem 0; color:var(--text-secondary); width:210px; vertical-align:top;">Active chain</td>
                            <td style="font-weight:700; color:var(--primary-color);">${pc.provider_chain || '—'}</td>
                        </tr>
                        <tr style="border-bottom:1px solid var(--border-color);">
                            <td style="padding:0.4rem 0; color:var(--text-secondary); vertical-align:top;">Verifier / Judge</td>
                            <td>${pc.verifier_provider || '—'}</td>
                        </tr>
                        <tr style="border-bottom:1px solid var(--border-color);">
                            <td style="padding:0.4rem 0; color:var(--text-secondary); vertical-align:top;">OpenRouter API Key</td>
                            <td>${flagHtml(creds.OPENROUTER_API_KEY)}</td>
                        </tr>
                        <tr style="border-bottom:1px solid var(--border-color);">
                            <td style="padding:0.4rem 0; color:var(--text-secondary); vertical-align:top;">
                                AWS Bedrock API Key
                                <div style="font-size:0.7rem; color:#64748b; margin-top:0.15rem;">${notes.AWS_BEDROCK_API_KEY || ''}</div>
                            </td>
                            <td>
                                ${flagHtml(creds.AWS_BEDROCK_API_KEY)}
                                ${creds.AWS_BEDROCK_API_KEY === 'set' ? `<div style="font-size:0.7rem; color:#64748b; margin-top:0.15rem;">${notes.LLM_FALLBACK_PROVIDERS || ''}</div>` : ''}
                            </td>
                        </tr>
                        <tr style="border-bottom:1px solid var(--border-color);">
                            <td style="padding:0.4rem 0; color:var(--text-secondary); vertical-align:top;">Anthropic API Key</td>
                            <td>${flagHtml(creds.ANTHROPIC_API_KEY)}</td>
                        </tr>
                        <tr>
                            <td style="padding:0.4rem 0; color:var(--text-secondary); vertical-align:top;">Dashboard API Key</td>
                            <td>${flagHtml(creds.API_KEY)}</td>
                        </tr>
                    </table>
                </div>
            </div>`;

        // ── Filter chips ──────────────────────────────────────────────────────
        const chipStyle = `display:inline-flex; align-items:center; padding:0.3rem 0.85rem; border-radius:20px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); font-size:0.8rem; cursor:pointer; white-space:nowrap; transition:background 0.15s, color 0.15s, border-color 0.15s; user-select:none;`;
        const chips = [
            {filter:'quick',      label:'⚡ Quick Setup'},
            {filter:'all',        label:'📋 All Settings'},
            {filter:'engine',     label:'🔍 Engine'},
            {filter:'conf_risk',  label:'📊 Confidence & Risk'},
            {filter:'moe',        label:'🧑‍🏫 MoE / Experts'},
            {filter:'llm_system', label:'🤖 LLM & System'},
            {filter:'patterns',   label:'🧩 Patterns'},
            {filter:'provider',   label:'🔑 Provider Chain'},
        ].map(c => `<button class="cfg-chip" data-filter="${c.filter}" style="${chipStyle}">${c.label}</button>`).join('');
        const filterRow = `<div id="cfg-filter-chips" style="display:flex; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem;">${chips}</div>`;

        // ── Quick Setup card (only shown when filter='quick') ─────────────────
        const qSec = data.moe || {}, qEng = data.engine || {}, qSys = data.system || {};
        const qSelStyle = `padding:0.35rem 0.6rem; border:1px solid var(--border-color); border-radius:6px; background:#1e293b; color:#e2e8f0; font-size:0.84rem; cursor:pointer; width:100%; box-sizing:border-box; color-scheme:dark;`;
        const qRow = (label, hint, inputHtml) => `
            <div style="display:grid; grid-template-columns:minmax(160px,1fr) minmax(240px,320px) minmax(200px,2fr); gap:1rem; align-items:start; padding:0.65rem 1.1rem; border-bottom:1px solid var(--border-color);">
                <div style="font-weight:600; font-size:0.84rem; color:var(--text-color);">${label}</div>
                <div>${inputHtml}</div>
                <div style="color:var(--text-secondary); font-size:0.78rem; line-height:1.5;">${hint}</div>
            </div>`;
        const mkSel = (section, field, opts, curVal) => {
            const oHtml = opts.map(o => `<option value="${o.v}" ${curVal===o.v?'selected':''}>${o.label}</option>`).join('');
            return `<select data-section="${section}" data-field="${field}" data-vtype="string" style="${qSelStyle}">${oHtml}</select>`;
        };
        const critModeOpts = [{v:'sequential',label:'sequential (recommended)'},{v:'parallel',label:'parallel (faster)'},{v:'auto',label:'auto'}];
        const maxPathsOpts = [{v:'5',label:'5'},{v:'10',label:'10 (recommended)'},{v:'15',label:'15'},{v:'25',label:'25'}];
        const topNOpts     = [{v:'3',label:'3'},{v:'5',label:'5 (recommended)'},{v:'8',label:'8'},{v:'10',label:'10'}];

        // Pattern toggles
        const catalog = data._patterns_catalog || {};
        const patToggleRows = (() => {
            // Per-pattern inline config definitions.
            // Fields are rendered using the same select/string vtype system as _renderConfigSection.
            const patternConfigs = {
                'ai_ml_arc': {
                    settingsLabel: '⚙ AI/ML Scoring Thresholds',
                    settingsId: 'pat-cfg-ai_ml_arc',
                    fields: [
                        { section:'ai_pattern', field:'category_entry_threshold', label:'Category Entry Threshold',
                          vtype:'select', options:[
                            {v:'30', label:'30 — Very sensitive (flag most categories)'},
                            {v:'40', label:'40 — Sensitive'},
                            {v:'50', label:'50 — Default (recommended)', rec:true},
                            {v:'60', label:'60 — Conservative (fewer flags)'},
                          ],
                          desc:'Minimum ARC risk score for a category to produce any control recommendation. Categories below this score are skipped entirely.' },
                        { section:'ai_pattern', field:'priority_threshold_integrity', label:'Priority Threshold — Integrity',
                          vtype:'select', options:[
                            {v:'70', label:'70 — Lower bar'},
                            {v:'75', label:'75 — Moderate'},
                            {v:'80', label:'80 — Default (recommended)', rec:true},
                            {v:'90', label:'90 — Strict'},
                          ],
                          desc:'Integrity risk at or above which input_validation and prompt_filtering are flagged as priority.' },
                        { section:'ai_pattern', field:'priority_threshold_safety', label:'Priority Threshold — Safety',
                          vtype:'select', options:[
                            {v:'75', label:'75 — Lower bar'},
                            {v:'80', label:'80 — Moderate'},
                            {v:'85', label:'85 — Default (recommended)', rec:true},
                            {v:'90', label:'90 — Strict'},
                          ],
                          desc:'Safety risk at or above which content_moderation and sandbox are flagged as priority.' },
                        { section:'ai_pattern', field:'priority_threshold_security', label:'Priority Threshold — Security',
                          vtype:'select', options:[
                            {v:'75', label:'75 — Lower bar'},
                            {v:'80', label:'80 — Moderate'},
                            {v:'85', label:'85 — Default (recommended)', rec:true},
                            {v:'90', label:'90 — Strict'},
                          ],
                          desc:'Security risk at or above which api_key_rotation and secrets_management are flagged as priority.' },
                        { section:'ai_pattern', field:'priority_threshold_privacy', label:'Priority Threshold — Privacy',
                          vtype:'select', options:[
                            {v:'70', label:'70 — Lower bar'},
                            {v:'75', label:'75 — Moderate'},
                            {v:'80', label:'80 — Default (recommended)', rec:true},
                            {v:'90', label:'90 — Strict'},
                          ],
                          desc:'Privacy risk at or above which pii_detection and data_loss_prevention are flagged as priority.' },
                        { section:'ai_pattern', field:'floor_threshold_transparency', label:'Floor — Transparency',
                          vtype:'select', options:[
                            {v:'50', label:'50 — Lower bar'},
                            {v:'60', label:'60 — Default (recommended)', rec:true},
                            {v:'70', label:'70 — Stricter'},
                          ],
                          desc:'Transparency risk at or above which logging and audit_trails are recommended.' },
                        { section:'ai_pattern', field:'floor_threshold_accountability', label:'Floor — Accountability',
                          vtype:'select', options:[
                            {v:'60', label:'60 — Lower bar'},
                            {v:'70', label:'70 — Default (recommended)', rec:true},
                            {v:'80', label:'80 — Stricter'},
                          ],
                          desc:'Accountability risk at or above which human_oversight and incident_response are recommended.' },
                    ]
                },
                'cloud': {
                    settingsLabel: '⚙ Cloud Risk Thresholds',
                    settingsId: 'pat-cfg-cloud',
                    fields: [
                        { section:'cloud_pattern', field:'base_risk_iam_abuse', label:'Base Risk — IAM Abuse',
                          vtype:'select', options:[
                            {v:'60', label:'60 — Low-sensitivity'},
                            {v:'70', label:'70 — Moderate'},
                            {v:'80', label:'80 — Default (recommended)', rec:true},
                            {v:'90', label:'90 — High-sensitivity'},
                          ],
                          desc:'Starting risk score for IAM abuse (privilege escalation, credential theft). Applies to IAM, API gateway, and compute nodes — all cloud workloads have attached execution roles.' },
                        { section:'cloud_pattern', field:'base_risk_data_exposure', label:'Base Risk — Data Exposure',
                          vtype:'select', options:[
                            {v:'55', label:'55 — Low-sensitivity'},
                            {v:'65', label:'65 — Moderate'},
                            {v:'75', label:'75 — Default (recommended)', rec:true},
                            {v:'85', label:'85 — High-sensitivity'},
                          ],
                          desc:'Starting risk score for data exposure (storage misconfiguration, object ACL). Applies to S3, Blob, GCS, and database nodes.' },
                        { section:'cloud_pattern', field:'base_risk_api_abuse', label:'Base Risk — API / CDN Abuse',
                          vtype:'select', options:[
                            {v:'50', label:'50 — Low'},
                            {v:'60', label:'60 — Moderate'},
                            {v:'70', label:'70 — Default (recommended)', rec:true},
                            {v:'80', label:'80 — High-sensitivity'},
                          ],
                          desc:'Starting risk score for API/CDN abuse (metadata SSRF, session theft, WAF bypass). Applies to API gateways, CloudFront, Cloudflare, Akamai, load balancers, and web app nodes.' },
                        { section:'cloud_pattern', field:'base_risk_compute_abuse', label:'Base Risk — Compute / GenAI Abuse',
                          vtype:'select', options:[
                            {v:'45', label:'45 — Low'},
                            {v:'55', label:'55 — Moderate'},
                            {v:'65', label:'65 — Default (recommended)', rec:true},
                            {v:'75', label:'75 — High-sensitivity'},
                          ],
                          desc:'Starting risk score for compute abuse (serverless, container escape, cryptomining). Applies to EC2, Lambda, Kubernetes, and generic cloud application nodes.' },
                        { section:'cloud_pattern', field:'base_risk_network_lateral', label:'Base Risk — Lateral Movement',
                          vtype:'select', options:[
                            {v:'40', label:'40 — Low'},
                            {v:'50', label:'50 — Moderate'},
                            {v:'60', label:'60 — Default (recommended)', rec:true},
                            {v:'70', label:'70 — High-sensitivity'},
                          ],
                          desc:'Starting risk score for lateral movement (VPC peering, cross-account trust, boundary bridging).' },
                        { section:'cloud_pattern', field:'base_risk_logging_gaps', label:'Base Risk — Logging Gaps',
                          vtype:'select', options:[
                            {v:'50', label:'50 — Low'},
                            {v:'60', label:'60 — Default (recommended)', rec:true},
                            {v:'70', label:'70 — High-sensitivity'},
                          ],
                          desc:'Starting risk score for logging gaps (audit log tampering, CloudTrail disable). Floor must not exceed this value.' },
                        { section:'cloud_pattern', field:'floor_iam_no_mfa_pam', label:'Risk Floor — IAM (no MFA + no PAM)',
                          vtype:'select', options:[
                            {v:'60', label:'60 — Lenient'},
                            {v:'70', label:'70 — Moderate'},
                            {v:'75', label:'75 — Default (recommended)', rec:true},
                            {v:'80', label:'80 — Strict'},
                          ],
                          desc:'Minimum IAM risk when both MFA and privileged access management are absent. Must not exceed Base Risk — IAM Abuse.' },
                        { section:'cloud_pattern', field:'priority_threshold_iam', label:'Priority Threshold — IAM Controls',
                          vtype:'select', options:[
                            {v:'65', label:'65 — Lower bar'},
                            {v:'70', label:'70 — Moderate'},
                            {v:'75', label:'75 — Default (recommended)', rec:true},
                            {v:'80', label:'80 — Higher bar'},
                          ],
                          desc:'IAM risk at or above which MFA, least-privilege, and PAM are recommended as priority controls.' },
                    ]
                }
            };

            const inpStyle = `width:100%; padding:0.38rem 0.6rem; border:1px solid var(--border-color); border-radius:6px; background:#1e293b; color:#e2e8f0; font-size:0.84rem; cursor:pointer; box-sizing:border-box; color-scheme:dark;`;

            const mkPatRow = (f, sectionData) => {
                const currentVal = sectionData[f.field] !== undefined ? String(sectionData[f.field]) : '';
                let inputHtml = '';
                if (f.vtype === 'select') {
                    const opts = f.options.map(o => {
                        const sel = (o.v === currentVal) ? 'selected' : '';
                        const recBadge = o.rec ? ' <span style="color:#0d9f6e; font-size:0.72rem;">(recommended)</span>' : '';
                        return `<option value="${o.v}" ${sel}>${o.label}${o.rec ? ' ★' : ''}</option>`;
                    }).join('');
                    inputHtml = `<select data-section="${f.section}" data-field="${f.field}" style="${inpStyle}" onchange="window.dashboard._onConfigFieldChange(this)">${opts}</select>`;
                }
                return `<div style="display:grid; grid-template-columns:minmax(160px,1fr) minmax(180px,240px) minmax(160px,2fr); gap:0.75rem; align-items:start; padding:0.5rem 1.1rem; border-bottom:1px solid var(--border-color)08;">
                    <div style="font-weight:500; font-size:0.82rem; color:var(--text-color); padding-top:0.3rem;">${f.label}</div>
                    <div>${inputHtml}</div>
                    <div style="font-size:0.76rem; color:var(--text-secondary); line-height:1.5; padding-top:0.2rem;">${f.desc}</div>
                </div>`;
            };

            return Object.entries(catalog).map(([pid, p]) => {
                const isActive = p.status === 'active';
                const badgeHtml = isActive
                    ? `<span style="padding:1px 6px; border-radius:3px; font-size:0.68rem; font-weight:700; background:#0d9f6e18; border:1px solid #0d9f6e44; color:#0d9f6e;">✓ Active</span>`
                    : `<span style="padding:1px 6px; border-radius:3px; font-size:0.68rem; font-weight:700; background:#64748b14; border:1px solid #64748b33; color:#64748b;">Coming soon</span>`;
                const statusDot = isActive
                    ? `<span style="display:inline-flex; align-items:center; gap:0.3rem; font-size:0.73rem; color:#0d9f6e;"><span style="width:7px;height:7px;border-radius:50%;background:#0d9f6e;flex-shrink:0;"></span>Auto-detected</span>`
                    : `<span style="display:inline-flex; align-items:center; gap:0.3rem; font-size:0.73rem; color:#64748b;"><span style="width:7px;height:7px;border-radius:50%;background:#334155;border:1px solid #64748b;flex-shrink:0;"></span>Not yet available</span>`;

                const patCfg = patternConfigs[pid];
                let settingsHtml = '';
                if (isActive && patCfg) {
                    const sectionData = data[patCfg.fields[0].section] || {};
                    // Build config rows using live data
                    const cfgRows = patCfg.fields.map(f => {
                        const sd = data[f.section] || {};
                        return mkPatRow(f, sd);
                    }).join('');
                    settingsHtml = `
                    <div style="border-top:1px solid var(--border-color);">
                        <div style="display:flex; align-items:center; justify-content:space-between; padding:0.45rem 1.1rem; cursor:pointer; user-select:none; background:#1e293b44;"
                             onclick="(function(el){var b=el.nextElementSibling;if(!b)return;var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.pat-chev').textContent=open?'▶':'▼';})(this)">
                            <span style="font-size:0.78rem; color:var(--text-secondary);">${patCfg.settingsLabel}</span>
                            <span class="pat-chev" style="font-size:0.65rem; color:var(--text-tertiary);">▼</span>
                        </div>
                        <div id="${patCfg.settingsId}" style="display:block;">${cfgRows}</div>
                    </div>`;
                }

                return `
                <div style="border-bottom:1px solid var(--border-color);">
                    <div style="display:flex; align-items:flex-start; gap:1rem; padding:0.75rem 1.1rem;">
                        <div style="flex:1; min-width:0;">
                            <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                                <span style="font-weight:600; font-size:0.88rem;">${p.name}</span>
                                ${badgeHtml}
                                ${statusDot}
                            </div>
                            <div style="color:var(--text-secondary); font-size:0.78rem; margin-top:0.25rem; line-height:1.5;">${p.description}</div>
                            ${p.arch_types && p.arch_types.length ? `<div style="margin-top:0.3rem; display:flex; flex-wrap:wrap; gap:0.25rem;">${p.arch_types.map(t => `<span style="padding:1px 5px; border-radius:3px; font-size:0.68rem; background:#1e293b; border:1px solid #334155; color:#94a3b8;">${t}</span>`).join('')}</div>` : ''}
                            ${p.requires && p.requires.length ? `<div style="font-size:0.71rem; color:#64748b; margin-top:0.2rem;">Requires: ${p.requires.join(' · ')}</div>` : ''}
                        </div>
                    </div>
                    ${settingsHtml}
                </div>`;
            }).join('');
        })();
        const patternsCard = `
            <div class="card" data-cfg-cat="patterns" style="margin-bottom:1rem;">
                <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1.1rem; cursor:pointer; user-select:none;"
                     onclick="(function(el){var b=document.getElementById('cfg-section-body-patterns');var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.cfg-chev').textContent=open?'▶':'▼';})(this)">
                    <div>
                        <span style="font-weight:700; font-size:0.95rem;">🧩 Threat Patterns</span>
                        <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">Threat patterns activate automatically when matching architecture components are detected — read only</span>
                    </div>
                    <span class="cfg-chev" style="font-size:0.7rem; color:var(--text-secondary);">▼</span>
                </div>
                <div id="cfg-section-body-patterns" style="border-top:1px solid var(--border-color);">
                    ${patToggleRows}
                </div>
            </div>`;

        // ── Quick Setup card body ─────────────────────────────────────────────
        const quickCard = `
            <div id="cfg-quick-card" style="display:none; margin-bottom:1rem;">
                <div class="card" style="margin-bottom:0.75rem;">
                    <div style="padding:0.75rem 1.1rem; border-bottom:1px solid var(--border-color);">
                        <span style="font-weight:700; font-size:0.95rem;">⚡ Quick Setup</span>
                        <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">The 5 most impactful settings — change only these if unsure</span>
                    </div>
                    ${qRow('Critic Mode', 'Sequential is most accurate. Switch to Parallel to speed up Expert Review.',
                        mkSel('moe','critic_mode', critModeOpts, String(qSec.critic_mode||'sequential')))}
                    ${qRow('Max Attack Paths', 'Higher = deeper BFS search, slower analysis.',
                        mkSel('engine','max_paths', maxPathsOpts, String(qEng.max_paths||'10')))}
                    ${qRow('Top-N Paths Kept', 'How many ranked paths appear in the report.',
                        mkSel('engine','top_n', topNOpts, String(qEng.top_n||'5')))}
                    ${qRow('Report Output Directory',
                        'Relative to project root or absolute path.',
                        `<input type="text" data-section="system" data-field="report_dir" data-vtype="string" value="${(qSys.report_dir||'report').replace(/"/g,'&quot;')}" style="${qSelStyle}" />`)}
                    <div style="padding:0.65rem 1.1rem;">
                        <div style="font-weight:600; font-size:0.84rem; color:var(--text-color); margin-bottom:0.5rem;">Threat Patterns</div>
                        ${patToggleRows}
                    </div>
                </div>
            </div>`;

        // Add data-cfg-cat attribute to each section card via wrapper
        const sectionCatMap = {
            '🔍 Analysis Engine':        'engine',
            '📊 Confidence Calculation': 'confidence',
            '🧑‍🏫 MoE / Expert Review':  'moe',
            '🔒 Residual Risk':          'residual_risk',
            '🤖 LLM & System':           'llm_system',
        };

        const sectionCards = sections.map(s => {
            const cat = sectionCatMap[s.title] || 'other';
            const html = this._renderConfigSection(s, data);
            // Inject data-cfg-cat into the outer div of the card
            return html.replace('<div class="card"', `<div class="card" data-cfg-cat="${cat}"`);
        }).join('');

        // Provider card also gets a cat
        const providerHtmlWithCat = providerHtml.replace(
            '<div class="card" style="margin-bottom:1rem;">',
            '<div class="card" data-cfg-cat="provider" style="margin-bottom:1rem;">'
        );

        return filterRow + warningBanner + quickCard + providerHtmlWithCat + sectionCards + patternsCard;
    }

    async _togglePattern(patternId, enabled) {
        const apiKey = localStorage.getItem('tm_api_key') || '';
        // Build new enabled_patterns list from all currently-checked pattern toggles
        const allToggles = document.querySelectorAll('[data-pattern-id]');
        const enabledList = [];
        allToggles.forEach(t => {
            // Use the just-changed value for the toggled pattern, current state for others
            const shouldEnable = t.dataset.patternId === patternId ? enabled : t.checked;
            if (shouldEnable) enabledList.push(t.dataset.patternId);
        });
        try {
            const resp = await fetch('/api/v1/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'TM-API-KEY': apiKey },
                body: JSON.stringify({ patterns: { enabled_patterns: enabledList } })
            });
            const data = await resp.json();
            if (!resp.ok) {
                this._showConfigStatus('error', `Pattern update failed: ${data.detail || 'error'}`);
                return;
            }
            this._configData = data.config;
            this._showConfigStatus('success', `Pattern "${patternId}" ${enabled ? 'enabled' : 'disabled'}. Takes effect on next analysis.`);
        } catch (err) {
            this._showConfigStatus('error', `Pattern update failed: ${err.message}`);
        }
    }

    _renderConfigSection(sectionDef, data) {
        const cs = `color:var(--text-secondary); font-size:0.78rem;`;
        const sectionId = 'cfg-section-body-' + sectionDef.title.replace(/\W+/g,'').toLowerCase();
        const inpStyle = `width:100%; padding:0.38rem 0.6rem; border:1px solid var(--border-color); border-radius:6px; background:#1e293b; color:#e2e8f0; font-size:0.84rem; cursor:pointer; box-sizing:border-box; color-scheme:dark;`;

        const rows = sectionDef.fields.map(f => {
            const sectionData = data[f.section] || {};
            const currentVal  = sectionData[f.field] !== undefined ? String(sectionData[f.field]) : '';
            let inputHtml;

            if (f.vtype === 'select') {
                // Options format: [{v, label, rec?}]  OR  [string, ...]
                const opts = f.options.map(o => {
                    const optVal   = typeof o === 'object' ? o.v   : o;
                    const optLabel = typeof o === 'object' ? o.label : o;
                    const isRec    = typeof o === 'object' && o.rec;
                    // Highlight recommended option label
                    const display  = isRec
                        ? optLabel.replace('(recommended)', '<span style="color:#0d9f6e;">(recommended)</span>')
                        : optLabel;
                    const sel = (currentVal === optVal || (currentVal === '' && isRec)) ? 'selected' : '';
                    return `<option value="${optVal}" ${sel}>${optLabel}</option>`;
                }).join('');
                inputHtml = `<select data-section="${f.section}" data-field="${f.field}" data-vtype="string" style="${inpStyle}">${opts}</select>`;

            } else if (f.vtype === 'string') {
                inputHtml = `<input type="text" data-section="${f.section}" data-field="${f.field}" data-vtype="string"
                    value="${currentVal}" style="${inpStyle}" />`;
            } else {
                // int / float — show a free input with recommended cap warning
                const overRec = f.recMax !== undefined && parseFloat(currentVal) > f.recMax;
                const recBadge = overRec
                    ? `<div style="margin-top:0.25rem; font-size:0.7rem; color:#f59e0b;">⚠ Exceeds recommended max (${f.recMax})</div>`
                    : '';
                inputHtml = `<input type="number" data-section="${f.section}" data-field="${f.field}" data-vtype="${f.vtype}"
                    value="${currentVal}" min="${f.min}" max="${f.max}" step="${f.step}"
                    style="${inpStyle}" />` + recBadge;
            }

            return `
            <div style="display:grid; grid-template-columns:minmax(180px,1fr) minmax(240px,320px) minmax(220px,2fr); gap:1rem; align-items:start; padding:0.65rem 1.1rem; border-bottom:1px solid var(--border-color);">
                <div>
                    <div style="font-weight:600; font-size:0.84rem; color:var(--text-color);">${f.label}</div>
                    <div style="${cs} margin-top:0.15rem;">Default: ${currentVal || '—'}</div>
                </div>
                <div style="padding-top:0.05rem;">${inputHtml}</div>
                <div style="${cs} padding-top:0.05rem; line-height:1.55;">
                    ${f.desc}
                    ${f.effects || ''}
                </div>
            </div>`;
        }).join('');

        return `
        <div class="card" style="margin-bottom:1rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1.1rem; cursor:pointer; user-select:none;"
                 onclick="(function(el){var b=document.getElementById('${sectionId}');var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.cfg-chev').textContent=open?'▶':'▼';})(this)">
                <div>
                    <span style="font-weight:700; font-size:0.95rem;">${sectionDef.title}</span>
                    <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">${sectionDef.subtitle}</span>
                </div>
                <span class="cfg-chev" style="font-size:0.7rem; color:var(--text-secondary);">▼</span>
            </div>
            <div id="${sectionId}" style="border-top:1px solid var(--border-color);">
                ${rows}
            </div>
        </div>`;
    }
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});
