"""
GroupCampaignMatcher — offline STIX-backed TTP overlap scorer.

Loads enterprise-attack.json once, builds a compact group index,
and caches it as a pickle alongside the source file. No LLM calls.

Usage:
    from chatbot.modules.group_campaign_matcher import get_matcher, ActorMatch
    matcher = get_matcher()
    matches: list[ActorMatch] = matcher.match(arch_techniques)
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_DEFAULT_STIX = Path(__file__).parent.parent / "data" / "enterprise-attack.json"
_PKL_SUFFIX = ".gcm.pkl"  # distinct suffix — avoids collision with other pkl users

# Module-level singleton
_instance: Optional["GroupCampaignMatcher"] = None


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ActorMatch:
    group_id: str           # e.g. "G0007"
    name: str               # e.g. "APT28"
    aliases: list[str]
    overlap_pct: float      # 0.0–1.0: matched / arch_technique_count
    matched_techniques: list[str]   # T-IDs in common
    tools: list[str]        # up to 5 known tools from STIX

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "aliases": self.aliases,
            "overlap_pct": self.overlap_pct,
            "matched_techniques": self.matched_techniques,
            "tools": self.tools,
        }


@dataclass
class _GroupEntry:
    group_id: str
    name: str
    aliases: list[str]
    techniques: set[str] = field(default_factory=set)
    tools: list[str] = field(default_factory=list)


# ── Matcher ───────────────────────────────────────────────────────────────────

class GroupCampaignMatcher:
    """
    Match an arch's technique set against MITRE ATT&CK threat actor groups.
    Returns top-N ActorMatch objects ranked by overlap_pct (descending).
    """

    def __init__(self, stix_path: Path = _DEFAULT_STIX) -> None:
        self._groups: dict[str, _GroupEntry] = {}
        self._load(stix_path)
        log.debug("GroupCampaignMatcher: loaded %d groups", len(self._groups))

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self, stix_path: Path) -> None:
        pkl = stix_path.with_suffix(_PKL_SUFFIX)
        if (
            pkl.exists()
            and pkl.stat().st_mtime >= stix_path.stat().st_mtime
        ):
            try:
                with open(pkl, "rb") as f:
                    self._groups = pickle.load(f)
                return
            except Exception:
                log.warning("GroupCampaignMatcher: pkl load failed, rebuilding")
        self._build_index(stix_path, pkl)

    def _build_index(self, stix_path: Path, pkl: Path) -> None:
        log.info("GroupCampaignMatcher: building STIX index from %s", stix_path)
        with open(stix_path) as f:
            data = json.load(f)
        objects = data["objects"]

        # stix-id → ATT&CK T-ID
        technique_map: dict[str, str] = {}
        for o in objects:
            if o["type"] == "attack-pattern":
                for ext in o.get("external_references", []):
                    if ext.get("source_name") == "mitre-attack":
                        tid = ext.get("external_id", "")
                        if tid.startswith("T"):
                            technique_map[o["id"]] = tid
                            break

        # stix-id → tool name
        tool_map: dict[str, str] = {}
        for o in objects:
            if o["type"] == "tool":
                tool_map[o["id"]] = o.get("name", "")

        # stix-id → _GroupEntry  (keyed by STIX id during build, re-keyed after)
        group_by_stix: dict[str, _GroupEntry] = {}
        for o in objects:
            if o["type"] == "intrusion-set":
                gid = ""
                for ext in o.get("external_references", []):
                    if ext.get("source_name") == "mitre-attack":
                        gid = ext.get("external_id", "")
                        break
                if not gid:
                    continue
                group_by_stix[o["id"]] = _GroupEntry(
                    group_id=gid,
                    name=o.get("name", ""),
                    aliases=o.get("aliases", []),
                )

        # campaign stix-id → group stix-id  (via attributed-to)
        campaign_to_group: dict[str, str] = {}
        for o in objects:
            if (
                o["type"] == "relationship"
                and o.get("relationship_type") == "attributed-to"
            ):
                src, tgt = o.get("source_ref", ""), o.get("target_ref", "")
                if src.startswith("campaign--") and tgt in group_by_stix:
                    campaign_to_group[src] = tgt

        # wire techniques + tools via `uses` relationships
        for o in objects:
            if o["type"] != "relationship" or o.get("relationship_type") != "uses":
                continue
            src = o.get("source_ref", "")
            tgt = o.get("target_ref", "")

            # resolve campaign → group
            group_stix_id = campaign_to_group.get(src, src)
            entry = group_by_stix.get(group_stix_id)
            if entry is None:
                continue

            if tgt in technique_map:
                entry.techniques.add(technique_map[tgt])
            elif tgt in tool_map:
                entry.tools.append(tool_map[tgt])

        # re-key by G-number for stable external lookup
        self._groups = {e.group_id: e for e in group_by_stix.values()}

        # persist
        try:
            with open(pkl, "wb") as f:
                pickle.dump(self._groups, f)
            log.debug("GroupCampaignMatcher: cached index at %s", pkl)
        except OSError as exc:
            log.warning("GroupCampaignMatcher: could not write pkl: %s", exc)

    # ── Scoring ───────────────────────────────────────────────────────────────

    def match(
        self,
        arch_techniques: set[str],
        top_n: int = 3,
        min_overlap: float = 0.0,
    ) -> list[ActorMatch]:
        """
        Score every group by TTP overlap against arch_techniques.

        overlap_pct = |group ∩ arch| / |arch|

        Returns top_n matches with overlap_pct >= min_overlap, highest first.
        Returns [] when arch_techniques is empty.
        """
        if not arch_techniques:
            return []

        # Normalise — strip subtechnique suffix for base-only matching fallback
        normalised = {t.split(".")[0] for t in arch_techniques} | arch_techniques

        results: list[ActorMatch] = []
        for entry in self._groups.values():
            matched = entry.techniques & normalised
            if not matched:
                continue
            overlap = len(matched) / len(arch_techniques)
            if overlap < min_overlap:
                continue
            results.append(
                ActorMatch(
                    group_id=entry.group_id,
                    name=entry.name,
                    aliases=entry.aliases,
                    overlap_pct=round(overlap, 4),
                    matched_techniques=sorted(matched),
                    tools=list(dict.fromkeys(entry.tools))[:5],
                )
            )

        results.sort(key=lambda x: x.overlap_pct, reverse=True)
        return results[:top_n]

    def get_group(self, group_id: str) -> Optional[_GroupEntry]:
        """Return raw entry by G-number, or None."""
        return self._groups.get(group_id)

    @property
    def group_count(self) -> int:
        return len(self._groups)


# ── Singleton factory ─────────────────────────────────────────────────────────

def get_matcher(stix_path: Path = _DEFAULT_STIX) -> GroupCampaignMatcher:
    """Return a process-level singleton GroupCampaignMatcher."""
    global _instance
    if _instance is None:
        _instance = GroupCampaignMatcher(stix_path)
    return _instance
