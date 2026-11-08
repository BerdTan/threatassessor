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
  nemotron_ultra → nvidia/nemotron-3-ultra-550b-a55b:free (OPENROUTER_API_KEY, slow ~10min/arch)
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
    "nemotron_ultra": {
        "provider": "openrouter",
        "model": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
        "env_key": "OPENROUTER_API_KEY",
        "max_tokens": 24000,
    },
    "deepseek_flash": {
        "provider": "openrouter",
        "model": "openrouter/deepseek/deepseek-v4.1-flash-1017",
        "env_key": "OPENROUTER_API_KEY",
        "max_tokens": 24000,  # 14000 truncates t3/t4 arches → incomplete JSON
        "strip_thinking": True,  # deepseek may emit <think>...</think> before JSON
    },
    "ta_v3": {
        "provider": "ta_api",
        "model": "ta-pipeline-v3",
        "env_key": None,
    },
    "ta_v3_1": {
        "provider": "ta_api",
        "model": "ta-pipeline-v3",
        "env_key": None,
        "force_mode": "api_only",  # bypass brain_fast; tests generator with ATLAS wiring
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
            max_tokens=config.get("max_tokens", 14000),
            temperature=0.1,
            **extra_kwargs,
        )
        raw = resp.content.strip()
        # Strip <think>...</think> blocks (deepseek and similar reasoning models)
        import re as _re
        if config.get("strip_thinking"):
            raw = _re.sub(r'<think>.*?</think>', '', raw, flags=_re.DOTALL).strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
        # Extract JSON object (skip any thinking prefix)
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if not m:
            print(f"  [error] no JSON found in response for {arch_id}", file=sys.stderr)
            return None
        return json.loads(m.group(0))
    except Exception as e:
        print(f"  [error] {tool}/{arch_id}: {e}", file=sys.stderr)
        return None


def call_ta_api(arch_id: str, tool: str = "ta_v3", dry_run: bool = False) -> dict | None:
    """Call TA's local API via /analyze-stream (SSE) and convert ta-export/1.0 → threatmodel/0.1."""
    import urllib.request
    import urllib.parse

    api_base = os.environ.get("TA_API_URL", "http://localhost:8000")
    api_key = os.environ.get("TA_API_KEY") or os.environ.get("API_KEY", "")
    if dry_run:
        print(f"\n[dry-run] Would call TA API at {api_base} for {arch_id}")
        return None

    config = TOOL_CONFIGS.get(tool, {})
    mmd = load_mmd(arch_id)
    form_fields: dict = {
        "mmd_text": mmd,
        "mmd_name": arch_id,
        "include_validation": "true",
    }
    if config.get("force_mode"):
        form_fields["force_mode"] = config["force_mode"]
    form_data = urllib.parse.urlencode(form_fields).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if api_key:
        headers["TM-API-KEY"] = api_key
    try:
        req = urllib.request.Request(
            f"{api_base}/api/v1/analyze-stream",
            data=form_data,
            headers=headers,
            method="POST",
        )
        # Consume the SSE stream to completion; extract architecture_name from complete event
        arch_name_resolved = arch_id
        current_event = None
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:") and current_event == "complete":
                    try:
                        evt = json.loads(line[5:].strip())
                        arch_name_resolved = evt.get("architecture_name", arch_id)
                    except json.JSONDecodeError:
                        pass
                    break
                elif not line:
                    current_event = None

        # Read ground_truth + governance from report directory
        report_dir = ROOT / "report" / arch_name_resolved
        gt_path = report_dir / "ground_truth.json"
        gs_path = report_dir / "governance_signals.json"
        if not gt_path.exists():
            print(f"  [error] ta_v3/{arch_id}: report not found at {gt_path}", file=sys.stderr)
            return None
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        gs = json.loads(gs_path.read_text(encoding="utf-8")) if gs_path.exists() else {}
        return convert_ta_gt_to_threatmodel(gt, gs, arch_id)
    except Exception as e:
        print(f"  [error] ta_v3/{arch_id}: {e}", file=sys.stderr)
        return None


def _load_mitre_lookup() -> dict:
    """Return {technique_id: (name, tactic)} from enterprise-attack.json."""
    mitre_path = ROOT / "chatbot/data/enterprise-attack.json"
    if not mitre_path.exists():
        return {}
    try:
        data = json.loads(mitre_path.read_text(encoding="utf-8"))
        lookup = {}
        for obj in data.get("objects", []):
            if obj.get("type") != "attack-pattern":
                continue
            refs = obj.get("external_references", [])
            tid = next((r["external_id"] for r in refs if r.get("source_name") == "mitre-attack"), None)
            if not tid:
                continue
            name = obj.get("name", "")
            phases = obj.get("kill_chain_phases", [])
            tactic = phases[0]["phase_name"].replace("-", " ").title() if phases else ""
            lookup[tid] = (name, tactic)
        return lookup
    except Exception:
        return {}


_MITRE_LOOKUP: dict = {}


