// Resizable Right Pane
// Allows users to drag and resize the detail pane

class ResizablePane {
    constructor(paneId, handleId) {
        this.pane = document.getElementById(paneId);
        this.handle = null;
        this.isResizing = false;
        this.startX = 0;
        this.startWidth = 0;
        this.minWidth = 300;
        this.maxWidth = 800;

        this.init();
    }

    init() {
        // Create resize handle
        this.handle = document.createElement('div');
        this.handle.id = 'resize-handle';
        this.handle.style.cssText = `
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 6px;
            cursor: ew-resize;
            background: transparent;
            transition: background 0.2s;
            z-index: 100;
        `;

        // Add visual indicator on hover
        this.handle.addEventListener('mouseenter', () => {
            this.handle.style.background = 'var(--primary-color)';
        });

        this.handle.addEventListener('mouseleave', () => {
            if (!this.isResizing) {
                this.handle.style.background = 'transparent';
            }
        });

        // Attach handle to pane
        if (this.pane) {
            this.pane.style.position = 'relative';
            this.pane.appendChild(this.handle);

            // Bind events
            this.handle.addEventListener('mousedown', this.startResize.bind(this));
            document.addEventListener('mousemove', this.resize.bind(this));
            document.addEventListener('mouseup', this.stopResize.bind(this));
        }

        // Load saved width from localStorage
        const savedWidth = localStorage.getItem('rightPaneWidth');
        if (savedWidth) {
            this.setWidth(parseInt(savedWidth));
        }
    }

    startResize(e) {
        this.isResizing = true;
        this.startX = e.clientX;
        this.startWidth = this.pane.offsetWidth;
        this.handle.style.background = 'var(--primary-color)';
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    }

    resize(e) {
        if (!this.isResizing) return;

        const deltaX = this.startX - e.clientX; // Note: reversed because we're resizing from left edge
        const newWidth = Math.min(
            Math.max(this.startWidth + deltaX, this.minWidth),
            this.maxWidth
        );

        this.setWidth(newWidth);
    }

    stopResize() {
        if (this.isResizing) {
            this.isResizing = false;
            this.handle.style.background = 'transparent';
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            // Save width to localStorage
            const currentWidth = this.pane.offsetWidth;
            localStorage.setItem('rightPaneWidth', currentWidth);
        }
    }

    setWidth(width) {
        if (this.pane.classList.contains('visible')) {
            this.pane.style.width = `${width}px`;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.resizablePane = new ResizablePane('right-pane');
});
