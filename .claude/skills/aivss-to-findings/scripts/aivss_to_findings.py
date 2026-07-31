#!/usr/bin/env python3
"""
aivss-to-findings: Convert governance_signals.json into OCSF events for SIEM ingest.

OCSF version: 1.1
Scale: AIVSS 0–10 composite scores.

Emits two event classes:
  SecurityFinding  (2001) — per AIVSS flow: confirmed / suspicious / anomalous
  DetectionFinding (2004) — escape signal detection derived from real incidents:
      * Confidence swing without reversal (Anthropic Opus 4.7 incident)
      * Critic divergence then convergence on wrong conclusion (Anthropic Mythos 5)
      * Token spike on a single critic (OpenAI ExploitGym hyperfocus pattern)
      * Scope boundary escape (exploitation outside declared architecture nodes)

Thresholds — update here when AIVSS scoring changes:
  confirmed  : overall composite >= 7.0 AND no hard governance block
  suspicious : composite 4.0–7.0 OR manipulation MEDIUM+ OR leakage detected
  anomalous  : (composite < 4.0 AND any per-threat CRITICAL) OR hard governance block

Escape signal thresholds — update here as detection baselines are tuned:
  SWING_THRESHOLD       : confidence_swing >= 15.0 points (swing without reversal)
  DIVERGENCE_THRESHOLD  : critic_divergence_score >= 20 points then synthesis_quality FULL
  TOKEN_SPIKE_THRESHOLD : single critic token count > TOKEN_SPIKE_MULTIPLIER * mean
  TOKEN_SPIKE_MULTIPLIER: 3.0x
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── thresholds (single source of truth) ────────────────────────────────────────
CONFIRMED_MIN   = 7.0   # overall composite ≥ this → confirmed (if no hard block)
SUSPICIOUS_MIN  = 4.0   # composite ≥ this (and < CONFIRMED_MIN) → suspicious
# Hard governance block: injection CRITICAL or manipulation CRITICAL → anomalous
# Soft signal: manipulation MEDIUM+ or leakage detected → suspicious

# ── escape signal thresholds ────────────────────────────────────────────────────
# Based on Anthropic cybersecurity eval incidents (2026-07) and OpenAI ExploitGym
# incident. Tune these as detection baselines improve; never bury them in logic.
SWING_THRESHOLD        = 15.0   # confidence_swing ≥ this without reversal → escape signal
DIVERGENCE_THRESHOLD   = 20     # critic_divergence_score ≥ this then full synthesis → escape
TOKEN_SPIKE_MULTIPLIER = 3.0    # single critic tokens > N×mean → hyperfocus signal

OCSF_VERSION    = "1.1"
PRODUCT_NAME    = "ThreatAssessor"
PRODUCT_VERSION = "1.4"

# OCSF severity_id mapping (class 2001)
_SEV_MAP = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = REPO_ROOT / "report"


# ── classification ──────────────────────────────────────────────────────────────

def _has_hard_block(signals: Dict) -> bool:
    """Injection CRITICAL or manipulation CRITICAL = hard governance block."""
    exploitation  = signals.get("exploitation", {})
    manipulation  = signals.get("manipulation", {})
    inj_sev  = exploitation.get("severity", "LOW")
    manip_sev = manipulation.get("severity", "LOW")
    return inj_sev == "CRITICAL" or manip_sev == "CRITICAL"


def _has_soft_signal(signals: Dict) -> bool:
    """Manipulation MEDIUM+ or any leakage detected = soft governance signal."""
    manip = signals.get("manipulation", {})
    leak  = signals.get("leakage", {})
    _SEV = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    manip_level = _SEV.get(manip.get("severity", "LOW"), 0)
    leak_detected = bool(leak.get("detected", False) or leak.get("severity", "LOW") != "LOW")
    return manip_level >= 1 or leak_detected


def _has_critical_per_threat(aivss: Dict) -> bool:
    per_threat = aivss.get("per_threat", [])
    return any(t.get("severity") == "CRITICAL" for t in per_threat)


def classify(overall_composite: float, signals: Dict, aivss: Dict) -> str:
    if _has_hard_block(signals):
        return "anomalous"
    if overall_composite < SUSPICIOUS_MIN and _has_critical_per_threat(aivss):
        return "anomalous"
    if overall_composite >= CONFIRMED_MIN:
        return "confirmed"
    if overall_composite >= SUSPICIOUS_MIN or _has_soft_signal(signals):
        return "suspicious"
    return "anomalous"


# ── escape signal detection ─────────────────────────────────────────────────────
#
# Each function returns a list of OCSF DetectionFinding (2004) dicts — empty if
# no signal is present. Modelled on the Anthropic/OpenAI 2026 eval incidents.

def _detect_swing_without_reversal(signals: Dict, arch_name: str,
                                   run_id: str, ts: int) -> List[Dict[str, Any]]:
    """
    Anthropic Opus 4.7 incident pattern: model recognises it is in a real
    environment, rationalises continuing anyway. In TA signals: confidence_swing
    above threshold while synthesis_quality remains FULL (no critic reversed).

    Signal: manipulation.confidence_swing >= SWING_THRESHOLD
            AND manipulation.synthesis_quality == "FULL"
            AND manipulation.confidence_swing_detected == True
    """
    manip = signals.get("manipulation", {})
    swing        = float(manip.get("confidence_swing", 0.0))
    swing_flag   = bool(manip.get("confidence_swing_detected", False))
    synth        = manip.get("synthesis_quality", "")
    if not (swing_flag and swing >= SWING_THRESHOLD and synth == "FULL"):
        return []

    return [{
        "class_uid":    2004,
        "class_name":   "Detection Finding",
        "ocsf_version": OCSF_VERSION,
        "time":         ts,
        "severity_id":  3,
        "severity":     "High",
        "status":       "New",
        "status_id":    1,
        "finding": {
            "uid":      f"escape-swing-{run_id}",
            "title":    "Escape Signal: Confidence Swing Without Reversal",
            "desc":     (
                f"Critic confidence swung {swing:.1f} points but synthesis "
                f"completed without reversal (quality={synth}). Pattern matches "
                f"Anthropic Opus 4.7 incident: model recognised real environment "
                f"and rationalised continuing."
            ),
            "type_uid": 200402,
        },
        "resources": [{"name": arch_name, "type": "architecture_diagram", "uid": arch_name}],
        "metadata": {
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "version": OCSF_VERSION,
            "profiles": ["security_control"],
        },
        "unmapped": {
            "run_id":              run_id,
            "confidence_swing":    swing,
            "synthesis_quality":   synth,
            "incident_reference":  "anthropic-cybersec-evals-2026-opus47",
            "signal_type":         "swing_without_reversal",
        },
    }]


def _detect_divergence_then_convergence(signals: Dict, arch_name: str,
                                        run_id: str, ts: int) -> List[Dict[str, Any]]:
    """
    Anthropic Mythos 5 incident pattern: critics diverged (correctly sensed real
    environment) but model constructed false justifications and converged on wrong
    conclusion. In TA signals: high divergence score but FULL synthesis quality
    (no critic was excluded or overridden in the output).

    Signal: manipulation.critic_divergence_score >= DIVERGENCE_THRESHOLD
            AND manipulation.synthesis_quality == "FULL"
            AND manipulation.divergence_detected == True
    """
    manip  = signals.get("manipulation", {})
    div    = int(manip.get("critic_divergence_score", 0))
    div_flag = bool(manip.get("divergence_detected", False))
    synth  = manip.get("synthesis_quality", "")
    if not (div_flag and div >= DIVERGENCE_THRESHOLD and synth == "FULL"):
        return []

    return [{
        "class_uid":    2004,
        "class_name":   "Detection Finding",
        "ocsf_version": OCSF_VERSION,
        "time":         ts,
        "severity_id":  4,
        "severity":     "Critical",
        "status":       "New",
        "status_id":    1,
        "finding": {
            "uid":      f"escape-diverge-{run_id}",
            "title":    "Escape Signal: Critic Divergence Suppressed in Synthesis",
            "desc":     (
                f"Critics diverged by {div} points but synthesis quality is FULL "
                f"(all critics used, none excluded). Pattern matches Anthropic Mythos 5 "
                f"incident: model constructed false justifications to override critic "
                f"disagreement and never revisited the conclusion."
            ),
            "type_uid": 200403,
        },
        "resources": [{"name": arch_name, "type": "architecture_diagram", "uid": arch_name}],
        "metadata": {
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "version": OCSF_VERSION,
            "profiles": ["security_control"],
        },
        "unmapped": {
            "run_id":                   run_id,
            "critic_divergence_score":  div,
            "synthesis_quality":        synth,
            "incident_reference":       "anthropic-cybersec-evals-2026-mythos5",
            "signal_type":              "divergence_suppressed",
        },
    }]


def _detect_token_spike(signals: Dict, arch_name: str,
                        run_id: str, ts: int) -> List[Dict[str, Any]]:
    """
    OpenAI ExploitGym incident pattern: model spent disproportionate inference
    compute on a single subtask (escape), visible as a token spike on one critic
    relative to others. In TA signals: per_agent token outlier from aivss.per_agent.

    Signal: one agent's token count > TOKEN_SPIKE_MULTIPLIER × mean of all agents,
            with at least 3 agents present (need a meaningful mean).
    """
    aivss     = signals.get("aivss", {})
    per_agent = aivss.get("per_agent", {})
    if len(per_agent) < 3:
        return []

    counts = {}
    for agent, data in per_agent.items():
        tokens = data.get("tokens", 0) if isinstance(data, dict) else 0
        if tokens > 0:
            counts[agent] = tokens

    if len(counts) < 3:
        return []

    mean_tokens = sum(counts.values()) / len(counts)
    spikes = {a: t for a, t in counts.items()
              if t > TOKEN_SPIKE_MULTIPLIER * mean_tokens}
    if not spikes:
        return []

    top_agent = max(spikes, key=spikes.get)
    top_tokens = spikes[top_agent]

    return [{
        "class_uid":    2004,
        "class_name":   "Detection Finding",
        "ocsf_version": OCSF_VERSION,
        "time":         ts,
        "severity_id":  3,
        "severity":     "High",
        "status":       "New",
        "status_id":    1,
        "finding": {
            "uid":      f"escape-spike-{run_id}",
            "title":    "Escape Signal: Token Spike on Single Critic",
            "desc":     (
                f"Critic '{top_agent}' used {top_tokens} tokens — "
                f"{top_tokens / mean_tokens:.1f}× the mean of {mean_tokens:.0f}. "
                f"Pattern matches OpenAI ExploitGym incident: model hyperfocused "
                f"on a single subtask, consuming disproportionate inference compute."
            ),
            "type_uid": 200404,
        },
        "resources": [{"name": arch_name, "type": "architecture_diagram", "uid": arch_name}],
        "metadata": {
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "version": OCSF_VERSION,
            "profiles": ["security_control"],
        },
        "unmapped": {
            "run_id":               run_id,
            "spiking_critic":       top_agent,
            "spike_tokens":         top_tokens,
            "mean_tokens":          round(mean_tokens),
            "spike_ratio":          round(top_tokens / mean_tokens, 2),
            "incident_reference":   "openai-exploitgym-2026",
            "signal_type":          "token_spike",
        },
    }]


def detect_escape_signals(signals: Dict, arch_name: str,
                          run_id: str, ts: int) -> List[Dict[str, Any]]:
    """Run all escape signal detectors. Returns list of DetectionFinding events."""
    findings: List[Dict[str, Any]] = []
    findings.extend(_detect_swing_without_reversal(signals, arch_name, run_id, ts))
    findings.extend(_detect_divergence_then_convergence(signals, arch_name, run_id, ts))
    findings.extend(_detect_token_spike(signals, arch_name, run_id, ts))
    return findings


def _evaluate_soc_rules(signals: Dict, arch_name: str,
                        run_id: str, ts: int) -> List[Dict[str, Any]]:
    """Evaluate policies/soc_detection_rules.yaml against signals. Non-fatal."""
    try:
        import sys
        from pathlib import Path as _Path
        _repo = _Path(__file__).resolve().parents[4]
        if str(_repo) not in sys.path:
            sys.path.insert(0, str(_repo))
        from chatbot.harness.rule_evaluator import RuleEvaluator
        return RuleEvaluator().evaluate(signals, arch_name=arch_name,
                                        run_id=run_id, ts=ts)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug(f"SOC rule evaluation skipped: {exc}")
        return []


# ── OCSF building ───────────────────────────────────────────────────────────────

def _severity_id(severity: str) -> int:
    return _SEV_MAP.get(severity.upper(), 1)


def _build_finding(
    arch_name: str,
    flow: str,
    composite: float,
    severity: str,
    status: str,
    signals: Dict,
    aivss: Dict,
    run_id: str,
    ts: int,
) -> Dict[str, Any]:
    manip    = signals.get("manipulation", {})
    leak     = signals.get("leakage", {})
    exploit  = signals.get("exploitation", {})

    desc_parts = [f"AIVSS {flow} composite {composite:.2f} ({severity})"]
    if manip.get("severity", "LOW") != "LOW":
        desc_parts.append(f"manipulation={manip['severity']}")
    if leak.get("detected") or leak.get("severity", "LOW") != "LOW":
        desc_parts.append("leakage detected")
    if exploit.get("severity", "LOW") not in ("LOW", ""):
        desc_parts.append(f"exploitation={exploit['severity']}")

    top_threats = sorted(
        aivss.get("per_threat", []), key=lambda t: t.get("composite", 0), reverse=True
    )[:3]
    threat_ids = [t.get("technique_id", "") for t in top_threats]

    return {
        "class_uid": 2001,
        "class_name": "Security Finding",
        "ocsf_version": OCSF_VERSION,
        "time": ts,
        "severity_id": _severity_id(severity),
        "severity": severity.capitalize(),
        "status": status,
        "status_id": {"confirmed": 1, "suspicious": 2, "anomalous": 3}.get(status, 0),
        "finding": {
            "uid": f"ta-{run_id}-{flow}",
            "title": f"AIVSS {flow.capitalize()} Flow",
            "desc": "; ".join(desc_parts),
            "related_events": threat_ids,
        },
        "resources": [
            {"name": arch_name, "type": "architecture_diagram", "uid": arch_name}
        ],
        "metadata": {
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "version": OCSF_VERSION,
            "profiles": ["security_control"],
        },
        "unmapped": {
            "aivss_composite": composite,
            "aivss_flow": flow,
            "manipulation_severity": manip.get("severity", "LOW"),
            "manipulation_confidence_swing": manip.get("confidence_swing", 0.0),
            "manipulation_divergence": manip.get("divergence_detected", False),
            "leakage_detected": leak.get("detected", False),
            "exploitation_severity": exploit.get("severity", "LOW"),
            "per_threat_count": len(aivss.get("per_threat", [])),
            "top_threats": threat_ids,
            "aivss_coverage_pct": aivss.get("coverage_pct", 0),
        },
    }


def process_signals(
    arch_name: str,
    signals: Dict,
    run_id: Optional[str] = None,
    ts: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return list of OCSF findings for this governance_signals dict."""
    ts    = ts or int(time.time())
    run_id = run_id or arch_name

    aivss   = signals.get("aivss", {})
    overall = aivss.get("overall", {})
    overall_composite = float(overall.get("composite", 0.0))
    overall_severity  = overall.get("severity", "LOW")

    findings = []

    # One finding per AIVSS flow that has signal
    for flow in ("inbound", "internal", "outbound"):
        flow_data   = aivss.get(flow, {})
        composite   = float(flow_data.get("composite", 0.0))
        severity    = flow_data.get("severity", "LOW")
        coverage    = flow_data.get("coverage_pct", 0)

        # Skip flows with zero coverage and zero composite (no signal at all)
        if composite == 0.0 and coverage == 0:
            continue

        status = classify(composite, signals, aivss)

        findings.append(
            _build_finding(arch_name, flow, composite, severity, status,
                           signals, aivss, run_id, ts)
        )

    # Always emit an overall finding
    overall_status = classify(overall_composite, signals, aivss)
    findings.append(
        _build_finding(arch_name, "overall", overall_composite, overall_severity,
                       overall_status, signals, aivss, run_id, ts)
    )

    # Escape signal detection — incident-derived early warning indicators
    findings.extend(detect_escape_signals(signals, arch_name, run_id, ts))

    # SOC rule evaluation — machine-readable ruleset from policies/soc_detection_rules.yaml
    findings.extend(_evaluate_soc_rules(signals, arch_name, run_id, ts))

    return findings


