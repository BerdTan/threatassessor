"""
bench_routing.py — Token-efficiency benchmark across pipeline routing modes.

Submits one arch per routing mode (brain_fast / api_only / full_moe) through the
streaming endpoint so smart_router assigns the mode naturally, then reads back
Langfuse trace metadata to extract token counts and wall time per mode.

Usage:
    # Default: 3 representative archs, one per routing mode
    python3 scripts/bench_routing.py --langfuse

    # Custom arch set
    python3 scripts/bench_routing.py --langfuse --archs 03_aws_3tier 21_agentic_ai_system

    # Dry run — shows which archs would run + expected routing, no API calls
    python3 scripts/bench_routing.py --dry-run

    # Pull results from a previous run without re-running
    python3 scripts/bench_routing.py --fetch-only

Output:
    Table: arch | routing_mode | wall_s | moe_tokens | aivss | token_savings_vs_full_moe
    Writes: report/bench/routing_efficiency.json

Langfuse quota:
    Each arch generates ~3–10 observations. A 3-arch run costs ~15–30 observations
    against the free-tier 50K/month limit.
"""

from __future__ import annotations

import json
import os
import sys
import time
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# ── defaults ─────────────────────────────────────────────────────────────────

os.environ.setdefault("LANGFUSE_SKIP", "1")  # safety net; --langfuse overrides

# Representative archs: one per routing mode based on Session 69 boxing table.
# brain_fast: D5=1.0, 9+ hits; api_only: 0 brain hits; full_moe: D5=0.154
DEFAULT_ARCHS = ["03_aws_3tier", "07_gcp_serverless", "21_agentic_ai_system"]

API_URL_DEFAULT = "http://localhost:8000"
STREAM_TIMEOUT  = 300   # seconds to wait for SSE complete event per arch
LANGFUSE_WAIT   = 8     # seconds after run before querying Langfuse (flush delay)

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
RED    = "\033[91m"
RESET  = "\033[0m"

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _c(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}" if sys.stdout.isatty() else text


def _api_key() -> str:
    return os.environ.get("API_KEY", "")


def _langfuse_creds() -> tuple[str, str, str]:
    base = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    pk   = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk   = os.environ.get("LANGFUSE_SECRET_KEY", "")
    return base, pk, sk


# ── streaming run ─────────────────────────────────────────────────────────────

