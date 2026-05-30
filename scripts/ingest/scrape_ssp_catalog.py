"""
Scrapes the Singapore Government ICT&SS SSP control catalogs and writes JSON files to
chatbot/data/ssp/.

Produces three files:
  cybersecurity_catalog.json  — all controls from /control-catalog/cybersecurity/
  dss_catalog.json            — all controls from /control-catalog/dss/
  ssp_profiles.json           — which controls apply at which level per system profile

Usage:
  python scripts/ingest/scrape_ssp_catalog.py
  python scripts/ingest/scrape_ssp_catalog.py --output-dir path/to/ssp/

Run quarterly when the catalog is updated, or whenever new profiles are added.
"""

import json
import re
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Install missing deps: pip install requests beautifulsoup4")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE = "https://info.standards.tech.gov.sg"
CYBER_CATEGORIES = ["ac", "as", "br", "cs", "ck", "dp", "dc", "ga", "hr", "is", "lm", "ns", "pm", "rs", "sc", "sd", "st"]
DSS_CATEGORIES   = ["bd", "pr", "tx", "tl", "uu", "wo", "wp", "wr", "wu"]

SSP_PROFILES = {
    "low_risk_cloud":              "/ssp/low-risk-cloud/",
    "low_risk_onprem":             "/ssp/low-risk-on-premises/",
    "medium_risk_cloud":           "/ssp/medium-risk-cloud/",
    "high_risk_cloud_cii":         "/ssp/high-risk-cloud/",
    "generative_ai":               "/ssp/gen-ai/",
    "digital_services_others":     "/ssp/dss-others/",
    "digital_services_high_impact": "/ssp/dss-high/",
    "sandbox":                     "/ssp/sandbox/",
}

CATEGORY_NAMES = {
    # Cybersecurity
    "ac": "Access Control", "as": "Application Security", "br": "Backup and Recovery",
    "cs": "Container Security", "ck": "Cryptography, Encryption & Key Management",
    "dp": "Data Protection", "dc": "Datacentre", "ga": "Generative AI",
    "hr": "Human Resource", "is": "Infrastructure Security",
    "lm": "Logging and Monitoring", "ns": "Network Security",
    "pm": "Security Programme Management", "rs": "Resiliency",
    "sc": "Software Supply Chain", "sd": "Secure Development", "st": "Security Testing",
    # DSS
    "bd": "Baseline Design Practices", "pr": "Performance and Reliability",
    "tx": "Transactions and Payments", "tl": "Trust and Legitimacy",
    "uu": "Understand Users", "wo": "WCAG: Operable", "wp": "WCAG: Perceivable",
    "wr": "WCAG: Robust", "wu": "WCAG: Understandable",
}


