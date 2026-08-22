"""
SOC Detection Rule Evaluator.

Loads policies/soc_detection_rules.yaml and evaluates each rule against a
governance_signals dict, returning OCSF DetectionFinding (class_uid 2004) events
enriched with rule_id, actions, playbook_ref, and kill_chain_stage.

This is the bridge between the raw governance signals and the SOC response chain:
  Signal → Threshold → Rule → Alert (OCSF 2004) → Action

Usage:
    from chatbot.harness.rule_evaluator import RuleEvaluator
    ev = RuleEvaluator()
    findings = ev.evaluate(governance_signals, arch_name="my_arch", run_id="run-001")

All public methods are non-fatal: YAML parse errors and field-lookup errors
produce warnings, never exceptions — the analysis pipeline must not crash on a
misconfigured ruleset.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parents[2] / "policies" / "soc_detection_rules.yaml"

OCSF_VERSION    = "1.1"
PRODUCT_NAME    = "ThreatAssessor"
PRODUCT_VERSION = "1.4"

_SEV_ORDER = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_SEV_ID    = {"informational": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}


# ── YAML loading ─────────────────────────────────────────────────────────────

def _load_rules() -> List[Dict]:
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        logger.warning("RuleEvaluator: pyyaml not installed — rule evaluation disabled")
        return []
    try:
        raw = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
        return raw.get("rules", []) if isinstance(raw, dict) else []
    except Exception as exc:
        logger.warning(f"RuleEvaluator: failed to load {RULES_PATH}: {exc}")
        return []


def _load_playbooks() -> Dict[str, Dict]:
    try:
        import yaml
        raw = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
        return raw.get("playbooks", {}) if isinstance(raw, dict) else {}
    except Exception:
        return {}


# ── Field resolution ─────────────────────────────────────────────────────────

def _resolve_field(signals: Dict, field_path: str) -> Any:
    """Resolve a dot-path into the governance_signals dict. Returns None on miss."""
    parts = field_path.split(".")
    current: Any = signals
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


# ── Condition evaluation ─────────────────────────────────────────────────────

def _eval_condition(signals: Dict, condition: Dict) -> bool:
    """Evaluate a single condition dict against governance_signals."""
    field = condition.get("field", "")
    op    = condition.get("op", "==")
    value = condition.get("value")

    val = _resolve_field(signals, field)

    try:
        if op == "==":
            # Handle boolean string coercion
            if isinstance(value, bool) and isinstance(val, str):
                return val.lower() == str(value).lower()
            return val == value

        if op == "!=":
            return val != value

        if op in (">=", ">", "<=", "<"):
            if val is None:
                return False
            fval = float(val)
            fthresh = float(value)
            if op == ">=": return fval >= fthresh
            if op == ">":  return fval > fthresh
            if op == "<=": return fval <= fthresh
            if op == "<":  return fval < fthresh

        if op == "contains":
            return value in (val or [])

        if op == "length_gt":
            return isinstance(val, (list, dict, str)) and len(val) > int(value)

        if op == "length_eq":
            return isinstance(val, (list, dict, str)) and len(val) == int(value)

        # token_spike: val is per_agent dict; checks if any agent > multiplier × mean
        if op == "token_spike":
            if not isinstance(val, dict):
                return False
            min_agents = int(condition.get("min_agents", 3))
            multiplier = float(value)
            counts = {}
            for agent, data in val.items():
                tokens = data.get("tokens", 0) if isinstance(data, dict) else 0
                if tokens > 0:
                    counts[agent] = tokens
            if len(counts) < min_agents:
                return False
            mean = sum(counts.values()) / len(counts)
            return any(t > multiplier * mean for t in counts.values())

        # no_critical: per_threat list has no entry with severity CRITICAL
        if op == "no_critical":
            if not isinstance(val, list):
                return True  # field absent or wrong type → no list → no critical entries
            has_critical = any(
                (t.get("severity") or "").upper() == "CRITICAL"
                for t in val
                if isinstance(t, dict)
            )
            return not has_critical

        # min_agents: per_agent dict has >= N entries with token data
        if op == "min_agents":
            if not isinstance(val, dict):
                return False
            return len(val) >= int(value)

        if op == "all_gt":
            if not isinstance(val, (list, dict)):
                return False
            items = val.values() if isinstance(val, dict) else val
            nums = [float(v) for v in items if v is not None]
            return bool(nums) and all(n > float(value) for n in nums)

    except (TypeError, ValueError, AttributeError) as exc:
        logger.debug(f"RuleEvaluator: condition eval error on {field!r}: {exc}")

    return False


def _eval_rule(signals: Dict, rule: Dict) -> bool:
    """Return True if all/any conditions in a rule match."""
    conditions = rule.get("conditions", [])
    if not conditions:
        return False
    combine = rule.get("combine", "all").lower()
    results = [_eval_condition(signals, c) for c in conditions]
    if combine == "any":
        return any(results)
    return all(results)


# ── Action resolution ────────────────────────────────────────────────────────

def _resolve_actions(rule: Dict, severity: str) -> List[Dict]:
    """Return actions that apply given the current severity."""
    raw_actions = rule.get("actions", [])
    resolved = []
    sev_level = _SEV_ORDER.get(severity.lower(), 0)

    for action in raw_actions:
        condition = action.get("condition", "")
        if condition:
            # Simple condition: "severity == Critical" or "severity >= High"
            try:
                parts = condition.strip().split()
                if len(parts) == 3 and parts[0] == "severity":
                    op, threshold = parts[1], parts[2].strip('"').strip("'")
                    thresh_level = _SEV_ORDER.get(threshold.lower(), 0)
                    if op == "==" and sev_level != thresh_level:
                        continue
                    if op == ">=" and sev_level < thresh_level:
                        continue
                    if op == ">" and sev_level <= thresh_level:
                        continue
            except Exception:
                pass
        resolved.append(action)

    return resolved


# ── OCSF DetectionFinding builder ────────────────────────────────────────────

def _build_detection_finding(
    rule: Dict,
    signals: Dict,
    arch_name: str,
    run_id: str,
    ts: int,
    playbooks: Dict,
) -> Dict[str, Any]:
    rule_id    = rule.get("id", "DETECT-???")
    name       = rule.get("name", "")
    severity   = rule.get("severity", "Medium")
    sev_id     = _SEV_ID.get(severity.lower(), 3)
    actions    = _resolve_actions(rule, severity)
    kill_chain = rule.get("kill_chain_stage", "")
    playbook   = playbooks.get(name, {})

    # Pull the specific signal values that triggered this rule for unmapped context
    triggered_values = {}
    for cond in rule.get("conditions", []):
        field = cond.get("field", "")
        val   = _resolve_field(signals, field)
        if val is not None:
            triggered_values[field] = val

    return {
        "class_uid":    2004,
        "class_name":   "Detection Finding",
        "ocsf_version": OCSF_VERSION,
        "time":         ts,
        "severity_id":  sev_id,
        "severity":     severity,
        "status":       "New",
        "status_id":    1,
        "finding": {
            "uid":          f"{rule_id}-{run_id}",
            "title":        rule.get("description", name).split("\n")[0].strip(),
            "desc":         rule.get("description", "").strip(),
            "type_uid":     rule.get("ocsf_type_uid", 200400),
            "kill_chain_stage": kill_chain,
        },
        "resources": [{"name": arch_name, "type": "architecture_diagram", "uid": arch_name}],
        "metadata": {
            "product": {"name": PRODUCT_NAME, "version": PRODUCT_VERSION},
            "version": OCSF_VERSION,
            "profiles": ["security_control", "detection"],
        },
        "unmapped": {
            "rule_id":           rule_id,
            "rule_name":         name,
            "run_id":            run_id,
            "incident_refs":     rule.get("incident_refs", []),
            "owasp":             rule.get("owasp", []),
            "atlas_tactic":      rule.get("atlas_tactic", ""),
            "kill_chain_stage":  kill_chain,
            "actions":           [a.get("type") for a in actions],
            "action_detail":     actions,
            "triggered_values":  triggered_values,
            "playbook_ref":      name if playbook else None,
            "playbook_steps":    playbook.get("analyst_steps", []),
            "tuning_note":       rule.get("tuning_note", "").strip(),
        },
    }


# ── Public evaluator ─────────────────────────────────────────────────────────

class RuleEvaluator:
    """
    Loads soc_detection_rules.yaml once and evaluates all rules against
    governance_signals dicts.

    Usage:
        evaluator = RuleEvaluator()
        findings = evaluator.evaluate(signals, arch_name="my_arch", run_id="r1")
    """

    def __init__(self, rules_path: Optional[Path] = None):
        path = rules_path or RULES_PATH
        try:
            import yaml
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            self._rules     = raw.get("rules", []) if isinstance(raw, dict) else []
            self._playbooks = raw.get("playbooks", {}) if isinstance(raw, dict) else {}
            logger.debug(f"RuleEvaluator: loaded {len(self._rules)} rules from {path}")
        except ImportError:
            logger.warning("RuleEvaluator: pyyaml not installed — evaluation disabled")
            self._rules = []
            self._playbooks = {}
        except Exception as exc:
            logger.warning(f"RuleEvaluator: failed to load rules: {exc}")
            self._rules = []
            self._playbooks = {}

    def evaluate(
        self,
        signals: Dict[str, Any],
        arch_name: str = "",
        run_id: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all rules against signals. Returns list of OCSF DetectionFinding events
        for every rule that matches — empty list if no rules fire.
        """
        ts     = ts or int(time.time())
        run_id = run_id or arch_name
        findings = []

        for rule in self._rules:
            try:
                if _eval_rule(signals, rule):
                    findings.append(
                        _build_detection_finding(
                            rule, signals, arch_name, run_id, ts, self._playbooks
                        )
                    )
            except Exception as exc:
                logger.warning(f"RuleEvaluator: rule {rule.get('id','?')} eval failed: {exc}")

        return findings

    @property
    def rule_ids(self) -> List[str]:
        return [r.get("id", "") for r in self._rules]

    def __len__(self) -> int:
        return len(self._rules)
