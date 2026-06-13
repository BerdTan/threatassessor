"""
story_caster.py - Deterministic user story generation from architecture graphs.

Two story levels:
  edge micro-stories  — one per MMD edge, granular critic context
  journey macro-stories — one per ranked attack path (co-generated, same BFS path)

Co-generation guarantee: journey stories share the exact path list from
expected_attack_paths so US == AP structurally. Uncorroborated paths (no
human actor on the path) are flagged no_user_story=True for critic escalation.

Fully deterministic by default. LLM enrichment is opt-in (use_llm=True).
"""

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-role inference from node label keywords
# ---------------------------------------------------------------------------

# Specific roles checked before generic-origin fallback.
# "internet" / "external" are NOT in this list — handled by destination context.
_ROLE_RULES = [
    (["admin", "ops", "console", "management", "sysadmin", "operator"], "system administrator"),
    (["partner", "vendor", "3rd", "third", "supplier"],                  "partner/third party"),
    (["attacker", "threat", "adversary", "hacker"],                      "threat actor"),
    (["service", "api", "worker", "job", "daemon", "function", "lambda", "microservice"], "service account"),
    (["user", "customer", "client", "browser", "mobile", "app", "frontend", "portal", "web"], "end user"),
]

# When source is a generic internet/external origin, refine role from destination label.
_DEST_ROLE_REFINEMENT = [
    (["admin", "ops", "console", "management"],          "system administrator"),
    (["partner", "vendor", "supplier"],                  "partner user"),
    (["api", "gateway"],                                  "API consumer"),
    (["mobile", "ios", "android"],                       "mobile user"),
    (["payment", "checkout", "commerce", "shop"],        "customer"),
    (["portal", "web", "browser", "frontend", "app"],   "web user"),
]

# Bare generic-origin keywords (no attached human qualifier)
_GENERIC_ORIGIN_RE = re.compile(r"\binternet\b|\bexternal\b", re.IGNORECASE)

# Human group nouns — when the node label itself names the people,
# use it directly as the story subject rather than prepending an inferred role.
# Pattern: labels containing these as standalone words (not part of a system name).
_HUMAN_GROUP_WORDS = re.compile(
    r"\busers?\b|\bcustomers?\b|\bclients?\b|\badmins?\b|\boperators?\b"
    r"|\bpartners?\b|\bvendors?\b|\bteam\b|\bstaff\b|\bemployees?\b"
    r"|\bdevelopers?\b|\banalysts?\b|\bauditors?\b|\bmanagers?\b",
    re.IGNORECASE,
)

# System/channel entry points — these name a technical access point, not a group of people.
# When the actor node matches these, the inferred role is the real subject.
_SYSTEM_ENTRY_RE = re.compile(
    r"\bvpn\b|remote.?access|jump.?server|bastion|\bgateway\b|\bportal\b"
    r"|\bapp\b|\bapplication\b|\bservice\b|\bapi\b|\bclient\b|\bbrowser\b"
    r"|\bmobile\b|\bdevice\b|\bendpoint\b|\binternet\b|\bexternal\b"
    r"|\bconsole\b|\bmanagement\b|\bserver\b|\bsystem\b|\bplatform\b|\binterface\b",
    re.IGNORECASE,
)


def _actor_is_human_group(label: str) -> bool:
    """
    True when the node label directly names a human group (use label as subject).
    False when it names a system/channel (use inferred role as subject, label as 'via X').

    Examples:
      'Internet Users'    → True  (the label IS the humans)
      'Admin Team'        → True
      'Customers'         → True
      'VPN Remote Access' → False (a system channel)
      'Internet'          → False (generic entry point)
      'Mobile App'        → False (a system, not humans)
      'Customer Portal'   → False (a portal system, not a group)
    """
    # If the label contains human group words AND is short (≤ 3 tokens),
    # treat it as a direct human group noun.
    # Longer labels with "Portal", "App", "Service" etc. are systems even if
    # they contain "customer" or "user".
    tokens = label.split()
    has_human = bool(_HUMAN_GROUP_WORDS.search(label))
    has_system = bool(_SYSTEM_ENTRY_RE.search(label))

    human_stems = {"user","customer","client","admin","operator","partner",
                   "vendor","team","staff","employee","developer","analyst","manager"}

    if not has_human:
        return False

    # Check last token — if it's a human noun, the label names a group of people
    # regardless of any qualifier words earlier (e.g. "Internet Users", "External Admins")
    last = tokens[-1].lower().rstrip('s')  # singularise
    if last in human_stems:
        return True

    # Last token is not a human noun — if any system word is present it's a system node
    if has_system:
        return False

    # Human word present, no system qualifier, non-human last token
    # e.g. "Admin Team" — "team" not in human_stems but label is clearly a group
    # Catch team/staff/group as collective nouns
    collective = {"team", "staff", "group", "crew", "squad", "department", "dept"}
    return last in collective