def _run_via_stream(api_url: str, arch: str, api_key: str, timeout: int) -> dict:
    """
    POST to /api/v1/analyze/stream (SSE) and drain until 'complete' event.
    smart_router assigns routing mode; Langfuse captures the trace.

    Returns dict with keys: routing_mode, wall_s, moe_tokens, aivss_composite, error.
    """
    import requests

    headers = {"TM-API-KEY": api_key, "Accept": "text/event-stream"}
    body    = {"arch_name": arch}

    t0 = time.time()
    routing_mode   = None
    moe_tokens     = 0
    aivss_composite = None
    error          = None

    try:
        with requests.post(
            f"{api_url}/api/v1/analyze/stream",
            json=body,
            headers=headers,
            stream=True,
            timeout=(10, timeout),
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                try:
                    payload = json.loads(raw_line[5:].strip())
                except json.JSONDecodeError:
                    continue

                etype = payload.get("type", "")

                if etype == "complete":
                    routing_mode    = payload.get("routing_mode") or payload.get("mode")
                    moe_tokens      = payload.get("moe_total_tokens", 0) or 0
                    aivss_composite = (
                        payload.get("aivss_composite")
                        or (payload.get("governance_signals") or {}).get("aivss", {})
                              .get("overall", {}).get("composite")
                    )
                    break

                if etype == "error":
                    error = payload.get("message", "unknown error")
                    break

    except Exception as exc:
        error = str(exc)

    wall_s = round(time.time() - t0, 1)
    return {
        "arch":           arch,
        "routing_mode":   routing_mode or "unknown",
        "wall_s":         wall_s,
        "moe_tokens":     moe_tokens,
        "aivss_composite": aivss_composite,
        "error":          error,
    }


# ── Langfuse read-back ────────────────────────────────────────────────────────

def _fetch_langfuse_trace(arch: str) -> dict:
    """
    Query Langfuse for the most recent trace whose id starts with arch name.
    Returns metadata dict with routing_mode, arch_type, aivss_composite, wall_s.
    """
    try:
        import requests as _req
        base, pk, sk = _langfuse_creds()
        r = _req.get(
            f"{base}/api/public/traces",
            auth=(pk, sk),
            params={"limit": 10, "orderBy": "timestamp.desc"},
            timeout=10,
        )
        r.raise_for_status()
        traces = r.json().get("data", [])

        for t in traces:
            tid = t.get("id", "")
            if tid.startswith(arch):
                meta = t.get("metadata", {}) or {}
                tags = t.get("tags", [])
                return {
                    "trace_id":       tid,
                    "routing_mode":   meta.get("routing_mode") or (tags[0] if tags else None),
                    "arch_type":      meta.get("arch_type"),
                    "aivss_composite": meta.get("aivss_composite"),
                    "pipeline_wall_s": meta.get("pipeline_wall_s"),
                    "observations":   _fetch_observations(base, pk, sk, tid),
                }
    except Exception as exc:
        logger.warning("Langfuse fetch failed: %s", exc)
    return {}


def _fetch_observations(base: str, pk: str, sk: str, trace_id: str) -> list[dict]:
    try:
        import requests as _req
        r = _req.get(
            f"{base}/api/public/observations",
            auth=(pk, sk),
            params={"traceId": trace_id, "limit": 50},
            timeout=10,
        )
        r.raise_for_status()
        obs = r.json().get("data", [])
        return [
            {
                "name":       o.get("name"),
                "type":       o.get("type"),
                "model":      o.get("model"),
                "tokens":     (o.get("usage") or {}).get("total", 0),
                "cost":       (o.get("calculatedTotalCost") or 0),
                "meta_keys":  list((o.get("metadata") or {}).keys()),
            }
            for o in obs
        ]
    except Exception:
        return []


# ── routing mode prediction (from smart_router, read-only) ──────────────────

def _predict_routing(arch: str) -> str:
    try:
        from chatbot.harness.smart_router import select_mode
        return select_mode(arch).mode
    except Exception:
        return "?"


# ── output ────────────────────────────────────────────────────────────────────

def _print_table(results: list[dict]) -> None:
    full_moe_tokens = next(
        (r["moe_tokens"] for r in results if r.get("routing_mode") == "full_moe" and r["moe_tokens"]),
        None,
    )

    header = f"{'Arch':<35} {'Mode':<12} {'Wall(s)':>7} {'MoE tok':>8} {'AIVSS':>6} {'Savings':>8}"
    print()
    print(_c(header, CYAN))
    print("─" * 80)

    for r in results:
        arch    = r["arch"]
        mode    = r.get("routing_mode", "unknown")
        wall    = r.get("wall_s", "—")
        tokens  = r.get("moe_tokens", 0) or 0
        aivss   = r.get("aivss_composite")
        err     = r.get("error")

        savings = "—"
        if full_moe_tokens and mode != "full_moe" and tokens is not None:
            pct = (1 - tokens / full_moe_tokens) * 100
            savings = f"{pct:+.0f}%"
        elif mode == "full_moe":
            savings = "baseline"

        mode_colour = GREEN if mode == "brain_fast" else (BLUE if mode == "api_only" else YELLOW)
        err_suffix  = f"  {_c('ERR: '+str(err)[:40], RED)}" if err else ""

        print(
            f"{arch:<35} {_c(mode, mode_colour):<12+len(mode_colour)+len(RESET)} "
            f"{str(wall):>7} {str(tokens):>8} "
            f"{str(round(aivss,2) if aivss else '—'):>6} {savings:>8}"
            f"{err_suffix}"
        )
    print()


def _save_results(results: list[dict], langfuse_data: dict) -> Path:
    out_dir = ROOT / "report" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "routing_efficiency.json"
    bundle = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results":       results,
        "langfuse_traces": langfuse_data,
    }
    out.write_text(json.dumps(bundle, indent=2))
    return out


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Token-efficiency benchmark across pipeline routing modes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--archs",      nargs="+", default=DEFAULT_ARCHS,
                    help="Arch names to run (default: one per routing mode)")
    ap.add_argument("--api-url",    default=API_URL_DEFAULT)
    ap.add_argument("--langfuse",   action="store_true",
                    help="Enable Langfuse tracing (overrides LANGFUSE_SKIP=1 default)")
    ap.add_argument("--fetch-only", action="store_true",
                    help="Skip pipeline runs; only read back Langfuse traces for --archs")
    ap.add_argument("--dry-run",    action="store_true",
                    help="Show predicted routing modes and exit — no API calls")
    ap.add_argument("--timeout",    type=int, default=STREAM_TIMEOUT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    if args.langfuse:
        os.environ["LANGFUSE_SKIP"] = "0"
        print(_c("Langfuse tracing ENABLED", GREEN))
    else:
        print(_c("Langfuse tracing OFF (pass --langfuse to enable)", YELLOW))

    print(f"Archs: {', '.join(args.archs)}")
    print()

    # ── dry run ──────────────────────────────────────────────────────────────
    if args.dry_run:
        print(_c("DRY RUN — predicted routing (no API calls):", CYAN))
        for arch in args.archs:
            mode = _predict_routing(arch)
            print(f"  {arch:<35}  → {mode}")
        return

    api_key = _api_key()
    if not api_key:
        print(_c("ERROR: API_KEY not set in .env", RED))
        sys.exit(1)

    results: list[dict] = []
    langfuse_data: dict = {}

    # ── fetch-only ────────────────────────────────────────────────────────────
    if args.fetch_only:
        print(_c("Fetch-only mode — reading Langfuse traces...", CYAN))
        for arch in args.archs:
            td = _fetch_langfuse_trace(arch)
            langfuse_data[arch] = td
            results.append({
                "arch":           arch,
                "routing_mode":   td.get("routing_mode", "unknown"),
                "wall_s":         td.get("pipeline_wall_s"),
                "moe_tokens":     sum(o.get("tokens", 0) for o in td.get("observations", [])
                                      if "critic" in (o.get("name") or "")),
                "aivss_composite": td.get("aivss_composite"),
                "error":          None if td else "trace not found",
            })
        _print_table(results)
        out = _save_results(results, langfuse_data)
        print(f"Saved → {out}")
        return

    # ── live runs ─────────────────────────────────────────────────────────────
    for arch in args.archs:
        predicted = _predict_routing(arch)
        print(f"Running {_c(arch, CYAN)} (predicted: {_c(predicted, YELLOW)}) ...", end=" ", flush=True)

        r = _run_via_stream(args.api_url, arch, api_key, args.timeout)
        results.append(r)

        status = _c("OK", GREEN) if not r["error"] else _c(f"ERR: {r['error'][:50]}", RED)
        print(f"{status}  mode={_c(r['routing_mode'], YELLOW)}  {r['wall_s']}s")

        # Wait for Langfuse flush before reading back
        if args.langfuse and not r["error"]:
            time.sleep(LANGFUSE_WAIT)
            td = _fetch_langfuse_trace(arch)
            langfuse_data[arch] = td
            # Prefer Langfuse values (more complete) over SSE payload
            if td.get("routing_mode"):
                r["routing_mode"] = td["routing_mode"]
            if td.get("pipeline_wall_s"):
                r["wall_s"] = td["pipeline_wall_s"]
            if td.get("aivss_composite"):
                r["aivss_composite"] = td["aivss_composite"]
            # Sum critic generation tokens from observations
            obs_tokens = sum(
                o.get("tokens", 0) for o in td.get("observations", [])
                if "critic" in (o.get("name") or "")
            )
            if obs_tokens:
                r["moe_tokens"] = obs_tokens
            r["langfuse_observations"] = len(td.get("observations", []))

    _print_table(results)
    out = _save_results(results, langfuse_data)
    print(f"Saved → {out}")

    if args.langfuse:
        total_obs = sum(r.get("langfuse_observations", 0) for r in results)
        print(_c(f"Langfuse observations used this run: ~{total_obs}", CYAN))


if __name__ == "__main__":
    main()
