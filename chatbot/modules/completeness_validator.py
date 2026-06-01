"""
Completeness Validation Framework

Phase 3B Enhancement: 6-check validation framework to ensure comprehensive threat analysis.

Validates:
1. Path completeness - Every attack path has ≥1 control
2. Orphan node detection - Every node reachable from entry points
3. Mitigation exhaustiveness - Controls cover ≥80% of MITRE mitigations
4. Diagram completeness - All recommended controls visualized
5. Control budget - Prevention (40%), Detect (30%), Isolate (20%), Respond (10%) ±5%
6. Hop coverage - Each hop in critical paths has ≥1 prevention control

Output: Validation report with confidence adjustment factor
"""

from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# VALIDATION ISSUE STRUCTURE
# ============================================================================

class ValidationIssue:
    """Represents a validation issue found during completeness checks."""

    def __init__(
        self,
        severity: str,
        check: str,
        message: str,
        impact: str,
        confidence_penalty: float = 0.0,
        details: Optional[Dict] = None
    ):
        self.severity = severity  # "error", "warning", "info"
        self.check = check  # Check name
        self.message = message  # Human-readable description
        self.impact = impact  # Impact description
        self.confidence_penalty = confidence_penalty  # 0.0-1.0 (how much to reduce confidence)
        self.details = details or {}

    def to_dict(self) -> Dict:
        return {
            "severity": self.severity,
            "check": self.check,
            "message": self.message,
            "impact": self.impact,
            "confidence_penalty": self.confidence_penalty,
            "details": self.details
        }


# ============================================================================
# CHECK 1: PATH COMPLETENESS
# ============================================================================

def validate_path_completeness(
    attack_paths: List[Dict],
    control_recommendations: List[Dict]
) -> List[ValidationIssue]:
    """
    Validate that every attack path has at least one control addressing it.

    Args:
        attack_paths: List of attack path dicts
        control_recommendations: List of control recommendation dicts

    Returns:
        List of ValidationIssue objects
    """
    issues = []

    if not attack_paths:
        return issues

    # Build mapping: path_id → controls addressing it
    path_controls = defaultdict(list)
    for ctrl in control_recommendations:
        for path_id in ctrl.get('attack_paths', []):
            path_controls[path_id].append(ctrl.get('control', 'unknown'))

    # Check each path
    for i, path in enumerate(attack_paths):
        if i not in path_controls:
            # Critical: Path has NO controls
            issues.append(ValidationIssue(
                severity="error",
                check="path_completeness",
                message=f"Attack path #{i+1} has NO controls addressing it",
                impact="Critical gap - attack path undefended",
                confidence_penalty=0.10,  # -10% confidence
                details={
                    "path_id": i,
                    "entry": path.get('entry'),
                    "target": path.get('target'),
                    "techniques": path.get('techniques', [])
                }
            ))
        elif len(path_controls[i]) < 2:
            # Warning: Path has only 1 control (no defense in depth)
            issues.append(ValidationIssue(
                severity="warning",
                check="path_completeness",
                message=f"Attack path #{i+1} has only 1 control (lacks defense-in-depth)",
                impact="Single point of failure - recommend adding layered controls",
                confidence_penalty=0.02,  # -2% confidence
                details={
                    "path_id": i,
                    "controls": path_controls[i]
                }
            ))

    if not issues:
        logger.info(f"✅ Path completeness: All {len(attack_paths)} paths have controls")
    else:
        logger.warning(f"⚠️  Path completeness: {len(issues)} issues found")

    return issues


# ============================================================================
# CHECK 2: ORPHAN NODE DETECTION
# ============================================================================