def _get(url: str, session: requests.Session, retries: int = 3) -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            log.warning(f"Attempt {attempt+1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    log.error(f"Giving up on {url}")
    return None


def _text(el) -> str:
    return el.get_text(separator=" ", strip=True) if el else ""


def _parse_control_id(raw: str) -> str:
    """Normalise 'ac-1' or 'AC-1:' → 'AC-1'."""
    return raw.strip().upper().replace("_", "-").rstrip(":")


def _extract_parameters(soup_section) -> list:
    """Extract parameter metadata from a parameters table or list."""
    params = []
    if not soup_section:
        return params
    rows = soup_section.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            param_id = _text(cells[0])
            if not param_id or param_id.lower() in ("id", "parameter"):
                continue
            param_type = _text(cells[1]) if len(cells) > 1 else ""
            param_desc = _text(cells[2]) if len(cells) > 2 else ""
            params.append({"id": param_id, "type": param_type, "description": param_desc})
    return params


def _extract_references(soup_section) -> list:
    """Extract external references as text list."""
    if not soup_section:
        return []
    return [a.get_text(strip=True) for a in soup_section.find_all("a") if a.get_text(strip=True)]


def _scrape_category(catalog: str, code: str, session: requests.Session) -> list:
    """Scrape all controls from one category page."""
    url = urljoin(BASE, f"/control-catalog/{catalog}/{code}/")
    soup = _get(url, session)
    if not soup:
        return []

    controls = []
    category_name = CATEGORY_NAMES.get(code.lower(), code.upper())

    # Controls are typically in article/section blocks or definition lists.
    # Try multiple selectors in priority order.
    blocks = (
        soup.select("article.control, section.control, div.control") or
        soup.select("[id^='%s-']" % code.lower()) or
        soup.select("[id^='%s-']" % code.upper()) or
        []
    )

    if not blocks:
        # Fall back: look for heading tags h2/h3 that match pattern CODE-N
        pattern = re.compile(r'^' + re.escape(code.upper()) + r'-\d+', re.IGNORECASE)
        # Control h2 headings match pattern; h3 headings are section labels inside the block.
        # All siblings live inside the same parent <div>, so we only stop on h2 (not h3/h4).
        headings = soup.find_all("h2", string=pattern)
        for h in headings:
            control_id_raw = h.get_text(strip=True).split()[0]
            control_id = _parse_control_id(control_id_raw)
            title_parts = h.get_text(strip=True).split(None, 1)
            # Strip trailing colon from title prefix
            raw_title = title_parts[1] if len(title_parts) > 1 else ""
            title = raw_title.lstrip(": ").strip()

            # Walk siblings; h3 tags are section labels (Statement/Recommendations/Risk Statement)
            sibling = h.find_next_sibling()
            content: dict = {}
            current_key: str | None = None
            while sibling and sibling.name != "h2":
                if sibling.name in ("h3", "h4"):
                    ltext = sibling.get_text(strip=True).lower()
                    if "risk" in ltext:
                        current_key = "risk_statement"
                    elif "recommendation" in ltext:
                        current_key = "recommendation"
                    elif "statement" in ltext:
                        current_key = "statement"
                    elif "parameter" in ltext:
                        current_key = "parameters"
                    elif "reference" in ltext:
                        current_key = "references"
                    else:
                        current_key = None
                elif current_key and sibling.name not in ("table",):
                    existing = content.get(current_key, "")
                    content[current_key] = (existing + " " + _text(sibling)).strip()
                sibling = sibling.find_next_sibling()

            controls.append({
                "id": control_id,
                "catalog": catalog,
                "category": code.lower(),
                "category_name": category_name,
                "title": title,
                "statement": content.get("statement", ""),
                "recommendation": content.get("recommendation", ""),
                "risk_statement": content.get("risk_statement", ""),
                "parameters": [],
                "references": [],
            })
        log.info(f"  {catalog}/{code}: {len(controls)} controls (heading-based parse)")
        return controls

    # Block-based parse
    for block in blocks:
        raw_id = block.get("id", "") or ""
        if not raw_id:
            heading = block.find(["h2", "h3", "h4"])
            raw_id = heading.get_text(strip=True).split()[0] if heading else ""
        control_id = _parse_control_id(raw_id) if raw_id else ""
        if not control_id:
            continue

        def _field(label: str) -> str:
            el = block.find(string=re.compile(label, re.IGNORECASE))
            if el and el.parent:
                sib = el.parent.find_next_sibling()
                return _text(sib) if sib else ""
            return ""

        title_el = block.find(["h2", "h3", "h4"])
        title_text = _text(title_el) if title_el else ""
        # Strip leading control ID from title
        title = re.sub(r'^' + re.escape(control_id) + r'\s*[-—]?\s*', '', title_text, flags=re.IGNORECASE).strip()

        params_table = block.find("table", id=re.compile("param", re.IGNORECASE))
        refs_section = block.find(attrs={"class": re.compile("reference", re.IGNORECASE)})

        controls.append({
            "id": control_id,
            "catalog": catalog,
            "category": code.lower(),
            "category_name": category_name,
            "title": title,
            "statement": _field("statement"),
            "recommendation": _field("recommendation"),
            "risk_statement": _field("risk"),
            "parameters": _extract_parameters(params_table),
            "references": _extract_references(refs_section),
        })

    log.info(f"  {catalog}/{code}: {len(controls)} controls")
    return controls


def _scrape_ssp_profiles(session: requests.Session) -> dict:
    """
    Returns {profile_name: {control_id: level (0|1|2)}} for all 8 profiles.
    Level 0 = cardinal/mandatory, 1 = basic hygiene, 2 = best practice.

    Each SSP profile page lists controls as <h3>XX-N: Title</h3> blocks.
    The level for each control is given by a <p><b>Profile Level:</b>N</p>
    tag that appears in the siblings after the h3 heading.
    """
    profiles = {}
    control_pat = re.compile(r'^([A-Z]{2}-\d+)', re.IGNORECASE)
    level_pat = re.compile(r'Profile Level:\s*(\d+)', re.IGNORECASE)

    for profile_name, path in SSP_PROFILES.items():
        url = urljoin(BASE, path)
        soup = _get(url, session)
        if not soup:
            profiles[profile_name] = {}
            continue

        profile_controls = {}

        # Each control is introduced by an <h3> heading like "SC-2: Dependency Management".
        # Walk forward from each h3 until the next h3, searching for "Profile Level: N".
        for h3 in soup.find_all("h3"):
            m = control_pat.match(h3.get_text(strip=True))
            if not m:
                continue
            control_id = m.group(1).upper()
            sibling = h3.find_next_sibling()
            while sibling and sibling.name != "h3":
                lm = level_pat.search(sibling.get_text(strip=True))
                if lm:
                    profile_controls[control_id] = int(lm.group(1))
                    break
                sibling = sibling.find_next_sibling()

        profiles[profile_name] = profile_controls
        log.info(f"  {profile_name}: {len(profile_controls)} controls mapped")

    return profiles


def _build_profile_index(profiles: dict) -> dict:
    """
    Invert profiles dict to: {control_id: {profile_name: level}} for easy lookup.
    """
    index = {}
    for profile_name, controls in profiles.items():
        for control_id, level in controls.items():
            index.setdefault(control_id, {})[profile_name] = level
    return index


def main():
    parser = argparse.ArgumentParser(description="Scrape Singapore SSP control catalogs")
    parser.add_argument("--output-dir", default="chatbot/data/ssp",
                        help="Directory to write JSON files (default: chatbot/data/ssp)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Seconds between requests (default: 0.5)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # --- Scrape cybersecurity catalog ---
    log.info("Scraping cybersecurity catalog...")
    cyber_controls = []
    for code in CYBER_CATEGORIES:
        cyber_controls.extend(_scrape_category("cybersecurity", code, session))
        time.sleep(args.delay)

    # --- Scrape DSS catalog ---
    log.info("Scraping DSS catalog...")
    dss_controls = []
    for code in DSS_CATEGORIES:
        dss_controls.extend(_scrape_category("dss", code, session))
        time.sleep(args.delay)

    # --- Scrape SSP profiles ---
    log.info("Scraping SSP profiles...")
    raw_profiles = _scrape_ssp_profiles(session)
    profile_index = _build_profile_index(raw_profiles)

    # --- Write outputs ---
    cyber_path = out_dir / "cybersecurity_catalog.json"
    dss_path   = out_dir / "dss_catalog.json"
    ssp_path   = out_dir / "ssp_profiles.json"

    cyber_path.write_text(json.dumps(cyber_controls, indent=2, ensure_ascii=False))
    dss_path.write_text(json.dumps(dss_controls, indent=2, ensure_ascii=False))
    ssp_path.write_text(json.dumps(profile_index, indent=2, ensure_ascii=False))

    log.info(f"Wrote {len(cyber_controls)} cybersecurity controls → {cyber_path}")
    log.info(f"Wrote {len(dss_controls)} DSS controls → {dss_path}")
    log.info(f"Wrote profile index for {len(profile_index)} controls → {ssp_path}")

    if len(cyber_controls) < 50:
        log.warning("Cybersecurity control count is low — page structure may have changed, review output")


if __name__ == "__main__":
    main()
