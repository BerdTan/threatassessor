"""
TAwatch — AI Risk incident corpus: adapter, DETECT tagger, heatmap builder.

Bridges the AI Risk Explorer Threat Watch corpus (real-world AI-enabled
operations) with TA's DETECT rule taxonomy and TAbrain.

Data file: report/brain/tawatch_incidents.jsonl  (one JSON object per line)
Populated via: scripts/tawatch/export_devtools.js  (browser DevTools)

Incident schema (Threat Watch fields):
  id              str   e.g. "op#113"
  date            str   e.g. "2025-11-01"
  title           str
  tactics         list[str]  MITRE ATT&CK phase names
  capabilities    list[str]  AI capability labels
  model           str   model family (GPT, Claude, Gemini …)
  model_open      bool  open vs closed weights
  sector          str
  actor_type      str   State-sponsored | Cybercriminal | Hacktivist | Commercial | Individual | Unknown
  origin          str   country name or "Unknown"
  sophistication  float composite score
  harm_type       list[str]  Financial | Personal data | System & credentials | Destruction & disruption
  description     str
  source_url      str
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
INCIDENTS_PATH = ROOT / "report" / "brain" / "tawatch_incidents.jsonl"

# ── Domain → tactic / capability mappings ─────────────────────────────────────

_TACTIC_TO_DOMAINS: Dict[str, List[str]] = {
    "Reconnaissance":       ["EXF", "MCP"],
    "Resource Development": ["RES", "INJ"],
    "Initial Access":       ["INJ", "SCT"],
    "Execution":            ["AGT", "MCP"],
    "Persistence":          ["PER"],
    "Privilege Escalation": ["SEC"],
    "Stealth":              ["SCT", "QC"],
    "Defense Impairment":   ["QC"],
    "Credential Access":    ["SEC"],
    "Discovery":            ["EXF", "ABU"],
    "Lateral Movement":     ["AGT"],
    "Collection":           ["EXF"],
    "Command and Control":  ["MCP", "AGT"],
    "Exfiltration":         ["EXF"],
    "Impact":               ["ABU"],
}

_CAPABILITY_TO_DOMAINS: Dict[str, List[str]] = {
    "Reconnaissance":                     ["EXF", "MCP"],
    "Artifact Development":               ["RES", "INJ"],
    "Social Engineering":                 ["INJ", "ABU"],
    "Intrusion Evasion & Persistence":    ["SCT", "PER", "QC"],
    "Attack Orchestration":               ["AGT", "MCP"],
    "Multi-agent dynamics":               ["AGT"],
    "Reward hacking":                     ["ABU", "QC"],
    "Deception":                          ["QC", "INJ"],
    "Situational Awareness":              ["ABU", "EXF"],
    "Lawlessness":                        ["ABU", "SEC"],
    "Persuasiveness":                     ["INJ"],
    "Design and Sequencing":              ["AGT", "RES"],
    "Innovation and Knowledge":           ["RES"],
    "AI R&D":                             ["RES", "AGT"],
}

# confidence: 3=high (tactic+capability agree), 2=medium (one source), 1=low (sector/actor only)
_CONFIDENCE_HIGH   = "high"
_CONFIDENCE_MEDIUM = "medium"
_CONFIDENCE_LOW    = "low"


# ── Incident adapter ──────────────────────────────────────────────────────────

class IncidentAdapter:
    """Maps a Threat Watch incident dict → set of matched DETECT domain codes + confidence."""

    def adapt(self, incident: Dict[str, Any]) -> Dict[str, str]:
        """
        Returns {domain_code: confidence} for all domains that match the incident.
        e.g. {"EXF": "high", "MCP": "medium", "INJ": "low"}
        """
        tactic_domains: Dict[str, int] = {}   # domain → hit count
        cap_domains:    Dict[str, int] = {}

        for t in incident.get("tactics", []):
            for d in _TACTIC_TO_DOMAINS.get(t, []):
                tactic_domains[d] = tactic_domains.get(d, 0) + 1

        for c in incident.get("capabilities", []):
            for d in _CAPABILITY_TO_DOMAINS.get(c, []):
                cap_domains[d] = cap_domains.get(d, 0) + 1

        all_domains = set(tactic_domains) | set(cap_domains)
        result: Dict[str, str] = {}
        for d in all_domains:
            in_tactic = d in tactic_domains
            in_cap    = d in cap_domains
            if in_tactic and in_cap:
                result[d] = _CONFIDENCE_HIGH
            else:
                result[d] = _CONFIDENCE_MEDIUM

        # low-confidence: actor type signals for AGT
        if incident.get("actor_type") in ("State-sponsored", "Cybercriminal") and "AGT" not in result:
            result["AGT"] = _CONFIDENCE_LOW

        return result

    def is_agentic(self, incident: Dict[str, Any]) -> bool:
        caps = incident.get("capabilities", [])
        return any(c in ("Attack Orchestration", "Multi-agent dynamics", "AI R&D") for c in caps)

    def model_family(self, incident: Dict[str, Any]) -> str:
        m = (incident.get("model") or "").lower()
        for fam in ("gpt", "claude", "gemini", "deepseek", "kimi", "grok", "qwen", "llama", "glm", "minimax"):
            if fam in m:
                return fam
        return "other"


# ── TAwatch core ──────────────────────────────────────────────────────────────

class TAwatch:
    """
    Loads the incident corpus, tags each incident against TA's DETECT domain taxonomy,
    and exposes query methods for heatmap, coverage stats, and brain enrichment.
    """

    def __init__(self, incidents_path: Optional[Path] = None):
        self._path = incidents_path or INCIDENTS_PATH
        self._adapter = IncidentAdapter()
        self._incidents: List[Dict[str, Any]] = []
        self._coverage: Dict[str, Dict[str, str]] = {}   # incident_id → {domain: confidence}
        self._rule_index: Dict[str, List[str]] = {}       # domain → [incident_ids]
        self._loaded = False

    # ── loading ───────────────────────────────────────────────────────────────

    def load(self) -> "TAwatch":
        if self._loaded:
            return self
        incidents: List[Dict[str, Any]] = []
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    incidents.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("tawatch: bad JSON line: %s", exc)
        self._incidents = incidents
        self._build_index()
        self._loaded = True
        logger.info("tawatch: loaded %d incidents", len(incidents))
        return self

    def _build_index(self) -> None:
        self._coverage = {}
        self._rule_index = {}
        for inc in self._incidents:
            iid = inc.get("id", "")
            domains = self._adapter.adapt(inc)
            self._coverage[iid] = domains
            for domain, conf in domains.items():
                self._rule_index.setdefault(domain, [])
                if iid not in self._rule_index[domain]:
                    self._rule_index[domain].append(iid)

    def reload(self) -> "TAwatch":
        self._loaded = False
        return self.load()

    # ── corpus stats ──────────────────────────────────────────────────────────

    @property
    def incident_count(self) -> int:
        return len(self._incidents)

    @property
    def corpus_loaded(self) -> bool:
        return self._loaded and len(self._incidents) > 0

    def status(self) -> Dict[str, Any]:
        self.load()
        return {
            "incident_count":   self.incident_count,
            "corpus_loaded":    self.corpus_loaded,
            "data_path":        str(self._path),
            "domains_covered":  sorted(self._rule_index.keys()),
            "domain_counts":    {d: len(ids) for d, ids in self._rule_index.items()},
        }

    # ── tagging ───────────────────────────────────────────────────────────────

    def tag_incident(self, incident: Dict[str, Any]) -> Dict[str, str]:
        """Return domain → confidence for one incident (no load needed)."""
        return self._adapter.adapt(incident)

    # ── heatmap ───────────────────────────────────────────────────────────────

    def build_heatmap(
        self,
        sector_filter: Optional[str] = None,
        actor_filter:  Optional[str] = None,
        model_filter:  Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return the coverage matrix:
          {
            "incidents": [...],      # filtered incident list (summary)
            "domains":   [...],      # ordered domain list
            "matrix":    {           # incident_id → {domain: confidence|"none"}
                "op#113": {"EXF": "high", "MCP": "medium", "INJ": "none", ...},
                ...
            },
            "domain_stats": {        # per-domain aggregate
                "EXF": {"count": 89, "high_pct": 0.72},
                ...
            },
          }
        """
        self.load()
        DOMAINS = ["QC", "INJ", "EXF", "SCT", "MCP", "RES", "ABU", "SEC", "AGT", "PER"]

        incidents = self._filter(sector_filter, actor_filter, model_filter)
        filtered_ids = {inc["id"] for inc in incidents}

        matrix: Dict[str, Dict[str, str]] = {}
        for inc in incidents:
            iid = inc["id"]
            dom = self._coverage.get(iid, {})
            matrix[iid] = {d: dom.get(d, "none") for d in DOMAINS}

        domain_stats: Dict[str, Dict[str, Any]] = {}
        for d in DOMAINS:
            matched = [iid for iid in filtered_ids if self._coverage.get(iid, {}).get(d)]
            high    = [iid for iid in matched if self._coverage.get(iid, {}).get(d) == _CONFIDENCE_HIGH]
            domain_stats[d] = {
                "count":    len(matched),
                "high_pct": round(len(high) / len(matched), 3) if matched else 0.0,
            }

        return {
            "incidents":    [self._incident_summary(i) for i in incidents],
            "domains":      DOMAINS,
            "matrix":       matrix,
            "domain_stats": domain_stats,
        }

    # ── coverage queries ──────────────────────────────────────────────────────

    def get_domain_incidents(
        self,
        domain: str,
        min_confidence: str = "low",
    ) -> List[Dict[str, Any]]:
        """Incidents that match a given DETECT domain at or above min_confidence."""
        self.load()
        order = {_CONFIDENCE_HIGH: 3, _CONFIDENCE_MEDIUM: 2, _CONFIDENCE_LOW: 1}
        min_level = order.get(min_confidence, 1)
        result = []
        for inc in self._incidents:
            iid = inc.get("id", "")
            conf = self._coverage.get(iid, {}).get(domain)
            if conf and order.get(conf, 0) >= min_level:
                result.append({**self._incident_summary(inc), "confidence": conf})
        result.sort(key=lambda x: x.get("sophistication", 0), reverse=True)
        return result

    def coverage_summary(self) -> List[Dict[str, Any]]:
        """Per-domain coverage stats for the CISO coverage view."""
        self.load()
        DOMAINS = ["QC", "INJ", "EXF", "SCT", "MCP", "RES", "ABU", "SEC", "AGT", "PER"]
        rows = []
        for d in DOMAINS:
            incidents = self.get_domain_incidents(d, min_confidence="low")
            high   = [i for i in incidents if i["confidence"] == _CONFIDENCE_HIGH]
            medium = [i for i in incidents if i["confidence"] == _CONFIDENCE_MEDIUM]
            sophs  = [i["sophistication"] for i in incidents if i.get("sophistication")]
            rows.append({
                "domain":               d,
                "total_incidents":      len(incidents),
                "high_confidence":      len(high),
                "medium_confidence":    len(medium),
                "mean_sophistication":  round(sum(sophs) / len(sophs), 2) if sophs else None,
                "top_sectors":          _top_n([i["sector"] for i in incidents if i.get("sector")], 3),
                "top_models":           _top_n([i["model"] for i in incidents if i.get("model")], 3),
            })
        return rows

    # ── brain enrichment ──────────────────────────────────────────────────────

    def match_architecture(
        self,
        sector: Optional[str] = None,
        model_family: Optional[str] = None,
        is_agentic: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Find real incidents that match an architecture profile.
        Used by ta_exporter and brain query surface.
        """
        self.load()
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for inc in self._incidents:
            score = 0
            if sector and inc.get("sector", "").lower() == sector.lower():
                score += 3
            if model_family:
                fam = self._adapter.model_family(inc)
                if fam == model_family.lower():
                    score += 2
            if is_agentic and self._adapter.is_agentic(inc):
                score += 2
            if score > 0:
                scored.append((score, inc))
        scored.sort(key=lambda x: (-x[0], -(x[1].get("sophistication") or 0)))
        return [
            {**self._incident_summary(inc), "match_score": s}
            for s, inc in scored[:10]
        ]

    def sector_risk_profile(self, sector: str) -> Dict[str, Any]:
        """Real-world attack profile for a given sector."""
        self.load()
        incs = [i for i in self._incidents if i.get("sector", "").lower() == sector.lower()]
        if not incs:
            return {"sector": sector, "incident_count": 0}
        sophs  = [i["sophistication"] for i in incs if i.get("sophistication")]
        tactics: List[str] = []
        caps:    List[str] = []
        models:  List[str] = []
        for i in incs:
            tactics.extend(i.get("tactics", []))
            caps.extend(i.get("capabilities", []))
            if i.get("model"):
                models.append(self._adapter.model_family(i))
        return {
            "sector":               sector,
            "incident_count":       len(incs),
            "mean_sophistication":  round(sum(sophs) / len(sophs), 2) if sophs else None,
            "top_tactics":          _top_n(tactics, 5),
            "top_capabilities":     _top_n(caps, 5),
            "top_models":           _top_n(models, 3),
        }

    def model_risk_profile(self, model_family: str) -> Dict[str, Any]:
        """Real-world operation profile for a given model family."""
        self.load()
        incs = [
            i for i in self._incidents
            if self._adapter.model_family(i) == model_family.lower()
        ]
        if not incs:
            return {"model_family": model_family, "incident_count": 0}
        sophs    = [i["sophistication"] for i in incs if i.get("sophistication")]
        tactics: List[str] = []
        sectors: List[str] = []
        for i in incs:
            tactics.extend(i.get("tactics", []))
            if i.get("sector"):
                sectors.append(i["sector"])
        return {
            "model_family":         model_family,
            "incident_count":       len(incs),
            "mean_sophistication":  round(sum(sophs) / len(sophs), 2) if sophs else None,
            "top_tactics":          _top_n(tactics, 5),
            "top_sectors":          _top_n(sectors, 3),
        }

    # ── helpers ───────────────────────────────────────────────────────────────

    def _filter(
        self,
        sector: Optional[str],
        actor:  Optional[str],
        model:  Optional[str],
    ) -> List[Dict[str, Any]]:
        result = self._incidents
        if sector:
            result = [i for i in result if i.get("sector", "").lower() == sector.lower()]
        if actor:
            result = [i for i in result if i.get("actor_type", "").lower() == actor.lower()]
        if model:
            result = [i for i in result if self._adapter.model_family(i) == model.lower()]
        return result

    def _incident_summary(self, inc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id":             inc.get("id", ""),
            "date":           inc.get("date", ""),
            "title":          inc.get("title", ""),
            "sector":         inc.get("sector", ""),
            "actor_type":     inc.get("actor_type", ""),
            "origin":         inc.get("origin", ""),
            "model":          inc.get("model", ""),
            "sophistication": inc.get("sophistication"),
            "tactics":        inc.get("tactics", []),
            "capabilities":   inc.get("capabilities", []),
            "harm_type":      inc.get("harm_type", []),
            "source_url":     inc.get("source_url", ""),
        }


def _top_n(items: List[str], n: int) -> List[str]:
    from collections import Counter
    return [k for k, _ in Counter(items).most_common(n)]


# ── module-level singleton ────────────────────────────────────────────────────

_singleton: Optional[TAwatch] = None


def get_tawatch() -> TAwatch:
    global _singleton
    if _singleton is None:
        _singleton = TAwatch()
    return _singleton.load()