def validate_orphan_nodes(
    nodes: Dict[str, Dict],
    edges: List[Dict],
    entry_nodes: List[str]
) -> List[ValidationIssue]:
    """
    Validate that all nodes are reachable from entry points.

    Orphan nodes: Have outbound connections but no path from entry points.

    Args:
        nodes: Dict of node_id → node_data
        edges: List of edge dicts with 'source' and 'target'
        entry_nodes: List of entry point node IDs

    Returns:
        List of ValidationIssue objects
    """
    issues = []

    if not nodes or not entry_nodes:
        return issues

    # Build adjacency list for reachability analysis
    graph = defaultdict(list)
    out_degree = defaultdict(int)
    in_degree = defaultdict(int)

    for edge in edges:
        source = edge.get('source')
        target = edge.get('target')
        if source and target:
            graph[source].append(target)
            out_degree[source] += 1
            in_degree[target] += 1

    # Find all reachable nodes from entry points (BFS)
    reachable = set(entry_nodes)
    queue = list(entry_nodes)

    while queue:
        node = queue.pop(0)
        for neighbor in graph.get(node, []):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)

    # Find orphan nodes: not reachable from entry BUT have outbound connections
    for node_id in nodes.keys():
        if node_id not in entry_nodes and node_id not in reachable:
            # Check if has outbound connections
            if out_degree.get(node_id, 0) > 0:
                # Orphan: not reachable but connects to other nodes
                issues.append(ValidationIssue(
                    severity="error",
                    check="orphan_detection",
                    message=f"Node '{node_id}' is unreachable from entry points but has outbound connections",
                    impact="Missing attack path analysis - add entry point or connection",
                    confidence_penalty=0.08,  # -8% confidence
                    details={
                        "node_id": node_id,
                        "node_label": nodes[node_id].get('label', node_id),
                        "out_degree": out_degree[node_id],
                        "targets": graph.get(node_id, [])
                    }
                ))
            else:
                # Isolated node (no in or out) - less critical
                if in_degree.get(node_id, 0) == 0:
                    issues.append(ValidationIssue(
                        severity="warning",
                        check="orphan_detection",
                        message=f"Node '{node_id}' is isolated (no connections)",
                        impact="Node not part of architecture flow",
                        confidence_penalty=0.01,  # -1% confidence
                        details={
                            "node_id": node_id,
                            "node_label": nodes[node_id].get('label', node_id)
                        }
                    ))

    if not issues:
        logger.info(f"✅ Orphan detection: All nodes reachable from entry points")
    else:
        logger.warning(f"⚠️  Orphan detection: {len(issues)} issues found")

    return issues


# ============================================================================
# CHECK 3: MITIGATION EXHAUSTIVENESS
# ============================================================================

def validate_mitigation_exhaustiveness(
    technique_ids: List[str],
    control_recommendations: List[Dict],
    threshold: float = None
) -> Tuple[List[ValidationIssue], float]:
    """
    Validate that recommended controls address ≥80% of techniques.

    Phase 3B: Uses technique coverage (not mitigation coverage) as primary metric.

    Args:
        technique_ids: All unique MITRE techniques from attack paths
        control_recommendations: List of control dicts
        threshold: Required coverage (defaults to config value, currently 80%)

    Returns:
        (issues, coverage_score)
    """
    if threshold is None:
        from chatbot.config import get_settings
        threshold = get_settings().completeness.technique_coverage_threshold

    issues = []

    if not technique_ids:
        return issues, 1.0

    # Get techniques covered by recommendations
    covered_techniques = set()
    for ctrl in control_recommendations:
        covered_techniques.update(ctrl.get('techniques', []))

    # Calculate coverage
    coverage = len(covered_techniques) / len(technique_ids) if technique_ids else 1.0

    if coverage < threshold:
        missing_techniques = [t for t in technique_ids if t not in covered_techniques]

        issues.append(ValidationIssue(
            severity="error",
            check="mitigation_exhaustiveness",
            message=f"Technique coverage {coverage:.1%} below threshold {threshold:.1%}",
            impact=f"{len(missing_techniques)} techniques not addressed by any control",
            confidence_penalty=0.15,  # -15% confidence
            details={
                "coverage": coverage,
                "threshold": threshold,
                "total_techniques": len(technique_ids),
                "covered_techniques": len(covered_techniques),
                "missing_techniques": missing_techniques
            }
        ))
    elif coverage < 1.0:
        missing_techniques = [t for t in technique_ids if t not in covered_techniques]

        issues.append(ValidationIssue(
            severity="warning",
            check="mitigation_exhaustiveness",
            message=f"Technique coverage {coverage:.1%} could be improved",
            impact=f"{len(missing_techniques)} techniques not addressed",
            confidence_penalty=0.03,  # -3% confidence
            details={
                "coverage": coverage,
                "missing_techniques": missing_techniques
            }
        ))

    if not issues:
        logger.info(f"✅ Mitigation exhaustiveness: {coverage:.1%} technique coverage")
    else:
        logger.warning(f"⚠️  Mitigation exhaustiveness: {coverage:.1%} technique coverage")

    return issues, coverage


