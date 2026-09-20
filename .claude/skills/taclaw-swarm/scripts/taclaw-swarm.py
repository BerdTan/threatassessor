#!/usr/bin/env python3
"""taclaw-swarm — fan out TAclaw jobs across multiple artifact targets."""

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_API_URL = os.environ.get("TA_API_URL", "http://localhost:8000")
DEFAULT_API_KEY = os.environ.get("API_KEY", "")
POLL_INTERVAL = 4
JOB_TIMEOUT = 300
MAX_CONCURRENT = 6


@dataclass
class SwarmJob:
    target: str
    job_id: str = ""
    status: str = "pending"
    result: dict = field(default_factory=dict)
    error: Optional[str] = None
    elapsed: float = 0.0


class TASwarmClient:
    def __init__(self, api_url: str, api_key: str, timeout: int = JOB_TIMEOUT):
        self.api_url = api_url.rstrip("/")
        self.job_timeout = timeout
        self.headers = {"TM-API-KEY": api_key, "Content-Type": "application/json"}

    def submit(self, target: str) -> str:
        payload = {"target": target, "target_type": "directory", "ssp_profile": "low_risk_cloud"}
        resp = httpx.post(
            f"{self.api_url}/api/v1/taclaw/run",
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["job_id"]

    def poll(self, job_id: str) -> dict:
        deadline = time.time() + self.job_timeout
        while time.time() < deadline:
            resp = httpx.get(
                f"{self.api_url}/api/v1/taclaw/jobs/{job_id}",
                headers=self.headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "completed":
                return data
            if data.get("status") == "failed":
                raise RuntimeError(data.get("error", "job failed"))
            time.sleep(POLL_INTERVAL)
        raise TimeoutError(f"job {job_id} timed out after {self.job_timeout}s")


def run_one(client: TASwarmClient, target: str) -> SwarmJob:
    job = SwarmJob(target=target)
    t0 = time.time()
    try:
        job.job_id = client.submit(target)
        job.result = client.poll(job.job_id)
        job.status = "completed"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
    job.elapsed = time.time() - t0
    return job


def _export(job: SwarmJob) -> dict:
    return job.result.get("export", {}) if job.status == "completed" else {}


def _assessment(job: SwarmJob) -> dict:
    return _export(job).get("assessment", {}) or {}


def _techniques(job: SwarmJob) -> list:
    raw = _assessment(job).get("techniques", []) or []
    # Normalise: list of dicts with "id", or plain strings
    ids = []
    for t in raw:
        if isinstance(t, dict):
            tid = t.get("id") or t.get("technique_id", "")
        else:
            tid = str(t)
        if tid:
            ids.append(tid)
    return ids


def _aivss(job: SwarmJob) -> float:
    return float(_assessment(job).get("aivss_composite", 0.0) or 0.0)


def _avg_fidelity(job: SwarmJob) -> float:
    fmap = job.result.get("adapter_metadata", {}).get("adapters_fidelity", {}) or {}
    return sum(fmap.values()) / len(fmap) if fmap else 0.5


def _detect_count(job: SwarmJob) -> int:
    return len(_export(job).get("detect_findings", []) or [])


def champion_score(job: SwarmJob) -> float:
    if job.status != "completed":
        return 0.0
    tech_count = len(_techniques(job))
    return _aivss(job) * _avg_fidelity(job) * math.log1p(tech_count)


def aggregate(jobs: list) -> dict:
    technique_freq: dict = {}
    total_detect = 0
    max_aivss = 0.0
    block_count = 0
    completed = [j for j in jobs if j.status == "completed"]

    for job in completed:
        for tid in _techniques(job):
            technique_freq[tid] = technique_freq.get(tid, 0) + 1
        total_detect += _detect_count(job)
        aivss = _aivss(job)
        if aivss > max_aivss:
            max_aivss = aivss
        if _export(job).get("gate") == "BLOCK":
            block_count += 1

    top_techniques = sorted(technique_freq.items(), key=lambda x: -x[1])[:10]
    return {
        "top_techniques": top_techniques,
        "detect_hit_count": total_detect,
        "max_aivss": max_aivss,
        "block_count": block_count,
        "completed": len(completed),
    }


def print_report(jobs: list, agg: dict) -> None:
    completed = [j for j in jobs if j.status == "completed"]
    failed = [j for j in jobs if j.status == "failed"]

    target_col = max((len(j.target) for j in jobs), default=10) + 2
    header = (
        f"{'Target':<{target_col}} {'Gate':<7} {'AIVSS':<7} "
        f"{'Techniques':<12} {'Fidelity':<10} {'Routing':<14} {'Time'}"
    )
    sep = "=" * len(header)
    thin = "-" * len(header)

    ranked = sorted(completed, key=champion_score, reverse=True)
    champ_target = ranked[0].target if ranked else ""

    print(f"\nSwarm Summary")
    print(sep)
    print(header)
    print(thin)

    for job in jobs:
        tgt = job.target
        if job.status != "completed":
            err = (job.error or "unknown")[:50]
            print(f"{tgt:<{target_col}} FAILED — {err}")
            continue

        gate = _export(job).get("gate", "?")
        aivss = _aivss(job)
        techs = len(_techniques(job))
        fid = f"{_avg_fidelity(job):.2f}"
        routing = job.result.get("routing_mode", "?")
        elapsed = f"{job.elapsed:.0f}s"
        star = " ★" if tgt == champ_target else ""
        print(
            f"{tgt:<{target_col}} {gate:<7} {aivss:<7.1f} "
            f"{techs:<12} {fid:<10} {routing:<14} {elapsed}{star}"
        )

    print(sep)
    print(
        f"\nTargets: {len(jobs)} total  {len(completed)} completed  {len(failed)} failed"
    )
    print(
        f"BLOCK gates: {agg['block_count']}/{len(completed)}"
        f"   Max AIVSS: {agg['max_aivss']:.1f}"
        f"   DETECT hits (cross-swarm): {agg['detect_hit_count']}"
    )

    if agg["top_techniques"]:
        print("\nTop techniques across swarm:")
        for tid, count in agg["top_techniques"][:5]:
            bar = "█" * min(count, 20)
            print(f"  {tid:<14} {bar} ({count}/{len(completed)} targets)")

    if champ_target:
        champ = ranked[0]
        tech_count = len(_techniques(champ))
        aivss_val = _aivss(champ)
        fid_val = _avg_fidelity(champ)
        det = _detect_count(champ)
        passport = champ.result.get("passport_id", "n/a")
        print(f"\n★  Champion: {champ_target}")
        print(
            f"   AIVSS {aivss_val:.1f}  ·  {tech_count} techniques"
            f"  ·  fidelity {fid_val:.2f}  ·  {det} DETECT hits"
        )
        print(f"   Passport: {passport}")


def discover_targets(base_dir: str, depth: int = 1) -> list:
    base = Path(base_dir)
    if not base.is_dir():
        return []
    if depth == 0:
        return [str(base)]
    return [str(c) for c in sorted(base.iterdir()) if c.is_dir() and not c.name.startswith(".")]


def run_wave(client: TASwarmClient, targets: list, max_concurrent: int, label: str = "") -> list:
    jobs: list = []
    total = len(targets)
    with ThreadPoolExecutor(max_workers=min(max_concurrent, total)) as pool:
        futures = {pool.submit(run_one, client, t): t for t in targets}
        done = 0
        for future in as_completed(futures):
            job = future.result()
            jobs.append(job)
            done += 1
            if job.status == "completed":
                gate = _export(job).get("gate", "?")
            else:
                gate = f"FAILED ({(job.error or '')[:30]})"
            prefix = f"[{label}] " if label else ""
            print(f"  {prefix}[{done}/{total}] {job.target} → {gate} ({job.elapsed:.0f}s)")
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fan out TAclaw jobs across multiple artifact targets and rank results."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--targets", nargs="+", metavar="PATH", help="Target directories")
    group.add_argument("--dir", metavar="DIR", help="Auto-discover subdirectories under DIR")
    group.add_argument("--targets-file", metavar="FILE", help="File with one target path per line")
    parser.add_argument("--depth", type=int, default=1, help="Discovery depth (--dir only, default 1)")
    parser.add_argument("--max-concurrent", type=int, default=MAX_CONCURRENT, metavar="N")
    parser.add_argument(
        "--wave2-on-block",
        action="store_true",
        help="Re-submit BLOCK targets for a second deeper pass after Wave 1",
    )
    parser.add_argument("--output", metavar="FILE", help="Write JSON report to FILE")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, metavar="URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, metavar="KEY")
    parser.add_argument("--timeout", type=int, default=JOB_TIMEOUT, help="Per-job poll timeout in seconds")
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: API key required (--api-key or $API_KEY)", file=sys.stderr)
        return 2

    # Resolve target list
    if args.targets:
        targets = args.targets
    elif args.dir:
        targets = discover_targets(args.dir, args.depth)
        if not targets:
            print(f"ERROR: no subdirectories found under {args.dir}", file=sys.stderr)
            return 2
        print(f"Discovered {len(targets)} targets under {args.dir}")
    else:
        lines = Path(args.targets_file).read_text().splitlines()
        targets = [l.strip() for l in lines if l.strip()]
        if not targets:
            print(f"ERROR: no targets in {args.targets_file}", file=sys.stderr)
            return 2

    print(f"Swarm: {len(targets)} targets  max_concurrent={args.max_concurrent}  timeout={args.timeout}s")

    client = TASwarmClient(args.api_url, args.api_key, timeout=args.timeout)

    # Wave 1
    print("\nWave 1")
    jobs = run_wave(client, targets, args.max_concurrent)

    # Wave 2 — optional, BLOCK targets only
    if args.wave2_on_block:
        block_targets = [
            j.target for j in jobs
            if j.status == "completed" and _export(j).get("gate") == "BLOCK"
        ]
        if block_targets:
            print(f"\nWave 2 — {len(block_targets)} BLOCK target(s) resubmitted for deeper analysis")
            wave2 = run_wave(client, block_targets, args.max_concurrent, label="W2")
            wave2_by_target = {j.target: j for j in wave2}
            jobs = [wave2_by_target.get(j.target, j) for j in jobs]
        else:
            print("\nWave 2 — no BLOCK targets; skipping")

    agg = aggregate(jobs)
    print_report(jobs, agg)

    if args.output:
        report = {
            "swarm_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "api_url": args.api_url,
            "targets_count": len(targets),
            "aggregate": agg,
            "jobs": [
                {
                    "target": j.target,
                    "job_id": j.job_id,
                    "status": j.status,
                    "gate": _export(j).get("gate") if j.status == "completed" else None,
                    "aivss": _aivss(j) if j.status == "completed" else None,
                    "technique_count": len(_techniques(j)) if j.status == "completed" else None,
                    "avg_fidelity": round(_avg_fidelity(j), 3) if j.status == "completed" else None,
                    "routing_mode": j.result.get("routing_mode") if j.status == "completed" else None,
                    "detect_hits": _detect_count(j) if j.status == "completed" else None,
                    "passport_id": j.result.get("passport_id") if j.status == "completed" else None,
                    "champion_score": round(champion_score(j), 3),
                    "elapsed": round(j.elapsed, 1),
                    "error": j.error,
                }
                for j in jobs
            ],
        }
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"\nReport saved: {args.output}")

    any_failed = any(j.status == "failed" for j in jobs)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
