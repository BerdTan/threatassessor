# Phase 3C: Multi-Agent Team Architecture (A-Team Critique)

**Date:** 2026-05-15  
**Status:** Design Complete  
**Purpose:** Trio of agents (Architect, Tester, Red Teamer) working as ONE TEAM to critique deterministic engine  
**Architecture:** Collaborative multi-agent system with shared memory

---

## Core Concept: A-Team Critique

```
┌─────────────────────────────────────────────────────────────────┐
│ Deterministic Engine (Phase 3B+ - 99.5% Confidence)            │
├─────────────────────────────────────────────────────────────────┤
│ Produces 5 ARTIFACTS:                                           │
│ 1. Attack Paths (per-node techniques, risk scores)             │
│ 2. Control Recommendations (rationale, placement, hop analysis) │
│ 3. Residual Risk (BEFORE/AFTER, per-threat breakdown)          │
│ 4. Validation Results (6-check framework, confidence)           │
│ 5. RAPIDS Assessment (6 categories, risk scores, priorities)   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ ARTIFACT PARSER (Pre-Processing)                                │
├─────────────────────────────────────────────────────────────────┤
│ Extracts & structures 5 artifacts from ground_truth.json       │
│ Creates indexed views for efficient agent access               │
│ Validates completeness (fail fast if missing)                  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR AGENT (Team Manager)                               │
├─────────────────────────────────────────────────────────────────┤
│ • Initializes shared memory                                     │
│ • Assigns critique tasks to A-Team                             │
│ • Manages inter-agent communication                             │
│ • Synthesizes findings                                          │
│ • Resolves conflicts                                            │
└─────────────────────────────────────────────────────────────────┘
           ↓                    ↓                    ↓
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ ARCHITECT│        │  TESTER  │        │ RED TEAM │
    │  AGENT   │←───────│  AGENT   │───────→│  AGENT   │
    └──────────┘        └──────────┘        └──────────┘
         ↑                    ↑                    ↑
         └────────────────────┴────────────────────┘
                            │
                ┌───────────────────────┐
                │   SHARED MEMORY       │
                │   (Agent Context)     │
                ├───────────────────────┤
                │ • Artifact indexes    │
                │ • Agent findings      │
                │ • Cross-references    │
                │ • Critique progress   │
                └───────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ SYNTHESIZED OUTPUT                                              │
├─────────────────────────────────────────────────────────────────┤
│ • Aggregate confidence (99.5% ± agents)                         │
│ • Consolidated findings (de-duplicated)                         │
│ • Architecture improvements (after-llm.mmd)                     │
│ • Validation report (Pass/Fail per artifact)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component 1: Artifact Parser (Preprocessing)

### Purpose
Extract and validate the 5 deterministic artifacts before agents start.

### Implementation

```python
# chatbot/modules/artifact_parser.py (NEW)

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArtifactSet:
    """
    Structured representation of 5 deterministic artifacts.
    Optimized for agent access with indexes.
    """
    
    # Artifact 1: Attack Paths
    attack_paths: List[Dict]
    path_index: Dict[int, Dict]  # path_id → path_data
    node_to_paths: Dict[str, List[int]]  # node_id → path_ids containing it
    technique_to_paths: Dict[str, List[int]]  # technique_id → path_ids using it
    
    # Artifact 2: Control Recommendations
    control_recommendations: List[Dict]
    control_index: Dict[str, Dict]  # control_name → control_data
    control_to_paths: Dict[str, List[int]]  # control_name → path_ids it addresses
    control_to_techniques: Dict[str, List[str]]  # control_name → technique_ids
    
    # Artifact 3: Residual Risk
    residual_risk: Dict
    risk_before: float
    risk_after: float
    risk_reduction_percent: float
    per_threat_risk: Dict[str, Dict]  # threat_name → {before, after, reduction}
    
    # Artifact 4: Validation Results
    validation_results: Dict
    checks_passed: int
    checks_total: int
    validation_issues: List[Dict]
    confidence_score: float
    
    # Artifact 5: RAPIDS Assessment
    rapids_assessment: Dict
    rapids_threats: List[str]  # 6 categories
    rapids_risk_scores: Dict[str, int]  # threat → risk (0-100)
    rapids_priorities: Dict[str, str]  # threat → priority (critical/high/medium/low)
    
    # Metadata
    architecture_name: str
    architecture_type: str
    total_nodes: int
    total_edges: int