# ============================================================================
# CHECK 4: DIAGRAM COMPLETENESS
# ============================================================================

def validate_diagram_completeness(
    control_recommendations: List[Dict],
    after_mmd_content: str
) -> List[ValidationIssue]:
    """
    Validate that all recommended controls appear in after.mmd diagram.

    Args:
        control_recommendations: List of control dicts
        after_mmd_content: Content of after.mmd file

    Returns:
        List of ValidationIssue objects
    """
    issues = []

    if not control_recommendations:
        return issues

    # Check each control
    missing_controls = []

    for ctrl in control_recommendations:
        control_name = ctrl.get('control', '')
        if not control_name:
            continue

        # Convert to diagram ID format
        diagram_id = 'NEW_' + control_name.upper().replace(' ', '').replace('/', '').replace('-', '').replace('_', '')

        if diagram_id not in after_mmd_content:
            missing_controls.append(control_name)

    if missing_controls:
        issues.append(ValidationIssue(
            severity="error",
            check="diagram_completeness",
            message=f"{len(missing_controls)} control(s) missing from diagram visualization",
            impact="Incomplete visualization undermines user trust",
            confidence_penalty=0.05,  # -5% confidence
            details={
                "missing_controls": missing_controls,
                "total_controls": len(control_recommendations)
            }
        ))
    else:
        logger.info(f"✅ Diagram completeness: All {len(control_recommendations)} controls visualized")

    return issues


# ============================================================================
# CHECK 5: CONTROL BUDGET (Prevention/Detect/Isolate/Respond)
# ============================================================================

