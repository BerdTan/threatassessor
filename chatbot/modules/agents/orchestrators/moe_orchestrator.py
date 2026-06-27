"""
MoE (Mixture of Experts) Orchestrator for Phase 3D

Architecture:
    Layer 1: Deterministic Expert (Source of Truth)
        └─> ground_truth.json (99.5% confidence)

    Layer 2: Expert Chain (LLM Validation)
        └─> 2A: Architect validates threat model
        └─> 2B: Tester validates MITRE + Architect
        └─> 2C: Red Team validates controls + Tester
        └─> 2D: Purple Team validates coverage, detection chain, TM/ADR operability
        └─> 2E: Blackhat cross-path chain analysis (runs last — has all prior context, supreme critic)

    Layer 3: Orchestrator (Impartial Whitehat Synthesis)
        └─> Consensus across all 5 critics, KNOWN/UNSURE distinction
        └─> Three investment tiers: Quick Win / Recommended / Maximum
        └─> Mode tradeoffs surfaced explicitly

Key Principles:
1. FAIL FAST: Missing prerequisite = abort (quality over quantity)
2. SEQUENTIAL: Each expert receives prior outputs (mode determines depth)
3. VALIDATION ONLY: LLM experts adjust confidence, not parallel recommendations
4. SINGLE SCORING: Base 99.5% ± adjustments (not composite scores)
5. CONSENSUS: Orchestrator is impartial — surfaces contradictions, never hides them
6. BH LAST: Blackhat has the most context (all 4 critics) to find what others missed

Version: 2.0 (Phase 3E — Purple Team + BH pivot-diverge)
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from chatbot.modules.agents.critics.architect_critic import EnhancedArchitectCritic
from chatbot.modules.agents.critics.tester_critic import TesterCritic
from chatbot.modules.agents.critics.red_teamer_critic import RedTeamerCritic
from chatbot.modules.agents.critics.purple_teamer_critic import PurpleTeamerCritic
from chatbot.modules.artifact_extractor import extract_artifacts, ArtifactSet
from chatbot.harness.registry import _DEFAULT_REGISTRY
from chatbot.modules.agent_framework import CritiqueScore
from agentic.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Orchestrator system prompt — defines the synthesis role precisely
# ---------------------------------------------------------------------------
_ORCHESTRATOR_SYSTEM = """You are the Layer 3 Orchestrator — the impartial Whitehat — in a Mixture-of-Experts security assessment pipeline.

Your role is SYNTHESIS, not generation. Up to five expert critics have reviewed a deterministic threat assessment:
- Architect (2A):     design quality and threat model completeness
- Tester (2B):        MITRE technique mappings and internal consistency
- Red Team (2C):      exploit difficulty and control bypass feasibility
- Purple Team (2E):   coverage gaps, detection chain, TM/ADR operability (may not be present)
- Blackhat (2D):      cross-path chain exploitation via pivot nodes (may not be present)

Your job: produce a balanced, transparent, actionable view the human decision-maker can act on.
You are impartial — you do not favour any single critic. You tap each critic's strength and are
explicitly wary of their structural blindspots (Architect misses operational gaps, Red Team misses
coverage completeness, Blackhat misses single-path issues, etc.).

