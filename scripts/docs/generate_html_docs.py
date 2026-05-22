#!/usr/bin/env python3
"""
Unified HTML Documentation Generator

Converts markdown documentation to interactive HTML with:
- Syntax highlighting (Prism.js)
- Responsive layout (Bootstrap 5.3)
- Interactive features (search, collapsible sections, charts)
- Dark mode support
- Navigation between docs

Usage:
    python3 scripts/docs/generate_html_docs.py [--watch]
"""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import markdown
from bs4 import BeautifulSoup


class DocumentMetadata:
    """Metadata for a documentation file."""

    def __init__(self, source_path: str, output_path: str, title: str,
                 doc_type: str, template: str):
        self.source_path = source_path
        self.output_path = output_path
        self.title = title
        self.doc_type = doc_type  # 'index', 'status', 'roadmap'
        self.template = template
        self.last_updated = self._get_git_last_modified()

    def _get_git_last_modified(self) -> str:
        """Get last modification date from git."""
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%ci', self.source_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # Parse git date: 2026-05-22 10:30:45 +0000
                date_str = result.stdout.strip().split()[0]
                return date_str
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback to file mtime
        try:
            mtime = os.path.getmtime(self.source_path)
            return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        except OSError:
            return datetime.now().strftime('%Y-%m-%d')


