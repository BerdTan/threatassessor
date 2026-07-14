"""
Critic Learning Loop

Accumulates recurring critic gap patterns across ER runs and promotes
high-confidence signals into the deterministic engine.

Architecture:
  ER run → _extract_signals() → critic_signals.jsonl (append)
           ↓ (periodic)
  _promote_signals() → engine_hints.json (consumed by ground_truth_generator)

Signal lifecycle:
  1. Each full_moe run writes gap signals to critic_signals.jsonl
  2. Signals are keyed by (arch_type, technique, gap_category)
  3. When a signal accumulates ≥ PROMOTE_THRESHOLD occurrences it's promoted
  4. Promoted signals feed back into the deterministic engine as hints:
     - Missing control hints → exhaustive_mitigation_mapper gets a new entry
     - Validation rule hints → self_validation gets a new heuristic
     - Technique pattern hints → ground_truth_generator gets a coverage rule

Usage (called automatically by MoEOrchestrator after a full_moe run):
    from chatbot.harness.critic_learning import record_er_signals
    record_er_signals(moe_result, ground_truth, arch_name)

Periodic promotion (run manually or via cron):
    python3 -m chatbot.harness.critic_learning --promote

Skill entry point: .claude/skills/critic-learn/
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.modules.agents.orchestrators.moe_orchestrator import MoEResult

logger = logging.getLogger(__name__)

# --- Config -------------------------------------------------------------------

_SIGNALS_FILE = Path("chatbot/data/critic_signals.jsonl")
_HINTS_FILE   = Path("chatbot/data/engine_hints.json")
PROMOTE_THRESHOLD = 3   # occurrences across distinct archs before promotion
MAX_SIGNALS_RETAINED = 5000  # rolling window — prune oldest on overflow

# Regex for technique IDs in gap descriptions
_TECH_RE = re.compile(r'\b(T\d{4}(?:\.\d{3})?|AML\.T\d{4}(?:\.\d{3})?)\b')
_CTRL_RE = re.compile(r'\b([A-Z][A-Z /\-]{3,})\b')  # rough uppercase control names


# --- Signal extraction --------------------------------------------------------

def _arch_type(ground_truth: Dict) -> str:
    """Derive a coarse arch type from ground_truth for signal keying."""
    desc = (ground_truth.get("description") or ground_truth.get("architecture") or "").lower()
    if any(k in desc for k in ("agentic", "llm", "ai ", "ml ", "model")):
        return "agentic"
    if any(k in desc for k in ("blockchain", "distributed ledger")):
        return "blockchain"
    if any(k in desc for k in ("iot", "sensor", "mqtt", "device")):
        return "iot"
    if any(k in desc for k in ("cdn", "edge", "multi-region", "multi_region")):
        return "distributed"
    if any(k in desc for k in ("legacy", "monolith")):
        return "legacy"
    return "generic"


def _extract_signals(moe_result: "MoEResult", ground_truth: Dict, arch_name: str) -> List[Dict]:
    """
    Extract learnable gap signals from a completed MoE run.

    Signals are extracted from all five critics' gaps. Each signal records:
      - arch_name, arch_type
      - critic: which critic surfaced it
      - gap_category: one of (detect_only_gap, missing_control, invalid_mapping,
                              coverage_blindspot, bypass_vector, cross_path_chain)
      - techniques: T-IDs mentioned in the gap description
      - description: raw gap text (truncated)
      - severity: as reported by the critic
    """
    from chatbot.modules.self_validation import _MITRE_DETECT_ONLY_TECHNIQUES

    arch_type = _arch_type(ground_truth)
    signals: List[Dict] = []

    critic_map = {
        "architect":   getattr(moe_result, "architect_critique",   None),
        "tester":      getattr(moe_result, "tester_critique",      None),
        "red_team":    getattr(moe_result, "red_team_critique",     None),
        "purple_team": getattr(moe_result, "purple_team_critique",  None),
        "blackhat":    getattr(moe_result, "blackhat_critique",     None),
    }

    for critic_name, vr in critic_map.items():
        if vr is None:
            continue
        for gap in getattr(vr, "gaps", []):
            desc = gap.get("description", str(gap)) if isinstance(gap, dict) else str(gap)
            severity = (gap.get("severity", "medium") if isinstance(gap, dict) else "medium").lower()
            techs = [t for t in _TECH_RE.findall(desc)]

            # Classify gap category
            cat = _classify_gap(desc, techs, critic_name, _MITRE_DETECT_ONLY_TECHNIQUES)

            signals.append({
                "arch_name":    arch_name,
                "arch_type":    arch_type,
                "critic":       critic_name,
                "gap_category": cat,
                "techniques":   techs,
                "severity":     severity,
                "description":  desc[:300],
                "ts":           datetime.utcnow().isoformat(),
            })

    return signals


def _classify_gap(
    desc: str,
    techs: List[str],
    critic: str,
    detect_only: frozenset,
) -> str:
    desc_l = desc.lower()
    if techs and all(t.split(".")[0] in detect_only for t in techs):
        return "detect_only_gap"
    if critic == "tester" and ("invalid" in desc_l or "not in" in desc_l or "m-id" in desc_l):
        return "invalid_mapping"
    if critic in ("purple_team",) and "unmapped" in desc_l:
        return "coverage_blindspot"
    if critic == "red_team" and ("bypass" in desc_l or "evasion" in desc_l):
        return "bypass_vector"
    if critic == "blackhat" and ("pivot" in desc_l or "chain" in desc_l or "cross-path" in desc_l):
        return "cross_path_chain"
    return "missing_control"


# --- Persistence --------------------------------------------------------------

def record_er_signals(
    moe_result: "MoEResult",
    ground_truth: Dict,
    arch_name: str,
) -> int:
    """
    Extract gap signals from a completed ER run and append to critic_signals.jsonl.
    Returns count of signals written.
    Called automatically by MoEOrchestrator after full_moe.
    """
    signals = _extract_signals(moe_result, ground_truth, arch_name)
    if not signals:
        return 0

    _SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _SIGNALS_FILE.open("a") as f:
        for s in signals:
            f.write(json.dumps(s) + "\n")

    logger.info(f"CriticLearning: recorded {len(signals)} signals for {arch_name}")
    return len(signals)


def _load_signals() -> List[Dict]:
    if not _SIGNALS_FILE.exists():
        return []
    signals = []
    with _SIGNALS_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    signals.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return signals[-MAX_SIGNALS_RETAINED:]  # rolling window


# --- Promotion ----------------------------------------------------------------

def _promote_signals() -> Dict:
    """
    Aggregate signals and promote those above PROMOTE_THRESHOLD into engine_hints.json.

    Promoted hint schema:
      {
        "hint_type": "missing_detection_control" | "coverage_rule" | "bypass_pattern",
        "arch_types": [...],
        "techniques": [...],
        "gap_category": "...",
        "recommended_control": "...",   # for missing_detection_control
        "rule_description": "...",
        "occurrences": N,
        "distinct_archs": N,
        "promoted_at": "ISO timestamp",
        "status": "pending_review" | "baked_in" | "rejected",
      }
    """
    signals = _load_signals()
    if not signals:
        logger.warning("CriticLearning: no signals to promote")
        return {}

    # Group by (gap_category, tuple(sorted(techniques)))
    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for s in signals:
        key = f"{s['gap_category']}|{'_'.join(sorted(s.get('techniques', [])))}"
        buckets[key].append(s)

    existing_hints: List[Dict] = []
    if _HINTS_FILE.exists():
        existing_hints = json.loads(_HINTS_FILE.read_text()).get("hints", [])

    existing_keys = {
        f"{h['gap_category']}|{'_'.join(sorted(h.get('techniques', [])))}"
        for h in existing_hints
        if h.get("status") != "rejected"
    }

    new_promotions = []
    for key, items in buckets.items():
        distinct_archs = len({s["arch_name"] for s in items})
        if distinct_archs < PROMOTE_THRESHOLD:
            continue
        if key in existing_keys:
            # Update occurrence count on existing hint
            for h in existing_hints:
                hkey = f"{h['gap_category']}|{'_'.join(sorted(h.get('techniques', [])))}"
                if hkey == key:
                    h["occurrences"] = len(items)
                    h["distinct_archs"] = distinct_archs
            continue

        techs = list({t for s in items for t in s.get("techniques", [])})
        arch_types = list({s["arch_type"] for s in items})
        cat = items[0]["gap_category"]

        hint = {
            "hint_type": _hint_type_for_category(cat),
            "arch_types": arch_types,
            "techniques": techs,
            "gap_category": cat,
            "recommended_control": _recommended_control(cat, techs),
            "rule_description": _rule_description(cat, techs, items),
            "occurrences": len(items),
            "distinct_archs": distinct_archs,
            "promoted_at": datetime.utcnow().isoformat(),
            "status": "pending_review",
        }
        new_promotions.append(hint)
        logger.info(f"CriticLearning: promoting signal [{cat}] techs={techs} "
                    f"({distinct_archs} archs, {len(items)} occurrences)")

    all_hints = existing_hints + new_promotions
    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "promote_threshold": PROMOTE_THRESHOLD,
        "total_signals": len(signals),
        "hints": all_hints,
    }
    _HINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HINTS_FILE.write_text(json.dumps(result, indent=2))

    logger.info(f"CriticLearning: {len(new_promotions)} new hints promoted, "
                f"{len(all_hints)} total in {_HINTS_FILE}")
    return result


def _hint_type_for_category(cat: str) -> str:
    return {
        "detect_only_gap":   "missing_detection_control",
        "missing_control":   "missing_detection_control",
        "coverage_blindspot": "coverage_rule",
        "bypass_vector":     "bypass_pattern",
        "cross_path_chain":  "bypass_pattern",
        "invalid_mapping":   "coverage_rule",
    }.get(cat, "coverage_rule")


def _recommended_control(cat: str, techs: List[str]) -> str:
    from chatbot.modules.self_validation import _MITRE_DETECT_ONLY_TECHNIQUES
    if cat == "detect_only_gap":
        if any("T1083" in t or "T1057" in t for t in techs):
            return "file integrity monitoring"
        if any("T1018" in t or "T1046" in t for t in techs):
            return "network monitoring"
        return "edr"
    if cat == "coverage_blindspot":
        return "ids/ips"
    return ""


def _rule_description(cat: str, techs: List[str], items: List[Dict]) -> str:
    sample_desc = items[0]["description"][:120] if items else ""
    arch_types = list({s["arch_type"] for s in items})
    return (
        f"Recurring {cat} for techniques {techs} across {arch_types} architectures. "
        f"Sample: {sample_desc}"
    )


# --- Engine hint consumption --------------------------------------------------

def load_engine_hints(arch_type: Optional[str] = None) -> List[Dict]:
    """
    Load promoted hints for use by the deterministic engine.
    Filters to hints with status 'pending_review' or 'baked_in' and optionally
    by arch_type. Called by ground_truth_generator and exhaustive_mitigation_mapper.
    """
    if not _HINTS_FILE.exists():
        return []
    try:
        data = json.loads(_HINTS_FILE.read_text())
    except Exception:
        return []

    hints = [
        h for h in data.get("hints", [])
        if h.get("status") in ("pending_review", "baked_in")
    ]
    if arch_type:
        hints = [h for h in hints if not h.get("arch_types") or arch_type in h["arch_types"]]
    return hints


# --- CLI ----------------------------------------------------------------------

def _print_summary() -> None:
    signals = _load_signals()
    if not signals:
        print("No signals recorded yet. Run full_moe on some architectures first.")
        return

    from collections import Counter
    by_cat = Counter(s["gap_category"] for s in signals)
    by_arch = Counter(s["arch_name"] for s in signals)
    by_critic = Counter(s["critic"] for s in signals)

    print(f"\nCritic Learning Signal Summary")
    print(f"  Total signals:  {len(signals)}")
    print(f"  Distinct archs: {len(by_arch)}")
    print(f"\nBy gap category:")
    for cat, n in by_cat.most_common():
        print(f"  {cat:<30} {n:>4}")
    print(f"\nBy critic:")
    for critic, n in by_critic.most_common():
        print(f"  {critic:<20} {n:>4}")

    if _HINTS_FILE.exists():
        hints = json.loads(_HINTS_FILE.read_text()).get("hints", [])
        pending = [h for h in hints if h.get("status") == "pending_review"]
        baked   = [h for h in hints if h.get("status") == "baked_in"]
        print(f"\nEngine hints: {len(hints)} total, {len(pending)} pending review, {len(baked)} baked in")
        for h in pending:
            print(f"  [PENDING] {h['hint_type']:30} techs={h['techniques']}  "
                  f"archs={h['distinct_archs']}  ctrl='{h.get('recommended_control','')}'")


if __name__ == "__main__":
    import sys
    if "--promote" in sys.argv:
        result = _promote_signals()
        promoted = [h for h in result.get("hints", []) if h.get("status") == "pending_review"]
        print(f"Promoted {len(promoted)} new hints to {_HINTS_FILE}")
        for h in promoted:
            print(f"  [{h['hint_type']}] {h['techniques']}  control='{h.get('recommended_control','')}'"
                  f"  ({h['distinct_archs']} archs)")
    else:
        _print_summary()
