#!/usr/bin/env python3
"""
bench_critics.py — TA Model Evaluation Benchmark

Two modes:

  --mode critics (default)
      Compares critic quality across models without re-running Analysis.
      Reads existing ground_truth.json, triggers MoE-only runs via REST API,
      scores depth / breadth / tokens / TATB / defensibility per critic × model.

  --mode brain
      Measures Brain + Workspace quality: Brier calibration, prediction recall,
      divergence % on hold-out archs. Run after rerun-moe to see if brain improved.

Corpus qualification:
  --qualify     Show estimated time/cost for all eligible archs and exit.
                Selects a representative BENCH corpus automatically if --archs not given:
                  · One arch per type (web_app/generic/iot/cloud/ai_system)
                  · Picks the arch with median complexity (node_count) per type
                  · Excludes duplicates (01_minimal_vulnerable_1, _2, _3)
                  · Excludes syn_* and 99_* archs
                  · Target: ≤ 8 archs, ≤ ~600k tokens total per model

Usage:
    # Qualify corpus first
    python3 scripts/bench_critics.py --qualify

    # Critic benchmark — two models side-by-side
    python3 scripts/bench_critics.py --models hetzner gemini_flash

    # Explicit archs
    python3 scripts/bench_critics.py \\
        --archs 21_agentic_ai_system 10_complex_enterprise 13_iot_architecture \\
        --models hetzner gemini_flash

    # Brain quality check (after rerun-moe)
    python3 scripts/bench_critics.py --mode brain

Model aliases:
    current         whatever is in .env right now (baseline)
    hetzner         Hetzner Qwen3.6-35B-A3B-FP8 (primary)
    gemini_flash    Google AI Studio gemini-3.6-flash (stable free tier, needs GEMINI_API_KEY)
    openrouter_free nvidia/nemotron-3.5-lightning:free (OR free model; thinking model, 1M ctx)

Gap trigger (critics mode): critic depth drop ≥ 2 pts → flagged for critic-gym.
"""

import argparse
import json
import os
import sys
import time
import shutil
import requests
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── ANSI ──────────────────────────────────────────────────────────────────────
RED    = "\033[31m"; GREEN  = "\033[32m"; YELLOW = "\033[33m"
BLUE   = "\033[34m"; CYAN   = "\033[36m"; BOLD   = "\033[1m"; RESET  = "\033[0m"

def _c(text, color): return f"{color}{text}{RESET}" if sys.stdout.isatty() else str(text)
def _col(v, hi=80, lo=60):
    return GREEN if v >= hi else YELLOW if v >= lo else RED

# ── Constants ─────────────────────────────────────────────────────────────────
HOLD_OUT_ARCHS = frozenset({
    "21_agentic_ai_system", "22_generic_ai_nodes",
    "20_data_pipeline", "14_container_orchestration", "01_minimal_vulnerable",
    "03_aws_3tier", "10_complex_enterprise", "08_dmz_architecture",
})

EXCLUDE_PREFIXES = ("syn_", "99_", "test_")
DUPLICATE_SUFFIXES = ("_1", "_2", "_3", "_4", "_5")  # versioned re-runs

CRITIC_NAMES = ["architect", "tester", "red_team", "purple_team", "blackhat"]

# Estimated tokens per MoE run when no prior run exists (based on 01_minimal_vulnerable baseline)
TOKENS_PER_NODE_ESTIMATE = 74_990 / 4   # ~18,748 tokens per node
MAX_BENCH_ARCHS = 8
MAX_BENCH_TOKENS = 600_000  # per model

