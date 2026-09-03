"""
Terraform adapter — converts .tf HCL or plan.json to ArchitectureGraph.

Handles:
  - .tf files: regex-based resource block parser (no python-hcl2 dep; uses it if available)
  - plan.json: Terraform plan output (resource_changes + planned_values)

No new dependencies required for .tf files. plan.json uses stdlib json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from chatbot.adapters.base import ArchEdge, ArchitectureGraph, ArchNode, BaseAdapter, NodeType
from chatbot.adapters.registry import register

# ── resource type → node type mapping ────────────────────────────────────────

_SERVICE_PREFIXES = (
    "aws_lambda_function", "aws_ecs_service", "aws_ecs_task_definition",
    "aws_eks_node_group", "aws_eks_cluster", "aws_elastic_beanstalk",
    "aws_apprunner", "aws_api_gateway_rest_api", "aws_api_gateway_v2_api",
    "aws_lb_listener", "aws_cloudfront_distribution", "aws_iam_role",
    "aws_iam_policy", "aws_security_group", "google_cloudfunctions",
    "google_cloud_run", "azurerm_app_service", "azurerm_function_app",
)
_NETWORK_PREFIXES = (
    "aws_alb", "aws_lb", "aws_elb", "aws_vpc", "aws_subnet",
    "aws_internet_gateway", "aws_nat_gateway", "aws_route_table",
    "aws_api_gateway", "azurerm_application_gateway", "google_compute_network",
)
_DATABASE_PREFIXES = (
    "aws_db_instance", "aws_rds_cluster", "aws_dynamodb_table",
    "aws_elasticache", "aws_redshift_cluster", "azurerm_sql",
    "azurerm_cosmos", "google_sql_database", "google_spanner",
    "google_bigtable",
)
_STORAGE_PREFIXES = (
    "aws_s3_bucket", "aws_efs_file_system", "aws_fsx",
    "azurerm_storage_account", "google_storage_bucket",
)
_QUEUE_PREFIXES = (
    "aws_sqs_queue", "aws_sns_topic", "aws_kinesis", "aws_msk_cluster",
    "azurerm_servicebus", "google_pubsub",
)
_EXTERNAL_PREFIXES = (
    "aws_route53", "aws_acm_certificate", "aws_wafv2", "aws_shield",
    "aws_cloudwatch", "aws_sns_topic_subscription",
)


def _resource_type_to_node_type(resource_type: str) -> NodeType:
    rt = resource_type.lower()
    for p in _DATABASE_PREFIXES:
        if rt.startswith(p):
            return "database"
    for p in _STORAGE_PREFIXES:
        if rt.startswith(p):
            return "storage"
    for p in _QUEUE_PREFIXES:
        if rt.startswith(p):
            return "queue"
    for p in _NETWORK_PREFIXES:
        if rt.startswith(p):
            return "network"
    for p in _EXTERNAL_PREFIXES:
        if rt.startswith(p):
            return "external"
    for p in _SERVICE_PREFIXES:
        if rt.startswith(p):
            return "service"
    return "service"  # default: most terraform resources are services


def _human_label(resource_type: str, resource_name: str) -> str:
    """Convert aws_lambda_function.my_handler → My Handler (Lambda)."""
    parts = resource_type.split("_")
    kind = " ".join(p.capitalize() for p in parts[2:]) if len(parts) > 2 else resource_type
    name = resource_name.replace("_", " ").replace("-", " ").title()
    return f"{name} ({kind})" if kind else name


# ── .tf HCL parser (regex) ────────────────────────────────────────────────────

_RESOURCE_BLOCK = re.compile(
    r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
    re.MULTILINE,
)
_REFERENCE = re.compile(
    r'\b([a-z][a-z0-9_]+\.[a-z][a-z0-9_]+)\.',  # e.g. aws_db_instance.main.
)
_DEPENDS_ON = re.compile(
    r'depends_on\s*=\s*\[([^\]]*)\]',
    re.DOTALL,
)


def _parse_tf(content: str) -> Tuple[List[ArchNode], List[ArchEdge]]:
    resources: Dict[str, Tuple[str, str]] = {}  # "TYPE.NAME" → (type, name)
    for m in _RESOURCE_BLOCK.finditer(content):
        rtype, rname = m.group(1), m.group(2)
        key = f"{rtype}.{rname}"
        resources[key] = (rtype, rname)

    nodes = [
        ArchNode(
            id=key,
            label=_human_label(rtype, rname),
            node_type=_resource_type_to_node_type(rtype),
        )
        for key, (rtype, rname) in resources.items()
    ]

    # Edges from attribute references
    seen_edges: Set[Tuple[str, str]] = set()
    edges: List[ArchEdge] = []

    for ref_match in _REFERENCE.finditer(content):
        ref = ref_match.group(1)  # e.g. "aws_db_instance.main"
        if ref in resources:
            # find which resource block this reference appears inside
            start = ref_match.start()
            # find the nearest preceding resource block
            last_block: Optional[str] = None
            for bm in _RESOURCE_BLOCK.finditer(content):
                if bm.start() < start:
                    last_block = f"{bm.group(1)}.{bm.group(2)}"
                else:
                    break
            if last_block and last_block != ref and (last_block, ref) not in seen_edges:
                seen_edges.add((last_block, ref))
                edges.append(ArchEdge(source=last_block, target=ref))

    # Edges from explicit depends_on
    for dep_match in _DEPENDS_ON.finditer(content):
        targets_raw = dep_match.group(1)
        dep_start = dep_match.start()
        last_block = None
        for bm in _RESOURCE_BLOCK.finditer(content):
            if bm.start() < dep_start:
                last_block = f"{bm.group(1)}.{bm.group(2)}"
            else:
                break
        if not last_block:
            continue
        for ref in re.findall(r'[a-z][a-z0-9_]+\.[a-z][a-z0-9_]+', targets_raw):
            if ref in resources and (last_block, ref) not in seen_edges:
                seen_edges.add((last_block, ref))
                edges.append(ArchEdge(source=last_block, target=ref, label="depends_on"))

    return nodes, edges


# ── plan.json parser ──────────────────────────────────────────────────────────

def _parse_plan_json(data: Dict) -> Tuple[List[ArchNode], List[ArchEdge]]:
    resources: Dict[str, ArchNode] = {}

    # From resource_changes
    for rc in data.get("resource_changes", []):
        addr = rc.get("address", "")  # e.g. "aws_lambda_function.handler"
        parts = addr.split(".")
        if len(parts) < 2:
            continue
        rtype, rname = parts[0], parts[1]
        if rc.get("change", {}).get("actions") == ["delete"]:
            continue
        resources[addr] = ArchNode(
            id=addr,
            label=_human_label(rtype, rname),
            node_type=_resource_type_to_node_type(rtype),
        )

    # Also from planned_values if resource_changes is empty
    pv = data.get("planned_values", {}).get("root_module", {})
    for res in pv.get("resources", []):
        addr = res.get("address", "")
        if addr in resources:
            continue
        rtype = res.get("type", "")
        rname = res.get("name", "")
        resources[addr] = ArchNode(
            id=addr,
            label=_human_label(rtype, rname),
            node_type=_resource_type_to_node_type(rtype),
        )

    nodes = list(resources.values())
    edges: List[ArchEdge] = []
    return nodes, edges


# ── adapter ───────────────────────────────────────────────────────────────────

class TerraformAdapter(BaseAdapter):
    source_formats = ["tf", "tf.json"]

    def can_handle(self, filename: str, content_peek: bytes) -> bool:
        name = Path(filename).name.lower()
        if name.endswith(".tf"):
            return True
        if name.endswith(".json"):
            text = content_peek.decode("utf-8", errors="ignore")
            return '"plan_format_version"' in text or '"resource_changes"' in text
        return False

    def extract(self, content: str | bytes, filename: str = "") -> ArchitectureGraph:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        name = Path(filename).name.lower()
        if name.endswith(".json"):
            try:
                data = json.loads(content)
                nodes, edges = _parse_plan_json(data)
                fmt = "terraform_plan"
            except json.JSONDecodeError:
                nodes, edges = _parse_tf(content)
                fmt = "terraform"
        else:
            # Try python-hcl2 if available, fall back to regex
            try:
                import hcl2  # type: ignore
                import io
                data = hcl2.load(io.StringIO(content))
                nodes, edges = _parse_hcl2(data)
                fmt = "terraform_hcl2"
            except ImportError:
                nodes, edges = _parse_tf(content)
                fmt = "terraform"

        title = Path(filename).stem or "terraform"
        return ArchitectureGraph(
            title=title,
            nodes=nodes,
            edges=edges,
            source_format=fmt,
            adapter_metadata={
                "filename": filename,
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )


def _parse_hcl2(data: Dict) -> Tuple[List[ArchNode], List[ArchEdge]]:
    """Parse python-hcl2 output dict."""
    resources: Dict[str, ArchNode] = {}
    for rtype, instances in data.get("resource", {}).items():
        for rname, _ in instances.items():
            key = f"{rtype}.{rname}"
            resources[key] = ArchNode(
                id=key,
                label=_human_label(rtype, rname),
                node_type=_resource_type_to_node_type(rtype),
            )
    return list(resources.values()), []


# Self-register
register(TerraformAdapter())
