"""
Shared per-control effort and cost benchmarks.

Used by threat_report.py (action plan table) and moe_orchestrator.py
(investment tier aggregation). One canonical source of truth.

Sources cited per tier:
  Config-only    — CIS Controls v8 IG1; NIST SP 800-53 Rev 5 (CM/AC families)
  Tool deploy    — Gartner Market Guide for Security Tools (2025);
                   SANS Security Spending Survey (2025)
  Process/prog   — NIST SP 800-53 Rev 5 (CA/RA/AT families); CIS Controls v8 IG2
  Architecture   — NIST SP 800-207 (Zero Trust); CIS Controls v8 IG3;
                   Gartner Security Architecture Guide (2025)
  AI/ML          — NIST AI RMF 1.0; OWASP LLM Top 10 (2025)
"""

import re
from typing import Dict, List, Optional, Tuple

# (effort_label, cost_low_k, cost_high_k)
# cost_low/high are USD thousands (int) for arithmetic aggregation.
# effort_rank is used to find the critical-path bottleneck across controls.

_EFFORT_RANK = {
    "2–4 hours":  1,
    "4–8 hours":  2,
    "1–2 days":   3,
    "2–3 days":   4,
    "3–5 days":   5,
    "1–2 weeks":  6,
    "2–3 weeks":  7,
    "2–4 weeks":  8,
}

# (effort_label, cost_low_usd_k, cost_high_usd_k)
CONTROL_BENCHMARK: Dict[str, Tuple[str, int, int]] = {
    # ── Config-only ──────────────────────────────────────────────────────────
    "mfa":                            ("2–4 hours",   0.5,   1),
    "logging":                        ("2–4 hours",   0.2, 0.5),
    "rate limiting":                  ("2–4 hours",   0.2, 0.5),
    "ip blocking":                    ("2–4 hours",   0.2, 0.5),
    "bucket policy":                  ("2–4 hours",   0.2, 0.5),
    "disable unnecessary features":   ("2–4 hours",   0.2, 0.5),
    "least privilege":                ("4–8 hours",   0.5,   1),
    "input validation":               ("4–8 hours",   0.5,   1),
    "encryption":                     ("4–8 hours",   0.5,   1),
    "encryption in transit":          ("4–8 hours",   0.5,   1),
    "tls inspection":                 ("4–8 hours",   0.5,   1),
    "file system permissions":        ("4–8 hours",   0.5,   1),
    "session management":             ("4–8 hours",   0.5,   1),
    # ── Tool deployment ──────────────────────────────────────────────────────
    "waf":                            ("1–2 days",      1,   3),
    "firewall":                       ("1–2 days",      1,   3),
    "ids/ips":                        ("1–2 days",      2,   5),
    "edr":                            ("1–2 days",      2,   5),
    "web content filtering":          ("1–2 days",      1,   3),
    "network monitoring":             ("1–2 days",      1,   3),
    "file integrity monitoring":      ("1–2 days",      1,   3),
    "fim":                            ("1–2 days",      1,   3),
    "email gateway":                  ("1–2 days",      1,   3),
    "backup":                         ("1–2 days",      1,   3),
    "monitoring":                     ("1–2 days",      1,   3),
    "reverse proxy":                  ("2–3 days",      2,   5),
    "secrets management":             ("2–3 days",      2,   5),
    "sandbox":                        ("2–3 days",      2,   5),
    "behavioral analysis":            ("2–3 days",      3,   8),
    "ueba":                           ("2–3 days",      3,   8),
    "dlp":                            ("2–3 days",      3,   8),
    "iam":                            ("2–3 days",      3,   8),
    "siem":                           ("2–3 days",      5,  10),
    "privileged access management":   ("3–5 days",      5,  15),
    "pam":                            ("3–5 days",      5,  15),
    "rasp":                           ("2–3 days",      3,   8),
    "application sandboxing":         ("2–3 days",      3,   8),
    # ── Process / programme ──────────────────────────────────────────────────
    "patching":                       ("2–3 days",      3,   5),
    "vulnerability scanning":         ("2–3 days",      3,   5),
    "code signing":                   ("2–3 days",      3,   5),
    "container scanning":             ("2–3 days",      3,   5),
    "operating system configuration": ("3–5 days",      3,   8),
    "sbom":                           ("3–5 days",      5,  10),
    "user training":                  ("1–2 weeks",     5,  15),
    "phishing simulation":            ("1–2 weeks",     5,  15),
    "data classification":            ("1–2 weeks",     5,  15),
    "pre-compromise security":        ("1–2 weeks",     5,  15),
    # ── Architecture changes ─────────────────────────────────────────────────
    "api access control":             ("3–5 days",      3,   8),
    "capability based access control":("3–5 days",      3,   8),
    "vpn":                            ("3–5 days",      5,  10),
    "cdn":                            ("3–5 days",      3,   8),
    "ddos protection":                ("3–5 days",      3,   8),
    "load balancer":                  ("3–5 days",      3,   8),
    "user account management":        ("3–5 days",      3,   8),
    "prompt sanitization":            ("3–5 days",      5,  10),
    "output filtering":               ("3–5 days",      5,  10),
    "llm output filtering":           ("3–5 days",      5,  10),
    "prompt injection filter":        ("3–5 days",      5,  10),
    "service mesh":                   ("1–2 weeks",    10,  20),
    "network segmentation":           ("1–2 weeks",    10,  30),
    "rag content validation":         ("1–2 weeks",     5,  10),
    "zero trust":                     ("2–4 weeks",    20,  50),
    # ── AI / ML ──────────────────────────────────────────────────────────────
    "training data integrity checks": ("1–2 weeks",     5,  15),
    "runtime application":            ("2–3 days",      3,   8),
}