MODEL_ALIASES = {
    # label → critic_model value sent in ExpertReviewRequest.
    # None = no override, uses .env defaults (whatever the API is configured with).
    "current":          None,
    "hetzner":          "openai/Qwen/Qwen3.6-35B-A3B-FP8",   # Hetzner 35B MoE (primary)
    "hetzner_27b":      "openai/Qwen3.8-27B",                  # Hetzner 27B dense — faster, smaller
    "gemini_flash":     "gemini/gemini-3.6-flash",              # Google AI Studio — stable, free tier
    "openrouter_free":  "openrouter/nvidia/nemotron-3.5-lightning:free",
    "cohere":           "openrouter/cohere/north-mini-code:free",  # non-thinking sparse MoE, agentic coding focus
    "glm":              "openrouter/z-ai/glm-5.2:free",            # reasoning model — use sequential + watch tester tokens
    "ox_alpha":         "openrouter/stealth/ox-alpha",              # was GLM-5.3 Flash (revealed on retirement 2026-08-26); gone
    "dots3":            "openrouter/dots-studio/dots-3-note-preview:free",  # 512K ctx, deprecates 2026-09-30
    "minimax":          "openrouter/minimax/minimax-m3:free",               # MiniMax M3 free
    "gemma":            "openrouter/google/gemma-4-31b-it:free",            # Gemma 4 31B free, 262K ctx
    "inkling":          "openrouter/thinkingmachines/inkling:free",         # GATED: OR restricts to approved agentic apps only (403 via direct API)
    "nemotron_nano":    "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # 30B/3B active, reasoning, 49 tok/s
    "nemotron_super":   "openrouter/nvidia/nemotron-3-super-120b-a12b:free",              # 120B/12B active MoE, 50 tok/s, 99.7% uptime
}


# ── Corpus qualification ───────────────────────────────────────────────────────