class ArtifactParser:
    """
    Parses ground_truth.json and extracts 5 deterministic artifacts.
    Creates indexed views for efficient agent access.
    """
    
    @staticmethod
    def parse(ground_truth: Dict) -> ArtifactSet:
        """
        Extract and validate 5 artifacts from ground_truth.json.
        
        Raises:
            ValueError: If any artifact is incomplete or missing
        
        Returns:
            ArtifactSet with indexed data
        """
        
        # Validate presence of 5 artifacts
        ArtifactParser._validate_completeness(ground_truth)
        
        # Extract Artifact 1: Attack Paths
        attack_paths = ground_truth.get("attack_paths", [])
        path_index = {i: path for i, path in enumerate(attack_paths)}
        node_to_paths = ArtifactParser._build_node_to_paths_index(attack_paths)
        technique_to_paths = ArtifactParser._build_technique_to_paths_index(attack_paths)
        
        # Extract Artifact 2: Control Recommendations
        controls = ground_truth.get("control_recommendations", [])
        control_index = {c["control"]: c for c in controls}
        control_to_paths = {c["control"]: c.get("attack_paths", []) for c in controls}
        control_to_techniques = {c["control"]: c.get("techniques", []) for c in controls}
        
        # Extract Artifact 3: Residual Risk
        residual = ground_truth.get("residual_risk", {})
        risk_before = residual.get("current_risk", 0)
        risk_after = residual.get("projected_risk", 0)
        risk_reduction = residual.get("risk_reduction_percent", 0)
        per_threat = residual.get("per_threat_risk", {})
        
        # Extract Artifact 4: Validation Results
        validation = ground_truth.get("validation", {})
        checks_passed = validation.get("checks_passed", 0)
        checks_total = validation.get("checks_total", 6)
        validation_issues = validation.get("issues", [])
        confidence = validation.get("confidence", 0.0)
        
        # Extract Artifact 5: RAPIDS Assessment
        rapids = ground_truth.get("rapids_assessment", {})
        rapids_threats = list(rapids.keys())
        rapids_scores = {k: v.get("risk", 0) for k, v in rapids.items()}
        rapids_priorities = {k: v.get("priority", "low") for k, v in rapids.items()}
        
        # Metadata
        arch_name = ground_truth.get("architecture", "unknown")
        arch_type = ground_truth.get("architecture_type", "generic")
        nodes = ground_truth.get("nodes", {})
        edges = ground_truth.get("edges", [])
        
        artifact_set = ArtifactSet(
            # Artifact 1
            attack_paths=attack_paths,
            path_index=path_index,
            node_to_paths=node_to_paths,
            technique_to_paths=technique_to_paths,
            # Artifact 2
            control_recommendations=controls,
            control_index=control_index,
            control_to_paths=control_to_paths,
            control_to_techniques=control_to_techniques,
            # Artifact 3
            residual_risk=residual,
            risk_before=risk_before,
            risk_after=risk_after,
            risk_reduction_percent=risk_reduction,
            per_threat_risk=per_threat,
            # Artifact 4
            validation_results=validation,
            checks_passed=checks_passed,
            checks_total=checks_total,
            validation_issues=validation_issues,
            confidence_score=confidence,
            # Artifact 5
            rapids_assessment=rapids,
            rapids_threats=rapids_threats,
            rapids_risk_scores=rapids_scores,
            rapids_priorities=rapids_priorities,
            # Metadata
            architecture_name=arch_name,
            architecture_type=arch_type,
            total_nodes=len(nodes),
            total_edges=len(edges)
        )
        
        logger.info(f"✅ Parsed 5 artifacts from {arch_name}")
        logger.info(f"  - Attack paths: {len(attack_paths)}")
        logger.info(f"  - Controls: {len(controls)}")
        logger.info(f"  - Residual risk: {risk_before} → {risk_after} ({risk_reduction}%)")
        logger.info(f"  - Validation: {checks_passed}/{checks_total} checks passed")
        logger.info(f"  - RAPIDS threats: {len(rapids_threats)}")
        
        return artifact_set
    
    @staticmethod
    def _validate_completeness(ground_truth: Dict) -> None:
        """
        Validate that all 5 artifacts are present and complete.
        
        Raises:
            ValueError: If any artifact is missing or incomplete
        """
        errors = []
        
        # Artifact 1: Attack Paths
        if "attack_paths" not in ground_truth:
            errors.append("Artifact 1 missing: attack_paths")
        elif len(ground_truth["attack_paths"]) == 0:
            errors.append("Artifact 1 incomplete: attack_paths is empty")
        else:
            # Check per-node techniques (Phase 3B+ feature)
            for i, path in enumerate(ground_truth["attack_paths"]):
                if "per_node_techniques" not in path:
                    errors.append(f"Artifact 1 incomplete: path #{i} missing per_node_techniques")
                    break
        
        # Artifact 2: Control Recommendations
        if "control_recommendations" not in ground_truth:
            errors.append("Artifact 2 missing: control_recommendations")
        elif len(ground_truth["control_recommendations"]) < 10:
            errors.append(f"Artifact 2 incomplete: only {len(ground_truth['control_recommendations'])} controls (expect ≥10)")
        else:
            # Check hop analysis (Phase 3B+ feature)
            for i, ctrl in enumerate(ground_truth["control_recommendations"]):
                if "_layered_defense" not in ctrl:
                    errors.append(f"Artifact 2 incomplete: control #{i} missing _layered_defense")
                    break
        
        # Artifact 3: Residual Risk
        if "residual_risk" not in ground_truth:
            errors.append("Artifact 3 missing: residual_risk")
        elif "current_risk" not in ground_truth["residual_risk"]:
            errors.append("Artifact 3 incomplete: missing current_risk")
        elif "projected_risk" not in ground_truth["residual_risk"]:
            errors.append("Artifact 3 incomplete: missing projected_risk")
        
        # Artifact 4: Validation Results
        if "validation" not in ground_truth:
            errors.append("Artifact 4 missing: validation")
        elif ground_truth["validation"].get("checks_total", 0) != 6:
            errors.append(f"Artifact 4 incomplete: expected 6 checks, got {ground_truth['validation'].get('checks_total', 0)}")
        
        # Artifact 5: RAPIDS Assessment
        if "rapids_assessment" not in ground_truth:
            errors.append("Artifact 5 missing: rapids_assessment")
        elif len(ground_truth["rapids_assessment"]) != 6:
            errors.append(f"Artifact 5 incomplete: expected 6 RAPIDS categories, got {len(ground_truth['rapids_assessment'])}")
        
        if errors:
            raise ValueError(
                "Artifact validation FAILED - cannot proceed to agent critique:\n" +
                "\n".join(f"  ❌ {err}" for err in errors) +
                "\n\nFix deterministic engine to produce complete artifacts."
            )
    
    @staticmethod
    def _build_node_to_paths_index(attack_paths: List[Dict]) -> Dict[str, List[int]]:
        """Build index: node_id → path_ids containing that node."""
        index = {}
        for path_id, path in enumerate(attack_paths):
            for node in path.get("path", []):
                node_id = node.get("id") or node  # Handle both dict and string formats
                if node_id not in index:
                    index[node_id] = []
                index[node_id].append(path_id)
        return index
    
    @staticmethod
    def _build_technique_to_paths_index(attack_paths: List[Dict]) -> Dict[str, List[int]]:
        """Build index: technique_id → path_ids using that technique."""
        index = {}
        for path_id, path in enumerate(attack_paths):
            for technique in path.get("techniques", []):
                if technique not in index:
                    index[technique] = []
                index[technique].append(path_id)
        return index