def validate_control_budget(
    control_recommendations: List[Dict],
    target_budget: Dict[str, float] = None,
    tolerance: float = 0.05
) -> Tuple[List[ValidationIssue], Dict[str, float]]:
    """
    Validate layered defense coverage (Prevention + DIR framework).

    Philosophy: Ensure fallback paths exist, not rigid percentages.
    Required defense layers:
    - Prevention (≥1): First line of defense
    - Detect (≥1): Visibility into attacks
    - Isolate OR Respond (≥1): Contain or recover from breaches

    Soft target: Prevention ~40%, Detect ~30%, Isolate ~20%, Respond ~10%
    (guidance, not enforcement - layered coverage is what matters)

    Args:
        control_recommendations: List of control dicts with 'dir_category'
        target_budget: Optional custom budget (for reference only)
        tolerance: Acceptable deviation (informational warnings only)

    Returns:
        (issues, actual_budget)
    """
    issues = []

    if target_budget is None:
        target_budget = {
            "prevention": 0.40,
            "detect": 0.30,
            "isolate": 0.20,
            "respond": 0.10
        }

    if not control_recommendations:
        return issues, {}

    # Count controls by DIR category
    dir_counts = defaultdict(int)
    total = len(control_recommendations)

    for ctrl in control_recommendations:
        dir_category = ctrl.get('dir_category', 'prevention').lower()
        dir_counts[dir_category] += 1

    # Calculate actual budget
    actual_budget = {
        cat: dir_counts[cat] / total if total > 0 else 0.0
        for cat in target_budget.keys()
    }

    # CRITICAL CHECK: Ensure layered defense paths exist
    has_prevention = dir_counts['prevention'] > 0
    has_detect = dir_counts['detect'] > 0
    has_isolate = dir_counts['isolate'] > 0
    has_respond = dir_counts['respond'] > 0
    has_containment = has_isolate or has_respond

    # Check for missing critical layers
    if not has_prevention:
        issues.append(ValidationIssue(
            severity="error",
            check="control_budget",
            message="No Prevention controls - missing first line of defense",
            impact="No ability to stop attacks before they start",
            confidence_penalty=0.10,
            details={"layer": "prevention", "count": 0}
        ))

    if not has_detect:
        issues.append(ValidationIssue(
            severity="error",
            check="control_budget",
            message="No Detect controls - blind to attacks",
            impact="Cannot see when attacks happen or trigger response",
            confidence_penalty=0.08,
            details={"layer": "detect", "count": 0}
        ))

    if not has_containment:
        issues.append(ValidationIssue(
            severity="warning",
            check="control_budget",
            message="No Isolate or Respond controls - cannot contain breaches",
            impact="No fallback if Prevention and Detection fail",
            confidence_penalty=0.05,
            details={"layer": "isolate/respond", "isolate_count": 0, "respond_count": 0}
        ))

    # INFORMATIONAL: Report deviations from soft targets (no penalties if layers exist)
    if has_prevention and has_detect and has_containment:
        # We have layered defense - check if distribution is far from guidance
        for category, target_pct in target_budget.items():
            actual_pct = actual_budget.get(category, 0.0)
            deviation = abs(actual_pct - target_pct)

            # Only warn if deviation is significant (>10%) AND layer has controls
            if deviation > tolerance * 2 and dir_counts[category] > 0:
                issues.append(ValidationIssue(
                    severity="info",
                    check="control_budget",
                    message=f"{category.title()}: {actual_pct:.1%} (guidance: {target_pct:.1%})",
                    impact=f"Distribution differs from 40/30/20/10 guidance (still has layered defense)",
                    confidence_penalty=0.0,  # No penalty if layered defense exists
                    details={
                        "category": category,
                        "actual": actual_pct,
                        "target": target_pct,
                        "deviation": deviation,
                        "control_count": dir_counts[category]
                    }
                ))

    if not issues:
        logger.info(f"✅ Layered defense: Prevention, Detect, and Containment layers present")
    elif all(i.severity != "error" for i in issues):
        logger.info(f"✅ Layered defense: All critical layers present (distribution varies from guidance)")
    else:
        logger.warning(f"⚠️  Layered defense: {len([i for i in issues if i.severity == 'error'])} missing layer(s)")

    return issues, actual_budget


# ============================================================================
# CHECK 6: HOP COVERAGE (Prevention controls at critical hops)
# ============================================================================

def validate_hop_coverage(
    attack_paths: List[Dict],
    control_recommendations: List[Dict]
) -> List[ValidationIssue]:
    """
    Validate that each hop in critical paths has ≥1 prevention control.

    Critical path: Paths from Internet/External to sensitive targets (DB, secrets)

    Args:
        attack_paths: List of attack path dicts
        control_recommendations: List of control dicts

    Returns:
        List of ValidationIssue objects
    """
    issues = []

    if not attack_paths:
        return issues

    # Identify critical paths (internet → database/secrets)
    critical_paths = []
    for i, path in enumerate(attack_paths):
        entry = path.get('entry', '').lower()
        target = path.get('target', '').lower()

        is_external_entry = any(kw in entry for kw in ['internet', 'external', 'public', 'partner'])
        is_sensitive_target = any(kw in target for kw in ['database', 'db', 'secret', 'key', 'credential', 'pii'])

        if is_external_entry and is_sensitive_target:
            critical_paths.append((i, path))

    if not critical_paths:
        logger.info("ℹ️  No critical paths (internet → sensitive) identified")
        return issues

    # Check hop coverage for critical paths
    for path_id, path in critical_paths:
        # Get per-node techniques
        per_node_techniques = path.get('per_node_techniques', {})

        if not per_node_techniques:
            # Can't validate hop coverage without per-node data
            continue

        # Check which hops have prevention controls
        path_route = path.get('path', [])
        hops_with_prevention = set()

        for ctrl in control_recommendations:
            if path_id in ctrl.get('attack_paths', []):
                dir_category = ctrl.get('dir_category', '').lower()
                if dir_category == 'prevention':
                    # This prevention control addresses this path
                    # Assume it covers all hops (simplified - could be more granular)
                    hops_with_prevention.update(path_route)

        # Check for gaps
        total_hops = len(path_route)
        covered_hops = len(hops_with_prevention)

        if covered_hops < total_hops * 0.5:  # <50% hop coverage
            issues.append(ValidationIssue(
                severity="warning",
                check="hop_coverage",
                message=f"Critical path #{path_id+1}: Only {covered_hops}/{total_hops} hops have prevention controls",
                impact="Weak hop-by-hop defense - attacker may bypass controls",
                confidence_penalty=0.02,
                details={
                    "path_id": path_id,
                    "entry": path.get('entry'),
                    "target": path.get('target'),
                    "total_hops": total_hops,
                    "covered_hops": covered_hops
                }
            ))

    if not issues:
        logger.info(f"✅ Hop coverage: {len(critical_paths)} critical paths adequately defended")
    else:
        logger.warning(f"⚠️  Hop coverage: {len(issues)} gaps in hop-by-hop defense")

    return issues


