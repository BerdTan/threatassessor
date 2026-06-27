"""
Governance layer for ThreatAssessor pipeline.

InhouseGovernanceAdapter is the default — zero external dependencies, covers all
5 OWASP Agentic dimensions. AGTGovernanceAdapter is an optional compliance upgrade
(requires: pip install agent-governance-toolkit) that wraps the inhouse adapter
with a formal policy engine and Merkle-chain audit log.

Enable AGT: PUT /api/v1/config {"governance": {"agt_enabled": true}}
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolError:
    tool_name: str
    critic_name: str
    error_message: str
    severity: str          # LOW | MEDIUM | HIGH | CRITICAL
    recoverable: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GovernanceSignals:
    # Dimension 1 — Exploitation (OWASP A01/A03, ARC INT+SAF, AML.TA0001)
    exploitation: dict = field(default_factory=dict)

    # Dimension 2 — Manipulation (OWASP A09/A05, ARC TRANS+ACC, AML.TA0009)
    manipulation: dict = field(default_factory=dict)

    # Dimension 3 — Data Leakage (OWASP A03/A06, ARC PRIV+SEC, AML.TA0007)
    leakage: dict = field(default_factory=dict)

    # Dimension 4 — Cross-Identity (OWASP A02/A06, ARC ACC+FAIR, AML.TA0006)
    identity: dict = field(default_factory=dict)

    # Dimension 5 — Sovereignty (OWASP A07/A08, ARC PRIV+SEC+SOC, AML.TA0010+TA0015)
    sovereignty: dict = field(default_factory=dict)

    # Summary
    overall_risk_level: str = "LOW"
    adapter_type: str = "inhouse"
    policy_version: str = "inhouse-1.0"
    arc_risk_scores: dict = field(default_factory=dict)
    kill_chain_coverage: list = field(default_factory=list)
    architecture_name: str = ""
    run_id: str = ""
    # Registry enforcement — critics to block based on governance policy decisions
    blocked_agents: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def merge(self, other: "GovernanceSignals") -> "GovernanceSignals":
        """Merge another GovernanceSignals into this one (union of signals, max severity)."""
        _SEV = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        _REV = {v: k for k, v in _SEV.items()}

        def _merge_dim(a: dict, b: dict) -> dict:
            merged = dict(a)
            for k, v in b.items():
                if k not in merged:
                    merged[k] = v
                elif isinstance(v, list) and isinstance(merged[k], list):
                    merged[k] = list(set(merged[k]) | set(v))
                elif k == "severity":
                    merged[k] = _REV[max(_SEV.get(a.get(k, "LOW"), 0),
                                         _SEV.get(v, 0))]
                elif k in ("blocked", "flagged") and isinstance(v, bool):
                    merged[k] = merged[k] or v
                elif isinstance(v, (int, float)) and isinstance(merged[k], (int, float)):
                    merged[k] = max(merged[k], v)
            return merged

        self.exploitation = _merge_dim(self.exploitation, other.exploitation)
        self.manipulation  = _merge_dim(self.manipulation, other.manipulation)
        self.leakage       = _merge_dim(self.leakage, other.leakage)
        self.identity      = _merge_dim(self.identity, other.identity)
        self.sovereignty   = _merge_dim(self.sovereignty, other.sovereignty)

        all_sevs = [
            self.exploitation.get("severity", "LOW"),
            self.manipulation.get("severity", "LOW"),
            self.leakage.get("severity", "LOW"),
            self.identity.get("severity", "LOW"),
            self.sovereignty.get("severity", "LOW"),
        ]
        self.overall_risk_level = _REV[max(_SEV.get(s, 0) for s in all_sevs)]

        kcc = set(self.kill_chain_coverage) | set(other.kill_chain_coverage)
        self.kill_chain_coverage = sorted(kcc)

        if other.arc_risk_scores:
            self.arc_risk_scores.update(other.arc_risk_scores)

        # Union blocked_agents lists
        self.blocked_agents = list(set(self.blocked_agents) | set(other.blocked_agents))

        return self


# ---------------------------------------------------------------------------
# Regex patterns (compiled once)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

# Common Cyrillic-to-Latin confusable map (characters that are visually
# identical to Latin letters but are separate Unicode codepoints).
# NFKD alone does not help here — Cyrillic letters have no decomposition.
_CONFUSABLE_MAP = str.maketrans({
    "а": "a",   # а → a
    "е": "e",   # е → e
    "і": "i",   # і → i  (Ukrainian)
    "й": "i",   # й → i  (approximate)
    "о": "o",   # о → o
    "р": "p",   # р → p  (looks like p, not r)
    "с": "c",   # с → c
    "х": "x",   # х → x
    "у": "y",   # у → y
    "в": "b",   # в → b  (approximate)
    "ѕ": "s",   # ѕ → s
    "ԁ": "d",   # ԁ → d
})


def _normalise(text: str) -> str:
    """Normalise text to defeat unicode homoglyph substitution.

    Step 1: NFKD + ASCII encode — handles accented Latin letters (é → e).
    Step 2: Apply Cyrillic confusable map — handles Cyrillic lookalikes
            (і → i, р → p, о → o) that NFKD does not decompose.
    """
    # Apply confusable map before NFKD so Cyrillic chars aren't dropped by encode
    text = text.translate(_CONFUSABLE_MAP)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Exploitation — injection (applied to normalised text)
_RE_INJECTION = re.compile(
    r"ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|context)"
    r"|jailbreak|<\s*script|prompt\s*injection|forget\s+(everything|your\s+instructions?)"
    r"|you\s+are\s+now\s+an?\s+|roleplay\s+as\s+|pretend\s+(you\s+are|to\s+be)",
    re.IGNORECASE,
)

# Exploitation — path traversal (raw + URL-encoded variants, case-insensitive hex)
_RE_PATH_TRAVERSAL = re.compile(
    r"\.\./|\.\.\\|%2e%2e[%/\\]|\.\.%2f|\.\.%5c|%2e%2e%2f|%2e%2e%5c",
    re.IGNORECASE,
)

# Data Leakage — PII
# NRIC: allow optional internal spaces ("S 1234567 A" is a common printed format)
_RE_NRIC = re.compile(r"\b[SFTG]\s?\d{3}\s?\d{4}\s?[A-Z]\b")
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_PHONE = re.compile(r"(?<!CVE-)(?<!cve-)(?<!\d-)(?<!\d)\b(\+65[\s-]?)?\d{4}[\s-]\d{4}\b")  # SG phone — excludes CVE-YYYY-NNNN patterns

# Data Leakage — credentials (expanded keyword list)
_RE_CRED = re.compile(
    r"\b(password|passwd|secret|api_key|apikey|token|private_key|access_key"
    r"|client_secret|auth_token|db_pass|db_password|database_url|database_password"
    r"|conn_string|connection_string|jdbc_url|smtp_password|encryption_key"
    r"|signing_key|bearer|credentials?)\s*[=:]\s*\S+",
    re.IGNORECASE,
)

# Sovereignty — cloud regions (hyphenated AWS/Azure/GCP patterns)
_RE_REGION = re.compile(
    r"\b(us-east-\d|us-west-\d|eu-west-\d|eu-central-\d"
    r"|ap-southeast-\d|ap-northeast-\d|ap-south-\d"
    r"|ca-central-\d|sa-east-\d"
    r"|australiaeast|australiasoutheast|westeurope|northeurope"
    r"|eastus[12]?|westus[12]?|centralus|southeastasia|eastasia)\b",
    re.IGNORECASE,
)
_RE_ZDR = re.compile(
    r"zero[\s_-]?data[\s_-]?retention|zdr\b|data[\s_-]?residency|cross[\s_-]?border",
    re.IGNORECASE,
)

# Sovereignty — external service + expanded LLM node vocabulary
_RE_EXTERNAL_SERVICE = re.compile(
    r"\b(sendgrid|twilio|stripe|salesforce|external\s+api|external\s+webhook"
    r"|third[\s_-]?party|3rd[\s_-]?party|outbound\s+webhook"
    r"|vendor\s+api|outsourced\s+service|external\s+service)\b",
    re.IGNORECASE,
)

# Severity thresholds
_LABEL_MAX_CHARS = 512
_STALE_DATA_DAYS = 90


def _severity(level: int) -> str:
    return ["LOW", "MEDIUM", "HIGH", "CRITICAL"][min(level, 3)]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class GovernanceAdapter(ABC):
    @abstractmethod
    def check_input(self, mmd_content: str, architecture_path: str) -> GovernanceSignals:
        """Scan raw MMD input before analysis."""

    @abstractmethod
    def check_artifact(self, ground_truth: dict) -> GovernanceSignals:
        """Scan ground_truth artifact after analysis stage."""

    @abstractmethod
    def wrap_capability(self, fn: Callable, capability_type: str, critic_name: str) -> Callable:
        """Return a wrapped version of fn that logs the call and catches ToolErrors."""


# ---------------------------------------------------------------------------
# Inhouse adapter — pure Python, no external deps
# ---------------------------------------------------------------------------

class InhouseGovernanceAdapter(GovernanceAdapter):

    def __init__(self, policy_path: str = "policies/agent_governance.yaml"):
        self._policy_path = policy_path
        self._capability_log: List[dict] = []
        self._tool_errors: List[ToolError] = []

    # ── Dimension 1: Exploitation ────────────────────────────────────────

    def check_input(self, mmd_content: str, architecture_path: str) -> GovernanceSignals:
        sig = GovernanceSignals(
            exploitation={
                "injection_patterns": [],
                "oversized_labels": 0,
                "path_traversal": [],
                "blocked": False,
                "severity": "LOW",
                "arc_categories": ["INT", "SAF"],
                "atlas_tactics": ["AML.TA0001"],
                "kill_chain_stage": "external_boundary",
            },
            leakage={
                "pii_indicators": [],
                "sensitive_keywords": [],
                "flagged": False,
                "supply_chain_stale_sources": [],
                "arc_categories": ["PRIV", "SEC"],
                "atlas_tactics": ["AML.TA0007"],
                "kill_chain_stage": "deterministic_layer",
            },
            sovereignty={
                "cross_boundary_nodes": [],
                "inferred_regions": [],
                "zdr_signals": [],
                "boundary_violations": [],
                "flagged": False,
                "severity": "LOW",
                "arc_categories": ["PRIV", "SEC", "SOC"],
                "atlas_tactics": ["AML.TA0010", "AML.TA0015"],
                "kill_chain_stage": "data_boundary",
            },
            kill_chain_coverage=["external_boundary"],
        )

        if not mmd_content:
            return sig

        # Normalise to ASCII before injection/traversal checks to defeat
        # unicode homoglyph substitution (e.g. Cyrillic 'о' swapped for 'o').
        normalised = _normalise(mmd_content)

        # Injection patterns (on normalised text)
        for match in _RE_INJECTION.finditer(normalised):
            sig.exploitation["injection_patterns"].append(match.group(0)[:80])

        # Path traversal in node IDs / labels (on normalised text)
        for match in _RE_PATH_TRAVERSAL.finditer(normalised):
            sig.exploitation["path_traversal"].append(match.group(0))

        # Oversized node labels (any token >512 chars between quotes or brackets)
        for token in re.findall(r'"[^"]{' + str(_LABEL_MAX_CHARS) + r',}"|\[[^\]]{' + str(_LABEL_MAX_CHARS) + r',}\]', mmd_content):
            sig.exploitation["oversized_labels"] += 1

        # Severity + blocked
        n_inj = len(sig.exploitation["injection_patterns"])
        n_trav = len(sig.exploitation["path_traversal"])
        n_over = sig.exploitation["oversized_labels"]
        if n_trav > 0 or n_over > 0:
            sig.exploitation["severity"] = "CRITICAL"
            sig.exploitation["blocked"] = True
        elif n_inj >= 2:
            sig.exploitation["severity"] = "HIGH"
        elif n_inj == 1:
            sig.exploitation["severity"] = "MEDIUM"

        # Sovereignty: cloud region hints in node labels
        for match in _RE_REGION.finditer(mmd_content):
            region = match.group(0).lower()
            sig.sovereignty["inferred_regions"].append(region)
            # Find context (surrounding node label text ~50 chars)
            start = max(0, match.start() - 40)
            ctx_snippet = mmd_content[start:match.end() + 20].replace("\n", " ").strip()
            sig.sovereignty["cross_boundary_nodes"].append(ctx_snippet[:80])

        # ZDR signals
        for match in _RE_ZDR.finditer(mmd_content):
            sig.sovereignty["zdr_signals"].append(match.group(0)[:60])

        # LLM → external service edges (sovereignty data flow)
        # Build a node-id → label map.  Mermaid allows node definitions both on
        # their own line AND inline within edge lines, so we scan the full content
        # (not line-anchored) for: id["label"], id[label], id(label), id((label))
        _RE_NODE_DEF = re.compile(
            r'\b(\w+)\s*[\[\(\{]+["\']?([^\]"\')\}]{1,120})["\']?[\]\)\}]+',
        )
        node_labels: dict = {}
        for nm in _RE_NODE_DEF.finditer(mmd_content):
            node_labels[nm.group(1)] = nm.group(2)

        _RE_LLM_NODE = re.compile(
            r'\b(LLM|GPT|Claude|Bedrock|OpenAI|AI\s*Model|AI\s*Engine|AI\s*Service'
            r'|ML\s*Model|Chat\s*Service|Inference\s*API?|Inference|GenAI|Foundation\s*Model)\b',
            re.IGNORECASE,
        )
        _RE_EDGE = re.compile(r'(\w+)\s*[-=]+>\s*(\w+)', re.MULTILINE)

        # Strip inline node labels before edge extraction so that
        # `LLM["LLM Service"] --> VendorAPI["Vendor API"]` reduces to `LLM --> VendorAPI`
        _edges_content = re.sub(r'[\[\(\{][^\]\)\}]*[\]\)\}]', '', mmd_content)

        llm_node_ids = {
            nid for nid, lbl in node_labels.items() if _RE_LLM_NODE.search(lbl)
        }
        # Also catch nodes whose ID itself looks like LLM
        llm_node_ids |= {
            nid for nid in node_labels if _RE_LLM_NODE.search(nid)
        }

        for em in _RE_EDGE.finditer(_edges_content):
            src, dst = em.group(1), em.group(2)
            if src in llm_node_ids:
                dst_label = node_labels.get(dst, dst)
                if _RE_EXTERNAL_SERVICE.search(dst_label) or _RE_EXTERNAL_SERVICE.search(dst):
                    sig.sovereignty["zdr_signals"].append(
                        f"inference→external: {src}[{node_labels.get(src, src)}] → {dst}[{dst_label[:60]}]"
                    )

        # Deduplicate
        sig.sovereignty["inferred_regions"] = list(set(sig.sovereignty["inferred_regions"]))
        sig.sovereignty["cross_boundary_nodes"] = list(dict.fromkeys(sig.sovereignty["cross_boundary_nodes"]))

        if sig.sovereignty["cross_boundary_nodes"] or sig.sovereignty["zdr_signals"]:
            sig.sovereignty["flagged"] = True
            sev_level = 2 if sig.sovereignty["zdr_signals"] else 1
            sig.sovereignty["severity"] = _severity(sev_level)

        sig.kill_chain_coverage = ["external_boundary", "data_boundary"]
        sig.overall_risk_level = self._compute_overall(sig)
        return sig

    # ── Dimension 3: Data Leakage + supply chain ─────────────────────────

    def check_artifact(self, ground_truth: dict) -> GovernanceSignals:
        sig = GovernanceSignals(
            leakage={
                "pii_indicators": [],
                "sensitive_keywords": [],
                "flagged": False,
                "supply_chain_stale_sources": [],
                "arc_categories": ["PRIV", "SEC"],
                "atlas_tactics": ["AML.TA0007"],
                "kill_chain_stage": "deterministic_layer",
            },
            identity={
                "critic_tool_calls": {},
                "tool_errors": [],
                "context_bleed_signals": [],
                "overreach_signals": [],
                "supply_chain_modified_modules": [],
                "arc_categories": ["ACC", "FAIR"],
                "atlas_tactics": ["AML.TA0006"],
                "kill_chain_stage": "llm_layer",
            },
            kill_chain_coverage=["deterministic_layer", "llm_layer"],
        )

        # Scan all string values in ground_truth for PII / credentials
        text_blob = json.dumps(ground_truth)

        for match in _RE_NRIC.finditer(text_blob):
            sig.leakage["pii_indicators"].append(f"NRIC:{match.group(0)}")
        for match in _RE_EMAIL.finditer(text_blob):
            sig.leakage["pii_indicators"].append(f"email:{match.group(0)}")
        for match in _RE_PHONE.finditer(text_blob):
            sig.leakage["pii_indicators"].append(f"phone:{match.group(0)}")
        for match in _RE_CRED.finditer(text_blob):
            kw = match.group(0).split("=")[0].split(":")[0].strip()
            sig.leakage["sensitive_keywords"].append(kw)

        if sig.leakage["pii_indicators"] or sig.leakage["sensitive_keywords"]:
            sig.leakage["flagged"] = True
            crit = any("NRIC:" in p for p in sig.leakage["pii_indicators"]) \
                   or sig.leakage["sensitive_keywords"]
            sig.leakage["severity"] = "CRITICAL" if crit else "HIGH"
        else:
            sig.leakage["severity"] = "LOW"

        # Supply chain: check data file ages
        sig.leakage["supply_chain_stale_sources"] = self._check_stale_sources()

        # Supply chain: module integrity (git hash check)
        sig.identity["supply_chain_modified_modules"] = self._check_module_integrity()

        # Attach tool errors captured so far
        sig.identity["tool_errors"] = [e.to_dict() for e in self._tool_errors]
        sig.identity["critic_tool_calls"] = self._summarise_capability_log()

        # ARC risk scores from ground_truth if available
        if arc_scores := ground_truth.get("arc_risk_scores"):
            sig.arc_risk_scores = dict(arc_scores)
        elif control_recs := ground_truth.get("control_recommendations"):
            # Derive approximate ARC scores from RAPIDS categories
            sig.arc_risk_scores = self._derive_arc_scores(ground_truth)

        sig.kill_chain_coverage = ["deterministic_layer", "llm_layer"]
        sig.overall_risk_level = self._compute_overall(sig)
        return sig

    # ── Dimension 4: wrap_capability ─────────────────────────────────────

    def wrap_capability(self, fn: Callable, capability_type: str, critic_name: str) -> Callable:
        def _wrapped(*args, **kwargs):
            entry = {
                "critic_name": critic_name,
                "capability_type": capability_type,
                "fn_name": fn.__name__,
                "args_hash": hashlib.md5(repr((args, kwargs)).encode()).hexdigest()[:8],
                "ts": time.time(),
            }
            self._capability_log.append(entry)
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                err = ToolError(
                    tool_name=fn.__name__,
                    critic_name=critic_name,
                    error_message=str(exc)[:200],
                    severity="HIGH",
                    recoverable=True,
                )
                self._tool_errors.append(err)
                raise
        return _wrapped

    # ── Internal helpers ──────────────────────────────────────────────────

    def _check_stale_sources(self) -> List[str]:
        """Return list of data file paths older than _STALE_DATA_DAYS days."""
        stale = []
        data_files = [
            "chatbot/data/enterprise-attack.json",
            "chatbot/data/technique_embeddings.json",
        ]
        cutoff = time.time() - _STALE_DATA_DAYS * 86400
        for path_str in data_files:
            p = Path(path_str)
            if p.exists():
                mtime = p.stat().st_mtime
                if mtime < cutoff:
                    age_days = int((time.time() - mtime) / 86400)
                    stale.append(f"{path_str} ({age_days}d old)")
        return stale

    def _check_module_integrity(self) -> List[str]:
        """
        Compare critic module file hashes against git object hashes.
        Falls back to empty list if .git is absent (container deployments).
        """
        modified = []
        try:
            import subprocess
            critic_dir = Path("chatbot/modules/agents/critics")
            if not critic_dir.exists() or not Path(".git").exists():
                return []
            result = subprocess.run(
                ["git", "ls-files", "-s", str(critic_dir)],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return []
            for line in result.stdout.strip().splitlines():
                # format: <mode> <hash> <stage>\t<path>
                parts = line.split()
                if len(parts) < 4:
                    continue
                git_hash = parts[1]
                file_path = parts[3]
                p = Path(file_path)
                if not p.exists():
                    continue
                content = p.read_bytes()
                blob = f"blob {len(content)}\x00".encode() + content
                disk_hash = hashlib.sha1(blob).hexdigest()
                if disk_hash != git_hash:
                    modified.append(file_path)
        except Exception as exc:
            logger.debug(f"Module integrity check skipped: {exc}")
        return modified

    def _summarise_capability_log(self) -> dict:
        summary: dict = {}
        for entry in self._capability_log:
            cn = entry["critic_name"]
            summary[cn] = summary.get(cn, 0) + 1
        return summary

    def _derive_arc_scores(self, ground_truth: dict) -> dict:
        """Approximate ARC scores from RAPIDS per-threat initial_risk values."""
        per_threat = ground_truth.get("residual_risks", {}).get("per_threat", {})

        def _score(key: str, default: int = 50) -> int:
            entry = per_threat.get(key, {})
            if isinstance(entry, dict):
                return int(entry.get("initial_risk", default))
            if isinstance(entry, (int, float)):
                return int(entry)
            return default

        return {
            "INT":   _score("application_vulns"),
            "SAF":   _score("dos"),
            "SEC":   max(_score("ransomware"), _score("supply_chain")),
            "PRIV":  _score("insider_threat"),
            "TRANS": 50,
            "ACC":   50,
            "FAIR":  50,
            "SOC":   50,
        }

    def _compute_overall(self, sig: GovernanceSignals) -> str:
        _SEV = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        _REV = {v: k for k, v in _SEV.items()}
        levels = [
            sig.exploitation.get("severity", "LOW"),
            sig.manipulation.get("severity", "LOW"),
            sig.leakage.get("severity", "LOW"),
            sig.identity.get("severity", "LOW"),
            sig.sovereignty.get("severity", "LOW"),
        ]
        return _REV[max(_SEV.get(s, 0) for s in levels)]


# ---------------------------------------------------------------------------
# AGT adapter — optional compliance upgrade
# ---------------------------------------------------------------------------

class AGTGovernanceAdapter(InhouseGovernanceAdapter):
    """
    Wraps InhouseGovernanceAdapter with Microsoft agent-governance-toolkit
    policy engine and Merkle-chain audit log.

    Falls back silently to inhouse behaviour if AGT is not installed.
    Install: pip install agent-governance-toolkit
    """

    def __init__(self, policy_path: str = "policies/agent_governance.yaml"):
        super().__init__(policy_path=policy_path)
        self._agt_available = False
        self._govern = None
        try:
            from agent_governance_toolkit import govern  # type: ignore[import]
            self._govern = govern
            self._agt_available = True
            logger.info("AGT policy engine loaded — Merkle audit enabled")
        except ImportError:
            logger.info("AGT not installed — using inhouse governance (install agent-governance-toolkit for compliance upgrade)")

    @property
    def adapter_type(self) -> str:
        return "agt" if self._agt_available else "inhouse"

    def check_input(self, mmd_content: str, architecture_path: str) -> GovernanceSignals:
        sig = super().check_input(mmd_content, architecture_path)
        sig.adapter_type = self.adapter_type
        if self._agt_available and self._govern:
            try:
                policy_result = self._govern(
                    action="check_input",
                    context={"path": architecture_path, "size": len(mmd_content)},
                    policy=self._policy_path,
                )
                if policy_result.get("decision") == "deny":
                    sig.exploitation["blocked"] = True
                    sig.exploitation["severity"] = "CRITICAL"
                    sig.exploitation["agt_policy_rule"] = policy_result.get("rule_id", "unknown")
                self._write_audit_log("check_input", policy_result)
            except Exception as exc:
                logger.warning(f"AGT check_input failed, inhouse result used: {exc}")
        return sig

    def wrap_capability(self, fn: Callable, capability_type: str, critic_name: str) -> Callable:
        wrapped_inhouse = super().wrap_capability(fn, capability_type, critic_name)
        if not (self._agt_available and self._govern):
            return wrapped_inhouse

        govern = self._govern
        policy_path = self._policy_path

        def _agt_wrapped(*args, **kwargs):
            try:
                policy_result = govern(
                    action=f"tool_call:{fn.__name__}",
                    context={"critic": critic_name, "capability_type": capability_type},
                    policy=policy_path,
                )
                self._write_audit_log(f"tool:{fn.__name__}", policy_result)
                if policy_result.get("decision") == "deny":
                    raise PermissionError(
                        f"AGT policy denied tool call {fn.__name__} by {critic_name}: "
                        f"rule={policy_result.get('rule_id')}"
                    )
            except PermissionError:
                raise
            except Exception as exc:
                logger.warning(f"AGT wrap_capability failed for {fn.__name__}: {exc}")
            return wrapped_inhouse(*args, **kwargs)

        return _agt_wrapped

    def _write_audit_log(self, action: str, policy_result: dict) -> None:
        Path("logs").mkdir(exist_ok=True)
        entry = json.dumps({
            "ts": time.time(),
            "action": action,
            "decision": policy_result.get("decision"),
            "rule_id": policy_result.get("rule_id"),
            "merkle_hash": policy_result.get("merkle_hash"),
        })
        with open("logs/governance_audit.jsonl", "a") as f:
            f.write(entry + "\n")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def get_governance_adapter(
    policy_path: str = "policies/agent_governance.yaml",
) -> GovernanceAdapter:
    """Return the appropriate adapter based on settings. Always succeeds."""
    try:
        from chatbot.config.settings import get_settings
        settings = get_settings()
        agt_enabled = getattr(getattr(settings, "governance", None), "agt_enabled", False)
    except Exception:
        agt_enabled = False

    if agt_enabled:
        return AGTGovernanceAdapter(policy_path=policy_path)
    return InhouseGovernanceAdapter(policy_path=policy_path)


def compute_manipulation_signals(moe_result: Any) -> dict:
    """
    Derive Dimension 2 (Manipulation) signals from a completed MoEResult.
    Called after expert review completes — no harness ctx required.
    """
    signals: dict = {
        "critic_divergence_score": 0,
        "confidence_swing": 0.0,
        "synthesis_quality": "UNKNOWN",
        "contradiction_ratio": 0.0,
        "fallback_triggered": False,
        "severity": "LOW",
        "arc_categories": ["TRANS", "ACC"],
        "atlas_tactics": ["AML.TA0009"],
        "kill_chain_stage": "llm_layer",
    }

    if moe_result is None:
        return signals

    # Extract from dict or object
    def _get(obj, *keys, default=None):
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k, default)
            else:
                obj = getattr(obj, k, default)
            if obj is default:
                return default
        return obj

    # Critic scores → divergence
    validations = _get(moe_result, "expert_validations", default={})
    if isinstance(validations, dict):
        scores = [
            v.get("score", 0) if isinstance(v, dict) else getattr(v, "score", 0)
            for v in validations.values()
            if v is not None
        ]
    else:
        scores = []

    if len(scores) >= 2:
        signals["critic_divergence_score"] = int(max(scores) - min(scores))

    # Synthesis quality / fallback
    synthesis_quality = _get(moe_result, "synthesis_quality", default="UNKNOWN")
    if synthesis_quality:
        signals["synthesis_quality"] = str(synthesis_quality)
        signals["fallback_triggered"] = str(synthesis_quality).upper() == "FALLBACK"

    # Confidence swing (final_confidence vs base)
    final_conf = _get(moe_result, "final_confidence", default=None)
    base_conf = _get(moe_result, "base_confidence", default=None)
    if final_conf is not None and base_conf is not None:
        try:
            signals["confidence_swing"] = round(abs(float(final_conf) - float(base_conf)), 2)
        except (TypeError, ValueError):
            pass

    # Contradiction ratio (recommendations that carry a "contested" / "contradicted" flag)
    recs = _get(moe_result, "consensus_recommendations", default=[])
    if recs and isinstance(recs, list):
        contested = sum(
            1 for r in recs
            if (r.get("contested") if isinstance(r, dict) else getattr(r, "contested", False))
        )
        signals["contradiction_ratio"] = round(contested / len(recs), 2)

    # Severity
    div = signals["critic_divergence_score"]
    if signals["fallback_triggered"] or div > 40:
        signals["severity"] = "HIGH"
    elif div > 20 or signals["confidence_swing"] > 15:
        signals["severity"] = "MEDIUM"

    return signals


def save_governance_signals(signals: GovernanceSignals, report_dir: str) -> None:
    """Write governance_signals.json to the report directory. Never raises."""
    try:
        out_path = Path(report_dir) / "governance_signals.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(signals.to_dict(), indent=2))
        logger.debug(f"Governance signals saved to {out_path}")
    except Exception as exc:
        logger.warning(f"Could not save governance_signals.json: {exc}")