```

---

## Component 2: Shared Memory (Agent Context Store)

### Purpose
Allow agents to share findings, reference each other's work, avoid duplication.

### Implementation

```python
# chatbot/modules/agent_memory.py (NEW)

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentFinding:
    """
    Single finding from an agent.
    """
    agent_name: str  # "architect", "tester", "red_teamer"
    finding_type: str  # "gap", "issue", "recommendation", "bypass"
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    artifact: str  # Which artifact this relates to (1-5)
    description: str
    evidence: Dict[str, Any]  # Supporting data
    timestamp: datetime = field(default_factory=datetime.now)
    references: List[str] = field(default_factory=list)  # References to other findings


class AgentMemory:
    """
    Shared memory for A-Team agents.
    Thread-safe for concurrent agent access.
    """
    
    def __init__(self, artifacts: ArtifactSet):
        self.artifacts = artifacts
        self.findings: List[AgentFinding] = []
        self.agent_status: Dict[str, str] = {
            "architect": "pending",
            "tester": "pending",
            "red_teamer": "pending"
        }
        self.cross_references: Dict[str, List[str]] = {}  # finding_id → related_finding_ids
        self._lock = threading.Lock()
        
        logger.info("✅ Shared memory initialized for A-Team")
    
    def add_finding(self, finding: AgentFinding) -> str:
        """
        Add finding to shared memory.
        Returns: finding_id for cross-referencing
        """
        with self._lock:
            finding_id = f"{finding.agent_name}_{len(self.findings)}"
            self.findings.append(finding)
            
            logger.debug(f"  [{finding.agent_name}] Added finding: {finding.finding_type} ({finding.severity})")
            
            return finding_id
    
    def update_agent_status(self, agent_name: str, status: str) -> None:
        """Update agent status (pending → in_progress → complete)."""
        with self._lock:
            self.agent_status[agent_name] = status
            logger.info(f"  [{agent_name}] Status: {status}")
    
    def get_findings_by_agent(self, agent_name: str) -> List[AgentFinding]:
        """Get all findings from a specific agent."""
        with self._lock:
            return [f for f in self.findings if f.agent_name == agent_name]
    
    def get_findings_by_artifact(self, artifact: str) -> List[AgentFinding]:
        """Get all findings related to a specific artifact."""
        with self._lock:
            return [f for f in self.findings if f.artifact == artifact]
    
    def get_findings_by_severity(self, severity: str) -> List[AgentFinding]:
        """Get all findings of a specific severity."""
        with self._lock:
            return [f for f in self.findings if f.severity == severity]
    
    def add_cross_reference(self, finding_id: str, related_finding_id: str) -> None:
        """Link related findings across agents."""
        with self._lock:
            if finding_id not in self.cross_references:
                self.cross_references[finding_id] = []
            self.cross_references[finding_id].append(related_finding_id)
    
    def get_all_agents_status(self) -> Dict[str, str]:
        """Get status of all agents."""
        with self._lock:
            return self.agent_status.copy()
    
    def is_all_agents_complete(self) -> bool:
        """Check if all agents have completed their critique."""
        with self._lock:
            return all(status == "complete" for status in self.agent_status.values())
    
    def get_summary(self) -> Dict:
        """Get summary of findings across all agents."""
        with self._lock:
            return {
                "total_findings": len(self.findings),
                "by_agent": {
                    agent: len([f for f in self.findings if f.agent_name == agent])
                    for agent in ["architect", "tester", "red_teamer"]
                },
                "by_severity": {
                    sev: len([f for f in self.findings if f.severity == sev])
                    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
                },
                "by_artifact": {
                    f"artifact_{i}": len([f for f in self.findings if f.artifact == f"artifact_{i}"])
                    for i in range(1, 6)
                },
                "cross_references": len(self.cross_references)
            }


# Convenience functions for agents to query memory

