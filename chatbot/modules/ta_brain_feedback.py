"""
TA Brain feedback — Stage 3: interaction log write-back.

Callers that know a prediction was right or wrong can record that signal.
Feedback is appended as a new entry in ta_brain_interactions.jsonl (never
modifies existing entries — append-only invariant preserved).

Stage 4 (confidence decay) reads these feedback entries and updates pattern
confidence. Stage 7 (TACO processor) joins them by topology_sig+arch_type+mode
to compute demand weights and gap priorities.

Feedback is also propagated to the cache layer immediately:
  confirmed → cache entry strengthened (hit_count++)
  wrong     → cache entry evicted
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chatbot.modules.ta_brain_cache import get_cache_manager

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report"
INTERACTIONS_PATH = REPORT_DIR / "ta_brain_interactions.jsonl"

VALID_FEEDBACK = ("confirmed", "wrong", "partial")


def record_feedback(
    topology_sig: str,
    arch_type: str,
    mode: str,
    feedback: str,
    reference_ts: str = "",
    caller_type: str = "rest",
) -> dict:
    """
    Append a feedback entry to ta_brain_interactions.jsonl and propagate
    to the cache layer.

    Args:
        topology_sig:  topology_signature of the queried architecture
        arch_type:     arch_type used in the original query
        mode:          query mode ("infer" | "gaps" | "patterns")
        feedback:      "confirmed" | "wrong" | "partial"
        reference_ts:  ISO ts of the original query entry (optional link)
        caller_type:   "rest" | "mcp" | "harness"

    Returns summary dict. Never raises.
    """
    if feedback not in VALID_FEEDBACK:
        return {"error": f"Invalid feedback '{feedback}'. Valid: {', '.join(VALID_FEEDBACK)}"}
    if not topology_sig:
        return {"error": "topology_sig is required"}

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "feedback",
        "feedback": feedback,
        "topology_signature": topology_sig,
        "arch_type": arch_type,
        "query_mode": mode,
        "reference_ts": reference_ts,
        "caller_type": caller_type,
    }

    try:
        with INTERACTIONS_PATH.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
        log_ok = True
    except Exception as exc:
        logger.warning("Could not write feedback to interaction log: %s", exc)
        log_ok = False

    # Propagate to cache layer
    cache = get_cache_manager()
    cache_updated = cache.record_feedback(topology_sig, arch_type, mode, feedback)

    return {
        "recorded": log_ok,
        "cache_updated": cache_updated,
        "feedback": feedback,
        "topology_sig": topology_sig,
        "arch_type": arch_type,
        "mode": mode,
        "ts": entry["ts"],
    }


def get_feedback_summary(
    interactions_path: Optional[Path] = None,
) -> dict:
    """
    Read interaction log and return feedback signal counts.
    Used by Stage 4 (confidence decay) and Stage 7 (TACO processor).

    Returns:
        {
          "total_queries": int,
          "total_feedback": int,
          "by_pattern_sig": {
            "<topology_sig>:<arch_type>:<mode>": {
              "confirmed": int, "wrong": int, "partial": int
            }
          }
        }
    """
    path = interactions_path or INTERACTIONS_PATH
    if not path.exists():
        return {"total_queries": 0, "total_feedback": 0, "by_pattern_sig": {}}

    total_queries = 0
    total_feedback = 0
    by_sig: dict = {}

    for line in path.read_text().strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if entry.get("type") == "feedback":
            total_feedback += 1
            key = f"{entry.get('topology_signature','')}:{entry.get('arch_type','')}:{entry.get('query_mode','')}"
            if key not in by_sig:
                by_sig[key] = {"confirmed": 0, "wrong": 0, "partial": 0}
            fb = entry.get("feedback", "")
            if fb in by_sig[key]:
                by_sig[key][fb] += 1
        elif entry.get("query_mode"):
            total_queries += 1

    return {
        "total_queries": total_queries,
        "total_feedback": total_feedback,
        "by_pattern_sig": by_sig,
    }