def _load_arch_meta(report_base: Path) -> list[dict]:
    """Read all real archs from report/ with type, complexity, token estimate."""
    rows = []
    for gt_path in sorted(report_base.glob("*/ground_truth.json")):
        arch = gt_path.parent.name
        # Exclude synthetic, versioned, and test archs
        if any(arch.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if any(arch.endswith(s) for s in DUPLICATE_SUFFIXES):
            continue
        try:
            gt = json.loads(gt_path.read_text())
            meta = gt.get("metadata", {})
            arch_type = meta.get("architecture_type", "generic")
            nodes     = meta.get("node_count", 0) or 0
            techs     = len({t for ap in gt.get("expected_attack_paths", [])
                              for t in ap.get("techniques", [])})
            moe_path = gt_path.parent / "07_moe_orchestrator.json"
            if moe_path.exists():
                moe = json.loads(moe_path.read_text())
                tokens = moe.get("pipeline_perf", {}).get("total_llm_tokens", 0) or 0
            else:
                tokens = round(nodes * TOKENS_PER_NODE_ESTIMATE)
            rows.append({
                "arch": arch, "arch_type": arch_type, "nodes": nodes,
                "techs": techs, "tokens_est": tokens,
                "is_hold_out": arch in HOLD_OUT_ARCHS,
                "has_moe": moe_path.exists(),
            })
        except Exception:
            pass
    return rows


def _select_bench_corpus(rows: list[dict], mode: str) -> list[dict]:
    """
    Auto-select a representative bench corpus.

    Critics mode: one arch per type at median complexity + the 2 AI hold-outs.
    Brain mode:   all HOLD_OUT_ARCHS that have ground_truth.json (honest eval set).
    """
    if mode == "brain":
        return [r for r in rows if r["is_hold_out"]]

    # Group by arch_type, pick median-complexity arch per type
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["arch_type"]].append(r)

    selected = []
    for atype, archs in sorted(by_type.items()):
        archs_sorted = sorted(archs, key=lambda x: x["nodes"])
        mid = archs_sorted[len(archs_sorted) // 2]
        selected.append(mid)

    # Always include both AI hold-outs (most distinctive type)
    ai_holdouts = [r for r in rows if r["is_hold_out"] and r["arch_type"] == "ai_system"]
    for r in ai_holdouts:
        if not any(s["arch"] == r["arch"] for s in selected):
            selected.append(r)

    # Cap at MAX_BENCH_ARCHS, prioritise hold-outs then by TTP richness
    selected.sort(key=lambda x: (-int(x["is_hold_out"]), -x["techs"]))
    selected = selected[:MAX_BENCH_ARCHS]

    # Token budget check — warn if over
    total_est = sum(r["tokens_est"] for r in selected)
    if total_est > MAX_BENCH_TOKENS:
        # Drop lowest-TTP non-hold-out until under budget
        non_hold = [r for r in selected if not r["is_hold_out"]]
        non_hold.sort(key=lambda x: x["techs"])
        for drop in non_hold:
            selected.remove(drop)
            total_est = sum(r["tokens_est"] for r in selected)
            if total_est <= MAX_BENCH_TOKENS:
                break

    return selected


def cmd_qualify(report_base: Path, mode: str):
    """Print corpus qualification table and exit."""
    rows = _load_arch_meta(report_base)
    selected = _select_bench_corpus(rows, mode)
    selected_names = {r["arch"] for r in selected}

    total_est = sum(r["tokens_est"] for r in rows)
    sel_est   = sum(r["tokens_est"] for r in selected)
    est_min_per_arch = 12   # minutes per MoE run (free tier)

    print(f"\n{BOLD}Corpus Qualification — {mode} mode{RESET}")
    print(f"{'─'*72}")
    print(f"{'Arch':<35} {'Type':<12} {'N':>4} {'TTPs':>5} {'Tok est':>9}  {'Hold':>4}  {'Sel':>4}")
    print(f"{'─'*72}")
    for r in sorted(rows, key=lambda x: x["arch"]):
        sel_mark = _c("  ✓ ", GREEN) if r["arch"] in selected_names else "    "
        hold_mark = "HOLD" if r["is_hold_out"] else "    "
        tok_str = f"{r['tokens_est']//1000}k" if r['tokens_est'] >= 1000 else str(r['tokens_est'])
        print(f"{r['arch']:<35} {r['arch_type']:<12} {r['nodes']:>4} {r['techs']:>5} "
              f"{tok_str:>9}  {hold_mark}  {sel_mark}")

    print(f"{'─'*72}")
    print(f"Full corpus: {len(rows)} archs  ~{total_est//1000}k tokens/model  "
          f"~{len(rows)*est_min_per_arch//60}h{len(rows)*est_min_per_arch%60}m/model")
    print(f"{_c('Bench corpus', CYAN)}: {len(selected)} archs  "
          f"~{sel_est//1000}k tokens/model  "
          f"~{len(selected)*est_min_per_arch}m/model")
    print(f"\nSelected: {', '.join(r['arch'] for r in selected)}")
    print(f"\nRun with: python3 scripts/bench_critics.py --mode {mode} "
          f"--archs {' '.join(r['arch'] for r in selected)}")


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _score_ttp(moe: dict) -> dict:
    moe_conf = (moe or {}).get("confidence", {})
    base  = moe_conf.get("base",  0) or 0
    final = moe_conf.get("final", 0) or 0
    lift  = (final - base) / 100 if final is not None and base is not None else 0
    return {"score": max(0, min(100, round(50 + lift * 500))), "moe_lift_pp": round(lift*100, 1)}

def _score_plan(moe: dict) -> dict:
    sm = (moe or {}).get("scrum_master", {})
    actions = sm.get("action_items", []) if sm else []
    high  = sum(1 for a in actions if (a.get("priority") or "").upper() in ("HIGH", "CRITICAL"))
    total = len(actions)
    if total == 0:
        return {"score": 0, "actions": 0, "high_priority": 0}
    return {"score": min(100, round((high/total)*60 + min(total, 10)*4)),
            "actions": total, "high_priority": high}

def _score_overall(ttp: dict, plan: dict) -> int:
    return round(ttp["score"] * 0.6 + plan["score"] * 0.4)

def _breadth(moe: dict) -> dict:
    ts = moe.get("technique_support", {})
    per = defaultdict(set)
    for tid, info in ts.items():
        for c in info.get("critics", []):
            per[c].add(tid)
    all_ttps = set(ts.keys())
    unique_per = {}
    for c, ttps in per.items():
        others = set().union(*(per[o] for o in per if o != c))
        unique_per[c] = len(ttps - others)
    return {"total_union": len(all_ttps),
            "per_critic": {c: len(v) for c, v in per.items()},
            "unique_per_critic": unique_per}

def _sm_quality_score(sm_report: dict) -> Optional[float]:
    """Quality composite for ScrumMaster on /12 scale.

    Measures actual plan output rather than inherited MoE confidence:
      - Coverage  (50%): action items as fraction of impediments found
      - Breadth   (25%): structural + immediate tiers both present
      - Completeness (25%): fraction of items with first_step filled in
    """
    ap   = sm_report.get("action_plan", [])
    imps = sm_report.get("impediments_found", [])
    if not ap:
        return 0.0
    n_imp = max(1, len(imps))
    coverage     = min(1.0, len(ap) / n_imp)
    tiers        = {(a.get("tier") or "").lower() for a in ap}
    breadth      = 1.0 if ("structural" in tiers and "immediate" in tiers) else 0.5
    first_steps  = sum(1 for a in ap if a.get("first_step", "").strip())
    completeness = first_steps / len(ap)
    raw = (coverage * 0.50 + breadth * 0.25 + completeness * 0.25) * 12
    return round(raw, 1)


def _depth(moe: dict, sm_report: Optional[dict] = None) -> dict:
    ev = moe.get("expert_validations", {})
    result = {name: round(ev.get(name, {}).get("original_score", 0) / 100 * 12, 1)
              if ev.get(name, {}).get("original_score") is not None else None
              for name in CRITIC_NAMES}
    # ScrumMaster: use quality composite when the full SM report is available;
    # fall back to inherited final_confidence for backwards compatibility.
    if sm_report:
        result["scrum_master"] = _sm_quality_score(sm_report)
    else:
        sm_conf = (moe.get("scrum_master") or {}).get("final_confidence")
        result["scrum_master"] = round(sm_conf / 100 * 12, 1) if sm_conf is not None else None
    return result

def _tokens(moe: dict) -> dict:
    pp = moe.get("pipeline_perf", {})
    cp = pp.get("critics", {})
    per_critic = {name: {
        "total":      cp.get(name, {}).get("llm_tokens", 0),
        "prompt":     cp.get(name, {}).get("llm_prompt_tokens", 0),
        "completion": cp.get(name, {}).get("llm_completion_tokens", 0),
        "latency_s":  cp.get(name, {}).get("llm_latency_s", 0.0),
        "model":      cp.get(name, {}).get("llm_model", ""),
    } for name in CRITIC_NAMES}
    # ScrumMaster token usage is stored under 'orchestrator' in pipeline_perf
    orch = cp.get("orchestrator", {})
    per_critic["scrum_master"] = {
        "total":      orch.get("llm_tokens", 0),
        "prompt":     orch.get("llm_prompt_tokens", 0),
        "completion": orch.get("llm_completion_tokens", 0),
        "latency_s":  orch.get("llm_latency_s", 0.0),
        "model":      orch.get("llm_model", ""),
    }
    return {
        "total_panel": pp.get("total_llm_tokens", 0),
        "per_critic": per_critic,
    }

def _defensibility(dest_dir: Path) -> Optional[float]:
    gs = dest_dir / "governance_signals.json"
    if not gs.exists():
        return None
    try:
        return json.loads(gs.read_text()).get("aivss", {}).get("overall", {}).get("composite")
    except Exception:
        return None

# ── Brain mode scoring ────────────────────────────────────────────────────────

def _score_brain(report_base: Path, arch: str) -> dict:
    """
    Compare Brain predictions vs actual harness output for one arch.
    Requires ground_truth.json + 07_moe_orchestrator.json.
    Returns: prediction_recall, divergence_pct, brier_proxy.
    """
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT))

    try:
        from chatbot.modules.ta_brain_query import query_brain
    except ImportError:
        return {"error": "ta_brain_query not importable"}

    gt_path  = report_base / arch / "ground_truth.json"
    moe_path = report_base / arch / "07_moe_orchestrator.json"
    if not gt_path.exists():
        return {"error": "no ground_truth.json"}

    gt  = json.loads(gt_path.read_text())
    moe = json.loads(moe_path.read_text()) if moe_path.exists() else {}

    # Actual TTPs from harness (ground truth + MoE technique_support)
    harness_ttps = {t for ap in gt.get("expected_attack_paths", [])
                    for t in ap.get("techniques", [])}
    harness_ttps |= set(moe.get("technique_support", {}).keys())

    # Brain prediction
    try:
        brain_result = query_brain(arch_name=arch, mode="infer")
        brain_ttps   = set(brain_result.get("predictions", {}).get("techniques", []))
        brain_conf   = brain_result.get("confidence", 0.0)
        had_match    = brain_result.get("had_match", False)
    except Exception as e:
        return {"error": str(e)}

    if not harness_ttps:
        return {"error": "no harness TTPs to compare against"}

    # Prediction recall: how many harness TTPs did brain predict?
    overlap = brain_ttps & harness_ttps
    recall  = round(len(overlap) / len(harness_ttps) * 100) if harness_ttps else 0

    # Divergence %: how much of workspace findings were NOT in brain predictions
    workspace_only = harness_ttps - brain_ttps
    divergence_pct = round(len(workspace_only) / len(harness_ttps) * 100) if harness_ttps else 100

    # Brier proxy: squared error of brain confidence vs binary outcome (did it match?)
    # match = recall >= 50%
    outcome = 1.0 if recall >= 50 else 0.0
    brier   = round((brain_conf - outcome) ** 2, 4)

    return {
        "arch":           arch,
        "had_match":      had_match,
        "brain_conf":     brain_conf,
        "brain_ttps":     len(brain_ttps),
        "harness_ttps":   len(harness_ttps),
        "overlap":        len(overlap),
        "prediction_recall": recall,
        "divergence_pct": divergence_pct,
        "brier":          brier,
    }


