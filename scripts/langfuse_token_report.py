#!/usr/bin/env python3
"""
langfuse_token_report.py — Pull per-routing-mode token efficiency from Langfuse.

Queries recent threat_assessment traces, groups by routing_mode tag, and prints
a comparison table: arch_type × routing_mode → avg tokens, cost, wall_s.

Usage:
    python3 scripts/langfuse_token_report.py
    python3 scripts/langfuse_token_report.py --limit 50
    python3 scripts/langfuse_token_report.py --since 2026-09-19

Requires LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL in .env.
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _lf_client():
    from langfuse import Langfuse  # type: ignore[import]
    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000"),
    )


def _fetch_traces(lf, limit: int, since: str | None):
    """Return list of trace dicts from Langfuse."""
    kwargs: dict = {"name": "threat_assessment", "limit": limit}
    if since:
        import datetime
        kwargs["from_timestamp"] = datetime.datetime.fromisoformat(since)
    page = lf.api.trace.list(**kwargs)
    return page.data if hasattr(page, "data") else []


def _routing_mode(trace) -> str:
    """Extract routing_mode from trace tags or metadata."""
    # Tags are the canonical source (set by LangfuseSink.run_start handler)
    tags = getattr(trace, "tags", []) or []
    for tag in tags:
        if tag in ("brain_fast", "api_only", "full_moe"):
            return tag
    # Fallback: metadata
    meta = getattr(trace, "metadata", {}) or {}
    return meta.get("routing_mode", "unknown")


def _arch_type(trace) -> str:
    meta = getattr(trace, "metadata", {}) or {}
    return meta.get("arch_type", "unknown")


def _build_table(traces) -> dict:
    """Group traces: {routing_mode: {arch_type: [metrics]}}"""
    groups: dict = defaultdict(lambda: defaultdict(list))
    for t in traces:
        rm = _routing_mode(t)
        at = _arch_type(t)
        output = getattr(t, "output", {}) or {}
        meta = getattr(t, "metadata", {}) or {}
        # Pull top-level token/cost from trace if available; else from observations
        total_tokens = getattr(t, "total_tokens", None) or 0
        total_cost = getattr(t, "total_cost", None) or 0.0
        wall_s = meta.get("pipeline_wall_s") or 0.0
        confidence = (output.get("confidence") if isinstance(output, dict) else None) or 0.0
        groups[rm][at].append({
            "tokens": total_tokens,
            "cost": total_cost,
            "wall_s": wall_s,
            "confidence": confidence,
        })
    return groups


def _avg(vals, key):
    v = [x[key] for x in vals if x[key]]
    return sum(v) / len(v) if v else 0.0


def _print_table(groups: dict, n_traces: int) -> None:
    BOLD = "\033[1m"; RESET = "\033[0m"; CYAN = "\033[36m"; GREEN = "\033[32m"

    print(f"\n{BOLD}Token-Efficiency Report — {n_traces} traces{RESET}")
    print("─" * 72)
    print(f"{'Routing Mode':<16} {'Arch Type':<22} {'N':>4}  {'Avg Tokens':>12}  {'Avg Cost $':>10}  {'Avg Wall s':>10}")
    print("─" * 72)

    mode_order = ["brain_fast", "api_only", "full_moe", "unknown"]
    for rm in mode_order:
        if rm not in groups:
            continue
        for at, vals in sorted(groups[rm].items()):
            avg_tok = _avg(vals, "tokens")
            avg_cost = _avg(vals, "cost")
            avg_wall = _avg(vals, "wall_s")
            n = len(vals)
            color = GREEN if rm == "brain_fast" else CYAN if rm == "api_only" else ""
            print(f"{color}{rm:<16}{RESET} {at:<22} {n:>4}  {avg_tok:>12,.0f}  {avg_cost:>10.4f}  {avg_wall:>10.1f}")

    print("─" * 72)

    # Summary by routing mode
    print(f"\n{BOLD}Summary by routing_mode:{RESET}")
    for rm in mode_order:
        if rm not in groups:
            continue
        all_vals = [v for vlist in groups[rm].values() for v in vlist]
        avg_tok = _avg(all_vals, "tokens")
        avg_cost = _avg(all_vals, "cost")
        n = len(all_vals)
        print(f"  {rm:<14}  n={n}  avg_tokens={avg_tok:,.0f}  avg_cost=${avg_cost:.4f}")

    # brain_fast vs full_moe delta
    if "brain_fast" in groups and "full_moe" in groups:
        bf = [v for vlist in groups["brain_fast"].values() for v in vlist]
        fm = [v for vlist in groups["full_moe"].values() for v in vlist]
        bf_tok = _avg(bf, "tokens"); fm_tok = _avg(fm, "tokens")
        bf_cost = _avg(bf, "cost"); fm_cost = _avg(fm, "cost")
        if fm_tok > 0:
            pct_tok = (fm_tok - bf_tok) / fm_tok * 100
            pct_cost = (fm_cost - bf_cost) / fm_cost * 100 if fm_cost > 0 else 0
            print(f"\n  brain_fast saves {pct_tok:.0f}% tokens / {pct_cost:.0f}% cost vs full_moe")


def main() -> None:
    _load_env()

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit",  type=int, default=100, help="Max traces to fetch")
    ap.add_argument("--since",  default=None, help="ISO date lower bound (e.g. 2026-09-19)")
    ap.add_argument("--raw",    action="store_true", help="Dump raw trace list as JSON")
    args = ap.parse_args()

    try:
        lf = _lf_client()
    except ImportError:
        print("langfuse package not installed. pip install langfuse", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Missing env var: {e}. Set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY.", file=sys.stderr)
        sys.exit(1)

    traces = _fetch_traces(lf, limit=args.limit, since=args.since)
    print(f"Fetched {len(traces)} traces from Langfuse.")

    if args.raw:
        import json
        raw = [{"id": getattr(t, "id", ""), "tags": getattr(t, "tags", []),
                "metadata": getattr(t, "metadata", {})} for t in traces]
        print(json.dumps(raw, indent=2))
        return

    groups = _build_table(traces)
    _print_table(groups, len(traces))


if __name__ == "__main__":
    main()