_CITATION = (
    "Benchmark estimate — CIS Controls v8 IG1–IG3 / NIST SP 800-53 Rev 5 / "
    "Gartner Market Guide for Security Tools (2025) / SANS Security Spending Survey (2025) / "
    "NIST AI RMF 1.0 / OWASP LLM Top 10 (2025)"
)

# Canonical public URLs for each benchmark source.
# Gartner and SANS require subscriptions — URLs point to public landing pages.
_SOURCES = {
    "CIS Controls v8":       "https://www.cisecurity.org/controls/v8",
    "NIST SP 800-53 Rev 5":  "https://doi.org/10.6028/NIST.SP.800-53r5",
    "NIST SP 800-207":       "https://doi.org/10.6028/NIST.SP.800-207",
    "NIST AI RMF 1.0":       "https://doi.org/10.6028/NIST.AI.100-1",
    "OWASP LLM Top 10 2025": "https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/",
    "Gartner Market Guide":  "https://www.gartner.com/en/documents/market-guide-for-security-tools",
    "SANS Security Survey":  "https://www.sans.org/white-papers/",
}


def lookup(control_name: str) -> Optional[Tuple[str, int, int]]:
    """Return (effort_label, cost_low_k, cost_high_k) or None if no match."""
    key = control_name.lower().strip().replace("_", " ")
    entry = CONTROL_BENCHMARK.get(key)
    if entry:
        return entry
    for k, v in CONTROL_BENCHMARK.items():
        if k in key or key in k:
            return v
    return None


def _cost_str(low_k: float, high_k: float) -> str:
    def _fmt(k):
        if k >= 1000:
            return f"${int(k/1000)}M"
        if k >= 1:
            return f"${int(k)}K"
        return f"${int(k*1000)}"
    return f"{_fmt(low_k)}–{_fmt(high_k)}"


def aggregate_tier(item_strings: List[str]) -> Dict:
    """
    Given a list of tier item strings (e.g. "MFA enforcement at Users…"),
    extract control names, look each up in the benchmark table, then return:
      effort  — label of the highest-rank (longest calendar) control
      cost    — summed low–high range across matched controls
      source  — citation string
      matched — list of (control_name, effort, cost_str) tuples for transparency
      unmatched_count — number of items with no benchmark entry
    """
    total_low:  float = 0.0
    total_high: float = 0.0
    best_rank:  int   = 0
    best_effort: str  = ""
    matched = []
    unmatched = 0

    for item in item_strings:
        hit = _match_item(item)
        if hit:
            ctrl_name, effort, low_k, high_k = hit
            total_low  += low_k
            total_high += high_k
            rank = _EFFORT_RANK.get(effort, 0)
            if rank > best_rank:
                best_rank   = rank
                best_effort = effort
            matched.append((ctrl_name, effort, _cost_str(low_k, high_k)))
        else:
            unmatched += 1

    if not matched:
        return {
            "effort": "not estimated",
            "cost":   "cost not estimated",
            "cost_source": "not_available",
            "matched_controls": [],
            "unmatched_count": unmatched,
        }

    return {
        "effort":      best_effort,
        "cost":        _cost_str(total_low, total_high),
        "cost_source": "benchmark",
        "citation":    _CITATION,
        "sources":     _SOURCES,
        "matched_controls": matched,
        "unmatched_count":  unmatched,
    }


def _match_item(item_str: str) -> Optional[Tuple[str, str, float, float]]:
    """
    Extract the control name from a tier item string and look it up.
    Item strings are typically "Control Name at Node — traces to: …"
    """
    # Strip node/path annotations — take only the part before " at " or " — "
    clean = re.split(r'\s+(?:at |—|with )', item_str, maxsplit=1)[0].strip()
    # Also try the full string for partial matches
    for candidate in [clean, item_str]:
        result = lookup(candidate)
        if result:
            return (clean, result[0], result[1], result[2])
    return None