_ACTOR_KEYWORDS = [
    "user", "customer", "client", "browser", "mobile", r"\bapp\b", "frontend",
    "portal", "internet", "external", "admin", "ops", r"\bconsole\b", "management",
    "operator", "partner", "vendor", r"\b3rd\b", "third",
]

_ACTOR_RE = re.compile("|".join(_ACTOR_KEYWORDS), re.IGNORECASE)


def _infer_user_role(label: str) -> str:
    """Role from source label alone (journey stories where actor node is already identified)."""
    lower = label.lower()
    for keywords, role in _ROLE_RULES:
        if any(k in lower for k in keywords):
            return role
    # Generic internet/external with no qualifier → plain end user
    if _GENERIC_ORIGIN_RE.search(label):
        return "end user"
    return "user"


def _infer_user_role_contextual(src_label: str, dest_label: str) -> str:
    """
    Role inference using source + destination context.
    When source is a bare generic origin (Internet, External) or a transparent
    infra layer, look at the destination to produce a richer role label.
    """
    # Specific role keywords on source take priority
    lower_src = src_label.lower()
    for keywords, role in _ROLE_RULES:
        if any(k in lower_src for k in keywords):
            return role

    # Generic origin OR infra source — refine from destination
    if _GENERIC_ORIGIN_RE.search(src_label) or _is_infra_layer(src_label):
        lower_dest = dest_label.lower()
        for keywords, role in _DEST_ROLE_REFINEMENT:
            if any(k in lower_dest for k in keywords):
                return role
        for keywords, role in _ROLE_RULES:
            if any(k in lower_dest for k in keywords):
                return role
        return "end user"

    # Unknown source (no keywords matched) — try destination before falling back
    lower_dest = dest_label.lower()
    for keywords, role in _ROLE_RULES:
        if any(k in lower_dest for k in keywords):
            return role

    return "user"


def _is_actor_node(label: str) -> bool:
    return bool(_ACTOR_RE.search(label))


# ---------------------------------------------------------------------------
# Transparent infrastructure layer detection + see-through
# ---------------------------------------------------------------------------

_TRANSPARENT_INFRA_RE = re.compile(
    r"\bddos\b|waf\b|\bfirewall\b|\bcdn\b|content.?delivery|reverse.?proxy|\bproxy\b"
    r"|traffic.?manager|ingress.?controller|load.?balan|\bnlb\b",
    re.IGNORECASE,
)


def _is_infra_layer(label: str) -> bool:
    """True for transparent protection/routing layers users don't interact with directly."""
    return bool(_TRANSPARENT_INFRA_RE.search(label))


def _resolve_effective_target(
    target_id: str,
    nodes: Dict[str, Dict],
    adj: Dict[str, List[str]],
    max_hops: int = 3,
) -> tuple:
    """
    If target is a transparent infra layer, follow edges downstream to find
    the actual service the user cares about.

    Returns (effective_label, via_str | None).
    e.g. "DDoS Protection" → "WAF" → "Web Application"
         returns ("Web Application", "DDoS Protection → WAF")
    """
    visited = {target_id}
    current_id = target_id
    via_chain: List[str] = []

    for _ in range(max_hops):
        label = nodes.get(current_id, {}).get("label", current_id)
        if not _is_infra_layer(label):
            via_str = " → ".join(via_chain) if via_chain else None
            return label, via_str
        via_chain.append(label)
        next_nodes = [n for n in adj.get(current_id, []) if n not in visited]
        if not next_nodes:
            break
        current_id = next_nodes[0]
        visited.add(current_id)

    # Fallback: original target as-is
    return nodes.get(target_id, {}).get("label", target_id), None