def query_findings(
    memory: AgentMemory,
    agent: Optional[str] = None,
    artifact: Optional[str] = None,
    severity: Optional[str] = None
) -> List[AgentFinding]:
    """
    Query findings with filters.
    Agents use this to check what others have found.
    """
    findings = memory.findings
    
    if agent:
        findings = [f for f in findings if f.agent_name == agent]
    if artifact:
        findings = [f for f in findings if f.artifact == artifact]
    if severity:
        findings = [f for f in findings if f.severity == severity]
    
    return findings


def has_finding_for(
    memory: AgentMemory,
    artifact: str,
    finding_type: str
) -> bool:
    """
    Check if any agent has already found a specific issue.
    Avoids duplication.
    """
    findings = memory.get_findings_by_artifact(artifact)
    return any(f.finding_type == finding_type for f in findings)
```

---

## Component 3: A-Team Agents (Collaborative Trio)

### Agent 1: Architect (Design Quality)

```python
# chatbot/modules/architect_agent.py (ENHANCED from existing architect_critic.py)

class ArchitectAgent:
    """
    Critiques threat model design quality.
    Uses ALL 5 artifacts in shared memory.
    """
    
    def __init__(self):
        self.role = "architect"
        self.rubric = {
            "artifact_1_attack_paths": 25,  # Attack path completeness
            "artifact_2_controls": 25,      # Control appropriateness
            "artifact_3_residual_risk": 20, # Risk calculation realism
            "artifact_4_validation": 15,    # Validation thoroughness
            "artifact_5_rapids": 15         # RAPIDS threat coverage
        }
    
    def critique(self, memory: AgentMemory) -> Dict:
        """
        Critique using all 5 artifacts from shared memory.
        Posts findings back to memory.
        """
        memory.update_agent_status("architect", "in_progress")
        
        artifacts = memory.artifacts
        findings = []
        score = 0
        
        # Critique Artifact 1: Attack Paths
        logger.info("  [Architect] Critiquing Artifact 1: Attack Paths...")
        artifact1_score, artifact1_findings = self._critique_attack_paths(artifacts)
        score += artifact1_score
        findings.extend(artifact1_findings)
        
        # Critique Artifact 2: Controls
        logger.info("  [Architect] Critiquing Artifact 2: Controls...")
        artifact2_score, artifact2_findings = self._critique_controls(artifacts, memory)
        score += artifact2_score
        findings.extend(artifact2_findings)
        
        # Critique Artifact 3: Residual Risk
        logger.info("  [Architect] Critiquing Artifact 3: Residual Risk...")
        artifact3_score, artifact3_findings = self._critique_residual_risk(artifacts)
        score += artifact3_score
        findings.extend(artifact3_findings)
        
        # Critique Artifact 4: Validation
        logger.info("  [Architect] Critiquing Artifact 4: Validation...")
        artifact4_score, artifact4_findings = self._critique_validation(artifacts)
        score += artifact4_score
        findings.extend(artifact4_findings)
        
        # Critique Artifact 5: RAPIDS
        logger.info("  [Architect] Critiquing Artifact 5: RAPIDS...")
        artifact5_score, artifact5_findings = self._critique_rapids(artifacts)
        score += artifact5_score
        findings.extend(artifact5_findings)
        
        # Post findings to shared memory
        for finding in findings:
            memory.add_finding(finding)
        
        memory.update_agent_status("architect", "complete")
        
        logger.info(f"  [Architect] Complete - Score: {score}/100")
        
        return {
            "score": score,
            "findings": findings
        }
    
    def _critique_attack_paths(self, artifacts: ArtifactSet) -> Tuple[int, List[AgentFinding]]:
        """
        Use Artifact 1 indexes for efficient critique.
        
        Checks:
        - Per-node technique completeness (using node_to_paths index)
        - Technique-to-path coverage (using technique_to_paths index)
        - Missing attack vectors
        """
        findings = []
        score = 25  # Start with full points
        
        # Check: Every node has techniques mapped
        for node_id, path_ids in artifacts.node_to_paths.items():
            # Get all techniques for this node across all paths
            node_techniques = set()
            for path_id in path_ids:
                path = artifacts.path_index[path_id]
                per_node = path.get("per_node_techniques", {})
                if node_id in per_node:
                    node_techniques.update(per_node[node_id])
            
            if len(node_techniques) == 0:
                findings.append(AgentFinding(
                    agent_name="architect",
                    finding_type="gap",
                    severity="HIGH",
                    artifact="artifact_1",
                    description=f"Node '{node_id}' has NO techniques mapped",
                    evidence={
                        "node_id": node_id,
                        "paths_containing": path_ids
                    }
                ))
                score -= 5
        
        # Check: High-risk paths have multiple techniques
        for path_id, path in artifacts.path_index.items():
            risk_score = path.get("risk_score", 0)
            technique_count = len(path.get("techniques", []))
            
            if risk_score >= 70 and technique_count < 5:
                findings.append(AgentFinding(
                    agent_name="architect",
                    finding_type="gap",
                    severity="MEDIUM",
                    artifact="artifact_1",
                    description=f"High-risk path #{path_id} has only {technique_count} techniques",
                    evidence={
                        "path_id": path_id,
                        "risk_score": risk_score,
                        "technique_count": technique_count,
                        "expected": "5+ techniques for high-risk paths"
                    }
                ))
                score -= 3
        
        return max(0, score), findings
    
    def _critique_controls(self, artifacts: ArtifactSet, memory: AgentMemory) -> Tuple[int, List[AgentFinding]]:
        """
        Use Artifact 2 indexes for efficient critique.
        
        Checks:
        - Control-to-technique mapping (using control_to_techniques index)
        - Control-to-path coverage (using control_to_paths index)
        - Placement appropriateness (from hop analysis)
        """
        findings = []
        score = 25
        
        # Check: Controls address techniques they claim
        for control_name, techniques in artifacts.control_to_techniques.items():
            control_data = artifacts.control_index[control_name]
            
            if len(techniques) == 0:
                findings.append(AgentFinding(
                    agent_name="architect",
                    finding_type="issue",
                    severity="HIGH",
                    artifact="artifact_2",
                    description=f"Control '{control_name}' has NO techniques mapped",
                    evidence={
                        "control": control_name,
                        "priority": control_data.get("priority")
                    }
                ))
                score -= 5
            
            # Check if Tester has already flagged this control
            if has_finding_for(memory, "artifact_2", f"control_{control_name}"):
                # Tester already found an issue - note but don't duplicate
                findings.append(AgentFinding(
                    agent_name="architect",
                    finding_type="reference",
                    severity="INFO",
                    artifact="artifact_2",
                    description=f"Control '{control_name}' also flagged by Tester",
                    evidence={"control": control_name},
                    references=["tester_findings"]
                ))
        
        # Check: Controls cover all attack paths
        uncovered_paths = []
        for path_id in artifacts.path_index.keys():
            covering_controls = [
                ctrl_name for ctrl_name, path_ids in artifacts.control_to_paths.items()
                if path_id in path_ids
            ]
            if len(covering_controls) == 0:
                uncovered_paths.append(path_id)
        
        if uncovered_paths:
            findings.append(AgentFinding(
                agent_name="architect",
                finding_type="gap",
                severity="CRITICAL",
                artifact="artifact_2",
                description=f"{len(uncovered_paths)} attack paths have NO controls",
                evidence={
                    "uncovered_paths": uncovered_paths
                }
            ))
            score -= 10
        
        return max(0, score), findings
    
    def _critique_residual_risk(self, artifacts: ArtifactSet) -> Tuple[int, List[AgentFinding]]:
        """Use Artifact 3 data."""
        findings = []
        score = 20
        
        # Check: BEFORE/AFTER scores realistic
        if artifacts.risk_reduction_percent > 80:
            findings.append(AgentFinding(
                agent_name="architect",
                finding_type="issue",
                severity="MEDIUM",
                artifact="artifact_3",
                description=f"Risk reduction {artifacts.risk_reduction_percent}% may be overly optimistic",
                evidence={
                    "before": artifacts.risk_before,
                    "after": artifacts.risk_after,
                    "reduction": artifacts.risk_reduction_percent
                }
            ))
            score -= 5
        
        # Check: Per-threat risk breakdown
        for threat, risk_data in artifacts.per_threat_risk.items():
            before = risk_data.get("before", 0)
            after = risk_data.get("after", 0)
            
            if before > 0 and after == 0:
                findings.append(AgentFinding(
                    agent_name="architect",
                    finding_type="issue",
                    severity="LOW",
                    artifact="artifact_3",
                    description=f"Threat '{threat}' reduced to 0 (unrealistic - should have residual risk)",
                    evidence={
                        "threat": threat,
                        "before": before,
                        "after": after
                    }
                ))
                score -= 2
        
        return max(0, score), findings
    
    def _critique_validation(self, artifacts: ArtifactSet) -> Tuple[int, List[AgentFinding]]:
        """Use Artifact 4 data."""
        findings = []
        score = 15
        
        # Check: All 6 validation checks passed
        if artifacts.checks_passed < artifacts.checks_total:
            findings.append(AgentFinding(
                agent_name="architect",
                finding_type="issue",
                severity="HIGH",
                artifact="artifact_4",
                description=f"Only {artifacts.checks_passed}/{artifacts.checks_total} validation checks passed",
                evidence={
                    "checks_passed": artifacts.checks_passed,
                    "checks_total": artifacts.checks_total,
                    "issues": artifacts.validation_issues
                }
            ))
            score -= 5
        
        return max(0, score), findings
    
    def _critique_rapids(self, artifacts: ArtifactSet) -> Tuple[int, List[AgentFinding]]:
        """Use Artifact 5 data."""
        findings = []
        score = 15
        
        # Check: All 6 RAPIDS categories present
        expected_rapids = ["ransomware", "ddos", "phishing", "supply_chain", "insider_threat", "data_breach"]
        missing_rapids = set(expected_rapids) - set(artifacts.rapids_threats)
        
        if missing_rapids:
            findings.append(AgentFinding(
                agent_name="architect",
                finding_type="gap",
                severity="HIGH",
                artifact="artifact_5",
                description=f"Missing RAPIDS categories: {', '.join(missing_rapids)}",
                evidence={
                    "missing": list(missing_rapids),
                    "present": artifacts.rapids_threats
                }
            ))
            score -= 5
        
        # Check: High-risk RAPIDS have appropriate controls
        for threat, risk_score in artifacts.rapids_risk_scores.items():
            if risk_score >= 70:
                # Check if controls address this threat
                controls_for_threat = [
                    ctrl_name for ctrl_name, ctrl_data in artifacts.control_index.items()
                    if threat in ctrl_data.get("rapids_threats", [])
                ]
                
                if len(controls_for_threat) < 3:
                    findings.append(AgentFinding(
                        agent_name="architect",
                        finding_type="gap",
                        severity="MEDIUM",
                        artifact="artifact_5",
                        description=f"High-risk RAPIDS threat '{threat}' (risk={risk_score}) has only {len(controls_for_threat)} controls",
                        evidence={
                            "threat": threat,
                            "risk_score": risk_score,
                            "controls": controls_for_threat,
                            "expected": "3+ controls for high-risk threats"
                        }
                    ))
                    score -= 3
        
        return max(0, score), findings