def cmd_brain(report_base: Path, archs: list[str], output_dir: Path):
    """Brain quality benchmark — no model override needed, fully deterministic."""
    run_id  = time.strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"brain_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{BOLD}Brain Quality Benchmark — {run_id}{RESET}")
    print(f"Archs: {', '.join(archs)}\n")

    results = []
    for arch in archs:
        r = _score_brain(report_base, arch)
        results.append(r)
        if "error" in r:
            print(f"  {arch:<35} {_c('ERROR: ' + r['error'], RED)}")
        else:
            rc = _c(f"{r['prediction_recall']:>3}%", _col(r['prediction_recall'], 60, 40))
            dv = _c(f"{r['divergence_pct']:>3}%",
                    RED if r['divergence_pct'] >= 70 else YELLOW if r['divergence_pct'] >= 40 else GREEN)
            br = _c(f"{r['brier']:.3f}", RED if r['brier'] > 0.25 else YELLOW if r['brier'] > 0.1 else GREEN)
            hm = "✓ match" if r["had_match"] else "~ type-level"
            print(f"  {arch:<35} recall={rc}  divergence={dv}  brier={br}  [{hm}]")

    valid = [r for r in results if "error" not in r]
    if valid:
        avg_recall = round(statistics.mean(r["prediction_recall"] for r in valid))
        avg_div    = round(statistics.mean(r["divergence_pct"]    for r in valid))
        avg_brier  = round(statistics.mean(r["brier"]             for r in valid), 4)
        print(f"\n  {'Avg':<35} recall={avg_recall:>3}%  divergence={avg_div:>3}%  brier={avg_brier:.3f}")
        print(f"\n  {_c('Interpretation:', BOLD)}")
        print(f"    recall ≥ 60% = Brain is predicting most of what harness finds")
        print(f"    divergence ≥ 70% = Architecture is novel — workspace doing the heavy lifting")
        print(f"    brier ≤ 0.10 = Brain confidence is well calibrated")

    (run_dir / "brain_results.json").write_text(json.dumps(results, indent=2))
    print(f"\n  Saved: {run_dir / 'brain_results.json'}")


