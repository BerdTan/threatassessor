#!/usr/bin/env python3
"""CLI wrapper for POST /api/v1/taco/run-sync."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _load_api_key() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("TM_API_KEY", "")


def _conf_bar(conf: float) -> str:
    filled = round(conf * 20)
    return f"[{'█' * filled}{'░' * (20 - filled)}] {conf * 100:.0f}%"


def main():
    parser = argparse.ArgumentParser(description="TACO run-sync CLI")
    parser.add_argument("query", help="Threat question")
    parser.add_argument("--arch", default=None, help="Known corpus arch_id")
    parser.add_argument("--mmd", default=None, help="Path to .mmd file")
    parser.add_argument("--sim", action="store_true", help="sim_mode — always walk all hops")
    parser.add_argument("--json", dest="raw_json", action="store_true", help="Print raw JSON")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    try:
        import urllib.request
    except ImportError:
        sys.exit("urllib not available")

    api_key = _load_api_key()
    mmd_content = None
    if args.mmd:
        mmd_content = Path(args.mmd).read_text()

    payload = json.dumps({
        "query": args.query,
        "arch_name": args.arch,
        "mmd_content": mmd_content,
        "sim_mode": args.sim,
    }).encode()

    req = urllib.request.Request(
        f"{args.api}/api/v1/taco/run-sync",
        data=payload,
        headers={"Content-Type": "application/json", "TM-API-KEY": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        sys.exit(f"Request failed: {exc}")

    if args.raw_json:
        print(json.dumps(body, indent=2))
        return

    chain_id = body.get("chain_id", "?")[:8]
    arch = body.get("arch_name") or "—"
    total_ms = body.get("total_duration_ms", 0)
    final_conf = body.get("final_confidence", 0.0)
    hop_flags = []
    if body.get("routed_to_rag"):    hop_flags.append("rag")
    if body.get("routed_to_harness"): hop_flags.append("harness")
    if body.get("routed_to_critics"): hop_flags.append("critics")

    HOP_ICONS = {"brain": "B", "rag": "R", "harness": "H", "critic": "C"}
    HOP_COLORS = {"brain": "\033[34m", "rag": "\033[32m", "harness": "\033[33m", "critic": "\033[35m"}
    RESET = "\033[0m"

    print(f"\n{'─'*60}")
    print(f"  TACO  chain={chain_id}  arch={arch}")
    print(f"  query: {args.query[:70]}")
    print(f"{'─'*60}")

    for hop in body.get("hops", []):
        ht = hop.get("hop_type", "?")
        col = HOP_COLORS.get(ht, "")
        icon = HOP_ICONS.get(ht, "?")
        conf = hop.get("confidence")
        conf_str = _conf_bar(conf) if conf is not None else "n/a"
        ms = hop.get("duration_ms", 0)
        summary = hop.get("response_summary", "")[:60]
        routed = " [routed]" if hop.get("routed") else ""
        print(f"  {col}[{icon}]{RESET} {ht:<8} {conf_str}  {ms}ms{routed}")
        print(f"       {summary}")

    print(f"{'─'*60}")
    print(f"  total: {total_ms}ms  final_conf: {_conf_bar(final_conf)}")
    if hop_flags:
        print(f"  flags: {', '.join(hop_flags)}")
    print()


if __name__ == "__main__":
    main()
