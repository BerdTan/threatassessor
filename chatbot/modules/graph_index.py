"""
graph_index.py — Structural knowledge graph index over ThreatAssessor report artefacts.

Builds a lightweight in-memory graph from ground_truth.json + critic JSONs
across a workspace. No vector DB, no embeddings, no LLM extraction — pure
Python dicts + sets over already-structured JSON. Relationships are explicit
in the data; this module indexes them, not discovers them.

Graph entities:
  - Architecture   (arch name)
  - AttackPath     (arch + AP id)
  - Node           (arch + node_id, with label, in/out degree, is_hub, is_spof)
  - Technique      (T-ID, cross-arch)
  - Control        (name, cross-arch)
  - CriticVerdict  (arch + role, with score, rating, gaps)

Graph edges (stored as typed adjacency sets):
  Architecture   -HAS_AP->         AttackPath
  Architecture   -HAS_NODE->       Node
  AttackPath     -USES->           Technique
  AttackPath     -HOP_SEQUENCE->   [Node, ...]   (ordered)
  Node           -HAS_TECHNIQUE->  Technique
  Technique      -MITIGATED_BY->   Control
  Control        -COVERS_AP->      AttackPath
  Architecture   -EVALUATED_BY->   CriticVerdict
  Architecture   -MISSING->        Control
  Architecture   -HAS->            Control       (present)

Usage:
    from chatbot.modules.graph_index import ThreatGraph
    g = ThreatGraph.build(workspace_arch_names, report_dir)
    result = g.query("which architectures have T1078?")
    result = g.query("critical paths in 24_eservices_serverless")
    result = g.query("missing controls for 24_eservices_serverless")
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AP:
    id: str
    arch: str
    entry: str
    target: str
    path: list[str]
    criticality_tier: str
    criticality: float
    techniques: list[str]


@dataclass
class GraphNode:
    id: str
    arch: str
    label: str
    in_degree: int
    out_degree: int
    is_hub: bool       # out_degree >= 3 and not pure infra
    is_spof: bool
    techniques: list[str]


@dataclass
class CriticVerdict:
    arch: str
    role: str
    score: int
    rating: str
    gaps: list[str]      # exploitable_gaps or coverage_gaps T-IDs
    top_findings: list[str]


@dataclass
class ThreatGraph:
    # Primary indices
    archs: list[str] = field(default_factory=list)
    attack_paths: dict[str, AP] = field(default_factory=dict)          # "arch::AP-1" -> AP
    nodes: dict[str, GraphNode] = field(default_factory=dict)          # "arch::node_id" -> GraphNode
    verdicts: dict[str, CriticVerdict] = field(default_factory=dict)   # "arch::role" -> CriticVerdict

    # Cross-arch inverted indices
    technique_to_archs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    technique_to_aps: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))    # T-ID -> {"arch::AP-1"}
    technique_to_controls: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))  # T-ID -> [control]
    control_to_archs_missing: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    control_to_archs_present: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    arch_controls_missing: dict[str, list[str]] = field(default_factory=dict)
    arch_controls_present: dict[str, list[str]] = field(default_factory=dict)
    arch_risk_score: dict[str, float] = field(default_factory=dict)
    arch_defensibility: dict[str, float] = field(default_factory=dict)
    hub_nodes: dict[str, list[GraphNode]] = field(default_factory=dict)  # arch -> [hub nodes]
    spof_nodes: dict[str, list[GraphNode]] = field(default_factory=dict)

    # ---------------------------------------------------------------------------
    # Build
    # ---------------------------------------------------------------------------

    @classmethod
    def build(cls, arch_names: list[str], report_dir: Path) -> "ThreatGraph":
        g = cls()
        g.archs = arch_names

        for arch in arch_names:
            arch_dir = report_dir / arch
            if not arch_dir.is_dir():
                continue
            g._ingest_arch(arch, arch_dir)

        return g

    def _ingest_arch(self, arch: str, arch_dir: Path) -> None:
        gt_path = arch_dir / "ground_truth.json"
        if not gt_path.exists():
            return

        try:
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
        except Exception:
            return

        self.arch_risk_score[arch]    = gt.get("expected_risk_score", 0) or 0
        self.arch_defensibility[arch] = gt.get("expected_defensibility", 0) or 0

        # Controls
        cm = [c.lower() for c in (gt.get("controls_missing") or [])]
        cp = [c.lower() for c in (gt.get("controls_present") or [])]
        self.arch_controls_missing[arch] = cm
        self.arch_controls_present[arch] = cp
        for c in cm:
            self.control_to_archs_missing[c].add(arch)
        for c in cp:
            self.control_to_archs_present[c].add(arch)

        # Attack paths
        aps = gt.get("expected_attack_paths") or []
        for ap_data in aps:
            ap_id = ap_data.get("id", "")
            key = f"{arch}::{ap_id}"
            techniques = list(ap_data.get("techniques") or [])
            ap = AP(
                id=ap_id,
                arch=arch,
                entry=ap_data.get("entry", ""),
                target=ap_data.get("target", ""),
                path=list(ap_data.get("path") or []),
                criticality_tier=ap_data.get("criticality_tier", ""),
                criticality=float(ap_data.get("criticality") or 0),
                techniques=techniques,
            )
            self.attack_paths[key] = ap
            for t in techniques:
                self.technique_to_archs[t].add(arch)
                self.technique_to_aps[t].add(key)

        # Nodes — build from AP paths (works on all report versions)
        spofs_from_gt: set[str] = set()
        for ap_data in aps:
            for hop_info in (ap_data.get("_layered_defense", {}).get("spofs") or []):
                spofs_from_gt.add(hop_info.get("node_id", ""))

        node_techniques: dict[str, list[str]] = defaultdict(list)
        node_labels: dict[str, str] = {}
        # Use sets to count unique edges (avoid inflating degree by repeated AP traversals)
        node_out_targets: dict[str, set[str]] = defaultdict(set)
        node_in_sources: dict[str, set[str]] = defaultdict(set)

        for ap_data in aps:
            pnt = ap_data.get("per_node_techniques") or {}
            for node_id, ttps in pnt.items():
                node_techniques[node_id].extend(ttps if isinstance(ttps, list) else [])

            # Derive unique edges from ordered path (works without _layered_defense)
            path = ap_data.get("path") or []
            for i, node_id in enumerate(path):
                node_labels.setdefault(node_id, node_id)
                if i < len(path) - 1:
                    node_out_targets[node_id].add(path[i + 1])
                if i > 0:
                    node_in_sources[node_id].add(path[i - 1])

        # Also collect labels from _layered_defense hop_analysis if present
        for ap_data in aps:
            for hop in (ap_data.get("_layered_defense", {}).get("hop_analysis") or []):
                src = hop.get("source_id", "")
                tgt = hop.get("target_id", "")
                if src:
                    node_labels.setdefault(src, hop.get("source_label", src))
                if tgt:
                    node_labels.setdefault(tgt, hop.get("target_label", tgt))

        _INFRA_KW = {"load balancer", "loadbalancer", "router", "switch", "firewall", "nat", "cdn", "proxy"}
        _ENTRY_KW = {"user", "visitor", "employee", "client", "browser", "mobile",
                     "internet", "external", "attacker", "citizen", "customer", "public"}
        for node_id, label in node_labels.items():
            label_l = label.lower()
            is_infra  = any(kw in label_l for kw in _INFRA_KW)
            is_entry  = any(kw in label_l for kw in _ENTRY_KW)
            od = len(node_out_targets.get(node_id, set()))
            id_ = len(node_in_sources.get(node_id, set()))
            gn = GraphNode(
                id=node_id,
                arch=arch,
                label=label,
                in_degree=id_,
                out_degree=od,
                is_hub=(od >= 3 and not is_infra and not is_entry),
                is_spof=(node_id in spofs_from_gt),
                techniques=list(set(node_techniques.get(node_id, []))),
            )
            self.nodes[f"{arch}::{node_id}"] = gn

        # Hub/SPOF index per arch
        self.hub_nodes[arch]  = [n for n in self.nodes.values() if n.arch == arch and n.is_hub]
        self.spof_nodes[arch] = [n for n in self.nodes.values() if n.arch == arch and n.is_spof]

        # Technique → control mapping from control_recommendations
        for cr in (gt.get("control_recommendations") or []):
            ctrl = (cr.get("control") or "").lower()
            for t in (cr.get("techniques") or []):
                if ctrl and t not in self.technique_to_controls[t]:
                    self.technique_to_controls[t].append(ctrl)

        # Critic verdicts
        critic_files = [
            ("04_architect_critique.json", "Architect"),
            ("05_tester_critique.json",    "Tester"),
            ("06_red_team_critique.json",  "RedTeam"),
            ("06b_purple_team_critique.json", "PurpleTeamer"),
            ("06c_blackhat_critique.json", "Blackhat"),
        ]
        for fname, role in critic_files:
            fpath = arch_dir / fname
            if not fpath.exists():
                continue
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                continue
            gaps: list[str] = []
            # Red team / purple team gap T-IDs
            for gap in (data.get("exploitable_gaps") or data.get("coverage_gaps") or []):
                if isinstance(gap, dict):
                    t = gap.get("technique") or gap.get("id") or ""
                    if t:
                        gaps.append(t)
                elif isinstance(gap, str):
                    gaps.append(gap)
            # Top findings from breakdown text (first 2 reasoning snippets)
            top: list[str] = []
            bd = data.get("breakdown") or {}
            for dim_val in bd.values():
                if isinstance(dim_val, dict) and "reasoning" in dim_val:
                    snippet = dim_val["reasoning"][:120].replace("\n", " ")
                    top.append(snippet)
                if len(top) >= 2:
                    break
            self.verdicts[f"{arch}::{role}"] = CriticVerdict(
                arch=arch, role=role,
                score=int(data.get("score") or 0),
                rating=str(data.get("rating") or ""),
                gaps=gaps[:10],
                top_findings=top,
            )

    # ---------------------------------------------------------------------------
    # Query dispatcher — pattern matches on the question text
    # ---------------------------------------------------------------------------

    def query(self, question: str) -> str | None:
        """Return a formatted answer if the question matches a structural pattern,
        or None if the question needs LLM reasoning."""
        q = question.strip().lower()

        # ── T-ID lookup: "which architectures have T1078" ────────────────────
        t_match = re.search(r'\bt(\d{4}(?:\.\d{3})?)\b', q)
        if t_match:
            tid = f"T{t_match.group(1)}"
            if any(kw in q for kw in ["which arch", "architecture", "appear", "have", "contain", "across", "in corpus", "in workspace"]):
                return self._q_technique_archs(tid)
            if any(kw in q for kw in ["cover", "mitigat", "control", "block"]):
                return self._q_technique_controls(tid)
            if any(kw in q for kw in ["path", "ap-", "ap "]):
                return self._q_technique_aps(tid)
            # default: full T-ID summary
            return self._q_technique_summary(tid)

        # ── Arch-scoped queries ───────────────────────────────────────────────
        # Detect arch name in question; if none found and only one arch has
        # actual data, use it implicitly (handles missing/empty arch dirs).
        arch = self._detect_arch(q)
        if arch is None:
            archs_with_data = [a for a in self.archs if a in self.arch_controls_missing or a in self.arch_risk_score]
            if len(archs_with_data) == 1:
                arch = archs_with_data[0]

        if arch:
            if any(kw in q for kw in ["critical path", "criticality", "highest risk path", "critical ap", "critical paths"]):
                return self._q_critical_paths(arch)
            if any(kw in q for kw in ["missing control", "gap", "controls missing", "not in place", "missing controls"]):
                return self._q_missing_controls(arch)
            if any(kw in q for kw in ["present control", "has control", "controls present", "in place"]):
                return self._q_present_controls(arch)
            if any(kw in q for kw in ["hub node", "pivot node", "hub nodes", "hubs"]):
                return self._q_hub_nodes(arch)
            if any(kw in q for kw in ["spof", "spofs", "single point", "bottleneck"]):
                return self._q_spof_nodes(arch)
            if any(kw in q for kw in ["critic", "architect", "tester", "red team", "verdict", "score"]):
                return self._q_critic_verdicts(arch)
            if any(kw in q for kw in ["attack path", "ap-", " ap ", "all paths", "paths"]):
                return self._q_all_paths(arch)
            if any(kw in q for kw in ["risk score", "defensibility"]):
                return self._q_arch_scores(arch)

        # ── Corpus-wide control gap ───────────────────────────────────────────
        ctrl = self._detect_control(q)
        if ctrl:
            if any(kw in q for kw in ["missing", "gap", "lack", "without", "not have"]):
                return self._q_control_missing_archs(ctrl)
            if any(kw in q for kw in ["present", "have", "covered", "implement"]):
                return self._q_control_present_archs(ctrl)

        # ── Corpus overview ───────────────────────────────────────────────────
        if any(kw in q for kw in ["all arch", "corpus", "workspace overview", "list arch", "architectures in", "overview"]):
            return self._q_corpus_overview()

        return None  # Falls through to LLM

    # ---------------------------------------------------------------------------
    # Query handlers
    # ---------------------------------------------------------------------------

    def _q_technique_archs(self, tid: str) -> str:
        archs = sorted(self.technique_to_archs.get(tid, set()))
        if not archs:
            return f"**{tid}** — not found in any architecture in this workspace."
        lines = [f"**{tid}** appears in **{len(archs)}** architecture(s):", ""]
        for a in archs:
            aps = [k.split("::")[1] for k in self.technique_to_aps.get(tid, set()) if k.startswith(f"{a}::")]
            lines.append(f"- **{a}** — paths: {', '.join(sorted(aps)) or '(none mapped)'}")
        return "\n".join(lines)

    def _q_technique_controls(self, tid: str) -> str:
        ctrls = self.technique_to_controls.get(tid, [])
        if not ctrls:
            return f"**{tid}** — no controls mapped to this technique in the workspace."
        return f"**{tid}** is addressed by: {', '.join(ctrls[:8])}."

    def _q_technique_aps(self, tid: str) -> str:
        aps = sorted(self.technique_to_aps.get(tid, set()))
        if not aps:
            return f"**{tid}** — not found in any attack path."
        lines = [f"**{tid}** appears in **{len(aps)}** attack path(s):", ""]
        for ap_key in aps:
            ap = self.attack_paths.get(ap_key)
            if ap:
                lines.append(f"- **{ap.arch} / {ap.id}** ({ap.criticality_tier}) — {ap.entry} → {ap.target}")
        return "\n".join(lines)

    def _q_technique_summary(self, tid: str) -> str:
        archs = sorted(self.technique_to_archs.get(tid, set()))
        aps = sorted(self.technique_to_aps.get(tid, set()))
        ctrls = self.technique_to_controls.get(tid, [])
        if not archs:
            return f"**{tid}** — not found in this workspace."
        parts = [f"**{tid}** summary:"]
        parts.append(f"- Architectures: {', '.join(archs)}")
        parts.append(f"- Attack paths ({len(aps)}): {', '.join(k.split('::')[1] + ' (' + k.split('::')[0] + ')' for k in aps[:6])}")
        if ctrls:
            parts.append(f"- Mitigating controls: {', '.join(ctrls[:5])}")
        return "\n".join(parts)

    def _q_critical_paths(self, arch: str) -> str:
        aps = [ap for ap in self.attack_paths.values() if ap.arch == arch]
        aps.sort(key=lambda a: a.criticality, reverse=True)
        critical = [ap for ap in aps if ap.criticality_tier in ("CRITICAL", "HIGH")]
        if not critical:
            critical = aps[:3]
        if not critical:
            return f"**{arch}** — no attack paths found."
        lines = [f"**{arch}** — top {len(critical)} path(s) by criticality:", ""]
        for ap in critical:
            path_str = " → ".join(ap.path) if len(ap.path) <= 6 else " → ".join(ap.path[:5]) + " → …"
            lines.append(f"- **{ap.id}** [{ap.criticality_tier}] {path_str}")
            if ap.techniques:
                lines.append(f"  Techniques: {', '.join(ap.techniques[:5])}")
        return "\n".join(lines)

    def _q_all_paths(self, arch: str) -> str:
        aps = sorted([ap for ap in self.attack_paths.values() if ap.arch == arch], key=lambda a: a.id)
        if not aps:
            return f"**{arch}** — no attack paths found."
        lines = [f"**{arch}** — {len(aps)} attack path(s):", ""]
        for ap in aps:
            lines.append(f"- **{ap.id}** [{ap.criticality_tier}] {ap.entry} → {ap.target} ({len(ap.path)-1} hops)")
        return "\n".join(lines)

    def _q_missing_controls(self, arch: str) -> str:
        cm = self.arch_controls_missing.get(arch, [])
        if not cm:
            return f"**{arch}** — no missing controls recorded."
        lines = [f"**{arch}** — {len(cm)} missing control(s):", ""]
        for c in cm[:15]:
            lines.append(f"- {c}")
        if len(cm) > 15:
            lines.append(f"- … and {len(cm)-15} more")
        return "\n".join(lines)

    def _q_present_controls(self, arch: str) -> str:
        cp = self.arch_controls_present.get(arch, [])
        if not cp:
            return f"**{arch}** — no controls recorded as present."
        return f"**{arch}** — controls present ({len(cp)}): {', '.join(cp[:15])}" + (f" +{len(cp)-15} more" if len(cp) > 15 else "")

    def _q_hub_nodes(self, arch: str) -> str:
        hubs = self.hub_nodes.get(arch, [])
        if not hubs:
            return f"**{arch}** — no hub nodes (out_degree ≥ 3) found."
        lines = [f"**{arch}** — {len(hubs)} hub node(s):", ""]
        for n in hubs:
            lines.append(f"- **{n.label}** (out={n.out_degree}) — techniques: {', '.join(n.techniques[:4]) or 'none'}")
        return "\n".join(lines)

    def _q_spof_nodes(self, arch: str) -> str:
        spofs = self.spof_nodes.get(arch, [])
        if not spofs:
            return f"**{arch}** — no SPOFs identified."
        lines = [f"**{arch}** — {len(spofs)} SPOF node(s):", ""]
        for n in spofs:
            lines.append(f"- **{n.label}** (in={n.in_degree} out={n.out_degree})")
        return "\n".join(lines)

    def _q_critic_verdicts(self, arch: str) -> str:
        vs = [v for v in self.verdicts.values() if v.arch == arch]
        if not vs:
            return f"**{arch}** — no critic verdicts found (ER not yet run)."
        lines = [f"**{arch}** — critic verdicts:", ""]
        for v in sorted(vs, key=lambda x: x.score, reverse=True):
            lines.append(f"- **{v.role}** — {v.score}/100 [{v.rating}]" + (f", gaps: {', '.join(v.gaps[:4])}" if v.gaps else ""))
        return "\n".join(lines)

    def _q_arch_scores(self, arch: str) -> str:
        risk = self.arch_risk_score.get(arch)
        defn = self.arch_defensibility.get(arch)
        if risk is None:
            return f"**{arch}** — scores not available."
        return f"**{arch}** — risk score: **{risk}**, defensibility: **{defn}%**"

    def _q_control_missing_archs(self, ctrl: str) -> str:
        archs = sorted(self.control_to_archs_missing.get(ctrl, set()))
        if not archs:
            return f"Control **{ctrl}** — not listed as missing in any architecture."
        return f"Control **{ctrl}** is missing in: {', '.join(archs)}."

    def _q_control_present_archs(self, ctrl: str) -> str:
        archs = sorted(self.control_to_archs_present.get(ctrl, set()))
        if not archs:
            return f"Control **{ctrl}** — not recorded as present in any architecture."
        return f"Control **{ctrl}** is present in: {', '.join(archs)}."

    def _q_corpus_overview(self) -> str:
        if not self.archs:
            return "No architectures in this workspace."
        lines = []
        missing = []
        for a in self.archs:
            if a not in self.arch_risk_score:
                missing.append(a)
                continue
            n_aps = sum(1 for ap in self.attack_paths.values() if ap.arch == a)
            n_cm = len(self.arch_controls_missing.get(a, []))
            risk = self.arch_risk_score.get(a, "—")
            lines.append(f"- **{a}** — {n_aps} paths, {n_cm} gaps, risk {risk}")
        header = f"Workspace — {len(lines)} architecture(s) with data:"
        if missing:
            header += f" ({', '.join(missing)} not yet analysed)"
        return header + "\n\n" + "\n".join(lines) if lines else f"No analysed architectures found. Not yet run: {', '.join(missing)}"

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _detect_arch(self, q: str) -> str | None:
        """Return the first arch name found in the question, or None."""
        for a in self.archs:
            if a.lower() in q or a.lower().replace("_", " ") in q:
                return a
        return None

    def _detect_control(self, q: str) -> str | None:
        """Return a control name if clearly identified in the question."""
        all_controls: set[str] = set()
        for lst in self.arch_controls_missing.values():
            all_controls.update(lst)
        for lst in self.arch_controls_present.values():
            all_controls.update(lst)
        for c in all_controls:
            if c in q:
                return c
        return None