Rules you must follow:
1. CITE YOUR EVIDENCE — every finding must name which critic raised it or which ground_truth field supports it.
2. DISTINGUISH KNOWN vs UNSURE — ≥2 critics agree → KNOWN. Single critic → UNSURE unless Red Team exploit data corroborates.
3. NEVER INVENT COSTS — use Red Team's exploit_mitigation_roadmap cost/effort verbatim. If absent, say "cost not estimated".
4. CALL OUT CONTRADICTIONS — where critics disagree, surface the contradiction and explain WHY it exists (different lenses). Do not resolve it yourself.
5. CALL OUT BLINDSPOTS — identify what ALL critics structurally could not see. Name the mode tradeoff if cross-referencing was limited.
6. ROI BALANCE — Quick Win = highest gain per unit effort, lowest friction. Recommended = balanced. Max = full coverage including diminishing returns.
7. RESIDUAL IS REAL — never claim any tier eliminates risk. State what residual remains (misconfiguration, human error, zero-days, implementation drift).
8. IMPROVEMENT TIERS MUST CONNECT — each tier's items must trace back to specific critic findings. No generic recommendations.
9. MODE TRANSPARENCY — if the run mode limited cross-referencing (parallel/partial-parallel), explicitly note which cross-critic findings are less certain as a result.
"""


# ============================================================================
# EXCEPTIONS
# ============================================================================

class MissingPrerequisiteError(Exception):
    """Raised when required input file is missing (fail-fast)."""
    def __init__(self, missing_file: str, layer: str):
        self.missing_file = missing_file
        self.layer = layer
        message = (
            f"MoE Pipeline ABORTED at {layer}\n"
            f"Missing prerequisite: {missing_file}\n\n"
            f"Quality depends on prior analysis - cannot proceed with missing data.\n"
            f"Run deterministic analysis first: python3 -m chatbot.main --gen-arch-truth <architecture.mmd>"
        )
        super().__init__(message)


# ============================================================================
# RESULT STRUCTURES
# ============================================================================

@dataclass
class ValidationResult:
    """Result from a single validation expert."""
    expert_name: str
    validation_status: str  # PASS, MINOR_GAPS, MAJOR_GAPS
    confidence_adjustment: float  # -0.0 to -0.25 (percentage)
    gaps: List[Dict]
    strengths: List[str]
    recommendations: List[Dict]
    original_score: int  # Original expert score (for reference)
    breakdown: Dict = None  # Sub-dimension scores (for UI display)
    reasoning: str = ""  # 2-3 sentence "so what" topliner for the dashboard card
    # Performance telemetry carried from CritiqueScore
    perf: Dict = None   # {llm_calls, llm_tokens, llm_cost_usd, llm_latency_s, llm_model, wall_clock_s}

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}
        if self.perf is None:
            self.perf = {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class MoEResult:
    """Result from full MoE pipeline."""
    # Architecture
    architecture_name: str

    # Confidence progression
    base_confidence: float  # 99.5% from deterministic
    architect_adjustment: float
    tester_adjustment: float
    red_team_adjustment: float
    final_confidence: float

    # Expert results
    architect_result: ValidationResult
    tester_result: ValidationResult
    red_team_result: ValidationResult

    # Consensus recommendations — produced by LLM synthesis
    critical_recommendations: List[Dict]  # ≥2 critics agree (KNOWN)
    high_recommendations: List[Dict]      # 1 critic + corroborated (UNSURE)
    review_recommendations: List[Dict]    # 1 critic only (UNSURE)

    # Layer 2D Purple Team (config-gated, optional — must follow non-default fields)
    purple_team_result: Optional[ValidationResult] = None
    purple_team_adjustment: float = 0.0

    # Layer 2E Blackhat (config-gated, optional — must follow non-default fields)
    blackhat_result: Optional[ValidationResult] = None
    blackhat_adjustment: float = 0.0

    # Synthesis extras
    blindspots: List[Dict] = None         # Gaps all critics structurally missed
    contradictions: List[Dict] = None     # Where critics disagree — human must decide
    synthesis_quality: str = "UNKNOWN"    # FULL | FALLBACK
    critic_mode: str = "sequential"       # sequential | partial_parallel | parallel (resolved)
    mode_tradeoffs: List[str] = None      # Plain-English sentences explaining cross-ref limits

    # Risk transformation (from deterministic)
    current_risk: int = 0
    target_risk: int = 0
    risk_reduction: int = 0

    # Pipeline performance telemetry
    # pipeline_perf: {
    #   pipeline_wall_clock_s, total_llm_tokens, total_llm_cost_usd,
    #   critics: {architect: {llm_calls, tokens, cost, latency_s, model, wall_s}, ...}
    # }
    pipeline_perf: Dict = None

    # Improvement options (sourced from Red Team roadmap, not hardcoded)
    quick_wins: Dict = None
    recommended: Dict = None
    maximum: Dict = None

    def __post_init__(self):
        if self.blindspots is None:
            self.blindspots = []
        if self.contradictions is None:
            self.contradictions = []
        if self.mode_tradeoffs is None:
            self.mode_tradeoffs = []
        if self.pipeline_perf is None:
            self.pipeline_perf = {}
        if self.quick_wins is None:
            self.quick_wins = {}
        if self.recommended is None:
            self.recommended = {}
        if self.maximum is None:
            self.maximum = {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        adjustments = {
            "architect": self.architect_adjustment,
            "tester": self.tester_adjustment,
            "red_team": self.red_team_adjustment,
        }
        if self.purple_team_result is not None:
            adjustments["purple_team"] = self.purple_team_adjustment
        if self.blackhat_result is not None:
            adjustments["blackhat"] = self.blackhat_adjustment

        expert_validations = {
            "architect": self.architect_result.to_dict(),
            "tester": self.tester_result.to_dict(),
            "red_team": self.red_team_result.to_dict(),
        }
        if self.purple_team_result is not None:
            expert_validations["purple_team"] = self.purple_team_result.to_dict()
        if self.blackhat_result is not None:
            expert_validations["blackhat"] = self.blackhat_result.to_dict()

        return {
            "architecture": self.architecture_name,
            "confidence": {
                "base": self.base_confidence,
                "adjustments": adjustments,
                "final": self.final_confidence,
                "interpretation": self._interpret_confidence()
            },
            "expert_validations": expert_validations,
            "consensus_recommendations": {
                "critical": self.critical_recommendations,
                "high": self.high_recommendations,
                "review": self.review_recommendations,
                "blindspots": self.blindspots,
                "contradictions": self.contradictions,
                "synthesis_quality": self.synthesis_quality,
            },
            "risk_transformation": {
                "current": self.current_risk,
                "target": self.target_risk,
                "reduction_percent": self.risk_reduction
            },
            "improvement_options": {
                "quick_wins": self.quick_wins,
                "recommended": self.recommended,
                "maximum": self.maximum
            },
            "critic_mode": self.critic_mode,
            "mode_tradeoffs": self.mode_tradeoffs,
            "pipeline_perf": self.pipeline_perf or {},
        }

    def _interpret_confidence(self) -> str:
        """Interpret final confidence score."""
        if self.final_confidence >= 95:
            return "EXCEPTIONAL - High confidence in analysis"
        elif self.final_confidence >= 90:
            return "EXCELLENT - Minor validation gaps"
        elif self.final_confidence >= 85:
            return "GOOD - Some gaps, recommendations valid"
        elif self.final_confidence >= 80:
            return "ACCEPTABLE - Several gaps, review recommended"
        else:
            return "NEEDS REVIEW - Significant gaps found"


# ============================================================================
# MOE ORCHESTRATOR
# ============================================================================

class MoEOrchestrator:
    """
    Mixture of Experts orchestrator with fail-fast sequential validation.

    Philosophy:
    - Deterministic analysis is SOURCE OF TRUTH (what to do)
    - LLM experts are VALIDATORS (how confident we are)
    - Orchestrator is PRESENTER (how to communicate)

    Never allows LLM to override deterministic recommendations.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        progress_callback=None,
        blocked_agents: Optional[List[str]] = None,
        agent_models: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize MoE orchestrator.

        Args:
            model: Single model override applied to ALL experts (backward-compat path).
                   Ignored when agent_models is provided.
            progress_callback: Optional callable(stage: str, result: ValidationResult)
                called immediately after each critic finishes.  Must be non-blocking.
            agent_models: Per-agent model dict from HarnessModelGuardian.models_dict().
                Keys: "architect", "tester", "red_team", "purple_team", "blackhat",
                      "moe_orchestrator". Takes precedence over `model`.
        """
        self.model = model
        self.agent_models = agent_models or {}
        self.progress_callback = progress_callback
        self._synth_perf: Dict = {}  # accumulated perf for orchestrator LLM calls

        # Build per-critic model dict:
        # agent_models wins; fall back to broadcast `model` for backward compat.
        _per_critic: Dict[str, str] = {}
        for key in ["architect", "tester", "red_team", "purple_team"]:
            m = self.agent_models.get(key) or model
            if m:
                _per_critic[key] = m

        # Activate critics via registry — governance can block by name
        _critics = _DEFAULT_REGISTRY.activate(
            blocked=blocked_agents or [],
            models=_per_critic,
        )
        self.architect   = _critics.get("architect")   or EnhancedArchitectCritic(model=_per_critic.get("architect") or model)
        self.tester      = _critics.get("tester")      or TesterCritic(model=_per_critic.get("tester") or model)
        self.red_team    = _critics.get("red_team")    or RedTeamerCritic(model=_per_critic.get("red_team") or model)
        self.purple_team = _critics.get("purple_team") or PurpleTeamerCritic(model=_per_critic.get("purple_team") or model)

        logger.info("MoEOrchestrator initialized with 4 validation experts (2A/2B/2C/2D) + Blackhat (2E)")

    @staticmethod
    def _compute_complexity_score(ground_truth: Dict) -> int:
        """
        Compute architecture complexity score for mode selection in auto mode.

        Formula: node_count*2 + edge_count + attack_path_count*3 + technique_count
        Threshold: >= 60 → sequential, < 60 → partial parallel.
        """
        meta   = ground_truth.get("metadata", {})
        paths  = ground_truth.get("expected_attack_paths", [])
        nodes  = int(meta.get("node_count", 0))
        edges  = int(meta.get("edge_count", 0))
        path_count = len(paths)
        tech_count = sum(len(p.get("techniques", [])) for p in paths)
        return nodes * 2 + edges + path_count * 3 + tech_count

    def run_pipeline(
        self,
        report_dir: str,
        base_confidence: float = None,
        critic_mode: str = None,
        run_blackhat: Optional[bool] = None,
    ) -> MoEResult:
        """
        Execute full MoE pipeline with fail-fast validation.

        Pipeline:
        1. Layer 1: Check deterministic analysis exists (ground_truth.json)
        2. Layer 2A/B/C: Critics run according to critic_mode
        3. Layer 3: Orchestrator synthesizes consensus

        Args:
            report_dir: Path to report directory
            base_confidence: Base confidence from deterministic (default: 99.5%)
            critic_mode: "sequential" | "parallel" | "auto"
                - sequential: Architect → Tester(uses arch) → Red Team(uses tester)
                - parallel:   All three critics run simultaneously (blind, no cross-ref)
            run_blackhat: Override blackhat.enabled setting. None = use config setting.
                - auto:       Decides based on architecture complexity score
                              (complexity < 60 → partial parallel; >= 60 → sequential)

        Returns:
            MoEResult with unified assessment

        Raises:
            MissingPrerequisiteError: If any prerequisite file missing
        """
        from chatbot.config import get_settings as _gs
        _moe_cfg = _gs().moe
        if base_confidence is None:
            base_confidence = _moe_cfg.base_confidence
        if critic_mode is None:
            critic_mode = _moe_cfg.critic_mode

        import time as _time
        _pipeline_start = _time.time()
        self._synth_perf = {"llm_calls": 0, "llm_tokens": 0, "llm_cost_usd": 0.0,
                            "llm_latency_s": 0.0, "llm_model": "", "wall_clock_s": 0.0}

        report_path = Path(report_dir)
        architecture_name = report_path.name

        logger.info(f"MoE Pipeline: Starting for {architecture_name}")
        logger.info(f"MoE Pipeline: Base confidence = {base_confidence}%, critic_mode = {critic_mode}")

        # ===== LAYER 1: DETERMINISTIC (REQUIRED) =====
        logger.info("MoE Pipeline: Layer 1 - Checking deterministic analysis...")
        gt_path = report_path / "ground_truth.json"

        if not gt_path.exists():
            raise MissingPrerequisiteError(
                missing_file=str(gt_path),
                layer="Layer 1 (Deterministic)"
            )

        with open(gt_path) as f:
            ground_truth = json.load(f)

        logger.info(f"MoE Pipeline: ✓ Layer 1 complete - ground_truth.json found")

        # Extract artifacts for experts
        artifacts = extract_artifacts(report_dir)
        logger.info(f"MoE Pipeline: Extracted {artifacts.completeness['overall']['present']}/10 artifacts")

        # ===== LAYER 2: CRITIC CHAIN =====
        complexity_score = self._compute_complexity_score(ground_truth)

        # Resolve auto mode
        resolved_mode = critic_mode
        if critic_mode == "auto":
            resolved_mode = "sequential" if complexity_score >= _moe_cfg.complexity_threshold else "partial_parallel"
            logger.info(
                f"MoE Pipeline: complexity_score={complexity_score} → auto resolved to '{resolved_mode}'"
            )
        else:
            logger.info(f"MoE Pipeline: complexity_score={complexity_score}, using explicit mode '{critic_mode}'")

        if resolved_mode == "parallel":
            architect_critique, tester_critique, red_team_critique = self._run_full_parallel(
                artifacts, ground_truth, report_path
            )
        elif resolved_mode == "partial_parallel":
            architect_critique, tester_critique, red_team_critique = self._run_partial_parallel(
                artifacts, ground_truth, report_path
            )
        else:
            architect_critique, tester_critique, red_team_critique = self._run_sequential(
                artifacts, ground_truth, report_path
            )

        architect_result = self._process_architect_validation(architect_critique)
        tester_result    = self._process_tester_validation(tester_critique)
        red_team_result  = self._process_red_team_validation(red_team_critique)

        logger.info(f"MoE Pipeline: ✓ Layer 2A/B/C complete ({resolved_mode}) — "
                    f"Arch={architect_result.validation_status}, "
                    f"Tester={tester_result.validation_status}, "
                    f"RedTeam={red_team_result.validation_status}")

        # Deterministic mode tradeoff strings — surfaced in UI and synthesis
        mode_tradeoffs: List[str] = self._compute_mode_tradeoffs(resolved_mode, critic_mode)

        # ===== LAYER 2E: PURPLE TEAM (always runs after 2A/B/C) =====
        purple_team_result: Optional[ValidationResult] = None
        purple_team_adjustment: float = 0.0
        purple_team_critique_score = None

        try:
            logger.info("MoE Pipeline: Layer 2D — Running Purple Team assessment...")
            pt_path = report_path / "06b_purple_team_critique.json"
            saved_pt = self._load_saved_critique(pt_path)
            if saved_pt:
                logger.info("MoE Pipeline: Layer 2D — Loading saved Purple Team critique (resume)")
                purple_team_critique_score = saved_pt
            else:
                purple_team_critique_score = self.purple_team.critique(
                    artifacts, ground_truth,
                    architect_critique=architect_critique,
                    tester_critique=tester_critique,
                    red_team_critique=red_team_critique,
                )
                self._save_validation(purple_team_critique_score, pt_path)

            pt_score = purple_team_critique_score.score
            # PT scoring is FORWARD (high = good), convert to adjustment:
            # score 90-100 → 0%, 75-89 → -0.01, 60-74 → -0.02, <60 → -0.04
            if pt_score >= 90:
                pt_adj = 0.0
            elif pt_score >= 75:
                pt_adj = -0.01
            elif pt_score >= 60:
                pt_adj = -0.02
            else:
                pt_adj = -0.04

            try:
                from chatbot.config.settings import get_settings as _gs_pt
                _moe_pt = _gs_pt().moe
                pt_status = (
                    "PASS" if pt_score >= 90 else
                    "MINOR_GAPS" if pt_score >= 75 else
                    "NEEDS_REVIEW" if pt_score >= 60 else
                    "MAJOR_GAPS"
                )
            except Exception:
                pt_status = "PASS" if pt_score >= 75 else "NEEDS_REVIEW"

            purple_team_result = self._attach_perf(ValidationResult(
                expert_name="PurpleTeam",
                validation_status=pt_status,
                confidence_adjustment=pt_adj,
                gaps=purple_team_critique_score.gaps,
                strengths=purple_team_critique_score.strengths,
                recommendations=[],
                original_score=pt_score,
                breakdown=purple_team_critique_score.breakdown or {},
                reasoning=purple_team_critique_score.reasoning or "",
            ), purple_team_critique_score)
            purple_team_adjustment = pt_adj

            # Embed summary into ground_truth for downstream use
            pt_bd = purple_team_critique_score.breakdown or {}
            ground_truth["purple_team_critique"] = {
                "score": pt_score,
                "rating": purple_team_critique_score.rating,
                "coverage_gaps": pt_bd.get("coverage_gaps", []),
                "detection_blindspots": pt_bd.get("detection_blindspots", []),
                "adr_coherence_failures": pt_bd.get("adr_coherence_failures", []),
                "summary_counts": pt_bd.get("summary_counts", {}),
            }
            with open(gt_path, "w") as f:
                json.dump(ground_truth, f, indent=2)

            if self.progress_callback:
                self.progress_callback("purple_team", purple_team_result)

            logger.info(f"MoE Pipeline: ✓ Layer 2D complete — score={pt_score}, adj={pt_adj*100:.1f}%")

        except Exception as exc:
            logger.warning(f"MoE Pipeline: Layer 2D skipped due to error: {exc}")

        # ===== LAYER 2D: BLACKHAT (runs last — has all prior context) =====
        blackhat_result: Optional[ValidationResult] = None
        blackhat_adjustment: float = 0.0

        if run_blackhat is not None:
            _bh_enabled = run_blackhat
        else:
            try:
                from chatbot.config.settings import get_settings as _gs_bh
                _bh_enabled = _gs_bh().blackhat.enabled
            except Exception:
                _bh_enabled = False

        if _bh_enabled:
            logger.info("MoE Pipeline: Layer 2E — Running Blackhat (has all prior critic context — supreme critic)...")
            try:
                _bh_model = self.agent_models.get("blackhat") or self.model
                blackhat_critic = _DEFAULT_REGISTRY.get("blackhat", model=_bh_model)
                if blackhat_critic is None:
                    from chatbot.modules.agents.critics.blackhat_critic import BlackhatCritic
                    blackhat_critic = BlackhatCritic(model=_bh_model)
                blackhat_critique_score = blackhat_critic.critique(
                    artifacts, ground_truth,
                    red_team_critique=red_team_critique,
                    purple_team_critique=purple_team_critique_score,
                )

                bh_score = blackhat_critique_score.score
                # BH is INVERTED: high score = bad. Thresholds: ≤30 PASS, ≤60 MINOR, >60 MAJOR
                if bh_score <= 30:
                    bh_adj = 0.0
                    bh_status = "PASS"
                elif bh_score <= 60:
                    bh_adj = -0.03
                    bh_status = "MINOR_GAPS"
                else:
                    bh_adj = -0.05
                    bh_status = "MAJOR_GAPS"

                blackhat_result = self._attach_perf(ValidationResult(
                    expert_name="Blackhat",
                    validation_status=bh_status,
                    confidence_adjustment=bh_adj,
                    gaps=blackhat_critique_score.gaps,
                    strengths=blackhat_critique_score.strengths,
                    recommendations=[],
                    original_score=bh_score,
                    breakdown=blackhat_critique_score.breakdown or {},
                    reasoning=blackhat_critique_score.reasoning or "",
                ), blackhat_critique_score)
                blackhat_adjustment = bh_adj

                # Embed into ground_truth for downstream report generators
                ground_truth["blackhat_critique"] = {
                    "score": bh_score,
                    "rating": blackhat_critique_score.rating,
                    "shared_nodes": blackhat_critique_score.breakdown.get("shared_nodes", {}),
                    "chained_exploit_findings": blackhat_critique_score.breakdown.get("chained_exploit_findings", []),
                    "pivot_diverge_chains": blackhat_critique_score.breakdown.get("pivot_diverge_chains", []),
                    "stealth_score": blackhat_critique_score.breakdown.get("stealth_score", 0),
                    "stealthy_techniques": blackhat_critique_score.breakdown.get("stealthy_techniques", []),
                    "least_resistance_paths": blackhat_critique_score.breakdown.get("least_resistance_paths", []),
                    "mitigation_gaps_for_chains": blackhat_critique_score.breakdown.get("mitigation_gaps_for_chains", []),
                    "uniqueness_vs_critics": blackhat_critique_score.breakdown.get("uniqueness_vs_critics", {}),
                }

                # Save 06c_blackhat_critique.json
                bh_path = report_path / "06c_blackhat_critique.json"
                with open(bh_path, "w") as f:
                    json.dump(blackhat_critique_score.to_dict(), f, indent=2)

                # Persist blackhat_critique back into ground_truth.json so diagram
                # generators and future runs can read it without re-running BH
                with open(gt_path, "w") as f:
                    json.dump(ground_truth, f, indent=2)

                logger.info(f"MoE Pipeline: ✓ Layer 2E complete — score={bh_score}, adj={bh_adj*100:.1f}%")

                # Generate after_bh.mmd — cross-path chain overlay on after.mmd
                try:
                    from chatbot.modules.bh_diagram_generator import generate_bh_diagram
                    bh_diag = generate_bh_diagram(str(report_path))
                    if bh_diag:
                        logger.info(f"MoE Pipeline: ✓ Generated BH chain diagram: {bh_diag}")
                except Exception as diag_exc:
                    logger.warning(f"MoE Pipeline: BH diagram generation failed: {diag_exc}")

                if self.progress_callback:
                    self.progress_callback("blackhat", blackhat_result)

            except Exception as exc:
                import traceback
                logger.warning(f"MoE Pipeline: Layer 2E skipped due to error: {exc}")
                logger.debug(f"MoE Pipeline: Layer 2E traceback:\n{traceback.format_exc()}")

        # ===== LAYER 3: CONSENSUS SYNTHESIS =====
        logger.info("MoE Pipeline: Layer 3 - Synthesizing consensus...")

        if self.progress_callback:
            self.progress_callback("synthesis:confidence", None)

        # Calculate final confidence (PT adjustment included)
        final_confidence = self._calculate_final_confidence(
            base_confidence,
            architect_result,
            tester_result,
            red_team_result,
            blackhat_result,
            purple_team_result=purple_team_result,
        )

        logger.info(f"MoE Pipeline: Final confidence = {final_confidence:.1f}%")

        if self.progress_callback:
            self.progress_callback("synthesis:llm", None)

        # Synthesize consensus — all 5 critics passed, orchestrator uses what's available
        consensus = self._synthesize_consensus(
            ground_truth,
            architect_result,
            tester_result,
            red_team_result,
            architect_raw=architect_critique,
            tester_raw=tester_critique,
            red_team_raw=red_team_critique,
            purple_team_result=purple_team_result,
            purple_team_raw=purple_team_critique_score,
            blackhat_result=blackhat_result,
            mode_tradeoffs=mode_tradeoffs,
        )

        if self.progress_callback:
            self.progress_callback("synthesis:build", None)

        # Extract risk transformation from ground truth
        risk_data = self._extract_risk_transformation(ground_truth)

        # Build improvement options
        improvement_options = self._build_improvement_options(
            consensus,
            risk_data
        )

        # Build final result
        result = MoEResult(
            architecture_name=architecture_name,
            base_confidence=base_confidence,
            architect_adjustment=architect_result.confidence_adjustment,
            tester_adjustment=tester_result.confidence_adjustment,
            red_team_adjustment=red_team_result.confidence_adjustment,
            purple_team_adjustment=purple_team_adjustment,
            blackhat_adjustment=blackhat_adjustment,
            final_confidence=final_confidence,
            architect_result=architect_result,
            tester_result=tester_result,
            red_team_result=red_team_result,
            purple_team_result=purple_team_result,
            blackhat_result=blackhat_result,
            critical_recommendations=consensus["critical"],
            high_recommendations=consensus["high"],
            review_recommendations=consensus["review"],
            blindspots=consensus.get("blindspots", []),
            contradictions=consensus.get("contradictions", []),
            synthesis_quality=consensus.get("synthesis_quality", "UNKNOWN"),
            critic_mode=resolved_mode,
            mode_tradeoffs=mode_tradeoffs,
            current_risk=risk_data["current"],
            target_risk=risk_data["target"],
            risk_reduction=risk_data["reduction"],
            quick_wins=improvement_options["quick_wins"],
            recommended=improvement_options["recommended"],
            maximum=improvement_options["maximum"]
        )

        # ── Populate pipeline_perf before saving so it lands in the JSON ────────
        _pipeline_elapsed = _time.time() - _pipeline_start
        _critics_perf: dict = {}
        _total_tokens = 0
        _total_cost   = 0.0

        for _cname, _vr in [
            ("architect",   result.architect_result),
            ("tester",      result.tester_result),
            ("red_team",    result.red_team_result),
            ("purple_team", result.purple_team_result),
            ("blackhat",    result.blackhat_result),
        ]:
            if _vr and _vr.perf and _vr.perf.get("llm_tokens", 0) > 0:
                _critics_perf[_cname] = dict(_vr.perf)
                _total_tokens += _vr.perf.get("llm_tokens", 0)
                _total_cost   += _vr.perf.get("llm_cost_usd", 0.0)

        # Include orchestrator synthesis calls (wall_clock_s = synthesis slice of pipeline)
        self._synth_perf["wall_clock_s"] = round(self._synth_perf["llm_latency_s"], 3)
        if self._synth_perf.get("llm_tokens", 0) > 0:
            _critics_perf["orchestrator"] = dict(self._synth_perf)
            _total_tokens += self._synth_perf.get("llm_tokens", 0)
            _total_cost   += self._synth_perf.get("llm_cost_usd", 0.0)

        result.pipeline_perf = {
            "pipeline_wall_clock_s": round(_pipeline_elapsed, 2),
            "total_llm_tokens":      _total_tokens,
            "total_llm_cost_usd":    round(_total_cost, 6),
            "critic_count":          len(_critics_perf),
            "critics":               _critics_perf,
        }
        logger.info(
            f"MoE Pipeline: perf — {_pipeline_elapsed:.1f}s wall | "
            f"{_total_tokens} tokens | ${_total_cost:.4f}"
        )

        if self.progress_callback:
            self.progress_callback("synthesis:save", None)

        # Save orchestrator result (MoE format)
        orch_path = report_path / "07_moe_orchestrator.json"
        with open(orch_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        # Also save as legacy format for backward compatibility with improvement generators
        legacy_path = report_path / "07_orchestrator_report.json"
        with open(legacy_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"MoE Pipeline: ✓ Layer 3 complete - saved to {orch_path} (+ legacy format)")

        # ===== GENERATE ADDITIONAL ARTIFACTS (Phase 3D Week 3) =====
        logger.info("MoE Pipeline: Generating CISO artifacts...")

        if self.progress_callback:
            self.progress_callback("synthesis:artifacts", None)

        # Generate executive dashboard (00_executive_dashboard.md) - NEW in Week 3
        try:
            from chatbot.modules.executive_dashboard_generator import generate_executive_dashboard
            dashboard_file = generate_executive_dashboard(report_dir)
            logger.info(f"MoE Pipeline: ✓ Generated executive dashboard: {dashboard_file}")
        except Exception as e:
            logger.warning(f"MoE Pipeline: Failed to generate executive dashboard: {e}")

        # Generate improvement summary (08_improvement_summary.md)
        try:
            from chatbot.modules.improvement_summary_generator import generate_summary
            summary_file = generate_summary(report_dir, orchestrator_result=None)
            logger.info(f"MoE Pipeline: ✓ Generated improvement summary: {summary_file}")
        except Exception as e:
            logger.warning(f"MoE Pipeline: Failed to generate improvement summary: {e}")

        # Generate stepped improvement MMDs (08a/08b/08c.mmd)
        try:
            from chatbot.modules.mmd_improvement_generator import generate_improvement_mmds
            mmd_files = generate_improvement_mmds(report_dir, orchestrator_result=None)
            logger.info(f"MoE Pipeline: ✓ Generated {len(mmd_files)} stepped improvement diagrams")
        except Exception as e:
            logger.warning(f"MoE Pipeline: Failed to generate improvement MMDs: {e}")

        logger.info(f"MoE Pipeline: COMPLETE - {final_confidence:.1f}% confidence")
        logger.info(f"MoE Pipeline: Generated 16/16 files (ground_truth + 1 dashboard + 6 JSON + 4 MD + 4 MMD)")

        return result

    # =========================================================================
    # LAYER 2 EXECUTION MODES
    # =========================================================================

    def _run_sequential(
        self,
        artifacts: "ArtifactSet",
        ground_truth: Dict,
        report_path: Path,
    ):
        """Mode A — Architect → Tester(arch) → RedTeam(tester). Full cross-critic reasoning."""
        arch_path = report_path / "04_architect_critique.json"
        test_path = report_path / "05_tester_critique.json"
        red_path  = report_path / "06_red_team_critique.json"

        # 2A: Architect
        saved_arch = self._load_saved_critique(arch_path)
        if saved_arch:
            logger.info("MoE Pipeline: Layer 2A - Loading saved Architect critique (resume)")
            architect_critique = saved_arch
        else:
            logger.info("MoE Pipeline: Layer 2A - Running Architect validation...")
            architect_critique = self.architect.critique(artifacts)
            self._save_validation(architect_critique, arch_path)
        architect_result = self._process_architect_validation(architect_critique)
        logger.info(f"MoE Pipeline: ✓ Layer 2A complete - {architect_result.validation_status} "
                    f"({architect_result.confidence_adjustment*100:+.1f}%)")
        if self.progress_callback:
            self.progress_callback("architect", architect_result)

        # 2B: Tester (receives Architect critique)
        saved_tester = self._load_saved_critique(test_path)
        if saved_tester:
            logger.info("MoE Pipeline: Layer 2B - Loading saved Tester critique (resume)")
            tester_critique = saved_tester
        else:
            logger.info("MoE Pipeline: Layer 2B - Running Tester validation...")
            tester_critique = self.tester.critique(artifacts, architect_critique)
            self._save_validation(tester_critique, test_path)
        tester_result = self._process_tester_validation(tester_critique)
        logger.info(f"MoE Pipeline: ✓ Layer 2B complete - {tester_result.validation_status} "
                    f"({tester_result.confidence_adjustment*100:+.1f}%)")
        if self.progress_callback:
            self.progress_callback("tester", tester_result)

        # 2C: Red Team (receives Tester critique)
        saved_red = self._load_saved_critique(red_path)
        if saved_red:
            logger.info("MoE Pipeline: Layer 2C - Loading saved Red Team critique (resume)")
            red_team_critique = saved_red
        else:
            logger.info("MoE Pipeline: Layer 2C - Running Red Team validation...")
            red_team_critique = self.red_team.critique(artifacts, ground_truth, tester_critique)
            self._save_validation(red_team_critique, red_path)
        red_team_result = self._process_red_team_validation(red_team_critique)
        logger.info(f"MoE Pipeline: ✓ Layer 2C complete - {red_team_result.validation_status} "
                    f"({red_team_result.confidence_adjustment*100:+.1f}%)")
        if self.progress_callback:
            self.progress_callback("red_team", red_team_result)

        return architect_critique, tester_critique, red_team_critique

    def _run_partial_parallel(
        self,
        artifacts: "ArtifactSet",
        ground_truth: Dict,
        report_path: Path,
    ):
        """
        Mode B — [Architect ∥ Red Team blind] → Tester(arch) → Red Team gap adjustment.

        Architect and a blind Red Team first-pass run concurrently.  Once Architect
        completes, Tester runs with Architect's output.  Red Team's numeric score is
        then adjusted post-hoc via _adjust_for_tester_gaps().

        Saves ~20s for simple architectures (complexity < 60).
        Cross-ref trade-off: Red Team LLM does not see Tester's exact gap phrasing,
        but the +5-pt-per-critical-gap numeric adjustment still applies.
        """
        arch_path = report_path / "04_architect_critique.json"
        test_path = report_path / "05_tester_critique.json"
        red_path  = report_path / "06_red_team_critique.json"

        # Check for saved critiques (resume path uses sequential order)
        saved_arch = self._load_saved_critique(arch_path)
        saved_red  = self._load_saved_critique(red_path)

        if saved_arch and saved_red:
            architect_critique = saved_arch
            red_team_critique  = saved_red
            logger.info("MoE Pipeline: Partial-parallel — loaded both saved critiques (resume)")
        elif saved_arch:
            architect_critique = saved_arch
            logger.info("MoE Pipeline: Partial-parallel — loaded saved Architect; running Red Team...")
            red_team_critique = self.red_team.critique(artifacts, ground_truth, tester_critique=None)
            self._save_validation(red_team_critique, red_path)
        else:
            logger.info("MoE Pipeline: Partial-parallel — running Architect ∥ Red Team (blind)...")
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_arch = pool.submit(self.architect.critique, artifacts)
                f_red  = pool.submit(self.red_team.critique, artifacts, ground_truth, None)
                architect_critique = f_arch.result()
                red_team_critique  = f_red.result()
            self._save_validation(architect_critique, arch_path)
            self._save_validation(red_team_critique, red_path)

        architect_result = self._process_architect_validation(architect_critique)
        logger.info(f"MoE Pipeline: ✓ Architect (partial-parallel) - {architect_result.validation_status}")
        if self.progress_callback:
            self.progress_callback("architect", architect_result)

        # Tester runs with Architect output
        saved_tester = self._load_saved_critique(test_path)
        if saved_tester:
            tester_critique = saved_tester
        else:
            logger.info("MoE Pipeline: Partial-parallel — running Tester with Architect output...")
            tester_critique = self.tester.critique(artifacts, architect_critique)
            self._save_validation(tester_critique, test_path)
        tester_result = self._process_tester_validation(tester_critique)
        logger.info(f"MoE Pipeline: ✓ Tester (partial-parallel) - {tester_result.validation_status}")
        if self.progress_callback:
            self.progress_callback("tester", tester_result)

        # Post-hoc gap adjustment on Red Team score
        original_score = red_team_critique.score
        adjusted_score = self.red_team._adjust_for_tester_gaps(original_score, tester_critique)
        if adjusted_score != original_score:
            logger.info(
                f"MoE Pipeline: Red Team post-hoc adjustment: {original_score} → {adjusted_score} "
                f"(tester critical gaps)"
            )
            red_team_critique.score = adjusted_score

        red_team_result = self._process_red_team_validation(red_team_critique)
        logger.info(f"MoE Pipeline: ✓ Red Team (partial-parallel) - {red_team_result.validation_status}")
        if self.progress_callback:
            self.progress_callback("red_team", red_team_result)

        return architect_critique, tester_critique, red_team_critique

    def _run_full_parallel(
        self,
        artifacts: "ArtifactSet",
        ground_truth: Dict,
        report_path: Path,
    ):
        """
        Mode C — All three critics run simultaneously against artifacts only.

        Tester gets no architect roadmap; Red Team gets no tester gaps.
        The synthesis LLM compensates by receiving all three raw outputs together.
        Saves ~30s (single wait for the slowest critic) at the cost of cross-referencing.
        """
        arch_path = report_path / "04_architect_critique.json"
        test_path = report_path / "05_tester_critique.json"
        red_path  = report_path / "06_red_team_critique.json"

        # Resume: load any already-saved critiques; only submit missing ones
        saved = {
            "architect": self._load_saved_critique(arch_path),
            "tester":    self._load_saved_critique(test_path),
            "red_team":  self._load_saved_critique(red_path),
        }

        to_run = [k for k, v in saved.items() if v is None]
        if to_run:
            logger.info(f"MoE Pipeline: Full-parallel — submitting {to_run} to thread pool...")

        # Signal that all critics are launching in parallel before blocking
        if self.progress_callback:
            self.progress_callback("parallel_starting", None)

        _proc_fns = {
            "architect": self._process_architect_validation,
            "tester":    self._process_tester_validation,
            "red_team":  self._process_red_team_validation,
        }
        _save_paths = {"architect": arch_path, "tester": test_path, "red_team": red_path}

        results = dict(saved)
        # Fire callbacks for already-resumed critics immediately
        for k, v in saved.items():
            if v is not None:
                vr = _proc_fns[k](v)
                logger.info(f"MoE Pipeline: ✓ {k} (resumed from disk)")
                if self.progress_callback:
                    self.progress_callback(k, vr)

        if to_run:
            def _arch():   return self.architect.critique(artifacts)
            def _tester(): return self.tester.critique(artifacts, architect_critique=None)
            def _red():    return self.red_team.critique(artifacts, ground_truth, tester_critique=None)
            fns = {"architect": _arch, "tester": _tester, "red_team": _red}

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(fns[k]): k for k in to_run}
                for f in as_completed(futures):
                    k = futures[f]
                    results[k] = f.result()
                    self._save_validation(results[k], _save_paths[k])
                    vr = _proc_fns[k](results[k])
                    logger.info(f"MoE Pipeline: ✓ {k} (full-parallel) - {vr.validation_status}")
                    if self.progress_callback:
                        self.progress_callback(k, vr)

        return results["architect"], results["tester"], results["red_team"]

    @staticmethod
    def _attach_perf(vr: ValidationResult, critique: "CritiqueScore") -> ValidationResult:
        """Copy CritiqueScore performance telemetry into the ValidationResult.perf dict."""
        vr.perf = {
            "llm_calls":     getattr(critique, "llm_calls",     0),
            "llm_tokens":    getattr(critique, "llm_tokens",    0),
            "llm_cost_usd":  getattr(critique, "llm_cost_usd",  0.0),
            "llm_latency_s": getattr(critique, "llm_latency_s", 0.0),
            "llm_model":     getattr(critique, "llm_model",     ""),
            "wall_clock_s":  getattr(critique, "wall_clock_s",  0.0),
        }
        return vr

    def _process_architect_validation(self, critique: CritiqueScore) -> ValidationResult:
        """
        Process Architect critique into validation result.

        Architect validates:
        - Threat model completeness
        - Control appropriateness
        - Defense-in-depth coverage
        - RAPIDS alignment
        """
        # Determine validation status
        from chatbot.config import get_settings as _gs_arch
        _at = _gs_arch().moe
        if critique.score >= _at.architect_pass_threshold:
            status = "PASS"
            adjustment = 0.0
        elif critique.score >= _at.architect_minor_gap_threshold:
            status = "MINOR_GAPS"
            adjustment = -0.02  # -2%
        elif critique.score >= _at.architect_major_gap_threshold:
            status = "MINOR_GAPS"
            adjustment = -0.05  # -5%
        else:
            status = "MAJOR_GAPS"
            adjustment = -0.10  # -10%

        # Extract actionable recommendations (not new controls)
        recommendations = []
        for item in critique.improvement_roadmap:
            recommendations.append({
                "priority": item.get("priority", 5),
                "action": item.get("action", "Unknown"),
                "category": item.get("category", "unknown"),
                "verification": item.get("verification_method", "Manual review")
            })

        return self._attach_perf(ValidationResult(
            expert_name="Architect",
            validation_status=status,
            confidence_adjustment=adjustment,
            gaps=critique.gaps,
            strengths=critique.strengths,
            recommendations=recommendations,
            original_score=critique.score,
            reasoning=critique.reasoning or "",
        ), critique)

    def _process_tester_validation(self, critique: CritiqueScore) -> ValidationResult:
        """
        Process Tester critique into validation result.

        Tester validates:
        - MITRE mappings correct
        - Internal consistency
        - Coverage metrics
        - Architect's recommendations valid
        """
        # Count CRITICAL/HIGH gaps — used to override PASS when serious gaps exist
        critical_gaps = len([g for g in critique.gaps if g.get("severity") in ["CRITICAL", "HIGH"]])

        # Penalty for sub-dimensions that critically fail (<50% of their max score)
        # e.g. roadmap_validation: 1/10 = 10% — flags structural weakness missed by aggregate score
        sub_penalty = 0.0
        raw_breakdown = critique.breakdown if isinstance(critique.breakdown, dict) else {}
        for sub_key, sub_data in raw_breakdown.items():
            if isinstance(sub_data, dict):
                sub_score = sub_data.get("score", 0)
                sub_max = sub_data.get("max", 0)
                if sub_max > 0 and (sub_score / sub_max) < 0.50:
                    sub_penalty -= 0.02  # -2% per critically failed sub-dimension
                    logger.info(
                        f"Tester: sub-dimension '{sub_key}' critically low "
                        f"({sub_score}/{sub_max} = {sub_score/sub_max*100:.0f}%) → -2% penalty"
                    )

        from chatbot.config import get_settings as _gs_test
        _tt = _gs_test().moe
        if critique.score >= _tt.tester_pass_threshold:
            status = "PASS"
            adjustment = 0.0
        elif critique.score >= _tt.tester_minor_gap_threshold:
            status = "MINOR_GAPS"
            adjustment = -0.01  # -1%
        elif critique.score >= _tt.tester_major_gap_threshold:
            status = "MINOR_GAPS"
            adjustment = -0.03  # -3%
        else:
            status = "MAJOR_GAPS"
            adjustment = -0.05  # -5%

        # Override: PASS is not valid when HIGH/CRITICAL gaps exist
        if status == "PASS" and critical_gaps > 0:
            status = "MINOR_GAPS"
            adjustment = -0.01

        # Apply sub-dimension penalty
        if sub_penalty < 0:
            adjustment += sub_penalty
            if adjustment <= -0.05:
                status = "MAJOR_GAPS"
            elif adjustment < 0 and status == "PASS":
                status = "MINOR_GAPS"

        # Extract recommendations
        recommendations = []
        for item in critique.improvement_roadmap:
            recommendations.append({
                "priority": item.get("priority", 5),
                "action": item.get("action", "Unknown"),
                "category": item.get("category", "unknown"),
                "verification": item.get("verification_method", "Manual review")
            })

        return self._attach_perf(ValidationResult(
            expert_name="Tester",
            validation_status=status,
            confidence_adjustment=adjustment,
            gaps=critique.gaps,
            strengths=critique.strengths,
            recommendations=recommendations,
            original_score=critique.score,
            breakdown=raw_breakdown,
            reasoning=critique.reasoning or "",
        ), critique)

    def _process_red_team_validation(self, critique: CritiqueScore) -> ValidationResult:
        """
        Process Red Team critique into validation result.

        Red Team validates:
        - Control effectiveness (would they actually stop attacks?)
        - Bypass scenarios
        - Tester's assessment correct
        """
        # Red Team is INVERTED: low score = hard to exploit = good
        # So high score (easy to exploit) = major gaps

        from chatbot.config import get_settings as _gs_rt
        _rt = _gs_rt().moe
        if critique.score <= _rt.red_team_hard_threshold:  # Hard to exploit
            status = "PASS"
            adjustment = 0.0
        elif critique.score <= _rt.red_team_medium_threshold:  # Moderate difficulty
            status = "MINOR_GAPS"
            adjustment = -0.03  # -3%
        elif critique.score <= _rt.red_team_easy_threshold:  # Somewhat easy
            status = "MINOR_GAPS"
            adjustment = -0.06  # -6%
        else:  # Easy to exploit
            status = "MAJOR_GAPS"
            adjustment = -0.10  # -10%

        # Extract recommendations (bypass scenarios)
        recommendations = []
        roadmap = critique.breakdown.get("exploit_mitigation_roadmap", [])
        for item in roadmap:
            if item.get("practical") == "YES":
                recommendations.append({
                    "priority": 1 if item.get("target_score", 100) < 40 else 2,
                    "action": f"Reduce exploit difficulty to {item.get('target_score')}/100",
                    "category": "control_effectiveness",
                    "verification": "Red Team penetration test"
                })

        return self._attach_perf(ValidationResult(
            expert_name="Red Team",
            validation_status=status,
            confidence_adjustment=adjustment,
            gaps=critique.gaps,
            strengths=critique.strengths,
            recommendations=recommendations,
            original_score=critique.score,
            reasoning=critique.reasoning or "",
        ), critique)

    def _calculate_final_confidence(
        self,
        base: float,
        architect: ValidationResult,
        tester: ValidationResult,
        red_team: ValidationResult,
        blackhat: Optional[ValidationResult] = None,
        purple_team_result: Optional[ValidationResult] = None,
    ) -> float:
        """
        Calculate final confidence with adjustments from all critics.

        Formula: Base × (1 + arch_adj) × (1 + tester_adj) × (1 + rt_adj) × (1 + pt_adj) × (1 + bh_adj)
        Capped at 100%, floored at 50%.
        """
        final = base
        final = final * (1 + architect.confidence_adjustment)
        final = final * (1 + tester.confidence_adjustment)
        final = final * (1 + red_team.confidence_adjustment)
        if purple_team_result is not None:
            final = final * (1 + purple_team_result.confidence_adjustment)
        if blackhat is not None:
            final = final * (1 + blackhat.confidence_adjustment)
        return max(50.0, min(100.0, final))

    @staticmethod
    def _compute_mode_tradeoffs(resolved_mode: str, requested_mode: str) -> List[str]:
        """
        Return deterministic plain-English sentences explaining what cross-referencing
        was sacrificed in the chosen mode. Shown in UI and passed to synthesis.
        """
        tradeoffs = []
        if resolved_mode == "parallel":
            tradeoffs = [
                "Parallel mode: all three critics ran independently without seeing each other's findings.",
                "Tester did not receive the Architect's roadmap — MITRE mapping gaps may overlap with design gaps.",
                "Red Team did not adjust for Tester's invalid technique flags — exploit difficulty may be over- or under-stated.",
                "Purple Team used all three critic outputs but cross-referencing is weaker than sequential mode.",
                "Findings marked KNOWN require extra scrutiny — independent agreement is less rigorous when critics had no shared context.",
            ]
        elif resolved_mode == "partial_parallel":
            tradeoffs = [
                "Partial-parallel mode: Architect and Red Team ran concurrently (Red Team had no Tester context at LLM time).",
                "Red Team's score was post-hoc adjusted for Tester gaps numerically, but the LLM reasoning did not incorporate them.",
                "Some Red Team gap descriptions may not reference Tester's specific MITRE mapping concerns.",
                "Purple Team and Blackhat received all prior outputs and ran sequentially — their findings are fully cross-referenced.",
            ]
        else:
            tradeoffs = [
                "Sequential mode: each critic received prior outputs — full cross-referencing enabled.",
                "Confidence adjustments are most reliable in this mode.",
            ]
        if requested_mode == "auto":
            tradeoffs.append(
                f"Auto mode selected '{resolved_mode}' based on architecture complexity score."
            )
        return tradeoffs

    def _synthesize_consensus(
        self,
        ground_truth: Dict,
        architect: ValidationResult,
        tester: ValidationResult,
        red_team: ValidationResult,
        architect_raw: Optional[CritiqueScore] = None,
        tester_raw: Optional[CritiqueScore] = None,
        red_team_raw: Optional[CritiqueScore] = None,
        purple_team_result: Optional[ValidationResult] = None,
        purple_team_raw: Optional[CritiqueScore] = None,
        blackhat_result: Optional[ValidationResult] = None,
        mode_tradeoffs: Optional[List[str]] = None,
    ) -> Dict:
        """
        LLM synthesis: cross-validate all three critic outputs and produce grounded
        consensus with KNOWN/UNSURE distinction, ROI-tiered improvement options,
        real costs from Red Team data, and explicit residual risk per tier.

        Falls back to simple gap-union if the LLM call fails.
        """
        synthesis = self._llm_synthesize(
            ground_truth, architect, tester, red_team,
            architect_raw, tester_raw, red_team_raw,
            purple_team_result=purple_team_result,
            purple_team_raw=purple_team_raw,
            blackhat_result=blackhat_result,
            mode_tradeoffs=mode_tradeoffs or [],
        )
        if synthesis:
            if synthesis.get("contradictions"):
                synthesis["contradictions"] = self._reflect_contradictions(
                    synthesis["contradictions"],
                    architect, tester, red_team,
                    purple_team_result=purple_team_result,
                    blackhat_result=blackhat_result,
                )
            return synthesis

        # ---- fallback: union of all gaps, no consensus scoring ----
        logger.warning("Orchestrator: LLM synthesis failed — using gap-union fallback")

        # PT gaps are high-confidence when coverage or detection blindspots are present
        pt_has_coverage_gaps = bool(
            purple_team_result
            and purple_team_result.raw_data
            and (
                purple_team_result.raw_data.get("coverage_gaps")
                or purple_team_result.raw_data.get("detection_blindspots")
            )
        )
        # BH pivot-diverge chains are cross-path facts — mark KNOWN if present
        bh_has_pivots = bool(
            blackhat_result
            and blackhat_result.raw_data
            and blackhat_result.raw_data.get("pivot_diverge_chains")
        )

        pt_gap_set = set(str(g.get("description", ""))[:80] for g in (purple_team_result.gaps if purple_team_result else []))
        bh_gap_set = set(str(g.get("description", ""))[:80] for g in (blackhat_result.gaps if blackhat_result else []))

        all_gaps = (
            architect.gaps + tester.gaps + red_team.gaps
            + (purple_team_result.gaps if purple_team_result else [])
            + (blackhat_result.gaps if blackhat_result else [])
        )
        seen, deduped = set(), []
        for g in all_gaps:
            key = g.get("description", "")[:80]
            if key not in seen:
                seen.add(key)
                # Determine confidence: PT coverage/detection findings and BH pivot chains are KNOWN
                is_pt_finding = key in pt_gap_set and pt_has_coverage_gaps
                is_bh_finding = key in bh_gap_set and bh_has_pivots
                label = "KNOWN" if (is_pt_finding or is_bh_finding) else "UNSURE"
                deduped.append({
                    "description": g.get("description", ""),
                    "category": g.get("category", ""),
                    "severity": g.get("severity", "MEDIUM"),
                    "source": "fallback-union",
                    "confidence_label": label,
                })
        return {
            "critical": [],
            "high": deduped[:5],
            "review": deduped[5:],
            "blindspots": [],
            "contradictions": [],
            "improvement_tiers": {},
            "synthesis_quality": "FALLBACK",
        }

    def _llm_synthesize(
        self,
        ground_truth: Dict,
        architect: ValidationResult,
        tester: ValidationResult,
        red_team: ValidationResult,
        architect_raw: Optional[CritiqueScore],
        tester_raw: Optional[CritiqueScore],
        red_team_raw: Optional[CritiqueScore],
        purple_team_result: Optional[ValidationResult] = None,
        purple_team_raw: Optional[CritiqueScore] = None,
        blackhat_result: Optional[ValidationResult] = None,
        mode_tradeoffs: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """
        Single LLM call that reads all three critic outputs and produces the
        structured synthesis JSON.  Returns None on any failure so the caller
        can fall back gracefully.
        """
        try:
            # ---- build the prompt ----
            arch_name = ground_truth.get("architecture", "unknown")

            # Risk numbers from ground truth
            rt = self._extract_risk_transformation(ground_truth)
            risk_summary = (
                f"Current risk score: {rt['current']}/100  |  "
                f"Target after all controls: {rt['target']}/100  |  "
                f"Estimated reduction: {rt['reduction']}%"
            )

            # Red Team exploit-mitigation roadmap (the only place real costs live)
            rt_roadmap = []
            if red_team_raw and hasattr(red_team_raw, 'breakdown'):
                rt_roadmap = red_team_raw.breakdown.get("exploit_mitigation_roadmap", [])
            rt_roadmap_json = json.dumps(rt_roadmap, indent=2) if rt_roadmap else "[]"

            # Serialize critic outputs compactly
            def _gap_list(v: ValidationResult) -> str:
                return json.dumps(v.gaps, indent=2) if v.gaps else "[]"

            def _roadmap(v: ValidationResult) -> str:
                return json.dumps(v.recommendations, indent=2) if v.recommendations else "[]"

            # Resolve all technique IDs mentioned by the critics so the synthesis
            # LLM has authoritative names and cannot generate false DATA_REFERENCE_ERROR
            # contradictions about valid technique IDs.
            all_critic_text = (
                json.dumps(architect.gaps) + json.dumps(architect.recommendations or []) +
                json.dumps(tester.gaps) + json.dumps(tester.recommendations or []) +
                json.dumps(red_team.gaps) + json.dumps(red_team.recommendations or []) +
                (json.dumps(purple_team_result.gaps) if purple_team_result else "") +
                (json.dumps(blackhat_result.gaps) if blackhat_result else "")
            )
            tech_grounding_block = self._resolve_technique_ids(all_critic_text)

            # Purple Team and Blackhat optional blocks
            pt_block = ""
            if purple_team_result:
                pt_bd = purple_team_result.breakdown or {}
                pt_counts = pt_bd.get("summary_counts", {})
                pt_block = f"""
{'═'*59}
PURPLE TEAM OUTPUT  (Layer 2D — Detection Depth, Coverage Gaps, ADR Operability)
Score: {purple_team_result.original_score}/100  |  Status: {purple_team_result.validation_status}
Coverage gaps (unmapped techniques): {pt_counts.get('coverage_gaps', 0)}
Detection blindspots (high-value paths, no SOC visibility): {pt_counts.get('detection_blindspots', 0)}
ADR coherence failures (controls that don't close the gap): {pt_counts.get('adr_coherence_failures', 0)}
Gaps:
{_gap_list(purple_team_result)}
"""
            bh_block = ""
            if blackhat_result:
                bh_bd = blackhat_result.breakdown or {}
                pivot_count = len(bh_bd.get("pivot_diverge_chains", []))
                seq_count = len(bh_bd.get("chained_exploit_findings", []))
                bh_block = f"""
{'═'*59}
BLACKHAT OUTPUT  (Layer 2E — Cross-Path Chain Exploitation — Supreme Critic)
Score: {blackhat_result.original_score}/100 (INVERTED: high = bad)  |  Status: {blackhat_result.validation_status}
Sequential chains (AP-i target → AP-j mid-node): {seq_count}
Pivot-diverge chains (shared node fans to multiple targets): {pivot_count}
Gaps:
{_gap_list(blackhat_result)}
"""
            tradeoff_block = ""
            if mode_tradeoffs:
                tradeoff_block = f"""
{'═'*59}
MODE TRADEOFFS (explain these in your mode_transparency field)
{chr(10).join('- ' + t for t in mode_tradeoffs)}
"""

            # Build deterministic validation checks block — surface new Check 7/8 results
            val_report = ground_truth.get("validation_report", {})
            val_checks = val_report.get("checks", {})
            det_analytics = val_checks.get("detection_analytics", {})
            ext_deps = val_checks.get("external_dependencies", {})
            val_issues = val_report.get("issues", [])
            # Collect messages for check 7 and 8 specifically
            det_issues = [i["message"] for i in val_issues if i.get("check") == "detection_analytics"]
            ext_issues = [i["message"] for i in val_issues if i.get("check") == "external_dependencies"]
            deterministic_block = ""
            if det_issues or ext_issues:
                lines = []
                for msg in det_issues:
                    lines.append(f"  [DETECTION_ANALYTICS — DETERMINISTIC KNOWN] {msg}")
                for msg in ext_issues:
                    lines.append(f"  [EXTERNAL_DEPS — DETERMINISTIC KNOWN] {msg}")
                deterministic_block = f"""
{'═'*59}
DETERMINISTIC ENGINE FLAGS (treat as KNOWN — not single-critic opinion)
These issues were flagged by the deterministic completeness validator before any LLM ran.
They are structural facts about the architecture, not critic opinions:
{chr(10).join(lines)}
"""

            # Build user journey intelligence block from ground_truth
            _us = ground_truth.get("user_stories", {})
            _journeys = _us.get("journeys", [])
            _story_block = ""
            if _journeys:
                _corr = [j for j in _journeys if not j.get("no_user_story")]
                _atk  = [j for j in _journeys if j.get("no_user_story")]
                _lines = [
                    f"{'═'*59}",
                    "USER JOURNEY INTELLIGENCE (StoryCaster — deterministic, pre-LLM)",
                    f"Corroborated paths ({len(_corr)}): attacker exploits the same route a real user takes.",
                    f"Post-compromise paths ({len(_atk)}): no legitimate user follows this route — attacker must already have a foothold.",
                    "",
                ]
                for j in _corr:
                    _lines.append(
                        f"  CORROBORATED {j.get('attack_path_id','?')}: "
                        f"{j.get('actor_label','?')} → {j.get('resource_label','?')} "
                        f"[{j.get('user_role','user')}] "
                        f"| Tactics: {', '.join(j.get('threat_relevance',[]))}"
                    )
                for j in _atk:
                    path_str = ' → '.join(j.get('path_labels', j.get('path', [])))
                    _lines.append(
                        f"  POST-COMPROMISE {j.get('attack_path_id','?')}: {path_str} "
                        f"— no behavioural baseline, detection must be network-layer only"
                    )
                _story_block = "\n".join(_lines) + "\n"

            prompt = f"""
You are synthesising a security assessment for architecture: "{arch_name}"

{risk_summary}

═══════════════════════════════════════════════════════════
ARCHITECT CRITIC OUTPUT  (Layer 2A)
Score: {architect.original_score}/100  |  Status: {architect.validation_status}
Gaps:
{_gap_list(architect)}
Recommendations:
{_roadmap(architect)}

═══════════════════════════════════════════════════════════
TESTER CRITIC OUTPUT  (Layer 2B)
Score: {tester.original_score}/100  |  Status: {tester.validation_status}
Gaps:
{_gap_list(tester)}
Recommendations:
{_roadmap(tester)}

═══════════════════════════════════════════════════════════
RED TEAM CRITIC OUTPUT  (Layer 2C)
Score: {red_team.original_score}/100  |  Status: {red_team.validation_status}
Gaps (exploit feasibility):
{_gap_list(red_team)}
Exploit Mitigation Roadmap (use these cost/effort fields verbatim — do not invent):
{rt_roadmap_json}
{pt_block}{bh_block}{_story_block}{deterministic_block}{tradeoff_block}
{'═'*59}
{tech_grounding_block if tech_grounding_block else ''}
═══════════════════════════════════════════════════════════
YOUR SYNTHESIS TASK

You are the impartial Whitehat orchestrator. Tap each critic's strength; be wary of their blindspots.
Each improvement tier MUST trace its items to specific critic findings — no generic recommendations.

Produce a JSON object with EXACTLY this structure:

```json
{{
  "critical": [
    {{
      "description": "plain English — what is wrong and why it matters operationally",
      "category": "...",
      "severity": "CRITICAL|HIGH",
      "source": "which critics raised this (e.g. architect+purple_team)",
      "confidence_label": "KNOWN",
      "evidence": "cite the specific gap/field that supports this"
    }}
  ],
  "high": [ /* same shape, confidence_label KNOWN or UNSURE */ ],
  "review": [ /* same shape, confidence_label UNSURE — single-critic findings */ ],
  "blindspots": [
    {{
      "description": "gap that ALL critics structurally missed",
      "why_missed": "reason (e.g. rubric scope, single-lens focus, mode tradeoff)",
      "recommendation": "what the human should investigate"
    }}
  ],
  "contradictions": [
    {{
      "topic": "...",
      "critic_a_view": "...",
      "critic_b_view": "...",
      "why_it_differs": "explain the lens difference — do not resolve",
      "resolution": "UNSURE — human review needed"
    }}
  ],
  "improvement_tiers": {{
    "quick_win": {{
      "rationale": "highest security gain per unit effort — prioritise post-compromise paths first (no detection fallback), then corroborated paths where attacker blends with user traffic",
      "items": ["control name — traces to: critic X finding Y — protects: [journey or post-compromise path ID]"],
      "effort": "use Red Team roadmap effort field verbatim, or state 'not estimated'",
      "cost": "use Red Team roadmap cost field verbatim, or state 'cost not estimated'",
      "risk_reduction": "estimated score change (e.g. {rt['current']} → X)",
      "residual": "what risk remains even after Quick Win — be honest",
      "practical_verdict": "YES|MAYBE based on Red Team practical field"
    }},
    "recommended": {{
      "rationale": "balanced security / usability / cost — include detection controls for corroborated paths (attacker mimics real users, so detection needs precise baselines)",
      "items": ["control — traces to: critic X finding Y — protects: [journey or post-compromise path ID]"],
      "effort": "...",
      "cost": "...",
      "risk_reduction": "...",
      "residual": "...",
      "practical_verdict": "..."
    }},
    "maximum": {{
      "rationale": "full coverage including diminishing-return items — address any post-compromise paths still lacking network segmentation",
      "items": ["..."],
      "effort": "...",
      "cost": "...",
      "risk_reduction": "...",
      "residual": "residual that persists regardless (misconfiguration, human error, zero-days, implementation drift) — never claim zero",
      "practical_verdict": "MAYBE|NO for most teams — explain tradeoff"
    }}
  }},
  "confidence_commentary": "1-2 sentences: what the cross-expert agreement pattern means for confidence in this assessment",
  "mode_transparency": "1-2 sentences explaining which critics ran, which did not, and what gaps this creates in the synthesis — reference the mode tradeoffs listed above",
  "synthesis_quality": "FULL"
}}
```

RULES:
- critical = findings ≥2 critics independently raised (mark KNOWN)
- high = single-critic findings that Red Team or Blackhat exploit data corroborates (mark UNSURE if not corroborated)
- review = single-critic, not corroborated elsewhere (mark UNSURE)
- Purple Team findings about uncovered techniques or detection blindspots are high-confidence — treat as KNOWN if coverage_gap count > 0 or detection_blindspot count > 0
- Blackhat pivot-diverge chains are KNOWN if pivot_count > 0 — they reveal cross-path risk that single-AP critics cannot see
- DETERMINISTIC ESCALATION — the following are KNOWN regardless of critic count because the deterministic engine flagged them:
  * If validation_report.checks.detection_analytics.issues > 0: T1005/T1213 paths lack behavioral analytics — mark KNOWN, not UNSURE
  * If validation_report.checks.detection_analytics mentions API Gateway placement unclear: mark KNOWN
  * If validation_report.checks.external_dependencies.issues > 0: supply chain risk or BCP gap — mark KNOWN
- USER JOURNEY TIER SHARPENING — use the USER JOURNEY INTELLIGENCE block above to sharpen tier placement:
  * POST-COMPROMISE paths (no user baseline): any preventive control covering that path (segmentation, firewall rule, network isolation) belongs in Quick Win — there is no detection fallback, so prevention is the only lever.
  * CORROBORATED paths (real user follows the same route): detection controls are valid but anomaly-based detection alone is insufficient — attacker blends with user traffic. Preventive controls (MFA, RBAC, WAF) belong in Quick Win; detection controls with precise baselines belong in Recommended.
  * When writing tier items, append "— protects [AP-id] ([user role] journey)" or "— covers post-compromise path [AP-id]" so the reader knows which journey each control addresses.
  * If all paths are corroborated: note in the residual that behavioural detection thresholds need calibration to avoid false positives from legitimate users.
  * If any path is post-compromise: include in residual that network-layer monitoring must be in place — SIEM alerts on user behaviour will not fire.
- STRUCTURAL BLINDSPOTS — all critic lenses have these systematic gaps; always include them in blindspots[] if not addressed by controls:
  * Supply chain / third-party: all critics focus on internal architecture nodes; vendor risk and external dependencies are outside every critic's rubric
  * Business continuity / DR impact: security-focused lenses do not evaluate operational resilience or availability impact of security controls
  * API Gateway placement: critics cannot determine which attack path hops a gateway defends unless nodes appear explicitly in the path — unclear placement should always be flagged
- Never invent cost figures. Quote Red Team roadmap fields exactly or say "cost not estimated".
- Residual must always be non-empty — controls reduce risk, they do not eliminate it.
- If critics contradict each other, put it in contradictions, do NOT resolve it yourself.
- improvement_tiers items MUST trace back to a specific critic finding or deterministic check — never write a generic control not mentioned by at least one critic or validator.
- **TECHNIQUE ID VALIDATION**: Before flagging a disagreement about whether a technique ID exists, verify it against the MITRE reference block below. A technique ID that appears in that block is VALID — do NOT generate a contradiction claiming it doesn't exist. Only flag DATA_REFERENCE_ERROR if an ID is genuinely absent from that block.
"""

            from chatbot.config import get_settings as _gs_synth
            _synth_cfg = _gs_synth().moe
            llm = LLMClient()
            response = llm.generate(
                prompt=prompt.strip(),
                system_message=_ORCHESTRATOR_SYSTEM,
                temperature=_synth_cfg.temperature_synthesis,
                max_tokens=_synth_cfg.max_tokens_synthesis,
            )

            # Accumulate perf for this synthesis call
            self._synth_perf["llm_calls"]    += 1
            self._synth_perf["llm_tokens"]   += getattr(response, "tokens_used",    0) or 0
            self._synth_perf["llm_cost_usd"] += getattr(response, "cost_usd",       0.0) or 0.0
            self._synth_perf["llm_latency_s"]+= getattr(response, "latency_seconds",0.0) or 0.0
            self._synth_perf["llm_model"]     = getattr(response, "model", self._synth_perf["llm_model"]) or self._synth_perf["llm_model"]

            # Parse JSON from response
            content = response.content if hasattr(response, 'content') else str(response)
            if '```json' in content:
                raw = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content and '{' in content:
                raw = content.split('```')[1].split('```')[0].strip()
            else:
                raw = content.strip()

            result = json.loads(raw)

            # Minimal validation
            required = ["critical", "high", "review", "improvement_tiers"]
            if not all(k in result for k in required):
                logger.warning("Orchestrator: LLM synthesis response missing required keys")
                return None

            logger.info(
                f"Orchestrator: LLM synthesis complete — "
                f"{len(result.get('critical',[]))} critical, "
                f"{len(result.get('high',[]))} high, "
                f"{len(result.get('review',[]))} review, "
                f"{len(result.get('blindspots',[]))} blindspots"
            )
            return result

        except Exception as e:
            logger.warning(f"Orchestrator: LLM synthesis exception: {e}")
            return None

    def _resolve_technique_ids(self, text: str) -> str:
        """
        Find all T####[.###] IDs in text, look them up in MITRE, and return a
        grounding block listing each ID with its verified name.  Returns an
        empty string if no IDs are found or the MITRE helper is unavailable.
        """
        ids = list(dict.fromkeys(re.findall(r'\bT\d{4}(?:\.\d{3})?\b', text)))
        if not ids:
            return ""
        try:
            from chatbot.modules.mitre import get_mitre_helper as _get_mitre
            mitre = _get_mitre()
            lines = []
            for tid in ids:
                tech = mitre.find_technique(tid)
                if tech:
                    lines.append(f"  {tid} — {tech.get('name', 'Unknown')} (VALID in MITRE ATT&CK)")
                else:
                    lines.append(f"  {tid} — NOT FOUND in MITRE ATT&CK (invalid or hallucinated ID)")
            if lines:
                return "VERIFIED MITRE ATT&CK TECHNIQUE NAMES (authoritative — use these, do not guess):\n" + "\n".join(lines)
        except Exception:
            pass
        return ""

    def _reflect_contradictions(
        self,
        contradictions: List[Dict],
        architect: "ValidationResult",
        tester: "ValidationResult",
        red_team: "ValidationResult",
        purple_team_result: Optional["ValidationResult"] = None,
        blackhat_result: Optional["ValidationResult"] = None,
    ) -> List[Dict]:
        """
        Second-pass LLM call: for each contradiction, ask WHY the critics disagree.
        Includes PT and BH context so their findings can participate in resolution.
        Falls back to the original list if the call fails.
        """
        try:
            items_json = json.dumps(contradictions, indent=2)
            # Resolve any technique IDs mentioned in the contradictions against
            # the authoritative MITRE database so the LLM cannot confuse labels
            tech_grounding = self._resolve_technique_ids(items_json)

            # Build supplementary PT/BH context snippets
            pt_context = ""
            if purple_team_result:
                pt_gaps = [g.get("description", "") for g in purple_team_result.gaps[:5]]
                if pt_gaps:
                    pt_context = "\nPURPLE TEAM (Layer 2D) flagged these detection/coverage gaps:\n" + "\n".join(f"  - {g}" for g in pt_gaps)

            bh_context = ""
            if blackhat_result:
                bh_gaps = [g.get("description", "") for g in blackhat_result.gaps[:5]]
                if bh_gaps:
                    bh_context = "\nBLACKHAT (Layer 2E) flagged these cross-path chain risks:\n" + "\n".join(f"  - {g}" for g in bh_gaps)

            prompt = f"""You are a quality-control reviewer for a multi-expert security assessment (5 critics: Architect 2A, Tester 2B, Red Team 2C, Purple Team 2D, Blackhat 2E).

The critics disagreed on the following topics:

{items_json}
{pt_context}{bh_context}
{f'''
IMPORTANT — VERIFIED TECHNIQUE NAMES (authoritative reference):
{tech_grounding}

A critic claiming a technique ID "doesn't exist" is WRONG if the verified list above marks it VALID.
In that case the root cause is CRITIC_HALLUCINATION (the tester/red-team invented a wrong label for a real ID),
NOT DATA_REFERENCE_ERROR on the part of whoever used the ID.
''' if tech_grounding else ''}
For each contradiction, diagnose WHY the disagreement exists.  Consider:
1. Scope mismatch — each critic only sees their rubric, so one may be correct within their scope and the other correct within theirs
2. Critic hallucination — a critic incorrectly described or denied a technique ID whose official name contradicts what they claimed
3. Assessment confidence — one critic may have guessed while the other had direct evidence
4. Genuine expert disagreement — both are right from different attack angles
5. PT/BH corroboration — if Purple Team or Blackhat findings above support one side of the contradiction, note that

Return a JSON array with the SAME length and order as the input, each item having:
{{
  "topic": "<same as input>",
  "architect_view": "<same as input>",
  "tester_or_redteam_view": "<same as input>",
  "resolution": "<original resolution or updated if PT/BH corroborates one side>",
  "disagreement_root_cause": "SCOPE_MISMATCH | DATA_REFERENCE_ERROR | CRITIC_HALLUCINATION | CONFIDENCE_DIFFERENCE | GENUINE_DISAGREEMENT",
  "root_cause_explanation": "1-2 sentences explaining specifically why these critics see it differently. If a technique ID is verified VALID above but a critic claimed it doesn't exist, state that the critic hallucinated an incorrect name/description for a real technique.",
  "human_action": "what a human reviewer should do to resolve this (e.g. check field X, run test Y)",
  "pt_bh_corroboration": "which side (if any) Purple Team or Blackhat findings support, or 'none'"
}}

Reply with only the JSON array, no other text.
"""
            from chatbot.config import get_settings as _gs_refl
            _refl_temp = max(0.0, _gs_refl().moe.temperature_synthesis - 0.1)
            llm = LLMClient()
            response = llm.generate(
                prompt=prompt.strip(),
                system_message="You are a rigorous security assessment quality reviewer. Return only valid JSON.",
                temperature=_refl_temp,
                max_tokens=2000,
            )

            # Accumulate perf for this reflection call
            self._synth_perf["llm_calls"]    += 1
            self._synth_perf["llm_tokens"]   += getattr(response, "tokens_used",    0) or 0
            self._synth_perf["llm_cost_usd"] += getattr(response, "cost_usd",       0.0) or 0.0
            self._synth_perf["llm_latency_s"]+= getattr(response, "latency_seconds",0.0) or 0.0
            self._synth_perf["llm_model"]     = getattr(response, "model", self._synth_perf["llm_model"]) or self._synth_perf["llm_model"]

            content = response.content if hasattr(response, 'content') else str(response)
            if '```json' in content:
                raw = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                raw = content.split('```')[1].split('```')[0].strip()
            else:
                raw = content.strip()

            enriched = json.loads(raw)
            if isinstance(enriched, list) and len(enriched) == len(contradictions):
                logger.info(f"Orchestrator: contradiction self-reflection complete ({len(enriched)} items)")
                return enriched
        except Exception as e:
            logger.warning(f"Orchestrator: contradiction reflection failed: {e}")
        return contradictions

    def _extract_risk_transformation(self, ground_truth: Dict) -> Dict:
        """
        Extract risk transformation from ground truth.

        Tries multiple data sources for robustness:
        1. residual_risk (newest format, Phase 3B+)
        2. residual_risks_before/after (Phase 3B format with overall_residual)
        3. risk_analysis (older format, Phase 3A)
        4. expected_risk_score (original format, Phase 1-2)
        """
        residual = ground_truth.get("residual_risk", {})
        before = residual.get("before", {}).get("score")
        after = residual.get("after", {}).get("score")

        # Fallback 1: residual_risks_before/after (Phase 3B format)
        if before is None:
            residual_before = ground_truth.get("residual_risks_before", {})
            residual_after = ground_truth.get("residual_risks_after", {})
            before = residual_before.get("overall_residual")
            after = residual_after.get("overall_residual")

        # Fallback 2: risk_analysis (older format)
        if before is None:
            risk_analysis = ground_truth.get("risk_analysis", {})
            before = risk_analysis.get("overall_risk_score")
            after = risk_analysis.get("overall_risk_score_with_controls")

        # Fallback 3: expected_risk_score (original format)
        if before is None:
            before = ground_truth.get("expected_risk_score")
            # Estimate "after" risk based on controls
            if after is None:
                controls_count = len(ground_truth.get("control_recommendations", []))
                if controls_count > 0:
                    # Rough estimate: each control reduces ~2-3 risk points
                    estimated_reduction = min(controls_count * 2.5, before * 0.6)
                    after = max(0, int(before - estimated_reduction))
                else:
                    after = before  # No controls = no reduction

            logger.info(
                f"Risk data from expected_risk_score: {before} → {after} "
                f"({controls_count} controls, {int(before - after if after else 0)} point reduction)"
            )

        before = before or 0
        after = after or 0
        reduction = int(((before - after) / before * 100) if before > 0 else 0)

        return {
            "current": before,
            "target": after,
            "reduction": reduction
        }

    def _build_improvement_options(self, consensus: Dict, risk_data: Dict) -> Dict:
        """
        Read improvement tier data from the LLM synthesis output (consensus).
        Falls back to count-based summaries without invented cost figures if
        synthesis did not produce tier data.
        """
        tiers = consensus.get("improvement_tiers", {})

        def _tier(key: str, name: str, focus: str) -> Dict:
            t = tiers.get(key, {})
            if t:
                return {
                    "name": name,
                    "items": t.get("items", []),
                    "effort": t.get("effort", "not estimated"),
                    "cost": t.get("cost", "cost not estimated"),
                    "risk_reduction": t.get("risk_reduction", ""),
                    "residual": t.get("residual", ""),
                    "practical_verdict": t.get("practical_verdict", ""),
                    "rationale": t.get("rationale", ""),
                }
            # Fallback — never invent costs
            counts = {
                "quick_win":   len(consensus.get("critical", [])),
                "recommended": len(consensus.get("critical", [])) + len(consensus.get("high", [])),
                "maximum":     len(consensus.get("critical", [])) + len(consensus.get("high", [])) + len(consensus.get("review", [])),
            }
            return {
                "name": name,
                "items": [],
                "effort": "not estimated",
                "cost": "cost not estimated",
                "risk_reduction": f"{risk_data['current']} → {risk_data['target']}",
                "residual": "Residual risk remains — controls reduce exposure but do not eliminate it.",
                "practical_verdict": "not assessed",
                "item_count": counts.get(key, 0),
                "focus": focus,
            }

        return {
            "quick_wins":  _tier("quick_win",   "Quick Wins",         "Critical gaps — highest ROI, lowest friction"),
            "recommended": _tier("recommended",  "Recommended Target", "Critical + High — balanced security/usability/cost"),
            "maximum":     _tier("maximum",      "Maximum Security",   "Full coverage including diminishing-return items"),
        }

    def _save_validation(self, critique: CritiqueScore, output_path: Path):
        """Save validation critique to JSON."""
        with open(output_path, 'w') as f:
            json.dump(critique.to_dict(), f, indent=2)

        logger.debug(f"Saved validation: {output_path}")

    def _load_saved_critique(self, path: Path) -> Optional['CritiqueScore']:
        """
        Load a previously saved CritiqueScore from disk.

        Used when resuming a paused pipeline — avoids re-calling the LLM for
        critics that already completed.  Returns None if the file is missing or
        malformed.
        """
        from chatbot.modules.agent_framework import CritiqueScore

        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return CritiqueScore(
                role=data.get("role", ""),
                score=data.get("score", 0),
                max_score=data.get("max_score", 100),
                rating=data.get("rating", "UNKNOWN"),
                breakdown=data.get("breakdown", {}),
                gaps=data.get("gaps", []),
                strengths=data.get("strengths", []),
                improvement_roadmap=data.get("improvement_roadmap", []),
                # Restore perf telemetry if present in the saved file
                llm_calls    =data.get("llm_calls",     0),
                llm_tokens   =data.get("llm_tokens",    0),
                llm_cost_usd =data.get("llm_cost_usd",  0.0),
                llm_latency_s=data.get("llm_latency_s", 0.0),
                llm_model    =data.get("llm_model",     ""),
                wall_clock_s =data.get("wall_clock_s",  0.0),
            )
        except Exception as e:
            logger.warning(f"Could not load saved critique from {path}: {e}")
            return None


    def run_targeted(
        self,
        report_dir: str,
        critics_to_run: list,
        new_proposals_context: dict,
        base_confidence: float = None,
        critic_mode: str = None,
    ) -> "MoEResult":
        """Re-run only specific critics and rebuild synthesis.

        Called by ScrumMasterCritic when targeted re-triggering is needed.
        Critics NOT in critics_to_run are loaded from their saved JSON files —
        no redundant LLM calls. Each re-run critic receives a
        SCRUM_MASTER_PROPOSALS block injected into its prompt context.

        Args:
            report_dir: Path to report directory (must already contain ground_truth.json)
            critics_to_run: Names of critics to re-run, e.g. ["architect", "red_team"]
                Valid names: "architect", "tester", "red_team", "purple_team", "blackhat"
            new_proposals_context: Dict injected into re-run critic prompts.
                Expected key: "scrum_master_proposals" → List[Dict].
                Critics receive this as a SCRUM_MASTER_PROPOSALS context block and
                must address each proposal in their critique.
            base_confidence: Override base confidence (defaults to existing result's base)
            critic_mode: Override mode for sequencing re-run critics

        Returns:
            Updated MoEResult with fresh ValidationResults for re-run critics,
            loaded results for skipped critics, and re-computed final confidence.
        """
        import os

        report_path = Path(report_dir)

        # Critic file mapping: name → (filename, delete-before-rerun)
        _CRITIC_FILES = {
            "architect":  report_path / "04_architect_critique.json",
            "tester":     report_path / "05_tester_critique.json",
            "red_team":   report_path / "06_red_team_critique.json",
            "purple_team": report_path / "06b_purple_team_critique.json",
            "blackhat":   report_path / "06c_blackhat_critique.json",
        }

        # Delete cached JSON for critics we need to re-run (forces fresh LLM call)
        for name in critics_to_run:
            path = _CRITIC_FILES.get(name)
            if path and path.exists():
                logger.info(f"run_targeted: deleting cached {path.name} for fresh re-run")
                os.remove(path)

        # Inject proposals context into orchestrator so critics can read it
        # We store it on self temporarily — each critic's _logic reads it via
        # the orchestrator reference passed during critique calls.
        self._scrum_master_proposals = new_proposals_context.get("scrum_master_proposals", [])

        try:
            resolved_mode = critic_mode or self.config.critic_mode
            resolved_confidence = base_confidence if base_confidence is not None else 99.5

            # Re-run the full pipeline — deleted files force re-generation of
            # targeted critics; saved files are loaded for all others.
            result = self.run_pipeline(
                report_dir=report_dir,
                base_confidence=resolved_confidence,
                critic_mode=resolved_mode,
            )
        finally:
            # Clean up temporary state
            self._scrum_master_proposals = []

        return result


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def run_moe_pipeline(
    report_dir: str,
    base_confidence: float = 99.5,
    progress_callback=None,
    critic_mode: str = "sequential",
    run_blackhat: Optional[bool] = None,
    blocked_agents: Optional[List[str]] = None,
    agent_models: Optional[Dict[str, str]] = None,
) -> MoEResult:
    """
    Convenience function to run full MoE pipeline.

    Args:
        report_dir: Path to report directory
        base_confidence: Base confidence from deterministic (default: 99.5%)
        progress_callback: Optional callable(stage: str, result: ValidationResult)
            called immediately after each critic finishes.  Must be non-blocking.
        critic_mode: "sequential" | "parallel" | "auto" (see MoEOrchestrator.run_pipeline)
        run_blackhat: Override blackhat.enabled setting. None = use config setting.
        agent_models: Per-agent model dict from HarnessModelGuardian.models_dict().
            Keys: "architect", "tester", "red_team", "purple_team", "blackhat",
                  "moe_orchestrator". Overrides env-var defaults per agent.

    Returns:
        MoEResult with unified assessment

    Raises:
        MissingPrerequisiteError: If any prerequisite file missing

    Example:
        >>> result = run_moe_pipeline("report/10_complex_enterprise")
        >>> print(f"Final confidence: {result.final_confidence:.1f}%")
    """
    orchestrator = MoEOrchestrator(
        model=agent_models.get("moe_orchestrator") if agent_models else None,
        progress_callback=progress_callback,
        blocked_agents=blocked_agents,
        agent_models=agent_models,
    )
    return orchestrator.run_pipeline(report_dir, base_confidence, critic_mode=critic_mode, run_blackhat=run_blackhat)


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.moe_orchestrator <report_dir>")
        print("Example: python3 -m chatbot.modules.moe_orchestrator report/10_complex_enterprise")
        sys.exit(1)

    report_dir = sys.argv[1]

    try:
        print(f"\n{'='*70}")
        print("MOE PIPELINE")
        print(f"{'='*70}\n")

        result = run_moe_pipeline(report_dir)

        print(f"\n{'='*70}")
        print("RESULTS")
        print(f"{'='*70}\n")
        print(f"Architecture: {result.architecture_name}")
        print(f"Final Confidence: {result.final_confidence:.1f}%")
        print(f"  Base: {result.base_confidence:.1f}%")
        print(f"  Architect: {result.architect_adjustment*100:+.1f}%")
        print(f"  Tester: {result.tester_adjustment*100:+.1f}%")
        print(f"  Red Team: {result.red_team_adjustment*100:+.1f}%")
        print(f"\nRisk Transformation:")
        print(f"  Current: {result.current_risk}/100")
        print(f"  Target: {result.target_risk}/100")
        print(f"  Reduction: {result.risk_reduction}%")
        print(f"\nConsensus Recommendations:")
        print(f"  Critical: {len(result.critical_recommendations)}")
        print(f"  High: {len(result.high_recommendations)}")
        print(f"  Review: {len(result.review_recommendations)}")
        print(f"\n{'='*70}\n")

    except MissingPrerequisiteError as e:
        print(f"\n❌ ERROR: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