```

### Agent 2: Tester (Quality Assurance)

```python
# chatbot/modules/tester_agent.py (NEW - builds on MVP2 spec)

class TesterAgent:
    """
    Validates assessment quality using metrics and consistency checks.
    Uses ALL 5 artifacts and references Architect findings.
    """
    
    def __init__(self):
        self.role = "tester"
        self.rubric = {
            "artifact_4_validation": 40,  # Validation checks passed
            "artifact_1_coverage": 20,    # Technique/path coverage metrics
            "artifact_2_consistency": 20, # Control-threat consistency
            "artifact_3_realism": 10,     # Risk score realism
            "artifact_5_completeness": 10 # RAPIDS completeness
        }
    
    def critique(self, memory: AgentMemory) -> Dict:
        """
        Validate assessment quality.
        References Architect findings from memory.
        """
        memory.update_agent_status("tester", "in_progress")
        
        artifacts = memory.artifacts
        findings = []
        score = 0
        
        # Get Architect's findings to reference
        architect_findings = memory.get_findings_by_agent("architect")
        
        # Validate Artifact 4 (primary focus)
        logger.info("  [Tester] Validating Artifact 4: Validation Results...")
        artifact4_score, artifact4_findings = self._validate_validation_results(artifacts, architect_findings)
        score += artifact4_score
        findings.extend(artifact4_findings)
        
        # Check coverage metrics (Artifact 1)
        logger.info("  [Tester] Checking Artifact 1: Coverage Metrics...")
        artifact1_score, artifact1_findings = self._check_coverage_metrics(artifacts)
        score += artifact1_score
        findings.extend(artifact1_findings)
        
        # Check consistency (Artifacts 2 & 5)
        logger.info("  [Tester] Checking Artifact 2: Consistency...")
        artifact2_score, artifact2_findings = self._check_consistency(artifacts)
        score += artifact2_score
        findings.extend(artifact2_findings)
        
        # Validate realism (Artifact 3)
        logger.info("  [Tester] Validating Artifact 3: Risk Realism...")
        artifact3_score, artifact3_findings = self._validate_risk_realism(artifacts)
        score += artifact3_score
        findings.extend(artifact3_findings)
        
        # Check RAPIDS completeness (Artifact 5)
        logger.info("  [Tester] Checking Artifact 5: RAPIDS Completeness...")
        artifact5_score, artifact5_findings = self._check_rapids_completeness(artifacts)
        score += artifact5_score
        findings.extend(artifact5_findings)
        
        # Post findings to shared memory
        for finding in findings:
            finding_id = memory.add_finding(finding)
            
            # Cross-reference with Architect findings
            for arch_finding in architect_findings:
                if finding.artifact == arch_finding.artifact:
                    memory.add_cross_reference(finding_id, f"architect_{architect_findings.index(arch_finding)}")
        
        memory.update_agent_status("tester", "complete")
        
        logger.info(f"  [Tester] Complete - Score: {score}/100")
        
        return {
            "score": score,
            "findings": findings
        }
    
    def _validate_validation_results(self, artifacts: ArtifactSet, architect_findings: List[AgentFinding]) -> Tuple[int, List[AgentFinding]]:
        """Primary focus: Validate Artifact 4 thoroughly."""
        findings = []
        score = 40
        
        # Check: All 6 checks passed
        if artifacts.checks_passed < artifacts.checks_total:
            findings.append(AgentFinding(
                agent_name="tester",
                finding_type="validation_failure",
                severity="CRITICAL",
                artifact="artifact_4",
                description=f"Validation FAILED: {artifacts.checks_passed}/{artifacts.checks_total} checks passed",
                evidence={
                    "failed_checks": artifacts.checks_total - artifacts.checks_passed,
                    "issues": artifacts.validation_issues
                },
                references=[f"architect_{i}" for i, f in enumerate(architect_findings) if f.artifact == "artifact_4"]
            ))
            score -= 20
        
        # Check: Validation issues severity
        critical_issues = [i for i in artifacts.validation_issues if i.get("severity") == "error"]
        if critical_issues:
            findings.append(AgentFinding(
                agent_name="tester",
                finding_type="validation_failure",
                severity="CRITICAL",
                artifact="artifact_4",
                description=f"{len(critical_issues)} critical validation errors detected",
                evidence={
                    "errors": critical_issues
                }
            ))
            score -= 10
        
        return max(0, score), findings
    
    # ... other validation methods similar to Architect but with QA focus