def convert_ta_gt_to_threatmodel(gt: dict, gs: dict, arch_id: str) -> dict:
    """Convert TA ground_truth.json + governance_signals.json → threatmodel/0.1."""
    global _MITRE_LOOKUP
    if not _MITRE_LOOKUP:
        _MITRE_LOOKUP = _load_mitre_lookup()

    _INITIAL_ACCESS = {"T1566", "T1190", "T1133", "T1078", "T1189", "T1091", "T1195", "T1199", "T1200"}
    _TIER_MAP = {"CRITICAL": "Critical", "HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}
    _CRIT_LIKELIHOOD = {"CRITICAL": "High", "HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}

    # Components: unique nodes from attack_path paths
    seen_nodes: set = set()
    components = []
    for ap in gt.get("attack_paths", []):
        for node in ap.get("path", []):
            if node not in seen_nodes:
                seen_nodes.add(node)
                components.append({"id": node, "role": "compute", "trust_zone": "internal"})

    # Threat actors: APT groups → threatmodel format
    threat_actors = []
    for actor in gt.get("threat_actors", []):
        overlap = actor.get("overlap_pct", 0)
        cap = "nation-state" if overlap >= 0.5 else ("targeted" if overlap >= 0.3 else "opportunistic")
        matched = actor.get("matched_techniques", [])
        ia_techs = [t for t in matched if t in _INITIAL_ACCESS]
        threat_actors.append({
            "name": actor.get("name", "Unknown Actor"),
            "motivation": "Cyber espionage and financial gain",
            "capability_tier": cap,
            "initial_access_vector": ia_techs[0] if ia_techs else (matched[0] if matched else ""),
            "non_capabilities": ["No physical access to target systems"],
        })

    # Attack paths
    recs = gt.get("control_recommendations", [])
    rec_by_path: dict = {}
    for rec in recs:
        for pid in rec.get("attack_paths", []):
            if pid not in rec_by_path:
                rec_by_path[pid] = rec.get("control", "")

    attack_paths = []
    for i, ap in enumerate(gt.get("attack_paths", [])):
        tier = ap.get("criticality_tier", "MEDIUM")
        techs = ap.get("techniques", [])
        tid = techs[0] if techs else ""
        tname, tactic = _MITRE_LOOKUP.get(tid, ("", ""))
        attack_paths.append({
            "path_id": ap.get("id", f"AP-{i+1:03d}"),
            "technique_id": tid,
            "technique_name": tname,
            "tactic": tactic,
            "target_component": ap.get("target", ""),
            "entry_point": ap.get("entry", ""),
            "impact": f"{tier}: {ap.get('target', '')} compromise via {ap.get('entry', '')}",
            "likelihood": _CRIT_LIKELIHOOD.get(tier, "Medium"),
            "likelihood_rationale": ap.get("rationale", ""),
            "mitigation": rec_by_path.get(i, ""),
            "finding": f"{_TIER_MAP.get(tier, tier)} severity path — {ap.get('hop_count', 0)} hops",
        })

    # Mitigations: top critical/high control recommendations (skip those without MITRE M-IDs)
    mitigations = []
    for rec in recs:
        ctrl_ids = [c for c in rec.get("mitigations", []) if c]
        if not ctrl_ids:
            continue
        j = len(mitigations)
        mitigations.append({
            "mitigation_id": f"M-{j+1:03d}",
            "control_id": ctrl_ids[0],
            "control_name": rec.get("control", ""),
            "addresses_technique": rec.get("techniques", [])[:5],
            "implementation_status": "Planned",
            "residual_risk": "Low",
        })
        if len(mitigations) >= 10:
            break

    # Findings: one per CRITICAL/HIGH attack path
    findings = []
    for k, ap in enumerate(gt.get("attack_paths", [])):
        tier = ap.get("criticality_tier", "MEDIUM")
        if tier not in ("CRITICAL", "HIGH"):
            continue
        severity = _TIER_MAP.get(tier, "High")
        cvss = ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H" if tier == "CRITICAL"
                else "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H")
        findings.append({
            "finding_id": f"F-{k+1:03d}",
            "severity": severity,
            "severity_rationale": ap.get("rationale", ""),
            "severity_vector": cvss,
            "affected_components": ap.get("path", []),
            "linked_techniques": ap.get("techniques", [])[:5],
            "linked_mitigations": [f"M-{j+1:03d}" for j in range(min(2, len(mitigations)))],
            "remediation_priority": "Immediate" if tier == "CRITICAL" else "Short-term",
        })

    # Governance
    sov = gs.get("sovereignty", {})
    arch_meta = gs.get("arch_metadata", {})
    governance: dict = {
        "data_sovereignty": sov.get("inferred_regions") or sov.get("arc_categories", []),
        "compliance_scope": sov.get("arc_categories", []),
        "third_party_dependencies": [],
    }
    if arch_meta.get("is_agentic"):
        governance["agentic"] = {
            "tool_call_scope": "restricted",
            "oversight_required": not arch_meta.get("no_oversight_path", False),
        }

    import datetime
    return {
        "spec_version": "threatmodel/0.1",
        "architecture_id": arch_id,
        "produced_by": "ta_v3 v1.0",
        "produced_at": datetime.datetime.utcnow().isoformat() + "Z",
        "architecture_summary": {
            "components": components,
            "trust_boundaries": list({ap.get("entry", "") for ap in gt.get("attack_paths", []) if ap.get("entry")}),
            "data_classification": "internal",
            "operational_context": gt.get("architecture_name", arch_id),
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
    if TOOL_CONFIGS.get(tool, {}).get("provider") == "ta_api":
        tm = call_ta_api(arch_id, tool=tool, dry_run=dry_run)
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