# ---------------------------------------------------------------------------
# Story type classification
# ---------------------------------------------------------------------------

_STORY_TYPE_RULES = [
    (["auth", "login", "sso", "token", "oauth", "iam", "identity", "saml", "credential"], "auth_flow"),
    (["admin", "management", "console", "ops", "config", "control"], "admin_access"),
    (["read", "get", "fetch", "query", "search", "retrieve", "download"], "data_read"),
    (["write", "post", "put", "upload", "insert", "update", "create", "submit"], "data_write"),
    (["internet", "external", "inbound", "ingress", "entry", "public"], "external_ingress"),
    (["egress", "outbound", "export", "send"], "external_egress"),
    (["db", "database", "store", "cache", "queue", "storage", "bucket"], "data_read"),
]

_DATA_CLASS_RULES = [
    (["password", "credential", "key", "secret", "token", "cert", "auth"], "credentials"),
    (["pii", "personal", "user", "customer", "profile", "email", "phone"], "pii"),
    (["config", "control", "admin", "policy", "setting"], "control"),
]


def _classify_story_type(source_label: str, target_label: str, edge_label: Optional[str]) -> str:
    combined = " ".join(filter(None, [source_label, target_label, edge_label or ""])).lower()
    for keywords, story_type in _STORY_TYPE_RULES:
        if any(k in combined for k in keywords):
            return story_type
    return "inter_service"


def _classify_data(source_label: str, target_label: str, edge_label: Optional[str]) -> str:
    combined = " ".join(filter(None, [source_label, target_label, edge_label or ""])).lower()
    for keywords, cls in _DATA_CLASS_RULES:
        if any(k in combined for k in keywords):
            return cls
    return "generic"


def _classify_flow_direction(source_label: str, target_label: str) -> str:
    sl, tl = source_label.lower(), target_label.lower()
    if any(k in sl for k in ["internet", "external", "user", "customer", "browser", "mobile"]):
        return "inbound"
    if any(k in tl for k in ["internet", "external"]):
        return "outbound"
    if any(k in sl for k in ["admin", "ops", "management"]):
        return "admin"
    return "lateral"


# ---------------------------------------------------------------------------
# Tactic mapping by story type
# ---------------------------------------------------------------------------

_TACTIC_MAP = {
    "external_ingress": ["Initial Access"],
    "auth_flow":        ["Credential Access", "Defense Evasion"],
    "data_read":        ["Collection", "Exfiltration"],
    "data_write":       ["Impact", "Persistence"],
    "admin_access":     ["Privilege Escalation", "Lateral Movement"],
    "external_egress":  ["Exfiltration", "Command and Control"],
    "inter_service":    ["Lateral Movement"],
    "control_flow":     ["Defense Evasion"],
}


# ---------------------------------------------------------------------------
# Story text templates
# ---------------------------------------------------------------------------

def _edge_story_text(user_role: str, story_type: str, source_label: str,
                     target_label: str, edge_label: Optional[str],
                     data_classification: str) -> str:
    action = edge_label or "communicate"
    if story_type == "auth_flow":
        return (
            f"As a {user_role}, I want to authenticate via {source_label} to {target_label} "
            f"so that I can access protected resources. "
            f"If this flow is compromised, an attacker gains a valid identity and all access rights it carries."
        )
    if story_type == "data_read":
        return (
            f"As a {user_role}, I want to retrieve {edge_label or 'data'} from {target_label} "
            f"via {source_label} so that I can fulfil my business need. "
            f"If this path is exploited, an attacker can silently collect {data_classification} data."
        )
    if story_type == "data_write":
        return (
            f"As a {user_role}, I want to {action} to {target_label} via {source_label} "
            f"to persist or update information. "
            f"If this path is abused, an attacker can inject malicious data or corrupt {data_classification} records."
        )
    if story_type == "admin_access":
        return (
            f"As a {user_role}, I need administrative access to {target_label} from {source_label} "
            f"to manage the system. "
            f"If this control-plane path is abused, an attacker with lateral movement gains privileged control over {target_label}."
        )
    if story_type == "external_ingress":
        return (
            f"As a {user_role}, I need to reach {target_label} from outside the network boundary "
            f"to use the service. "
            f"This is the primary initial access surface — an attacker can exploit it to gain a foothold without internal credentials."
        )
    if story_type == "external_egress":
        return (
            f"As a {user_role}, the system needs to {action} to {target_label} "
            f"from {source_label} to deliver results. "
            f"If this egress path is hijacked, an attacker can exfiltrate data or establish a C2 channel."
        )
    # inter_service / fallback
    return (
        f"As a {user_role}, I want to {action} between {source_label} and {target_label} "
        f"to support the workflow. "
        f"If this service path is compromised, an attacker can pivot laterally to {target_label}."
    )


