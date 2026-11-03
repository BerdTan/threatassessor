#!/usr/bin/env python3
"""
tmbench_generate.py — TMbench: generate TM JSON from corpus arch using any LLM.

Usage:
  python3 scripts/tmbench/tmbench_generate.py --tool hetzner --arch t1_web_app
  python3 scripts/tmbench/tmbench_generate.py --tool gemini_flash --all
  python3 scripts/tmbench/tmbench_generate.py --tool gpt4o --arch t2_microservices --dry-run

Tools (aligned with model_routing.yaml confirmed/partial models):
  hetzner        → Qwen3.6-35B-A3B-FP8 via Hetzner   (HETZNER_API_KEY)
  hetzner_27b    → Qwen3.8-27B via Hetzner             (HETZNER_API_KEY, high_quality tier)
  gemini_flash   → gemini-3.6-flash via Gemini AI      (GEMINI_API_KEY)
  nemotron_super → nvidia/nemotron-3-super-120b:free    (OPENROUTER_API_KEY, slow ~10min/arch)
  gpt4o          → openai/gpt-4o via OpenRouter         (OPENROUTER_API_KEY, external comparison)
  ta_v3          → TA full harness API → threatmodel/0.1 (TA_API_URL, requires running API)

After generation, auto-ingests with tmbench_runner.py --ingest.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Load .env early so API keys are available for env checks
try:
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
except ImportError:
    pass
CORPUS_DIR = ROOT / "docs/tmbench/corpus"
RESULTS_DIR = ROOT / "docs/tmbench/results"
SPEC_PATH = ROOT / "docs/tmbench/threatmodel.md"
RUNNER = ROOT / "scripts/tmbench/tmbench_runner.py"

CORPUS_ARCHS = [
    "t1_web_app", "t1_rest_api",
    "t2_microservices", "t2_cicd_pipeline", "t2_saas_integration",
    "t3_multicloud_data", "t3_hybrid_identity", "t3_container_orchestration",
    "t4_rag_pipeline", "t4_agent_fleet",
]

# Model IDs are the full LiteLLM strings passed directly to LLMClient.generate(model=...).
# Aligned with policies/model_routing.yaml confirmed/partial entries.
TOOL_CONFIGS = {
    "hetzner": {
        "provider": "hetzner",
        "model": "openai/Qwen/Qwen3.6-35B-A3B-FP8",
        "env_key": "HETZNER_API_KEY",
        "extra_body": {"enable_thinking": False},
    },
    "hetzner_27b": {
        "provider": "hetzner",
        "model": "openai/Qwen3.8-27B",
        "env_key": "HETZNER_API_KEY",
        "extra_body": {"enable_thinking": False},
    },
    "gemini_flash": {
        "provider": "gemini",
        "model": "gemini/gemini-3.6-flash",
        "env_key": "GEMINI_API_KEY",
    },
    "nemotron_super": {
        "provider": "openrouter",
        "model": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "env_key": "OPENROUTER_API_KEY",
    },
    "ta_v3": {
        "provider": "ta_api",
        "model": "ta-pipeline-v3",
        "env_key": None,
    },
}

SYSTEM_PROMPT = """You are a security architect producing a structured threat model.
You will be given an architecture diagram in Mermaid syntax and the threatmodel/0.1 spec.
Produce a complete, valid threat model JSON that satisfies every requirement in the spec.

Rules:
- Output ONLY valid JSON — no markdown fences, no commentary, no preamble
- Follow the output schema in §4 exactly
- Use real MITRE ATT&CK technique IDs (verify tactic phase matches)
- For AI/ML components include MITRE ATLAS techniques
- Every threat actor must have a non-empty non_capabilities list
- Every attack path must have a mitigation and a finding
- High and Critical findings require a CVSS 3.1 vector
- The produced_by field must be: {tool_name} v1.0"""

USER_PROMPT_TEMPLATE = """Spec:
---
{spec_excerpt}
---

Architecture ID: {arch_id}
Mermaid diagram:
```
{mmd}
```