# ── REST API helpers ──────────────────────────────────────────────────────────

def _api_key() -> str:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return os.environ.get("API_KEY", "")

_CRITIC_CACHE_FILES = [
    "04_architect_critique.json",
    "05_tester_critique.json",
    "06_red_team_critique.json",
    "06b_purple_team_critique.json",
    "06c_blackhat_critique.json",
    "07_moe_orchestrator.json",   # also clear synthesis so stale file isn't read on CriticStage failure
    "08_scrum_master.json",
]

def _clear_critiques(arch: str, report_base: Path) -> None:
    """Delete cached critic critique files so MoE re-runs them fresh."""
    arch_dir = report_base / arch
    for f in _CRITIC_CACHE_FILES:
        p = arch_dir / f
        if p.exists():
            p.unlink()

def _trigger_expert_review(
    api_url: str, arch: str, api_key: str, timeout: int,
    critic_model: str | None = None,
    critic_mode: str = "partial_parallel",
) -> None:
    headers = {"TM-API-KEY": api_key, "Content-Type": "application/json"}
    body: dict = {"arch_name": arch, "critic_mode": critic_mode, "run_blackhat": True}
    if critic_model:
        body["critic_model"] = critic_model
    r = requests.post(f"{api_url}/api/v1/jobs/expert-review",
                      json=body, headers=headers, timeout=30)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = requests.get(f"{api_url}/api/v1/jobs/{job_id}/status", headers=headers, timeout=10).json()
        status = s.get("status", "")
        if status == "completed":
            return
        if status in ("failed", "error"):
            raise RuntimeError(f"Job {job_id} failed: {s.get('error', '?')}")
        time.sleep(8)
    raise TimeoutError(f"Job {job_id} timed out after {timeout}s")

