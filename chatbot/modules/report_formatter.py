"""
Report Formatting Utilities

Provides modern, professional formatting for threat assessment reports.
Improves readability with visual hierarchy, tables, and clean markdown.

Target audiences:
- Executive Summary: C-level (business focus)
- Technical Report: Security specialists (technical depth)
- Action Plan: CISO team (execution focus)
"""

from typing import Dict, List, Optional
import re


def format_section_header(title: str, icon: str, level: int = 2) -> str:
    """
    Generate clean section headers with icons.

    Args:
        title: Section title
        icon: Emoji icon for visual anchor
        level: Header level (2=##, 3=###, default: 2)

    Returns:
        Formatted markdown header with icon

    Example:
        >>> format_section_header("Risk Overview", "🎯", 2)
        '## 🎯 Risk Overview\\n\\n'
    """
    hashes = '#' * level
    return f"{hashes} {icon} {title}\n\n"


def format_metric_dashboard(metrics: Dict[str, Dict]) -> str:
    """
    Generate executive dashboard with 4-column metric grid.

    Args:
        metrics: Dictionary of metrics with format:
            {
                "risk": {"value": "91/100", "label": "CRITICAL", "icon": "🔴"},
                "timeline": {"value": "24-48h", "label": "URGENT", "icon": "⏰"},
                "investment": {"value": "$50K", "label": "Budget", "icon": "💰"},
                "reduction": {"value": "95%", "label": "Risk Reduction", "icon": "📉"}
            }

    Returns:
        HTML table with centered metrics in 4 columns

    Example:
        >>> metrics = {
        ...     "risk": {"value": "91/100", "label": "CRITICAL", "icon": "🔴"}
        ... }
        >>> result = format_metric_dashboard(metrics)
        >>> "table" in result
        True
    """
    output = ['<table>', '<tr>']

    # Determine number of columns (max 4)
    num_metrics = min(len(metrics), 4)
    width = 100 // num_metrics

    for metric_data in list(metrics.values())[:4]:
        icon = metric_data.get('icon', '')
        label = metric_data.get('label', '')
        value = metric_data.get('value', '')

        output.append(f'<td align="center" width="{width}%">\n')
        output.append(f'\n**{label}**  \n')
        output.append(f'{icon} **{value}**  \n')
        output.append('\n</td>')

    output.append('</tr>')
    output.append('</table>\n\n')

    return '\n'.join(output)


def format_before_after_comparison(
    before: Dict,
    after: Dict,
    metric_name: str = "Risk Transformation"
) -> str:
    """
    Generate side-by-side before/after comparison table.

    Args:
        before: {"risk": "65/100", "status": "HIGH RISK", "controls": 0}
        after: {"risk": "3/100", "status": "LOW RISK", "controls": 16}
        metric_name: Section title (default: "Risk Transformation")

    Returns:
        Side-by-side table with color-coded states

    Example:
        >>> before = {"risk": "65/100", "status": "HIGH", "controls": 0}
        >>> after = {"risk": "3/100", "status": "ACCEPT", "controls": 16}
        >>> result = format_before_after_comparison(before, after)
        >>> "Current State" in result and "Target State" in result
        True
    """
    output = [f"### 📊 {metric_name}\n"]
    output.append('\n<table>')
    output.append('<tr>')
    output.append('<td width="50%">\n')
    output.append('\n**🔴 Current State**\n')
    output.append('```')
    output.append(f'Risk: {before.get("risk", "N/A")}')
    output.append(f'Status: {before.get("status", "N/A")}')
    output.append(f'Controls: {before.get("controls", 0)} implemented')
    output.append('```\n')
    output.append('</td>')
    output.append('<td width="50%">\n')
    output.append('\n**🟢 Target State**\n')
    output.append('```')
    output.append(f'Risk: {after.get("risk", "N/A")}')
    output.append(f'Status: {after.get("status", "N/A")}')
    output.append(f'Controls: {after.get("controls", 0)} implemented')
    output.append('```\n')
    output.append('</td>')
    output.append('</tr>')
    output.append('</table>\n\n')

    return '\n'.join(output)


def format_task_card(
    task: Dict,
    phase: str,
    task_num: int
) -> str:
    """
    Generate action plan task card with table and details.

    Args:
        task: {
            "control": "Rate Limiting",
            "owner": "SecOps Team",
            "effort": "4-8 hours",
            "cost": "$500-$1K",
            "impact": "-10 to -15 points",
            "validation": "Security team testing",
            "rationale": "Prevents DoS attacks by limiting request rates"
        }
        phase: "Phase 1: Quick Wins"
        task_num: 1

    Returns:
        Task card with table and rationale

    Example:
        >>> task = {"control": "MFA", "owner": "SecOps", "effort": "4h"}
        >>> result = format_task_card(task, "Phase 1", 1)
        >>> "Task 1" in result and "MFA" in result
        True
    """
    control = task.get('control', 'Unknown Control')
    output = [f"### 📋 Task {task_num}: {control}\n"]
    output.append('| Attribute | Details |')
    output.append('|-----------|---------|')
    output.append(f'| **Owner** | {task.get("owner", "TBD")} |')
    output.append(f'| **Effort** | {task.get("effort", "TBD")} ⏱️ |')
    output.append(f'| **Cost** | {task.get("cost", "TBD")} 💰 |')
    output.append(f'| **Impact** | 🔻 {task.get("impact", "TBD")} |')
    output.append(f'| **Validation** | {task.get("validation", "TBD")} |\n')

    if task.get('rationale'):
        output.append(f"**Why this matters:** {task['rationale']}\n")

    return '\n'.join(output)


