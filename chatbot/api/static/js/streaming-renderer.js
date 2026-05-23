// Streaming Renderer for Large Files
// Provides line-by-line progressive rendering with loading feedback

class StreamingRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.isStreaming = false;
    }

    /**
     * Stream large text content line-by-line
     * @param {string} content - Full content to render
     * @param {string} language - Syntax highlighting language (optional)
     * @param {number} linesPerChunk - Lines to render per chunk (default: 50)
     * @param {number} chunkDelay - Delay between chunks in ms (default: 10)
     */
    async streamText(content, language = null, linesPerChunk = 50, chunkDelay = 10) {
        if (!this.container) return;

        this.isStreaming = true;
        const lines = content.split('\n');
        const totalLines = lines.length;

        // Show loading state
        this.showLoadingState(totalLines);

        // Create container for streamed content
        const contentDiv = document.createElement('div');
        contentDiv.id = 'streaming-content';
        contentDiv.style.opacity = '0';
        contentDiv.style.transition = 'opacity 0.3s';

        if (language) {
            contentDiv.innerHTML = '<pre style="margin: 0;"><code class="language-' + language + '" id="streaming-code"></code></pre>';
        } else {
            contentDiv.innerHTML = '<pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word;" id="streaming-code"></pre>';
        }

        this.container.appendChild(contentDiv);

        const codeBlock = document.getElementById('streaming-code');
        const progressElement = document.getElementById('streaming-progress');

        // Fade in container
        setTimeout(() => contentDiv.style.opacity = '1', 100);

        // Stream lines in chunks
        for (let i = 0; i < lines.length; i += linesPerChunk) {
            if (!this.isStreaming) break; // Allow cancellation

            const chunk = lines.slice(i, i + linesPerChunk);
            const chunkText = chunk.join('\n') + (i + linesPerChunk < lines.length ? '\n' : '');

            // Append chunk
            const textNode = document.createTextNode(chunkText);
            codeBlock.appendChild(textNode);

            // Update progress
            const currentLine = Math.min(i + linesPerChunk, totalLines);
            const percent = Math.round((currentLine / totalLines) * 100);

            if (progressElement) {
                progressElement.textContent = `Loading: ${currentLine.toLocaleString()} / ${totalLines.toLocaleString()} lines (${percent}%)`;
            }

            // Auto-scroll to bottom (smooth user experience)
            if (this.container.parentElement) {
                this.container.parentElement.scrollTop = this.container.parentElement.scrollHeight;
            }

            // Yield to browser for rendering
            await new Promise(resolve => setTimeout(resolve, chunkDelay));
        }

        // Apply syntax highlighting if applicable
        if (language && window.hljs) {
            const finalCodeBlock = document.getElementById('streaming-code');
            if (finalCodeBlock) {
                hljs.highlightElement(finalCodeBlock);
            }
        }

        // Remove loading indicator
        const loader = document.getElementById('streaming-loader');
        if (loader) {
            loader.style.opacity = '0';
            setTimeout(() => loader.remove(), 300);
        }

        this.isStreaming = false;
    }

    /**
     * Stream JSON with progressive rendering
     * @param {object} data - JSON object to render
     * @param {number} chunkDelay - Delay between chunks in ms
     */
    async streamJSON(data, chunkDelay = 10) {
        const jsonString = JSON.stringify(data, null, 2);
        await this.streamText(jsonString, 'json', 100, chunkDelay);
    }

    /**
     * Stream Markdown with progressive rendering
     * @param {string} markdown - Markdown content
     * @param {boolean} renderAsHTML - Render as HTML or plain text
     */
    async streamMarkdown(markdown, renderAsHTML = true) {
        if (renderAsHTML && window.marked) {
            // For markdown, render all at once (HTML parsing is complex)
            this.showLoadingState(1);

            await new Promise(resolve => setTimeout(resolve, 100));

            const html = marked.parse(markdown);
            this.container.innerHTML = html;

            const loader = document.getElementById('streaming-loader');
            if (loader) loader.remove();
        } else {
            // Stream as plain text
            await this.streamText(markdown, 'markdown', 50, 15);
        }
    }

    /**
     * Show loading state with spinner and progress
     */
    showLoadingState(totalLines) {
        if (!this.container) return;

        const loader = document.createElement('div');
        loader.id = 'streaming-loader';
        loader.style.cssText = `
            padding: 2rem;
            text-align: center;
            transition: opacity 0.3s;
        `;

        loader.innerHTML = `
            <div style="display: inline-block; position: relative;">
                <div class="spinner" style="
                    width: 40px;
                    height: 40px;
                    border: 4px solid var(--border-color);
                    border-top-color: var(--primary-color);
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 1rem;
                "></div>
                <style>
                    @keyframes spin {
                        to { transform: rotate(360deg); }
                    }
                </style>
            </div>
            <div id="streaming-progress" style="
                color: var(--text-secondary);
                font-size: 0.875rem;
                margin-top: 0.5rem;
            ">
                Loading content... (${totalLines.toLocaleString()} lines)
            </div>
        `;

        this.container.innerHTML = '';
        this.container.appendChild(loader);
    }

    /**
     * Cancel ongoing stream
     */
    cancel() {
        this.isStreaming = false;
    }

    /**
     * Clear container
     */
    clear() {
        if (this.container) {
            this.container.innerHTML = '<p class="placeholder">Select an item to view contents</p>';
        }
    }
}

// Export for global access
window.StreamingRenderer = StreamingRenderer;