# ── Critics mode — single arch × model run ────────────────────────────────────

def run_single(api_url: str, arch: str, model_alias: str,
               report_base: Path, run_dir: Path, api_key: str, timeout: int,
               critic_mode: str = "partial_parallel") -> dict:
    print(f"  → {_c(arch, CYAN)} × {_c(model_alias, BLUE)}")
    critic_model = MODEL_ALIASES.get(model_alias)  # None = use .env defaults
    # Clear cached critiques so the job re-runs all critics with the requested model
    _clear_critiques(arch, report_base)
    t0 = time.time()
    try:
        _trigger_expert_review(api_url, arch, api_key, timeout, critic_model=critic_model,
                               critic_mode=critic_mode)
    except Exception as e:
        print(f"    {_c('ERROR', RED)}: {e}")
        return {"error": str(e)}
    elapsed = time.time() - t0

    src_moe = report_base / arch / "07_moe_orchestrator.json"
    src_gov = report_base / arch / "governance_signals.json"
    dest    = run_dir / arch / model_alias
    dest.mkdir(parents=True, exist_ok=True)

    if not src_moe.exists():
        return {"error": "07_moe_orchestrator.json not found"}

    moe = json.loads(src_moe.read_text())
    shutil.copy2(src_moe, dest / "07_moe_orchestrator.json")
    if src_gov.exists():
        shutil.copy2(src_gov, dest / "governance_signals.json")

    gt_path = report_base / arch / "ground_truth.json"
    gt = json.loads(gt_path.read_text()) if gt_path.exists() else {}

    sm_path = report_base / arch / "08_scrum_master.json"
    sm_report = json.loads(sm_path.read_text()) if sm_path.exists() else None

    ttp  = _score_ttp(moe)
    plan = _score_plan(moe)
    result = {
        "arch": arch, "model": model_alias,
        "elapsed_s": round(elapsed, 1),
        "depth":       _depth(moe, sm_report),
        "breadth":     _breadth(moe),
        "tokens":      _tokens(moe),
        "tatb":        {"ttp": ttp, "plan": plan, "overall": _score_overall(ttp, plan)},
        "defensibility": _defensibility(dest),
    }
    (dest / "bench_result.json").write_text(json.dumps(result, indent=2))
    return result

# ── Gap detection ─────────────────────────────────────────────────────────────

def detect_gaps(results: dict, m0: str, m1: str) -> list:
    gaps = []
    for arch, models in results.items():
        ra, rb = models.get(m0, {}), models.get(m1, {})
        if "error" in ra or "error" in rb:
            continue
        for critic in CRITIC_NAMES:
            da = ra.get("depth", {}).get(critic)
            db = rb.get("depth", {}).get(critic)
            if da is not None and db is not None and (da - db) >= 2:
                gaps.append({"arch": arch, "critic": critic,
                             "score_a": da, "score_b": db, "drop": round(da - db, 1)})
    return gaps

# ── Pretty diff table ─────────────────────────────────────────────────────────

