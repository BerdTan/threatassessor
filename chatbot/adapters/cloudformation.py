"""
CloudFormation adapter — converts CF templates (YAML/JSON) to ArchitectureGraph.

Handles:
  - CloudFormation YAML/JSON templates (AWSTemplateFormatVersion or Resources: key)
  - CDK synth output (same structure as CloudFormation)
  - SAM templates

Uses yaml.safe_load (already in requirements). No new dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from chatbot.adapters.base import ArchEdge, ArchitectureGraph, ArchNode, BaseAdapter, NodeType
from chatbot.adapters.registry import register

# ── resource type → node type ─────────────────────────────────────────────────

_CF_SERVICE = (
    "AWS::Lambda::Function", "AWS::ECS::Service", "AWS::ECS::TaskDefinition",
    "AWS::Serverless::Function", "AWS::AppSync::GraphQLApi",
    "AWS::ApiGateway::RestApi", "AWS::ApiGatewayV2::Api",
    "AWS::ElasticBeanstalk::Application", "AWS::IAM::Role", "AWS::IAM::Policy",
    "AWS::IAM::ManagedPolicy", "AWS::EC2::Instance", "AWS::AutoScaling::AutoScalingGroup",
    "AWS::EKS::Cluster", "AWS::EKS::Nodegroup", "AWS::Cognito::UserPool",
    "AWS::Cognito::IdentityPool",
)
_CF_NETWORK = (
    "AWS::ElasticLoadBalancingV2::LoadBalancer", "AWS::ElasticLoadBalancing::LoadBalancer",
    "AWS::CloudFront::Distribution", "AWS::Route53::RecordSet",
    "AWS::EC2::VPC", "AWS::EC2::Subnet", "AWS::EC2::InternetGateway",
    "AWS::EC2::NatGateway", "AWS::EC2::RouteTable", "AWS::EC2::SecurityGroup",
    "AWS::WAFv2::WebACL",
)
_CF_DATABASE = (
    "AWS::RDS::DBInstance", "AWS::RDS::DBCluster", "AWS::DynamoDB::Table",
    "AWS::ElastiCache::CacheCluster", "AWS::ElastiCache::ReplicationGroup",
    "AWS::Redshift::Cluster", "AWS::Neptune::DBCluster",
    "AWS::DocumentDB::DBCluster",
)
_CF_STORAGE = (
    "AWS::S3::Bucket", "AWS::EFS::FileSystem", "AWS::FSx::FileSystem",
    "AWS::Glacier::Vault",
)
_CF_QUEUE = (
    "AWS::SQS::Queue", "AWS::SNS::Topic", "AWS::Kinesis::Stream",
    "AWS::MSK::Cluster", "AWS::EventSchemas::Registry",
    "AWS::Events::EventBus",
)


def _cf_type_to_node_type(cf_type: str) -> NodeType:
    for t in _CF_DATABASE:
        if cf_type.startswith(t):
            return "database"
    for t in _CF_STORAGE:
        if cf_type.startswith(t):
            return "storage"
    for t in _CF_QUEUE:
        if cf_type.startswith(t):
            return "queue"
    for t in _CF_NETWORK:
        if cf_type.startswith(t):
            return "network"
    for t in _CF_SERVICE:
        if cf_type.startswith(t):
            return "service"
    return "service"


def _short_label(logical_id: str, cf_type: str) -> str:
    """Convert LogicalResourceId + AWS::Lambda::Function → My Function (Lambda)."""
    # Extract the service name from the type, e.g. "Lambda::Function" → "Lambda Function"
    parts = cf_type.split("::")
    kind = " ".join(parts[1:]) if len(parts) > 1 else cf_type
    return f"{logical_id} ({kind})"


# ── reference extraction ──────────────────────────────────────────────────────

def _collect_refs(value: Any, refs: Set[str]) -> None:
    """Recursively find all {"Ref": ...} and {"Fn::GetAtt": [...]} values."""
    if isinstance(value, dict):
        if "Ref" in value and isinstance(value["Ref"], str):
            refs.add(value["Ref"])
        elif "Fn::GetAtt" in value:
            attr = value["Fn::GetAtt"]
            if isinstance(attr, list) and attr:
                refs.add(str(attr[0]))
            elif isinstance(attr, str):
                refs.add(attr.split(".")[0])
        else:
            for v in value.values():
                _collect_refs(v, refs)
    elif isinstance(value, list):
        for item in value:
            _collect_refs(item, refs)


def _parse_template(data: Dict) -> Tuple[List[ArchNode], List[ArchEdge]]:
    resources: Dict[str, Tuple[str, ArchNode]] = {}  # logical_id → (cf_type, node)

    for logical_id, res_def in data.get("Resources", {}).items():
        if not isinstance(res_def, dict):
            continue
        cf_type = res_def.get("Type", "AWS::Unknown::Unknown")
        node = ArchNode(
            id=logical_id,
            label=_short_label(logical_id, cf_type),
            node_type=_cf_type_to_node_type(cf_type),
            metadata={"cf_type": cf_type},
        )
        resources[logical_id] = (cf_type, node)

    nodes = [n for _, n in resources.values()]
    edges: List[ArchEdge] = []
    seen: Set[Tuple[str, str]] = set()

    for logical_id, res_def in data.get("Resources", {}).items():
        if not isinstance(res_def, dict):
            continue
        props = res_def.get("Properties", {}) or {}

        # Refs inside Properties
        refs: Set[str] = set()
        _collect_refs(props, refs)

        # DependsOn
        dep_on = res_def.get("DependsOn", [])
        if isinstance(dep_on, str):
            dep_on = [dep_on]
        refs.update(dep_on)

        for ref in refs:
            if ref in resources and ref != logical_id:
                key = (logical_id, ref)
                if key not in seen:
                    seen.add(key)
                    edges.append(ArchEdge(source=logical_id, target=ref))

    return nodes, edges


# ── adapter ───────────────────────────────────────────────────────────────────

class CloudFormationAdapter(BaseAdapter):
    source_formats = ["yaml", "yml", "json"]

    def can_handle(self, filename: str, content_peek: bytes) -> bool:
        text = content_peek.decode("utf-8", errors="ignore")
        return (
            "AWSTemplateFormatVersion" in text
            or '"AWSTemplateFormatVersion"' in text
            or "Resources:" in text
            or '"Resources"' in text and '"Type"' in text and '"AWS::' in text
        )

    def extract(self, content: str | bytes, filename: str = "") -> ArchitectureGraph:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = {}

        if not isinstance(data, dict):
            data = {}

        nodes, edges = _parse_template(data)
        title = (
            data.get("Description")
            or data.get("Metadata", {}).get("Name")
            or Path(filename).stem
            or "cloudformation"
        )

        return ArchitectureGraph(
            title=str(title)[:80],
            nodes=nodes,
            edges=edges,
            source_format="cloudformation",
            adapter_metadata={
                "filename": filename,
                "template_version": data.get("AWSTemplateFormatVersion", ""),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )


# Self-register (after TerraformAdapter so CF YAML check runs second)
register(CloudFormationAdapter())
