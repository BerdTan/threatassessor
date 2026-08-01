"""
RuleTrendEvaluator — per-rule firing trend across governance_signals history.

Reads governance_signals_history.jsonl (one JSON line per pipeline run),
evaluates each snapshot through the rule evaluator, and computes:
  - fired_on:    list of ISO timestamps when rule fired
  - last_n:      bool list for the N most recent runs (True = fired)
  - trend:       "new" | "rising" | "stable" | "falling" | "cleared" | "never"

Trend logic (requires >= 2 snapshots):
  new      — fired in latest run, never fired before
  cleared  — did not fire in latest run, fired in a previous run
  rising   — fired rate in last half > fired rate in first half
  falling  — fired rate in last half < fired rate in first half
  stable   — fired rate unchanged or single-snapshot baseline
  never    — no snapshot has ever fired this rule

Usage:
    from chatbot.harness.rule_trend_evaluator import RuleTrendEvaluator
    evaluator = RuleTrendEvaluator()
    trends = evaluator.compute_arch(report_dir)  # {rule_id: TrendResult}
    corpus = evaluator.compute_corpus(report_base_dir)  # {arch: {rule_id: TrendResult}}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

HISTORY_FILENAME = "governance_signals_history.jsonl"


@dataclass
class TrendResult:
    rule_id:    str
    arch:       str
    fired_on:   List[str]          # ISO timestamps when rule fired
    last_n:     List[bool]         # bool per snapshot, newest last
    trend:      str                # new|rising|stable|falling|cleared|never
    total_runs: int
    fired_runs: int

    @property
    def fire_rate(self) -> float:
        return round(self.fired_runs / self.total_runs, 3) if self.total_runs else 0.0

    def to_dict(self) -> dict:
        return {
            "rule_id":    self.rule_id,
            "arch":       self.arch,
            "fired_on":   self.fired_on,
            "last_n":     self.last_n,
            "trend":      self.trend,
            "total_runs": self.total_runs,
            "fired_runs": self.fired_runs,
            "fire_rate":  self.fire_rate,
        }


def _compute_trend(last_n: List[bool]) -> str:
    """Derive trend label from the firing history (ordered oldest → newest)."""
    if not last_n:
        return "never"
    fired_any = any(last_n)
    latest    = last_n[-1]

    if not fired_any:
        return "never"
    if len(last_n) == 1:
        return "new" if latest else "cleared"

    if latest and not any(last_n[:-1]):
        return "new"
    if not latest and any(last_n[:-1]):
        return "cleared"

    # Need at least 2 points for rising/falling
    if len(last_n) < 2:
        return "stable"

    mid   = len(last_n) // 2
    first = sum(last_n[:mid]) / mid if mid else 0
    last  = sum(last_n[mid:]) / (len(last_n) - mid) if (len(last_n) - mid) else 0

    if last > first + 0.1:
        return "rising"
    if last < first - 0.1:
        return "falling"
    return "stable"


class RuleTrendEvaluator:
    """Compute per-rule firing trends from governance_signals_history.jsonl."""

    def __init__(self, rules_yaml: Optional[Path] = None) -> None:
        self._ev = self._load_evaluator()
        self._rule_ids = self._ev.rule_ids if self._ev else []

    def _load_evaluator(self):
        try:
            from chatbot.harness.rule_evaluator import RuleEvaluator
            return RuleEvaluator()
        except Exception as exc:
            logger.warning(f"RuleTrendEvaluator: could not load RuleEvaluator: {exc}")
            return None

    def load_history(self, report_dir: Path) -> List[dict]:
        """Load all snapshots from governance_signals_history.jsonl. Newest last."""
        hist_path = report_dir / HISTORY_FILENAME
        if not hist_path.exists():
            return []
        entries = []
        try:
            for line in hist_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            logger.debug(f"RuleTrendEvaluator: could not read {hist_path}: {exc}")
        return entries

    def compute_arch(self, report_dir: Path) -> Dict[str, TrendResult]:
        """
        Compute trend for every rule for a single architecture.
        Returns {rule_id: TrendResult}.
        """
        arch = report_dir.name
        entries = self.load_history(report_dir)

        if not entries or not self._ev:
            return {
                rid: TrendResult(rid, arch, [], [], "never", 0, 0)
                for rid in self._rule_ids
            }

        # Evaluate each snapshot
        fired_by_rule: Dict[str, List[bool]] = {rid: [] for rid in self._rule_ids}
        ts_by_rule:    Dict[str, List[str]]  = {rid: [] for rid in self._rule_ids}

        for entry in entries:
            sig = entry.get("signals", {})
            ts  = entry.get("ts", "")
            run_id = entry.get("run_id", "")
            try:
                findings = self._ev.evaluate(sig, arch_name=arch, run_id=run_id)
                fired_ids = {f["unmapped"]["rule_id"] for f in findings}
            except Exception:
                fired_ids = set()

            for rid in self._rule_ids:
                did_fire = rid in fired_ids
                fired_by_rule[rid].append(did_fire)
                if did_fire:
                    ts_by_rule[rid].append(ts)

        results = {}
        total = len(entries)
        for rid in self._rule_ids:
            history = fired_by_rule[rid]
            fired_n = sum(history)
            results[rid] = TrendResult(
                rule_id    = rid,
                arch       = arch,
                fired_on   = ts_by_rule[rid],
                last_n     = history,
                trend      = _compute_trend(history),
                total_runs = total,
                fired_runs = fired_n,
            )
        return results

    def compute_corpus(self, report_base: Path) -> Dict[str, Dict[str, TrendResult]]:
        """
        Compute trends for all architectures under report_base.
        Returns {arch_name: {rule_id: TrendResult}}.
        """
        corpus: Dict[str, Dict[str, TrendResult]] = {}
        if not report_base.exists():
            return corpus
        for d in sorted(report_base.iterdir()):
            if not d.is_dir():
                continue
            if not (d / "governance_signals.json").exists():
                continue
            corpus[d.name] = self.compute_arch(d)
        return corpus

    def corpus_coverage_matrix(
        self, report_base: Path
    ) -> Dict[str, Dict[str, str]]:
        """
        Returns {rule_id: {arch: trend_label}} for all rules that have
        at least one non-'never' trend in the corpus.
        """
        corpus = self.compute_corpus(report_base)
        matrix: Dict[str, Dict[str, str]] = {rid: {} for rid in self._rule_ids}
        for arch, trends in corpus.items():
            for rid, tr in trends.items():
                if tr.trend != "never":
                    matrix[rid][arch] = tr.trend
        return {rid: v for rid, v in matrix.items() if v}
