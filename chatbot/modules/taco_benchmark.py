"""
taco_benchmark.py — 7-dimension TACO quality scorer.

Scores three TACO modes against ground_truth.json for each architecture:

  workspace  — TACOminiRAG alone (deterministic graph search; no brain KG)
  taco_brain — TACOminiBrain alone (pattern KG; no RAG)
  taco_rag   — brain + RAG combined (union of predictions)

Seven dimensions:
  1. Threat-Relevant        recall of ground-truth techniques         weight 0.20
  2. TTP-Accurate           precision vs confirmed technique list      weight 0.20
  3. Risk-Defensible        control coverage of missing controls       weight 0.15
  4. Plan-Actionable        SM action plan quality (None if no SM)     weight 0.10
  5. Groundedness           weighted T-ID + control coverage           weight 0.15
  6. Confidence-Calibration alignment of reported vs actual accuracy   weight 0.10
  7. CISO-Utility           five proxy signals for actionability       weight 0.10

All scores are 0–100. overall = weighted average (None dims excluded from denominator).

Golden dataset for hold-out evaluation:
  from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

_WEIGHTS: Dict[str, float] = {
    "threat_relevant":        0.20,
    "ttp_accurate":           0.20,
    "risk_defensible":        0.15,
    "plan_actionable":        0.10,
    "groundedness":           0.15,
    "confidence_calibration": 0.10,
    "ciso_utility":           0.10,
}


def _default_report_dir() -> Path:
    try:
        from chatbot.config import get_settings  # noqa: PLC0415
        rd = get_settings().system.report_dir
        return Path(rd) if Path(rd).is_absolute() else ROOT / rd
    except Exception:
        return ROOT / "report"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkScore:
    arch_name: str
    mode: str                            # "workspace" | "taco_brain" | "taco_rag"
    threat_relevant: Optional[float]     # 0–100
    ttp_accurate: Optional[float]        # 0–100
    risk_defensible: Optional[float]     # 0–100
    plan_actionable: Optional[float]     # 0–100; None when no SM JSON exists
    groundedness: float                  # 0–100
    confidence_calibration: float        # 0–100
    ciso_utility: float                  # 0–100
    overall: float                       # weighted average, None dims excluded
    duration_ms: int
    hop_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "arch_name": self.arch_name,
            "mode": self.mode,
            "scores": {
                "threat_relevant": self.threat_relevant,
                "ttp_accurate": self.ttp_accurate,
                "risk_defensible": self.risk_defensible,
                "plan_actionable": self.plan_actionable,
                "groundedness": self.groundedness,
                "confidence_calibration": self.confidence_calibration,
                "ciso_utility": self.ciso_utility,
                "overall": self.overall,
            },
            "duration_ms": self.duration_ms,
            "hop_summary": self.hop_summary,
        }


@dataclass
class BenchmarkResult:
    arch_name: str
    workspace: BenchmarkScore
    taco_brain: BenchmarkScore
    taco_rag: BenchmarkScore
    scored_at: str

    def to_dict(self) -> dict:
        return {
            "arch_name": self.arch_name,
            "series": {
                "workspace": self.workspace.to_dict(),
                "taco_brain": self.taco_brain.to_dict(),
                "taco_rag": self.taco_rag.to_dict(),
            },
            "scored_at": self.scored_at,
        }


# ---------------------------------------------------------------------------
# Ground-truth helpers
# ---------------------------------------------------------------------------

def _actual_techs(gt: dict) -> Set[str]:
    techs = gt.get("techniques") or []
    if isinstance(techs, dict):
        return set(techs.keys())
    return {str(t) for t in techs}


def _confirmed_techs(gt: dict) -> Set[str]:
    tv = gt.get("technique_validation") or []
    return {
        str(v.get("technique") or v.get("id") or "")
        for v in tv
        if v.get("valid") is True
    } - {""}


def _actual_missing_controls(gt: dict) -> Set[str]:
    return {c.lower() for c in (gt.get("controls_missing") or [])} - {""}


# ---------------------------------------------------------------------------
# Dimension scorers (static)
# ---------------------------------------------------------------------------

def _dim_threat_relevant(predicted_techs: Set[str], gt: dict) -> float:
    actual = _actual_techs(gt)
    if not actual:
        return 50.0
    return float(min(100, round(len(predicted_techs & actual) / len(actual) * 100)))


def _dim_ttp_accurate(predicted_techs: Set[str], gt: dict) -> float:
    if not predicted_techs:
        return 50.0
    confirmed = _confirmed_techs(gt)
    if not confirmed:
        return 50.0
    return float(min(100, round(len(predicted_techs & confirmed) / len(predicted_techs) * 100)))


def _dim_risk_defensible(predicted_controls: Set[str], gt: dict) -> float:
    actual_missing = _actual_missing_controls(gt)
    if not actual_missing:
        return 50.0
    return float(min(100, round(len(predicted_controls & actual_missing) / len(actual_missing) * 100)))


def _dim_groundedness(
    predicted_techs: Set[str],
    predicted_controls: Set[str],
    gt: dict,
) -> float:
    actual_techs = _actual_techs(gt)
    actual_missing = _actual_missing_controls(gt)
    tech_cov = len(predicted_techs & actual_techs) / max(1, len(actual_techs))
    ctrl_cov = len(predicted_controls & actual_missing) / max(1, len(actual_missing))
    return float(min(100, round((tech_cov * 0.60 + ctrl_cov * 0.40) * 100)))


def _dim_confidence_calibration(reported_confidence: float, groundedness: float) -> float:
    actual_acc = groundedness / 100.0
    error = abs(reported_confidence - actual_acc)
    return float(max(0.0, round(100.0 - error * 200.0)))


def _dim_ciso_utility(hop_summary: dict, gt: dict) -> bool:
    """Return score 0–100 based on 5 proxy signals."""
    brain_preds = hop_summary.get("brain_predictions") or {}
    signals = [
        float(brain_preds.get("aivss_floor") or 0.0) > 0,
        len(hop_summary.get("predicted_controls") or []) >= 1,
        len(hop_summary.get("predicted_techs") or []) >= 1,
        bool(hop_summary.get("had_graph_hit", False)),
        float(hop_summary.get("final_confidence") or 0.0) > 0.0,
    ]
    return float(round(sum(signals) / 5 * 100))


def _load_plan_actionable(arch_dir: Path) -> Optional[float]:
    """Load Plan-Actionable score from SM JSON if available."""
    sm_path = arch_dir / "08_scrum_master.json"
    if not sm_path.exists():
        return None
    try:
        with open(sm_path) as f:
            sm = json.load(f)
        action_items = sm.get("action_plan") or sm.get("action_items") or []
        if not action_items:
            return 50.0
        # Proxy: % of action items that reference a T-ID or control name
        scored = sum(
            1 for item in action_items
            if isinstance(item, dict) and (
                item.get("technique_id") or item.get("control") or
                any(c in str(item).upper() for c in ["T1", "M1", "AC-", "AU-", "CM-"])
            )
        )
        return float(min(100, round(scored / len(action_items) * 100)))
    except Exception:
        return None


def _compute_overall(s: BenchmarkScore) -> float:
    total_w = total_s = 0.0
    for dim, w in _WEIGHTS.items():
        v = getattr(s, dim, None)
        if v is not None:
            total_s += float(v) * w
            total_w += w
    return round(total_s / total_w) if total_w > 0 else 0.0


# ---------------------------------------------------------------------------
# TACOBenchmark
# ---------------------------------------------------------------------------

class TACOBenchmark:
    """7-dimension TACO quality scorer against ground_truth.json."""

    def __init__(self, report_dir: Optional[Path] = None) -> None:
        self.report_dir = report_dir or _default_report_dir()

    # ── public surface ───────────────────────────────────────────────────

    def score_arch(self, arch_name: str) -> BenchmarkResult:
        """Score all three series for one architecture."""
        arch_dir = self.report_dir / arch_name
        gt_path = arch_dir / "ground_truth.json"
        if not gt_path.exists():
            raise FileNotFoundError(f"ground_truth.json not found for {arch_name}")
        with open(gt_path) as f:
            gt = json.load(f)

        ws = self._score_workspace(arch_name, gt, arch_dir)
        tb = self._score_taco_brain(arch_name, gt, arch_dir)
        tr = self._score_taco_rag(arch_name, gt, arch_dir)

        return BenchmarkResult(
            arch_name=arch_name,
            workspace=ws,
            taco_brain=tb,
            taco_rag=tr,
            scored_at=datetime.now(timezone.utc).isoformat(),
        )

    def score_hold_out(self) -> List[BenchmarkResult]:
        """Score all HOLD_OUT_ARCHS; skip archs with no ground_truth.json."""
        from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS  # noqa: PLC0415
        results = []
        for arch_name in sorted(HOLD_OUT_ARCHS):
            try:
                results.append(self.score_arch(arch_name))
            except FileNotFoundError:
                logger.warning("Skipping %s — no ground_truth.json", arch_name)
            except Exception:
                logger.exception("score_arch failed for %s", arch_name)
        return results

    # ── mode runners ─────────────────────────────────────────────────────

    def _score_workspace(self, arch_name: str, gt: dict, arch_dir: Path) -> BenchmarkScore:
        import time as _time
        t0 = _time.monotonic()

        predicted_techs: Set[str] = set()
        predicted_controls: Set[str] = set()
        had_hit = False

        try:
            from chatbot.modules.graph_index import ThreatGraph  # noqa: PLC0415
            g = ThreatGraph.build([arch_name], self.report_dir)
            answer = g.query(f"critical paths in {arch_name}")
            had_hit = answer is not None
            predicted_techs = {
                t
                for ap in g.attack_paths.values()
                if ap.arch == arch_name
                for t in ap.techniques
            }
            predicted_controls = {c.lower() for c in g.arch_controls_missing.get(arch_name, [])}
        except Exception:
            logger.exception("Workspace graph build failed for %s", arch_name)

        duration_ms = int((_time.monotonic() - t0) * 1000)
        reported_conf = 0.80 if had_hit else 0.50

        hop_summary = {
            "predicted_techs": list(predicted_techs),
            "predicted_controls": list(predicted_controls),
            "had_graph_hit": had_hit,
            "final_confidence": reported_conf,
            "brain_predictions": {},
        }

        tr = _dim_threat_relevant(predicted_techs, gt)
        ta = _dim_ttp_accurate(predicted_techs, gt)
        rd = _dim_risk_defensible(predicted_controls, gt)
        pa = _load_plan_actionable(arch_dir)
        gr = _dim_groundedness(predicted_techs, predicted_controls, gt)
        cc = 50.0   # deterministic retriever: confidence calibration not meaningful
        cu = _dim_ciso_utility(hop_summary, gt)

        s = BenchmarkScore(
            arch_name=arch_name, mode="workspace",
            threat_relevant=tr, ttp_accurate=ta, risk_defensible=rd,
            plan_actionable=pa, groundedness=gr, confidence_calibration=cc,
            ciso_utility=cu, overall=0.0, duration_ms=duration_ms, hop_summary=hop_summary,
        )
        s.overall = _compute_overall(s)
        return s

    def _score_taco_brain(self, arch_name: str, gt: dict, arch_dir: Path) -> BenchmarkScore:
        import time as _time
        from chatbot.modules.taco_agent import TACOAgent, TACOminiBrain  # noqa: PLC0415
        t0 = _time.monotonic()

        predicted_techs: Set[str] = set()
        predicted_controls: Set[str] = set()
        reported_conf = 0.0
        brain_predictions: dict = {}
        hop_summary: dict = {}

        try:
            agent = TACOAgent(
                minis={"brain": TACOminiBrain()},
                threshold=1.1,  # never escalate
            )
            chain = agent.run(
                f"what are the main threats and missing controls for {arch_name}?",
                arch_name=arch_name,
            )
            brain_hop = chain.hops[0]
            preds = brain_hop.metadata.get("predictions") or {}
            predicted_techs = set(preds.get("techniques") or [])
            predicted_controls = {c.lower() for c in (preds.get("missing_controls") or [])}
            reported_conf = brain_hop.confidence or 0.0
            brain_predictions = preds

            hop_summary = {
                "chain_id": chain.chain_id,
                "hops": len(chain.hops),
                "predicted_techs": list(predicted_techs),
                "predicted_controls": list(predicted_controls),
                "had_graph_hit": False,
                "final_confidence": reported_conf,
                "brain_predictions": brain_predictions,
            }
        except Exception:
            logger.exception("taco_brain scoring failed for %s", arch_name)

        duration_ms = int((_time.monotonic() - t0) * 1000)

        tr = _dim_threat_relevant(predicted_techs, gt)
        ta = _dim_ttp_accurate(predicted_techs, gt)
        rd = _dim_risk_defensible(predicted_controls, gt)
        pa = _load_plan_actionable(arch_dir)
        gr = _dim_groundedness(predicted_techs, predicted_controls, gt)
        cc = _dim_confidence_calibration(reported_conf, gr)
        cu = _dim_ciso_utility(hop_summary, gt)

        s = BenchmarkScore(
            arch_name=arch_name, mode="taco_brain",
            threat_relevant=tr, ttp_accurate=ta, risk_defensible=rd,
            plan_actionable=pa, groundedness=gr, confidence_calibration=cc,
            ciso_utility=cu, overall=0.0, duration_ms=duration_ms, hop_summary=hop_summary,
        )
        s.overall = _compute_overall(s)
        return s

    def _score_taco_rag(self, arch_name: str, gt: dict, arch_dir: Path) -> BenchmarkScore:
        import time as _time
        from chatbot.modules.taco_agent import (  # noqa: PLC0415
            TACOAgent, TACOminiBrain, TACOminiRAG,
        )
        t0 = _time.monotonic()

        predicted_techs: Set[str] = set()
        predicted_controls: Set[str] = set()
        reported_conf = 0.0
        had_graph_hit = False
        brain_predictions: dict = {}
        hop_summary: dict = {}

        try:
            agent = TACOAgent(
                minis={
                    "brain": TACOminiBrain(),
                    "rag":   TACOminiRAG(report_dir=self.report_dir),
                },
                threshold=1.1,
            )
            chain = agent.run(
                f"what are the main threats and missing controls for {arch_name}?",
                arch_name=arch_name,
            )
            brain_hop = next((h for h in chain.hops if h.hop_type == "brain"), None)
            rag_hop   = next((h for h in chain.hops if h.hop_type == "rag"), None)

            brain_techs    = set((brain_hop.metadata.get("predictions") or {}).get("techniques") or []) if brain_hop else set()
            brain_controls = {c.lower() for c in ((brain_hop.metadata.get("predictions") or {}).get("missing_controls") or [])} if brain_hop else set()
            rag_techs      = set(rag_hop.metadata.get("techniques") or []) if rag_hop else set()
            rag_controls   = set(rag_hop.metadata.get("missing_controls") or []) if rag_hop else set()

            predicted_techs    = brain_techs | rag_techs
            predicted_controls = brain_controls | rag_controls

            brain_conf = (brain_hop.confidence or 0.0) if brain_hop else 0.0
            rag_conf   = (rag_hop.confidence   or 0.0) if rag_hop   else 0.0
            reported_conf = max(brain_conf, rag_conf)
            had_graph_hit = bool(rag_hop and rag_hop.metadata.get("had_hit"))

            if brain_hop:
                brain_predictions = (brain_hop.metadata.get("predictions") or {})

            hop_summary = {
                "chain_id": chain.chain_id,
                "hops": len(chain.hops),
                "predicted_techs": list(predicted_techs),
                "predicted_controls": list(predicted_controls),
                "had_graph_hit": had_graph_hit,
                "final_confidence": reported_conf,
                "brain_predictions": brain_predictions,
            }
        except Exception:
            logger.exception("taco_rag scoring failed for %s", arch_name)

        duration_ms = int((_time.monotonic() - t0) * 1000)

        tr = _dim_threat_relevant(predicted_techs, gt)
        ta = _dim_ttp_accurate(predicted_techs, gt)
        rd = _dim_risk_defensible(predicted_controls, gt)
        pa = _load_plan_actionable(arch_dir)
        gr = _dim_groundedness(predicted_techs, predicted_controls, gt)
        cc = _dim_confidence_calibration(reported_conf, gr)
        cu = _dim_ciso_utility(hop_summary, gt)

        s = BenchmarkScore(
            arch_name=arch_name, mode="taco_rag",
            threat_relevant=tr, ttp_accurate=ta, risk_defensible=rd,
            plan_actionable=pa, groundedness=gr, confidence_calibration=cc,
            ciso_utility=cu, overall=0.0, duration_ms=duration_ms, hop_summary=hop_summary,
        )
        s.overall = _compute_overall(s)
        return s
