// Artifact Viewer for ThreatAssessor Dashboard

class ArtifactViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
    }

    showJSON(data) {
        if (!this.container) return;

        const jsonStr = JSON.stringify(data, null, 2);
        this.container.innerHTML = `<pre><code class="language-json">${this.escapeHtml(jsonStr)}</code></pre>`;

        // Apply syntax highlighting if available
        if (window.hljs) {
            const codeBlock = this.container.querySelector('code');
            if (codeBlock) {
                hljs.highlightElement(codeBlock);
            }
        }
    }

    showMarkdown(content) {
        if (!this.container) return;

        // Option 1: Render as HTML
        if (window.marked) {
            this.container.innerHTML = marked.parse(content);
        } else {
            // Option 2: Show raw with syntax highlighting
            this.container.innerHTML = `<pre><code class="language-markdown">${this.escapeHtml(content)}</code></pre>`;
            if (window.hljs) {
                hljs.highlightElement(this.container.querySelector('code'));
            }
        }
    }

    showText(content) {
        if (!this.container) return;
        this.container.innerHTML = `<pre>${this.escapeHtml(content)}</pre>`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    clear() {
        if (this.container) {
            this.container.innerHTML = '<p class="placeholder">Select an artifact to view contents</p>';
        }
    }
}

// Export for global access
window.ArtifactViewer = ArtifactViewer;