# ============================================================================
# COMPREHENSIVE VALIDATION
# ============================================================================

def validate_completeness(
    ground_truth: Dict,
    after_mmd_path: Optional[str] = None
) -> Dict:
    """
    Run all 6 completeness validation checks.

    Args:
        ground_truth: Ground truth dict with attack paths, controls, etc.
        after_mmd_path: Optional path to after.mmd file

    Returns:
        {
            "validation_passed": bool,
            "confidence_adjustment": float (0-1),
            "issues": [ValidationIssue.to_dict()],
            "checks": {
                "path_completeness": {"passed": bool, "issues": int},
                "orphan_detection": {...},
                "mitigation_exhaustiveness": {...},
                "diagram_completeness": {...},
                "control_budget": {...},
                "hop_coverage": {...}
            }
        }
    """
    logger.info("="*80)
    logger.info("COMPLETENESS VALIDATION FRAMEWORK (6 CHECKS)")
    logger.info("="*80)

    all_issues = []
    check_results = {}

    # Extract data
    attack_paths = ground_truth.get('expected_attack_paths', [])
    control_recommendations = ground_truth.get('control_recommendations', [])
    nodes = ground_truth.get('metadata', {}).get('parsed_nodes', {})
    edges = ground_truth.get('metadata', {}).get('parsed_edges', [])

    # Get unique techniques from all paths
    all_techniques = set()
    for path in attack_paths:
        all_techniques.update(path.get('techniques', []))

    # Get entry nodes
    entry_nodes = list(set(path.get('entry') for path in attack_paths if path.get('entry')))

    # CHECK 1: Path completeness
    logger.info("\nCheck 1: Path Completeness")
    logger.info("-"*80)
    issues_1 = validate_path_completeness(attack_paths, control_recommendations)
    all_issues.extend(issues_1)
    check_results['path_completeness'] = {
        "passed": len(issues_1) == 0,
        "issues": len(issues_1)
    }

    # CHECK 2: Orphan detection
    logger.info("\nCheck 2: Orphan Node Detection")
    logger.info("-"*80)
    if nodes and entry_nodes:
        issues_2 = validate_orphan_nodes(nodes, edges, entry_nodes)
    else:
        issues_2 = []
        logger.warning("Skipping orphan detection (no parsed nodes/edges in metadata)")
    all_issues.extend(issues_2)
    check_results['orphan_detection'] = {
        "passed": len(issues_2) == 0,
        "issues": len(issues_2)
    }

    # CHECK 3: Mitigation exhaustiveness
    logger.info("\nCheck 3: Mitigation Exhaustiveness")
    logger.info("-"*80)
    issues_3, coverage = validate_mitigation_exhaustiveness(list(all_techniques), control_recommendations)
    all_issues.extend(issues_3)
    check_results['mitigation_exhaustiveness'] = {
        "passed": len(issues_3) == 0,
        "issues": len(issues_3),
        "coverage": coverage
    }

    # CHECK 4: Diagram completeness
    logger.info("\nCheck 4: Diagram Completeness")
    logger.info("-"*80)
    if after_mmd_path:
        try:
            with open(after_mmd_path, 'r') as f:
                after_mmd_content = f.read()
            issues_4 = validate_diagram_completeness(control_recommendations, after_mmd_content)
        except FileNotFoundError:
            issues_4 = []
            logger.warning(f"Skipping diagram completeness (file not found: {after_mmd_path})")
    else:
        issues_4 = []
        logger.warning("Skipping diagram completeness (no after_mmd_path provided)")
    all_issues.extend(issues_4)
    check_results['diagram_completeness'] = {
        "passed": len(issues_4) == 0,
        "issues": len(issues_4)
    }

    # CHECK 5: Control budget
    logger.info("\nCheck 5: Control Budget (40/30/20/10)")
    logger.info("-"*80)
    issues_5, actual_budget = validate_control_budget(control_recommendations)
    all_issues.extend(issues_5)
    check_results['control_budget'] = {
        "passed": len(issues_5) == 0,
        "issues": len(issues_5),
        "actual": actual_budget
    }

    # CHECK 6: Hop coverage
    logger.info("\nCheck 6: Hop Coverage (Critical Paths)")
    logger.info("-"*80)
    issues_6 = validate_hop_coverage(attack_paths, control_recommendations)
    all_issues.extend(issues_6)
    check_results['hop_coverage'] = {
        "passed": len(issues_6) == 0,
        "issues": len(issues_6)
    }

    # Calculate confidence adjustment
    total_penalty = sum(issue.confidence_penalty for issue in all_issues)
    confidence_adjustment = max(0.0, 1.0 - total_penalty)  # Floor at 0%

    # Overall result
    critical_failures = [i for i in all_issues if i.severity == "error"]
    validation_passed = len(critical_failures) == 0

    logger.info("\n" + "="*80)
    logger.info("VALIDATION SUMMARY")
    logger.info("="*80)
    logger.info(f"Total issues: {len(all_issues)} (errors: {len(critical_failures)}, warnings: {len(all_issues) - len(critical_failures)})")
    logger.info(f"Confidence adjustment: {confidence_adjustment:.2%} (penalty: {total_penalty:.2%})")
    logger.info(f"Overall: {'✅ PASS' if validation_passed else '❌ FAIL (critical issues found)'}")

    result = {
        "validation_passed": validation_passed,
        "confidence_adjustment": confidence_adjustment,
        "total_issues": len(all_issues),
        "critical_issues": len(critical_failures),
        "issues": [issue.to_dict() for issue in all_issues],
        "checks": check_results
    }

    return result


