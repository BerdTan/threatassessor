"""
TACO cache layer — Stage 2.5.

Sits between callers and the KG pattern layer. Answers identical-topology queries
without KG retrieval; on miss, labels the miss as variant or new (for interaction
log meta-layer signals), then bypasses to KG and writes the result.

Routing:
  HIT     — exact (topology_sig, arch_type, mode) key + current pattern_version
  MISS    — anything else → bypass to KG, write entry on return

Variant labeling (on MISS, for interaction log only — does NOT change routing):
  variant — same arch_type, multiset-Jaccard(shape_counts) ≥ VARIANT_THRESHOLD
  new     — no cached entry in same arch_type passes threshold, or no shape_counts given

Invalidation:
  pattern_version bump → stale entries bypass to KG on next query, then refresh.
  evict_stale() removes them proactively (call after build_brain).

Self-learning signals (via record_feedback):
  confirmed → hit_count++, last_confirmed_ts updated
  wrong     → entry evicted immediately

Determinism contract: no LLM calls anywhere in this module.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report"


def _brain_dir() -> Path:
    try:
        from chatbot.config import get_settings  # noqa: PLC0415
        rd = get_settings().system.report_dir
        base = Path(rd) if Path(rd).is_absolute() else ROOT / rd
    except Exception:
        base = ROOT / "report"
    return base / "brain"


CACHE_PATH = _brain_dir() / "ta_brain_cache.json"

VARIANT_THRESHOLD = 0.7  # multiset Jaccard threshold for variant labeling

# ── Shape utilities ───────────────────────────────────────────────────────────

def extract_shape_counts(parsed_nodes: dict) -> dict:
    """Count occurrences of each node shape — used for multiset Jaccard."""
    return dict(Counter(v.get("shape", "unknown") for v in parsed_nodes.values()))


def multiset_jaccard(a: dict, b: dict) -> float:
    """
    Generalized Jaccard similarity on shape count dicts.
    Returns 1.0 if both are empty; 0.0 if one is empty and other is not.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    all_keys = set(a) | set(b)
    intersection = sum(min(a.get(k, 0), b.get(k, 0)) for k in all_keys)
    union = sum(max(a.get(k, 0), b.get(k, 0)) for k in all_keys)
    return round(intersection / union, 4) if union else 0.0


# ── Cache key ─────────────────────────────────────────────────────────────────

def _make_key(topology_sig: str, arch_type: str, mode: str) -> str:
    return f"{topology_sig}:{arch_type}:{mode}"


# ── CacheManager ──────────────────────────────────────────────────────────────