class HTMLGenerator:
    """Generates HTML documentation from markdown sources."""

    # Document configurations
    DOCS = [
        DocumentMetadata(
            source_path='README.md',
            output_path='html/index.html',
            title='ThreatAssessor - User Guide',
            doc_type='index',
            template='index'
        ),
        DocumentMetadata(
            source_path='STATUS_AND_PLAN.md',
            output_path='html/status.html',
            title='ThreatAssessor - Project Status',
            doc_type='status',
            template='status'
        ),
        DocumentMetadata(
            source_path='docs/specs/MVP_SPECIFICATION.md',
            output_path='html/roadmap.html',
            title='ThreatAssessor - Product Roadmap',
            doc_type='roadmap',
            template='roadmap'
        ),
    ]

    def __init__(self, project_root: str = '.'):
        self.project_root = Path(project_root).resolve()
        self.md = markdown.Markdown(extensions=[
            'fenced_code',
            'tables',
            'toc',
            'attr_list',
            'md_in_html',
            'nl2br'  # Preserve line breaks
        ])

    def convert_markdown_to_html(self, md_content: str) -> Tuple[str, str]:
        """
        Convert markdown to HTML.

        Returns:
            Tuple of (html_content, toc_html)
        """
        self.md.reset()
        html = self.md.convert(md_content)
        toc = self.md.toc if hasattr(self.md, 'toc') else ''
        return html, toc

    def extract_frontmatter(self, content: str) -> Tuple[Dict, str]:
        """Extract YAML frontmatter if present."""
        frontmatter = {}
        body = content

        if content.startswith('---\n'):
            parts = content.split('---\n', 2)
            if len(parts) >= 3:
                # Simple YAML parsing (key: value)
                for line in parts[1].strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip()
                body = parts[2]

        return frontmatter, body

    def enhance_code_blocks(self, html: str) -> str:
        """Add Prism.js classes to code blocks and convert Mermaid to diagrams."""
        soup = BeautifulSoup(html, 'html.parser')

        for pre in soup.find_all('pre'):
            code = pre.find('code')
            if code:
                # Extract language from class (markdown adds language-*)
                lang_class = None
                for cls in code.get('class', []):
                    if cls.startswith('language-'):
                        lang_class = cls
                        break

                # Check if this is a Mermaid diagram
                if lang_class == 'language-mermaid':
                    # Convert to Mermaid div instead of code block
                    mermaid_div = soup.new_tag('div', **{'class': 'mermaid'})
                    mermaid_div.string = code.get_text()
                    pre.replace_with(mermaid_div)
                    continue

                if not lang_class:
                    # Default to plaintext
                    lang_class = 'language-plaintext'
                    code['class'] = code.get('class', []) + [lang_class]

                # Add line-numbers class for Prism (but not for mermaid)
                pre['class'] = pre.get('class', []) + ['line-numbers']

        return str(soup)

    def add_copy_buttons(self, html: str) -> str:
        """Add copy buttons to code blocks."""
        soup = BeautifulSoup(html, 'html.parser')

        for pre in soup.find_all('pre'):
            # Wrap in container
            container = soup.new_tag('div', **{'class': 'code-block-container'})
            pre.wrap(container)

            # Add copy button
            button = soup.new_tag('button', **{
                'class': 'copy-button',
                'onclick': 'copyCode(this)',
                'title': 'Copy code'
            })
            button.string = '📋 Copy'
            container.insert(0, button)

        return str(soup)

    def make_tables_sortable(self, html: str) -> str:
        """Convert tables to Bootstrap sortable tables."""
        soup = BeautifulSoup(html, 'html.parser')

        for table in soup.find_all('table'):
            table['class'] = table.get('class', []) + [
                'table', 'table-striped', 'table-hover',
                'table-responsive', 'sortable'
            ]

        return str(soup)

    def extract_metrics_for_dashboard(self, html: str, doc_type: str) -> Dict:
        """Extract metrics for status dashboard charts."""
        metrics = {}

        if doc_type == 'status':
            soup = BeautifulSoup(html, 'html.parser')

            # Extract phase completion percentages
            # Look for patterns like "99.5% confidence"
            confidence_pattern = r'(\d+\.?\d*)%\s+confidence'
            for match in re.finditer(confidence_pattern, html):
                metrics['confidence'] = float(match.group(1))

            # Extract validation pass rate
            # Look for "22/22 architectures" or "100%"
            pass_rate_pattern = r'(\d+)/(\d+)\s+architectures'
            for match in re.finditer(pass_rate_pattern, html):
                passed = int(match.group(1))
                total = int(match.group(2))
                metrics['pass_rate'] = (passed / total) * 100

            # Count phases by status
            metrics['phases'] = {
                'complete': html.count('✅ Complete') + html.count('✅ COMPLETE'),
                'in_progress': html.count('🚧 In Progress'),
                'planned': html.count('📋 Planned') + html.count('📦 Future')
            }

        return metrics

    def generate_base_template(self) -> str:
        """Generate base HTML template."""
        return '''<!DOCTYPE html>
<html lang="en" data-bs-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}}</title>
    <meta name="description" content="{{description}}">
    <meta name="generator" content="ThreatAssessor HTML Generator">
    <meta name="last-updated" content="{{last_updated}}">

    <!-- Bootstrap 5.3 CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">

    <!-- Prism.js for syntax highlighting -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-numbers/prism-line-numbers.min.css" rel="stylesheet">

    <!-- Font Awesome for icons -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">

    <!-- Mermaid.js for diagram rendering -->
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'loose'
        });
    </script>

    <!-- Custom CSS -->
    <link href="{{css_path}}" rel="stylesheet">

    <style>
        /* Base styles */
        :root {
            --primary-color: #0d6efd;
            --bg-color: #ffffff;
            --text-color: #212529;
            --code-bg: #f8f9fa;
            --border-color: #dee2e6;
        }

        [data-bs-theme="dark"] {
            --bg-color: #212529;
            --text-color: #dee2e6;
            --code-bg: #2d3748;
            --border-color: #495057;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
        }

        .code-block-container {
            position: relative;
            margin-bottom: 1.5rem;
        }

        .copy-button {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            padding: 0.25rem 0.5rem;
            font-size: 0.875rem;
            background-color: var(--code-bg);
            border: 1px solid var(--border-color);
            border-radius: 0.25rem;
            cursor: pointer;
            z-index: 10;
        }

        .copy-button:hover {
            background-color: var(--primary-color);
            color: white;
        }

        table.sortable th {
            cursor: pointer;
            user-select: none;
        }

        table.sortable th:hover {
            background-color: var(--code-bg);
        }

        .navbar {
            border-bottom: 1px solid var(--border-color);
        }

        .theme-toggle {
            cursor: pointer;
            padding: 0.5rem;
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-light bg-light sticky-top">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{home_url}}">
                <i class="fas fa-shield-alt"></i> ThreatAssessor
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link {{active_index}}" href="{{index_url}}">
                            <i class="fas fa-book"></i> User Guide
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{active_status}}" href="{{status_url}}">
                            <i class="fas fa-chart-line"></i> Status
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{active_roadmap}}" href="{{roadmap_url}}">
                            <i class="fas fa-map"></i> Roadmap
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="../docs/NEXT_STEPS.md">
                            <i class="fas fa-tasks"></i> Next Steps
                        </a>
                    </li>
                </ul>
                <div class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode">
                    <i class="fas fa-moon"></i>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    {{content}}

    <!-- Footer -->
    <footer class="mt-5 py-4 bg-light border-top">
        <div class="container text-center text-muted">
            <p class="mb-0">
                Generated by ThreatAssessor HTML Generator |
                Last Updated: {{last_updated}} |
                <a href="{{source_url}}">View Markdown Source</a>
            </p>
        </div>
    </footer>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

    <!-- Prism.js for syntax highlighting -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/line-numbers/prism-line-numbers.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-bash.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-markdown.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-yaml.min.js"></script>

    <!-- Fuse.js for search -->
    <script src="https://cdn.jsdelivr.net/npm/fuse.js@6.6.2"></script>

    <!-- Chart.js for status dashboard -->
    {{chart_js}}

    <!-- Custom JavaScript -->
    <script>
        // Theme toggle
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-bs-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-bs-theme', newTheme);
            localStorage.setItem('theme', newTheme);

            // Update icon
            const icon = document.querySelector('.theme-toggle i');
            icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }

        // Load saved theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-bs-theme', savedTheme);
        if (savedTheme === 'dark') {
            document.querySelector('.theme-toggle i').className = 'fas fa-sun';
        }

        // Copy code function
        function copyCode(button) {
            const container = button.parentElement;
            const pre = container.querySelector('pre');
            const code = pre.querySelector('code');
            const text = code.textContent;

            navigator.clipboard.writeText(text).then(() => {
                button.textContent = '✓ Copied!';
                setTimeout(() => {
                    button.textContent = '📋 Copy';
                }, 2000);
            });
        }

        // Make tables sortable
        document.addEventListener('DOMContentLoaded', function() {
            const tables = document.querySelectorAll('table.sortable');
            tables.forEach(table => {
                const headers = table.querySelectorAll('th');
                headers.forEach((header, index) => {
                    header.addEventListener('click', () => {
                        sortTable(table, index);
                    });
                });
            });
        });

        function sortTable(table, column) {
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const isAscending = table.dataset.sortOrder !== 'asc';

            rows.sort((a, b) => {
                const aValue = a.cells[column].textContent.trim();
                const bValue = b.cells[column].textContent.trim();

                // Try numeric comparison
                const aNum = parseFloat(aValue);
                const bNum = parseFloat(bValue);
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return isAscending ? aNum - bNum : bNum - aNum;
                }

                // Fall back to string comparison
                return isAscending
                    ? aValue.localeCompare(bValue)
                    : bValue.localeCompare(aValue);
            });

            // Reorder rows
            rows.forEach(row => tbody.appendChild(row));

            // Update sort order
            table.dataset.sortOrder = isAscending ? 'asc' : 'desc';

            // Update header indicator
            const headers = table.querySelectorAll('th');
            headers.forEach((h, i) => {
                const icon = h.querySelector('.sort-icon');
                if (icon) icon.remove();
            });

            const icon = document.createElement('span');
            icon.className = 'sort-icon ms-2';
            icon.innerHTML = isAscending ? '▲' : '▼';
            headers[column].appendChild(icon);
        }

        {{custom_js}}
    </script>
</body>
</html>'''

    def generate_doc(self, doc: DocumentMetadata) -> None:
        """Generate HTML for a single document."""
        print(f"Generating {doc.output_path}...")

        # Read source markdown
        source_file = self.project_root / doc.source_path
        if not source_file.exists():
            print(f"  ⚠️  Source file not found: {source_file}")
            return

        with open(source_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # Extract frontmatter
        frontmatter, body = self.extract_frontmatter(md_content)

        # Convert markdown to HTML
        html_body, toc = self.convert_markdown_to_html(body)

        # Enhance HTML
        html_body = self.enhance_code_blocks(html_body)
        html_body = self.add_copy_buttons(html_body)
        html_body = self.make_tables_sortable(html_body)

        # Extract metrics for dashboard
        metrics = self.extract_metrics_for_dashboard(html_body, doc.doc_type)

        # Generate final HTML using template
        template = self.generate_base_template()

        # Wrap content based on doc type
        if doc.doc_type == 'index':
            content = f'<div class="container my-5">{html_body}</div>'
        elif doc.doc_type == 'status':
            content = self._generate_status_content(html_body, metrics)
        elif doc.doc_type == 'roadmap':
            content = self._generate_roadmap_content(html_body, toc)
        else:
            content = f'<main class="container my-5">{html_body}</main>'

        # Replace template variables
        html = template.replace('{{title}}', doc.title)
        html = html.replace('{{description}}', frontmatter.get('description', doc.title))
        html = html.replace('{{last_updated}}', doc.last_updated)
        html = html.replace('{{content}}', content)
        html = html.replace('{{css_path}}', self._get_css_path(doc))
        html = html.replace('{{chart_js}}', self._get_chartjs_include(doc))
        html = html.replace('{{custom_js}}', self._get_custom_js(doc, metrics))

        # Navigation URLs (all HTML in html/ folder now)
        html = html.replace('{{home_url}}', 'index.html')
        html = html.replace('{{index_url}}', 'index.html')
        html = html.replace('{{status_url}}', 'status.html')
        html = html.replace('{{roadmap_url}}', 'roadmap.html')
        html = html.replace('{{source_url}}', '../' + doc.source_path)

        # Active nav highlighting
        html = html.replace('{{active_index}}', 'active' if doc.doc_type == 'index' else '')
        html = html.replace('{{active_status}}', 'active' if doc.doc_type == 'status' else '')
        html = html.replace('{{active_roadmap}}', 'active' if doc.doc_type == 'roadmap' else '')

        # Write output
        output_file = self.project_root / doc.output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"  ✓ Generated {doc.output_path}")

    def _get_css_path(self, doc: DocumentMetadata) -> str:
        """Get CSS file path relative to output."""
        # All HTML files now in html/ folder, so same relative path
        return '../docs/specs/templates/main.css'

    def _get_chartjs_include(self, doc: DocumentMetadata) -> str:
        """Get Chart.js include if needed."""
        if doc.doc_type == 'status':
            return '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'
        return ''

    def _get_custom_js(self, doc: DocumentMetadata, metrics: Dict) -> str:
        """Get custom JavaScript for document type."""
        if doc.doc_type == 'status' and metrics:
            return f'''
        // Status dashboard metrics
        const metrics = {json.dumps(metrics)};

        // Render charts
        document.addEventListener('DOMContentLoaded', function() {{
            // Confidence gauge
            const confidenceCtx = document.getElementById('confidenceChart');
            if (confidenceCtx) {{
                new Chart(confidenceCtx, {{
                    type: 'doughnut',
                    data: {{
                        datasets: [{{
                            data: [metrics.confidence || 0, 100 - (metrics.confidence || 0)],
                            backgroundColor: ['#0d6efd', '#e9ecef']
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        circumference: 180,
                        rotation: -90,
                        cutout: '75%',
                        plugins: {{
                            legend: {{ display: false }},
                            tooltip: {{ enabled: false }}
                        }}
                    }}
                }});
            }}
        }});
            '''
        return ''

    def _generate_status_content(self, html_body: str, metrics: Dict) -> str:
        """Generate status dashboard content with metrics."""
        dashboard = f'''
<div class="container-fluid my-4">
    <div class="row">
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h5 class="card-title">Confidence</h5>
                    <canvas id="confidenceChart" width="150" height="75"></canvas>
                    <h2 class="mt-2">{metrics.get('confidence', 'N/A')}%</h2>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h5 class="card-title">Validation Pass Rate</h5>
                    <h2 class="text-success">{metrics.get('pass_rate', 'N/A')}%</h2>
                    <p class="text-muted">22/22 architectures</p>
                </div>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">Phase Status</h5>
                    <div class="d-flex justify-content-around">
                        <div class="text-center">
                            <h3 class="text-success">{metrics.get('phases', {}).get('complete', 0)}</h3>
                            <small>Complete</small>
                        </div>
                        <div class="text-center">
                            <h3 class="text-warning">{metrics.get('phases', {}).get('in_progress', 0)}</h3>
                            <small>In Progress</small>
                        </div>
                        <div class="text-center">
                            <h3 class="text-secondary">{metrics.get('phases', {}).get('planned', 0)}</h3>
                            <small>Planned</small>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div class="row mt-4">
        <div class="col-12">
            <div class="card">
                <div class="card-body">
                    {html_body}
                </div>
            </div>
        </div>
    </div>
</div>
        '''
        return dashboard

    def _generate_roadmap_content(self, html_body: str, toc: str) -> str:
        """Generate roadmap content with sidebar navigation."""
        return f'''
<div class="container-fluid">
    <div class="row">
        <nav class="col-md-3 col-lg-2 d-md-block bg-light sidebar collapse" id="sidebarMenu">
            <div class="position-sticky pt-3">
                <h6 class="sidebar-heading px-3 mt-4 mb-1 text-muted">
                    <span>Navigation</span>
                </h6>
                {toc}
                <div class="px-3 mt-4">
                    <input type="text" class="form-control" id="searchBox" placeholder="Search...">
                </div>
            </div>
        </nav>
        <main class="col-md-9 ms-sm-auto col-lg-10 px-md-4">
            <div class="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center pt-3 pb-2 mb-3 border-bottom">
                <h1 class="h2">Product Roadmap</h1>
                <div class="btn-toolbar mb-2 mb-md-0">
                    <span class="badge bg-success">Strategic Vision</span>
                </div>
            </div>
            <div class="pb-5">
                {html_body}
            </div>
        </main>
    </div>
</div>
        '''

    def generate_all(self) -> None:
        """Generate all HTML documentation."""
        print("ThreatAssessor HTML Documentation Generator")
        print("=" * 50)

        for doc in self.DOCS:
            self.generate_doc(doc)

        print("\n✓ All documentation generated successfully!")
        print("\nGenerated files:")
        for doc in self.DOCS:
            print(f"  - {doc.output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate HTML documentation from markdown sources'
    )
    parser.add_argument(
        '--watch',
        action='store_true',
        help='Watch for changes and regenerate (not implemented yet)'
    )
    parser.add_argument(
        '--project-root',
        default='.',
        help='Project root directory (default: current directory)'
    )

    args = parser.parse_args()

    if args.watch:
        print("⚠️  Watch mode not implemented yet. Run manually after changes.")
        return 1

    generator = HTMLGenerator(project_root=args.project_root)
    generator.generate_all()

    return 0


if __name__ == '__main__':
    exit(main())
