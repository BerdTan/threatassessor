"""
TMAgent — model-swappable threat model generation agent.

Produces threatmodel/0.1 conformant JSON from any architecture input
(Mermaid diagram, Terraform, prose description).

Usage:
    from chatbot.agents.tmagent import TMAgent, TMResult

    agent = TMAgent(model="hetzner")
    result = agent.run(arch_input=mmd_text, arch_id="my_arch")
    if result.tm:
        print(f"Score: {result.score}/13")

Model options:
  "hetzner"      — Qwen3-235B-A22B via Hetzner (default; set HETZNER_API_KEY)
  "claude"       — claude-sonnet-4-6 via Anthropic (set ANTHROPIC_API_KEY)
  "gpt4o"        — gpt-4o via OpenAI (set OPENAI_API_KEY)
  "ta_full_moe"  — TA's full harness → convert ta-export/1.0 → threatmodel/0.1
                   (requires TA API running at TA_API_URL, default http://localhost:8000)
  any other str  — treated as a literal OpenRouter model id (set OPENROUTER_API_KEY)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_SPEC_PATH = _ROOT / "docs" / "tmbench" / "threatmodel.md"
_SCORER_PATH = _ROOT / ".claude" / "skills" / "tmbench-check" / "scripts" / "tmbench-check.py"

SPEC_VERSION = "threatmodel/0.1"

# Canonical model configs — extend as new providers are onboarded.
MODEL_CONFIGS: dict[str, dict] = {
    "hetzner": {
        "provider": "hetzner",
        "model": "Qwen/Qwen3-235B-A22B",
        "env_key": "HETZNER_API_KEY",
        "extra_body": {"enable_thinking": False},
    },
    "claude": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "gpt4o": {
        "provider": "openai",
        "model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
    },
    "ta_full_moe": {
        "provider": "ta_api",
        "model": "ta-pipeline-v3",
        "env_key": None,
    },
}

_SYSTEM_PROMPT = """\
You are a security architect producing a structured threat model.
You will be given an architecture description and the threatmodel/0.1 spec.
Produce a complete, valid threat model JSON that satisfies every requirement in the spec.

Rules:
- Output ONLY valid JSON — no markdown fences, no commentary, no preamble
- Follow the output schema in §4 exactly
- Use real MITRE ATT&CK technique IDs (verify tactic phase matches)
- For AI/ML components include MITRE ATLAS techniques
- Every threat actor must have a non-empty non_capabilities list
- Every attack path must have a mitigation and a finding
- High and Critical findings require a CVSS 3.1 vector
- The produced_by field must be: {produced_by}"""

_USER_PROMPT = """\
Spec:
---
{spec_excerpt}
---

Architecture ID: {arch_id}
{input_label}:
```
{arch_input}
```