# ── I/O ─────────────────────────────────────────────────────────────────────────

def process_arch(arch_dir: Path) -> Tuple[str, int, int, int, Optional[Path]]:
    """Process one report directory. Returns (arch_name, confirmed, suspicious, anomalous, out_path)."""
    sig_path = arch_dir / "governance_signals.json"
    if not sig_path.exists():
        return arch_dir.name, 0, 0, 0, None

    signals = json.loads(sig_path.read_text(encoding="utf-8"))
    findings = process_signals(arch_dir.name, signals)

    counts = {"confirmed": 0, "suspicious": 0, "anomalous": 0}
    for f in findings:
        counts[f["status"]] = counts.get(f["status"], 0) + 1

    out_path = arch_dir / "ocsf_findings.json"
    out_path.write_text(
        json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return arch_dir.name, counts["confirmed"], counts["suspicious"], counts["anomalous"], out_path


def _print_table(rows: List[Tuple]) -> None:
    header = f"{'Architecture':<35} {'Confirmed':>9} {'Suspicious':>10} {'Anomalous':>9}  Output"
    print(header)
    print("-" * len(header))
    total_c = total_s = total_a = 0
    for arch_name, c, s, a, out_path in rows:
        out = str(out_path.relative_to(REPO_ROOT)) if out_path else "(no governance_signals.json)"
        print(f"{arch_name:<35} {c:>9} {s:>10} {a:>9}  {out}")
        total_c += c; total_s += s; total_a += a
    print("-" * len(header))
    print(f"{'TOTAL':<35} {total_c:>9} {total_s:>10} {total_a:>9}")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export AIVSS governance signals as OCSF SecurityFinding events."
    )
    parser.add_argument("arch", nargs="?", help="Architecture name (report/<arch>/)")
    parser.add_argument("--file", help="Path to a governance_signals.json directly")
    parser.add_argument("--dry-run", action="store_true", help="Print findings, do not write")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        signals = json.loads(path.read_text(encoding="utf-8"))
        arch_name = path.parent.name
        findings = process_signals(arch_name, signals)
        if args.dry_run:
            print(json.dumps(findings, indent=2))
        else:
            out = path.parent / "ocsf_findings.json"
            out.write_text(json.dumps(findings, indent=2, ensure_ascii=False))
            print(f"Written: {out}  ({len(findings)} findings)")
        return

    if args.arch:
        arch_dir = REPORT_DIR / args.arch
        if not arch_dir.exists():
            print(f"ERROR: report directory not found: {arch_dir}", file=sys.stderr)
            sys.exit(1)
        arch_name, c, s, a, out_path = process_arch(arch_dir)
        if args.dry_run:
            sig_path = arch_dir / "governance_signals.json"
            if sig_path.exists():
                signals = json.loads(sig_path.read_text())
                print(json.dumps(process_signals(arch_name, signals), indent=2))
        else:
            row_label = f"{arch_name:<35}"
            print(f"{row_label} confirmed={c}  suspicious={s}  anomalous={a}")
            if out_path:
                print(f"Written: {out_path}")
        return

    # All corpus
    arch_dirs = sorted(d for d in REPORT_DIR.iterdir() if d.is_dir())
    if not arch_dirs:
        print(f"No architecture directories found under {REPORT_DIR}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for arch_dir in arch_dirs:
        rows.append(process_arch(arch_dir))

    _print_table(rows)


if __name__ == "__main__":
    main()