def format_mitre_technique_card(
    technique_id: str,
    technique_name: str,
    description: str,
    context: Dict
) -> str:
    """
    Generate detailed MITRE technique card.

    Args:
        technique_id: "T1190"
        technique_name: "Exploit Public-Facing Application"
        description: Full MITRE description
        context: {
            "severity": "CRITICAL",
            "paths": [1],
            "current_defense": None,
            "recommended": ["WAF", "Input Validation"]
        }

    Returns:
        Detailed technique card with severity, paths, and recommendations

    Example:
        >>> card = format_mitre_technique_card(
        ...     "T1190", "Exploit Public-Facing Application",
        ...     "Adversaries may exploit...",
        ...     {"severity": "CRITICAL", "paths": [1], "recommended": ["WAF"]}
        ... )
        >>> "T1190" in card and "CRITICAL" in card
        True
    """
    severity_icons = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢"
    }

    severity = context.get('severity', 'MEDIUM')
    icon = severity_icons.get(severity, '⚪')

    output = [f"### 🎯 {technique_id}: {technique_name}\n"]
    output.append(f"**Severity:** {icon} {severity}  ")
    output.append(f"**Attack Vector:** {description[:100]}...\n")
    output.append('\n| Attribute | Value |')
    output.append('|-----------|-------|')

    if context.get('paths'):
        path_list = ', '.join([f"#{p}" for p in context['paths']])
        output.append(f"| **Present in Paths** | {path_list} |")

    current = context.get('current_defense', 'None')
    if current:
        output.append(f"| **Current Defense** | ✅ {current} |")
    else:
        output.append(f"| **Current Defense** | ❌ None |")

    if context.get('recommended'):
        rec_list = ', '.join(context['recommended'])
        output.append(f"| **Recommended** | {rec_list} |\n")

    return '\n'.join(output)


def remove_ascii_separators(text: str, remove_all: bool = True) -> str:
    """
    Replace ASCII art separators with clean markdown or remove entirely.

    Replaces:
    - ═══...═══ → (removed)
    - ───...─── → (removed)
    - ===...=== → (removed)
    - {'='*80} → (removed)

    Args:
        text: Report text with ASCII separators
        remove_all: If True, removes separators entirely. If False, converts to ---

    Returns:
        Clean text without distracting separators

    Example:
        >>> text = "═══════════════\\nSection\\n═══════════════\\n"
        >>> result = remove_ascii_separators(text)
        >>> "═" not in result
        True
    """
    # Replace box-drawing characters
    if remove_all:
        text = re.sub(r'═{3,}', '', text)
        text = re.sub(r'─{3,}', '', text)
        text = re.sub(r'^={3,}$', '', text, flags=re.MULTILINE)
    else:
        text = re.sub(r'═{3,}', '---', text)
        text = re.sub(r'─{3,}', '---', text)
        text = re.sub(r'^={3,}$', '---', text, flags=re.MULTILINE)

    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


def format_callout(text: str, style: str = "info") -> str:
    """
    Generate markdown callout/alert box.

    Args:
        text: Content to display in callout
        style: "info", "warning", "success", "danger" (default: "info")

    Returns:
        Markdown blockquote with appropriate icon

    Example:
        >>> result = format_callout("Important message", "warning")
        >>> "⚠️" in result
        True
    """
    icons = {
        "info": "ℹ️",
        "warning": "⚠️",
        "success": "✅",
        "danger": "🚨"
    }

    icon = icons.get(style, "ℹ️")
    return f"> {icon} **{text}**\n\n"


def format_progress_bar(
    current: int,
    total: int,
    width: int = 20,
    label: str = ""
) -> str:
    """
    Generate ASCII progress bar.

    Args:
        current: Current progress value
        total: Total/max value
        width: Width of bar in characters (default: 20)
        label: Optional label to display

    Returns:
        Progress bar string with percentage

    Example:
        >>> result = format_progress_bar(15, 20, width=10, label="Risk")
        >>> "75%" in result and "█" in result
        True
    """
    if total == 0:
        percent = 0
    else:
        percent = int((current / total) * 100)

    filled = int((current / total) * width) if total > 0 else 0
    bar = "█" * filled + "░" * (width - filled)

    if label:
        return f"{label}: [{bar}] {percent}%"
    else:
        return f"[{bar}] {percent}%"


def format_key_value_table(data: Dict[str, str], title: str = "") -> str:
    """
    Generate simple two-column key-value table.

    Args:
        data: Dictionary of key-value pairs
        title: Optional table title

    Returns:
        Markdown table

    Example:
        >>> data = {"Risk": "91/100", "Status": "CRITICAL"}
        >>> result = format_key_value_table(data, "Metrics")
        >>> "Risk" in result and "91/100" in result
        True
    """
    output = []
    if title:
        output.append(f"**{title}**\n")

    output.append('| Attribute | Value |')
    output.append('|-----------|-------|')

    for key, value in data.items():
        output.append(f'| **{key}** | {value} |')

    output.append('')
    return '\n'.join(output)
