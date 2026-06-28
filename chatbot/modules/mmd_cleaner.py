"""
Clean annotation-style recommended MMDs into analysis-ready architecture diagrams.

The report generator writes 08b_recommended_target.mmd with NEW_* control nodes
whose labels contain MITRE/RAPIDS metadata annotations:

    NEW_MFA["Mfa<br/>MITRE: M1032<br/>Prevents: T1078"]
    NEW_USERTRAINING["User Training<br/>RAPIDS: Phishing<br/>Prevention<br/>Hardening"]

The analysis engine matches controls by node label text, so these nodes are
recognisable — but the `<br/>` metadata must be stripped so the engine
doesn't treat "M1032" or "T1078" as part of the control name.

This module produces a clean MMD where:
  - NEW_* node IDs become readable names (MFA, RateLimiting, etc.)
  - Node labels retain only the human-readable control name
  - Original architecture nodes and edges are preserved unchanged
  - %% comment lines and style directives are removed
  - All edge references to NEW_* IDs are updated to clean names
"""

import re
from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_recommended_mmd(mmd_text: str) -> str:
    """Transform an annotation-style recommended MMD into an analysis-ready MMD.

    Safe to call on any MMD — if no NEW_* nodes are present the text is
    returned with only comment/style lines stripped.
    """
    lines = mmd_text.splitlines()
    id_map = _build_id_map(lines)          # {NEW_MFA: "MFA", ...}
    cleaned = _transform_lines(lines, id_map)
    return "\n".join(cleaned).strip() + "\n"


def extract_control_names(mmd_text: str) -> list:
    """Return the human-readable names of all NEW_* control nodes in an MMD."""
    id_map = _build_id_map(mmd_text.splitlines())
    return sorted(id_map.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Match a NEW_* node definition line, capturing:
#   group 1 = full node ID (NEW_MFA)
#   group 2 = opening bracket chars (["  or [("  or [/"  etc.)
#   group 3 = label text (everything before the first <br/> or closing bracket)
#   group 4 = closing bracket chars
_NODE_RE = re.compile(
    r'^(\s*)(NEW_[A-Z0-9_]+)'          # indent + node ID
    r'(\[[\(\"/]*)'                    # opening bracket(s)
    r'"([^"<\n]+)'                     # label up to first <br/> or quote
    r'(?:<br/>.*?)?'                   # optional metadata (greedy-lazy)
    r'"([\)\"/]*\])',                  # closing bracket(s)
    re.DOTALL,
)

# Simpler fallback: just capture node ID and first part of label
_NODE_SIMPLE_RE = re.compile(
    r'^(\s*)(NEW_[A-Z0-9_]+)\s*(\[[\(\"/]*)"([^"<\n]+)',
)


def _clean_label(raw: str) -> str:
    """Extract only the human-readable name from a NEW_* label.

    'Mfa<br/>MITRE: M1032<br/>Prevents: T1078'  →  'MFA'
    'Rate Limiting<br/>MITRE: M1033'             →  'Rate Limiting'
    'User Training<br/>RAPIDS: Phishing'         →  'User Training'
    """
    # Take only what's before the first <br/>
    name = raw.split("<br/>")[0].strip()
    # Title-case short all-lowercase labels (e.g. "mfa" → "MFA", "edr" → "EDR")
    if len(name) <= 4 and name.isalpha():
        return name.upper()
    return name


def _node_id_to_clean(node_id: str) -> str:
    """NEW_RATELIMITING → RateLimiting,  NEW_USER_TRAINING → UserTraining"""
    # Strip NEW_ prefix, then title-case each segment split by _
    name = node_id[4:]  # remove "NEW_"
    parts = name.split("_")
    return "".join(p.capitalize() for p in parts)


def _build_id_map(lines: list) -> Dict[str, str]:
    """Scan lines for NEW_* node definitions and build {node_id: clean_label}."""
    id_map: Dict[str, str] = {}
    for line in lines:
        # Try to match node definition
        m = _NODE_SIMPLE_RE.match(line)
        if m:
            node_id = m.group(2)
            raw_label = m.group(4)
            clean = _clean_label(raw_label)
            if not clean:
                clean = _node_id_to_clean(node_id)
            id_map[node_id] = clean
        elif "NEW_" in line and not line.strip().startswith("%") and "-->" not in line and "-..->" not in line:
            # Bare node ID without a label (just NEW_XXX on its own or in a subgraph)
            bare = re.search(r'(NEW_[A-Z0-9_]+)', line)
            if bare and bare.group(1) not in id_map:
                node_id = bare.group(1)
                id_map[node_id] = _node_id_to_clean(node_id)
    return id_map


def _is_skip_line(line: str) -> bool:
    """Return True for lines that should be dropped from the clean output."""
    stripped = line.strip()
    # Drop %% comment lines
    if stripped.startswith("%%"):
        return True
    # Drop style directives for NEW_* nodes
    if stripped.startswith("style NEW_"):
        return True
    # Drop blank lines that were separating comment blocks (keep single blank lines)
    return False


def _rewrite_node_def(line: str, id_map: Dict[str, str]) -> str:
    """Rewrite a NEW_* node definition to use clean ID and stripped label."""
    for node_id, clean_label in id_map.items():
        if node_id not in line:
            continue
        # Determine the Mermaid shape brackets from the original
        # ["  →  rectangle,  [/"  →  subroutine,  [("  →  cylinder
        shape_open  = '["'
        shape_close = '"]'
        if '[/"' in line or '[/' in line:
            shape_open, shape_close = '[/"', '"/]'
        elif '[("' in line or '[(' in line:
            shape_open, shape_close = '[("', '")]'

        indent = len(line) - len(line.lstrip())
        return " " * indent + f'{clean_label}{shape_open}{clean_label}{shape_close}'
    return line


def _rewrite_edge(line: str, id_map: Dict[str, str]) -> str:
    """Replace all NEW_* node ID references in an edge line with clean names."""
    result = line
    # Sort by length descending so NEW_RATELIMITING isn't partially matched by NEW_RATE
    for node_id, clean_label in sorted(id_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(node_id, clean_label)
    return result


def _transform_lines(lines: list, id_map: Dict[str, str]) -> list:
    """Apply all transformations to produce the clean MMD line list."""
    out = []
    prev_blank = False

    for line in lines:
        stripped = line.strip()

        # Skip comment and style lines
        if _is_skip_line(line):
            continue

        # Collapse consecutive blank lines to one
        if stripped == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
            continue
        prev_blank = False

        # Rewrite NEW_* node definitions
        if re.match(r'\s*NEW_[A-Z0-9_]+\s*[\[\(]', line):
            out.append(_rewrite_node_def(line, id_map))
            continue

        # Rewrite NEW_* references in edge lines (arrows present)
        if "NEW_" in line and ("-" in line or "-->") :
            out.append(_rewrite_edge(line, id_map))
            continue

        # Keep everything else unchanged (original arch nodes, subgraphs, etc.)
        out.append(line)

    return out
