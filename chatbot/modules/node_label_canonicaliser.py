"""
Node Label Canonicaliser

Maps synonym/variant node labels to the canonical keywords that
TRAVERSAL_TECHNIQUES, TARGET_TECHNIQUES, and the validator keyword lists
recognise. One canonical source of truth — eliminates multi-file keyword scatter.

Usage:
    from chatbot.modules.node_label_canonicaliser import canonicalise
    label_for_matching = canonicalise(node_label)

The returned string is NOT stored — it is used only for technique/validator
matching. Display labels remain unchanged.

Synonym → canonical-keyword mapping rules:
- Keys are lowercased substrings / full labels (longest match wins)
- Values are the canonical keyword used in TRAVERSAL_TECHNIQUES or keyword lists
- Order matters: more specific entries first to prevent short keys swallowing them
"""

from typing import Dict

# Ordered list of (synonym_fragment, canonical_keyword).
# Applied left-to-right; first match wins.
# Longer / more specific patterns must precede shorter ones.
_SYNONYM_PAIRS: list = [
    # ── Human-entry synonyms ─────────────────────────────────────────────────
    ("end user",         "user"),
    ("end-user",         "user"),
    ("internet user",    "user"),
    ("global user",      "user"),
    ("external user",    "user"),
    ("public user",      "user"),
    ("citizen",          "user"),
    ("govstaff",         "user"),
    ("gov staff",        "user"),
    ("gov user",         "user"),
    ("tenant user",      "user"),
    ("customer",         "user"),
    ("visitor",          "user"),
    ("staff",            "user"),
    ("operator",         "user"),
    ("person",           "user"),
    ("browser",          "user"),
    ("workstation",      "user"),
    ("laptop",           "user"),
    ("desktop",          "user"),
    ("employee",         "user"),

    # ── Database synonyms ────────────────────────────────────────────────────
    ("primary database", "database"),
    ("replica database", "database"),
    ("on-prem database", "database"),
    ("user database",    "database"),
    ("user db",          "database"),
    ("order db",         "database"),
    ("payment db",       "database"),
    ("inventory db",     "database"),
    ("shared database",  "database"),
    ("state database",   "database"),
    ("corporate database","database"),
    ("eu replica db",    "database"),
    ("us primary db",    "database"),
    (" replica db",      "database"),
    (" primary db",      "database"),
    ("database statefulset", "database"),
    ("database tool",    "database"),
    ("database:",        "database"),   # "database: mysql 8.0"
    ("database -",       "database"),   # "database - encrypted"
    ("database with",    "database"),   # "database with encryption"
    ("firestore",        "database"),
    ("dynamodb",         "database"),
    ("cosmosdb",         "database"),
    ("bigtable",         "database"),
    ("spanner",          "database"),
    ("rds",              "database"),
    ("aurora",           "database"),

    # ── Storage / cloud storage ──────────────────────────────────────────────
    ("data lake",        "storage"),
    ("data warehouse",   "warehouse"),
    ("data store",       "storage"),
    ("object store",     "storage"),
    ("blob store",       "storage"),
    ("pub/sub",          "queue"),
    ("pubsub",           "queue"),
    ("event hub",        "queue"),
    ("sns",              "queue"),
    ("sqs",              "queue"),

    # ── Server / application synonyms ────────────────────────────────────────
    ("app server",       "server"),
    ("appserver",        "server"),
    ("web server",       "server"),
    ("webserver",        "server"),
    ("backend server",   "server"),
    ("nginx",            "server"),
    ("apache",           "server"),
    ("tomcat",           "server"),
    ("iis",              "server"),
    ("spring",           "application"),
    ("flask",            "application"),
    ("django",           "application"),
    ("express",          "application"),
    ("rails",            "application"),
    ("node app",         "application"),
    ("nodeapp",          "application"),

    # ── Load balancer / CDN / WAF synonyms ───────────────────────────────────
    ("alb",              "load balancer"),
    ("elb",              "load balancer"),
    ("nlb",              "load balancer"),
    ("ingress controller","load balancer"),
    ("ingress",          "load balancer"),
    ("waf",              "firewall"),
    ("ddos protection",  "firewall"),
    ("ddos",             "firewall"),
    ("cloudfront",       "cdn"),
    ("edge location",    "cdn"),
    ("direct connect",   "vpn"),
    ("expressroute",     "vpn"),
    ("private link",     "vpn"),

    # ── Auth / Identity synonyms ─────────────────────────────────────────────
    ("oauth",            "auth"),
    ("oidc",             "auth"),
    ("saml",             "auth"),
    ("identity provider","identity"),
    ("idp",              "identity"),
    ("active dir",       "active directory"),
    ("ad server",        "active directory"),
    ("ldap server",      "ldap"),

    # ── Monitoring / Logging synonyms ────────────────────────────────────────
    ("audit log",        "audit"),
    ("access log",       "log"),
    ("event log",        "log"),
    ("cloud watch",      "monitor"),
    ("cloudwatch",       "monitor"),
    ("prometheus",       "monitor"),
    ("grafana",          "monitor"),
    ("datadog",          "siem"),
    ("splunk",           "siem"),

    # ── Partner / tenant synonyms ────────────────────────────────────────────
    ("partner",          "partner"),
    ("tenant",           "tenant"),
    ("third-party",      "partner"),
    ("third party",      "partner"),
    ("external provider","partner"),
    ("payment provider", "partner"),
    ("stripe",           "partner"),
    ("vendor",           "partner"),
    ("supplier",         "supplier"),

    # ── IoT / physical synonyms ──────────────────────────────────────────────
    ("iot device",       "sensor"),
    ("iot hub",          "sensor"),
    ("rfid",             "sensor"),
    ("door controller",  "controller"),
    ("video surveillance","sensor"),
    ("camera",           "sensor"),
    ("plc",              "controller"),
    ("scada",            "controller"),
    ("hmi",              "controller"),

    # ── AI/ML synonyms ───────────────────────────────────────────────────────
    ("ml model",         "llm"),
    ("ai model",         "llm"),
    ("model endpoint",   "llm"),
    ("inference endpoint","llm"),
    ("openai",           "llm"),
    ("bedrock",          "llm"),
    ("vertex ai",        "llm"),
    ("sagemaker",        "llm"),

    # ── Blockchain / peer synonyms ───────────────────────────────────────────
    ("peer node",        "server"),
    ("consensus engine", "server"),
    ("validator node",   "server"),
    ("blockchain node",  "server"),

    # ── Dashboard / BI synonyms ──────────────────────────────────────────────
    # Note: "bi" in TRAVERSAL_TECHNIQUES already matches "bi dashboard" as substring.
    # "dashboard" alone is NOT mapped — prevents "bi dashboard" → "bi bi" double-sub.
    ("data sources",     "storage"),
]

# Build lookup as ordered list (longest key first for greedy matching)
_SORTED_PAIRS: list = sorted(_SYNONYM_PAIRS, key=lambda x: -len(x[0]))


def canonicalise(label: str) -> str:
    """
    Return a normalised version of *label* for keyword matching.

    Lowercases the input, then replaces the first matching synonym fragment
    with its canonical keyword. The result is used only for matching — never
    stored or displayed.

    Examples:
        canonicalise("ALB")               → "load balancer"
        canonicalise("Primary Database")  → "database"
        canonicalise("CitizenPortal")     → "userportal"
        canonicalise("Agent Orchestrator")→ "agent orchestrator"  (no change)
    """
    lower = label.lower().strip()
    # Strip newlines / formatting artefacts common in diagram labels
    lower = lower.replace("\n", " ").replace("\\n", " ")
    for synonym, canonical in _SORTED_PAIRS:
        if synonym in lower:
            lower = lower.replace(synonym, canonical, 1)
            break  # first match wins
    return lower
