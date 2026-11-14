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
INCIDENTS_PATH   = ROOT / "report" / "brain" / "tawatch_incidents.jsonl"
DETECT_RULES_PATH = ROOT / "policies" / "soc_detection_rules.yaml"


def _load_rule_meta() -> Dict[str, Dict[str, str]]:
    """Return {rule_id: {name, description, severity, kill_chain_stage}} from YAML.

    Lightweight line-by-line scan — no full YAML parse dep.
    """
    result: Dict[str, Dict[str, str]] = {}
    current: Dict[str, str] = {}
    desc_lines: List[str] = []
    in_desc = False
    try:
        for raw in DETECT_RULES_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("- id: DETECT-"):
                if current.get("id"):
                    if desc_lines:
                        current["description"] = " ".join(desc_lines).strip()
                    result[current["id"]] = current
                current = {"id": line[len("- id: "):].strip()}
                desc_lines = []
                in_desc = False
            elif current.get("id"):
                if line.startswith("name: "):
                    current["name"] = line[len("name: "):].strip()
                    in_desc = False
                elif line.startswith("severity: "):
                    current["severity"] = line[len("severity: "):].strip()
                    in_desc = False
                elif line.startswith("kill_chain_stage: "):
                    current["kill_chain_stage"] = line[len("kill_chain_stage: "):].strip()
                    in_desc = False
                elif line.startswith("description: >") or line.startswith("description: |"):
                    in_desc = True
                    desc_lines = []
                elif line.startswith("description: "):
                    current["description"] = line[len("description: "):].strip()
                    in_desc = False
                elif in_desc:
                    if line and not line.startswith("-") and not line.endswith(":"):
                        desc_lines.append(line)
                    elif line.startswith("- ") or (line and line[0].isalpha() and line.endswith(":")):
                        in_desc = False
        if current.get("id"):
            if desc_lines:
                current["description"] = " ".join(desc_lines).strip()
            result[current["id"]] = current
    except OSError:
        logger.warning("tawatch: soc_detection_rules.yaml not found — rule meta unavailable")
    return result


