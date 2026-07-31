#!/usr/bin/env python3
"""
langfuse-to-ocsf: Fetch ThreatAssessor pipeline traces from Langfuse and export
as OCSF v1.1 events for SIEM ingest.

OCSF version: 1.1
Langfuse SDK: 4.x (tested 4.14.0)

Class mapping (single source of truth — update here on SDK or OCSF version bumps):
  Trace              → ProcessActivity (1007)
  Span               → ProcessActivity (1007)
  Generation (LLM)   → APIActivity     (6003)
  Score (AIVSS)      → SecurityFinding (2001)
  Governance dim     → DetectionFinding (2004)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

OCSF_VERSION    = "1.1"
PRODUCT_NAME    = "ThreatAssessor"
PRODUCT_VERSION = "1.4"
DEFAULT_LIMIT   = 50

# ── OCSF severity mapping ────────────────────────────────────────────────────

_SEV_LABEL = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

def _sev_id(label: str) -> int:
    return _SEV_LABEL.get((label or "LOW").upper(), 1)

def _sev_from_score(score: float) -> tuple:
    """Map AIVSS 0-10 composite to (severity_label, severity_id)."""
    if score >= 9.0:   return "Critical", 4
    if score >= 7.0:   return "High",     3
    if score >= 4.0:   return "Medium",   2
    return "Low", 1


# ── OCSF metadata block ──────────────────────────────────────────────────────

def _metadata(profiles: Optional[List[str]] = None) -> Dict:
    return {
        "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
        "version": OCSF_VERSION,
        "profiles": profiles or ["network_activity"],
    }

def _actor() -> Dict:
    return {"process": {"name": PRODUCT_NAME}}


# ── timestamp helpers ────────────────────────────────────────────────────────

def _epoch(dt_val) -> int:
    if dt_val is None:
        return 0
    if isinstance(dt_val, (int, float)):
        return int(dt_val)
    if isinstance(dt_val, str):
        try:
            dt_val = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
        except ValueError:
            return 0
    if hasattr(dt_val, "timestamp"):
        return int(dt_val.timestamp())
    return 0

def _duration_ms(start, end) -> int:
    s, e = _epoch(start), _epoch(end)
    if s and e and e > s:
        return (e - s) * 1000
    return 0


# ── Trace → ProcessActivity (1007) ───────────────────────────────────────────

def trace_to_ocsf(trace) -> Dict[str, Any]:
    """
    Langfuse Trace → OCSF ProcessActivity (class_uid 1007).
    One event per pipeline run.
    """
    meta   = getattr(trace, "metadata", {}) or {}
    output = getattr(trace, "output", {}) or {}
    ts     = _epoch(getattr(trace, "timestamp", None))
    end_ts = _epoch(getattr(trace, "updated_at", None) or getattr(trace, "createdAt", None))

    arch       = meta.get("architecture", "") or getattr(trace, "name", "")
    confidence = output.get("confidence") if isinstance(output, dict) else None
    errors     = output.get("errors", []) if isinstance(output, dict) else []

    status    = "Success" if not errors else "Failure"
    status_id = 1 if not errors else 2

    return {
        "class_uid":     1007,
        "class_name":    "Process Activity",
        "ocsf_version":  OCSF_VERSION,
        "activity_id":   1,
        "activity_name": "Launch",
        "time":          ts,
        "duration":      _duration_ms(ts, end_ts),
        "severity_id":   1,
        "severity":      "Informational",
        "status":        status,
        "status_id":     status_id,
        "actor":         _actor(),
        "process": {
            "name":    PRODUCT_NAME,
            "pid":     0,
            "cmd_line": f"analyze {arch}",
        },
        "metadata": _metadata(["process_activity"]),
        "unmapped": {
            "trace_id":    getattr(trace, "id", ""),
            "architecture": arch,
            "scenario":    meta.get("scenario", ""),
            "confidence":  confidence,
            "errors":      errors,
            "run_id":      getattr(trace, "id", ""),
        },
    }


# ── Span → ProcessActivity (1007) ────────────────────────────────────────────

def span_to_ocsf(obs, trace_id: str) -> Dict[str, Any]:
    """
    Langfuse Span or Event → OCSF ProcessActivity (class_uid 1007).
    One event per critic/stage run.
    """
    meta  = getattr(obs, "metadata", {}) or {}
    name  = getattr(obs, "name", "") or ""
    ts    = _epoch(getattr(obs, "start_time", None))
    end   = _epoch(getattr(obs, "end_time", None))
    level = (getattr(obs, "level", None) or "DEFAULT").upper()

    sev_label = "Medium" if level == "WARNING" else ("High" if level == "ERROR" else "Informational")
    sev_id    = 2 if level == "WARNING" else (3 if level == "ERROR" else 1)

    score  = meta.get("score") or meta.get("moe_score") or 0
    rating = meta.get("rating", "")
    gaps   = meta.get("gaps", [])

    return {
        "class_uid":     1007,
        "class_name":    "Process Activity",
        "ocsf_version":  OCSF_VERSION,
        "activity_id":   2,
        "activity_name": "Terminate",
        "time":          ts,
        "duration":      _duration_ms(ts, end),
        "severity_id":   sev_id,
        "severity":      sev_label,
        "status":        "Success",
        "status_id":     1,
        "actor":         _actor(),
        "process": {
            "name":    name,
            "pid":     0,
            "cmd_line": f"stage:{name}",
        },
        "metadata": _metadata(["process_activity"]),
        "unmapped": {
            "trace_id":     trace_id,
            "observation_id": getattr(obs, "id", ""),
            "stage_name":   name,
            "score":        score,
            "rating":       rating,
            "gaps":         gaps,
            "level":        level,
        },
    }


# ── Generation → APIActivity (6003) ──────────────────────────────────────────

def generation_to_ocsf(obs, trace_id: str) -> Dict[str, Any]:
    """
    Langfuse Generation → OCSF APIActivity (class_uid 6003).
    One event per LLM call (critic).
    """
    meta    = getattr(obs, "metadata", {}) or {}
    name    = getattr(obs, "name", "") or ""
    ts      = _epoch(getattr(obs, "start_time", None))
    end     = _epoch(getattr(obs, "end_time", None))
    model   = getattr(obs, "model", "") or meta.get("model", "")
    usage   = getattr(obs, "usage_details", {}) or {}
    cost    = getattr(obs, "cost_details",  {}) or {}

    total_tokens = (usage.get("total_tokens") or usage.get("total") or
                    meta.get("moe_total_tokens", 0))
    total_cost   = (cost.get("total_cost") or cost.get("total") or
                    meta.get("moe_total_cost", 0.0))

    # Derive provider from model name
    provider = "unknown"
    if model:
        m = model.lower()
        if "anthropic" in m or "claude" in m:  provider = "anthropic"
        elif "openai" in m or "gpt" in m:       provider = "openai"
        elif "amazon" in m or "nova" in m:      provider = "amazon_bedrock"
        elif "google" in m or "gemini" in m:    provider = "google"
        elif "mistral" in m:                    provider = "mistral"
        elif "/" in model:                      provider = model.split("/")[0]

    latency_ms = _duration_ms(ts, end)

    return {
        "class_uid":     6003,
        "class_name":    "API Activity",
        "ocsf_version":  OCSF_VERSION,
        "activity_id":   1,
        "activity_name": "Create",
        "time":          ts,
        "duration":      latency_ms,
        "severity_id":   1,
        "severity":      "Informational",
        "status":        "Success",
        "status_id":     1,
        "actor":         _actor(),
        "api": {
            "operation":  "chat_completions",
            "service":    {"name": provider},
            "response":   {"code": 200, "message": "OK"},
        },
        "metadata": _metadata(["api_activity"]),
        "unmapped": {
            "trace_id":     trace_id,
            "observation_id": getattr(obs, "id", ""),
            "critic_name":  name,
            "model":        model,
            "provider":     provider,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "latency_ms":   latency_ms,
            "score":        meta.get("score"),
            "rating":       meta.get("rating"),
        },
    }


# ── Score → SecurityFinding (2001) ───────────────────────────────────────────

# AIVSS score names written by LangfuseSink (current) or future LangfuseSink extension
_AIVSS_SCORE_NAMES = {"aivss_inbound", "aivss_internal", "aivss_outbound", "aivss_overall"}

def score_to_ocsf(score, trace_id: str) -> Optional[Dict[str, Any]]:
    """
    Langfuse Score (AIVSS type) → OCSF SecurityFinding (class_uid 2001).
    Non-AIVSS scores are skipped (return None).
    """
    name = (getattr(score, "name", "") or "").lower()
    if name not in _AIVSS_SCORE_NAMES:
        return None

    raw_value = getattr(score, "value", 0.0) or 0.0
    try:
        composite = float(raw_value)
    except (TypeError, ValueError):
        composite = 0.0

    sev_label, sev_id = _sev_from_score(composite)
    flow = name.replace("aivss_", "")
    ts   = _epoch(getattr(score, "timestamp", None) or getattr(score, "created_at", None))

    return {
        "class_uid":    2001,
        "class_name":   "Security Finding",
        "ocsf_version": OCSF_VERSION,
        "time":         ts,
        "severity_id":  sev_id,
        "severity":     sev_label,
        "status":       "New",
        "status_id":    1,
        "finding": {
            "uid":   f"aivss-{trace_id}-{flow}",
            "title": f"AIVSS {flow.capitalize()} Score",
            "desc":  f"AIVSS {flow} composite {composite:.2f} ({sev_label})",
        },
        "resources": [{"name": trace_id, "type": "pipeline_run", "uid": trace_id}],
        "metadata": _metadata(["security_control"]),
        "unmapped": {
            "trace_id":        trace_id,
            "score_id":        getattr(score, "id", ""),
            "aivss_flow":      flow,
            "aivss_composite": composite,
        },
    }


# ── Governance metadata → DetectionFinding (2004) ────────────────────────────

_GOV_DIMS = {
    "D1_exploitation":  ("Exploitation", "injection"),
    "D2_manipulation":  ("Manipulation", "manipulation"),
    "D3_leakage":       ("Data Leakage", "leakage"),
    "D4_identity":      ("Identity Integrity", "identity"),
    "D5_sovereignty":   ("Data Sovereignty", "sovereignty"),
}

def governance_to_ocsf(trace, trace_id: str) -> List[Dict[str, Any]]:
    """
    Governance metadata on a Trace → list of OCSF DetectionFinding (class_uid 2004) events.
    One event per dimension that is not LOW.
    """
    meta = getattr(trace, "metadata", {}) or {}
    ts   = _epoch(getattr(trace, "timestamp", None))
    events = []

    for key, (label, category) in _GOV_DIMS.items():
        severity = (meta.get(key) or "LOW").upper()
        if severity == "LOW":
            continue

        sev_id = _sev_id(severity)
        events.append({
            "class_uid":    2004,
            "class_name":   "Detection Finding",
            "ocsf_version": OCSF_VERSION,
            "time":         ts,
            "severity_id":  sev_id,
            "severity":     severity.capitalize(),
            "status":       "New",
            "status_id":    1,
            "finding": {
                "uid":      f"gov-{trace_id}-{key}",
                "title":    f"Governance: {label}",
                "desc":     f"{label} dimension elevated to {severity}",
                "type_uid": 200401,
            },
            "resources": [{"name": trace_id, "type": "pipeline_run", "uid": trace_id}],
            "metadata": _metadata(["detection_finding"]),
            "unmapped": {
                "trace_id":          trace_id,
                "governance_dim":    key,
                "governance_label":  label,
                "governance_category": category,
                "severity":          severity,
                "blocked_agents":    meta.get("blocked_agents", []),
            },
        })

    return events


# ── Langfuse fetch ────────────────────────────────────────────────────────────

def _get_client():
    try:
        from langfuse import Langfuse
    except ImportError:
        print("ERROR: langfuse package not installed. Run: pip install langfuse", file=sys.stderr)
        sys.exit(1)

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    host       = os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000")

    if not public_key or not secret_key:
        print("ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    return Langfuse(public_key=public_key, secret_key=secret_key, host=host)


def fetch_traces(lf, arch: Optional[str], trace_id: Optional[str],
                 since: Optional[str], limit: int) -> List:
    """Return a list of Trace objects from Langfuse."""
    if trace_id:
        t = lf.api.trace.get(trace_id)
        return [t] if t else []

    kwargs = {"name": "threat_assessment", "limit": limit}
    if arch:
        # Langfuse v4: filter by metadata not directly supported in list —
        # fetch by name + post-filter on metadata.architecture
        kwargs["limit"] = min(limit * 4, 200)  # over-fetch then filter
    if since:
        try:
            kwargs["from_timestamp"] = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            print(f"WARNING: invalid --since value '{since}', ignoring.", file=sys.stderr)

    kwargs["fields"] = "core,io,scores,metrics"
    result = lf.api.trace.list(**kwargs)
    traces = list(getattr(result, "data", []) or [])

    if arch:
        traces = [
            t for t in traces
            if (getattr(t, "metadata", {}) or {}).get("architecture") == arch
        ][:limit]

    return traces


def fetch_observations(lf, trace_id: str) -> List:
    resp = lf.api.observations.get_many(
        trace_id=trace_id,
        fields="basic,io,model,usage,metadata,metrics",
        limit=200,
    )
    return list(getattr(resp, "data", []) or [])


def fetch_scores(lf, trace_id: str) -> List:
    resp = lf.api.scores_v3.get_many_v3(trace_id=trace_id, limit=100)
    return list(getattr(resp, "data", []) or [])


# ── Export pipeline ──────────────────────────────────────────────────────────

def export_trace(lf, trace) -> List[Dict[str, Any]]:
    """Convert one Langfuse trace + its observations + scores to OCSF events."""
    trace_id = getattr(trace, "id", "")
    events: List[Dict[str, Any]] = []

    # 1. Trace → ProcessActivity
    events.append(trace_to_ocsf(trace))

    # 2. Governance dims → DetectionFindings
    events.extend(governance_to_ocsf(trace, trace_id))

    # 3. Observations → ProcessActivity (span) or APIActivity (generation)
    try:
        observations = fetch_observations(lf, trace_id)
        for obs in observations:
            obs_type = (getattr(obs, "type", "") or "").upper()
            if obs_type == "GENERATION":
                events.append(generation_to_ocsf(obs, trace_id))
            elif obs_type in ("SPAN", "EVENT", ""):
                events.append(span_to_ocsf(obs, trace_id))
    except Exception as exc:
        print(f"WARNING: could not fetch observations for {trace_id}: {exc}", file=sys.stderr)

    # 4. AIVSS scores → SecurityFindings
    try:
        scores = fetch_scores(lf, trace_id)
        for score in scores:
            ev = score_to_ocsf(score, trace_id)
            if ev is not None:
                events.append(ev)
    except Exception as exc:
        print(f"WARNING: could not fetch scores for {trace_id}: {exc}", file=sys.stderr)

    return events


# ── Summary table ────────────────────────────────────────────────────────────

def _print_summary(all_events: List[Dict]) -> None:
    counts: Dict[str, int] = {}
    for ev in all_events:
        key = f"{ev['class_uid']} {ev['class_name']}"
        counts[key] = counts.get(key, 0) + 1
    print(f"\n{'OCSF Class':<40} {'Count':>6}")
    print("-" * 48)
    for cls, n in sorted(counts.items()):
        print(f"{cls:<40} {n:>6}")
    print(f"\nTotal events: {len(all_events)}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch ThreatAssessor traces from Langfuse and export as OCSF v1.1 events."
    )
    parser.add_argument("--trace-id", help="Export a single trace by ID")
    parser.add_argument("--arch",     help="Filter traces by architecture name")
    parser.add_argument("--since",    help="ISO 8601 datetime — only traces after this")
    parser.add_argument("--limit",    type=int, default=DEFAULT_LIMIT,
                        help=f"Max traces to fetch (default {DEFAULT_LIMIT})")
    parser.add_argument("--out",      default="ocsf_export.json",
                        help="Output file path (default: ocsf_export.json)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print events to stdout, do not write file")
    args = parser.parse_args()

    lf = _get_client()

    print(f"Fetching traces from Langfuse...", file=sys.stderr)
    traces = fetch_traces(lf, args.arch, args.trace_id, args.since, args.limit)

    if not traces:
        print("No traces found. Run a pipeline analysis with LangfuseSink active.", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(traces)} trace(s). Converting to OCSF...", file=sys.stderr)
    all_events: List[Dict] = []
    for trace in traces:
        all_events.extend(export_trace(lf, trace))

    if args.dry_run:
        print(json.dumps(all_events, indent=2, ensure_ascii=False))
        _print_summary(all_events)
        return

    out_path = Path(args.out)
    out_path.write_text(json.dumps(all_events, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {out_path}")
    _print_summary(all_events)


if __name__ == "__main__":
    main()