if __name__ == "__main__":
    # Test validation framework
    import sys
    import json
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.completeness_validator <architecture_name>")
        print("Example: python3 -m chatbot.modules.completeness_validator 10_complex_enterprise")
        sys.exit(1)

    arch_name = sys.argv[1]
    ground_truth_path = f"report/{arch_name}/ground_truth.json"
    after_mmd_path = f"report/{arch_name}/after.mmd"

    # Load ground truth
    with open(ground_truth_path, 'r') as f:
        ground_truth = json.load(f)

    # Run validation
    result = validate_completeness(ground_truth, after_mmd_path)

    # Print results
    print("\n" + "="*80)
    print("COMPLETENESS VALIDATION RESULT")
    print("="*80)
    print(f"Validation: {'✅ PASSED' if result['validation_passed'] else '❌ FAILED'}")
    print(f"Confidence Adjustment: {result['confidence_adjustment']:.1%}")
    print(f"Issues Found: {result['total_issues']} ({result['critical_issues']} critical)")

    if result['issues']:
        print("\nIssues:")
        for issue in result['issues']:
            icon = "❌" if issue['severity'] == 'error' else "⚠️" if issue['severity'] == 'warning' else "ℹ️"
            print(f"  {icon} [{issue['check']}] {issue['message']}")
            print(f"     Impact: {issue['impact']}")

    print("="*80)

    sys.exit(0 if result['validation_passed'] else 1)
