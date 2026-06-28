"""
Clean annotation-style recommended MMDs into analysis-ready architecture diagrams.

The report generator writes 08b_recommended_target.mmd with NEW_* control nodes
whose labels contain MITRE/RAPIDS metadata annotations:

    NEW_MFA["Mfa<br/>MITRE: M1032<br/>Prevents: T1078"]
    NEW_USERTRAINING["User Training<br/>RAPIDS: Phishing<br/>Prevention<br/>Hardening"]

This module produces a clean MMD where:
  - NEW_* node IDs become safe Mermaid identifiers (no spaces): MFA, RateLimiting
  - Node labels retain only the human-readable display name: "MFA", "Rate Limiting"
  - Edges reference the safe identifier, not the display name
  - %% comment lines and style directives are removed
  - Original architecture nodes and edges are preserved unchanged
"""

import re
from typing import Dict, NamedTuple


class _NodeInfo(NamedTuple):
    clean_id:    str   # Safe Mermaid node ID — no spaces (e.g. RateLimiting)
    display:     str   # Human-readable label text (e.g. "Rate Limiting")
    shape_open:  str   # Mermaid bracket opening (["  or [/"  or [(" )
    shape_close: str   # Mermaid bracket closing ("]  or "/]  or ")]  )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_recommended_mmd(mmd_text: str) -> str:
    """Transform an annotation-style recommended MMD into an analysis-ready MMD.

    Safe to call on any MMD — if no NEW_* nodes are present the text is
    returned with only comment/style lines stripped.
    """
    lines  = mmd_text.splitlines()
    id_map = _build_id_map(lines)        # {NEW_MFA: _NodeInfo(clean_id, display, ...)}
    return "\n".join(_transform_lines(lines, id_map)).strip() + "\n"


def extract_control_names(mmd_text: str) -> list:
    """Return the human-readable display names of all NEW_* control nodes."""
    id_map = _build_id_map(mmd_text.splitlines())
    return sorted(info.display for info in id_map.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_NODE_SIMPLE_RE = re.compile(
    r'^(\s*)(NEW_[A-Z0-9_]+)\s*(\[[\(\"/]*)\"([^\"<\n]+)',
)


def _display_label(raw: str) -> str:
    """Extract the human-readable name from a raw NEW_* label string.

    'Mfa<br/>MITRE: M1032<br/>Prevents: T1078'  →  'MFA'
    'Rate Limiting<br/>MITRE: M1033'             →  'Rate Limiting'
    'User Training<br/>RAPIDS: Phishing'         →  'User Training'
    """
    name = raw.split("<br/>")[0].strip()
    # Uppercase short all-alpha labels (mfa → MFA, edr → EDR, dlp → DLP, waf → WAF)
    if len(name) <= 4 and name.isalpha():
        return name.upper()
    return name


def _clean_id(node_id: str) -> str:
    """Derive a space-free Mermaid node ID from a NEW_* identifier.

    NEW_RATELIMITING   → RateLimiting
    NEW_USER_TRAINING  → UserTraining
    NEW_MFA            → MFA
    NEW_DLP            → DLP
    """
    name = node_id[4:]              # strip "NEW_"
    parts = name.split("_")
    joined = "".join(p.capitalize() for p in parts)
    # Uppercase short (<=4 char, all-alpha) results
    if len(joined) <= 4 and joined.isalpha():
        return joined.upper()
    return joined


def _shape_brackets(bracket_str: str) -> tuple:
    """Infer opening/closing shape brackets from the original bracket string."""
    if '/"' in bracket_str or bracket_str.strip().startswith('[/'):
        return '[/"', '"/]'
    if '("' in bracket_str or bracket_str.strip().startswith('[('):
        return '[("', '")]'
    return '["', '"]'


def _build_id_map(lines: list) -> Dict[str, _NodeInfo]:
    """Scan lines for NEW_* node definitions → {raw_id: _NodeInfo}."""
    id_map: Dict[str, _NodeInfo] = {}
    for line in lines:
        m = _NODE_SIMPLE_RE.match(line)
        if m:
            raw_id      = m.group(2)
            bracket_str = m.group(3)
            raw_label   = m.group(4)
            display     = _display_label(raw_label) or _clean_id(raw_id)
            s_open, s_close = _shape_brackets(bracket_str)
            id_map[raw_id] = _NodeInfo(
                clean_id=_clean_id(raw_id),
                display=display,
                shape_open=s_open,
                shape_close=s_close,
            )
        elif "NEW_" in line and not line.strip().startswith("%") \
                and "-->" not in line and "-..->" not in line and "-.->":
            bare = re.search(r'(NEW_[A-Z0-9_]+)', line)
            if bare and bare.group(1) not in id_map:
                raw_id = bare.group(1)
                cid    = _clean_id(raw_id)
                id_map[raw_id] = _NodeInfo(
                    clean_id=cid, display=cid,
                    shape_open='["', shape_close='"]',
                )
    return id_map


def _is_skip_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("%%"):
        return True
    if stripped.startswith("style NEW_"):
        return True
    return False


def _rewrite_node_def(line: str, id_map: Dict[str, _NodeInfo]) -> str:
    """Rewrite a NEW_* node definition line.

    NEW_RATELIMITING["Rate Limiting<br/>MITRE: M1033<br/>..."]
    → RateLimiting["Rate Limiting"]
    """
    for raw_id, info in id_map.items():
        if raw_id not in line:
            continue
        indent = len(line) - len(line.lstrip())
        return (
            " " * indent
            + info.clean_id
            + info.shape_open
            + info.display
            + info.shape_close
        )
    return line


def _rewrite_edge(line: str, id_map: Dict[str, _NodeInfo]) -> str:
    """Replace all NEW_* IDs in an edge line with their clean_id (no spaces)."""
    result = line
    # Sort longest-first to avoid partial matches (NEW_RATELIMITING before NEW_RATE)
    for raw_id, info in sorted(id_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(raw_id, info.clean_id)
    return result


def _transform_lines(lines: list, id_map: Dict[str, _NodeInfo]) -> list:
    out = []
    prev_blank = False

    for line in lines:
        stripped = line.strip()

        if _is_skip_line(line):
            continue

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

        # Rewrite NEW_* references in edges
        if "NEW_" in line and ("-" in line or "-->"):
            out.append(_rewrite_edge(line, id_map))
            continue

        out.append(line)

    return out