Produce the complete threat model JSON for this architecture.
Set architecture_id to "{arch_id}" and produced_by to "{tool_name} v1.0"."""


def load_spec_excerpt() -> str:
    """Load sections 1-4 of the spec (required sections + schema)."""
    text = SPEC_PATH.read_text(encoding="utf-8")
    # Everything up to §5 (Scoring Summary)
    idx = text.find("## 5. Scoring Summary")
    return text[:idx].strip() if idx > 0 else text


def load_mmd(arch_id: str) -> str:
    path = CORPUS_DIR / f"{arch_id}.mmd"
    if not path.exists():
        raise FileNotFoundError(f"MMD not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def call_llm_client(tool: str, arch_id: str, dry_run: bool = False) -> dict | None:
    """Call TA's LLMClient with explicit provider + model routing."""
    config = TOOL_CONFIGS[tool]
    env_key = config["env_key"]
    if env_key and not os.environ.get(env_key):
        print(f"[error] {env_key} not set — cannot run {tool}", file=sys.stderr)
        return None

    spec_excerpt = load_spec_excerpt()
    mmd = load_mmd(arch_id)
    produced_by = f"{tool} v1.0"
    system = SYSTEM_PROMPT.format(tool_name=produced_by)
    user = USER_PROMPT_TEMPLATE.format(
        spec_excerpt=spec_excerpt,
        arch_id=arch_id,
        mmd=mmd,
        tool_name=produced_by,
    )

    if dry_run:
        print(f"\n[dry-run] Would send to {tool}:")
        print(f"  arch:    {arch_id}")
        print(f"  model:   {config['model']}")
        print(f"  prompt:  {len(system)+len(user)} chars")
        return None

    print(f"  Calling {tool} ({config['model']}) for {arch_id}...")
    try:
        sys.path.insert(0, str(ROOT))
        import dotenv
        dotenv.load_dotenv(ROOT / ".env")
        from agentic.llm_client import LLMClient, LLMProvider

        client = LLMClient()
        provider = LLMProvider(config["provider"])
        extra_kwargs = {}
        if config.get("extra_body"):
            extra_kwargs["extra_body"] = config["extra_body"]

        resp = client.generate(
            prompt=user,
            system_message=system,
            provider=provider,
            model=config["model"],
            max_tokens=14000,
            temperature=0.1,
            **extra_kwargs,
        )
        raw = resp.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
        # Extract JSON object (skip any thinking prefix)
        import re as _re
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if not m:
            print(f"  [error] no JSON found in response for {arch_id}", file=sys.stderr)
            return None
        return json.loads(m.group(0))
    except Exception as e:
        print(f"  [error] {tool}/{arch_id}: {e}", file=sys.stderr)
        return None