```

### Agent 3: Red Teamer (Adversarial Testing)

```python
# chatbot/modules/red_team_agent.py (NEW)

class RedTeamAgent:
    """
    Adversarial validation from attacker perspective.
    Uses ALL 5 artifacts to find weakest path and test bypasses.
    """
    
    def __init__(self):
        self.role = "red_teamer"
        self.rubric = {
            "artifact_1_exploitation": 40,  # Weakest path selection
            "artifact_2_bypass": 30,        # Control bypass scenarios
            "artifact_3_realism": 20,       # AFTER risk achievable?
            "artifact_5_threat_model": 10   # RAPIDS threats exploitable?
        }
    
    def critique(self, memory: AgentMemory) -> Dict:
        """
        Red team attack from attacker perspective.
        References Architect and Tester findings.
        """
        memory.update_agent_status("red_teamer", "in_progress")
        
        artifacts = memory.artifacts
        findings = []
        score = 100  # Red team: LOWER score = BETTER (more exploitable)
        
        # Select weakest attack path (Artifact 1)
        logger.info("  [Red Team] Selecting weakest attack path (Artifact 1)...")
        chosen_path, exploit_score = self._select_weakest_path(artifacts)
        score = exploit_score
        
        # Test control bypasses (Artifact 2)
        logger.info("  [Red Team] Testing control bypasses (Artifact 2)...")
        bypass_findings = self._test_control_bypasses(artifacts, chosen_path)
        findings.extend(bypass_findings)
        
        # Validate residual risk realism (Artifact 3)
        logger.info("  [Red Team] Validating residual risk realism (Artifact 3)...")
        risk_findings = self._validate_residual_risk_realism(artifacts, chosen_path)
        findings.extend(risk_findings)
        
        # Check RAPIDS exploitability (Artifact 5)
        logger.info("  [Red Team] Checking RAPIDS exploitability (Artifact 5)...")
        rapids_findings = self._check_rapids_exploitability(artifacts)
        findings.extend(rapids_findings)
        
        # Post findings to shared memory
        for finding in findings:
            memory.add_finding(finding)
        
        memory.update_agent_status("red_teamer", "complete")
        
        logger.info(f"  [Red Team] Complete - Exploitability Score: {score}/100 (lower=better defense)")
        
        return {
            "score": score,
            "findings": findings,
            "chosen_path": chosen_path
        }
    
    # ... implementation methods for red team testing
