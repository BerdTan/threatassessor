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

    _setOverviewDetailVisible(visible) {
        const detail = document.getElementById('overview-detail');
        const banner = document.getElementById('overview-running-banner');
        if (!detail) return;
        if (visible) {
            detail.style.display = '';
            if (banner) banner.style.display = 'none';
        } else {
            detail.style.display = 'none';
            // Show/create a slim banner in its place
            if (banner) {
                banner.style.display = 'flex';
            } else {
                const b = document.createElement('div');
                b.id = 'overview-running-banner';
                b.style.cssText = 'margin-top:1.25rem; padding:0.75rem 1rem; background:var(--card-bg); border:1px solid var(--border-color); border-radius:8px; display:flex; align-items:center; gap:0.6rem; font-size:0.85rem; color:var(--text-tertiary);';
                b.innerHTML = '<span style="animation:spin 1.2s linear infinite; display:inline-block;">⏳</span> Expert Consensus and Architecture Diagram will appear here once analysis completes.';
                detail.parentNode.insertBefore(b, detail.nextSibling);
            }
        }
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
        this._analysing = true;
        this._setContentTabsDisabled(true);
        this._setOverviewDetailVisible(false);

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
            // RAPIDS is universal (always present) — skip its badge to avoid header noise
            if (pattern.pattern_id === 'rapids') return;
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
        this._analysing = false;
        this._setContentTabsDisabled(false);
        this._setOverviewDetailVisible(true);

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

        // Restore overview detail (so it's visible when next analysis loads)
        this._analysing = false;
        this._setOverviewDetailVisible(true);

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
        let moeExpertValidationsOuter = {};
        try {
            const moeResp = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (moeResp.ok) {
                const moe = await moeResp.json();
                moeExpertValidationsOuter = moe.expert_validations || {};
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

        // Build Expert Review synthesis summary for Overview — one plain-English "biggest gap" sentence
        let moeOverviewSummary = '';
        if (hasMoe) {
            // Find the single biggest confidence drop across expert validations
            let biggestDrop = null;
            let biggestDropLabel = '';
            let biggestDropDesc = '';
            const expertValidationsOv = moeExpertValidationsOuter;
            const criticLabels = { architect: 'Architecture Review', tester: 'Coverage Audit', red_team: 'Exploit Analysis', purple_team: 'Purple Team', blackhat: 'Blackhat' };
            for (const [key, ev] of Object.entries(expertValidationsOv)) {
                const adj = ev.confidence_adjustment || 0;
                if (adj < 0 && (biggestDrop === null || adj < biggestDrop)) {
                    biggestDrop = adj;
                    biggestDropLabel = criticLabels[key] || key;
                    // Get the top gap description
                    const gaps = ev.gaps || [];
                    const topGap = gaps.find(g => ['CRITICAL','HIGH'].includes((g.severity || '').toUpperCase())) || gaps[0];
                    biggestDropDesc = topGap ? (topGap.description || '') : (ev.summary || '');
                }
            }

            // Also check consensus KNOWN findings for the top recommendation
            const topKnown = moeKnownFindings[0];
            const topRec = topKnown ? (topKnown.recommendation || topKnown.description || '') : '';

            let summaryLine = '';
            if (biggestDrop !== null && biggestDropDesc) {
                const dropPct = Math.abs(Math.round(biggestDrop * 100));
                summaryLine = `<strong>${biggestDropLabel}</strong> flagged: "${biggestDropDesc}" — this is pulling confidence down by <strong>${dropPct}%</strong>.`;
            } else if (topRec) {
                summaryLine = `Top finding: "${topRec}"`;
            } else {
                summaryLine = 'No critical multi-expert findings — strong security posture.';
            }

            moeOverviewSummary = '<div style="background:var(--primary-color)0e; border:1px solid var(--primary-color)44; border-radius:8px; padding:0.75rem 1rem; margin-bottom:1.25rem;">'
                + '<div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.35rem;">'
                + '<span style="font-size:0.9375rem;">🧑‍🏫</span>'
                + '<span style="font-size:0.8125rem; font-weight:700; color:var(--primary-color);">Expert Review validated — ' + validatedConf.toFixed(1) + '% confidence</span>'
                + '</div>'
                + '<div style="font-size:0.875rem; color:var(--text-color); line-height:1.55;">' + summaryLine + '</div>'
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
        if (!container) return;
        if (this._analysing) {
            container.innerHTML = '<p class="placeholder" style="font-size:0.85rem; color:var(--text-tertiary);">⏳ Analysis in progress — Architecture Diagram will appear here once complete.</p>';
            return;
        }
        if (!this.uploadedFile) return;

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
        // Replaced by renderExpertConsensusStrip — kept as no-op to avoid call-site errors
        this.renderExpertConsensusStrip();
    }

    async renderExpertConsensusStrip() {
        const strip = document.getElementById('expert-consensus-strip');
        if (!strip) return;

        if (this._analysing) {
            strip.innerHTML = '<p class="placeholder" style="font-size:0.85rem; color:var(--text-tertiary);">⏳ Analysis in progress — Expert Consensus will appear here once complete.</p>';
            return;
        }

        const archName = this.analysisData?.architecture_name || this.analysisData?.architecture || '';
        if (!archName) {
            strip.innerHTML = '<p class="placeholder" style="font-size:0.85rem;">Load an architecture analysis first.</p>';
            return;
        }

        let moe = null;
        try {
            const r = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (r.ok) moe = await r.json();
        } catch (_) {}

        if (!moe) {
            strip.innerHTML = '<p class="placeholder" style="font-size:0.85rem;">Run Expert Review to see critic consensus here.</p>';
            return;
        }

        const ev = moe.expert_validations || {};
        const adj = moe.confidence?.adjustments || {};
        const tradeoffs = moe.mode_tradeoffs || [];
        const mode = moe.mode || 'sequential';

        const CRITIC_DEFS = [
            { key: 'architect',   icon: '🏛️', label: 'Architecture Review',   desc: 'Structural gaps, unmodelled threats, ADR completeness' },
            { key: 'tester',      icon: '🔬', label: 'Coverage Audit',         desc: 'MITRE mapping accuracy, control effectiveness, configuration validation' },
            { key: 'red_team',    icon: '🎯', label: 'Exploit Analysis',        desc: 'Bypass paths, control evasion, attack feasibility under active exploitation' },
            { key: 'purple_team', icon: '🟣', label: 'Purple Team',             desc: 'Detection depth, coverage gaps, investigation value & ADR operability' },
            { key: 'blackhat',    icon: '⚔️', label: 'Blackhat Cross-Path',     desc: 'Cross-path chaining, pivot-diverge routes & chain exploits (supreme critic)' },
        ];

        const STATUS_CHIP = {
            'PASS':        { color: 'var(--secondary-color)', label: 'PASS',        tip: 'No significant issues found' },
            'MINOR_GAPS':  { color: 'var(--warning-color)',   label: 'MINOR GAPS',  tip: 'Small gaps found — low exploitability' },
            'MAJOR_GAPS':  { color: 'var(--danger-color)',    label: 'MAJOR GAPS',  tip: 'Significant issues — high exploitability risk' },
            'FAIL':        { color: 'var(--danger-color)',    label: 'FAIL',         tip: 'Critical failures — immediate action required' },
        };

        // Legend
        const legendHtml = `
            <div style="display:flex;flex-wrap:wrap;gap:0.6rem;align-items:center;margin-bottom:0.85rem;padding:0.5rem 0.75rem;background:var(--nav-hover-bg);border-radius:6px;font-size:0.73rem;color:var(--text-tertiary);">
                <span style="font-weight:700;color:var(--text-secondary);">Status legend:</span>
                ${Object.entries(STATUS_CHIP).map(([k, v]) =>
                    `<span style="display:inline-flex;align-items:center;gap:0.3rem;"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${v.color};"></span>${v.label} — ${v.tip}</span>`
                ).join('')}
                <span style="margin-left:0.5rem;"><strong>Δ conf</strong> = change to overall confidence from this critic</span>
            </div>`;

        // Critic cards
        let cardsHtml = `<div style="display:flex;flex-wrap:wrap;gap:0.75rem;margin-bottom:${tradeoffs.length > 0 ? '0.85rem' : '0'};">`;
        CRITIC_DEFS.forEach(def => {
            const v = ev[def.key];
            if (!v) {
                // Not-run card
                cardsHtml += `
                    <div style="flex:1;min-width:200px;max-width:320px;padding:0.85rem 1rem;background:var(--card-bg);border-radius:10px;border:1px solid var(--border-color);opacity:0.45;">
                        <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;">
                            <span style="font-size:1.25rem;">${def.icon}</span>
                            <span style="font-weight:700;font-size:0.85rem;color:var(--text-tertiary);">${def.label}</span>
                        </div>
                        <div style="font-size:0.75rem;color:var(--text-tertiary);font-style:italic;">Not run this session</div>
                    </div>`;
                return;
            }
            const status = v.validation_status || 'UNKNOWN';
            const chip   = STATUS_CHIP[status] || { color: 'var(--text-tertiary)', label: status, tip: '' };
            const adjPct = parseFloat(((adj[def.key] || 0) * 100).toFixed(1));
            const adjStr = adjPct === 0 ? '±0%' : (adjPct > 0 ? '+' : '') + adjPct + '%';
            const adjColor = adjPct < 0 ? 'var(--warning-color)' : adjPct === 0 ? 'var(--text-tertiary)' : 'var(--secondary-color)';
            const score  = v.original_score ?? '–';
            // Full verdict text — all gaps listed, or strengths fallback
            const allGaps = (v.gaps && v.gaps.length > 0)
                ? v.gaps.map(g => g.description || '').filter(Boolean)
                : [];
            const verdictFull = allGaps.length > 0
                ? allGaps.join(' · ')
                : (v.strengths && v.strengths.length > 0 ? 'Strengths confirmed; no critical gaps.' : def.desc);
            const PREVIEW_LEN = 120;
            const needsExpand = verdictFull.length > PREVIEW_LEN;
            const verdictPreview = needsExpand ? verdictFull.slice(0, PREVIEW_LEN).trimEnd() + '…' : verdictFull;
            const cardId = 'ec-card-' + def.key;

            cardsHtml += `
                <div id="${cardId}" style="flex:1;min-width:200px;max-width:320px;padding:0.85rem 1rem;background:var(--card-bg);border-radius:10px;border:1px solid ${chip.color}44;transition:box-shadow 0.15s;">
                    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.45rem;">
                        <span style="font-size:1.25rem;">${def.icon}</span>
                        <span style="font-weight:700;font-size:0.85rem;color:var(--text-color);">${def.label}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">
                        <span style="padding:0.1rem 0.5rem;background:${chip.color}22;color:${chip.color};border-radius:4px;font-size:0.7rem;font-weight:700;">${chip.label}</span>
                        <span style="font-size:0.78rem;font-weight:700;color:${adjColor};">Δ ${adjStr}</span>
                        <span style="margin-left:auto;font-size:0.72rem;color:var(--text-tertiary);">score ${score}/100</span>
                    </div>
                    <div style="font-size:0.78rem;color:var(--text-secondary);line-height:1.5;">
                        <span class="ec-preview">${verdictPreview}</span>
                        ${needsExpand ? `<span class="ec-full" style="display:none;">${verdictFull}</span>
                        <a href="#" style="display:inline-block;margin-top:0.2rem;font-size:0.72rem;color:var(--primary-color);text-decoration:none;" onclick="(function(a){var card=a.closest('[id^=ec-card-]');var pre=card.querySelector('.ec-preview');var full=card.querySelector('.ec-full');var isExpanded=full.style.display!=='none';pre.style.display=isExpanded?'':'none';full.style.display=isExpanded?'none':'';a.textContent=isExpanded?'…more':'less ↑';})(this);return false;">…more</a>` : ''}
                    </div>
                    <div style="margin-top:0.55rem;padding-top:0.45rem;border-top:1px solid var(--border-color);font-size:0.71rem;color:var(--text-tertiary);cursor:pointer;" onclick="window.dashboard?.switchTab('expert-review')" title="Open Expert Review">
                        Open full review →
                    </div>
                </div>`;
        });
        cardsHtml += '</div>';

        // Mode tradeoff note
        let tradeoffNote = '';
        if (tradeoffs.length > 0) {
            tradeoffNote = `
                <div style="padding:0.6rem 0.85rem;background:var(--warning-color)12;border-left:3px solid var(--warning-color);border-radius:6px;font-size:0.78rem;color:var(--text-secondary);">
                    <strong style="color:var(--warning-color);">Mode tradeoffs (${mode})</strong>
                    <ul style="margin:0.3rem 0 0;padding-left:1.2rem;">
                        ${tradeoffs.map(t => `<li style="margin-bottom:0.2rem;">${t}</li>`).join('')}
                    </ul>
                </div>`;
        }

        strip.innerHTML = legendHtml + cardsHtml + tradeoffNote;
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

        // Pre-compute aggregate counts for display in filter header
        const countByPriority = { critical: 0, high: 0, medium: 0, low: 0 };
        const countByDir = { prevention: 0, detect: 0, isolate: 0, respond: 0, other: 0 };
        let sspMapped = 0;
        for (const c of controlRecs) {
            if (c.priority in countByPriority) countByPriority[c.priority]++;
            const dc = (c.dir_category || '').toLowerCase();
            if (dc === 'prevention' || dc === 'hardening' || dc === 'governance') countByDir.prevention++;
            else if (dc === 'detect' || dc === 'detection') countByDir.detect++;
            else if (dc === 'isolate') countByDir.isolate++;
            else if (dc === 'respond' || dc === 'response') countByDir.respond++;
            else countByDir.other++;
            if (c.ssp_context && c.ssp_context.primary) sspMapped++;
        }

        // Render control recommendations with search, priority + dir_category filters, collapse/expand
        tableContainer.innerHTML = `
            <div style="margin-bottom: 0.75rem; padding: 0.85rem 1rem; background: var(--nav-hover-bg); border-radius: 8px;">
                <div style="display:flex; gap:0.6rem; align-items:center; flex-wrap:wrap; margin-bottom:0.6rem;">
                    <input id="ctrl-search" type="search" placeholder="🔍 Search controls…"
                        style="flex:1; min-width:160px; padding:0.35rem 0.65rem; border:1px solid var(--border-color); border-radius:6px; background:var(--main-bg); color:var(--text-color); font-size:0.83rem;">
                    <button id="ctrl-expand-all" title="Expand all" style="padding:0.3rem 0.65rem; border-radius:6px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); font-size:0.8rem; cursor:pointer;">⊞ Expand all</button>
                    <button id="ctrl-collapse-all" title="Collapse all" style="padding:0.3rem 0.65rem; border-radius:6px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); font-size:0.8rem; cursor:pointer;">⊟ Collapse all</button>
                </div>
                <div style="display:flex; gap:0.75rem; flex-wrap:wrap; align-items:center; margin-bottom:0.45rem;">
                    <span style="font-size:0.78rem; font-weight:600; color:var(--text-tertiary);">Priority:</span>
                    <label style="display:flex; align-items:center; gap:0.3rem; cursor:pointer; font-size:0.82rem;">
                        <input type="checkbox" class="priority-checkbox" value="critical" checked style="cursor:pointer;">
                        <span style="color:var(--danger-color); font-weight:700;">CRITICAL <span style="font-size:0.7rem; font-weight:400; color:var(--text-tertiary);">(${countByPriority.critical})</span></span>
                    </label>
                    <label style="display:flex; align-items:center; gap:0.3rem; cursor:pointer; font-size:0.82rem;">
                        <input type="checkbox" class="priority-checkbox" value="high" checked style="cursor:pointer;">
                        <span style="color:var(--warning-color); font-weight:700;">HIGH <span style="font-size:0.7rem; font-weight:400; color:var(--text-tertiary);">(${countByPriority.high})</span></span>
                    </label>
                    <label style="display:flex; align-items:center; gap:0.3rem; cursor:pointer; font-size:0.82rem;">
                        <input type="checkbox" class="priority-checkbox" value="medium" checked style="cursor:pointer;">
                        <span style="color:var(--primary-color); font-weight:700;">MEDIUM <span style="font-size:0.7rem; font-weight:400; color:var(--text-tertiary);">(${countByPriority.medium})</span></span>
                    </label>
                    <button id="select-all-filter" style="padding:0.2rem 0.55rem; border-radius:5px; background:var(--secondary-color)22; color:var(--secondary-color); border:1px solid var(--secondary-color); cursor:pointer; font-size:0.76rem; font-weight:600;">All</button>
                    <button id="reset-filter" style="padding:0.2rem 0.55rem; border-radius:5px; background:transparent; color:var(--text-tertiary); border:1px solid var(--border-color); cursor:pointer; font-size:0.76rem;">None</button>
                </div>
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center; margin-bottom:0.45rem;">
                    <span style="font-size:0.78rem; font-weight:600; color:var(--text-tertiary);">ZT Layer:</span>
                    <button class="dir-btn active" data-dir="all" style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid var(--border-color); background:var(--primary-color)22; color:var(--primary-color); cursor:pointer; font-size:0.76rem; font-weight:600;">All</button>
                    <button class="dir-btn" data-dir="prevention" style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); cursor:pointer; font-size:0.76rem;">🛡 Prevent <span style="opacity:0.6;">(${countByDir.prevention})</span></button>
                    <button class="dir-btn" data-dir="detect" style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); cursor:pointer; font-size:0.76rem;">🔍 Detect <span style="opacity:0.6;">(${countByDir.detect})</span></button>
                    <button class="dir-btn" data-dir="isolate" style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); cursor:pointer; font-size:0.76rem;">🔒 Isolate <span style="opacity:0.6;">(${countByDir.isolate})</span></button>
                    <button class="dir-btn" data-dir="respond" style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid var(--border-color); background:var(--card-bg); color:var(--text-secondary); cursor:pointer; font-size:0.76rem;">⚡ Respond <span style="opacity:0.6;">(${countByDir.respond})</span></button>
                    <button class="dir-btn" data-dir="ssp" style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid #0891b244; background:var(--card-bg); color:#06b6d4; cursor:pointer; font-size:0.76rem;">🏛 SSP-mapped <span style="opacity:0.6;">(${sspMapped})</span></button>
                </div>
                <div style="margin-top:0.3rem; font-size:0.8rem; color:var(--text-secondary);">
                    Showing <strong id="control-count">${controlRecs.length}</strong> of ${controlRecs.length} controls · Total: ${controlRecs.length} · SSP-mapped: ${sspMapped}
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
        // Multi-select ZT layer filter: empty Set = "All"
        let _activeDirFilters = new Set();

        const _DIR_ALIASES = {
            prevention: ['prevention', 'hardening', 'governance'],
            detect:     ['detect', 'detection'],
            isolate:    ['isolate', 'response'],
            respond:    ['respond', 'response'],
        };

        const renderControls = (selectedPriorities = ['critical', 'high', 'medium']) => {
            controlsList.innerHTML = '';
            const searchVal = (tableContainer.querySelector('#ctrl-search')?.value || '').toLowerCase();

            const filteredControls = controlRecs.filter(c => {
                if (!selectedPriorities.includes(c.priority)) return false;
                if (_activeDirFilters.size > 0) {
                    // Multi-select: match if control satisfies ANY active filter
                    const dirCat = (c.dir_category || '').toLowerCase();
                    const hasSsp = c.ssp_context && c.ssp_context.primary;
                    const matches = [..._activeDirFilters].some(f => {
                        if (f === 'ssp') return hasSsp;
                        const allowed = _DIR_ALIASES[f] || [f];
                        return allowed.includes(dirCat);
                    });
                    if (!matches) return false;
                }
                if (searchVal) {
                    const hay = ((c.control || '') + ' ' + (c.rationale || '') + ' ' + (c.placement || '')).toLowerCase();
                    if (!hay.includes(searchVal)) return false;
                }
                return true;
            });

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

                const card = document.createElement('details');
                card.className = 'list-item';
                card.dataset.priority = control.priority;
                card.style.cssText = `
                    margin-bottom: 0.6rem;
                    background: var(--card-bg);
                    border-radius: 8px;
                    border-left: 4px solid ${priorityColor};
                    overflow: hidden;
                `;

                const dirCatLabel = (control.dir_category || 'prevention').charAt(0).toUpperCase() + (control.dir_category || 'prevention').slice(1);
                card.innerHTML = `
                    <summary style="padding:0.75rem 1rem; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:0.5rem; list-style:none; user-select:none;">
                        <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; flex:1; min-width:0;">
                            <strong style="font-size:0.92rem; color:var(--primary-color); white-space:nowrap;">${this._esc(control.control)}</strong>
                            <span style="padding:0.15rem 0.5rem; background:${priorityColor}22; color:${priorityColor}; border-radius:8px; font-size:0.68rem; font-weight:700; text-transform:uppercase; flex-shrink:0;">${control.priority}</span>
                            <span style="padding:0.15rem 0.5rem; background:var(--border-color); color:var(--text-tertiary); border-radius:8px; font-size:0.68rem; font-weight:600; flex-shrink:0;">${this._esc(dirCatLabel)}</span>
                            ${sourceTag}
                            ${sspBadge}
                        </div>
                        <div style="text-align:right; flex-shrink:0; min-width:60px;">
                            <div style="font-size:0.95rem; font-weight:700; color:${priorityColor};">${control.score ? control.score.toFixed(1) : 'N/A'}</div>
                            <div style="font-size:0.64rem; color:var(--text-tertiary);">${(control.score || 0) >= 20 ? 'high' : (control.score || 0) >= 10 ? 'medium' : 'lower'} impact</div>
                        </div>
                    </summary>
                    <div style="padding:0.75rem 1rem; border-top:1px solid var(--border-color);">
                        ${arcCats ? `<div style="font-size:0.75rem; color:#a78bfa; margin-bottom:0.35rem;">ARC categories: ${arcCats}</div>` : ''}
                        <div style="font-size:0.85rem; color:var(--text-secondary); margin-bottom:0.5rem; line-height:1.55;">${control.rationale}</div>
                        <div style="display:flex; gap:1rem; font-size:0.79rem; color:var(--text-tertiary); margin-bottom:0.5rem; flex-wrap:wrap;">
                            <span>📍 ${control.attack_paths ? control.attack_paths.length : 0} paths</span>
                            <span>🎯 ${control.techniques ? control.techniques.length : 0} ${isArc ? 'ATLAS' : 'Enterprise'} techniques</span>
                            <span>🛡️ ${control.mitigations ? control.mitigations.length : 0} mitigations</span>
                        </div>
                        ${control.control_type ? `<div style="font-size:0.79rem; color:var(--text-tertiary); padding-top:0.4rem; border-top:1px solid var(--border-color)22;"><strong>Implementation:</strong> ${this._esc(control.control_type)}${control.layer ? ` | ${this._esc(control.layer)}` : ''}${control.placement ? ` | ${this._esc(control.placement)}` : ''}</div>` : ''}
                        <div style="margin-top:0.5rem;">
                            <button style="padding:0.2rem 0.6rem; border-radius:5px; border:1px solid var(--border-color); background:var(--nav-hover-bg); color:var(--primary-color); cursor:pointer; font-size:0.76rem; font-weight:600;">View full details →</button>
                        </div>
                    </div>
                `;

                card.querySelector('button').addEventListener('click', (e) => {
                    e.stopPropagation();
                    controlsList.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                    card.classList.add('active');
                    this.showControlDetail(control);
                });

                controlsList.appendChild(card);
            });
        };

        const _getSelected = () => Array.from(tableContainer.querySelectorAll('.priority-checkbox')).filter(cb => cb.checked).map(cb => cb.value);
        const _rerender = () => renderControls(_getSelected());

        // Initial render
        renderControls(['critical', 'high', 'medium']);

        // Priority checkbox listeners
        tableContainer.querySelectorAll('.priority-checkbox').forEach(cb => cb.addEventListener('change', _rerender));

        tableContainer.querySelector('#select-all-filter').addEventListener('click', () => {
            tableContainer.querySelectorAll('.priority-checkbox').forEach(cb => cb.checked = true);
            _rerender();
        });
        tableContainer.querySelector('#reset-filter').addEventListener('click', () => {
            tableContainer.querySelectorAll('.priority-checkbox').forEach(cb => cb.checked = false);
            _rerender();
        });

        // Dir filter buttons — multi-select toggle (click to add/remove, All deselects everything)
        tableContainer.querySelectorAll('.dir-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const dir = btn.dataset.dir;
                if (dir === 'all') {
                    // Clear all selections → show everything
                    _activeDirFilters.clear();
                    tableContainer.querySelectorAll('.dir-btn').forEach(b => {
                        if (b.dataset.dir === 'all') {
                            b.style.background = 'var(--primary-color)22';
                            b.style.color = 'var(--primary-color)';
                            b.classList.add('active');
                        } else {
                            b.style.background = 'var(--card-bg)';
                            b.style.color = 'var(--text-secondary)';
                            b.classList.remove('active');
                        }
                    });
                } else {
                    // Toggle this filter on/off
                    if (_activeDirFilters.has(dir)) {
                        _activeDirFilters.delete(dir);
                        btn.style.background = 'var(--card-bg)';
                        btn.style.color = 'var(--text-secondary)';
                        btn.classList.remove('active');
                    } else {
                        _activeDirFilters.add(dir);
                        btn.style.background = 'var(--primary-color)22';
                        btn.style.color = 'var(--primary-color)';
                        btn.classList.add('active');
                    }
                    // Deactivate the "All" button when specific filters are set
                    const allBtn2 = tableContainer.querySelector('.dir-btn[data-dir="all"]');
                    if (allBtn2) {
                        if (_activeDirFilters.size > 0) {
                            allBtn2.style.background = 'var(--card-bg)';
                            allBtn2.style.color = 'var(--text-secondary)';
                            allBtn2.classList.remove('active');
                        } else {
                            allBtn2.style.background = 'var(--primary-color)22';
                            allBtn2.style.color = 'var(--primary-color)';
                            allBtn2.classList.add('active');
                        }
                    }
                }
                _rerender();
            });
        });

        // Search box
        tableContainer.querySelector('#ctrl-search').addEventListener('input', _rerender);

        // Expand / Collapse all
        tableContainer.querySelector('#ctrl-expand-all').addEventListener('click', () => {
            controlsList.querySelectorAll('details').forEach(d => d.open = true);
        });
        tableContainer.querySelector('#ctrl-collapse-all').addEventListener('click', () => {
            controlsList.querySelectorAll('details').forEach(d => d.open = false);
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
        const blackhat = analysis.blackhat_critique || null;

        if (attackPaths.length === 0) {
            listContainer.innerHTML = '<p class="placeholder">No attack paths available</p>';
            return;
        }

        // --- Graceful D3 fallback ---
        if (typeof d3 === 'undefined') {
            console.warn('[Visualise] D3 not loaded — falling back to card list');
            this._loadHardeningTabCards(listContainer, attackPaths, controlRecs);
            return;
        }

        // ─── AP colour palette ───────────────────────────────────────────────────
        const AP_PALETTE = ['#4da6ff', '#51cf66', '#ff6b6b', '#cc5de8', '#ffd43b'];
        const BH_COLOR   = '#ff8c00';
        const MULTI_COLOR = '#64748b';

        // Map AP id → palette index (AP-1 → 0, AP-2 → 1, …)
        const apColorMap = {};
        attackPaths.forEach((ap, i) => {
            apColorMap[ap.id] = AP_PALETTE[i % AP_PALETTE.length];
        });

        // ─── Build pivot node set (BH shared_nodes + pivot_diverge_chains) ─────────
        const sharedPivotSet = new Set();
        if (blackhat) {
            (blackhat.shared_nodes || []).forEach(n => sharedPivotSet.add(n));
            (blackhat.pivot_diverge_chains || []).forEach(chain => {
                if (chain.pivot) sharedPivotSet.add(chain.pivot);
            });
        }

        // Track entry and exit (target) nodes across all APs
        const entryNodes  = new Set(attackPaths.map(ap => ap.entry).filter(Boolean));
        const targetNodes = new Set(attackPaths.map(ap => ap.target).filter(Boolean));

        const nodeMap = {}; // id → { id, label, aps: [apId, …], isSharedPivot, isEntry, isTarget }
        attackPaths.forEach(ap => {
            (ap.path || []).forEach(nodeName => {
                if (!nodeMap[nodeName]) {
                    nodeMap[nodeName] = {
                        id: nodeName,
                        label: nodeName,
                        aps: [],
                        isSharedPivot: sharedPivotSet.has(nodeName),
                        isEntry: entryNodes.has(nodeName),
                        isTarget: targetNodes.has(nodeName)
                    };
                }
                if (!nodeMap[nodeName].aps.includes(ap.id)) {
                    nodeMap[nodeName].aps.push(ap.id);
                }
            });
        });
        const nodes = Object.values(nodeMap);

        // ─── Build edge list ─────────────────────────────────────────────────────
        const edges = [];
        const edgeSet = new Set();
        attackPaths.forEach(ap => {
            const path = ap.path || [];
            for (let i = 0; i < path.length - 1; i++) {
                const key = `${ap.id}::${path[i]}→${path[i+1]}`;
                if (!edgeSet.has(key)) {
                    edgeSet.add(key);
                    edges.push({
                        source: path[i],
                        target: path[i+1],
                        apId: ap.id,
                        criticality: ap.criticality_tier,
                        color: apColorMap[ap.id] || AP_PALETTE[0],
                        dashed: false
                    });
                }
            }
        });

        // BH chain edges
        const bhEdges = [];
        if (blackhat && blackhat.least_resistance_paths && blackhat.least_resistance_paths.length > 0) {
            blackhat.least_resistance_paths.forEach(lrp => {
                const chain = lrp.chain || [];
                if (chain.length >= 2) {
                    bhEdges.push({
                        source: chain[0],
                        target: chain[1],
                        apId: 'BH',
                        pivot: lrp.pivot || '',
                        criticality: lrp.chain_criticality || '',
                        color: BH_COLOR,
                        dashed: true
                    });
                }
            });
        }
        const allEdges = edges.concat(bhEdges);

        // ─── Render shell HTML ───────────────────────────────────────────────────
        const chipIds = attackPaths.map(ap => ap.id);
        const hasBH = bhEdges.length > 0;

        // Build chip HTML
        let chipHtml = '';
        attackPaths.forEach((ap, i) => {
            const color = AP_PALETTE[i % AP_PALETTE.length];
            chipHtml += `<button class="vg-chip" data-ap="${ap.id}" data-active="1" style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.2rem 0.65rem;border-radius:12px;border:2px solid ${color};background:${color}22;color:${color};font-size:0.78rem;font-weight:700;cursor:pointer;transition:all 0.15s;">`
                + `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};"></span>${ap.id}</button>`;
        });
        if (hasBH) {
            chipHtml += `<button class="vg-chip" data-ap="BH" data-active="1" style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.2rem 0.65rem;border-radius:12px;border:2px solid ${BH_COLOR};background:${BH_COLOR}22;color:${BH_COLOR};font-size:0.78rem;font-weight:700;cursor:pointer;transition:all 0.15s;">`
                + `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${BH_COLOR};"></span>&#9876; BH</button>`;
        }
        chipHtml += `<button id="vg-all-btn" style="padding:0.2rem 0.65rem;border-radius:12px;border:1px solid var(--border-color);background:var(--nav-hover-bg);color:var(--text-secondary);font-size:0.78rem;cursor:pointer;">ALL</button>`;
        chipHtml += `<button id="vg-reset-btn" style="padding:0.2rem 0.65rem;border-radius:12px;border:1px solid var(--border-color);background:var(--nav-hover-bg);color:var(--text-secondary);font-size:0.78rem;cursor:pointer;">RESET</button>`;

        // Build legend HTML
        let legendHtml = '<div style="display:flex;flex-wrap:wrap;gap:0.6rem;align-items:center;font-size:0.75rem;">';
        attackPaths.forEach((ap, i) => {
            const color = AP_PALETTE[i % AP_PALETTE.length];
            legendHtml += `<span style="display:inline-flex;align-items:center;gap:0.3rem;"><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:${color};"></span><span style="color:var(--text-secondary);">${ap.id} — ${ap.entry || ''} → ${ap.target || ''}</span></span>`;
        });
        if (hasBH) {
            legendHtml += `<span style="display:inline-flex;align-items:center;gap:0.3rem;"><span style="display:inline-block;width:18px;height:3px;background:${BH_COLOR};border-top:2px dashed ${BH_COLOR};"></span><span style="color:var(--text-secondary);">BH chain</span></span>`;
        }
        legendHtml += `<span style="display:inline-flex;align-items:center;gap:0.3rem;"><svg width="14" height="14" viewBox="-8 -8 16 16"><circle cx="0" cy="0" r="6" fill="#64748b" stroke="#dc2626" stroke-width="2"/></svg><span style="color:var(--text-secondary);">Entry</span></span>`;
        legendHtml += `<span style="display:inline-flex;align-items:center;gap:0.3rem;"><svg width="14" height="14" viewBox="-8 -8 16 16"><circle cx="0" cy="0" r="6" fill="#64748b" stroke="#f97316" stroke-width="2"/></svg><span style="color:var(--text-secondary);">Target</span></span>`;
        if (sharedPivotSet.size > 0) {
            legendHtml += `<span style="display:inline-flex;align-items:center;gap:0.3rem;"><svg width="14" height="14" viewBox="-8 -8 16 16"><polygon points="0,-7 7,0 0,7 -7,0" fill="none" stroke="${BH_COLOR}" stroke-width="2"/></svg><span style="color:var(--text-secondary);">Pivot node (diamond + amber ring)</span></span>`;
        }
        legendHtml += '</div>';

        listContainer.innerHTML = `
            <div style="margin-bottom:0.75rem;">
                <h4 style="margin:0 0 0.5rem;font-size:0.95rem;color:var(--primary-color);">Attack Path Graph</h4>
                <div id="vg-chips" style="display:flex;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.5rem;">${chipHtml}</div>
                <div id="vg-legend" style="margin-bottom:0.6rem;">${legendHtml}</div>
            </div>
            <div id="vg-svg-wrap" style="width:100%;border-radius:8px;border:1px solid var(--border-color);background:var(--code-bg);overflow:hidden;">
                <svg id="vg-svg" width="100%" height="480" style="display:block;"></svg>
            </div>
            <div id="vg-pivot-info" style="display:none;margin-top:0.75rem;padding:0.65rem 1rem;background:${BH_COLOR}18;border-left:4px solid ${BH_COLOR};border-radius:6px;font-size:0.82rem;color:var(--text-secondary);"></div>
            <div id="vg-ap-picker" style="display:none;margin-top:0.75rem;padding:0.65rem 1rem;background:var(--nav-hover-bg);border-radius:6px;font-size:0.82rem;"></div>
            <p style="margin-top:0.5rem;font-size:0.78rem;color:var(--text-tertiary);">Click a node to drill into its attack path and control placement.</p>
        `;

        // ─── D3 force graph ──────────────────────────────────────────────────────
        const svgEl = document.getElementById('vg-svg');
        const wrap  = document.getElementById('vg-svg-wrap');
        const W = wrap.clientWidth  || 800;
        const H = 480;
        svgEl.setAttribute('viewBox', `0 0 ${W} ${H}`);

        const svg = d3.select(svgEl);

        // Defs: arrowhead markers per AP color + BH
        const defs = svg.append('defs');
        const markerColors = Object.values(apColorMap).concat(hasBH ? [BH_COLOR] : []);
        const uniqueColors = [...new Set(markerColors)];
        uniqueColors.forEach(color => {
            const safeId = 'arrow-' + color.replace('#', '');
            defs.append('marker')
                .attr('id', safeId)
                .attr('viewBox', '0 -4 8 8')
                .attr('refX', 18)
                .attr('refY', 0)
                .attr('markerWidth', 6)
                .attr('markerHeight', 6)
                .attr('orient', 'auto')
              .append('path')
                .attr('d', 'M0,-4L8,0L0,4')
                .attr('fill', color);
        });

        // Link group
        const linkGroup = svg.append('g').attr('class', 'vg-links');
        // Node group
        const nodeGroup = svg.append('g').attr('class', 'vg-nodes');

        // Create D3 node/link data (copies for simulation)
        const simNodes = nodes.map(n => Object.assign({}, n));
        const nodeById = {};
        simNodes.forEach(n => { nodeById[n.id] = n; });

        const simEdges = allEdges.map(e => Object.assign({}, e, {
            source: e.source,
            target: e.target
        }));

        // Draw links
        const linkEls = linkGroup.selectAll('line')
            .data(simEdges)
            .enter().append('line')
            .attr('class', d => 'vg-edge vg-ap-' + d.apId)
            .attr('stroke', d => d.color)
            .attr('stroke-width', 2)
            .attr('stroke-dasharray', d => d.dashed ? '6 3' : null)
            .attr('marker-end', d => {
                const safeId = 'arrow-' + d.color.replace('#', '');
                return 'url(#' + safeId + ')';
            })
            .attr('opacity', 0.8);

        // Draw nodes
        const nodeEls = nodeGroup.selectAll('g.vg-node')
            .data(simNodes)
            .enter().append('g')
            .attr('class', 'vg-node')
            .style('cursor', 'pointer');

        // Pivot nodes: diamond (polygon) + amber ring; entry nodes: red ring; target nodes: orange ring; regular: circle
        const ENTRY_COLOR  = '#dc2626'; // red
        const TARGET_COLOR = '#f97316'; // orange
        nodeEls.each(function(d) {
            const g = d3.select(this);
            const fill = d.aps.length > 1 ? MULTI_COLOR : (apColorMap[d.aps[0]] || MULTI_COLOR);
            if (d.isSharedPivot) {
                const r = 26;
                // Outer amber ring (slightly larger diamond)
                g.append('polygon')
                    .attr('points', `0,${-(r+5)} ${r+5},0 0,${r+5} ${-(r+5)},0`)
                    .attr('fill', 'none')
                    .attr('stroke', BH_COLOR)
                    .attr('stroke-width', 3)
                    .attr('opacity', 0.85);
                // Inner filled diamond
                g.append('polygon')
                    .attr('points', `0,${-r} ${r},0 0,${r} ${-r},0`)
                    .attr('fill', fill)
                    .attr('stroke', BH_COLOR)
                    .attr('stroke-width', 2);
            } else {
                const ringColor = d.isEntry ? ENTRY_COLOR : d.isTarget ? TARGET_COLOR : null;
                if (ringColor) {
                    // Outer ring for entry/exit
                    g.append('circle')
                        .attr('r', 24)
                        .attr('fill', 'none')
                        .attr('stroke', ringColor)
                        .attr('stroke-width', 3)
                        .attr('opacity', 0.9);
                }
                g.append('circle')
                    .attr('r', 20)
                    .attr('fill', fill)
                    .attr('stroke', ringColor || 'none')
                    .attr('stroke-width', ringColor ? 2 : 0);
            }
        });

        nodeEls.append('text')
            .text(d => d.label.length > 14 ? d.label.substring(0, 12) + '…' : d.label)
            .attr('text-anchor', 'middle')
            .attr('dy', d => (d.isSharedPivot ? 32 : 22) + 12)
            .attr('font-size', '11px')
            .attr('fill', 'var(--text-secondary)')
            .style('pointer-events', 'none')
            .style('user-select', 'none');

        // ─── Simulation (static layout — tick 200 times then stop) ───────────────
        const simulation = d3.forceSimulation(simNodes)
            .force('link', d3.forceLink(simEdges).id(d => d.id).distance(120))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(W / 2, H / 2))
            .stop();

        // Run ticks synchronously
        for (let i = 0; i < 200; i++) simulation.tick();

        // Apply positions
        linkEls
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        nodeEls.attr('transform', d => `translate(${d.x},${d.y})`);

        // ─── Toggle chip logic ────────────────────────────────────────────────────
        const self = this;
        const activeAps = new Set([...chipIds, ...(hasBH ? ['BH'] : [])]);

        function applyToggles() {
            // Edges
            linkEls.style('display', d => activeAps.has(d.apId) ? null : 'none');

            // Nodes: show if at least one of their APs is active
            nodeEls.style('opacity', d => {
                const visible = d.aps.some(apId => activeAps.has(apId));
                return visible ? 1 : 0.18;
            });
        }

        listContainer.querySelectorAll('.vg-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const apId = chip.dataset.ap;
                const wasActive = chip.dataset.active === '1';
                if (wasActive) {
                    activeAps.delete(apId);
                    chip.dataset.active = '0';
                    chip.style.background = 'transparent';
                    chip.style.opacity = '0.45';
                } else {
                    activeAps.add(apId);
                    chip.dataset.active = '1';
                    const color = apId === 'BH' ? BH_COLOR : (apColorMap[apId] || AP_PALETTE[0]);
                    chip.style.background = color + '22';
                    chip.style.opacity = '1';
                }
                applyToggles();
            });
        });

        const allBtn   = document.getElementById('vg-all-btn');
        const resetBtn = document.getElementById('vg-reset-btn');

        if (allBtn) {
            allBtn.addEventListener('click', () => {
                [...chipIds, ...(hasBH ? ['BH'] : [])].forEach(id => activeAps.add(id));
                listContainer.querySelectorAll('.vg-chip').forEach(chip => {
                    chip.dataset.active = '1';
                    const color = chip.dataset.ap === 'BH' ? BH_COLOR : (apColorMap[chip.dataset.ap] || AP_PALETTE[0]);
                    chip.style.background = color + '22';
                    chip.style.opacity = '1';
                });
                applyToggles();
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                activeAps.clear();
                listContainer.querySelectorAll('.vg-chip').forEach(chip => {
                    chip.dataset.active = '0';
                    chip.style.background = 'transparent';
                    chip.style.opacity = '0.45';
                });
                applyToggles();
            });
        }

        // ─── Node click handler ───────────────────────────────────────────────────
        const pivotInfo  = document.getElementById('vg-pivot-info');
        const apPicker   = document.getElementById('vg-ap-picker');

        function showNodeDetail(nodeName, ap) {
            const rightPane        = document.getElementById('right-pane');
            const rightPaneContent = document.getElementById('right-pane-content');
            if (!rightPane || !rightPaneContent) return;

            const apIndex      = attackPaths.indexOf(ap);
            const pathControls = controlRecs.filter(c => c.attack_paths && c.attack_paths.includes(apIndex));

            // Per-node techniques from ground_truth per_node_techniques
            const perNodeTech = (self.analysisData?.analysis?.per_node_techniques || {})[nodeName] || [];

            // Controls specifically targeting this node (strict match — avoid laundry list)
            const nodeControls = pathControls.filter(c => {
                const targets = c.node_targets || c.apply_to_nodes || [];
                if (targets.length === 0) return false; // skip broadly-scoped controls with no node assignment
                return targets.some(t => t === nodeName || t.includes(nodeName) || nodeName.includes(t));
            });
            // Fallback: if no node-targeted controls exist, show all AP controls (broad coverage only)
            const displayControls = nodeControls.length > 0 ? nodeControls : pathControls;

            const isPivot = sharedPivotSet.has(nodeName);
            const pivotChains = isPivot
                ? (blackhat && blackhat.pivot_diverge_chains || []).filter(ch => ch.pivot === nodeName)
                : [];

            const critColor = ap.criticality_tier === 'CRITICAL' ? 'var(--danger-color)'
                : ap.criticality_tier === 'HIGH' ? 'var(--warning-color)'
                : 'var(--primary-color)';

            // Pivot section
            let pivotSection = '';
            if (isPivot) {
                const divergeTargets = pivotChains.flatMap(c => c.diverge_targets || []).join(', ') || ap.aps ? ap.aps.join(', ') : '–';
                pivotSection = `
                    <div style="margin-bottom:1.25rem;padding:0.75rem 1rem;background:${BH_COLOR}18;border-left:4px solid ${BH_COLOR};border-radius:6px;">
                        <div style="font-weight:700;color:${BH_COLOR};margin-bottom:0.35rem;">⬥ Pivot Node — Cross-Path Chaining Risk</div>
                        <p style="margin:0;font-size:0.85rem;color:var(--text-secondary);line-height:1.55;">
                            Compromising <strong>${nodeName}</strong> gives an attacker forked reach into
                            <strong>${divergeTargets}</strong>. Per-path controls cannot stop this branching —
                            a single breach here expands the blast radius across multiple attack paths simultaneously.
                        </p>
                    </div>`;
            }

            // Technique-control pairs
            let pairsHtml = '';
            if (perNodeTech.length > 0) {
                pairsHtml = '<h4 style="margin:0 0 0.65rem;font-size:0.9rem;color:var(--text-color);">Attack techniques at this node</h4>';
                self.fetchTechniqueNames(perNodeTech).then(techNames => {
                    const pairsContainer = document.getElementById('vg-tech-pairs');
                    if (!pairsContainer) return;
                    let html = '';
                    perNodeTech.forEach(techId => {
                        const techName = techNames[techId] || techId;
                        // Use displayControls (node-specific if available, else AP-broad)
                        const mitigating = displayControls.filter(c =>
                            (c.techniques || []).includes(techId)
                        );
                        const prioColor = mitigating.length > 0 ? 'var(--secondary-color)' : 'var(--warning-color)';
                        html += `<div style="margin-bottom:0.9rem;padding:0.75rem 0.9rem;background:var(--nav-hover-bg);border-radius:8px;border-left:3px solid ${prioColor};">`;
                        html += `<div style="font-size:0.82rem;font-weight:700;color:var(--text-color);margin-bottom:0.3rem;">${techId} — ${techName}</div>`;
                        if (mitigating.length > 0) {
                            mitigating.forEach(c => {
                                const pc = c.priority ? c.priority.toUpperCase() : 'BASELINE';
                                const pColor = pc === 'CRITICAL' ? 'var(--danger-color)' : pc === 'HIGH' ? 'var(--warning-color)' : 'var(--primary-color)';
                                html += `<div style="margin-top:0.35rem;display:flex;align-items:flex-start;gap:0.5rem;">`;
                                html += `<span style="padding:0.1rem 0.45rem;background:${pColor}22;color:${pColor};border-radius:4px;font-size:0.7rem;font-weight:700;white-space:nowrap;">${pc}</span>`;
                                html += `<span style="font-size:0.82rem;color:var(--text-secondary);line-height:1.5;">${c.control} — ${c.rationale || ''}</span>`;
                                html += `</div>`;
                            });
                        } else {
                            html += `<div style="font-size:0.8rem;color:var(--warning-color);margin-top:0.3rem;">⚠ No control mapped to this technique at this node</div>`;
                        }
                        html += `</div>`;
                    });
                    pairsContainer.innerHTML = html;
                });
            } else if (displayControls.length > 0) {
                // No per-node techniques but controls exist — show controls directly
                const isBroadFallback = nodeControls.length === 0;
                pairsHtml = `<h4 style="margin:0 0 0.65rem;font-size:0.9rem;color:var(--text-color);">${isBroadFallback ? 'Controls for this attack path' : 'Controls at this node'}</h4>`;
                if (isBroadFallback) {
                    pairsHtml += `<div style="font-size:0.75rem;color:var(--text-tertiary);margin-bottom:0.65rem;font-style:italic;">No node-specific controls assigned — showing all ${ap.id} path controls.</div>`;
                }
                displayControls.forEach(c => {
                    const pc = c.priority ? c.priority.toUpperCase() : 'BASELINE';
                    const pColor = pc === 'CRITICAL' ? 'var(--danger-color)' : pc === 'HIGH' ? 'var(--warning-color)' : 'var(--primary-color)';
                    pairsHtml += `<div style="margin-bottom:0.75rem;padding:0.65rem 0.9rem;background:var(--nav-hover-bg);border-radius:8px;border-left:3px solid ${pColor};">`;
                    pairsHtml += `<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.3rem;"><span style="padding:0.1rem 0.45rem;background:${pColor}22;color:${pColor};border-radius:4px;font-size:0.7rem;font-weight:700;">${pc}</span><strong style="font-size:0.85rem;">${c.control}</strong></div>`;
                    pairsHtml += `<p style="margin:0;font-size:0.82rem;color:var(--text-secondary);line-height:1.5;">${c.rationale || ''}</p>`;
                    pairsHtml += `</div>`;
                });
            } else {
                pairsHtml = `<p style="font-size:0.85rem;color:var(--warning-color);">⚠ No controls mapped to this node in ${ap.id}.</p>`;
            }

            // Node position in path
            const pathPos = ap.path ? ap.path.indexOf(nodeName) : -1;
            const posLabel = pathPos === 0 ? 'Entry Point' : pathPos === (ap.path || []).length - 1 ? 'Target' : `Traversal node (step ${pathPos + 1})`;

            rightPaneContent.innerHTML = `
                <div style="margin-bottom:1rem;">
                    <div style="font-size:0.75rem;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem;">${ap.id} · ${posLabel}</div>
                    <h3 style="margin:0 0 0.25rem;font-size:1.05rem;color:var(--text-color);">${nodeName}</h3>
                    <div style="font-size:0.82rem;color:var(--text-secondary);">${ap.entry || ''} → ${ap.target || ''}</div>
                    <span style="display:inline-block;margin-top:0.4rem;padding:0.15rem 0.6rem;background:${critColor}22;color:${critColor};border-radius:4px;font-size:0.72rem;font-weight:700;">${ap.criticality_tier || ''}</span>
                </div>
                ${pivotSection}
                <div id="vg-tech-pairs">${pairsHtml}</div>
            `;
            rightPane.classList.add('visible');
        }

        nodeEls.on('click', function(event, d) {
            event.stopPropagation();

            // Hide stale panels
            pivotInfo.style.display = 'none';
            apPicker.style.display  = 'none';

            // Highlight selected node
            nodeEls.selectAll('circle,polygon').attr('opacity', n => n.id === d.id ? 1 : 0.55);
            d3.select(this).selectAll('circle,polygon').attr('opacity', 1);

            if (d.aps.length === 1) {
                const ap = attackPaths.find(a => a.id === d.aps[0]);
                if (!ap) return;
                showNodeDetail(d.id, ap);
            } else {
                // Multi-AP node — show inline picker
                let pickerHtml = `<p style="margin:0 0 0.4rem;font-weight:600;color:var(--text-color);">
                    <strong>${d.id}</strong> appears in ${d.aps.length} attack paths — choose one to explore:</p>
                    <div style="display:flex;flex-wrap:wrap;gap:0.4rem;">`;
                d.aps.forEach(apId => {
                    const color = apColorMap[apId] || AP_PALETTE[0];
                    pickerHtml += `<button class="vg-picker-btn" data-apid="${apId}" style="padding:0.25rem 0.75rem;border-radius:8px;border:2px solid ${color};background:${color}22;color:${color};font-size:0.8rem;font-weight:700;cursor:pointer;">${apId}</button>`;
                });
                pickerHtml += `</div>`;
                apPicker.innerHTML = pickerHtml;
                apPicker.style.display = 'block';

                apPicker.querySelectorAll('.vg-picker-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        apPicker.style.display = 'none';
                        const ap = attackPaths.find(a => a.id === btn.dataset.apid);
                        if (!ap) return;
                        showNodeDetail(d.id, ap);
                    });
                });
            }
        });

        // Click on SVG background to deselect
        d3.select(svgEl).on('click', () => {
            nodeEls.selectAll('circle,polygon').attr('opacity', 1);
            pivotInfo.style.display = 'none';
            apPicker.style.display  = 'none';
        });
    }

    // ─── Fallback card list (used when D3 is unavailable) ────────────────────
    _loadHardeningTabCards(listContainer, attackPaths, controlRecs) {
        listContainer.innerHTML = `
            <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--nav-hover-bg); border-radius: 8px; border-left: 4px solid var(--primary-color);">
                <h4 style="margin-bottom: 0.75rem; font-size: 1rem; color: var(--primary-color);">Attack Path Controls</h4>
                <p style="color: var(--text-secondary); margin-bottom: 0; font-size: 0.875rem;">
                    Click an attack path to view its technique-control pairs in the detail panel.
                </p>
            </div>
        `;

        const sortedPaths = [...attackPaths].sort((a, b) => {
            const aIndex = attackPaths.indexOf(a);
            const bIndex = attackPaths.indexOf(b);
            const aControls = controlRecs.filter(c => c.attack_paths && c.attack_paths.includes(aIndex)).length;
            const bControls = controlRecs.filter(c => c.attack_paths && c.attack_paths.includes(bIndex)).length;
            if (bControls !== aControls) return bControls - aControls;
            const tierOrder = { 'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1 };
            return (tierOrder[b.criticality_tier] || 0) - (tierOrder[a.criticality_tier] || 0);
        });

        sortedPaths.forEach(path => {
            const pathIndex = attackPaths.indexOf(path);
            const pathControls = controlRecs.filter(c =>
                c.attack_paths && c.attack_paths.includes(pathIndex)
            );

            const criticalityColor =
                path.criticality_tier === 'CRITICAL' ? 'var(--danger-color)' :
                path.criticality_tier === 'HIGH' ? 'var(--warning-color)' :
                'var(--secondary-color)';

            const card = document.createElement('div');
            card.className = 'list-item';
            card.style.cssText = `padding:1rem;margin-bottom:0.75rem;background:var(--card-bg);border-radius:8px;border-left:4px solid ${criticalityColor};cursor:pointer;transition:all 0.2s;`;
            card.innerHTML = `
                <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.4rem;">
                    <strong style="font-size:1rem;color:var(--primary-color);">${path.id}</strong>
                    <span style="padding:0.15rem 0.6rem;background:${criticalityColor}22;color:${criticalityColor};border-radius:12px;font-size:0.72rem;font-weight:700;text-transform:uppercase;">${path.criticality_tier}</span>
                </div>
                <div style="font-size:0.875rem;color:var(--text-secondary);margin-bottom:0.35rem;">${path.entry} → ${path.target}</div>
                <div style="font-size:0.8rem;color:var(--text-tertiary);">🛡️ ${pathControls.length} control${pathControls.length !== 1 ? 's' : ''} &nbsp;|&nbsp; 🎯 ${path.techniques ? path.techniques.length : 0} techniques</div>
            `;
            card.addEventListener('click', () => {
                listContainer.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
                card.classList.add('active');
                this._showPathDetailPane(path, pathControls);
            });
            listContainer.appendChild(card);
        });
    }

    _showPathDetailPane(path, pathControls) {
        const rightPane        = document.getElementById('right-pane');
        const rightPaneContent = document.getElementById('right-pane-content');
        if (!rightPane || !rightPaneContent) return;

        const critColor = path.criticality_tier === 'CRITICAL' ? 'var(--danger-color)'
            : path.criticality_tier === 'HIGH' ? 'var(--warning-color)' : 'var(--primary-color)';

        let controlsHtml = '';
        if (pathControls.length === 0) {
            controlsHtml = `<p style="color:var(--warning-color);font-size:0.85rem;">No controls mapped for this attack path.</p>`;
        } else {
            pathControls.forEach(c => {
                const pc = (c.priority || 'baseline').toUpperCase();
                const pColor = pc === 'CRITICAL' ? 'var(--danger-color)' : pc === 'HIGH' ? 'var(--warning-color)' : 'var(--primary-color)';
                controlsHtml += `<div style="margin-bottom:0.75rem;padding:0.65rem 0.9rem;background:var(--nav-hover-bg);border-radius:8px;border-left:3px solid ${pColor};">`;
                controlsHtml += `<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.3rem;"><span style="padding:0.1rem 0.45rem;background:${pColor}22;color:${pColor};border-radius:4px;font-size:0.7rem;font-weight:700;">${pc}</span><strong style="font-size:0.85rem;">${c.control}</strong></div>`;
                controlsHtml += `<p style="margin:0;font-size:0.82rem;color:var(--text-secondary);line-height:1.5;">${c.rationale || ''}</p>`;
                if (c.techniques && c.techniques.length > 0) {
                    controlsHtml += `<div style="margin-top:0.3rem;font-size:0.75rem;color:var(--text-tertiary);">Mitigates: ${c.techniques.join(', ')}</div>`;
                }
                controlsHtml += `</div>`;
            });
        }

        rightPaneContent.innerHTML = `
            <div style="margin-bottom:1rem;">
                <div style="font-size:0.75rem;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem;">Attack Path</div>
                <h3 style="margin:0 0 0.25rem;font-size:1.05rem;color:var(--text-color);">${path.id}</h3>
                <div style="font-size:0.82rem;color:var(--text-secondary);">${path.entry} → ${path.target}</div>
                <span style="display:inline-block;margin-top:0.4rem;padding:0.15rem 0.6rem;background:${critColor}22;color:${critColor};border-radius:4px;font-size:0.72rem;font-weight:700;">${path.criticality_tier}</span>
            </div>
            <h4 style="margin:0 0 0.65rem;font-size:0.9rem;color:var(--text-color);">Controls for this path</h4>
            ${controlsHtml}
        `;
        rightPane.classList.add('visible');
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
                ${techniques.size} techniques identified across ${attackPaths.length} attack paths
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
        const layout = document.getElementById('tm-layout');
        if (!gt || !gt.threat_model) {
            if (placeholder) placeholder.style.display = 'block';
            if (layout) layout.style.display = 'none';
            return;
        }
        if (placeholder) placeholder.style.display = 'none';
        if (layout) layout.style.display = 'flex';

        this._tmInitResizer();

        const tm = gt.threat_model || {};
        const aps = gt.expected_attack_paths || [];
        const adrs = gt.architecture_decision_records || [];
        const bh = gt.blackhat_critique || null;
        const rrs = tm.residual_risk_summary || {};

        // Cache for AP selection
        this._tmAps = aps;
        this._tmAdrs = adrs;
        this._tmBh = bh;
        this._tmGt = gt;
        this._tmRrs = rrs;
        this._tmCurrentFilter = this._tmCurrentFilter || 'ALL';

        // Extract BH pivot-diverge chains as synthetic "new APs"
        const bhBreakdown = bh ? (bh.breakdown || bh) : null;
        this._tmBhChains = bhBreakdown ? (bhBreakdown.pivot_diverge_chains || []) : [];

        // TLDR banner
        const tldr = document.getElementById('tm-tldr');
        const tldrText = document.getElementById('tm-tldr-text');
        if (tldr && tldrText && tm.highest_risk_scenario) {
            const rs = tm.highest_risk_scenario;
            tldrText.innerHTML = `<b>${this._esc(rs.threat_actor || '?')}</b> targeting <b>${this._esc(rs.targeted_asset || '?')}</b> via ${this._esc(rs.exploited_vulnerability || '?')} <span style="color:#FF8C00;">&#8594;</span> ${this._esc(rs.impact || '?')}`;
            tldr.style.display = 'block';
        }

        // Architecture overview card (left panel)
        const overviewCard = document.getElementById('tm-overview-card');
        const overviewContent = document.getElementById('tm-overview-content');
        if (overviewCard && overviewContent) {
            const boundaries = (tm.trust_boundaries_at_risk || []).map(n => `<code>${this._esc(n)}</code>`).join(', ') || '—';
            const riskLine = rrs.overall_before
                ? `<div style="margin-top:0.4rem; padding:0.3rem 0.5rem; background:var(--card-bg); border-radius:4px; font-size:0.78rem;">Risk: <b>${rrs.overall_before}</b> &#8594; <b>${rrs.overall_after_controls}</b> (${rrs.status_after || ''}), &#8722;${rrs.risk_reduction_pct || 0}%</div>`
                : '';
            overviewContent.innerHTML =
                `<div><b>Type:</b> ${this._esc(tm.architecture_type || '?')}</div>` +
                `<div><b>Primary actor:</b> ${this._esc(tm.primary_threat_actor || '?')}</div>` +
                `<div><b>Bottleneck:</b> <code>${this._esc(tm.architecture_weakness || '?')}</code></div>` +
                `<div><b>Trust boundaries:</b> ${boundaries}</div>` +
                riskLine +
                (tm.summary ? `<div style="margin-top:0.5rem; font-style:italic; color:var(--text-tertiary);">${this._esc(tm.summary)}</div>` : '');
            overviewCard.style.display = 'block';
        }

        // Build AP list
        this._tmRenderApList();

        // Blackhat card (left panel bottom)
        const bhCard = document.getElementById('tm-blackhat-card');
        const bhSummary = document.getElementById('tm-blackhat-summary');
        if (bh && bhCard && bhSummary) {
            const breakdown = bh.breakdown || bh;
            const score = bh.score || 0;
            const chains = (breakdown.chained_exploit_findings || []).length;
            bhSummary.textContent = `Score ${score}/100 · ${chains} chained path(s) found`;
            bhCard.style.display = 'block';
        }

        // Interactive node graph toggle button
        const diagToggle = document.getElementById('tm-diagram-toggle');
        if (diagToggle) {
            diagToggle.style.display = 'inline-block';
            this._tmDiagramBuilt = false;
        }

        // Diagram links (ThreatModel+ADR and BH variant)
        const tmDiagLinks = document.getElementById('tm-diagram-links');
        if (tmDiagLinks) {
            const archName = this.analysisData.architecture_name;
            const baseFile = 'threatmodel_adr.mmd';
            const bhFile = 'threatmodel_adr_bh.mmd';
            tmDiagLinks.innerHTML =
                `<button class="btn-sm" style="font-size:0.75rem; margin-right:0.4rem;" onclick="window.dashboard._openTmDiagram('${archName}','${baseFile}')">🗂️ ThreatModel+ADR</button>` +
                (bh ? `<button class="btn-sm" style="font-size:0.75rem;" onclick="window.dashboard._openTmDiagram('${archName}','${bhFile}')">⚔️ +BH Chains</button>` : '');
            tmDiagLinks.style.display = 'block';
        }

        // Select first AP by default
        if (aps.length) this._tmSelectAp(aps[0].id);
    }

    async _openTmDiagram(archName, filename) {
        const resp = await fetch(`/api/v1/reports/${encodeURIComponent(archName)}/files/${encodeURIComponent(filename)}`);
        if (!resp.ok) {
            this.showRightPane(`📄 ${filename}`, `<p style="color:var(--text-tertiary); padding:1rem;">${filename} not found — re-run analysis.</p>`);
            return;
        }
        const mmd = await resp.text();
        let html = '';
        if (window.mermaid) {
            try {
                const id = 'tm-diag-' + Date.now();
                const { svg } = await window.mermaid.render(id, mmd);
                html = `<div style="padding:1rem; overflow:auto;">${svg}</div>`;
            } catch (e) {
                html = `<pre style="padding:1rem; overflow:auto; font-size:0.7rem;">${this._esc(mmd)}</pre>`;
            }
        } else {
            html = `<pre style="padding:1rem; overflow:auto; font-size:0.7rem;">${this._esc(mmd)}</pre>`;
        }
        this.showRightPane(`📄 ${filename}`, html);
    }

    _tmRenderApList() {
        const container = document.getElementById('tm-ap-list');
        if (!container) return;
        const aps = this._tmAps || [];
        const filter = this._tmCurrentFilter || 'ALL';
        const tierOrder = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1};
        const tierColor = {CRITICAL: '#DC143C', HIGH: '#FF8C00', MEDIUM: '#cc9900', LOW: '#32CD32'};
        const sorted = [...aps]
            .filter(ap => filter === 'ALL' || ap.criticality_tier === filter)
            .sort((a, b) => (tierOrder[b.criticality_tier] || 0) - (tierOrder[a.criticality_tier] || 0));

        const bhChains = (filter === 'ALL') ? (this._tmBhChains || []) : [];

        if (!sorted.length && !bhChains.length) {
            container.innerHTML = `<div style="padding:1rem; font-size:0.8rem; color:var(--text-tertiary);">No paths match filter.</div>`;
            return;
        }

        const apHtml = sorted.map(ap => {
            const tier = ap.criticality_tier || 'UNKNOWN';
            const color = tierColor[tier] || '#888';
            const pathStr = (ap.path || []).join(' → ') || ap.id;
            const rs = ap.risk_scenario || {};
            const adrId = ap.adr_id || (ap.adr_ids || [])[0] || '';
            const adr = (this._tmAdrs || []).find(a => a.adr_id === adrId);
            const riskBefore = adr ? adr.consequences.overall_risk_before : '?';
            const riskAfter = adr ? adr.consequences.overall_risk_after : '?';
            return `<div class="tm-ap-item" data-apid="${this._esc(ap.id)}" onclick="window.dashboard._tmSelectAp('${this._esc(ap.id)}')"
                style="padding:0.65rem 1rem 0.65rem 0.75rem; cursor:pointer; border-left:3px solid ${color}; border-bottom:1px solid var(--border-color); transition:background 0.15s;"
                onmouseover="this.style.background='var(--list-hover-bg)'" onmouseout="this.style.background=(this.classList.contains('selected')?'var(--list-active-bg)':'')">
                <div style="font-weight:600; font-size:0.83rem; display:flex; justify-content:space-between; align-items:center; gap:0.3rem;">
                    <span>${this._esc(ap.id)}</span>
                    <span style="font-size:0.68rem; padding:0.1rem 0.35rem; border-radius:3px; background:${color}22; color:${color}; border:1px solid ${color}44;">${tier}</span>
                </div>
                <div style="font-size:0.72rem; color:var(--text-tertiary); margin-top:0.2rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${this._esc(pathStr)}">${this._esc(pathStr)}</div>
                ${rs.threat_actor ? `<div style="font-size:0.71rem; color:var(--text-secondary); margin-top:0.15rem;">${this._esc(rs.threat_actor)}</div>` : ''}
                ${adrId ? `<div style="font-size:0.69rem; color:#1E90FF; margin-top:0.15rem;">${this._esc(adrId)} · ${riskBefore}&#8594;${riskAfter}</div>` : ''}
            </div>`;
        }).join('');

        // BH-discovered chains section (only shown when filter=ALL)
        let bhSectionHtml = '';
        if (bhChains.length) {
            const bhDivider = `<div style="padding:0.4rem 0.75rem; font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:#a855f7; background:#a855f711; border-bottom:1px solid #a855f733;">⚔️ BH-Discovered Chains</div>`;
            const bhItems = bhChains.map((chain, idx) => {
                const chainId = `BH-${idx + 1}`;
                const crit = chain.chain_criticality || 'UNKNOWN';
                const critColor = crit === 'CRITICAL' ? '#DC143C' : crit === 'HIGH' ? '#FF8C00' : '#cc9900';
                const stealth = chain.stealth_elevated ? ' 👁‍🗨 stealth' : '';
                const targetStr = (chain.targets || []).join(', ') || '?';
                const apIds = (chain.ap_ids || []).join(', ');
                return `<div class="tm-ap-item" data-apid="${this._esc(chainId)}" onclick="window.dashboard._tmSelectAp('${this._esc(chainId)}')"
                    style="padding:0.65rem 1rem 0.65rem 0.75rem; cursor:pointer; border-left:3px solid #a855f7; border-bottom:1px solid var(--border-color); transition:background 0.15s;"
                    onmouseover="this.style.background='var(--list-hover-bg)'" onmouseout="this.style.background=(this.classList.contains('selected')?'var(--list-active-bg)':'')">
                    <div style="font-weight:600; font-size:0.83rem; display:flex; justify-content:space-between; align-items:center; gap:0.3rem;">
                        <span style="color:#a855f7;">${this._esc(chainId)}</span>
                        <span style="font-size:0.68rem; padding:0.1rem 0.35rem; border-radius:3px; background:${critColor}22; color:${critColor}; border:1px solid ${critColor}44;">${crit}${stealth}</span>
                    </div>
                    <div style="font-size:0.72rem; color:var(--text-tertiary); margin-top:0.2rem;">pivot: <code style="font-size:0.7rem;">${this._esc(chain.pivot || '?')}</code></div>
                    <div style="font-size:0.69rem; color:#a855f766; margin-top:0.1rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="targets: ${this._esc(targetStr)}">→ ${this._esc(targetStr)}</div>
                    ${apIds ? `<div style="font-size:0.67rem; color:var(--text-tertiary); margin-top:0.1rem;">via ${this._esc(apIds)}</div>` : ''}
                </div>`;
            }).join('');
            bhSectionHtml = bhDivider + bhItems;
        }

        container.innerHTML = apHtml + bhSectionHtml;
    }

    _tmFilter(tier) {
        this._tmCurrentFilter = tier;
        // Update button active states
        document.querySelectorAll('.tm-filter-btn').forEach(btn => {
            const isActive = btn.dataset.filter === tier;
            btn.style.background = isActive ? 'var(--primary-color)' : 'transparent';
            btn.style.color = isActive ? '#fff' : (btn.dataset.filter === 'CRITICAL' ? '#DC143C' : btn.dataset.filter === 'HIGH' ? '#FF8C00' : btn.dataset.filter === 'MEDIUM' ? '#cc9900' : btn.dataset.filter === 'LOW' ? '#32CD32' : 'var(--text-color)');
        });
        this._tmRenderApList();
        // Re-select first visible AP
        const first = (this._tmAps || []).find(ap => tier === 'ALL' || ap.criticality_tier === tier);
        if (first) this._tmSelectAp(first.id);
        else { const d = document.getElementById('tm-detail-content'); if (d) d.innerHTML = '<p style="color:var(--text-tertiary); text-align:center; margin-top:2rem;">No paths match filter.</p>'; }
    }

    _tmSelectAp(apId) {
        // Highlight selected in list (shared for both AP and BH items)
        document.querySelectorAll('.tm-ap-item').forEach(el => {
            const sel = el.dataset.apid === apId;
            el.classList.toggle('selected', sel);
            el.style.background = sel ? 'var(--list-active-bg)' : '';
        });

        // Route BH-discovered chain IDs to BH detail renderer
        if (apId.startsWith('BH-')) {
            const idx = parseInt(apId.slice(3), 10) - 1;
            const chain = (this._tmBhChains || [])[idx];
            if (chain) this._tmRenderBhChainDetail(apId, chain);
            return;
        }

        const aps = this._tmAps || [];
        const adrs = this._tmAdrs || [];
        const ap = aps.find(a => a.id === apId);
        if (!ap) return;

        const adrId = ap.adr_id || (ap.adr_ids || [])[0] || '';
        const adr = adrs.find(a => a.adr_id === adrId);
        const tierColor = {CRITICAL: '#DC143C', HIGH: '#FF8C00', MEDIUM: '#cc9900', LOW: '#32CD32'};
        const dirIcon = {prevention: '🛡️', detection: '👁️', response: '🔄', isolate: '🔒', hardening: '⚙️', governance: '📋'};

        const detail = document.getElementById('tm-detail-content');
        if (!detail) return;

        const tier = ap.criticality_tier || 'UNKNOWN';
        const color = tierColor[tier] || '#888';
        const rs = ap.risk_scenario || {};
        const pathStr = (ap.path || []).join(' → ');

        // Section 1: Risk scenario narrative
        let html = `<div style="margin-bottom:1.5rem;">
            <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem;">
                <span style="font-size:1.1rem; font-weight:700; color:var(--text-color);">${this._esc(apId)}</span>
                <span style="padding:0.15rem 0.55rem; border-radius:4px; font-size:0.72rem; font-weight:700; background:${color}22; color:${color}; border:1px solid ${color}55;">${tier}</span>
                ${adrId ? `<span style="padding:0.15rem 0.55rem; border-radius:4px; font-size:0.72rem; background:#1E90FF22; color:#1E90FF; border:1px solid #1E90FF44;">${this._esc(adrId)}</span>` : ''}
            </div>
            <div style="font-size:0.78rem; color:var(--text-tertiary); margin-bottom:0.9rem; font-family:monospace;">${this._esc(pathStr)}</div>`;

        if (rs.threat_actor) {
            html += `<div style="padding:0.65rem 0.9rem; background:var(--card-bg); border-radius:6px; border-left:3px solid ${color}; margin-bottom:0.75rem;">
                <div style="display:flex; flex-wrap:wrap; gap:0.6rem 1.25rem;">
                    <div style="min-width:100px;"><span style="color:var(--text-tertiary); font-size:0.67rem; text-transform:uppercase; letter-spacing:0.05em;">Actor</span><br><span style="font-size:0.78rem; font-weight:700; color:#4da6ff;">${this._esc(rs.threat_actor)}</span></div>
                    <div style="min-width:100px;"><span style="color:var(--text-tertiary); font-size:0.67rem; text-transform:uppercase; letter-spacing:0.05em;">Target</span><br><span style="font-size:0.78rem; color:var(--danger-color);">${this._esc(rs.targeted_asset || '?')}</span></div>
                    <div style="flex:1; min-width:140px;"><span style="color:var(--text-tertiary); font-size:0.67rem; text-transform:uppercase; letter-spacing:0.05em;">Exploited via</span><br><span style="font-size:0.78rem; color:var(--warning-color);">${this._esc(rs.exploited_vulnerability || '?')}</span></div>
                </div>
                <div style="margin-top:0.4rem; padding-top:0.4rem; border-top:1px solid var(--border-color);"><span style="color:var(--text-tertiary); font-size:0.67rem; text-transform:uppercase; letter-spacing:0.05em;">Impact</span>&nbsp;<span style="font-size:0.82rem; font-weight:700; color:#FF8C00;">${this._esc(rs.impact || '?')}</span></div>
            </div>`;
        }
        html += `</div>`;

        // Section 2: ADR walkthrough (if ADR exists)
        if (adr) {
            const ctx = adr.context || {};
            const cons = adr.consequences || {};
            const hops = adr.hops || [];

            // Threat scenario prose
            if (ctx.threat_scenario) {
                html += `<div style="margin-bottom:1.25rem; padding:0.75rem 1rem; background:var(--card-bg); border-radius:6px; font-size:0.86rem; line-height:1.65; color:var(--text-secondary);">
                    ${this._esc(ctx.threat_scenario)}
                </div>`;
            }

            // RAPIDS active threats table
            if (ctx.active_threats && ctx.active_threats.length) {
                html += `<div style="margin-bottom:1.25rem;">
                    <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">RAPIDS Threat Scores</div>
                    <table style="width:100%; border-collapse:collapse; font-size:0.8rem;">
                        <thead><tr style="border-bottom:1px solid var(--border-color);">
                            <th style="text-align:left; padding:0.3rem 0.5rem; color:var(--text-tertiary); font-weight:600;">Category</th>
                            <th style="text-align:center; padding:0.3rem 0.5rem; color:var(--text-tertiary); font-weight:600;">Score</th>
                            <th style="text-align:left; padding:0.3rem 0.5rem; color:var(--text-tertiary); font-weight:600;">Consequence</th>
                        </tr></thead>
                        <tbody>${ctx.active_threats.map(t => {
                            const bar = Math.round(t.score / 5);
                            const tcolor = t.score >= 70 ? '#DC143C' : t.score >= 40 ? '#FF8C00' : '#32CD32';
                            return `<tr style="border-bottom:1px solid var(--border-color)22;">
                                <td style="padding:0.3rem 0.5rem; font-weight:600; color:${tcolor};">${this._esc(t.category.replace(/_/g,' '))}</td>
                                <td style="padding:0.3rem 0.5rem; text-align:center;">
                                    <span style="display:inline-block; width:${bar * 3}px; height:6px; background:${tcolor}; border-radius:3px; vertical-align:middle; margin-right:4px;"></span>${t.score}
                                </td>
                                <td style="padding:0.3rem 0.5rem; color:var(--text-secondary);">${this._esc(t.consequence)}</td>
                            </tr>`;
                        }).join('')}</tbody>
                    </table>
                </div>`;
            }

            // Gap summary callout
            if (ctx.gap_summary && ctx.gap_summary !== 'All hops are covered with at least one control.') {
                html += `<div style="margin-bottom:1.25rem; padding:0.6rem 0.9rem; background:#FF8C0011; border:1px solid #FF8C0044; border-radius:6px; font-size:0.82rem; color:#FF8C00;">
                    <b>Gap:</b> ${this._esc(ctx.gap_summary)}
                </div>`;
            }

            // Decision rationale
            if (ctx.decision_rationale) {
                html += `<div style="margin-bottom:1.25rem; font-size:0.84rem; color:var(--text-secondary); line-height:1.6;">
                    <span style="font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary);">Decision Rationale</span><br>
                    ${this._esc(ctx.decision_rationale)}
                </div>`;
            }

            // Risk outcome line
            html += `<div style="margin-bottom:1.5rem; display:flex; gap:1.5rem; font-size:0.85rem;">
                <div><span style="color:var(--text-tertiary); font-size:0.72rem;">Risk Before</span><br><b style="font-size:1rem; color:#DC143C;">${cons.overall_risk_before}</b></div>
                <div style="color:var(--text-tertiary); font-size:1.2rem; align-self:flex-end; padding-bottom:2px;">&#8594;</div>
                <div><span style="color:var(--text-tertiary); font-size:0.72rem;">Risk After</span><br><b style="font-size:1rem; color:#32CD32;">${cons.overall_risk_after}</b></div>
                <div><span style="color:var(--text-tertiary); font-size:0.72rem;">Reduction</span><br><b style="font-size:1rem; color:var(--primary-color);">&#8722;${cons.risk_reduction_pct}%</b></div>
            </div>`;

            // Hop walkthrough — node graph + controls
            if (hops.length) {
                html += `<div style="margin-bottom:0.5rem; font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary);">Hop-by-Hop Walkthrough</div>`;

                // Mini legend for hop cards
                html += `<div style="margin-bottom:0.6rem; padding:0.4rem 0.65rem; background:var(--nav-hover-bg); border-radius:5px; font-size:0.71rem; display:flex; flex-wrap:wrap; gap:0.6rem; align-items:center; color:var(--text-tertiary);">
                    <span style="font-weight:700; font-size:0.68rem; text-transform:uppercase; letter-spacing:0.04em;">Legend:</span>
                    <span><span style="color:#FF8C00;">■</span> Gap border = ZT layer missing</span>
                    <span><span style="color:#FF8C00;">missing X</span> = absent ZT layer</span>
                    <span><span style="color:var(--secondary-color);">Present: Y</span> = covered layers</span>
                    <span>🏛 <span style="color:#06b6d4;">AC-1</span> <span style="background:var(--danger-color)22; color:var(--danger-color); border-radius:2px; padding:0 2px; font-weight:700;">L0</span> = SSP mandatory</span>
                    <span><span style="background:var(--warning-color)22; color:var(--warning-color); border-radius:2px; padding:0 2px; font-weight:700;">L1</span> = baseline</span>
                    <span><span style="background:var(--text-tertiary)22; color:var(--text-tertiary); border-radius:2px; padding:0 2px; font-weight:700;">L2</span> = best practice</span>
                </div>`;

                // Path node graph (click to expand)
                html += this._tmBuildNodeGraph(ap, hops, adr);

                // Hop detail cards
                hops.forEach((hop, idx) => {
                    const isGap = hop.gap_note;
                    const hasCtrls = hop.controls && hop.controls.length > 0;
                    const hopId = `tm-hop-${apId}-${idx}`;
                    html += `<details id="${hopId}" style="margin-bottom:0.5rem; border:1px solid ${isGap ? '#FF8C0044' : 'var(--border-color)'}; border-radius:6px; overflow:hidden;">
                        <summary style="cursor:pointer; padding:0.55rem 0.9rem; font-weight:600; font-size:0.84rem; background:var(--card-bg); display:flex; align-items:center; gap:0.5rem;">
                            <span style="font-size:0.7rem; color:var(--text-tertiary); font-weight:400;">Hop ${idx + 1}</span>
                            <code style="font-size:0.83rem;">${this._esc(hop.node_label || hop.node)}</code>
                            ${hasCtrls ? `<span style="margin-left:auto; font-size:0.69rem; padding:0.1rem 0.4rem; background:#1E90FF22; color:#1E90FF; border-radius:3px;">${hop.controls.length} control${hop.controls.length > 1 ? 's' : ''}</span>` : ''}
                            ${isGap ? `<span style="margin-left:${hasCtrls ? '0' : 'auto'}; font-size:0.69rem; padding:0.1rem 0.4rem; background:#FF8C0022; color:#FF8C00; border-radius:3px;">gap</span>` : ''}
                        </summary>
                        <div style="padding:0.75rem 0.9rem; font-size:0.82rem;">`;

                    // Techniques at this hop
                    if (hop.node_techniques && hop.node_techniques.length) {
                        html += `<div style="margin-bottom:0.5rem; color:var(--text-tertiary); font-size:0.76rem;">
                            <b>Techniques:</b> ${hop.node_techniques.map(t => `<code style="font-size:0.74rem; padding:0.05rem 0.25rem; background:var(--code-bg); border-radius:3px;">${this._esc(t)}</code>`).join(' ')}
                        </div>`;
                    }

                    // Gap callout — split "missing X" (gap color) from "Present: Y" (neutral)
                    if (isGap) {
                        const rawNote = hop.gap_note || '';
                        // Attempt to split on "Present:" so we colour the two halves differently
                        const presentIdx = rawNote.indexOf('Present:');
                        let gapNoteHtml;
                        if (presentIdx > 0) {
                            const missingPart = this._esc(rawNote.slice(0, presentIdx).trim());
                            const presentPart = this._esc(rawNote.slice(presentIdx).trim());
                            gapNoteHtml = `<span style="color:#FF8C00;">${missingPart}</span> <span style="color:var(--secondary-color); font-size:0.76rem;">${presentPart}</span>`;
                        } else {
                            gapNoteHtml = `<span style="color:#FF8C00;">${this._esc(rawNote)}</span>`;
                        }
                        html += `<div style="margin-bottom:0.6rem; padding:0.4rem 0.7rem; background:#FF8C0011; border-left:3px solid #FF8C00; border-radius:4px; font-size:0.79rem;">${gapNoteHtml}</div>`;
                    }

                    // Controls
                    if (hasCtrls) {
                        hop.controls.forEach(ctrl => {
                            const icon = dirIcon[ctrl.dir_category] || '🔹';
                            const rr = ctrl.risk_reduction || 0;
                            const sspCtx = ctrl.ssp_context;
                            let sspBadge = '';
                            if (sspCtx && sspCtx.primary) {
                                const p = sspCtx.primary;
                                const lvl = p.level ?? 2;
                                const lvlColor = lvl === 0 ? 'var(--danger-color)' : lvl === 1 ? 'var(--warning-color)' : 'var(--text-tertiary)';
                                const lvlLabel = ['L0','L1','L2'][lvl] ?? `L${lvl}`;
                                const govTip = lvl === 0 ? 'Cardinal — mandatory, HQ approval required' : lvl === 1 ? 'Basic Hygiene — SC risk acceptance required' : 'Best Practice — risk-owner acceptance';
                                sspBadge = `<span title="${this._esc(p.title || '')} · ${govTip}" style="display:inline-flex; align-items:center; gap:0.2rem; font-size:0.67rem; padding:0.1rem 0.38rem; background:#06b6d418; color:#06b6d4; border:1px solid #06b6d444; border-radius:3px; cursor:default;">🏛 ${this._esc(p.id)} <span style="padding:0 2px; background:${lvlColor}22; color:${lvlColor}; border-radius:2px; font-size:0.62rem; font-weight:700;">${lvlLabel}</span></span>`;
                            }
                            html += `<div style="padding:0.5rem 0.7rem; background:var(--main-bg); border:1px solid var(--border-color); border-radius:5px; margin-bottom:0.4rem;">
                                <div style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem;">
                                    <span style="font-weight:700; font-size:0.83rem;">${icon} ${this._esc(ctrl.control.toUpperCase())}</span>
                                    <div style="display:flex; gap:0.35rem; align-items:center; flex-shrink:0;">
                                        ${sspBadge}
                                        <span style="font-size:0.69rem; padding:0.1rem 0.35rem; background:var(--card-bg); border:1px solid var(--border-color); border-radius:3px; color:var(--text-secondary);">${this._esc(ctrl.dir_category)}</span>
                                        <span style="font-size:0.69rem; padding:0.1rem 0.35rem; border-radius:3px; background:${ctrl.priority === 'critical' ? '#DC143C22' : ctrl.priority === 'high' ? '#FF8C0022' : 'var(--card-bg)'}; color:${ctrl.priority === 'critical' ? '#DC143C' : ctrl.priority === 'high' ? '#FF8C00' : 'var(--text-tertiary)'}; border:1px solid var(--border-color);">${this._esc(ctrl.priority)}</span>
                                    </div>
                                </div>
                                <div style="font-size:0.78rem; color:var(--text-secondary); margin-top:0.3rem; line-height:1.5;">${this._esc(ctrl.reason)}</div>
                                ${rr > 0 ? `<div style="font-size:0.72rem; color:#32CD32; margin-top:0.25rem;">&#8722;${rr} risk reduction</div>` : ''}
                            </div>`;
                        });
                    } else if (!isGap) {
                        html += `<div style="color:var(--text-tertiary); font-size:0.79rem;">No controls assigned to this hop.</div>`;
                    }

                    html += `</div></details>`;
                });
            }

            // New risks introduced
            if (cons.new_risks_introduced && cons.new_risks_introduced.length) {
                html += `<div style="margin-top:1rem; padding:0.6rem 0.9rem; background:#DC143C11; border:1px solid #DC143C44; border-radius:6px; font-size:0.8rem; color:#DC143C;">
                    <b>New risks introduced:</b><br>${cons.new_risks_introduced.map(r => `• ${this._esc(r)}`).join('<br>')}
                </div>`;
            }
        } else {
            html += `<div style="color:var(--text-tertiary); font-size:0.83rem; margin-top:0.5rem;">No ADR found for this path.</div>`;
        }

        detail.innerHTML = html;
    }

    _tmSelectBlackhat() {
        const bh = this._tmBh;
        const detail = document.getElementById('tm-detail-content');
        if (!detail || !bh) return;

        // Highlight blackhat card
        document.querySelectorAll('.tm-ap-item').forEach(el => { el.classList.remove('selected'); el.style.background = ''; });
        const bhCard = document.getElementById('tm-blackhat-card');
        if (bhCard) bhCard.style.background = 'var(--list-active-bg)';

        const breakdown = bh.breakdown || bh;
        const chains = breakdown.chained_exploit_findings || [];
        const stealth = breakdown.stealth_score || 0;
        const stealthTechs = breakdown.stealthy_techniques || [];
        const gaps = breakdown.mitigation_gaps_for_chains || [];
        const shared = breakdown.shared_nodes || {};
        const unique = (breakdown.uniqueness_vs_critics || {}).new_findings_not_in_redteam || [];
        const score = bh.score || 0;
        const scoreColor = score <= 30 ? '#32CD32' : score <= 60 ? '#FF8C00' : '#DC143C';

        let html = `<div style="margin-bottom:1.5rem;">
            <div style="font-size:1.05rem; font-weight:700; margin-bottom:0.5rem;">Blackhat Cross-Path Analysis</div>
            <div style="font-size:0.8rem; color:var(--text-tertiary); margin-bottom:1rem;">
                Analyses all attack paths together — the only critic that reasons about attacker pivoting across paths via shared nodes.
            </div>
            <div style="display:flex; gap:1.5rem; margin-bottom:1rem;">
                <div><span style="font-size:0.7rem; color:var(--text-tertiary);">Cross-chain score</span><br><b style="font-size:1.1rem; color:${scoreColor};">${score}/100</b></div>
                <div><span style="font-size:0.7rem; color:var(--text-tertiary);">Stealth techniques</span><br><b style="font-size:1.1rem;">${stealth}</b></div>
                <div><span style="font-size:0.7rem; color:var(--text-tertiary);">Chained paths</span><br><b style="font-size:1.1rem;">${chains.length}</b></div>
            </div>
        </div>`;

        // Pivot nodes
        const pivotNodes = Object.keys(shared);
        if (pivotNodes.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">Pivot Nodes (shared across paths)</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                    ${pivotNodes.slice(0, 8).map(n => `<span style="padding:0.2rem 0.55rem; background:var(--card-bg); border:1px solid #FF8C0055; border-radius:4px; font-size:0.78rem;"><code>${this._esc(n)}</code> <span style="color:var(--text-tertiary);">(${(shared[n] || []).length} path(s))</span></span>`).join('')}
                </div>
            </div>`;
        }

        // Chained exploits
        if (chains.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">Chained Exploit Paths</div>
                <ul style="margin:0; padding-left:1.2rem; font-size:0.83rem; color:var(--text-secondary); line-height:1.7;">
                    ${chains.slice(0, 6).map(c => `<li>${this._esc(c)}</li>`).join('')}
                </ul>
            </div>`;
        }

        // Stealth
        if (stealth > 0) {
            html += `<div style="margin-bottom:1.25rem; padding:0.6rem 0.9rem; background:#FF8C0011; border-left:3px solid #FF8C00; border-radius:4px; font-size:0.82rem;">
                <b>Stealth evasion:</b> ${stealth} Defence Evasion technique(s) active in chains — ${stealthTechs.slice(0, 4).map(t => `<code style="font-size:0.76rem;">${this._esc(t)}</code>`).join(', ')}.
                ${stealth >= 2 ? ' An attacker using these would evade detection controls on individual paths.' : ''}
            </div>`;
        }

        // Mitigation gaps
        if (gaps.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">Cross-Path Gaps</div>
                <ul style="margin:0; padding-left:1.2rem; font-size:0.83rem; color:var(--text-secondary); line-height:1.7;">
                    ${gaps.slice(0, 5).map(g => `<li>${this._esc(g)}</li>`).join('')}
                </ul>
            </div>`;
        }

        // Unique findings
        if (unique.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">Unique to Blackhat (not raised by Red Team)</div>
                <ul style="margin:0; padding-left:1.2rem; font-size:0.83rem; color:var(--text-secondary); line-height:1.7;">
                    ${unique.slice(0, 4).map(f => `<li>${this._esc(f)}</li>`).join('')}
                </ul>
            </div>`;
        }

        detail.innerHTML = html;
    }

    _tmRenderBhChainDetail(chainId, chain) {
        const detail = document.getElementById('tm-detail-content');
        if (!detail) return;

        const crit = chain.chain_criticality || 'UNKNOWN';
        const critColor = crit === 'CRITICAL' ? '#DC143C' : crit === 'HIGH' ? '#FF8C00' : '#cc9900';
        const pivot = chain.pivot || '?';
        const targets = chain.targets || [];
        const apIds = chain.ap_ids || [];
        const techniques = chain.techniques || [];
        const stealth = chain.stealth_elevated;

        // Collect original AP details for the feeding APs
        const aps = this._tmAps || [];
        const bhBreakdown = this._tmBh ? (this._tmBh.breakdown || this._tmBh) : {};
        const gapsList = (bhBreakdown.mitigation_gaps_for_chains || []).filter(g =>
            typeof g === 'string' ? g.toLowerCase().includes(pivot.toLowerCase()) : false
        );

        let html = `<div style="margin-bottom:1.5rem;">
            <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem;">
                <span style="font-size:1.1rem; font-weight:700; color:#a855f7;">${this._esc(chainId)}</span>
                <span style="padding:0.15rem 0.55rem; border-radius:4px; font-size:0.72rem; font-weight:700; background:${critColor}22; color:${critColor}; border:1px solid ${critColor}55;">${crit}</span>
                ${stealth ? `<span style="padding:0.15rem 0.45rem; border-radius:4px; font-size:0.71rem; background:#ff000022; color:#ff6666; border:1px solid #ff666644;">👁‍🗨 stealth</span>` : ''}
                <span style="padding:0.15rem 0.45rem; border-radius:4px; font-size:0.71rem; background:#a855f722; color:#a855f7; border:1px solid #a855f744;">⚔️ surfaced by BH expert</span>
            </div>
            <div style="padding:0.5rem 0.8rem; background:#a855f711; border:1px solid #a855f733; border-radius:6px; font-size:0.82rem; color:var(--text-secondary); margin-bottom:1rem; line-height:1.55;">
                Blackhat Expert (Layer 2E) identified <strong style="color:#a855f7;">${this._esc(pivot)}</strong> as a shared pivot node reachable from
                ${apIds.length ? apIds.map(id => `<span style="color:#4da6ff; font-weight:600;">${this._esc(id)}</span>`).join(', ') : 'multiple paths'}.
                From this pivot, an attacker can diverge to <strong>${targets.length}</strong> distinct target${targets.length !== 1 ? 's' : ''},
                creating a cross-path chain not modelled in the original attack paths.
                ${stealth ? '<br><span style="color:#ff6666; font-size:0.79rem;">⚠ Pivot node has no detection coverage — chain would be invisible to defenders.</span>' : ''}
            </div>
        </div>`;

        // Chain diagram: pivot → targets
        if (targets.length) {
            const pivotW = 120, nodeW = 110, nodeH = 34, gapX = 80, gapY = 10;
            const totalH = Math.max(60, targets.length * (nodeH + gapY) + gapY);
            const svgW = pivotW + gapX + nodeW + 20;
            const pivotX = 10, pivotY = totalH / 2 - nodeH / 2;
            let svgParts = [`<svg width="${svgW}" height="${totalH}" style="font-family:monospace; overflow:visible;">`];

            // Pivot node (amber/purple)
            svgParts.push(`<rect x="${pivotX}" y="${pivotY}" width="${pivotW}" height="${nodeH}" rx="5" fill="#a855f711" stroke="#a855f7" stroke-width="2"/>`);
            svgParts.push(`<text x="${pivotX + pivotW/2}" y="${pivotY + nodeH/2 + 5}" text-anchor="middle" fill="#a855f7" font-size="11" font-weight="600">${this._esc(pivot.length > 14 ? pivot.slice(0,13)+'…' : pivot)}</text>`);
            svgParts.push(`<text x="${pivotX + pivotW/2}" y="${pivotY - 6}" text-anchor="middle" fill="#a855f788" font-size="9">pivot</text>`);

            // Target nodes
            targets.forEach((tgt, i) => {
                const tgtX = pivotX + pivotW + gapX;
                const tgtY = gapY + i * (nodeH + gapY);
                const midX = pivotX + pivotW + gapX / 2;
                const pivotMidY = pivotY + nodeH / 2;
                const tgtMidY = tgtY + nodeH / 2;
                svgParts.push(`<path d="M ${pivotX + pivotW} ${pivotMidY} C ${midX} ${pivotMidY}, ${midX} ${tgtMidY}, ${tgtX} ${tgtMidY}" fill="none" stroke="#FF8C00" stroke-width="1.5" stroke-dasharray="4,3"/>`);
                svgParts.push(`<polygon points="${tgtX-5},${tgtMidY-4} ${tgtX},${tgtMidY} ${tgtX-5},${tgtMidY+4}" fill="#FF8C00"/>`);
                svgParts.push(`<rect x="${tgtX}" y="${tgtY}" width="${nodeW}" height="${nodeH}" rx="5" fill="#FF8C0011" stroke="#FF8C00" stroke-width="1.5"/>`);
                svgParts.push(`<text x="${tgtX + nodeW/2}" y="${tgtY + nodeH/2 + 5}" text-anchor="middle" fill="#FF8C00" font-size="10">${this._esc(tgt.length > 14 ? tgt.slice(0,13)+'…' : tgt)}</text>`);
            });

            svgParts.push(`</svg>`);
            html += `<div style="margin-bottom:1.25rem; padding:0.75rem; background:var(--card-bg); border-radius:6px; overflow-x:auto;">${svgParts.join('')}</div>`;
        }

        // Feeding APs
        if (apIds.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.5rem;">Feeding Attack Paths</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                ${apIds.map(id => {
                    const ap = aps.find(a => a.id === id);
                    const tier = ap ? (ap.criticality_tier || '') : '';
                    const tColor = tier === 'CRITICAL' ? '#DC143C' : tier === 'HIGH' ? '#FF8C00' : tier === 'MEDIUM' ? '#cc9900' : '#888';
                    return `<span onclick="window.dashboard._tmSelectAp('${this._esc(id)}')" style="cursor:pointer; padding:0.2rem 0.6rem; border-radius:4px; font-size:0.78rem; font-weight:600; background:#1E90FF11; color:#1E90FF; border:1px solid #1E90FF44;" title="Click to view ${this._esc(id)}">${this._esc(id)}${tier ? ` <span style="color:${tColor}; font-size:0.68rem;">(${tier})</span>` : ''}</span>`;
                }).join('')}
                </div>
            </div>`;
        }

        // Techniques at pivot
        if (techniques.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">Techniques at Pivot Node</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.35rem;">
                ${techniques.map(t => `<code style="padding:0.15rem 0.4rem; background:var(--code-bg); border-radius:3px; font-size:0.76rem; color:var(--text-secondary);">${this._esc(t)}</code>`).join('')}
                </div>
            </div>`;
        }

        // Mitigation gaps relevant to this chain
        if (gapsList.length) {
            html += `<div style="margin-bottom:1.25rem;">
                <div style="font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--text-tertiary); margin-bottom:0.4rem;">Mitigation Gaps</div>
                ${gapsList.map(g => `<div style="padding:0.4rem 0.7rem; background:#FF8C0011; border-left:3px solid #FF8C00; border-radius:4px; font-size:0.8rem; color:#FF8C00; margin-bottom:0.35rem;">${this._esc(g)}</div>`).join('')}
            </div>`;
        }

        // No ADR notice
        html += `<div style="padding:0.55rem 0.9rem; background:var(--card-bg); border-radius:6px; font-size:0.8rem; color:var(--text-tertiary); border:1px dashed var(--border-color);">
            <b>No ADR for this chain</b> — BH-discovered cross-path chains are not part of the original architecture decision records.
            Review feeding APs above for existing mitigations, then consider whether a new ADR is warranted to address the pivot node exposure.
        </div>`;

        detail.innerHTML = html;
    }

    _tmBuildNodeGraph(ap, hops, adr) {
        // Build a simple inline SVG node-link diagram for the attack path.
        // Each node is clickable to toggle a tooltip showing techniques + controls.
        const nodes = ap.path || [];
        if (!nodes.length) return '';

        const nodeW = 90, nodeH = 32, gapX = 56, padX = 16, padY = 20;
        const totalW = nodes.length * nodeW + (nodes.length - 1) * gapX + padX * 2;
        const totalH = nodeH + padY * 2 + 32; // 32px for labels

        const tierColor = {CRITICAL: '#DC143C', HIGH: '#FF8C00', MEDIUM: '#cc9900', LOW: '#32CD32'};
        const nodeColor = '#1E90FF';
        const gapColor = '#FF8C00';
        const safeColor = '#32CD32';

        // Build hop lookup
        const hopByNode = {};
        hops.forEach(h => { hopByNode[h.node] = h; });

        let svgParts = [`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${totalW} ${totalH}" style="width:100%; max-width:${totalW}px; display:block; margin-bottom:1rem; font-family:inherit; cursor:default;" role="img" aria-label="Attack path: ${this._esc(ap.id)}">`];

        // Arrows between nodes
        for (let i = 0; i < nodes.length - 1; i++) {
            const x1 = padX + i * (nodeW + gapX) + nodeW;
            const x2 = padX + (i + 1) * (nodeW + gapX);
            const y = padY + nodeH / 2;
            svgParts.push(`<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="#FF8C00" stroke-width="1.5" stroke-dasharray="4,3" marker-end="url(#arrowhead)"/>`);
        }

        // Arrowhead marker
        svgParts.unshift(`<defs><marker id="arrowhead" markerWidth="7" markerHeight="5" refX="6" refY="2.5" orient="auto"><polygon points="0 0, 7 2.5, 0 5" fill="#FF8C00"/></marker></defs>`);

        // Nodes
        nodes.forEach((node, i) => {
            const hop = hopByNode[node];
            const hasGap = hop && hop.gap_note;
            const hasCtrl = hop && hop.controls && hop.controls.length > 0;
            const fill = hasGap ? gapColor : (hasCtrl ? safeColor : nodeColor);
            const rx = padX + i * (nodeW + gapX);
            const ry = padY;
            const cx = rx + nodeW / 2;
            const cy = ry + nodeH / 2;

            // Encode tooltip content for onclick
            const techStr = hop ? (hop.node_techniques || []).join(', ') || 'none' : 'none';
            const ctrlStr = hop ? (hop.controls || []).map(c => c.control).join(', ') || 'none' : 'none';
            const gapStr = hop && hop.gap_note ? hop.gap_note : '';
            const label = node.length > 10 ? node.slice(0, 9) + '…' : node;

            const thisApId = ap.id;
            svgParts.push(`<g class="tm-node" onclick="window.dashboard._tmNodeClick('${this._esc(node)}','${this._esc(thisApId)}',event)" style="cursor:pointer;" role="button" tabindex="0" aria-label="${this._esc(node)}">
                <rect x="${rx}" y="${ry}" width="${nodeW}" height="${nodeH}" rx="5" fill="${fill}22" stroke="${fill}" stroke-width="1.5"/>
                <text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="11" fill="var(--text-color)" font-weight="600">${this._esc(label)}</text>
                ${hasGap ? `<circle cx="${rx + nodeW - 6}" cy="${ry + 6}" r="5" fill="#FF8C00"/><text x="${rx + nodeW - 6}" y="${ry + 10}" text-anchor="middle" font-size="7" fill="#fff" font-weight="700">!</text>` : ''}
            </g>`);

            // Control count badge below node
            if (hasCtrl) {
                svgParts.push(`<text x="${cx}" y="${ry + nodeH + 14}" text-anchor="middle" font-size="9" fill="${safeColor}">${hop.controls.length} ctrl</text>`);
            }
        });

        svgParts.push(`</svg>`);

        const svgHtml = svgParts.join('\n');
        return `<div style="margin-bottom:1rem; padding:0.75rem; background:var(--card-bg); border-radius:6px; border:1px solid var(--border-color);">
            <div style="font-size:0.7rem; color:var(--text-tertiary); margin-bottom:0.4rem;">Attack path — click a node to jump to its hop detail</div>
            <div style="display:flex; gap:0.75rem; margin-bottom:0.5rem; font-size:0.7rem;">
                <span><span style="display:inline-block;width:8px;height:8px;background:#32CD32;border-radius:1px;margin-right:3px;"></span>controlled</span>
                <span><span style="display:inline-block;width:8px;height:8px;background:#FF8C00;border-radius:1px;margin-right:3px;"></span>gap</span>
                <span><span style="display:inline-block;width:8px;height:8px;background:#1E90FF;border-radius:1px;margin-right:3px;"></span>no techniques</span>
            </div>
            ${svgHtml}
            <div id="tm-node-tooltip" style="display:none; margin-top:0.5rem; padding:0.5rem 0.75rem; background:var(--main-bg); border:1px solid var(--border-color); border-radius:5px; font-size:0.79rem; line-height:1.5;"></div>
        </div>`;
    }

    _tmNodeClick(nodeName, apId, event) {
        const aps = this._tmAps || [];
        const adrs = this._tmAdrs || [];
        const ap = aps.find(a => a.id === apId);
        if (!ap) return;
        const adrId = ap.adr_id || (ap.adr_ids || [])[0] || '';
        const adr = adrs.find(a => a.adr_id === adrId);
        const hopIdx = adr && adr.hops ? adr.hops.findIndex(h => h.node === nodeName) : -1;

        // Primary action: open and scroll to the hop card in the right pane
        if (hopIdx >= 0) {
            const hopId = `tm-hop-${apId}-${hopIdx}`;
            const hopEl = document.getElementById(hopId);
            if (hopEl) {
                hopEl.setAttribute('open', '');
                hopEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // Pulse highlight so the user sees which card opened
                hopEl.style.outline = `2px solid var(--primary-color)`;
                hopEl.style.outlineOffset = '2px';
                setTimeout(() => { hopEl.style.outline = ''; hopEl.style.outlineOffset = ''; }, 1400);
            }
        }

        // Secondary: update the inline tooltip so the graph still shows context
        const tooltip = document.getElementById('tm-node-tooltip');
        if (!tooltip) return;
        const hop = adr && adr.hops ? adr.hops[hopIdx] : null;
        if (!hop) {
            tooltip.innerHTML = `<code>${this._esc(nodeName)}</code> — no hop data for this path.`;
            tooltip.style.display = 'block';
            return;
        }
        const techs = (hop.node_techniques || []).join(', ') || 'none';
        const ctrls = (hop.controls || []).map(c => `<code>${this._esc(c.control)}</code>`).join(', ') || 'none';
        const gapBadge = hop.gap_note
            ? `<span style="margin-left:0.4rem; font-size:0.7rem; padding:0.1rem 0.35rem; background:#FF8C0022; color:#FF8C00; border-radius:3px;">${hop.gap_type || 'gap'}</span>`
            : '';

        tooltip.innerHTML = `<b><code>${this._esc(nodeName)}</code></b>${gapBadge}<br>
            <span style="color:var(--text-tertiary); font-size:0.75rem;">Techniques:</span> ${this._esc(techs)}<br>
            <span style="color:var(--text-tertiary); font-size:0.75rem;">Controls:</span> ${ctrls}
            <div style="margin-top:0.3rem; font-size:0.7rem; color:var(--primary-color);">&#8595; Scrolled to hop card</div>`;
        tooltip.style.display = 'block';
    }

    _tmToggleDiagram() {
        const wrapper = document.getElementById('tm-diagram-wrapper');
        const btn = document.getElementById('tm-diagram-toggle');
        if (!wrapper) return;
        const isVisible = wrapper.style.display !== 'none';
        wrapper.style.display = isVisible ? 'none' : 'block';
        if (btn) btn.textContent = isVisible ? 'Show Diagram' : 'Hide Diagram';

        // Build the interactive node graph on first show
        if (!isVisible && !this._tmDiagramBuilt) {
            this._tmBuildFullDiagram();
            this._tmDiagramBuilt = true;
        }
    }

    _tmBuildFullDiagram() {
        const diagramEl = document.getElementById('tm-diagram');
        if (!diagramEl) return;
        const aps = this._tmAps || [];
        const adrs = this._tmAdrs || [];
        if (!aps.length) { diagramEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:0.85rem;">No attack paths to display.</div>'; return; }

        // Collect all unique nodes and edges across all APs
        const nodeSet = new Map(); // node -> {hops: [], aps: []}
        const edges = [];
        const tierColor = {CRITICAL: '#DC143C', HIGH: '#FF8C00', MEDIUM: '#cc9900', LOW: '#32CD32'};

        aps.forEach(ap => {
            const adrId = ap.adr_id || (ap.adr_ids || [])[0] || '';
            const adr = adrs.find(a => a.adr_id === adrId);
            const pathNodes = ap.path || [];
            const hopByNode = {};
            if (adr) adr.hops.forEach(h => { hopByNode[h.node] = h; });

            pathNodes.forEach((node, i) => {
                if (!nodeSet.has(node)) nodeSet.set(node, {hops: [], aps: []});
                nodeSet.get(node).aps.push(ap.id);
                if (hopByNode[node]) nodeSet.get(node).hops.push(hopByNode[node]);
                if (i < pathNodes.length - 1) {
                    edges.push({from: node, to: pathNodes[i + 1], apId: ap.id, tier: ap.criticality_tier});
                }
            });
        });

        // Layout: arrange nodes left-to-right by first-appearance order
        const nodeList = Array.from(nodeSet.keys());
        const columns = {};
        let col = 0;
        aps.forEach(ap => {
            (ap.path || []).forEach(n => { if (columns[n] === undefined) columns[n] = col++; });
        });

        const nodeW = 100, nodeH = 36, gapX = 60, gapY = 70, padX = 20, padY = 20;
        const sortedNodes = nodeList.sort((a, b) => (columns[a] || 0) - (columns[b] || 0));

        // Assign rows: nodes that appear in multiple APs get their own row per AP usage
        const nodePos = {};
        sortedNodes.forEach((n, i) => { nodePos[n] = {x: padX + i * (nodeW + gapX), y: padY}; });

        const totalW = Math.max(400, padX * 2 + sortedNodes.length * (nodeW + gapX) - gapX);
        const totalH = nodeH + padY * 2 + 40;

        let svgParts = [`<defs><marker id="fgarrow" markerWidth="7" markerHeight="5" refX="6" refY="2.5" orient="auto"><polygon points="0 0,7 2.5,0 5" fill="#FF8C00" opacity="0.7"/></marker></defs>`];
        svgParts.unshift(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${totalW} ${totalH}" style="width:100%; max-width:${totalW}px; display:block;" aria-label="Full architecture diagram">`);

        // Edges
        edges.forEach(e => {
            const from = nodePos[e.from];
            const to = nodePos[e.to];
            if (!from || !to) return;
            const ec = tierColor[e.tier] || '#888';
            svgParts.push(`<line x1="${from.x + nodeW}" y1="${from.y + nodeH / 2}" x2="${to.x}" y2="${to.y + nodeH / 2}" stroke="${ec}" stroke-width="1.5" stroke-opacity="0.5" marker-end="url(#fgarrow)"/>`);
        });

        // Nodes
        sortedNodes.forEach(n => {
            const pos = nodePos[n];
            const info = nodeSet.get(n);
            const firstHop = info.hops[0];
            const hasGap = firstHop && firstHop.gap_note;
            const hasCtrl = firstHop && firstHop.controls && firstHop.controls.length > 0;
            const fill = hasGap ? '#FF8C00' : hasCtrl ? '#32CD32' : '#1E90FF';
            const label = n.length > 11 ? n.slice(0, 10) + '…' : n;
            const cx = pos.x + nodeW / 2;
            const cy = pos.y + nodeH / 2;
            svgParts.push(`<g onclick="window.dashboard._tmSelectApFromNode('${this._esc(n)}')" style="cursor:pointer;" title="${this._esc(n)}">
                <rect x="${pos.x}" y="${pos.y}" width="${nodeW}" height="${nodeH}" rx="5" fill="${fill}22" stroke="${fill}" stroke-width="1.5"/>
                <text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="11" fill="var(--text-color)" font-weight="600">${this._esc(label)}</text>
                ${hasGap ? `<circle cx="${pos.x + nodeW - 7}" cy="${pos.y + 7}" r="5" fill="#FF8C00"/><text x="${pos.x + nodeW - 7}" y="${pos.y + 11}" text-anchor="middle" font-size="7" fill="#fff" font-weight="700">!</text>` : ''}
            </g>
            <text x="${cx}" y="${pos.y + nodeH + 14}" text-anchor="middle" font-size="9" fill="var(--text-tertiary)">${this._esc(info.aps.slice(0,2).join(','))}</text>`);
        });

        svgParts.push(`</svg>`);
        diagramEl.innerHTML = svgParts.join('\n') + `<div style="margin-top:0.5rem; font-size:0.72rem; color:var(--text-tertiary);">Click a node to navigate to its attack path. <span style="color:#32CD32;">Green</span> = controlled, <span style="color:#FF8C00;">orange</span> = gap, <span style="color:#1E90FF;">blue</span> = no techniques.</div>`;
    }

    _tmSelectApFromNode(nodeName) {
        const aps = this._tmAps || [];
        const ap = aps.find(a => (a.path || []).includes(nodeName));
        if (ap) this._tmSelectAp(ap.id);
    }

    _tmInitResizer() {
        const handle = document.getElementById('tm-resize-handle');
        const left   = document.getElementById('tm-left');
        if (!handle || !left || handle._resizerBound) return;
        handle._resizerBound = true;

        let startX = 0, startW = 0;

        const onMove = (e) => {
            const dx = (e.clientX || (e.touches && e.touches[0].clientX) || 0) - startX;
            const newW = Math.max(180, Math.min(520, startW + dx));
            left.style.width = newW + 'px';
        };
        const onUp = () => {
            handle.classList.remove('dragging');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onUp);
            document.body.style.userSelect = '';
            document.body.style.cursor = '';
        };
        handle.addEventListener('mousedown', (e) => {
            startX = e.clientX;
            startW = left.getBoundingClientRect().width;
            handle.classList.add('dragging');
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            e.preventDefault();
        });
        handle.addEventListener('touchstart', (e) => {
            startX = e.touches[0].clientX;
            startW = left.getBoundingClientRect().width;
            handle.classList.add('dragging');
            document.addEventListener('touchmove', onMove, {passive: false});
            document.addEventListener('touchend', onUp);
            e.preventDefault();
        }, {passive: false});
    }

    _esc(str) {
        return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
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
            '01_executive_summary.md': {
                id: 'executive', title: 'Executive Summary', icon: '📊', audience: 'stakeholder', type: 'markdown',
                desc: 'High-level threat overview for leadership and CISOs',
                personas: ['CIO', 'CISO'],
                readersContext: 'Written for executive stakeholders who need a concise risk picture without technical detail. It answers: how exposed are we, what is the confidence in this assessment, and what is the headline recommendation? Use this to brief the board or justify security investment.',
            },
            '03_action_plan.md': {
                id: 'action', title: 'Action Plan', icon: '✅', audience: 'stakeholder', type: 'markdown',
                desc: 'Prioritised recommendations with implementation steps',
                personas: ['CISO', 'Security Engineer', 'IT Team'],
                readersContext: 'Translates the threat analysis into a sequenced to-do list ranked by risk reduction and implementation effort. CISOs use it to set quarterly security roadmaps; security engineers and IT teams use it to understand what to build or configure first.',
            },
            '08_improvement_summary.md': {
                id: 'improvement', title: 'Improvement Summary', icon: '🗺️', audience: 'stakeholder', type: 'markdown',
                desc: 'Roadmap across Quick Win, Recommended, and Maximum tiers',
                personas: ['CISO', 'Security Engineer'],
                readersContext: 'Three-tier roadmap showing risk reduction at each investment level. Quick Wins deliver the highest security gain per unit effort. Recommended balances security with usability. Maximum covers all residual risk. Decision-makers use this to match security spend to risk appetite.',
            },
            'before.mmd': {
                id: 'before', title: 'Current Architecture', icon: '⚠️', audience: 'stakeholder', type: 'mermaid', color: 'var(--danger-color)',
                desc: 'Architecture before hardening controls are applied',
                personas: ['CIO', 'CISO', 'Security Engineer'],
                readersContext: 'Visual map of the architecture as it stands today, with attack paths highlighted. Each red node or edge marks an exploitable gap. CIOs use this to understand what systems are at risk; security engineers use it to identify where to focus hardening effort first.',
            },
            'after.mmd': {
                id: 'after', title: 'Hardened Architecture', icon: '🛡️', audience: 'stakeholder', type: 'mermaid', color: 'var(--secondary-color)',
                desc: 'Architecture with all recommended controls applied',
                personas: ['CIO', 'CISO', 'Security Engineer', 'IT Team'],
                readersContext: 'Shows the target state once all recommended controls are in place. Green nodes indicate hardened components. IT teams use this as the "done" picture to work toward; CISOs use it to communicate the security improvement story to leadership.',
            },
            'after_bh.mmd': {
                id: 'after-bh', title: 'BH Chain Overlay', icon: '⚔️', audience: 'technical', type: 'mermaid', color: '#ff8c00',
                desc: 'Hardened architecture + Blackhat cross-path chain edges and gap controls',
                personas: ['Security Engineer', 'CISO'],
                readersContext: 'The hardened architecture overlaid with Blackhat cross-path chain analysis. Amber dashed edges show pivot routes that remain exploitable even after per-path hardening. Security engineers use this to identify controls that close cross-path chaining risk that single-AP mitigations cannot address.',
            },
            '02_technical_report.md': {
                id: 'technical', title: 'Technical Report', icon: '🔧', audience: 'technical', type: 'markdown',
                desc: 'Full MITRE ATT&CK technique mappings and control analysis',
                personas: ['Security Engineer'],
                readersContext: 'The complete technical deep-dive: every MITRE ATT&CK technique identified, its RAPIDS risk score, and the specific controls mapped to each. Security engineers use this to verify coverage completeness and as a reference when implementing controls or updating the threat model.',
            },
            '08a_quick_wins.mmd': {
                id: 'tier-a', title: 'Quick Wins Diagram', icon: '⚡', audience: 'technical', type: 'mermaid', color: 'var(--secondary-color)',
                desc: 'Architecture diagram with Quick Win controls highlighted',
                personas: ['Security Engineer', 'IT Team'],
                readersContext: 'Architecture annotated with Quick Win control placements — the changes that close the biggest gaps fastest. IT teams use this to plan sprint work; security engineers use it to validate that the right nodes are being hardened first.',
            },
            '08b_recommended_target.mmd': {
                id: 'tier-b', title: 'Recommended Diagram', icon: '📈', audience: 'technical', type: 'mermaid', color: 'var(--primary-color)',
                desc: 'Architecture diagram with Recommended controls highlighted',
                personas: ['Security Engineer', 'IT Team'],
                readersContext: 'The balanced target-state architecture: Recommended tier controls applied. This is the most practical roadmap for most organisations — good security posture without over-engineering. Use this as the reference architecture for the next 6–12 months.',
            },
            '08c_maximum_security.mmd': {
                id: 'tier-c', title: 'Maximum Coverage', icon: '🔒', audience: 'technical', type: 'mermaid', color: 'var(--warning-color)',
                desc: 'Architecture diagram with Maximum controls highlighted',
                personas: ['Security Engineer', 'CISO'],
                readersContext: 'All controls applied — the highest achievable security posture. Some of these controls have high implementation effort or user friction. Security architects and CISOs use this to understand the theoretical ceiling and to evaluate which diminishing-return controls are still worth pursuing given the risk context.',
            },
            'threatmodel_adr.mmd': {
                id: 'tm-adr', title: 'ThreatModel + ADR', icon: '🗂️', audience: 'technical', type: 'mermaid', color: '#6c757d',
                desc: 'Per-AP subgraphs with per-hop controls, gap notes, and ADR annotations',
                personas: ['Security Engineer'],
                readersContext: 'Per-attack-path subgraphs showing exactly which controls are placed at each hop, with gap annotations and ADR (Architecture Decision Record) notes. Security engineers use this to verify that every hop in every attack path has a control rationale and that ADR decisions close the intended gap.',
            },
            'threatmodel_adr_bh.mmd': {
                id: 'tm-adr-bh', title: 'ThreatModel + ADR + BH', icon: '⚔️', audience: 'technical', type: 'mermaid', color: '#d63384',
                desc: 'ThreatModel+ADR with Blackhat cross-path chain subgraphs appended',
                personas: ['Security Engineer', 'CISO'],
                readersContext: 'Extends ThreatModel+ADR with Blackhat cross-path chain subgraphs at the end. These show the lateral movement routes that remain available after per-path hardening. Use this when doing a comprehensive threat model review that needs to account for chained attack scenarios, not just individual paths.',
            },
            '00_executive_dashboard.md': {
                id: 'exec-dashboard', title: 'Executive Dashboard', icon: '🖥️', audience: 'stakeholder', type: 'markdown',
                desc: 'One-page visual dashboard — risk scores, coverage, and headline controls at a glance',
                personas: ['CIO', 'CISO'],
                readersContext: 'A single-page snapshot designed for rapid briefings. Shows the composite risk score, RAPIDS confidence, control coverage percentage, and the top three headline recommendations. CIOs use this as a standing agenda item in security reviews; CISOs use it to track posture improvement across analysis runs.',
            },
            '09_threat_model.md': {
                id: 'threat-model', title: 'Threat Model', icon: '🎯', audience: 'technical', type: 'markdown',
                desc: 'Structured per-AP threat model — actors, assets, techniques, and controls for each attack path',
                personas: ['Security Engineer', 'CISO'],
                readersContext: 'A formal threat model structured by attack path. For each path it records the threat actor, targeted assets, MITRE ATT&CK techniques used, existing controls, and residual gaps. Security engineers use this as the authoritative reference for control traceability; CISOs use it for audit evidence and compliance submissions.',
            },
            '10_adr_report.md': {
                id: 'adr-report', title: 'ADR Report', icon: '📝', audience: 'technical', type: 'markdown',
                desc: 'Architecture Decision Records — per-path master ADR with rationale, alternatives, and control placements',
                personas: ['Security Engineer'],
                readersContext: 'Architecture Decision Records (ADRs) document every security control placement decision: what was decided, why, which alternatives were considered, and what risk is accepted. Security engineers use this to onboard new team members, justify control choices to auditors, and track which ADR decisions need revisiting as the architecture evolves.',
            },
        };

        // Skip JSON and README — JSON belongs in Raw Data, README is noise
        const SKIP_EXTS = new Set(['.json']);
        const SKIP_FILES = new Set(['README.md']);

        const fileMap = {};
        allFiles.forEach(f => fileMap[f.filename] = f);

        const allReports = [];
        Object.entries(REPORT_CATALOGUE).forEach(([filename, meta]) => {
            if (fileMap[filename]) {
                allReports.push({ ...meta, filename, url: fileMap[filename].url, size: fileMap[filename].size });
            }
        });

        // Any unrecognised non-JSON files go in too (uncatalogued)
        allFiles.forEach(f => {
            const ext = f.filename.includes('.') ? '.' + f.filename.split('.').pop() : '';
            if (!REPORT_CATALOGUE[f.filename] && !SKIP_EXTS.has(ext) && !SKIP_FILES.has(f.filename)) {
                allReports.push({
                    id: f.filename, title: f.filename, icon: f.type === 'mermaid' ? '🏗️' : '📄',
                    desc: '', personas: [], audience: 'technical', type: f.type || 'text',
                    filename: f.filename, url: f.url, size: f.size, readersContext: '',
                });
            }
        });

        const PERSONAS = ['All', 'CIO', 'CISO', 'Security Engineer', 'IT Team'];

        const personaChips = PERSONAS.map((p, i) =>
            `<button class="rp-persona-chip${i === 0 ? ' active' : ''}" data-persona="${p}"
              style="padding:0.2rem 0.65rem;border-radius:12px;border:1.5px solid ${i === 0 ? 'var(--primary-color)' : 'var(--border-color)'};
                     background:${i === 0 ? 'var(--primary-color)' : 'transparent'};
                     color:${i === 0 ? 'white' : 'var(--text-secondary)'};font-size:0.78rem;font-weight:600;cursor:pointer;transition:all 0.15s;">${p}</button>`
        ).join('');

        listContainer.innerHTML = `
            <!-- Download packs -->
            <div style="display:flex;gap:0.75rem;margin-bottom:1rem;flex-wrap:wrap;align-items:center;">
                <span style="font-size:0.8125rem;color:var(--text-secondary);font-weight:600;">Download:</span>
                <a href="/api/v1/reports/${archName}/download?pack=stakeholder" download="${archName}_stakeholder.zip"
                   class="btn-primary" style="padding:0.5rem 1rem;font-size:0.8125rem;font-weight:600;text-decoration:none;">⬇ Stakeholder Pack</a>
                <a href="/api/v1/reports/${archName}/download?pack=reports" download="${archName}_reports.zip"
                   style="padding:0.5rem 1rem;font-size:0.8125rem;font-weight:600;background:transparent;color:var(--text-color);border:1.5px solid var(--border-color);border-radius:6px;text-decoration:none;">⬇ All Reports</a>
                <a href="/api/v1/reports/${archName}/briefing" download="${archName}_briefing.md"
                   style="padding:0.5rem 1rem;font-size:0.8125rem;font-weight:600;background:transparent;color:#a855f7;border:1.5px solid #a855f744;border-radius:6px;text-decoration:none;" title="Single-file Markdown briefing for offline sharing — no dashboard needed">📄 Export Briefing</a>
                <span style="font-size:0.72rem;color:var(--text-tertiary);margin-left:auto;">Click a card to preview · ⬇ to download · JSON → Raw Data tab</span>
            </div>

            <!-- Persona filter bar -->
            <div style="margin-bottom:0.9rem;">
                <span style="font-size:0.75rem;color:var(--text-tertiary);margin-right:0.5rem;font-weight:600;">Filter by role:</span>
                <div id="rp-persona-chips" style="display:inline-flex;flex-wrap:wrap;gap:0.35rem;">${personaChips}</div>
            </div>

            <!-- Card grid -->
            <div id="rp-card-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:0.625rem;">
                ${allReports.map(r => this._reportCard(r, archName)).join('')}
            </div>
        `;

        // Persona filter logic
        const chipsEl = listContainer.querySelector('#rp-persona-chips');
        if (chipsEl) {
            chipsEl.querySelectorAll('.rp-persona-chip').forEach(chip => {
                chip.addEventListener('click', () => {
                    chipsEl.querySelectorAll('.rp-persona-chip').forEach(c => {
                        c.classList.remove('active');
                        c.style.background = 'transparent';
                        c.style.color = 'var(--text-secondary)';
                        c.style.borderColor = 'var(--border-color)';
                    });
                    chip.classList.add('active');
                    chip.style.background = 'var(--primary-color)';
                    chip.style.color = 'white';
                    chip.style.borderColor = 'var(--primary-color)';

                    const persona = chip.dataset.persona;
                    listContainer.querySelectorAll('[data-report-id]').forEach(card => {
                        const rp = card.dataset.personas ? JSON.parse(card.dataset.personas) : [];
                        const show = persona === 'All' || rp.length === 0 || rp.includes(persona);
                        card.style.display = show ? '' : 'none';
                    });
                });
            });
        }

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
        const personasJson = JSON.stringify(report.personas || []).replace(/"/g, '&quot;');
        const personaChips = (report.personas || []).map(p =>
            `<span style="padding:0.05rem 0.4rem;background:var(--primary-color)18;color:var(--primary-color);border-radius:4px;font-size:0.65rem;font-weight:600;">${p}</span>`
        ).join('');
        return `
            <div data-report-id="${report.id}" data-personas="${personasJson}" style="
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
                        ${report.desc ? `<div style="font-size: 0.72rem; color: var(--text-tertiary); margin-top: 0.1rem; line-height: 1.3;">${report.desc}</div>` : ''}
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem; flex-wrap: wrap; gap: 0.3rem;">
                    <div style="display:flex;gap:0.25rem;flex-wrap:wrap;">${personaChips}</div>
                    <a href="/api/v1/reports/${archName}/files/${report.filename}" target="_blank"
                       style="font-size: 0.75rem; color: var(--primary-color); text-decoration: none; padding: 0.125rem 0.375rem; border: 1px solid var(--primary-color); border-radius: 4px; flex-shrink:0;"
                       onclick="event.stopPropagation()">⬇</a>
                </div>
            </div>
        `;
    }

    async _renderReportInRightPane(report, archName) {
        const downloadLink = `<a href="/api/v1/reports/${archName}/files/${report.filename}" download="${report.filename}" class="btn-primary" style="display:inline-block;text-decoration:none;padding:0.375rem 0.875rem;font-size:0.8125rem;margin-bottom:0.75rem;">⬇ Download ${report.filename}</a>`;

        // Readers context — who reads this and what decision it enables
        const contextHtml = report.readersContext ? `
            <div style="margin-bottom:1rem;padding:0.75rem 1rem;background:var(--nav-hover-bg);border-left:3px solid var(--primary-color);border-radius:0 6px 6px 0;font-size:0.82rem;color:var(--text-secondary);line-height:1.55;">
                ${report.readersContext}
            </div>` : '';

        this.showRightPane(`${report.icon} ${report.title}`, `
            ${contextHtml}
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

    setupDiagramZoom(prefix) {
        const container = document.getElementById(`${prefix}-container`) || document.getElementById(prefix);
        if (!container) return;
        const getSvg = () => container.querySelector('svg');
        if (this[`${prefix}Scale`] === undefined) this[`${prefix}Scale`] = 1;
        const applyScale = s => {
            const svg = getSvg(); if (!svg) return;
            const w = parseFloat(svg.getAttribute('width'))  || 800;
            const h = parseFloat(svg.getAttribute('height')) || 600;
            if (!this[`${prefix}OrigW`]) { this[`${prefix}OrigW`] = w; this[`${prefix}OrigH`] = h; }
            this[`${prefix}Scale`] = s;
            svg.setAttribute('width',  this[`${prefix}OrigW`] * s);
            svg.setAttribute('height', this[`${prefix}OrigH`] * s);
            svg.style.maxWidth = 'none';
        };
        setTimeout(() => {
            const svg = getSvg(); if (!svg) return;
            const w = parseFloat(svg.getAttribute('width')) || 800;
            this[`${prefix}OrigW`] = w;
            this[`${prefix}OrigH`] = parseFloat(svg.getAttribute('height')) || 600;
            const fit = Math.min(1, (container.clientWidth - 32) / w);
            applyScale(fit);
        }, 200);
        const wire = (id, fn) => {
            const el = document.getElementById(id); if (!el) return;
            const clone = el.cloneNode(true); el.parentNode.replaceChild(clone, el);
            clone.addEventListener('click', fn);
        };
        wire(`${prefix}-zoom-in`,    () => applyScale(Math.min(this[`${prefix}Scale`] + 0.2, 4)));
        wire(`${prefix}-zoom-out`,   () => applyScale(Math.max(this[`${prefix}Scale`] - 0.2, 0.1)));
        wire(`${prefix}-zoom-reset`, () => applyScale(1));
        wire(`${prefix}-fit-height`, () => applyScale((container.clientHeight - 32) / (this[`${prefix}OrigH`] || 600)));
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
                            <div id="erp-card-purple_team" style="flex:1; min-width:130px; padding:0.5rem 0.75rem; border-radius:6px; border:1px solid var(--border-color); background:var(--nav-hover-bg); opacity:0.45; transition:opacity 0.3s, border-color 0.3s;">
                                <div style="font-size:0.875rem;">🟣</div>
                                <div style="font-size:0.75rem; font-weight:600; color:var(--text-color); margin-top:0.2rem;">Purple Team</div>
                                <div id="erp-card-purple_team-status" style="font-size:0.7rem; color:var(--text-tertiary);">Waiting</div>
                                <div id="erp-card-purple_team-preview" style="display:none; margin-top:0.35rem; font-size:0.65rem; color:var(--text-tertiary); line-height:1.4;"></div>
                            </div>
                            <div id="erp-card-blackhat" style="flex:1; min-width:130px; padding:0.5rem 0.75rem; border-radius:6px; border:1px solid var(--border-color); background:var(--nav-hover-bg); opacity:0.45; transition:opacity 0.3s, border-color 0.3s;">
                                <div style="font-size:0.875rem;">⚔️</div>
                                <div style="font-size:0.75rem; font-weight:600; color:var(--text-color); margin-top:0.2rem;">Blackhat</div>
                                <div id="erp-card-blackhat-status" style="font-size:0.7rem; color:var(--text-tertiary);">Waiting</div>
                                <div id="erp-card-blackhat-preview" style="display:none; margin-top:0.35rem; font-size:0.65rem; color:var(--text-tertiary); line-height:1.4;"></div>
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
        const stageMap = { architect: '🏛️ Architect', tester: '🔬 Tester', red_team: '🎯 Red Team', purple_team: '🟣 Purple Team', blackhat: '⚔️ Blackhat', synthesis: '⚙️ Synthesis', complete: '✅ Done' };
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
        const agentOrder = ['architect', 'tester', 'red_team', 'purple_team', 'blackhat', 'synthesis'];
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

            // Count how many critics actually ran (have an entry in expert_validations)
            const expertValidationsForCount = moe.expert_validations || {};
            const ranCriticKeys = ['architect', 'tester', 'red_team', 'purple_team', 'blackhat'].filter(k => expertValidationsForCount[k]);
            const ranCriticLabels = { architect: 'Architect', tester: 'Coverage Auditor', red_team: 'Exploit Analyst', purple_team: 'Purple Team', blackhat: 'Blackhat' };
            const criticCountLabel = ranCriticKeys.length + ' critic' + (ranCriticKeys.length !== 1 ? 's' : '');
            const criticNamesLabel = ranCriticKeys.map(k => ranCriticLabels[k]).join(', ');

            // Build blindspots HTML
            let blindspotsHtml = '';
            if (blindspots.length > 0) {
                // Classify each blindspot by topic to decide note vs action
                const _bsClassify = (b) => {
                    const desc = (b.description || '').toLowerCase();
                    const rec  = (b.recommendation || '').toLowerCase();
                    const combined = desc + ' ' + rec;
                    if (combined.includes('supply chain') || combined.includes('vendor') || combined.includes('third-party') || combined.includes('third party')) {
                        return { actionable: true, pill: '⚠ Act', pillColor: 'var(--warning-color)', action: 'Conduct a separate vendor risk assessment. Review all third-party integrations for contractual security controls and incident notification requirements.' };
                    }
                    if (combined.includes('bcp') || combined.includes('business continuity') || combined.includes('disaster recovery') || combined.includes('dr plan') || combined.includes('availability')) {
                        return { actionable: true, pill: '⚠ Act', pillColor: 'var(--warning-color)', action: 'Evaluate resilience controls: define RTO/RPO targets, map which attack paths impact availability, and add BCP/DR controls to the relevant ADRs.' };
                    }
                    if (combined.includes('api gateway') || combined.includes('api-gateway')) {
                        return { actionable: true, pill: '⚠ Act', pillColor: 'var(--warning-color)', action: 'Review attack paths that traverse external-facing entry points — an API Gateway node is expected between external actors and internal services. If missing from your diagram, add it and re-run analysis.' };
                    }
                    return { actionable: false, pill: '📋 Note', pillColor: 'var(--text-tertiary)', action: null };
                };
                let cards = '';
                for (const b of blindspots) {
                    const cls = _bsClassify(b);
                    const pillHtml = '<span style="font-size:0.68rem; font-weight:700; color:' + cls.pillColor + '; background:' + cls.pillColor + '18; border:1px solid ' + cls.pillColor + '44; border-radius:8px; padding:1px 7px; margin-left:0.5rem; white-space:nowrap;">' + cls.pill + '</span>';
                    cards += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid ' + (cls.actionable ? 'var(--warning-color)' : 'var(--primary-color)') + ';">'
                        + '<div style="font-size: 0.875rem; font-weight:600; color: var(--text-color); display:flex; align-items:baseline; flex-wrap:wrap; gap:0.2rem;">' + (b.description || '') + pillHtml + '</div>'
                        + (b.why_missed ? '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-top:0.25rem;">Why missed: ' + b.why_missed + '</div>' : '')
                        + (b.recommendation ? '<div style="font-size:0.8125rem; color:var(--secondary-color); margin-top:0.25rem;">→ ' + b.recommendation + '</div>' : '')
                        + (cls.action ? '<div style="font-size:0.75rem; color:var(--warning-color); margin-top:0.3rem; padding-top:0.3rem; border-top:1px solid var(--border-color);">Action: ' + cls.action + '</div>' : '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.3rem; padding-top:0.3rem; border-top:1px solid var(--border-color);">No immediate action required — document for awareness and revisit when scope changes.</div>')
                        + '</div>';
                }
                blindspotsHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                    + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">🔍 Blindspots</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">Gaps all ' + criticCountLabel + ' structurally could not see. <strong>⚠ Act</strong> = actionable now. <strong>📋 Note</strong> = awareness only.</p></div>'
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
                        + (c.purple_team_view ? '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-top:0.2rem;">🟣 Purple Team: ' + c.purple_team_view + '</div>' : '')
                        + (c.blackhat_view ? '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-top:0.2rem;">⚔️ Blackhat: ' + c.blackhat_view + '</div>' : '')
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
                        + '<div style="padding:0.65rem 1rem; background:var(--secondary-color)14; border:1px solid var(--secondary-color)44; border-radius:8px; font-size:0.875rem; color:var(--secondary-color);">All ' + criticCountLabel + ' (' + criticNamesLabel + ') read each other\'s output and found no conflicting positions — this is genuine consensus.</div>'
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
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;">Synthesised from all ' + criticCountLabel + ' findings. Cost and effort from Red Team exploit roadmap — not estimated where absent.</p></div>'
                    + '<span class="er-chevron" style="font-size:1.25rem; color:var(--text-tertiary); min-width:1rem; text-align:center;">∨</span>'
                    + '</div>'
                    + '<div class="er-panel-body" style="padding: 0 1.25rem 1.25rem;">' + tierCards + '</div>'
                    + '</div>';
            }

            const bhValidation = expertValidations.blackhat || null;
            const bhAdjNum = parseFloat(((confidence.adjustments?.blackhat || 0) * 100).toFixed(1));

            const expertDefs = [
                { key: 'architect',    icon: '🏛️', label: 'Architecture Review',     role: 'Structural gaps, unmodelled threats, ADR completeness' },
                { key: 'tester',       icon: '🔬', label: 'Coverage Audit',           role: 'MITRE mapping accuracy, control effectiveness, configuration validation' },
                { key: 'red_team',     icon: '🎯', label: 'Exploit Analysis',         role: 'Bypass paths, attack feasibility, control evasion under active exploitation' },
                { key: 'purple_team',  icon: '🟣', label: 'Purple Team',              role: 'Detection depth, coverage gaps, investigation value & ADR operability', isOptional: true },
                { key: 'blackhat',     icon: '⚔️', label: 'Blackhat Cross-Path',      role: 'Cross-path chaining, pivot-diverge routes & chain exploits (supreme critic)', isOptional: true },
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
                // Optional critics: show a "not run" card if absent
                if (!v) {
                    if (e.isOptional) {
                        const notRunNote = e.key === 'blackhat'
                            ? 'Not run — enable in Config → MoE → Blackhat Critic (Layer 2E) and re-run Expert Review'
                            : 'Not run — enable in Config → MoE → Purple Team Critic (Layer 2D) and re-run Expert Review';
                        expertPanelCards += '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; border: 1px solid var(--border-color); overflow:hidden; opacity:0.55;">'
                            + '<div style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center;">'
                            + '<div style="display:flex; align-items:center; gap:0.75rem;">'
                            + '<span style="font-size:1.5rem;">' + e.icon + '</span>'
                            + '<div><div style="font-weight:700; color:var(--text-tertiary);">' + e.label + '</div>'
                            + '<div style="font-size:0.8125rem; color:var(--text-tertiary);">' + e.role + '</div></div>'
                            + '</div>'
                            + '<div style="font-size:0.8125rem; color:var(--text-tertiary); font-style:italic;">' + notRunNote + '</div>'
                            + '</div>'
                            + '</div>';
                    }
                    continue;
                }
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
                // Blackhat breakdown: chain findings, stealth score, shared nodes
                if (e.key === 'blackhat' && v.breakdown) {
                    const bd = v.breakdown;
                    const chains = bd.chained_exploit_findings || [];
                    const stealth = bd.stealth_score || 0;
                    const stealthTechs = bd.stealthy_techniques || [];
                    const shared = bd.shared_nodes || {};
                    const lrp = bd.least_resistance_paths || [];
                    const chainGaps = bd.mitigation_gaps_for_chains || [];
                    const unique = (bd.uniqueness_vs_critics || {}).new_findings_not_in_redteam || [];
                    const stealthColor = stealth >= 60 ? 'var(--danger-color)' : stealth >= 35 ? 'var(--warning-color)' : 'var(--secondary-color)';
                    const sharedNodeList = Object.keys(shared).join(', ') || 'none';
                    let bhInner = '<div style="display:flex; flex-wrap:wrap; gap:0.5rem; margin-bottom:0.65rem;">'
                        + '<span style="padding:2px 8px; border-radius:8px; font-size:0.76rem; background:' + stealthColor + '18; border:1px solid ' + stealthColor + '44; color:' + stealthColor + '; font-weight:600;">Stealth: ' + stealth + '/100</span>'
                        + '<span style="padding:2px 8px; border-radius:8px; font-size:0.76rem; background:var(--nav-hover-bg); color:var(--text-secondary); border:1px solid var(--border-color);">' + chains.length + ' chain finding' + (chains.length !== 1 ? 's' : '') + '</span>'
                        + '<span style="padding:2px 8px; border-radius:8px; font-size:0.76rem; background:var(--nav-hover-bg); color:var(--text-secondary); border:1px solid var(--border-color);">' + Object.keys(shared).length + ' shared node' + (Object.keys(shared).length !== 1 ? 's' : '') + ': ' + sharedNodeList + '</span>'
                        + (unique.length ? '<span style="padding:2px 8px; border-radius:8px; font-size:0.76rem; background:var(--warning-color)18; border:1px solid var(--warning-color)44; color:var(--warning-color);">' + unique.length + ' unique vs Red Team</span>' : '')
                        + '</div>';
                    if (chains.length) {
                        bhInner += '<div style="font-size:0.78rem; font-weight:600; color:var(--text-secondary); margin-bottom:0.35rem;">Chain findings:</div>';
                        for (const ch of chains.slice(0, 5)) {
                            bhInner += '<div style="padding:0.5rem 0.65rem; background:var(--nav-hover-bg); border-left:3px solid var(--warning-color); border-radius:4px; margin-bottom:0.3rem; font-size:0.78rem;">'
                                + (ch.chain || ch.description || JSON.stringify(ch))
                                + '</div>';
                        }
                    }
                    if (stealthTechs.length) {
                        bhInner += '<div style="font-size:0.76rem; color:var(--text-tertiary); margin-top:0.4rem;">Stealth techniques: ' + stealthTechs.join(', ') + '</div>';
                    }
                    if (lrp.length) {
                        bhInner += '<div style="font-size:0.76rem; color:var(--text-tertiary); margin-top:0.2rem;">Least-resistance paths: ' + lrp.slice(0,3).map(p => Array.isArray(p) ? p.join('→') : String(p)).join(' | ') + '</div>';
                    }
                    if (chainGaps.length) {
                        bhInner += '<div style="font-size:0.76rem; color:var(--warning-color); margin-top:0.3rem;">Chain mitigation gaps: ' + chainGaps.slice(0,4).join(', ') + '</div>';
                    }
                    // Link to after_bh.mmd in Reports tab
                    bhInner += '<div style="margin-top:0.65rem; padding-top:0.5rem; border-top:1px solid var(--border-color);">'
                        + '<span style="font-size:0.78rem; color:var(--text-tertiary);">Cross-path chains visible in </span>'
                        + '<button onclick="window.dashboard._openBhDiagram()" style="font-size:0.78rem; color:#ff8c00; background:transparent; border:1px solid #ff8c0044; border-radius:6px; padding:2px 8px; cursor:pointer; margin-left:0.35rem;">⚔️ BH Chain Diagram →</button>'
                        + '</div>';
                    breakdownBars = '<div style="margin-bottom:0.75rem; padding:0.65rem 0.75rem; background:var(--nav-hover-bg); border-radius:6px;">' + bhInner + '</div>';
                }
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
                    inner += '<div style="margin: 0.75rem 0 0.5rem;">'
                        + '<div style="font-size:0.8125rem; font-weight:600; color:var(--text-tertiary); text-transform:uppercase; letter-spacing:0.04em;">For Review</div>'
                        + '<div style="font-size:0.72rem; color:var(--text-tertiary); margin-top:0.15rem;">UNSURE = raised by a single critic only. No second critic confirmed or refuted it — review and decide whether to act.</div>'
                        + '</div>';
                    for (const r of consensusReview) {
                        const known = isKnown(r);
                        const badge = known
                            ? '<span style="font-size:0.7rem; font-weight:700; color:var(--secondary-color); background:var(--secondary-color)18; border:1px solid var(--secondary-color)44; border-radius:8px; padding:1px 6px; margin-left:0.4rem;">KNOWN</span>'
                            : '<span style="font-size:0.7rem; font-weight:700; color:var(--text-tertiary); background:var(--nav-hover-bg); border:1px solid var(--border-color); border-radius:8px; padding:1px 6px; margin-left:0.4rem;">UNSURE</span>';
                        const src = (r.source || '').toLowerCase();
                        let actionHint = '';
                        if (src.includes('architect')) {
                            actionHint = 'Architecture concern — verify whether this applies to your specific design. If the finding describes a generic gap rather than a confirmed path, document as accepted risk or revisit on a more complex architecture diagram.';
                        } else if (src.includes('tester') || src.includes('coverage')) {
                            actionHint = 'Control coverage gap — check whether the flagged control exists and is correctly mapped. If the gap is real, add the missing control to the ADR.';
                        } else if (src.includes('red_team') || src.includes('red team') || src.includes('exploit')) {
                            actionHint = 'Exploit feasibility concern — assess whether this bypass path is realistic for your threat model. If confirmed, escalate to the Red Team improvement tier.';
                        } else if (src.includes('purple') || src.includes('detection')) {
                            actionHint = 'Detection gap — if this technique is in scope, add the suggested behavioral analytics or detection control (UEBA, DAM, anomaly detection) to the relevant ADR.';
                        } else if (src.includes('blackhat')) {
                            actionHint = 'Cross-path chain concern — review whether the identified pivot nodes are reachable in practice. If confirmed, treat as a high-priority chaining risk.';
                        } else {
                            actionHint = 'Review this finding: if it describes a real gap in your architecture, add a control to the relevant ADR. If it does not apply, document as accepted risk.';
                        }
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--border-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-secondary); display:flex; align-items:baseline; flex-wrap:wrap; gap:0.2rem;">' + (r.description || r.recommendation || '') + badge + '</div>'
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.2rem;">Raised by: ' + r.source + '</div>' : '')
                            + '<div style="font-size:0.75rem; color:var(--primary-color); margin-top:0.3rem; padding-top:0.3rem; border-top:1px solid var(--border-color);">→ ' + actionHint + '</div>'
                            + '</div>';
                    }
                }
                consensusHtml = '<div class="er-panel" style="background: var(--card-bg); border-radius: 10px; margin-bottom: 1rem; border: 1px solid var(--border-color); overflow:hidden;">'
                    + '<div class="er-panel-header" onclick="(function(h){var b=h.closest(\'.er-panel\').querySelector(\'.er-panel-body\');var c=h.querySelector(\'.er-chevron\');var open=b.style.display!==\'none\';b.style.display=open?\'none\':\'block\';c.textContent=open?\'›\':\' ⌄\';})(this)" style="padding: 1rem 1.25rem; display:flex; justify-content:space-between; align-items:center; cursor:pointer; user-select:none;">'
                    + '<div><h3 style="margin: 0 0 0.15rem; color: var(--text-color); font-size: 1rem;">Cross-Expert Findings</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0;"><strong>KNOWN</strong> = confirmed by ≥2 critics — act on these. <strong>UNSURE</strong> = single critic raised it, no second opinion yet — needs human review, not necessarily wrong.</p></div>'
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

    // Open after_bh.mmd in the Reports tab (right pane viewer)
    async _openBhDiagram() {
        const archName = this.analysisData?.architecture_name || this.analysisData?.architecture;
        if (!archName) return;
        try {
            const resp = await fetch(`/api/v1/reports/${encodeURIComponent(archName)}/files/after_bh.mmd`);
            if (!resp.ok) {
                this.showRightPane('⚔️ BH Chain Diagram', '<p style="color:var(--text-tertiary); padding:1rem;">after_bh.mmd not found — re-run Expert Review with Blackhat enabled.</p>');
                return;
            }
            const mmdContent = await resp.text();
            this.showRightPane('⚔️ Blackhat Cross-Path Chain Overlay', `
                <p style="font-size:0.8125rem; color:var(--text-secondary); margin:0 0 0.75rem;">
                    Cross-path chain edges (dashed orange/red) and gap controls (pink) overlaid on the hardened architecture.
                    Edges show pivot routes BH identified across multiple attack paths.
                </p>
                <div id="bh-diag-container" style="overflow:auto; max-height:calc(100vh - 260px); background:var(--code-bg); border-radius:8px; border:1px solid var(--border-color); padding:1rem;">
                    <div class="mermaid">${mmdContent}</div>
                </div>`);
            if (window.mermaid) {
                setTimeout(() => mermaid.run({ querySelector: '#bh-diag-container .mermaid' }).catch(() => {}), 50);
            }
        } catch (err) {
            this.showRightPane('⚔️ BH Chain Diagram', `<p style="color:var(--danger-color); padding:1rem;">${err.message}</p>`);
        }
    }

    // Build a live critic result card HTML from a critic_result SSE event payload
    _buildLiveCriticCard(data) {
        const labels = { architect: '🏛️ Architect', tester: '🔬 Coverage Auditor', red_team: '🎯 Exploit Analyst', purple_team: '🟣 Purple Team', blackhat: '⚔️ Blackhat' };
        const roles  = { architect: 'Architecture Review', tester: 'MITRE mapping, control effectiveness & configuration validation', red_team: 'Bypass paths, attack feasibility & control evasion', purple_team: 'Detection depth, coverage gaps & ADR operability', blackhat: 'Cross-path chain exploitation & pivot hacking' };
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
        const stageMap = { architect: '🏛️ Architect', tester: '🔬 Tester', red_team: '🎯 Red Team', purple_team: '🟣 Purple Team', blackhat: '⚔️ Blackhat', synthesis: '⚙️ Synthesis', complete: '✅ Done' };
        if (msgEl) msgEl.textContent = data.message || '';

        if (parallelMode) {
            // Per-critic bars: each stage drives its own bar
            const criticStages = ['architect', 'tester', 'red_team', 'purple_team', 'blackhat'];
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
                        const criticLabels = { architect: '🏛️ Architect', tester: '🔬 Coverage Audit', red_team: '🎯 Red Team', purple_team: '🟣 Purple Team', blackhat: '⚔️ Blackhat' };
                        for (const c of ['architect', 'tester', 'red_team', 'purple_team', 'blackhat']) {
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

        const agentOrder = ['architect', 'tester', 'red_team', 'purple_team', 'blackhat', 'synthesis'];
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
        if (parallelMode2 && ['architect', 'tester', 'red_team', 'purple_team', 'blackhat'].includes(critic)) {
            const cBar = document.getElementById('erp-bar-' + critic);
            const cPct = document.getElementById('erp-pct-' + critic);
            if (cBar) { cBar.style.width = '100%'; cBar.style.background = statusColor; }
            if (cPct) { cPct.textContent = '✓'; cPct.style.color = statusColor; }
        }

        // Stop parallel elapsed timer once all core critics have results
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
            '04_architect_critique.json': { title: 'Architecture Review', icon: '🏛️', desc: 'Expert assessment of structural gaps, unmodelled threats, and ADR completeness', group: 'expert' },
            '05_tester_critique.json':  { title: 'Coverage Audit',   icon: '🔬', desc: 'MITRE technique mapping accuracy, control effectiveness, configuration validation', group: 'expert' },
            '06_red_team_critique.json':{ title: 'Exploit Analysis', icon: '🎯', desc: 'Bypass paths, control evasion, and attack feasibility under active exploitation', group: 'expert' },
            '06b_purple_team_critique.json': { title: 'Purple Team', icon: '🟣', desc: 'Detection depth, coverage gaps, investigation value, and ADR operability', group: 'expert' },
            '06c_blackhat_critique.json': { title: 'Blackhat Cross-Path', icon: '⚔️', desc: 'Cross-path chaining, pivot-diverge routes, and chain exploit feasibility (supreme critic)', group: 'expert' },
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
            title: '🧑‍🏫 MoE — Base Settings',
            subtitle: 'Mixture-of-Experts pipeline: starting confidence, execution mode, and LLM parameters. Blackhat (Layer 2E) is the supreme critic and runs last.',
            fields: [
              { section:'moe', field:'enabled', label:'Enable Expert Review (MoE)',
                vtype:'select',
                options:[
                  {v:'true',  label:'true — Enabled (recommended)', rec:true},
                  {v:'false', label:'false — Deterministic only (skip all critics)'},
                ],
                desc:'Master switch for the full MoE expert review chain. When disabled, only the deterministic engine runs — no LLM calls. The three core critics (Architect, Coverage Auditor, Exploit Analyst) always run when MoE is enabled and cannot be individually disabled. Purple Team and Blackhat can be toggled separately below.',
                effects: ef('Enables full LLM-backed validation','Architect/Tester/Red Team always run; Purple Team/Blackhat optional','High','Requires LLM API key') },

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
                desc:'How the enabled critics run. Sequential means each critic sees prior results for cross-referencing. Applies to all critics including Purple Team and Blackhat if enabled.',
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

            ]
          },
          {
            title: '🏛️ MoE — Architect Critic (Layer 2A)',
            subtitle: 'Always on — cannot be disabled individually. Assesses structural coverage, defence-in-depth, and zero-trust alignment.',
            fields: [
              { section:'moe', field:'architect_sensitivity', label:'Sensitivity',
                vtype:'select',
                options:[
                  {v:'lenient',   label:'lenient — Fewer gaps flagged, higher tolerance for design trade-offs'},
                  {v:'balanced',  label:'balanced — Standard thresholds (recommended)', rec:true},
                  {v:'strict',    label:'strict — More gaps flagged, higher bar for design quality'},
                ],
                desc:'Controls how aggressively the Architect critic flags structural gaps. Lenient suits early-stage or exploratory architectures; strict suits production or regulated environments.',
                effects: ef('Strict = more gaps flagged','Strict = lower confidence scores','High','None') },
            ]
          },
          {
            title: '🧪 MoE — Tester Critic (Layer 2B)',
            subtitle: 'Always on — cannot be disabled individually. Validates MITRE ATT&CK technique mapping accuracy, control effectiveness, and configuration gaps.',
            fields: [
              { section:'moe', field:'tester_sensitivity', label:'Sensitivity',
                vtype:'select',
                options:[
                  {v:'lenient',   label:'lenient — Fewer MITRE mapping gaps flagged'},
                  {v:'balanced',  label:'balanced — Standard thresholds (recommended)', rec:true},
                  {v:'strict',    label:'strict — Stricter MITRE coverage bar, more gaps flagged'},
                ],
                desc:'Controls how strictly the Coverage Auditor validates technique-to-control mappings. Lenient reduces noise on immature mappings; strict ensures comprehensive coverage on production assessments.',
                effects: ef('Strict = more technique gaps flagged','Strict = lower confidence scores','High','None') },
            ]
          },
          {
            title: '🔴 MoE — Red Team Critic (Layer 2C)',
            subtitle: 'Always on — cannot be disabled individually. Scores exploit feasibility across bypass paths and control evasion. Lower score = harder to exploit (better).',
            fields: [
              { section:'moe', field:'red_team_sensitivity', label:'Sensitivity',
                vtype:'select',
                options:[
                  {v:'lenient',   label:'lenient — Only obvious, low-effort exploits trigger penalty'},
                  {v:'balanced',  label:'balanced — Standard thresholds (recommended)', rec:true},
                  {v:'strict',    label:'strict — Any realistic exploit path triggers penalty'},
                ],
                desc:'Controls how aggressively the Exploit Analyst penalises confidence. Lenient is appropriate for internal-only architectures with strong perimeter controls; strict is appropriate for internet-facing or high-value systems.',
                effects: ef('Strict = more exploit paths penalised','Strict = lower confidence scores','Very High','None') },
            ]
          },
          {
            title: '🟣 MoE — Purple Team Critic (Layer 2D)',
            subtitle: 'Detection depth and coverage gap analysis. Runs after Architect/Tester/Red Team and before Blackhat, feeding detection blindspot data to the cross-path analysis.',
            fields: [
              { section:'purple_team', field:'enabled', label:'Enable Purple Team Critic',
                vtype:'select',
                options:[
                  {v:'true',  label:'true — Enabled (recommended)', rec:true},
                  {v:'false', label:'false — Disabled'},
                ],
                desc:'When disabled, the core three critics (Architect, Coverage Auditor, Exploit Analyst) still run — the assessment is not broken. Purple Team adds detection-depth analysis: coverage gaps, blindspots, and ADR operability. Adds ~20–40s per run.',
                effects: ef('Surfaces detection/response gaps','Disabling skips detection-depth layer only — core assessment unaffected','High','Adds LLM call per run') },

              { section:'purple_team', field:'detection_focus', label:'Detection Focus Mode',
                vtype:'select',
                options:[
                  {v:'balanced',   label:'balanced — Coverage + Detection + ADR (recommended)', rec:true},
                  {v:'detection',  label:'detection — Emphasise detection blindspots'},
                  {v:'coverage',   label:'coverage — Emphasise unmapped technique coverage'},
                  {v:'adr',        label:'adr — Emphasise ADR operability failures'},
                ],
                desc:'Controls which of the three Purple Team lenses is weighted most heavily in the critique.',
                effects: ef('Shifts critique focus','Changes which gaps score highest','Moderate','None') },
            ]
          },
          {
            title: '⚔️ MoE — Blackhat Critic (Layer 2E)',
            subtitle: 'Cross-path chain exploitation analysis. Finds attacker pivot routes across multiple attack paths. Runs last in the MoE chain — the supreme critic that sees all prior findings.',
            fields: [
              { section:'blackhat', field:'enabled', label:'Enable Blackhat Critic',
                vtype:'select',
                options:[
                  {v:'true',  label:'true — Enabled (recommended)', rec:true},
                  {v:'false', label:'false — Disabled'},
                ],
                desc:'When disabled, the core three critics (Architect, Coverage Auditor, Exploit Analyst) still run — the assessment is not broken. Blackhat adds cross-path chain analysis: pivot routes and chain exploits that single-path critics cannot see. Adds ~30–60s per run.',
                effects: ef('Enables chain-risk detection','Disabling skips cross-path chain layer only — core assessment unaffected','High','Adds LLM call per run') },

              { section:'blackhat', field:'rubric_preset', label:'Scoring Rubric Preset',
                vtype:'select',
                options:[
                  {v:'balanced',          label:'balanced — Equal weight across dimensions (recommended)', rec:true},
                  {v:'stealth_focused',   label:'stealth_focused — Emphasise evasion techniques (stealth ×40)'},
                  {v:'chain_focused',     label:'chain_focused — Emphasise chaining feasibility (chain ×40)'},
                  {v:'mitigation_stress', label:'mitigation_stress — Emphasise mitigation coverage gaps (coverage ×40)'},
                ],
                desc:'Named rubric preset. Controls how the Blackhat score is weighted across: cross-path chain feasibility, least-resistance path, stealth potential, and mitigation chain coverage.',
                effects: ef('Shifts what type of risk the score reflects','Changes which findings score highest','High','None') },
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
        const providerLsKey = 'cfg_open_' + providerBodyId;
        const providerOpen = localStorage.getItem(providerLsKey) === 'true';
        const providerHtml = `
            <div class="card" style="margin-bottom:1rem;">
                <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1.1rem; cursor:pointer; user-select:none;"
                     onclick="(function(el){var b=document.getElementById('${providerBodyId}');var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.cfg-chev').textContent=open?'▶':'▼';localStorage.setItem('${providerLsKey}',String(!open));})(this)">
                    <div>
                        <span style="font-weight:700; font-size:0.95rem;">🔑 LLM Provider Chain</span>
                        <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">Read-only — configure in .env</span>
                    </div>
                    <span class="cfg-chev" style="font-size:0.7rem; color:var(--text-secondary);">${providerOpen ? '▼' : '▶'}</span>
                </div>
                <div id="${providerBodyId}" style="display:${providerOpen ? 'block' : 'none'}; border-top:1px solid var(--border-color); padding:0.9rem 1.1rem;">
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
            <div style="padding:0.65rem 1.1rem; border-bottom:1px solid var(--border-color);">
                <div style="display:flex; align-items:baseline; justify-content:space-between; gap:1.25rem; flex-wrap:wrap;">
                    <span style="font-weight:600; font-size:0.84rem; color:var(--text-color); min-width:140px; flex-shrink:0;">${label}</span>
                    <div style="flex:1; min-width:260px; max-width:560px;">${inputHtml}</div>
                </div>
                <div style="color:var(--text-secondary); font-size:0.78rem; line-height:1.5; margin-top:0.35rem;">${hint}</div>
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
                return `<div style="padding:0.5rem 1.1rem; border-bottom:1px solid var(--border-color)08;">
                    <div style="display:flex; align-items:baseline; justify-content:space-between; gap:1.25rem; flex-wrap:wrap;">
                        <span style="font-weight:500; font-size:0.82rem; color:var(--text-color); min-width:140px; flex-shrink:0;">${f.label}</span>
                        <div style="flex:1; min-width:240px; max-width:520px;">${inputHtml}</div>
                    </div>
                    <div style="font-size:0.76rem; color:var(--text-secondary); line-height:1.5; margin-top:0.35rem;">${f.desc}</div>
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
        const patternsLsKey = 'cfg_open_cfg-section-body-patterns';
        const patternsOpen = localStorage.getItem(patternsLsKey) === 'true';
        const patternsCard = `
            <div class="card" data-cfg-cat="patterns" style="margin-bottom:1rem;">
                <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1.1rem; cursor:pointer; user-select:none;"
                     onclick="(function(el){var b=document.getElementById('cfg-section-body-patterns');var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.cfg-chev').textContent=open?'▶':'▼';localStorage.setItem('${patternsLsKey}',String(!open));})(this)">
                    <div>
                        <span style="font-weight:700; font-size:0.95rem;">🧩 Threat Patterns</span>
                        <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">Threat patterns activate automatically when matching architecture components are detected — read only</span>
                    </div>
                    <span class="cfg-chev" style="font-size:0.7rem; color:var(--text-secondary);">${patternsOpen ? '▼' : '▶'}</span>
                </div>
                <div id="cfg-section-body-patterns" style="display:${patternsOpen ? 'block' : 'none'}; border-top:1px solid var(--border-color);">
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
            '🔍 Analysis Engine':                        'engine',
            '📊 Confidence Calculation':                 'confidence',
            '🧑‍🏫 MoE — Base Settings':                 'moe',
            '🏛️ MoE — Architect Critic (Layer 2A)':     'moe',
            '🧪 MoE — Tester Critic (Layer 2B)':        'moe',
            '🔴 MoE — Red Team Critic (Layer 2C)':      'moe',
            '🟣 MoE — Purple Team Critic (Layer 2D)':   'moe',
            '⚔️ MoE — Blackhat Critic (Layer 2E)':      'moe',
            '🔒 Residual Risk':                          'residual_risk',
            '🤖 LLM & System':                           'llm_system',
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
            <div style="padding:0.65rem 1.1rem; border-bottom:1px solid var(--border-color);">
                <div style="display:flex; align-items:baseline; justify-content:space-between; gap:1.25rem; flex-wrap:wrap;">
                    <div style="min-width:140px; flex-shrink:0;">
                        <span style="font-weight:600; font-size:0.84rem; color:var(--text-color);">${f.label}</span>
                        <span style="${cs} margin-left:0.6rem;">current: ${currentVal || '—'}</span>
                    </div>
                    <div style="flex:1; min-width:260px; max-width:560px;">${inputHtml}</div>
                </div>
                <div style="${cs} margin-top:0.4rem; line-height:1.55;">
                    ${f.desc}
                    ${f.effects || ''}
                </div>
            </div>`;
        }).join('');

        const lsKey = 'cfg_open_' + sectionId;
        const isOpen = localStorage.getItem(lsKey) === 'true';
        return `
        <div class="card" style="margin-bottom:1rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1.1rem; cursor:pointer; user-select:none;"
                 onclick="(function(el){var b=document.getElementById('${sectionId}');var open=b.style.display!=='none';b.style.display=open?'none':'block';el.querySelector('.cfg-chev').textContent=open?'▶':'▼';localStorage.setItem('${lsKey}',String(!open));})(this)">
                <div>
                    <span style="font-weight:700; font-size:0.95rem;">${sectionDef.title}</span>
                    <span style="margin-left:0.6rem; font-size:0.75rem; color:var(--text-tertiary);">${sectionDef.subtitle}</span>
                </div>
                <span class="cfg-chev" style="font-size:0.7rem; color:var(--text-secondary);">${isOpen ? '▼' : '▶'}</span>
            </div>
            <div id="${sectionId}" style="display:${isOpen ? 'block' : 'none'}; border-top:1px solid var(--border-color);">
                ${rows}
            </div>
        </div>`;
    }
}

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});