def _load_rule_ids() -> Dict[str, List[str]]:
    """Return {domain: [rule_id, ...]} loaded from soc_detection_rules.yaml.

    Uses a lightweight line scan — no full YAML parse dependency.
    Rule IDs are lines matching '  - id: DETECT-<DOMAIN>-NNN'.
    Returns domain-ordered dict; falls back to hardcoded 10 domains if file missing.
    """
    domain_order = ["QC", "INJ", "EXF", "SCT", "MCP", "RES", "ABU", "SEC", "AGT", "PER"]
    result: Dict[str, List[str]] = {d: [] for d in domain_order}
    try:
        for line in DETECT_RULES_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("- id: DETECT-"):
                rule_id = line[len("- id: "):].strip()
                parts = rule_id.split("-")
                if len(parts) >= 3:
                    domain = parts[1]
                    result.setdefault(domain, [])
                    if rule_id not in result[domain]:
                        result[domain].append(rule_id)
    except OSError:
        logger.warning("tawatch: soc_detection_rules.yaml not found — rule-level heatmap unavailable")
    return result

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
    """
    Maps a Threat Watch incident dict → set of matched DETECT domain codes + confidence.

    Real Supabase schema fields used:
      mitre_tactics   list[str]  MITRE ATT&CK phase names
      taxonomy_cats   list[str]  AI capability labels (Social Engineering, Reconnaissance …)
      risk_cats       list[str]  Cyber Offense | Manipulation | Biological Risk | Loss of Control
      models_involved list[str]  model families (GPT, Claude, Gemini …)
      actor_type      list[str]  Cybercriminal | State-sponsored | Hacktivist …
      targeted_sector list[str]  sector labels
      actors_origin   list[str]  country names
      model_availability str     Closed-weight | Open-weight
      headline        str        incident title
      reporting_date  str        YYYY-MM-DD
      link            str        source URL
      sophistication  float      composite score (joined from incident_sophistication_scores)
    """

    def adapt(self, incident: Dict[str, Any]) -> Dict[str, str]:
        """Returns {domain_code: confidence} for all domains that match the incident."""
        tactic_domains: Dict[str, int] = {}
        cap_domains:    Dict[str, int] = {}

        for t in _to_list(incident.get("mitre_tactics")):
            for d in _TACTIC_TO_DOMAINS.get(t, []):
                tactic_domains[d] = tactic_domains.get(d, 0) + 1

        for c in _to_list(incident.get("taxonomy_cats")):
            for d in _CAPABILITY_TO_DOMAINS.get(c, []):
                cap_domains[d] = cap_domains.get(d, 0) + 1

        # risk_cats as secondary domain signal
        risk_map = {
            "Cyber Offense":  ["EXF", "MCP", "INJ"],
            "Manipulation":   ["INJ", "ABU"],
            "Loss of Control":["AGT", "QC"],
            "Biological Risk":[],
        }
        for rc in _to_list(incident.get("risk_cats")):
            for d in risk_map.get(rc, []):
                if d not in tactic_domains and d not in cap_domains:
                    cap_domains[d] = cap_domains.get(d, 0) + 1

        all_domains = set(tactic_domains) | set(cap_domains)
        result: Dict[str, str] = {}
        for d in all_domains:
            if d in tactic_domains and d in cap_domains:
                result[d] = _CONFIDENCE_HIGH
            else:
                result[d] = _CONFIDENCE_MEDIUM

        actor_types = _to_list(incident.get("actor_type"))
        if any(a in ("State-sponsored", "Cybercriminal") for a in actor_types) and "AGT" not in result:
            result["AGT"] = _CONFIDENCE_LOW

        return result

    def is_agentic(self, incident: Dict[str, Any]) -> bool:
        cats = _to_list(incident.get("taxonomy_cats"))
        return any(c in ("Attack Orchestration", "Multi-agent dynamics", "AI R&D") for c in cats)

    def model_family(self, incident: Dict[str, Any]) -> str:
        models = _to_list(incident.get("models_involved"))
        combined = " ".join(models).lower()
        for fam in ("gpt", "claude", "gemini", "deepseek", "kimi", "grok", "qwen", "llama", "glm", "minimax"):
            if fam in combined:
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
        """Return the rule-level coverage matrix.

        {
          "incidents":    [...],       # filtered incident list (summary)
          "rules":        [...],       # ordered rule IDs e.g. ["DETECT-QC-001", ...]
          "domains":      [...],       # ordered domain codes (for column grouping)
          "rule_domain":  {...},       # rule_id → domain code
          "matrix":       {            # incident_id → {rule_id: confidence|"none"}
              "op#113": {"DETECT-EXF-001": "high", "DETECT-MCP-001": "medium", ...},
          },
          "rule_stats":   {            # rule_id → {count, high_pct}
              "DETECT-EXF-001": {"count": 89, "high_pct": 0.72},
          },
        }

        Each incident's domain-level confidence is propagated to all rules within that
        domain (e.g. incident matched INJ at high → all DETECT-INJ-* at high).
        """
        self.load()
        rule_map = _load_rule_ids()   # {domain: [rule_id, ...]}
        domain_order = ["QC", "INJ", "EXF", "SCT", "MCP", "RES", "ABU", "SEC", "AGT", "PER"]

        # flat ordered rule list; unknown domains appended at end
        rules: List[str] = []
        rule_domain: Dict[str, str] = {}
        seen_domains = set(rule_map.keys())
        for d in domain_order:
            for rid in rule_map.get(d, []):
                rules.append(rid)
                rule_domain[rid] = d
        for d in sorted(seen_domains - set(domain_order)):
            for rid in rule_map[d]:
                rules.append(rid)
                rule_domain[rid] = d

        incidents = self._filter(sector_filter, actor_filter, model_filter)
        filtered_ids = {inc["id"] for inc in incidents}

        matrix: Dict[str, Dict[str, str]] = {}
        for inc in incidents:
            iid = inc["id"]
            dom_conf = self._coverage.get(iid, {})
            row: Dict[str, str] = {}
            for rid in rules:
                domain = rule_domain[rid]
                row[rid] = dom_conf.get(domain, "none")
            matrix[iid] = row

        rule_stats: Dict[str, Dict[str, Any]] = {}
        for rid in rules:
            domain = rule_domain[rid]
            matched = [iid for iid in filtered_ids if self._coverage.get(iid, {}).get(domain)]
            high    = [iid for iid in matched if self._coverage.get(iid, {}).get(domain) == _CONFIDENCE_HIGH]
            rule_stats[rid] = {
                "count":    len(matched),
                "high_pct": round(len(high) / len(matched), 3) if matched else 0.0,
            }

        return {
            "incidents":   [self._incident_summary(i) for i in incidents],
            "rules":       rules,
            "domains":     [d for d in domain_order if d in seen_domains],
            "rule_domain": rule_domain,
            "matrix":      matrix,
            "rule_stats":  rule_stats,
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
                "top_capabilities":     _top_n([c for i in incidents for c in i.get("capabilities", [])], 3),
            })
        return rows

    # ── brain enrichment ──────────────────────────────────────────────────────

    def match_architecture(
        self,
        sector: Optional[str] = None,
        model_family: Optional[str] = None,
        is_agentic: bool = False,
    ) -> List[Dict[str, Any]]:
        """Find real incidents that match an architecture profile."""
        self.load()
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for inc in self._incidents:
            score = 0
            if sector:
                sec_str = " ".join(_to_list(inc.get("targeted_sector"))).lower()
                if sector.lower() in sec_str:
                    score += 3
            if model_family:
                if self._adapter.model_family(inc) == model_family.lower():
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
        incs = [i for i in self._incidents if sector.lower() in " ".join(_to_list(i.get("targeted_sector"))).lower()]
        if not incs:
            return {"sector": sector, "incident_count": 0}
        sophs: List[float] = [i["sophistication"] for i in incs if i.get("sophistication")]
        tactics: List[str] = []
        caps:    List[str] = []
        models:  List[str] = []
        for i in incs:
            tactics.extend(_to_list(i.get("mitre_tactics")))
            caps.extend(_to_list(i.get("taxonomy_cats")))
            models.append(self._adapter.model_family(i))
        return {
            "sector":              sector,
            "incident_count":      len(incs),
            "mean_sophistication": round(sum(sophs) / len(sophs), 2) if sophs else None,
            "top_tactics":         _top_n(tactics, 5),
            "top_capabilities":    _top_n(caps, 5),
            "top_models":          _top_n(models, 3),
        }

    def model_risk_profile(self, model_family: str) -> Dict[str, Any]:
        """Real-world operation profile for a given model family."""
        self.load()
        incs = [i for i in self._incidents if self._adapter.model_family(i) == model_family.lower()]
        if not incs:
            return {"model_family": model_family, "incident_count": 0}
        sophs: List[float] = [i["sophistication"] for i in incs if i.get("sophistication")]
        tactics: List[str] = []
        sectors: List[str] = []
        for i in incs:
            tactics.extend(_to_list(i.get("mitre_tactics")))
            sectors.extend(_to_list(i.get("targeted_sector")))
        return {
            "model_family":        model_family,
            "incident_count":      len(incs),
            "mean_sophistication": round(sum(sophs) / len(sophs), 2) if sophs else None,
            "top_tactics":         _top_n(tactics, 5),
            "top_sectors":         _top_n(sectors, 3),
        }

    # ── helpers ───────────────────────────────────────────────────────────────

    # ── CISO brief ────────────────────────────────────────────────────────────

    def ciso_brief(self) -> Dict[str, Any]:
        """Return per-rule CISO briefing cards + cross-rule top-10 priority list.

        Each card has: rule metadata (id, name, description, severity,
        kill_chain_stage), incident stats, top-3 incidents by sophistication,
        and a priority_score used to rank the top-10 list.

        priority_score = incident_count × high_pct × mean_sophistication
        (a rule with many high-confidence incidents on sophisticated operations
        ranks highest).
        """
        self.load()
        rule_meta   = _load_rule_meta()   # {rule_id: {name, description, severity, kill_chain_stage}}
        rule_map    = _load_rule_ids()    # {domain: [rule_id]}
        order       = {_CONFIDENCE_HIGH: 3, _CONFIDENCE_MEDIUM: 2, _CONFIDENCE_LOW: 1}

        # flat rule list in domain order
        domain_order = ["QC", "INJ", "EXF", "SCT", "MCP", "RES", "ABU", "SEC", "AGT", "PER"]
        all_rules: List[str] = []
        for d in domain_order:
            all_rules.extend(rule_map.get(d, []))

        cards = []
        for rid in all_rules:
            domain = rid.split("-")[1] if rid.count("-") >= 2 else "?"
            # incidents matching this domain at any confidence
            dom_incidents = []
            for inc in self._incidents:
                iid = inc.get("id", "")
                conf = self._coverage.get(iid, {}).get(domain)
                if conf:
                    dom_incidents.append((inc, conf))

            meta   = rule_meta.get(rid, {})
            total  = len(dom_incidents)
            high   = sum(1 for _, c in dom_incidents if c == _CONFIDENCE_HIGH)
            med    = sum(1 for _, c in dom_incidents if c == _CONFIDENCE_MEDIUM)
            sophs  = [i.get("sophistication") or 0 for i, _ in dom_incidents]
            mean_soph = round(sum(sophs) / len(sophs), 2) if sophs else 0.0
            high_pct  = round(high / total, 3) if total else 0.0
            # weighted confidence blend so domains with only medium-conf still rank
            conf_weight = round((high + med * 0.5) / total, 3) if total else 0.0
            sev_weight = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(meta.get("severity", ""), 1)
            priority_score = round(sev_weight * total * conf_weight * mean_soph, 1)

            # top-3 by sophistication
            top3 = sorted(dom_incidents, key=lambda x: x[0].get("sophistication") or 0, reverse=True)[:3]
            top3_summaries = []
            for inc, conf in top3:
                s = self._incident_summary(inc)
                s["confidence"] = conf
                top3_summaries.append(s)

            top_sectors = _top_n(
                [", ".join(_to_list(i.get("targeted_sector"))) for i, _ in dom_incidents if i.get("targeted_sector")], 3
            )
            top_risk_cats = _top_n(
                [rc for i, _ in dom_incidents for rc in _to_list(i.get("risk_cats"))], 3
            )
            cards.append({
                "rule_id":        rid,
                "domain":         domain,
                "name":           meta.get("name", ""),
                "description":    meta.get("description", ""),
                "severity":       meta.get("severity", ""),
                "kill_chain":     meta.get("kill_chain_stage", ""),
                "incident_count": total,
                "high_pct":       high_pct,
                "mean_soph":      mean_soph,
                "priority_score": priority_score,
                "top_sectors":    top_sectors,
                "top_risk_cats":  top_risk_cats,
                "top_incidents":  top3_summaries,
            })

        # top-10: best rule per domain (by priority_score), then rank across domains
        seen_domains: set = set()
        top10 = []
        for card in sorted(cards, key=lambda c: c["priority_score"], reverse=True):
            if card["domain"] not in seen_domains:
                seen_domains.add(card["domain"])
                top10.append(card)
            if len(top10) == 10:
                break

        return {
            "cards":        cards,
            "top10":        top10,
            "total_rules":  len(all_rules),
            "total_incidents": len(self._incidents),
        }

    def _filter(
        self,
        sector: Optional[str],
        actor:  Optional[str],
        model:  Optional[str],
    ) -> List[Dict[str, Any]]:
        result = self._incidents
        if sector:
            result = [i for i in result if sector.lower() in " ".join(_to_list(i.get("targeted_sector"))).lower()]
        if actor:
            result = [i for i in result if actor.lower() in " ".join(_to_list(i.get("actor_type"))).lower()]
        if model:
            result = [i for i in result if self._adapter.model_family(i) == model.lower()]
        return result

    def _incident_summary(self, inc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id":             inc.get("id", ""),
            "date":           inc.get("reporting_date", ""),
            "title":          inc.get("headline", ""),
            "sector":         ", ".join(_to_list(inc.get("targeted_sector"))),
            "actor_type":     ", ".join(_to_list(inc.get("actor_type"))),
            "origin":         ", ".join(_to_list(inc.get("actors_origin"))),
            "model":          ", ".join(_to_list(inc.get("models_involved"))),
            "sophistication": inc.get("sophistication"),
            "tactics":        _to_list(inc.get("mitre_tactics")),
            "capabilities":   _to_list(inc.get("taxonomy_cats")),
            "risk_cats":      _to_list(inc.get("risk_cats")),
            "harm_type":      _to_list(inc.get("disarm_stage")),
            "source_url":     inc.get("link", ""),
        }


def _to_list(v: Any) -> List[str]:
    """Normalise a field that may be a list, comma-string, or None → list[str]."""
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    return [str(v)]


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