```

---

## Component 4: Orchestrator (Team Manager)

```python
# chatbot/modules/agent_orchestrator.py (ENHANCED)

import concurrent.futures
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Manages A-Team (Architect, Tester, Red Teamer).
    Coordinates collaborative critique using shared memory.
    """
    
    def __init__(self):
        self.architect = ArchitectAgent()
        self.tester = TesterAgent()
        self.red_teamer = RedTeamAgent()
    
    def run_team_critique(self, ground_truth: Dict, architecture_mmd: str) -> Dict:
        """
        Run A-Team critique in parallel with shared memory.
        
        Returns: {
            "final_confidence": float,
            "agent_scores": {...},
            "consolidated_findings": {...},
            "after_llm_mmd": str,
            "validation_report": str
        }
        """
        
        logger.info("=" * 80)
        logger.info("🚀 Starting A-Team Critique (Architect + Tester + Red Teamer)")
        logger.info("=" * 80)
        
        # STEP 1: Parse 5 artifacts
        logger.info("\n📋 Step 1/5: Parsing deterministic artifacts...")
        try:
            artifacts = ArtifactParser.parse(ground_truth)
        except ValueError as e:
            logger.error(f"❌ Artifact parsing FAILED: {e}")
            raise
        
        # STEP 2: Initialize shared memory
        logger.info("\n🧠 Step 2/5: Initializing shared memory...")
        memory = AgentMemory(artifacts)
        
        # STEP 3: Run A-Team in parallel
        logger.info("\n👥 Step 3/5: Running A-Team critique (parallel execution)...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.architect.critique, memory): "architect",
                executor.submit(self.tester.critique, memory): "tester",
                executor.submit(self.red_teamer.critique, memory): "red_teamer"
            }
            
            agent_results = {}
            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result()
                    agent_results[agent_name] = result
                    logger.info(f"  ✅ {agent_name.capitalize()} complete")
                except Exception as e:
                    logger.error(f"  ❌ {agent_name.capitalize()} failed: {e}")
                    agent_results[agent_name] = {"score": 0, "findings": [], "error": str(e)}
        
        # STEP 4: Synthesize findings
        logger.info("\n🔄 Step 4/5: Synthesizing findings...")
        consolidated = self._consolidate_findings(memory)
        
        # STEP 5: Calculate final confidence
        logger.info("\n📊 Step 5/5: Calculating final confidence...")
        final_confidence = self._calculate_final_confidence(
            deterministic_baseline=artifacts.confidence_score,
            agent_results=agent_results
        )
        
        logger.info("=" * 80)
        logger.info(f"✅ A-Team Critique Complete - Final Confidence: {final_confidence['final_confidence']:.1%}")
        logger.info("=" * 80)
        
        return {
            "final_confidence": final_confidence,
            "agent_scores": {
                "architect": agent_results["architect"]["score"],
                "tester": agent_results["tester"]["score"],
                "red_teamer": agent_results["red_teamer"]["score"]
            },
            "consolidated_findings": consolidated,
            "memory_summary": memory.get_summary(),
            "validation_report": self._generate_validation_report(agent_results, memory)
        }
    
    def _consolidate_findings(self, memory: AgentMemory) -> Dict:
        """
        De-duplicate and organize findings by artifact.
        """
        consolidated = {
            f"artifact_{i}": [] for i in range(1, 6)
        }
        
        # Group by artifact, remove duplicates
        seen_descriptions = set()
        
        for finding in memory.findings:
            # De-duplicate by description
            if finding.description in seen_descriptions:
                continue
            seen_descriptions.add(finding.description)
            
            consolidated[finding.artifact].append({
                "agent": finding.agent_name,
                "type": finding.finding_type,
                "severity": finding.severity,
                "description": finding.description,
                "evidence": finding.evidence,
                "references": finding.references
            })
        
        return consolidated
    
    def _calculate_final_confidence(
        self,
        deterministic_baseline: float,
        agent_results: Dict
    ) -> Dict:
        """
        Aggregate confidence from deterministic + 3 agents.
        
        Formula:
        - Architect: (score - 50) / 500 (±0.10)
        - Tester: (score - 50) / 500 (±0.10)
        - Red Teamer: (50 - score) / 500 (±0.10, inverted - lower exploit = higher confidence)
        """
        
        architect_score = agent_results.get("architect", {}).get("score", 50)
        tester_score = agent_results.get("tester", {}).get("score", 50)
        red_team_score = agent_results.get("red_teamer", {}).get("score", 50)
        
        architect_adj = (architect_score - 50) / 500
        tester_adj = (tester_score - 50) / 500
        red_team_adj = (50 - red_team_score) / 500  # Inverted: lower exploit = better
        
        total_adj = architect_adj + tester_adj + red_team_adj
        final = max(0.0, min(1.0, deterministic_baseline + total_adj))
        
        # Determine level
        if final >= 0.95:
            level = "CRITICAL"
        elif final >= 0.85:
            level = "HIGH"
        elif final >= 0.70:
            level = "MEDIUM"
        else:
            level = "LOW"
        
        return {
            "final_confidence": final,
            "level": level,
            "baseline": deterministic_baseline,
            "adjustments": {
                "architect": architect_adj,
                "tester": tester_adj,
                "red_teamer": red_team_adj,
                "total": total_adj
            },
            "agent_scores": {
                "architect": architect_score,
                "tester": tester_score,
                "red_teamer": red_team_score
            }
        }
    
    def _generate_validation_report(self, agent_results: Dict, memory: AgentMemory) -> str:
        """Generate human-readable validation report."""
        
        report = "# A-Team Validation Report\n\n"
        
        for agent_name in ["architect", "tester", "red_teamer"]:
            result = agent_results.get(agent_name, {})
            score = result.get("score", 0)
            
            status = "✅ PASS" if score >= 70 else "⚠️ NEEDS IMPROVEMENT"
            
            report += f"## {agent_name.replace('_', ' ').title()}\n"
            report += f"**Score:** {score}/100\n"
            report += f"**Status:** {status}\n\n"
        
        # Add summary
        summary = memory.get_summary()
        report += f"## Summary\n"
        report += f"- **Total Findings:** {summary['total_findings']}\n"
        report += f"- **Critical:** {summary['by_severity']['CRITICAL']}\n"
        report += f"- **High:** {summary['by_severity']['HIGH']}\n"
        report += f"- **Medium:** {summary['by_severity']['MEDIUM']}\n"
        report += f"- **Low:** {summary['by_severity']['LOW']}\n"
        
        return report
```

---

## CLI Integration

```bash
# Run deterministic engine + A-Team critique
python3 -m chatbot.main --gen-arch-truth-team architecture.mmd

# Output:
# report/architecture_name/
#   ground_truth.json           (deterministic)
#   artifact_analysis.json      (5 artifacts parsed)
#   agent_memory.json           (shared findings)
#   architect_critique.json     (Agent 1)
#   tester_critique.json        (Agent 2)
#   red_team_critique.json      (Agent 3)
#   consolidated_findings.json  (de-duplicated)
#   validation_report.md        (Pass/Fail)
#   final_confidence.json       (99.5% ± agents)
```

---

## Implementation Roadmap

| Phase | Component | Hours | Priority |
|-------|-----------|-------|----------|
| 1 | Artifact Parser | 1.5 | CRITICAL |
| 2 | Agent Memory | 1 | CRITICAL |
| 3 | Architect Agent (enhance existing) | 2 | HIGH |
| 4 | Tester Agent | 2 | HIGH |
| 5 | Red Team Agent | 3 | HIGH |
| 6 | Orchestrator | 2 | HIGH |
| 7 | CLI Integration | 1 | MEDIUM |
| 8 | Testing & Validation | 2 | MEDIUM |
| **Total** | **14.5 hours** | | |

---

## Success Criteria

### Artifact Utilization
- [ ] All 5 artifacts parsed and validated
- [ ] Agents use artifact indexes (not raw data)
- [ ] 100% artifact coverage across agents

### Team Collaboration
- [ ] Agents run in parallel (not sequential)
- [ ] Shared memory enables cross-referencing
- [ ] De-duplication of findings (no repeats)

### Confidence Accuracy
- [ ] Final confidence: 99.5% ± 30% (3 agents)
- [ ] Adjustments justified per agent
- [ ] Breakdown shows per-artifact scores

### Performance
- [ ] All 3 agents complete in ≤90 seconds (parallel)
- [ ] Artifact parsing ≤5 seconds
- [ ] Memory operations thread-safe

---

**Document Version:** 1.0  
**Date:** 2026-05-15  
**Purpose:** Multi-agent team architecture with shared memory and 5-artifact utilization  
**Supersedes:** PHASE3C_NEXT_STEPS.md (sequential approach)
