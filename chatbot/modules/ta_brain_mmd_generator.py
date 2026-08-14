"""
TA Brain Stage 8 — Gap→MMD generator.

Reads meta-layer gap generation_prompt entries from ta_brain.json, calls the LLM
to produce synthetic Mermaid architecture diagrams targeting under-sampled topology
regions, then stages them for human approval before harness submission.

Determinism contract:
  LLM is ONLY in the generate phase (generate_mmd_for_gap).
  validate_mmd, build_generation_prompt, staging, and queue operations are all
  deterministic pure functions — no LLM calls.

Self-growing loop step:
  gap detected → generate_synthetic_mmds() → staged queue → human approves →
  harness run (source=synthetic) → instance ingest → distiller → patterns update
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report"
BRAIN_PATH = REPORT_DIR / "ta_brain.json"
QUEUE_DIR = REPORT_DIR / "brain_synthetic_queue"

MAX_DEFAULT = 3
MIN_NODES = 3
MIN_EDGES = 2

VALID_STATUSES = {"staged", "approved", "rejected", "ingested"}

ARCH_VOCABULARIES: dict = {
    "ai_system": [
        "LLM", "VectorDB", "API Gateway", "Embedding Service",
        "Auth Service", "Rate Limiter", "Prompt Filter",
    ],
    "web_app": [
        "WebServer", "AppServer", "Database", "CDN",
        "WAF", "Auth Service", "Cache",
    ],
    "cloud": [
        "LoadBalancer", "EC2", "S3", "RDS",
        "IAM", "CloudWatch", "VPC",
    ],
    "iot": [
        "IoTDevice", "MQTT Broker", "Gateway",
        "CloudBackend", "FirmwareServer", "Dashboard",
    ],
    "generic": ["Service", "Database", "API", "Auth", "Client", "Monitor"],
}


# ── Validation ────────────────────────────────────────────────────────────────

def validate_mmd(mmd_text: str) -> tuple:
    """Deterministic structural validation. Returns (is_valid, reason). No LLM calls."""
    if not mmd_text or not mmd_text.strip():
        return False, "empty response"

    text = mmd_text.strip()

    # Accept graph TD / graph LR / flowchart TD / flowchart LR
    has_header = bool(re.search(r"^\s*(graph|flowchart)\s+(TD|LR|BT|RL)", text, re.MULTILINE | re.IGNORECASE))
    if not has_header:
        return False, "missing graph/flowchart header"

    # Count edge lines (contain --> or --- or ==> or -.->)
    edge_lines = [ln for ln in text.splitlines() if re.search(r"-{1,2}>|---", ln)]
    if len(edge_lines) < MIN_EDGES:
        return False, f"too few edges ({len(edge_lines)} < {MIN_EDGES})"

    # Count node definition lines: lines with brackets/parens/braces (node labels)
    # Also count node IDs appearing on edge lines as either source or target
    node_ids: set = set()
    for ln in text.splitlines():
        # Node definition: ID[label] ID(label) ID{label} ID((label))
        node_ids.update(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*[\[\(\{]", ln))
        # Node IDs on edge lines (source or target of -->)
        node_ids.update(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:-->|---|==>|-\.->)", ln))
        node_ids.update(re.findall(r"(?:-->|---|==>|-\.->)\s*([A-Za-z_][A-Za-z0-9_]*)\b", ln))

    # Remove common Mermaid keywords
    node_ids -= {"graph", "flowchart", "TD", "LR", "BT", "RL", "subgraph", "end", "style", "classDef", "class"}

    if len(node_ids) < MIN_NODES:
        return False, f"too few nodes ({len(node_ids)} < {MIN_NODES})"

    return True, "ok"


# ── Prompt construction ───────────────────────────────────────────────────────

def build_generation_prompt(gap: dict) -> tuple:
    """Build (system_message, user_prompt) for gap MMD generation. Pure function — no I/O."""
    region = gap.get("region", "")
    arch_type = region.replace("arch_type:", "").strip() if "arch_type:" in region else "generic"
    vocab = ARCH_VOCABULARIES.get(arch_type, ARCH_VOCABULARIES["generic"])
    gap_prompt = gap.get("generation_prompt", f"Generate a {arch_type} architecture diagram.")

    system_message = (
        "You are an expert software architect specialising in threat modelling and security architecture. "
        "You generate precise, realistic Mermaid architecture diagrams used to train threat assessment systems. "
        "Every diagram you produce must be syntactically valid Mermaid and architecturally coherent."
    )

    user_prompt = (
        f"Generate a synthetic {arch_type} architecture diagram for threat modelling research.\n\n"
        f"Gap being addressed: {gap_prompt}\n\n"
        f"Suggested component vocabulary for {arch_type} architectures: {', '.join(vocab)}\n\n"
        "Requirements:\n"
        "1. Use `graph TD` format.\n"
        "2. Include 5–10 nodes with meaningful labels reflecting the component vocabulary above.\n"
        "3. Include at least 3 directed edges showing data or control flow.\n"
        "4. Include at least one security-sensitive component (auth, encryption, logging, validation, etc.).\n"
        "5. Node IDs must be alphanumeric identifiers (no spaces).\n\n"
        "Output ONLY the Mermaid diagram. No explanation, no markdown fences."
    )

    return system_message, user_prompt


# ── LLM generation ────────────────────────────────────────────────────────────

def generate_mmd_for_gap(gap: dict, llm_client=None) -> dict:
    """Call LLM to produce a synthetic MMD for a single gap. llm_client injected for tests."""
    arch_type = gap.get("region", "generic").replace("arch_type:", "").strip()
    system_message, user_prompt = build_generation_prompt(gap)

    try:
        if llm_client is not None:
            raw_response = llm_client(user_prompt, system_message)
        else:
            from agentic.llm_client import generate_response_with_system
            raw_response = generate_response_with_system(
                prompt=user_prompt,
                system_message=system_message,
                temperature=0.7,
                max_tokens=800,
            )
    except Exception as exc:
        logger.warning("LLM call failed for gap %s: %s", gap.get("id"), exc)
        return {
            "gap_id": gap.get("id"),
            "arch_type": arch_type,
            "mmd_text": "",
            "valid": False,
            "validation_reason": f"llm_error: {exc}",
            "raw_response": "",
        }

    # Strip markdown fences if the model wrapped anyway
    mmd_text = raw_response.strip()
    if mmd_text.startswith("```"):
        mmd_text = re.sub(r"^```[a-zA-Z]*\n?", "", mmd_text)
        mmd_text = re.sub(r"\n?```$", "", mmd_text).strip()

    valid, reason = validate_mmd(mmd_text)
    return {
        "gap_id": gap.get("id"),
        "arch_type": arch_type,
        "gap_type": gap.get("type", ""),
        "generation_prompt": gap.get("generation_prompt", ""),
        "mmd_text": mmd_text,
        "valid": valid,
        "validation_reason": reason,
        "raw_response": raw_response,
    }


# ── Queue management ──────────────────────────────────────────────────────────

def _get_existing_gen_ids(queue_dir: Path) -> set:
    """Return set of gap_ids that already have a staged/approved entry in the queue."""
    if not queue_dir.exists():
        return set()
    existing: set = set()
    for meta_file in queue_dir.glob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            if meta.get("status") in ("staged", "approved"):
                existing.add(meta.get("gap_id"))
        except Exception:
            pass
    return existing


def stage_result(result: dict, queue_dir: Path = None) -> Optional[dict]:
    """
    Write .mmd + .meta.json for a valid generation result.
    Returns the meta dict written, or None if skipped (invalid or already staged).
    """
    qdir = queue_dir or QUEUE_DIR
    qdir.mkdir(parents=True, exist_ok=True)

    if not result.get("valid"):
        return None

    existing = _get_existing_gen_ids(qdir)
    if result.get("gap_id") in existing:
        logger.debug("Gap %s already staged — skipping", result.get("gap_id"))
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    gen_id = f"GEN-{result['gap_id']}-{ts}"
    mmd_file = f"{gen_id}.mmd"

    meta = {
        "gen_id": gen_id,
        "gap_id": result["gap_id"],
        "arch_type": result["arch_type"],
        "gap_type": result.get("gap_type", ""),
        "generation_prompt": result.get("generation_prompt", ""),
        "status": "staged",
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "mmd_file": mmd_file,
        "valid": result["valid"],
        "validation_reason": result["validation_reason"],
    }

    (qdir / mmd_file).write_text(result["mmd_text"])
    (qdir / f"{gen_id}.meta.json").write_text(json.dumps(meta, indent=2))
    logger.info("Staged %s for gap %s", gen_id, result["gap_id"])
    return meta


def generate_synthetic_mmds(
    gap_ids: list = None,
    max_per_run: int = MAX_DEFAULT,
    brain_path: Path = None,
    queue_dir: Path = None,
    llm_client=None,
) -> list:
    """
    Main entry point. Reads gaps from brain, selects by priority (forced_gap first),
    skips already-staged, generates up to max_per_run, stages valid results.
    Returns list of staged meta dicts.
    """
    bpath = brain_path or BRAIN_PATH
    qdir = queue_dir or QUEUE_DIR

    if not bpath.exists():
        raise ValueError(f"Brain not built: {bpath}")

    brain = json.loads(bpath.read_text())
    all_gaps = brain.get("gaps", [])

    # Filter to requested gap_ids if provided
    if gap_ids:
        all_gaps = [g for g in all_gaps if g.get("id") in gap_ids]

    # Skip gaps already staged/approved
    existing_gap_ids = _get_existing_gen_ids(qdir)
    candidates = [g for g in all_gaps if g.get("id") not in existing_gap_ids]

    # Sort: forced_gap first, then by priority descending
    candidates.sort(key=lambda g: (0 if g.get("forced_gap") else 1, -g.get("priority", 0)))

    selected = candidates[:max_per_run]
    staged: list = []

    for gap in selected:
        result = generate_mmd_for_gap(gap, llm_client=llm_client)
        meta = stage_result(result, queue_dir=qdir)
        if meta:
            staged.append(meta)

    return staged


def list_synthetic_queue(queue_dir: Path = None) -> list:
    """Return all meta dicts from queue dir, sorted by generated_ts descending."""
    qdir = queue_dir or QUEUE_DIR
    if not qdir.exists():
        return []

    entries: list = []
    for meta_file in qdir.glob("*.meta.json"):
        try:
            entries.append(json.loads(meta_file.read_text()))
        except Exception:
            pass

    entries.sort(key=lambda e: e.get("generated_ts", ""), reverse=True)
    return entries


def update_synthetic_status(gen_id: str, status: str, queue_dir: Path = None) -> dict:
    """
    Update status in a .meta.json file. Raises FileNotFoundError if gen_id not found.
    status must be one of: staged, approved, rejected, ingested.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_STATUSES}")

    qdir = queue_dir or QUEUE_DIR
    meta_path = qdir / f"{gen_id}.meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Generation entry not found: {gen_id}")

    meta = json.loads(meta_path.read_text())
    meta["status"] = status
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def get_generation_summary(queue_dir: Path = None) -> dict:
    """Return stats: total, by_status counts, by_gap_id counts, gaps_covered list."""
    entries = list_synthetic_queue(queue_dir=queue_dir)

    by_status: dict = {"staged": 0, "approved": 0, "rejected": 0, "ingested": 0}
    by_gap_id: dict = {}

    for entry in entries:
        s = entry.get("status", "staged")
        if s in by_status:
            by_status[s] += 1
        gid = entry.get("gap_id", "unknown")
        by_gap_id[gid] = by_gap_id.get(gid, 0) + 1

    return {
        "total": len(entries),
        "by_status": by_status,
        "by_gap_id": by_gap_id,
        "gaps_covered": sorted(by_gap_id.keys()),
    }