def print_diff_table(results: dict, models: list):
    def _fd(d):
        if d is None: return "   —  "
        c = GREEN if d >= 10 else YELLOW if d >= 7 else RED
        return _c(f"{d:4.1f}", c)

    def _ft(t): return f"{t//1000}k" if t >= 1000 else str(t)

    def _delta(a, b, higher_better=True):
        if a is None or b is None: return "  — "
        d = b - a
        if d == 0: return "  0 "
        s = "+" if d > 0 else ""
        c = GREEN if (d > 0) == higher_better else RED
        return _c(f"{s}{d:.1f}", c)

    m0 = models[0]
    m1 = models[1] if len(models) >= 2 else None

    for arch, arch_r in results.items():
        r0 = arch_r.get(m0, {})
        r1 = arch_r.get(m1, {}) if m1 else {}
        print(f"\n{BOLD}{'─'*72}{RESET}")
        print(f"{BOLD}{arch}{RESET}  "
              f"({_c(m0, BLUE)}{' vs ' + _c(m1, CYAN) if m1 else ''})")
        print(f"{'─'*72}")

        if m1:
            print(f"{'Critic':<14} {'Dep':>5}/{m0[:6]:<6} {'Dep':>5}/{m1[:6]:<6} "
                  f"{'Δdep':>5}  {'Tok/'+m0[:4]:>8} {'Tok/'+m1[:4]:>8}  "
                  f"{'in/out':>8}  {'Uniq':>5}/{m0[:4]:<4} {'Uniq':>5}/{m1[:4]:<4}")
            print(f"{'─'*72}")
            for cr in CRITIC_NAMES:
                da  = r0.get("depth", {}).get(cr)
                db  = r1.get("depth", {}).get(cr)
                ta  = r0.get("tokens", {}).get("per_critic", {}).get(cr, {})
                tb  = r1.get("tokens", {}).get("per_critic", {}).get(cr, {})
                ua  = r0.get("breadth", {}).get("unique_per_critic", {}).get(cr, 0)
                ub  = r1.get("breadth", {}).get("unique_per_critic", {}).get(cr, 0)
                inp = tb.get("prompt", 0); out = tb.get("completion", 0)
                io  = f"{_ft(inp)}in/{_ft(out)}out" if (inp or out) else "  — "
                gap = _c(" ← GAP", RED) if da and db and (da - db) >= 2 else ""
                print(f"{cr:<14} {_fd(da):>5}       {_fd(db):>5}       "
                      f"{_delta(da, db):>5}  {_ft(ta.get('total',0)):>8} {_ft(tb.get('total',0)):>8}  "
                      f"{io:>8}  {ua:>5}       {ub:>5}{gap}")

            print(f"{'─'*72}")
            b0 = r0.get("breadth", {}).get("total_union", 0)
            b1 = r1.get("breadth", {}).get("total_union", 0)
            t0 = r0.get("tokens", {}).get("total_panel", 0)
            t1 = r1.get("tokens", {}).get("total_panel", 0)
            ta0 = r0.get("tatb", {}).get("overall", 0)
            ta1 = r1.get("tatb", {}).get("overall", 0)
            d0 = r0.get("defensibility"); d1 = r1.get("defensibility")
            print(f"{'Breadth (TTP union)':<30} {b0:>6}       {b1:>6}  Δ {_delta(b0, b1)}")
            print(f"{'Total tokens':<30} {_ft(t0):>6}       {_ft(t1):>6}  Δ {_delta(t0, t1, False)}")
            print(f"{'TATB overall':<30} {ta0:>6}       {ta1:>6}  Δ {_delta(ta0, ta1)}")
            if d0 is not None or d1 is not None:
                d0s = f"{d0:.2f}" if d0 else " — "
                d1s = f"{d1:.2f}" if d1 else " — "
                print(f"{'Defensibility (AIVSS)':<30} {d0s:>6}       {d1s:>6}  Δ {_delta(d0, d1)}")
        else:
            # Single model — absolute numbers
            for cr in CRITIC_NAMES:
                d = r0.get("depth", {}).get(cr)
                t = r0.get("tokens", {}).get("per_critic", {}).get(cr, {})
                inp = t.get("prompt", 0); out = t.get("completion", 0)
                print(f"  {cr:<14} {_fd(d)}  tok={_ft(t.get('total',0))}  "
                      f"in={_ft(inp)} out={_ft(out)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode",     default="critics", choices=["critics", "brain"])
    ap.add_argument("--archs",    nargs="*", default=None,
                    help="Arch names to benchmark. Omit to auto-select (uses qualify logic).")
    ap.add_argument("--models",   nargs="+", default=["current"],
                    help="Model aliases: current hetzner hetzner_27b gemini_flash openrouter_free cohere glm ox_alpha dots3 minimax gemma inkling nemotron_nano nemotron_super")
    ap.add_argument("--critic-mode", default="partial_parallel",
                    choices=["partial_parallel", "sequential", "parallel", "auto"],
                    help="MoE critic execution mode (default: partial_parallel). Use sequential for rate-limited providers.")
    ap.add_argument("--qualify",  action="store_true",
                    help="Show corpus qualification table and exit (no runs)")
    ap.add_argument("--combine",  nargs="+", metavar="SUMMARY",
                    help="Merge N bench_summary.json files from separate runs into one report")
    ap.add_argument("--out-dir",  default=None,
                    help="Output directory for --combine report")
    ap.add_argument("--api-url",  default="http://localhost:8000")
    ap.add_argument("--output",   default="bench_results")
    ap.add_argument("--timeout",  type=int, default=1500)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    # --combine: merge existing summaries and exit
    if args.combine:
        try:
            from scripts.bench_report import generate_combined as _gc
        except ImportError:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "bench_report", ROOT / "scripts" / "bench_report.py")
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            _gc = mod.generate_combined
        import datetime
        out_dir = Path(args.out_dir) if args.out_dir else (
            ROOT / "bench_results" / f"combined_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        rp = _gc(args.combine, out_dir)
        print(f"Combined report: {rp}")
        return

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    report_base = Path(args.report_dir) if args.report_dir else ROOT / "report"
    output_dir  = ROOT / args.output

    # Qualify and exit
    if args.qualify:
        cmd_qualify(report_base, args.mode)
        return

    # Resolve archs
    if args.archs:
        archs = args.archs
    else:
        rows   = _load_arch_meta(report_base)
        archs  = [r["arch"] for r in _select_bench_corpus(rows, args.mode)]
        print(f"{_c('Auto-selected bench corpus:', CYAN)} {', '.join(archs)}")

    # Validate
    for arch in archs:
        if not (report_base / arch / "ground_truth.json").exists():
            print(_c(f"ERROR: no ground_truth.json for {arch} — run analysis first", RED))
            sys.exit(1)

    # Brain mode — no API, no model override
    if args.mode == "brain":
        cmd_brain(report_base, archs, output_dir)
        return

    # Critics mode
    api_key = _api_key()
    if not api_key:
        print(_c("ERROR: API_KEY not set in .env", RED))
        sys.exit(1)

    run_id  = time.strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Estimate time/cost upfront
    rows     = _load_arch_meta(report_base)
    row_map  = {r["arch"]: r for r in rows}
    est_tok  = sum(row_map.get(a, {}).get("tokens_est", 0) for a in archs)
    est_min  = len(archs) * len(args.models) * 12
    print(f"\n{BOLD}TA Critic Benchmark — run {run_id}{RESET}")
    print(f"Archs ({len(archs)}):  {', '.join(archs)}")
    print(f"Models ({len(args.models)}): {', '.join(args.models)}")
    print(f"Est. tokens: ~{est_tok*len(args.models)//1000}k total  "
          f"Est. time: ~{est_min}m\n")

    results = {}

    for arch in archs:
        results[arch] = {}
        for model_alias in args.models:
            results[arch][model_alias] = run_single(
                api_url=args.api_url, arch=arch, model_alias=model_alias,
                report_base=report_base, run_dir=run_dir,
                api_key=api_key, timeout=args.timeout,
                critic_mode=args.critic_mode,
            )

    print_diff_table(results, args.models)

    # Gap report
    if len(args.models) >= 2:
        gaps = detect_gaps(results, args.models[0], args.models[1])
        if gaps:
            print(f"\n{BOLD}{_c('GAP REPORT', RED)}{RESET} — critics to address with critic-gym:")
            for g in sorted(gaps, key=lambda x: -x["drop"]):
                print(f"  {g['arch']} / {_c(g['critic'], YELLOW)}: "
                      f"{g['score_a']:.1f} → {g['score_b']:.1f}  "
                      f"(drop {_c(str(g['drop']), RED)} pts on {args.models[1]})")
            print(f"\n  Next: /critic-gym {gaps[0]['critic']} --model {args.models[1]}")
        else:
            print(f"\n{_c('No depth gaps detected (all critics within 2 pts).', GREEN)}")

    model_strings = {
        alias: (MODEL_ALIASES[alias] or "(provider default)") if alias in MODEL_ALIASES else alias
        for alias in args.models
    }
    summary = {"run_id": run_id, "mode": "critics", "archs": archs,
               "models": args.models, "model_strings": model_strings, "results": results}
    sp = run_dir / "bench_summary.json"
    sp.write_text(json.dumps(summary, indent=2))
    print(f"\nResults: {sp}")

    # Auto-generate HTML visual report
    try:
        from scripts.bench_report import generate as _gen_report
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bench_report", ROOT / "scripts" / "bench_report.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _gen_report = mod.generate
    rp = _gen_report(sp)
    print(f"Report:  {rp}")


if __name__ == "__main__":
    main()