def call_ta_api(arch_id: str, dry_run: bool = False) -> dict | None:
    """Call TA's local API and convert ta-export/1.0 → threatmodel/0.1."""
    import urllib.request

    api_base = os.environ.get("TA_API_URL", "http://localhost:8000")
    if dry_run:
        print(f"\n[dry-run] Would call TA API at {api_base} for {arch_id}")
        return None

    mmd = load_mmd(arch_id)
    payload = json.dumps({"content": mmd, "arch_name": arch_id}).encode()
    try:
        req = urllib.request.Request(
            f"{api_base}/api/v1/analyze/artifact",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            bundle = json.loads(resp.read())
        return convert_ta_export_to_threatmodel(bundle, arch_id)
    except Exception as e:
        print(f"  [error] ta_v3/{arch_id}: {e}", file=sys.stderr)
        return None


def convert_ta_export_to_threatmodel(bundle: dict, arch_id: str) -> dict:
    """Best-effort conversion from ta-export/1.0 to threatmodel/0.1."""
    assessment = bundle.get("assessment", {})
    gt = assessment.get("ground_truth", {})

    components = [
        {"id": c.get("id", c.get("name", "unknown")),
         "role": c.get("role", "compute"),
         "trust_zone": c.get("trust_zone", "internal")}
        for c in gt.get("components", [])
    ]

    threat_actors = []
    for actor in gt.get("threat_actors", []):
        threat_actors.append({
            "name": actor.get("name", "Unknown Actor"),
            "motivation": actor.get("motivation", ""),
            "capability_tier": actor.get("capability_tier", "targeted"),
            "initial_access_vector": actor.get("initial_access", ""),
            "non_capabilities": actor.get("non_capabilities", ["No physical access"]),
        })

    attack_paths = []
    for i, ap in enumerate(gt.get("attack_paths", [])):
        attack_paths.append({
            "path_id": ap.get("path_id", f"AP-{i+1:03d}"),
            "technique_id": ap.get("technique_id", ""),
            "technique_name": ap.get("technique_name", ""),
            "tactic": ap.get("tactic", ""),
            "target_component": ap.get("target_component", ""),
            "entry_point": ap.get("entry_point", ""),
            "impact": ap.get("impact", ""),
            "likelihood": ap.get("likelihood", "Medium"),
            "likelihood_rationale": ap.get("likelihood_rationale", ""),
        })

    mitigations = []
    for m in gt.get("mitigations", []):
        mitigations.append({
            "mitigation_id": m.get("mitigation_id", ""),
            "control_id": m.get("control_id", ""),
            "control_name": m.get("control_name", ""),
            "addresses_technique": m.get("addresses_technique", []),
            "implementation_status": m.get("implementation_status", "Planned"),
            "residual_risk": m.get("residual_risk", "Medium"),
        })

    findings = []
    for f in gt.get("findings", []):
        findings.append({
            "finding_id": f.get("finding_id", ""),
            "severity": f.get("severity", "Medium"),
            "severity_rationale": f.get("severity_rationale", ""),
            "severity_vector": f.get("cvss_vector", f.get("aivss_vector", "")),
            "affected_components": f.get("affected_components", []),
            "linked_techniques": f.get("linked_techniques", []),
            "linked_mitigations": f.get("linked_mitigations", []),
            "remediation_priority": f.get("remediation_priority", "Short-term"),
        })

    gov = gt.get("governance", {})
    governance = {
        "data_sovereignty": gov.get("data_sovereignty", []),
        "compliance_scope": gov.get("compliance_scope", []),
        "third_party_dependencies": gov.get("third_party_dependencies", []),
    }
    if "agentic" in gov:
        governance["agentic"] = gov["agentic"]

    return {
        "spec_version": "threatmodel/0.1",
        "architecture_id": arch_id,
        "produced_by": "ta_v3 v1.0",
        "produced_at": bundle.get("produced_at", ""),
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


def ingest(tool: str, arch_id: str, tm: dict) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(tm, f, indent=2)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--ingest", tool, tmp_path],
            capture_output=True, text=True
        )
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def run_one(tool: str, arch_id: str, dry_run: bool) -> bool:
    if tool == "ta_v3":
        tm = call_ta_api(arch_id, dry_run=dry_run)
    else:
        tm = call_llm_client(tool, arch_id, dry_run=dry_run)

    if tm is None:
        return False

    ingest(tool, arch_id, tm)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="TMbench generator — Step 37")
    parser.add_argument("--tool", required=True,
                        choices=list(TOOL_CONFIGS.keys()),
                        help=f"Tool to run: {', '.join(TOOL_CONFIGS)}")
    parser.add_argument("--arch", help="Single architecture ID to run")
    parser.add_argument("--all", action="store_true",
                        help="Run all 10 corpus architectures")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be sent without calling the LLM")
    args = parser.parse_args()

    if not args.arch and not args.all:
        parser.error("Pass --arch <id> or --all")

    archs = CORPUS_ARCHS if args.all else [args.arch]

    print(f"\nTMbench Generator — tool: {args.tool}")
    print(f"Archs: {len(archs)}")
    if args.dry_run:
        print("Mode: dry-run (no LLM calls)\n")

    success = 0
    for arch_id in archs:
        if args.all:
            print(f"\n[{archs.index(arch_id)+1}/{len(archs)}] {arch_id}")
        ok = run_one(args.tool, arch_id, dry_run=args.dry_run)
        if ok:
            success += 1
        if not args.dry_run and len(archs) > 1:
            time.sleep(0.5)

    if not args.dry_run:
        print(f"\nGenerated: {success}/{len(archs)} architectures")
        if success > 0:
            print(f"\nLeaderboard update:")
            subprocess.run([sys.executable, str(RUNNER), "--leaderboard"])


if __name__ == "__main__":
    main()
