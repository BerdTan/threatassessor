"""
taco_agent.py — TACO companion agent + TACOmini sub-agent registry.

Architecture:
  TACOmini     — single-responsibility hop executor; each subclass handles one task.
                 Carries an optional `model` field so each mini can be routed to a
                 cheaper/faster model independently (e.g. haiku for brain lookups,
                 sonnet for harness, opus for critics).
  TACOContext  — typed input passed to every mini's run() call.
  TACOAgent    — master router/assembler; holds a mini registry, decides routing,
                 assembles HopChain from mini results.

Adding a new hop type = write one TACOmini subclass, inject it into TACOAgent.minis.

Pydantic models (HopRecord, HopChain, TACOContext) are wire-safe:
  HopChain.model_validate(data)   — deserialise over the wire
  HopChain.model_json_schema()    — publish stable schema for external consumers
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]


def _brain_dir() -> Path:
    """Mirror of ta_brain_query._brain_dir() — resolved fresh at call time."""
    try:
        from chatbot.config import get_settings  # noqa: PLC0415
        rd = get_settings().system.report_dir
        base = Path(rd) if Path(rd).is_absolute() else ROOT / rd
    except Exception:
        base = ROOT / "report"
    return base / "brain"


def _workspace_report_dir() -> Path:
    """Return the report directory root for Workspace graph search."""
    try:
        from chatbot.config import get_settings  # noqa: PLC0415
        rd = get_settings().system.report_dir
        return Path(rd) if Path(rd).is_absolute() else ROOT / rd
    except Exception:
        return ROOT / "report"


# ---------------------------------------------------------------------------
# Wire-safe data model
# ---------------------------------------------------------------------------

class HopRecord(BaseModel):
    """One system boundary crossed during a TACO routing chain."""
    hop_id: str = Field(description="UUID4 identifier for this hop")
    hop_type: str = Field(description="'brain' | 'harness' | 'critic'")
    component: str = Field(description="'TABrain' | 'TAHarness' | 'TACritic'")
    query_summary: str = Field(description="First 120 chars of query or arch_name")
    response_summary: str = Field(description="Human-readable one-liner result")
    confidence: Optional[float] = Field(None, description="Confidence score 0–1; None if unavailable")
    duration_ms: int = Field(description="Wall time for this hop in milliseconds")
    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="JSON-native payload")
    routed: bool = Field(False, description="True = triggered by a routing decision")
    model_used: Optional[str] = Field(None, description="Model that served this hop, if applicable")


class HopChain(BaseModel):
    """Full routing trace for one TACO query. Portable via model_validate() / model_json_schema()."""
    chain_id: str = Field(description="UUID4 chain identifier")
    query: str = Field(description="Original user query")
    arch_name: Optional[str] = Field(None, description="Corpus arch_id if provided")
    hops: List[HopRecord] = Field(default_factory=list, description="Ordered hop records")
    final_confidence: float = Field(description="Confidence of the last hop")
    final_response: Dict[str, Any] = Field(default_factory=dict, description="Metadata of last hop")
    total_duration_ms: int = Field(description="Sum of all hop durations (not wall-clock)")
    routed_to_harness: bool = Field(False, description="True if TAHarness was invoked")
    routed_to_rag: bool = Field(False, description="True if TACOminiRAG was invoked")
    routed_to_critics: bool = Field(False, description="True if TACritic was invoked (Phase 4)")
    created_at: str = Field(description="ISO 8601 UTC timestamp of chain creation")


class TACOContext(BaseModel):
    """Typed input passed to every TACOmini.run() call."""
    query: str = Field("", description="Natural-language threat question")
    arch_name: Optional[str] = Field(None, description="Known corpus arch_id")
    arch_mmd: Optional[str] = Field(None, description="Raw Mermaid diagram content")


# ---------------------------------------------------------------------------
# TACOmini — single-responsibility sub-agent base
# ---------------------------------------------------------------------------

class TACOmini:
    """Base class for TACO sub-agents. Each subclass handles exactly one hop type.

    Subclass contract:
      - Set `hop_type`, `component`, and `is_deterministic` as class attributes.
      - Implement `run(context: TACOContext) -> HopRecord`.
      - Never raise — errors should be returned as a HopRecord with confidence=0.0.

    `is_deterministic = True`  → no LLM calls; model field is reserved but inert.
    `is_deterministic = False` → makes LLM calls; model field controls which model is used:
      TACOminiBrain(model="haiku")      # cheap + fast for KG lookups (currently deterministic)
      TACOminiHarness(model="sonnet")   # balanced for pipeline runs (currently deterministic)
      TACOminiCritic(model="opus")      # capable for expert review — Phase 3, LLM-active
    """

    hop_type: str = ""
    component: str = ""
    is_deterministic: bool = True   # False = makes LLM calls; model field is active

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model  # None = use default env-var routing; only matters when is_deterministic=False

    def run(self, context: TACOContext) -> HopRecord:
        raise NotImplementedError(f"{self.__class__.__name__}.run() not implemented")

    def _base_hop(self, context: TACOContext, **kwargs) -> HopRecord:
        """Convenience builder for subclasses — sets shared fields."""
        return HopRecord(
            hop_id=str(uuid.uuid4()),
            hop_type=self.hop_type,
            component=self.component,
            model_used=self.model,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# TACOminiBrain — queries TABrain KG (deterministic, no LLM, <50 ms)
# ---------------------------------------------------------------------------

class TACOminiBrain(TACOmini):
    """Query the TABrain knowledge graph. Fast, deterministic, zero LLM cost."""

    hop_type = "brain"
    component = "TABrain"

    def run(self, context: TACOContext) -> HopRecord:
        from chatbot.modules.ta_brain_query import query_brain  # noqa: PLC0415

        t0 = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()

        result = query_brain(
            mode="infer",
            arch_name=context.arch_name or "",
            caller_type="taco_agent",
        )

        duration_ms = int((time.monotonic() - t0) * 1000)

        if "error" in result:
            return self._base_hop(
                context,
                query_summary=(context.query or "")[:120],
                response_summary=f"brain error: {str(result['error'])[:80]}",
                confidence=0.0,
                duration_ms=duration_ms,
                timestamp=ts,
                metadata={"had_match": False, "error": str(result["error"])},
            )

        # Clean no-match (arch not in brain, not an error)
        if result.get("reason") == "arch_not_in_brain":
            return self._base_hop(
                context,
                query_summary=(context.query or "")[:120],
                response_summary="not in brain yet — run /brain-ingest to add this arch",
                confidence=0.0,
                duration_ms=duration_ms,
                timestamp=ts,
                metadata={
                    "had_match": False,
                    "patterns_fired": [],
                    "arch_type": "",
                    "cache_route": "miss",
                    "predictions": {
                        "techniques": [],
                        "detect_rules": [],
                        "aivss_floor": 0.0,
                        "aivss_mean": 0.0,
                        "missing_controls": [],
                    },
                    "reason": "arch_not_in_brain",
                },
            )

        had_match = bool(result.get("had_match", False))
        confidence = float(result.get("confidence") or 0.0)
        patterns_fired = result.get("patterns_fired") or []

        response_summary = (
            f"conf={confidence:.2f}, {len(patterns_fired)} pattern(s)"
            if had_match else "no match in brain"
        )

        predictions = result.get("predictions") or {}
        metadata: dict = {
            "had_match": had_match,
            "patterns_fired": list(patterns_fired),
            "arch_type": str(result.get("arch_type") or ""),
            "cache_route": str(result.get("cache_route") or ""),
            "predictions": {
                "techniques": list(predictions.get("techniques") or [])[:10],
                "detect_rules": list(predictions.get("detect_rules") or []),
                "aivss_floor": float(predictions.get("aivss_floor") or 0.0),
                "aivss_mean": float(predictions.get("aivss_mean") or 0.0),
                "missing_controls": list(predictions.get("common_missing_controls") or [])[:5],
            },
        }

        return self._base_hop(
            context,
            query_summary=(context.query or "")[:120],
            response_summary=response_summary,
            confidence=confidence,
            duration_ms=duration_ms,
            timestamp=ts,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# TACOminiHarness — runs TAHarness pipeline (API_ONLY, ~30 s)
# ---------------------------------------------------------------------------

class TACOminiHarness(TACOmini):
    """Run the TAHarness analysis pipeline. Writes MMD to tempfile; cleans up on exit."""

    hop_type = "harness"
    component = "TAHarness"

    def __init__(self, model: Optional[str] = None, harness=None) -> None:
        super().__init__(model=model)
        self._harness = harness  # injectable for testing

    def run(self, context: TACOContext) -> HopRecord:
        from chatbot.harness.controller import (  # noqa: PLC0415
            ThreatAssessorHarness,
            PipelineRequest,
        )

        arch_name = context.arch_name or "taco_input"
        mmd = context.arch_mmd or ""

        t0 = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        tmp_mmd_path: Optional[str] = None
        tmp_dir: Optional[str] = None

        try:
            tmp_fd, tmp_mmd_path = tempfile.mkstemp(suffix=".mmd")
            with os.fdopen(tmp_fd, "w") as fh:
                fh.write(mmd)

            tmp_dir = tempfile.mkdtemp(prefix="taco_harness_")

            request = PipelineRequest(
                architecture_path=tmp_mmd_path,
                report_dir=tmp_dir,
                architecture_name=arch_name,
                use_llm=False,
                enable_moe=False,
                enable_scrum_master=False,
            )

            harness = self._harness or ThreatAssessorHarness(scenario="api_only")
            response = harness.run_typed(request)

            duration_ms = int((time.monotonic() - t0) * 1000)

            gov = response.governance_summary or {}
            det = response.detect_summary or {}
            metadata: dict = {
                "success": bool(response.success),
                "run_id": str(response.run_id or ""),
                "confidence": float(response.confidence or 0.0),
                "governance_summary": {
                    "aivss_overall": float(gov.get("aivss_overall") or 0.0),
                    "aivss_severity": str(gov.get("aivss_severity") or ""),
                    "overall_risk_level": str(gov.get("overall_risk_level") or ""),
                },
                "detect_summary": {
                    "rules_fired": list(det.get("rules_fired") or []),
                    "total_fired": int(det.get("total_fired") or 0),
                },
                "errors": [str(e) for e in (response.errors or [])],
            }

            aivss = gov.get("aivss_overall", 0.0)
            if response.success:
                response_summary = (
                    f"API_ONLY ok · AIVSS {aivss:.2f} · "
                    f"{det.get('total_fired', 0)} rules fired"
                )
            else:
                errs = "; ".join(str(e) for e in (response.errors or [])[:2])
                response_summary = f"harness error: {errs[:80]}"

            return self._base_hop(
                context,
                query_summary=arch_name[:120],
                response_summary=response_summary,
                confidence=float(response.confidence or 0.0),
                duration_ms=duration_ms,
                timestamp=ts,
                metadata=metadata,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.exception("TACOminiHarness failed for arch=%s", arch_name)
            return self._base_hop(
                context,
                query_summary=arch_name[:120],
                response_summary=f"exception: {str(exc)[:80]}",
                confidence=0.0,
                duration_ms=duration_ms,
                timestamp=ts,
                metadata={"success": False, "error": str(exc)},
            )

        finally:
            if tmp_mmd_path and os.path.exists(tmp_mmd_path):
                try:
                    os.unlink(tmp_mmd_path)
                except OSError:
                    pass
            if tmp_dir and os.path.exists(tmp_dir):
                import shutil
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# TACOminiRAG — deterministic Workspace graph search (Phase 3)
# ---------------------------------------------------------------------------

class TACOminiRAG(TACOmini):
    """Deterministic Workspace graph search using ThreatGraph.

    Builds the ThreatGraph lazily on first call and caches it per arch_name.
    Returns confidence=0.80 on a graph hit, 0.50 on a miss.
    Metadata includes extracted techniques and missing controls for downstream
    benchmark scoring without a second graph traversal.
    """

    hop_type = "rag"
    component = "TAWorkspace"
    is_deterministic = True

    def __init__(
        self,
        model: Optional[str] = None,
        report_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(model=model)
        self._report_dir = report_dir       # injectable; None → resolved at run time
        self._graph: Optional[Any] = None   # ThreatGraph, lazy-built and cached
        self._graph_arch: Optional[str] = None

    def _get_graph(self, arch_name: str) -> Optional[Any]:
        """Return a ThreatGraph for arch_name; build and cache if needed."""
        if self._graph is not None and self._graph_arch == arch_name:
            return self._graph
        report_dir = self._report_dir or _workspace_report_dir()
        arch_dir = report_dir / arch_name
        if not arch_dir.is_dir() or not (arch_dir / "ground_truth.json").exists():
            return None
        from chatbot.modules.graph_index import ThreatGraph  # noqa: PLC0415
        self._graph = ThreatGraph.build([arch_name], report_dir)
        self._graph_arch = arch_name
        return self._graph

    def run(self, context: TACOContext) -> HopRecord:
        t0 = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        arch_name = context.arch_name or ""

        try:
            g = self._get_graph(arch_name) if arch_name else None

            if g is None:
                return self._base_hop(
                    context,
                    query_summary=(context.query or "")[:120],
                    response_summary="no workspace graph available",
                    confidence=0.50,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    timestamp=ts,
                    metadata={
                        "had_hit": False,
                        "arch_name": arch_name,
                        "techniques": [],
                        "missing_controls": [],
                    },
                )

            answer = g.query(context.query)
            had_hit = answer is not None

            techniques = sorted({
                t
                for ap in g.attack_paths.values()
                if ap.arch == arch_name
                for t in ap.techniques
            })
            missing_controls = sorted(g.arch_controls_missing.get(arch_name, []))

            confidence = 0.80 if had_hit else 0.50
            response_summary = (
                f"graph hit · {len(answer)} chars" if had_hit
                else "no structural match"
            )

            return self._base_hop(
                context,
                query_summary=(context.query or "")[:120],
                response_summary=response_summary,
                confidence=confidence,
                duration_ms=int((time.monotonic() - t0) * 1000),
                timestamp=ts,
                metadata={
                    "had_hit": had_hit,
                    "answer": answer or "",
                    "arch_name": arch_name,
                    "techniques": techniques[:20],
                    "missing_controls": missing_controls[:20],
                },
            )

        except Exception as exc:
            logger.exception("TACOminiRAG failed for arch=%s", arch_name)
            return self._base_hop(
                context,
                query_summary=(context.query or "")[:120],
                response_summary=f"error: {str(exc)[:80]}",
                confidence=0.0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                timestamp=ts,
                metadata={"had_hit": False, "arch_name": arch_name, "error": str(exc)},
            )


# ---------------------------------------------------------------------------
# TACOminiCritic — reads existing MoE results (Phase 4)
# ---------------------------------------------------------------------------

class TACOminiCritic(TACOmini):
    """Read existing MoE expert review results for an architecture.

    Gate design: this mini is NEVER invoked automatically by the confidence
    threshold.  It only runs when the caller explicitly sets force_critic=True
    in TACOAgent.run() — which requires the human to set that flag in the
    API request.  A second gate (critic_enabled in settings.yaml) controls
    whether the mini is even registered.

    Fast path (default): reads 07_moe_orchestrator.json from report/{arch}/
    and extracts consensus confidence + key signals.  No LLM calls, <5 ms.

    Slow path (future): if no MoE file exists and fresh_review=True, triggers
    an async jobs/expert-review run.  Not implemented in Phase 4 initial drop.
    """

    hop_type = "critic"
    component = "TACritic"
    is_deterministic = False  # LLM-backed in principle; fast path reads JSON

    _MOE_FILE = "07_moe_orchestrator.json"

    def __init__(
        self,
        model: Optional[str] = None,
        report_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(model=model)
        self._report_dir = report_dir  # injectable for testing

    def _get_report_dir(self) -> Path:
        if self._report_dir is not None:
            return self._report_dir
        try:
            from chatbot.config import get_settings  # noqa: PLC0415
            rd = get_settings().system.report_dir
            return Path(rd) if Path(rd).is_absolute() else ROOT / rd
        except Exception:
            return ROOT / "report"

    def run(self, context: TACOContext) -> HopRecord:
        t0 = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        arch_name = context.arch_name or ""

        if not arch_name:
            return self._base_hop(
                context,
                query_summary=(context.query or "")[:120],
                response_summary="no arch_name — critic requires a known architecture",
                confidence=0.0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                timestamp=ts,
                metadata={"had_moe": False, "reason": "no_arch_name"},
            )

        moe_path = self._get_report_dir() / arch_name / self._MOE_FILE
        if not moe_path.exists():
            return self._base_hop(
                context,
                query_summary=arch_name[:120],
                response_summary="no MoE data — run expert review first",
                confidence=0.0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                timestamp=ts,
                metadata={"had_moe": False, "reason": "no_moe_file", "arch_name": arch_name},
            )

        try:
            import json  # noqa: PLC0415
            raw = json.loads(moe_path.read_text())
        except Exception as exc:
            return self._base_hop(
                context,
                query_summary=arch_name[:120],
                response_summary=f"MoE parse error: {str(exc)[:60]}",
                confidence=0.0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                timestamp=ts,
                metadata={"had_moe": False, "reason": "parse_error", "arch_name": arch_name},
            )

        # Extract consensus confidence (0–100 scale → 0–1)
        conf_block = raw.get("confidence") or {}
        final_conf_raw = conf_block.get("final")
        moe_confidence = float(final_conf_raw) / 100.0 if isinstance(final_conf_raw, (int, float)) else 0.0
        moe_confidence = min(max(moe_confidence, 0.0), 1.0)

        # Scrum master signals
        sm = raw.get("scrum_master") or {}
        sm_confidence = sm.get("final_confidence")
        redesign_signal = bool(sm.get("redesign_signal", False))

        # Per-critic adjustments
        evs = raw.get("expert_validations") or {}
        critic_verdicts: Dict[str, str] = {
            name: str(ev.get("validation_status") or "")
            for name, ev in evs.items()
        }

        interpretation = str(conf_block.get("interpretation") or "")
        response_summary = (
            f"MoE conf={moe_confidence:.2f} · "
            f"{'REDESIGN' if redesign_signal else 'OK'} · "
            f"{len(evs)} critic(s)"
        )

        return self._base_hop(
            context,
            query_summary=arch_name[:120],
            response_summary=response_summary,
            confidence=moe_confidence,
            duration_ms=int((time.monotonic() - t0) * 1000),
            timestamp=ts,
            metadata={
                "had_moe": True,
                "arch_name": arch_name,
                "moe_confidence": moe_confidence,
                "sm_confidence": float(sm_confidence) if isinstance(sm_confidence, (int, float)) else None,
                "redesign_signal": redesign_signal,
                "interpretation": interpretation,
                "critic_verdicts": critic_verdicts,
                "critics_count": len(evs),
            },
        )


# ---------------------------------------------------------------------------
# TACOAgent — master router + assembler
# ---------------------------------------------------------------------------

class TACOAgent:
    """Master TACO agent. Holds a registry of TACOmini sub-agents, decides routing,
    assembles HopChain from mini results.

    Inject custom minis to swap models or behaviours without subclassing:
        agent = TACOAgent(minis={
            "brain":   TACOminiBrain(model="haiku"),
            "harness": TACOminiHarness(model="sonnet"),
        })
    """

    def __init__(
        self,
        brain_path: Optional[Path] = None,
        threshold: Optional[float] = None,
        minis: Optional[Dict[str, TACOmini]] = None,
    ) -> None:
        self.brain_path = brain_path or (_brain_dir() / "ta_brain.json")

        # Read threshold and mini_models from settings; explicit args override.
        cfg_threshold = 0.65
        cfg_mini_models: Dict[str, str] = {}
        try:
            from chatbot.config import get_settings  # noqa: PLC0415
            taco_cfg = get_settings().taco
            cfg_threshold = taco_cfg.confidence_threshold
            # Filter out unresolved ${VAR} placeholders — treat them as "no override"
            cfg_mini_models = {
                k: v for k, v in (taco_cfg.mini_models or {}).items()
                if v and not v.startswith("${")
            }
        except Exception:
            pass

        self.threshold = threshold if threshold is not None else cfg_threshold

        cfg_rag_enabled = True
        cfg_critic_enabled = False
        try:
            from chatbot.config import get_settings  # noqa: PLC0415
            taco_cfg2 = get_settings().taco
            cfg_rag_enabled = getattr(taco_cfg2, "rag_enabled", True)
            cfg_critic_enabled = getattr(taco_cfg2, "critic_enabled", False)
        except Exception:
            pass

        if minis is not None:
            self.minis = minis
        else:
            self.minis: Dict[str, TACOmini] = {
                "brain":   TACOminiBrain(model=cfg_mini_models.get("brain")),
                "harness": TACOminiHarness(model=cfg_mini_models.get("harness")),
            }
            if cfg_rag_enabled:
                self.minis["rag"] = TACOminiRAG(model=cfg_mini_models.get("rag"))
            if cfg_critic_enabled:
                self.minis["critic"] = TACOminiCritic(model=cfg_mini_models.get("critic"))

    # ── public surface ──────────────────────────────────────────────────────

    def run(
        self,
        query: str,
        arch_name: Optional[str] = None,
        arch_mmd: Optional[str] = None,
        force_critic: bool = False,
    ) -> HopChain:
        """Execute the routing chain and return a complete HopChain.

        Args:
            force_critic: When True and "critic" mini is registered, append a
                          TACOminiCritic hop after all other hops.  This is the
                          human-trigger gate — the critic never runs automatically.
        """
        ctx = TACOContext(query=query, arch_name=arch_name, arch_mmd=arch_mmd)
        hops: list[HopRecord] = []

        # Hop 1: Brain (always)
        brain_hop = self._run_mini("brain", ctx)
        hops.append(brain_hop)

        # Hop 2: RAG (if registered)
        rag_hop: Optional[HopRecord] = None
        ran_rag = "rag" in self.minis
        if ran_rag:
            rag_hop = self._run_mini("rag", ctx)
            rag_hop.routed = True
            hops.append(rag_hop)

        # Escalation: use best confidence from brain and RAG
        brain_conf = brain_hop.confidence or 0.0
        rag_conf = (rag_hop.confidence or 0.0) if rag_hop is not None else 0.0
        best_conf = max(brain_conf, rag_conf)

        should_escalate = best_conf < self.threshold and ctx.arch_mmd is not None
        if should_escalate:
            harness_hop = self._run_mini("harness", ctx)
            harness_hop.routed = True
            hops.append(harness_hop)

        # Critic hop — human-triggered only; never part of automatic routing
        ran_critic = False
        if force_critic and "critic" in self.minis:
            critic_hop = self._run_mini("critic", ctx)
            critic_hop.routed = True
            hops.append(critic_hop)
            ran_critic = True

        return HopChain(
            chain_id=str(uuid.uuid4()),
            query=query,
            arch_name=arch_name,
            hops=hops,
            final_confidence=hops[-1].confidence or 0.0,
            final_response=hops[-1].metadata,
            total_duration_ms=sum(h.duration_ms for h in hops),
            routed_to_harness=should_escalate,
            routed_to_rag=ran_rag,
            routed_to_critics=ran_critic,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _run_mini(self, name: str, context: TACOContext) -> HopRecord:
        """Dispatch to a named mini. Raises KeyError if the mini is not registered."""
        return self.minis[name].run(context)

    def to_dict(self, chain: HopChain) -> dict:
        """Return a JSON-serializable dict of the HopChain."""
        return chain.model_dump()