def _journey_story_text(user_role: str, path_labels: List[str],
                        edge_labels: List[Optional[str]],
                        target_label: str, story_type: str) -> tuple:
    """Returns (story_text, user_goal, exploitation_chain)."""
    entry = path_labels[0] if path_labels else "entry"
    mid   = path_labels[1:-1] if len(path_labels) > 2 else []
    resource = path_labels[-1] if path_labels else target_label

    # Decide how to construct the subject sentence.
    # If the actor node label IS a human group name, use it directly.
    # If it's a system/channel, the inferred role is the real subject.
    actor_is_group = _actor_is_human_group(entry)

    if actor_is_group:
        # "Internet Users connect through Web Application to reach Database."
        subject = entry          # "Internet Users", "Admin Team", "Customers"
        verb = "connect"
        from_clause = ""         # no "from X" — the label already names them
    else:
        # "A system administrator connects via VPN Remote Access to the Admin Console."
        article = "An" if user_role[0].lower() in "aeiou" else "A"
        subject = f"{article} {user_role}"
        verb = "connects"
        from_clause = f" via {entry}"

    # Mid-path intermediaries
    via_mid = f" through {' and '.join(mid)}" if mid else ""

    # User goal — from edge labels if present, else from story type
    verbs = [e for e in edge_labels if e]
    if verbs:
        user_goal = f"{' and '.join(verbs)} to reach {resource}"
    else:
        _goal_by_type = {
            "external_ingress": f"access {resource} from outside the network",
            "auth_flow":        f"authenticate and access {resource}",
            "data_read":        f"read data from {resource}",
            "data_write":       f"write data to {resource}",
            "admin_access":     f"administer {resource}",
            "external_egress":  f"send data out via {resource}",
        }
        user_goal = _goal_by_type.get(story_type, f"access {resource}")

    story_text = (
        f"{subject} {verb}{from_clause}{via_mid} to {resource}. "
        f"This is a normal, intended workflow. "
        f"An attacker who gains a foothold at {entry} can follow the same path{via_mid} "
        f"and reach {resource} — blending with legitimate traffic."
    )

    # Exploitation chain
    chain_parts = [f"Gain initial access at {entry}."]
    for i, label in enumerate(path_labels[1:], 1):
        prev = path_labels[i - 1]
        edge_verb = edge_labels[i - 1] if i - 1 < len(edge_labels) and edge_labels[i - 1] else None
        if edge_verb:
            chain_parts.append(f"Use '{edge_verb}' from {prev} to reach {label}.")
        elif i == len(path_labels) - 1:
            chain_parts.append(f"Reach target {label} — exfiltrate, encrypt, or disrupt.")
        elif i == 1:
            chain_parts.append(f"Access {label} via the initial entry point.")
        else:
            chain_parts.append(f"Move from {prev} to {label}.")

    exploitation_chain = " ".join(chain_parts)

    return story_text, user_goal, exploitation_chain


# ---------------------------------------------------------------------------
# Public API — edge micro-stories
# ---------------------------------------------------------------------------