class CacheManager:
    """
    File-backed cache manager. Loads on first access, flushes on every write.
    Thread-safety: not required for single-process async FastAPI usage.
    """

    def __init__(self, cache_path: Path = CACHE_PATH):
        self._path = cache_path
        self._entries: dict = {}  # key → entry dict
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                self._entries = raw.get("entries", {})
            except Exception as exc:
                logger.warning("Could not load cache: %s", exc)
                self._entries = {}
        self._loaded = True

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "meta": {
                    "entry_count": len(self._entries),
                    "flushed_ts": datetime.now(timezone.utc).isoformat(),
                },
                "entries": self._entries,
            }
            self._path.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            logger.warning("Could not flush cache: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def route(
        self,
        topology_sig: str,
        arch_type: str,
        mode: str,
        current_pattern_version: int,
        shape_counts: Optional[dict] = None,
    ) -> tuple:
        """
        Check cache for a query.

        Returns:
          ("hit", response_dict)              — serve from cache
          ("miss", None, "variant"|"new")     — bypass to KG; label for interaction log
        """
        self._load()
        key = _make_key(topology_sig, arch_type, mode)
        entry = self._entries.get(key)

        if entry and entry.get("pattern_version") == current_pattern_version:
            entry["hit_count"] = entry.get("hit_count", 0) + 1
            entry["last_hit_ts"] = datetime.now(timezone.utc).isoformat()
            self._flush()
            return ("hit", entry["response"])

        # Miss — label as variant or new using multiset Jaccard
        miss_label = self._classify_miss(arch_type, mode, shape_counts)
        return ("miss", None, miss_label)

    def _classify_miss(
        self,
        arch_type: str,
        mode: str,
        shape_counts: Optional[dict],
    ) -> str:
        """Returns "variant" or "new" based on Jaccard vs same-type cached entries."""
        if not shape_counts:
            return "new"
        for entry in self._entries.values():
            if entry.get("arch_type") != arch_type or entry.get("query_mode") != mode:
                continue
            cached_shapes = entry.get("shape_counts", {})
            if multiset_jaccard(shape_counts, cached_shapes) >= VARIANT_THRESHOLD:
                return "variant"
        return "new"

    def write(
        self,
        topology_sig: str,
        arch_type: str,
        mode: str,
        shape_counts: dict,
        response: dict,
        pattern_version: int,
    ) -> None:
        """Write or refresh a cache entry."""
        self._load()
        key = _make_key(topology_sig, arch_type, mode)
        existing = self._entries.get(key, {})
        self._entries[key] = {
            "topology_signature": topology_sig,
            "arch_type": arch_type,
            "query_mode": mode,
            "shape_counts": shape_counts,
            "response": response,
            "pattern_version": pattern_version,
            "hit_count": existing.get("hit_count", 0),
            "last_hit_ts": existing.get("last_hit_ts"),
            "last_confirmed_ts": existing.get("last_confirmed_ts"),
            "created_ts": existing.get("created_ts", datetime.now(timezone.utc).isoformat()),
        }
        self._flush()

    def record_feedback(
        self,
        topology_sig: str,
        arch_type: str,
        mode: str,
        feedback: str,
    ) -> bool:
        """
        Record caller feedback on a cache hit.
          confirmed → update last_confirmed_ts, increment hit_count
          wrong     → evict entry immediately

        Returns True if the entry was found.
        """
        self._load()
        key = _make_key(topology_sig, arch_type, mode)
        if key not in self._entries:
            return False

        if feedback == "wrong":
            del self._entries[key]
            logger.info("Cache evicted (wrong feedback): %s", key)
        elif feedback == "confirmed":
            self._entries[key]["last_confirmed_ts"] = datetime.now(timezone.utc).isoformat()
            self._entries[key]["hit_count"] = self._entries[key].get("hit_count", 0) + 1
        self._flush()
        return True

    def evict_stale(self, current_pattern_version: int) -> int:
        """Remove entries whose pattern_version is older than current. Returns count removed."""
        self._load()
        stale = [k for k, e in self._entries.items()
                 if e.get("pattern_version", -1) != current_pattern_version]
        for k in stale:
            del self._entries[k]
        if stale:
            self._flush()
        return len(stale)

    def pre_warm(
        self,
        instances: list,
        brain: dict,
        infer_fn,
        report_dir: Path = REPORT_DIR,
    ) -> int:
        """
        Pre-warm cache from corpus instances so cache is never cold for known topologies.

        infer_fn: callable (topology_sig, arch_type, brain) → infer result dict
                  Pass _run_infer from ta_brain_query to avoid circular import.

        Reads parsed_nodes from ground_truth.json to compute shape_counts.
        Skips archs already cached with current pattern_version.

        Returns number of entries written.
        """
        pattern_version = brain.get("pattern_version", 0)
        written = 0

        for inst in instances:
            arch_id = inst.get("arch_id", "")
            arch_type = inst.get("arch_type", "")
            topology_sig = inst.get("topology_signature", "")
            mode = "infer"

            # Skip if already cached at current version
            self._load()
            key = _make_key(topology_sig, arch_type, mode)
            if (key in self._entries and
                    self._entries[key].get("pattern_version") == pattern_version):
                continue

            # Extract shape_counts from ground_truth.json
            shape_counts: dict = {}
            gt_path = report_dir / arch_id / "ground_truth.json"
            if gt_path.exists():
                try:
                    meta = json.loads(gt_path.read_text()).get("metadata", {})
                    shape_counts = extract_shape_counts(meta.get("parsed_nodes", {}))
                except Exception:
                    pass

            # Run KG infer and cache the result
            try:
                response = infer_fn(topology_sig, arch_type, brain)
                self.write(topology_sig, arch_type, mode, shape_counts, response, pattern_version)
                written += 1
            except Exception as exc:
                logger.warning("pre_warm failed for %s: %s", arch_id, exc)

        return written

    def stats(self) -> dict:
        """Return cache statistics."""
        self._load()
        entries = list(self._entries.values())
        if not entries:
            return {"total": 0}
        versions = Counter(e.get("pattern_version") for e in entries)
        arch_types = Counter(e.get("arch_type") for e in entries)
        total_hits = sum(e.get("hit_count", 0) for e in entries)
        confirmed = sum(1 for e in entries if e.get("last_confirmed_ts"))
        return {
            "total": len(entries),
            "total_hits": total_hits,
            "confirmed_entries": confirmed,
            "pattern_versions": dict(versions),
            "arch_types": dict(arch_types),
        }

    def reset(self) -> None:
        """Clear all entries (used in tests)."""
        self._entries = {}
        self._loaded = True
        self._flush()


# ── Module-level singleton ────────────────────────────────────────────────────

_singleton: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    global _singleton
    if _singleton is None:
        _singleton = CacheManager(CACHE_PATH)
    return _singleton


def reset_singleton() -> None:
    """Force next get_cache_manager() call to create a fresh instance. Used in tests."""
    global _singleton
    _singleton = None
