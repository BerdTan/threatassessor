"""
Mermaid Parser - Deterministic graph extraction from Mermaid flowchart syntax.

This parser is the foundation of Phase 3A. It must work 100% of the time
without LLM dependency.

Supported syntax:
- flowchart TB/TD/LR/RL
- Nodes: [label], (label), ((label)), [(label)], {{label}}
- Edges: -->, ---, <-->, ---|label|-->
- Subgraphs: subgraph Name ... end

Key Design Principles:
1. Deterministic (no LLM, no randomness)
2. Robust (handles edge cases, special characters)
3. Validated (test with 20 diverse .mmd files)
"""

import re
from typing import Dict, List, Tuple, Optional


class MermaidParser:
    """Parse Mermaid flowchart syntax into graph representation."""

    def __init__(self):
        self.nodes = {}  # {node_id: {label, shape, subgraph}}
        self.edges = []  # [{source, target, label}]
        self.subgraphs = {}  # {name: [node_ids]}
        self.direction = None  # TB, LR, etc.

    def parse(self, mermaid_text: str) -> Dict:
        """
        Parse Mermaid flowchart into graph representation.

        Args:
            mermaid_text: Mermaid flowchart syntax

        Returns:
            {
                "nodes": {node_id: {label, shape, subgraph}},
                "edges": [{source, target, label}],
                "subgraphs": {name: [node_ids]},
                "direction": "TB"|"LR"|etc,
                "stats": {node_count, edge_count, subgraph_count}
            }
        """
        self.nodes = {}
        self.edges = []
        self.subgraphs = {}
        self.direction = None

        lines = mermaid_text.strip().split('\n')
        current_subgraph = None

        for line in lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('%%'):
                continue

            # Parse flowchart direction
            if line.startswith('flowchart') or line.startswith('graph'):
                self.direction = self._parse_direction(line)
                continue

            # Parse subgraph start
            if line.startswith('subgraph'):
                current_subgraph = self._parse_subgraph_start(line)
                continue

            # Parse subgraph end
            if line == 'end':
                current_subgraph = None
                continue

            # Parse node definitions and edges
            if '-->' in line or '---' in line or '<-->' in line:
                self._parse_edge(line, current_subgraph)
            elif '[' in line or '(' in line or '{' in line:
                self._parse_node_definition(line, current_subgraph)

        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "subgraphs": self.subgraphs,
            "direction": self.direction,
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "subgraph_count": len(self.subgraphs),
            }
        }

    def _parse_direction(self, line: str) -> str:
        """Extract flowchart direction (TB, LR, etc.)"""
        parts = line.split()
        if len(parts) >= 2:
            return parts[1].upper()
        return "TB"  # Default

    def _parse_subgraph_start(self, line: str) -> str:
        """Extract subgraph name."""
        # Format: subgraph Name or subgraph Name[Display Label]
        match = re.match(r'subgraph\s+(\w+)(?:\[(.*?)\])?', line)
        if match:
            subgraph_id = match.group(1)
            display_name = match.group(2) if match.group(2) else subgraph_id
            self.subgraphs[subgraph_id] = {
                "display_name": display_name,
                "nodes": []
            }
            return subgraph_id
        return None

    def _parse_node_definition(self, line: str, current_subgraph: Optional[str] = None):
        """
        Parse node definition.

        Formats:
        - Node1[Label]
        - Node2(Label)
        - Node3((Label))
        - Node4[(Label)]
        - Node5{{Label}}
        """
        # Extract node_id and label
        # Pattern: NodeID followed by shape brackets
        patterns = [
            (r'(\w+)\[\[([^\]]+)\]\]', 'subroutine'),  # [[label]]
            (r'(\w+)\[\(([^\]]+)\)\]', 'cylinder'),    # [(label)]
            (r'(\w+)\(\(([^\)]+)\)\)', 'circle'),      # ((label))
            (r'(\w+)\{{([^\}]+)\}}', 'hexagon'),       # {{label}}
            (r'(\w+)\["([^"]+)"\]', 'rectangle'),      # ["label with special chars"]
            (r'(\w+)\[([^\]]+)\]', 'rectangle'),       # [label]
            (r'(\w+)\(([^\)]+)\)', 'rounded'),         # (label)
        ]

        for pattern, shape in patterns:
            match = re.search(pattern, line)
            if match:
                node_id = match.group(1)
                label = match.group(2)

                # Add node
                self.nodes[node_id] = {
                    "label": label,
                    "shape": shape,
                    "subgraph": current_subgraph
                }

                # Add to subgraph
                if current_subgraph and current_subgraph in self.subgraphs:
                    self.subgraphs[current_subgraph]["nodes"].append(node_id)

                break

    def _parse_edge(self, line: str, current_subgraph: Optional[str] = None):
        """
        Parse edge (connection between nodes).

        Formats:
        - Node1 --> Node2
        - Node1 --- Node2
        - Node1 <--> Node2
        - Node1 -->|Label| Node2
        - Node1 ---|Label|--- Node2
        """
        # Extract edge components
        # Pattern: Source [edge_type with optional label] Target

        # Try bidirectional first
        if '<-->' in line:
            parts = line.split('<-->')
            if len(parts) == 2:
                source = parts[0].strip().split()[-1]
                target = parts[1].strip().split()[0]
                self._add_edge(source, target, label=None, bidirectional=True, current_subgraph=current_subgraph)
                return

        # Try directed arrow
        if '-->' in line:
            # Check for label: -->|Label|
            label_match = re.search(r'-->\|([^\|]+)\|', line)
            if label_match:
                label = label_match.group(1)
                parts = line.split('-->|')
                source = parts[0].strip().split()[-1]
                target_part = parts[1].split('|', 1)[1].strip()
                target = target_part.split()[0]
            else:
                parts = line.split('-->')
                if len(parts) == 2:
                    source = parts[0].strip().split()[-1]
                    target = parts[1].strip().split()[0]
                    label = None
                else:
                    return

            self._add_edge(source, target, label=label, bidirectional=False, current_subgraph=current_subgraph)
            return

        # Try undirected line
        if '---' in line:
            # Check for label: ---|Label|---
            label_match = re.search(r'---\|([^\|]+)\|---', line)
            if label_match:
                label = label_match.group(1)
                parts = line.split('---|')
                source = parts[0].strip().split()[-1]
                target_part = parts[1].split('|', 1)[1].strip()
                target = target_part.split()[0]
            else:
                parts = line.split('---')
                if len(parts) == 2:
                    source = parts[0].strip().split()[-1]
                    target = parts[1].strip().split()[0]
                    label = None
                else:
                    return

            self._add_edge(source, target, label=label, bidirectional=False, current_subgraph=current_subgraph)

    def _add_edge(self, source: str, target: str, label: Optional[str], bidirectional: bool, current_subgraph: Optional[str]):
        """Add edge to graph."""
        # Create nodes if they don't exist (edge-only definition)
        if source not in self.nodes:
            self.nodes[source] = {
                "label": source,  # Use ID as label
                "shape": "rectangle",
                "subgraph": current_subgraph
            }
            if current_subgraph and current_subgraph in self.subgraphs:
                self.subgraphs[current_subgraph]["nodes"].append(source)

        if target not in self.nodes:
            self.nodes[target] = {
                "label": target,  # Use ID as label
                "shape": "rectangle",
                "subgraph": current_subgraph
            }
            if current_subgraph and current_subgraph in self.subgraphs:
                self.subgraphs[current_subgraph]["nodes"].append(target)

        # Add edge
        edge = {
            "source": source,
            "target": target,
            "label": label,
            "bidirectional": bidirectional
        }
        self.edges.append(edge)

        # Add reverse edge if bidirectional
        if bidirectional:
            reverse_edge = {
                "source": target,
                "target": source,
                "label": label,
                "bidirectional": True
            }
            self.edges.append(reverse_edge)

    def get_adjacency_list(self) -> Dict[str, List[str]]:
        """
        Build adjacency list for graph traversal algorithms (BFS, DFS).

        Returns:
            {node_id: [neighbor_node_ids]}
        """
        adjacency = {node_id: [] for node_id in self.nodes.keys()}

        for edge in self.edges:
            source = edge["source"]
            target = edge["target"]

            if target not in adjacency[source]:
                adjacency[source].append(target)

        return adjacency


def parse_mermaid_file(file_path: str) -> Dict:
    """
    Parse Mermaid file and return graph representation.

    Args:
        file_path: Path to .mmd file

    Returns:
        Graph dict from MermaidParser.parse()
    """
    with open(file_path, 'r') as f:
        mermaid_text = f.read()

    parser = MermaidParser()
    return parser.parse(mermaid_text)


if __name__ == "__main__":
    # Test with simple example
    sample = """
flowchart TB
    Internet((Internet))
    ALB[Application Load Balancer]
    App[Application Server]
    DB[(Database)]

    Internet --> ALB
    ALB --> App
    App --> DB
"""

    parser = MermaidParser()
    result = parser.parse(sample)

    print("Nodes:", len(result["nodes"]))
    print("Edges:", len(result["edges"]))
    print("Direction:", result["direction"])

    for node_id, node_data in result["nodes"].items():
        print(f"  {node_id}: {node_data['label']} ({node_data['shape']})")

    for edge in result["edges"]:
        label_str = f" [{edge['label']}]" if edge['label'] else ""
        print(f"  {edge['source']} --> {edge['target']}{label_str}")