def cast_stories(
    nodes: Dict[str, Dict],
    edges: List[Dict],
    subgraphs: Dict,
    controls_present: List[str],
    architecture_type: str,
    use_llm: bool = False,
    llm_model: Optional[str] = None,
) -> List[Dict]:
    """
    Generate edge micro-stories — one per MMD edge.

    Returns a list of story dicts (story_level='edge').
    Journey macro-stories are co-generated in cast_journey_story() alongside
    each ranked attack path and stored directly on the AP dict.
    """
    # Build forward adjacency map for infra see-through
    adj: Dict[str, List[str]] = {}
    for edge in edges:
        adj.setdefault(edge["source"], []).append(edge["target"])

    stories = []

    for edge in edges:
        src_id = edge.get("source", "")
        tgt_id = edge.get("target", "")
        edge_label = edge.get("label") or None

        src_data = nodes.get(src_id, {})
        tgt_data = nodes.get(tgt_id, {})
        src_label = src_data.get("label", src_id)
        tgt_label_raw = tgt_data.get("label", tgt_id)

        # Infra-to-infra edges (e.g. DDoS→WAF) are plumbing — no user story
        if _is_infra_layer(src_label) and _is_infra_layer(tgt_label_raw):
            stories.append({
                "story_level":    "edge",
                "edge_id":        f"{src_id}->{tgt_id}",
                "source_label":   src_label,
                "target_label":   tgt_label_raw,
                "infra_only":     True,
                "story_text":     f"Infrastructure routing: {src_label} → {tgt_label_raw}. No user-facing story — transparent protection layer.",
                "story_type":     "infra_routing",
                "threat_relevance": ["Defense Evasion"],
            })
            continue

        # Infra see-through: resolve effective target beyond transparent layers
        effective_tgt_label, via_infra = _resolve_effective_target(tgt_id, nodes, adj)
        display_tgt = (
            f"{effective_tgt_label} (via {via_infra})"
            if via_infra else effective_tgt_label
        )

        user_role = _infer_user_role_contextual(src_label, effective_tgt_label)
        story_type = _classify_story_type(src_label, effective_tgt_label, edge_label)
        flow_direction = _classify_flow_direction(src_label, effective_tgt_label)
        data_class = _classify_data(src_label, effective_tgt_label, edge_label)
        threat_relevance = _TACTIC_MAP.get(story_type, ["Lateral Movement"])

        story_text = _edge_story_text(
            user_role, story_type, src_label, display_tgt, edge_label, data_class
        )
        exploitation_consequence = story_text.split("If ")[1] if "If " in story_text else ""

        stories.append({
            "story_level":             "edge",
            "edge_id":                 f"{src_id}->{tgt_id}",
            "source_id":               src_id,
            "source_label":            src_label,
            "target_id":               tgt_id,
            "target_label":            tgt_label_raw,
            "effective_target_label":  effective_tgt_label,
            "via_infra":               via_infra,
            "edge_label":              edge_label,
            "user_role":               user_role,
            "story_text":              story_text,
            "story_type":              story_type,
            "flow_direction":          flow_direction,
            "data_classification":     data_class,
            "threat_relevance":        threat_relevance,
            "exploitation_consequence": exploitation_consequence,
        })

    logger.info(f"story_caster: generated {len(stories)} edge micro-stories")
    return stories


# ---------------------------------------------------------------------------
# Public API — journey macro-story (called per AP during path ranking)
# ---------------------------------------------------------------------------

