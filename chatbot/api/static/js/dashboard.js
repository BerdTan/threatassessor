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
        try {
            const moeResp = await fetch(`/api/v1/reports/${archName}/files/07_moe_orchestrator.json`);
            if (moeResp.ok) {
                const moe = await moeResp.json();
                validatedConf = (moe.confidence?.final ?? null);
                moeInterp = moe.confidence?.interpretation ?? '';
            }
        } catch (_) {}

        // Top 3 immediate actions: critical first, then high
        const priority = { critical: 0, high: 1, medium: 2, low: 3 };
        const top3 = [...controlRecs]
            .filter(c => c.attack_paths && c.attack_paths.length > 0)
            .sort((a, b) => (priority[a.priority?.toLowerCase()] ?? 9) - (priority[b.priority?.toLowerCase()] ?? 9))
            .slice(0, 3);

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

        // Honest residual note
        const residualNote = `
            <div style="margin-top:0.75rem; padding:0.625rem 0.875rem; background:var(--warning-color)11; border:1px solid var(--warning-color)44; border-radius:6px; font-size:0.75rem; color:var(--text-secondary); line-height:1.6;">
                ⚠️ <strong style="color:var(--text-color);">Controls reduce risk — they do not eliminate it.</strong>
                Residual exposure persists due to implementation gaps, misconfigurations, human error, and technical bypasses.
                The goal is risk-informed management, not false certainty. Review quarterly.
            </div>`;

        // Improvement tier cards — active if MoE run, locked otherwise
        const hasMoe = validatedConf !== null;
        const tiers = [
            { icon: '⚡', label: 'Quick Wins',     timeline: '1–2 weeks',   cost: '$10K–$50K',    delta: '+10',  file: '08a_quick_wins.mmd' },
            { icon: '⭐', label: 'Recommended',    timeline: '1–3 months',  cost: '$75K–$200K',   delta: '+20',  file: '08b_recommended_target.mmd', recommended: true },
            { icon: '🔒', label: 'Maximum',        timeline: '6–12 months', cost: '$300K–$600K',  delta: 'Full', file: '08c_maximum_security.mmd' },
        ];
        const tierCards = tiers.map(t => {
            const border = t.recommended ? '2px solid var(--secondary-color)' : '1px solid var(--border-color)';
            const bg     = t.recommended ? 'var(--card-bg)' : 'var(--card-bg)';
            return `
            <div style="flex:1; min-width:160px; background:${bg}; border:${border}; border-radius:10px; padding:1rem; position:relative;">
                ${t.recommended ? `<div style="position:absolute; top:-10px; left:50%; transform:translateX(-50%); background:var(--secondary-color); color:#000; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:10px;">RECOMMENDED</div>` : ''}
                <div style="font-size:1.5rem; margin-bottom:0.5rem;">${t.icon}</div>
                <div style="font-weight:700; color:var(--text-color); margin-bottom:0.25rem;">${t.label}</div>
                <div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:0.25rem;">${t.timeline}</div>
                <div style="font-size:0.8125rem; color:var(--text-secondary); margin-bottom:0.75rem;">${t.cost}</div>
                ${hasMoe
                    ? `<button class="btn-secondary tier-diagram-btn" data-file="${t.file}" style="width:100%; padding:0.375rem; font-size:0.8125rem; cursor:pointer;">View Diagram →</button>`
                    : `<div style="font-size:0.75rem; color:var(--text-tertiary); font-style:italic;">Run Expert Review to unlock roadmap</div>`
                }
            </div>`;
        }).join('');

        container.innerHTML = `
        <!-- Confidence + Scores Row -->
        <div style="display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.25rem;">
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Risk Score</div>
                <div style="font-size:2rem; font-weight:700; color:${riskColor};">${risk}<span style="font-size:1rem; color:var(--text-secondary);">/100</span></div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">lower is better</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Defensibility</div>
                <div style="font-size:2rem; font-weight:700; color:${defColor};">${def}<span style="font-size:1rem; color:var(--text-secondary);">/100</span></div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">higher is better</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Threat Paths</div>
                <div style="font-size:2rem; font-weight:700; color:var(--text-color);">${attackPaths.length}</div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">${controlsPresent.length} controls active</div>
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Foundation Score</div>
                <div style="font-size:2rem; font-weight:700; color:var(--secondary-color);">${foundationConf.toFixed(1)}<span style="font-size:1rem;">%</span></div>
                ${validatedConf !== null
                    ? `<div style="font-size:0.8125rem; color:var(--primary-color); font-weight:600;">Validated: ${validatedConf.toFixed(1)}%</div>`
                    : `<div style="font-size:0.75rem; color:var(--text-tertiary);">Expert Review pending</div>`}
            </div>
            <div style="flex:1; min-width:140px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1rem; text-align:center;">
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:0.25rem; text-transform:uppercase; letter-spacing:.05em;">Risk Reduction</div>
                <div style="font-size:2rem; font-weight:700; color:var(--secondary-color);">${riskReductionPct}<span style="font-size:1rem;">%</span></div>
                <div style="font-size:0.75rem; color:var(--text-tertiary);">\$${implCost}K · ${roi}x ROI</div>
            </div>
        </div>

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
            <!-- Top 3 Actions -->
            <div style="flex:1; min-width:240px; background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1.25rem;">
                <h3 style="margin:0 0 0.375rem; font-size:0.9375rem; color:var(--text-color);">⚡ Start Here</h3>
                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:1rem;">Highest-coverage controls across all threat categories</div>
                ${top3.length > 0 ? top3.map((c, i) => {
                    const priColor = c.priority === 'critical' ? 'var(--danger-color)' : c.priority === 'high' ? 'var(--warning-color)' : 'var(--primary-color)';
                    return `
                <div style="padding:0.75rem 0; border-bottom:1px solid var(--border-color);">
                    <div style="display:flex; align-items:flex-start; gap:0.5rem;">
                        <div style="width:22px; height:22px; border-radius:50%; background:${priColor}; color:#fff; font-size:0.75rem; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0;">${i+1}</div>
                        <div style="flex:1;">
                            <div style="font-weight:600; color:var(--text-color); font-size:0.875rem; text-transform:uppercase;">${c.control}</div>
                            <div style="font-size:0.75rem; color:var(--text-secondary); margin-top:0.2rem;">
                                Covers ${c.attack_paths?.length || 0} threat path${(c.attack_paths?.length || 0) !== 1 ? 's' : ''}
                                <span style="margin-left:0.5rem; padding:0.1rem 0.35rem; background:${priColor}22; color:${priColor}; border-radius:3px; font-size:0.7rem; font-weight:700;">${c.priority}</span>
                            </div>
                        </div>
                    </div>
                </div>`}).join('') : '<div style="color:var(--text-tertiary); font-size:0.875rem;">No critical actions identified</div>'}
                ${top3.length > 0 ? `
                <div style="margin-top:0.75rem; font-size:0.75rem; color:var(--text-tertiary); font-style:italic;">
                    These are Quick Win candidates. The full action plan is in the
                    <strong style="color:var(--primary-color); cursor:pointer;" onclick="window.dashboard?.switchTab('controls')">Mitigations tab</strong>.
                </div>` : ''}
            </div>
        </div>

        <!-- Improvement Tiers -->
        <div style="background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:1.25rem; margin-bottom:0.5rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.375rem; flex-wrap:wrap; gap:0.5rem;">
                <h3 style="margin:0; font-size:0.9375rem; color:var(--text-color);">Investment Tiers — What Each Level Achieves</h3>
                ${!hasMoe ? `<span style="font-size:0.8125rem; color:var(--text-tertiary);">Run Expert Review to unlock diagrams</span>` : `<span style="font-size:0.8125rem; color:var(--secondary-color);">✅ Expert Review complete</span>`}
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
                <h4 style="margin-bottom: 0.75rem; font-size: 0.9375rem; color: var(--primary-color);">🔬 Techniques & Mitigations</h4>
                ${techs.length > 0 ? `
                    ${techs.map(tech => {
                        const techName = techniqueNames[tech] || tech;
                        const mits = sortedMits(techMitMappings[tech] || []);
                        return `
                        <div style="margin-bottom: 0.75rem; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden;">
                            <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--nav-hover-bg); border-left: 3px solid var(--primary-color);">
                                <div>
                                    <code style="font-weight: 700; color: var(--primary-color); font-size: 0.875rem;">${tech}</code>
                                    ${techName !== tech ? `<span style="margin-left: 0.5rem; color: var(--text-color); font-size: 0.875rem; font-weight: 600;">· ${techName}</span>` : ''}
                                </div>
                                <a href="https://attack.mitre.org/techniques/${tech}/" target="_blank" class="btn-icon" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; text-decoration: none; flex-shrink: 0;">🔗</a>
                            </div>
                            ${mits.length > 0 ? `
                                <div style="background: var(--card-bg); border-top: 1px solid var(--border-color);">
                                    <div style="padding: 0.375rem 0.75rem; font-size: 0.6875rem; color: var(--text-tertiary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border-color);">
                                        ${mits.length} Mitigation${mits.length !== 1 ? 's' : ''} — broadest coverage first
                                    </div>
                                    ${mits.map((m, idx) => {
                                        const cov = mitCoverage[m] || 1;
                                        const covLabel = techs.length > 1 ? `covers ${cov}/${techs.length} technique${cov !== 1 ? 's' : ''}` : '';
                                        return `
                                        <a href="https://attack.mitre.org/mitigations/${m}/" target="_blank"
                                           style="display:flex; align-items:center; gap:0.5rem; padding:0.5rem 0.75rem; border-bottom:${idx < mits.length - 1 ? '1px solid var(--border-color)' : 'none'}; text-decoration:none; transition:background 0.15s;"
                                           onmouseover="this.style.background='var(--nav-hover-bg)'" onmouseout="this.style.background='transparent'">
                                            <code style="color:var(--secondary-color); font-weight:700; font-size:0.8125rem; flex-shrink:0;">${m}</code>
                                            <span style="color:var(--text-secondary); font-size:0.8125rem; flex:1;">${mitigationNames[m] || ''}</span>
                                            ${covLabel ? `<span style="font-size:0.7rem; color:var(--text-tertiary); flex-shrink:0; white-space:nowrap;">${covLabel}</span>` : ''}
                                            <span style="font-size:0.7rem; color:var(--text-tertiary); flex-shrink:0;">↗</span>
                                        </a>
                                    `}).join('')}
                                </div>
                            ` : `<div style="padding:0.5rem 0.75rem; background:var(--card-bg); border-top:1px solid var(--border-color); font-size:0.75rem; color:var(--text-tertiary); font-style:italic;">No mitigations mapped for this technique</div>`}
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
        // Support both naming conventions: "rp-diagram" (no separate container) and "before"/"after"/"full"
        const container = document.getElementById(`${prefix}-container`) || document.getElementById(`${prefix}`);
        const getDiagram = () => container?.querySelector('svg');

        const zoomInBtn = document.getElementById(`${prefix}-zoom-in`);
        const zoomOutBtn = document.getElementById(`${prefix}-zoom-out`);
        const zoomResetBtn = document.getElementById(`${prefix}-zoom-reset`);
        const fitWidthBtn = document.getElementById(`${prefix}-fit-width`);
        const fitHeightBtn = document.getElementById(`${prefix}-fit-height`);

        if (!container) return;

        let scale = 1;

        // Auto-fit to container width on first load
        setTimeout(() => {
            const svg = getDiagram();
            if (!svg) return;

            const bbox = svg.getBBox();
            const currentWidth = parseFloat(svg.getAttribute('width')) || bbox.width || 800;
            const currentHeight = parseFloat(svg.getAttribute('height')) || bbox.height || 600;

            this[`${prefix}OriginalWidth`] = currentWidth;
            this[`${prefix}OriginalHeight`] = currentHeight;

            // Fit to container width by default (with 32px padding)
            const containerWidth = container.clientWidth - 32;
            if (currentWidth > containerWidth) {
                scale = containerWidth / currentWidth;
                svg.setAttribute('width', currentWidth * scale);
                svg.setAttribute('height', currentHeight * scale);
                svg.style.maxWidth = 'none';
            } else {
                // Already fits — ensure no stale max-width constraint
                svg.style.maxWidth = 'none';
            }
        }, 150);

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => {
                scale = Math.min(scale + 0.2, 4);
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
            });
        }

        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => {
                scale = Math.max(scale - 0.2, 0.1);
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    svg.setAttribute('width', this[`${prefix}OriginalWidth`] * scale);
                    svg.setAttribute('height', this[`${prefix}OriginalHeight`] * scale);
                }
            });
        }

        if (zoomResetBtn) {
            zoomResetBtn.addEventListener('click', () => {
                const svg = getDiagram();
                if (svg && this[`${prefix}OriginalWidth`]) {
                    // Reset to fit-width
                    const containerWidth = container.clientWidth - 32;
                    scale = Math.min(1, containerWidth / this[`${prefix}OriginalWidth`]);
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

        // Catalogue definitions — maps filename prefix/exact to metadata
        const REPORT_CATALOGUE = {
            '01_executive_summary.md':    { id: 'executive',    title: 'Executive Summary',    icon: '📊', desc: 'High-level threat overview for leadership and CISOs', audience: 'stakeholder', type: 'markdown' },
            '03_action_plan.md':          { id: 'action',       title: 'Action Plan',           icon: '✅', desc: 'Prioritised recommendations with implementation steps', audience: 'stakeholder', type: 'markdown' },
            '08_improvement_summary.md':  { id: 'improvement',  title: 'Improvement Summary',   icon: '🗺️', desc: 'Roadmap across Quick Win, Recommended, and Maximum tiers', audience: 'stakeholder', type: 'markdown' },
            'before.mmd':                 { id: 'before',       title: 'Current Architecture',  icon: '⚠️', desc: 'Architecture before hardening controls are applied', audience: 'stakeholder', type: 'mermaid', color: 'var(--danger-color)' },
            'after.mmd':                  { id: 'after',        title: 'Hardened Architecture', icon: '🛡️', desc: 'Architecture with all recommended controls applied', audience: 'stakeholder', type: 'mermaid', color: 'var(--secondary-color)' },
            '02_technical_report.md':     { id: 'technical',    title: 'Technical Report',      icon: '🔧', desc: 'Full MITRE ATT&CK technique mappings and control analysis', audience: 'technical', type: 'markdown' },
            '04_architect_critique.json': { id: 'arch-critique', title: 'Architecture Review',  icon: '🏛️', desc: 'Expert assessment of threat model completeness', audience: 'expert', type: 'json' },
            '05_tester_critique.json':    { id: 'tester-critique', title: 'Coverage Audit',     icon: '🧪', desc: 'MITRE technique coverage and mapping accuracy review', audience: 'expert', type: 'json' },
            '06_red_team_critique.json':  { id: 'red-critique', title: 'Exploit Analysis',      icon: '🔴', desc: 'Red team assessment of control weaknesses and bypasses', audience: 'expert', type: 'json' },
            '08a_quick_wins.mmd':         { id: 'tier-a',       title: 'Quick Wins Diagram',    icon: '⚡', desc: 'Architecture diagram with Quick Win controls highlighted', audience: 'expert', type: 'mermaid', color: 'var(--secondary-color)' },
            '08b_recommended_target.mmd': { id: 'tier-b',       title: 'Recommended Diagram',   icon: '📈', desc: 'Architecture diagram with Recommended controls highlighted', audience: 'expert', type: 'mermaid', color: 'var(--primary-color)' },
            '08c_maximum_security.mmd':   { id: 'tier-c',       title: 'Maximum Coverage',      icon: '🔒', desc: 'Architecture diagram with Maximum controls highlighted', audience: 'expert', type: 'mermaid', color: 'var(--warning-color)' },
        };

        // Suppressed files (raw data, noise, or duplicates)
        const SUPPRESSED = new Set(['ground_truth.json', '07_moe_orchestrator.json', '07_orchestrator_report.json', 'README.md']);

        // Build report objects from files returned by API
        const byAudience = { stakeholder: [], technical: [], expert: [] };
        const fileMap = {};
        allFiles.forEach(f => fileMap[f.filename] = f);

        Object.entries(REPORT_CATALOGUE).forEach(([filename, meta]) => {
            if (fileMap[filename]) {
                byAudience[meta.audience].push({ ...meta, filename, url: fileMap[filename].url, size: fileMap[filename].size });
            }
        });

        // Any unrecognised files not suppressed go to technical as raw items
        allFiles.forEach(f => {
            if (!REPORT_CATALOGUE[f.filename] && !SUPPRESSED.has(f.filename)) {
                byAudience.technical.push({
                    id: f.filename,
                    title: f.filename,
                    icon: f.type === 'json' ? '📊' : f.type === 'mermaid' ? '🏗️' : '📄',
                    desc: '',
                    audience: 'technical',
                    type: f.type,
                    filename: f.filename,
                    url: f.url,
                    size: f.size
                });
            }
        });

        const hasExpert = byAudience.expert.length > 0;

        // Stakeholder download pack filenames
        const stakeholderFiles = byAudience.stakeholder.map(r => r.filename);
        const allPackFiles = [...stakeholderFiles, ...byAudience.technical.map(r => r.filename), ...byAudience.expert.map(r => r.filename)];

        listContainer.innerHTML = `
            <!-- Download packs -->
            <div style="display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; align-items: center;">
                <span style="font-size: 0.8125rem; color: var(--text-secondary); font-weight: 600;">Download:</span>
                <a id="dl-stakeholder-pack" href="/api/v1/reports/${archName}/download?pack=stakeholder" download="${archName}_stakeholder.zip"
                   class="btn-primary" style="padding: 0.5rem 1rem; font-size: 0.8125rem; font-weight: 600; text-decoration: none;">
                    ⬇ Stakeholder Pack
                </a>
                <a id="dl-full-pack" href="/api/v1/reports/${archName}/download?pack=full" download="${archName}_full.zip"
                   style="padding: 0.5rem 1rem; font-size: 0.8125rem; font-weight: 600; background: transparent; color: var(--text-color); border: 1.5px solid var(--border-color); border-radius: 6px; text-decoration: none;">
                    ⬇ Full Pack
                </a>
                <span style="font-size: 0.75rem; color: var(--text-tertiary); margin-left: auto;">
                    Click any card to preview · ⬇ to download file
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

            <!-- Section: Expert Review Findings (only when MoE data present) -->
            ${hasExpert ? `
            <div class="report-section" style="margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem;">
                    <span style="font-size: 1.125rem;">🧑‍🏫</span>
                    <h4 style="margin: 0; color: var(--text-color); font-size: 0.9375rem;">Expert Review Findings</h4>
                    <span style="font-size: 0.75rem; color: var(--secondary-color); padding: 0.125rem 0.5rem; background: var(--secondary-color)18; border-radius: 10px; border: 1px solid var(--secondary-color)44;">Validated</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.625rem;">
                    ${byAudience.expert.map(r => this._reportCard(r, archName)).join('')}
                </div>
            </div>` : ''}
        `;

        // Wire card clicks → right pane preview
        const allReports = [...byAudience.stakeholder, ...byAudience.technical, ...byAudience.expert];
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
                        <p style="color: var(--text-secondary); max-width: 440px; margin: 0 auto 1.5rem;">
                            The expert panel (Architecture Review, Coverage Audit, Exploit Analysis) has not reviewed this assessment yet.
                            Running it adjusts confidence from the Foundation Score and unlocks the Improvement Roadmap.
                        </p>
                        <button id="run-expert-review-btn" onclick="window.dashboard.runExpertReview('${archName}')"
                            style="background: var(--primary-color); color: #fff; border: none; border-radius: 8px;
                                   padding: 0.75rem 1.75rem; font-size: 0.9375rem; font-weight: 600;
                                   cursor: pointer; margin-bottom: 1.5rem;">
                            Run Expert Review (~90 s)
                        </button>
                        <div id="expert-review-progress" style="display:none; max-width: 480px; margin: 0 auto; text-align: left;">
                            <div style="background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border-color); padding: 1rem;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                                    <span id="erp-stage-label" style="font-size:0.875rem; color: var(--text-secondary);">Starting...</span>
                                    <span id="erp-pct" style="font-size:0.875rem; font-weight:600; color:var(--primary-color);">0%</span>
                                </div>
                                <div style="background: var(--nav-hover-bg); border-radius: 4px; height: 6px; overflow: hidden;">
                                    <div id="erp-bar" style="height:100%; width:0%; background: var(--primary-color); transition: width 0.4s ease;"></div>
                                </div>
                                <div id="erp-message" style="font-size:0.8125rem; color:var(--text-tertiary); margin-top:0.5rem; min-height:1.2em;"></div>
                            </div>
                        </div>
                        <div id="expert-review-error" style="display:none; color:var(--danger-color); font-size:0.875rem; margin-top:1rem; max-width:440px; margin-left:auto; margin-right:auto;"></div>
                    </div>`;
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
                blindspotsHtml = '<div style="background: var(--card-bg); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border-color);">'
                    + '<h3 style="margin: 0 0 0.25rem; color: var(--text-color); font-size: 1rem;">🔍 Blindspots</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0 0 1rem;">Gaps all three critics structurally could not see — highest priority for human review.</p>'
                    + cards + '</div>';
            }

            // Build contradictions HTML
            let contradictionsHtml = '';
            if (contradictions.length > 0) {
                let cards = '';
                for (const c of contradictions) {
                    cards += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--warning-color);">'
                        + '<div style="font-size: 0.875rem; font-weight:600; color: var(--text-color); margin-bottom:0.5rem;">' + (c.topic || '') + '</div>'
                        + '<div style="font-size:0.8125rem; color:var(--text-secondary);">🏛️ Architect/Tester: ' + (c.architect_view || '') + '</div>'
                        + '<div style="font-size:0.8125rem; color:var(--text-secondary); margin-top:0.2rem;">🎯 Red Team: ' + (c.tester_or_redteam_view || '') + '</div>'
                        + '<div style="font-size:0.8125rem; color:var(--warning-color); margin-top:0.35rem; font-style:italic;">' + (c.resolution || 'UNSURE — human review needed') + '</div>'
                        + '</div>';
                }
                contradictionsHtml = '<div style="background: var(--card-bg); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border-color);">'
                    + '<h3 style="margin: 0 0 0.25rem; color: var(--text-color); font-size: 1rem;">⚠️ Expert Disagreements</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0 0 1rem;">Where critics contradict each other — human judgment required, not resolved by the system.</p>'
                    + cards + '</div>';
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
                        + '<div><span style="color:var(--text-tertiary);">Risk:</span> ' + (t.risk_reduction || '—') + '</div>'
                        + '</div>'
                        + itemList
                        + residualBlock
                        + '</div>';
                }
                tiersHtml = '<div style="background: var(--card-bg); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border-color);">'
                    + '<h3 style="margin: 0 0 0.25rem; color: var(--text-color); font-size: 1rem;">📊 Improvement Tiers</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0 0 1rem;">Cost and effort from Red Team exploit roadmap — not estimated where data is absent.</p>'
                    + tierCards
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

            const finalConf = (confidence.final || 0).toFixed(1);
            const baseConf  = (confidence.base  || 99.5).toFixed(1);
            const interp    = confidence.interpretation || '';

            // Build confidence waterfall nodes
            let waterfallNodes = '';
            for (const e of expertDefs) {
                const v = expertValidations[e.key];
                if (!v) continue;
                const adj = ((v.confidence_adjustment || 0) * 100).toFixed(1);
                const sign = parseFloat(adj) >= 0 ? '+' : '';
                waterfallNodes += '<div style="color: var(--text-tertiary); font-size: 1.25rem;">→</div>'
                    + '<div style="text-align: center; min-width: 80px;">'
                    + '<div style="font-size: 1rem; font-weight: 600; color: var(--warning-color);">' + sign + adj + '%</div>'
                    + '<div style="font-size: 0.75rem; color: var(--text-secondary);">' + e.label + '</div>'
                    + '</div>';
            }

            // Build expert panel cards
            let expertPanels = '';
            for (const e of expertDefs) {
                const v = expertValidations[e.key];
                if (!v) continue;
                const adj = ((v.confidence_adjustment || 0) * 100).toFixed(1);
                const sign = parseFloat(adj) >= 0 ? '+' : '';
                const status = v.validation_status || 'UNKNOWN';
                const color = statusColor[status] || 'var(--text-secondary)';
                const gaps = v.gaps || [];
                let gapItems = '';
                for (const g of gaps) {
                    const borderCol = (g.severity === 'HIGH' || g.severity === 'CRITICAL') ? 'var(--danger-color)' : 'var(--warning-color)';
                    const sevCol = (g.severity === 'HIGH' || g.severity === 'CRITICAL') ? 'var(--danger-color)' : 'var(--warning-color)';
                    gapItems += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid ' + borderCol + ';">'
                        + '<div style="font-size: 0.8125rem; font-weight: 600; color: var(--text-color); margin-bottom: 0.25rem;">' + (g.category ? g.category.replace(/_/g, ' ').toUpperCase() : '') + ' · <span style="color: ' + sevCol + ';">' + (g.severity || '') + '</span></div>'
                        + '<div style="font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.5rem;">' + (g.description || '') + '</div>'
                        + (g.recommendation ? '<div style="font-size: 0.8125rem; color: var(--secondary-color);">→ ' + g.recommendation + '</div>' : '')
                        + '</div>';
                }
                expertPanels += '<div style="background: var(--card-bg); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden;">'
                    + '<div style="padding: 1rem 1.25rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color);">'
                    + '<div style="display: flex; align-items: center; gap: 0.75rem;">'
                    + '<span style="font-size: 1.5rem;">' + e.icon + '</span>'
                    + '<div><div style="font-weight: 700; color: var(--text-color);">' + e.label + '</div>'
                    + '<div style="font-size: 0.8125rem; color: var(--text-secondary);">' + e.role + '</div></div>'
                    + '</div>'
                    + '<div style="text-align: right;">'
                    + '<div style="font-size: 1.125rem; font-weight: 700; color: var(--warning-color);">' + sign + adj + '%</div>'
                    + '<div style="font-size: 0.75rem; font-weight: 600; color: ' + color + ';">' + status.replace('_', ' ') + '</div>'
                    + '</div></div>'
                    + (gaps.length > 0 ? '<div style="padding: 1rem 1.25rem;"><div style="font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.75rem;">' + gaps.length + ' finding' + (gaps.length > 1 ? 's' : '') + '</div>' + gapItems + '</div>' : '')
                    + '</div>';
            }

            // Build consensus section
            let consensusHtml = '';
            if (consensusCritical.length + consensusHigh.length + consensusReview.length > 0) {
                let inner = '';
                if (consensusCritical.length > 0) {
                    inner += '<div style="font-size:0.8125rem; font-weight:600; color:var(--danger-color); text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.5rem;">Critical · KNOWN</div>';
                    for (const r of consensusCritical) {
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--danger-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-color);">' + (r.description || r.recommendation || '') + '</div>'
                            + (r.evidence ? '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.25rem;">Evidence: ' + r.evidence + '</div>' : '')
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary);">Source: ' + r.source + '</div>' : '')
                            + '</div>';
                    }
                }
                if (consensusHigh.length > 0) {
                    inner += '<div style="font-size:0.8125rem; font-weight:600; color:var(--warning-color); text-transform:uppercase; letter-spacing:0.04em; margin: 0.75rem 0 0.5rem;">High · UNSURE</div>';
                    for (const r of consensusHigh) {
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--warning-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-color);">' + (r.description || r.recommendation || '') + '</div>'
                            + (r.evidence ? '<div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:0.25rem;">Evidence: ' + r.evidence + '</div>' : '')
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary);">Source: ' + r.source + '</div>' : '')
                            + '</div>';
                    }
                }
                if (consensusReview.length > 0) {
                    inner += '<div style="font-size:0.8125rem; font-weight:600; color:var(--text-tertiary); text-transform:uppercase; letter-spacing:0.04em; margin: 0.75rem 0 0.5rem;">For Review · UNSURE (single critic)</div>';
                    for (const r of consensusReview) {
                        inner += '<div style="padding: 0.75rem; background: var(--nav-hover-bg); border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid var(--border-color);">'
                            + '<div style="font-size: 0.875rem; color: var(--text-secondary);">' + (r.description || r.recommendation || '') + '</div>'
                            + (r.source ? '<div style="font-size:0.75rem; color:var(--text-tertiary);">Raised by: ' + r.source + '</div>' : '')
                            + '</div>';
                    }
                }
                consensusHtml = '<div style="background: var(--card-bg); border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; border: 1px solid var(--border-color);">'
                    + '<h3 style="margin: 0 0 0.25rem; color: var(--text-color); font-size: 1rem;">Cross-Expert Findings</h3>'
                    + '<p style="font-size: 0.875rem; color: var(--text-secondary); margin: 0 0 1rem;">KNOWN = ≥2 critics independently agree. UNSURE = single critic, needs human verification.</p>'
                    + inner + '</div>';
            }

            container.innerHTML = ''
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
                + '<div style="display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.5rem;">' + expertPanels + '</div>'
                + consensusHtml
                + blindspotsHtml
                + contradictionsHtml
                + tiersHtml
                + synthFooterHtml;
        } catch (err) {
            container.innerHTML = `<p class="placeholder">Error loading expert review: ${err.message}</p>`;
        }
    }

    runExpertReview(archName) {
        const btn = document.getElementById('run-expert-review-btn');
        const progressBox = document.getElementById('expert-review-progress');
        const errorBox = document.getElementById('expert-review-error');
        const bar = document.getElementById('erp-bar');
        const pct = document.getElementById('erp-pct');
        const stageLabel = document.getElementById('erp-stage-label');
        const message = document.getElementById('erp-message');

        if (!btn || !progressBox) return;

        btn.disabled = true;
        btn.textContent = 'Running...';
        btn.style.opacity = '0.6';
        progressBox.style.display = 'block';
        if (errorBox) errorBox.style.display = 'none';

        const apiKey = localStorage.getItem('tm_api_key') || '';
        const url = `/api/v1/expert-review?architecture_name=${encodeURIComponent(archName)}`;

        // SSE over fetch (EventSource doesn't support custom headers)
        fetch(url, { headers: { 'TM-API-KEY': apiKey } })
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
                                const p = data.progress || 0;
                                bar.style.width = p + '%';
                                pct.textContent = p + '%';
                                const stageMap = { architect: '🏛️ Architect', tester: '🔬 Tester', red_team: '🎯 Red Team', synthesis: '⚙️ Synthesis', complete: '✅ Done' };
                                stageLabel.textContent = stageMap[data.stage] || data.stage;
                                message.textContent = data.message || '';
                            } else if (evtType === 'complete') {
                                // Reload the tab with fresh MoE data
                                setTimeout(() => this.loadExpertReviewTab(), 600);
                                // Also refresh Overview to show updated confidence
                                setTimeout(() => {
                                    if (this.currentTab === 'overview') this.loadOverviewTab();
                                }, 1200);
                            } else if (evtType === 'error') {
                                btn.disabled = false;
                                btn.textContent = 'Retry Expert Review';
                                btn.style.opacity = '1';
                                if (errorBox) {
                                    errorBox.textContent = data.detail || data.message || 'Expert Review failed';
                                    errorBox.style.display = 'block';
                                }
                            }
                        } catch (_) {}
                    }
                    return pump();
                });
                return pump();
            })
            .catch(err => {
                btn.disabled = false;
                btn.textContent = 'Retry Expert Review';
                btn.style.opacity = '1';
                if (errorBox) {
                    errorBox.textContent = `Connection error: ${err.message}`;
                    errorBox.style.display = 'block';
                }
            });
    }

    loadRawDataTab() {
        const listContainer = document.getElementById('artifacts-list');

        if (!this.analysisData) {
            listContainer.innerHTML = '<p class="placeholder">No analysis data available</p>';
            return;
        }

        const analysis = this.analysisData.analysis || {};

        // Build artifact list from in-memory analysis data (ground_truth.json is in Reports tab)
        const artifacts = [
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
