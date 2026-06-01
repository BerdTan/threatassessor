"""
Fetch and parse CAVEAT threat intelligence data from Cloud Security Alliance GitHub.

CAVEAT (Cloud Adversarial, Vulnerability, Exploitation, and Threat) documents
cloud-specific attack techniques with CSP-specific (AWS/Azure/GCP) mitigations
and detection guidance.

Source: https://github.com/CloudSecurityAlliance-WG/CAVEaT
License: CC0-1.0 (public domain)

Output: chatbot/data/caveat/caveat_techniques.yaml
         (git-ignored — regenerate with this script)

Usage:
    python3 scripts/data/fetch_caveat.py
    python3 scripts/data/fetch_caveat.py --output-dir path/to/caveat/
"""

import re
import sys
import argparse
import logging
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print("Install missing deps: pip install requests pyyaml")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

RAW_URL = (
    "https://raw.githubusercontent.com/CloudSecurityAlliance-WG/CAVEaT"
    "/main/data/CAVEaT-files/CAVEaT-all-entries.md"
)

_REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUT_DIR = _REPO_ROOT / "chatbot" / "data" / "caveat"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _split_entries(raw: str) -> list[tuple[str, str]]:
    """Split the concatenated all-entries file into (title_line, body) pairs."""
    # Entries start with a line like: "## Title (version X.Y)" or "Title (version X.Y)"
    # The all-entries file uses H1 for title: "# Abuse Queue Services(version 1.0)"
    pattern = re.compile(r"^(?:#{1,2}\s+)?(.+?\(version [0-9.]+\))\s*$", re.MULTILINE)
    matches = list(pattern.finditer(raw))
    if not matches:
        log.warning("No CAVEAT entries found — check source format")
        return []

    entries = []
    for i, m in enumerate(matches):
        title_line = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        entries.append((title_line, body))
    return entries


def _parse_title(title_line: str) -> tuple[str, str]:
    """Return (title, version) from 'IAM Abuse (version 1.0)'."""
    m = re.match(r"^(.*?)\s*\(version\s*([0-9.]+)\)\s*$", title_line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title_line.strip(), "unknown"


def _extract_cloud_label(body: str) -> str:
    """Return 'IaaS, PaaS' etc from 'Cloud Service Label: IaaS, PaaS'."""
    m = re.search(r"Cloud Service Label:\s*(.+)", body)
    return m.group(1).strip() if m else ""


def _extract_section(body: str, section_name: str, next_sections: list[str]) -> str:
    """Extract text between 'section_name' header and the next known section."""
    # Build stop pattern from known subsequent sections
    stop = "|".join(re.escape(s) for s in next_sections)
    pattern = re.compile(
        rf"(?:^|\n){re.escape(section_name)}\s*\n(.*?)(?=\n(?:{stop})\s*\n|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(body)
    return m.group(1).strip() if m else ""


def _split_csp_rows(text: str) -> dict[str, list[str]]:
    """
    Split a mitigation/detection section into per-CSP lists.

    CAVEAT uses markdown pipe tables where CSP labels appear as cell values:
        | Audit      | | Description... |
        |            | AWS | AWS-specific text... |
        |            | Azure | Azure-specific text... |
        |            | GCP | GCP-specific text... |

    We scan cells by splitting on '|' and watch for CSP-label cells,
    then assign the adjacent description cell to that CSP bucket.

    Returns: {"aws": [...], "azure": [...], "gcp": [...], "generic": [...]}
    """
    result: dict[str, list[str]] = {"aws": [], "azure": [], "gcp": [], "generic": []}

    # Split into table rows (lines), then process cell-by-cell
    rows = text.splitlines()
    for row in rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if not cells:
            continue
        # Skip separator rows like --- | --- | ---
        if all(re.match(r"^-+$", c) for c in cells):
            continue

        # Walk cells looking for CSP labels
        i = 0
        current_csp = "generic"
        description_cells = []
        while i < len(cells):
            cell = cells[i]
            if re.match(r"^AWS$", cell, re.IGNORECASE):
                current_csp = "aws"
            elif re.match(r"^Azure$", cell, re.IGNORECASE):
                current_csp = "azure"
            elif re.match(r"^GCP$", cell, re.IGNORECASE):
                current_csp = "gcp"
            elif cell not in ("", "**Mitigation**", "**Description**",
                              "**Detection**", "**Detection of activities after exploitation**"):
                description_cells.append((current_csp, cell))
            i += 1

        for csp, desc in description_cells:
            # Clean markdown bold markers from text
            clean = re.sub(r"\*\*", "", desc).strip()
            if clean and not re.match(r"^-+$", clean):
                result[csp].append(clean)

    return result


def _extract_references(body: str) -> list[str]:
    """Extract numbered references list."""
    section = _extract_section(body, "References", [])
    refs = []
    for line in section.splitlines():
        line = line.strip()
        if line and re.match(r"^\d+\.", line):
            refs.append(line)
    return refs


def _keywords_from_title(title: str) -> list[str]:
    """Derive search keywords from technique title (lowercase words ≥4 chars)."""
    words = re.findall(r"[a-zA-Z]{4,}", title.lower())
    return list(dict.fromkeys(words))  # Unique, order-preserving


def _parse_entry(title_line: str, body: str) -> dict:
    """Parse one CAVEAT entry into a structured dict."""
    title, version = _parse_title(title_line)
    cloud_label = _extract_cloud_label(body)

    # Known section order in CAVEAT files
    _sections = ["Description", "Examples", "Mitigations", "Detection", "References"]

    description = _extract_section(body, "Description", _sections[1:])
    mit_raw = _extract_section(body, "Mitigations", _sections[3:])
    det_raw = _extract_section(body, "Detection", _sections[4:])

    mit_split = _split_csp_rows(mit_raw)
    det_split = _split_csp_rows(det_raw)

    return {
        "title": title,
        "version": version,
        "cloud_label": cloud_label,
        "description": description,
        "mitigations_aws": mit_split["aws"],
        "mitigations_azure": mit_split["azure"],
        "mitigations_gcp": mit_split["gcp"],
        "mitigations_generic": mit_split["generic"],
        "detection_aws": det_split["aws"],
        "detection_azure": det_split["azure"],
        "detection_gcp": det_split["gcp"],
        "detection_generic": det_split["generic"],
        "references": _extract_references(body),
        "keywords": _keywords_from_title(title),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_and_parse(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "caveat_techniques.yaml"

    log.info(f"Fetching CAVEAT all-entries from GitHub...")
    resp = requests.get(RAW_URL, timeout=60)
    resp.raise_for_status()
    raw = resp.text
    log.info(f"Downloaded {len(raw):,} bytes")

    entries_raw = _split_entries(raw)
    log.info(f"Found {len(entries_raw)} entries to parse")

    techniques = [_parse_entry(t, b) for t, b in entries_raw]

    # Backup existing file
    if out_path.exists():
        backup = out_path.with_suffix(".yaml.bak")
        backup.write_bytes(out_path.read_bytes())
        log.info(f"Backed up existing file to {backup}")

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            {"techniques": techniques, "source": RAW_URL, "count": len(techniques)},
            fh,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    log.info(f"Wrote {len(techniques)} CAVEAT techniques to {out_path}")

    # Quick sanity check
    with open(out_path, "r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    assert loaded["count"] == len(techniques), "Write/read count mismatch"
    log.info("Validation passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch CAVEAT threat data from CSA GitHub")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Directory for caveat_techniques.yaml output",
    )
    args = parser.parse_args()
    fetch_and_parse(Path(args.output_dir))


if __name__ == "__main__":
    main()