def cast_journey_story(
    ap: Dict,
    nodes: Dict[str, Dict],
    edges: List[Dict],
    story_id: str,
) -> Dict:
    """
    Generate a single journey macro-story co-generated on the same BFS path as ap.

    Called after attack path ranking, once per AP.
    Returns a story dict (story_level='journey') with attack_path_id cross-reference.
    Sets ap['no_user_story'] = True if no human actor node is found on the path.
    """
    path = ap.get("path", [])
    if not path:
        ap["no_user_story"] = True
        return {}

    # Resolve node labels
    path_labels = [nodes.get(n, {}).get("label", n) for n in path]

    # Find actor node: first node on path with an actor keyword in its label
    actor_idx = next(
        (i for i, lbl in enumerate(path_labels) if _is_actor_node(lbl)),
        None,
    )

    if actor_idx is None:
        # No human actor — attacker-only path
        ap["no_user_story"] = True
        logger.debug(f"story_caster: {ap.get('id', story_id)} has no actor node — flagged attacker-only")
        return {
            "story_level":      "journey",
            "story_id":         story_id,
            "attack_path_id":   ap.get("id", story_id),
            "no_user_story":    True,
            "reason":           "No human actor node detected on path — likely lateral movement or infra-to-infra path.",
            "path":             path,
            "path_labels":      path_labels,
        }

    ap["no_user_story"] = False

    actor_node = path[actor_idx]
    actor_label = path_labels[actor_idx]
    resource_node = path[-1]
    resource_label = path_labels[-1]

    # Skip infra layers when resolving the effective destination for role refinement
    effective_resource_label = next(
        (lbl for lbl in reversed(path_labels) if not _is_infra_layer(lbl)),
        resource_label,
    )
    user_role = _infer_user_role_contextual(actor_label, effective_resource_label)

    # Collect edge labels along the path (in order)
    edge_map: Dict[str, Optional[str]] = {}
    for edge in edges:
        key = f"{edge['source']}->{edge['target']}"
        edge_map[key] = edge.get("label") or None

    edge_labels_on_path: List[Optional[str]] = []
    for i in range(len(path) - 1):
        key = f"{path[i]}->{path[i+1]}"
        edge_labels_on_path.append(edge_map.get(key))

    # Infer dominant story type from path
    combined = " ".join(path_labels + [e for e in edge_labels_on_path if e]).lower()
    story_type = "inter_service"
    for keywords, stype in _STORY_TYPE_RULES:
        if any(k in combined for k in keywords):
            story_type = stype
            break

    threat_relevance = _TACTIC_MAP.get(story_type, ["Lateral Movement"])

    story_text, user_goal, exploitation_chain = _journey_story_text(
        user_role, path_labels, edge_labels_on_path, resource_label, story_type
    )

    business_value = (
        f"Enables {user_role} to {user_goal} — core to the system's intended function."
    )

    story = {
        "story_level":          "journey",
        "story_id":             story_id,
        "attack_path_id":       ap.get("id", story_id),
        "actor_node":           actor_node,
        "actor_label":          actor_label,
        "resource_node":        resource_node,
        "resource_label":       resource_label,
        "path":                 path,
        "path_labels":          path_labels,
        "edge_labels_on_path":  edge_labels_on_path,
        "user_role":            user_role,
        "user_goal":            user_goal,
        "business_value":       business_value,
        "story_text":           story_text,
        "exploitation_chain":   exploitation_chain,
        "story_type":           story_type,
        "threat_relevance":     threat_relevance,
        "no_user_story":        False,
    }

    return story


# ---------------------------------------------------------------------------
# Rationale builder — replaces topology-only rationale on APs
# ---------------------------------------------------------------------------

def build_ap_rationale_from_story(
    ap: Dict,
    journey_story: Dict,
) -> str:
    """
    Build a flow narrative rationale for an AP from its co-generated journey story.
    Falls back to topology string if no story or attacker-only path.
    """
    if not journey_story or journey_story.get("no_user_story"):
        # Attacker-only path — describe it as such
        path_labels = journey_story.get("path_labels") or []
        hop_str = " → ".join(path_labels) if path_labels else " → ".join(ap.get("path", []))
        tier = ap.get("criticality_tier", "UNKNOWN")
        hops = ap.get("hop_count", len(ap.get("path", [])) - 1)
        return (
            f"[{tier}] Attacker-only path (no human actor baseline): {hop_str}. "
            f"{hops} hop{'s' if hops != 1 else ''}, criticality {ap.get('criticality', 0):.2f}. "
            f"No legitimate user traversal — behavioral anomaly detection will not catch this."
        )

    tier = ap.get("criticality_tier", "UNKNOWN")
    user_role = journey_story.get("user_role", "user")
    hop_str = " → ".join(journey_story.get("path_labels", ap.get("path", [])))
    edge_labels = [e for e in journey_story.get("edge_labels_on_path", []) if e]
    verb_phrase = " → ".join(edge_labels) if edge_labels else "traverse path"

    corroborated = not journey_story.get("no_user_story", True)
    signal = "Corroborated: user journey matches attack path." if corroborated else ""

    return (
        f"[{tier}] {hop_str}. "
        f"Legitimate use: {user_role} {verb_phrase} to reach {journey_story.get('resource_label', 'target')}. "
        f"If exploited: {journey_story.get('exploitation_chain', '')} "
        f"{signal}".strip()
    )