Produce the complete threat model JSON for this architecture.
Set architecture_id to "{arch_id}" and produced_by to "{produced_by}"."""


@dataclass
class TMResult:
    arch_id: str
    model: str
    tm: Optional[dict] = None
    score: Optional[int] = None
    tatb: Optional[dict] = None
    error: Optional[str] = None
    produced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return self.score is not None and self.score >= 8

    def to_json(self) -> str:
        return json.dumps(self.tm, indent=2) if self.tm else ""


class TMAgent:
    """
    Generate a threatmodel/0.1 conformant JSON from any architecture input.

    Parameters
    ----------
    model : str
        One of the keys in MODEL_CONFIGS, or a literal OpenRouter model id.
        Defaults to "hetzner".
    score_after : bool
        Whether to run tmbench-check on the output after generation.
        Defaults to True.
    """

    def __init__(self, model: str = "hetzner", score_after: bool = True):
        self.model = model
        self.score_after = score_after
        self._scorer = None

    def run(
        self,
        arch_input: str,
        arch_id: str = "arch",
        input_type: str = "auto",
    ) -> TMResult:
        """
        Generate a threat model for the given architecture input.

        Parameters
        ----------
        arch_input : str
            Architecture description — Mermaid MMD, Terraform HCL, or prose.
        arch_id : str
            Identifier used in the output JSON and result filenames.
        input_type : str
            "mmd" | "terraform" | "prose" | "auto" (auto-detects from content).
        """
        if input_type == "auto":
            input_type = _detect_input_type(arch_input)

        if self.model == "ta_full_moe":
            tm, err = self._generate_via_ta_api(arch_input, arch_id)
        else:
            tm, err = self._generate_direct(arch_input, arch_id, input_type)

        if err or tm is None:
            return TMResult(arch_id=arch_id, model=self.model, error=err or "no output")

        result = TMResult(arch_id=arch_id, model=self.model, tm=tm)

        if self.score_after:
            score, tatb = self._score(tm)
            result.score = score
            result.tatb = tatb

        return result

    # ── internal helpers ──────────────────────────────────────────────────────

    def _generate_direct(
        self,
        arch_input: str,
        arch_id: str,
        input_type: str,
    ) -> tuple[Optional[dict], Optional[str]]:
        config = MODEL_CONFIGS.get(self.model)
        if config is None:
            # Treat as literal OpenRouter model id
            config = {
                "provider": "openrouter",
                "model": self.model,
                "env_key": "OPENROUTER_API_KEY",
            }

        env_key = config.get("env_key")
        if env_key and not os.environ.get(env_key):
            return None, f"{env_key} not set — cannot use model '{self.model}'"

        spec_excerpt = _load_spec_excerpt()
        produced_by = f"TMAgent/{self.model} v1.0"
        input_label = {"mmd": "Mermaid diagram", "terraform": "Terraform HCL", "prose": "Architecture description"}.get(
            input_type, "Architecture input"
        )

        system = _SYSTEM_PROMPT.format(produced_by=produced_by)
        user = _USER_PROMPT.format(
            spec_excerpt=spec_excerpt,
            arch_id=arch_id,
            input_label=input_label,
            arch_input=arch_input,
            produced_by=produced_by,
        )

        try:
            sys.path.insert(0, str(_ROOT))
            from agentic.llm_client import generate_response_with_system

            extra_kwargs = {}
            if config.get("extra_body"):
                extra_kwargs["extra_body"] = config["extra_body"]

            raw = generate_response_with_system(
                user,
                system,
                max_tokens=14000,
                temperature=0.1,
                **extra_kwargs,
            )
            return _parse_json_response(raw, arch_id)
        except Exception as exc:
            logger.exception("TMAgent generation failed for %s/%s", self.model, arch_id)
            return None, str(exc)

    def _generate_via_ta_api(
        self,
        arch_input: str,
        arch_id: str,
    ) -> tuple[Optional[dict], Optional[str]]:
        api_base = os.environ.get("TA_API_URL", "http://localhost:8000")
        payload = json.dumps({"content": arch_input, "arch_name": arch_id}).encode()
        try:
            req = urllib.request.Request(
                f"{api_base}/api/v1/analyze/artifact",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                bundle = json.loads(resp.read())
            tm = _convert_ta_export(bundle, arch_id)
            return tm, None
        except Exception as exc:
            logger.exception("TMAgent ta_full_moe failed for %s", arch_id)
            return None, str(exc)

    def _score(self, tm: dict) -> tuple[Optional[int], Optional[dict]]:
        scorer = self._load_scorer()
        if scorer is None:
            return None, None
        try:
            result = scorer.score_tm(tm)
            total = result.get("total", 0)
            tatb = {k: v[0] for k, v in result.get("tatb", {}).items()}
            return total, tatb
        except Exception:
            logger.exception("tmbench-check scoring failed")
            return None, None

    def _load_scorer(self):
        if self._scorer is not None:
            return self._scorer
        if not _SCORER_PATH.exists():
            logger.warning("tmbench-check scorer not found at %s", _SCORER_PATH)
            return None
        spec = importlib.util.spec_from_file_location("tmbench_check", _SCORER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._scorer = mod
        return mod


# ── module-level helpers ──────────────────────────────────────────────────────

def _detect_input_type(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("graph ") or stripped.startswith("flowchart") or "-->|" in stripped or "--->" in stripped:
        return "mmd"
    if re.search(r'\bresource\s+"[a-z][a-z0-9_]+"', stripped) or stripped.startswith("terraform {"):
        return "terraform"
    return "prose"


def _load_spec_excerpt() -> str:
    if not _SPEC_PATH.exists():
        raise FileNotFoundError(f"threatmodel.md spec not found at {_SPEC_PATH}")
    text = _SPEC_PATH.read_text(encoding="utf-8")
    idx = text.find("## 5. Scoring Summary")
    return text[:idx].strip() if idx > 0 else text


def _parse_json_response(raw: str, arch_id: str) -> tuple[Optional[dict], Optional[str]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return None, f"no JSON object found in LLM response for {arch_id}"
    try:
        return json.loads(m.group(0)), None
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error for {arch_id}: {exc}"


def _convert_ta_export(bundle: dict, arch_id: str) -> dict:
    """Convert ta-export/1.0 bundle → threatmodel/0.1 JSON."""
    assessment = bundle.get("assessment", {})
    gt = assessment.get("ground_truth", {})

    components = [
        {
            "id": c.get("id", c.get("name", "unknown")),
            "role": c.get("role", "compute"),
            "trust_zone": c.get("trust_zone", "internal"),
        }
        for c in gt.get("components", [])
    ]

    threat_actors = [
        {
            "name": a.get("name", "Unknown Actor"),
            "motivation": a.get("motivation", ""),
            "capability_tier": a.get("capability_tier", "targeted"),
            "initial_access_vector": a.get("initial_access", ""),
            "non_capabilities": a.get("non_capabilities", ["No physical access"]),
        }
        for a in gt.get("threat_actors", [])
    ]

    attack_paths = [
        {
            "path_id": ap.get("path_id", f"AP-{i+1:03d}"),
            "technique_id": ap.get("technique_id", ""),
            "technique_name": ap.get("technique_name", ""),
            "tactic": ap.get("tactic", ""),
            "target_component": ap.get("target_component", ""),
            "entry_point": ap.get("entry_point", ""),
            "impact": ap.get("impact", ""),
            "likelihood": ap.get("likelihood", "Medium"),
            "likelihood_rationale": ap.get("likelihood_rationale", ""),
        }
        for i, ap in enumerate(gt.get("attack_paths", []))
    ]

    mitigations = [
        {
            "mitigation_id": m.get("mitigation_id", ""),
            "control_id": m.get("control_id", ""),
            "control_name": m.get("control_name", ""),
            "addresses_technique": m.get("addresses_technique", []),
            "implementation_status": m.get("implementation_status", "Planned"),
            "residual_risk": m.get("residual_risk", "Medium"),
        }
        for m in gt.get("mitigations", [])
    ]

    findings = [
        {
            "finding_id": f.get("finding_id", ""),
            "severity": f.get("severity", "Medium"),
            "severity_rationale": f.get("severity_rationale", ""),
            "severity_vector": f.get("cvss_vector", f.get("aivss_vector", "")),
            "affected_components": f.get("affected_components", []),
            "linked_techniques": f.get("linked_techniques", []),
            "linked_mitigations": f.get("linked_mitigations", []),
            "remediation_priority": f.get("remediation_priority", "Short-term"),
        }
        for f in gt.get("findings", [])
    ]

    governance_raw = gt.get("governance", {})
    governance: dict[str, Any] = {
        "data_sovereignty": governance_raw.get("data_sovereignty", ["unspecified"]),
        "compliance_scope": governance_raw.get("compliance_scope", []),
        "third_party_dependencies": governance_raw.get("third_party_dependencies", []),
    }
    if governance_raw.get("agentic"):
        governance["agentic"] = governance_raw["agentic"]

    return {
        "spec_version": SPEC_VERSION,
        "architecture_id": arch_id,
        "produced_by": "TMAgent/ta_full_moe v1.0",
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "architecture_summary": {
            "components": components,
            "trust_boundaries": gt.get("trust_boundaries", []),
            "data_classification": gt.get("data_classification", "internal"),
            "operational_context": gt.get("operational_context", ""),
        },
        "threat_actors": threat_actors,
        "attack_paths": attack_paths,
        "mitigations": mitigations,
        "findings": findings,
        "governance": governance,
    }
