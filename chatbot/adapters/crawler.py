"""
RepoCrawler — walk a directory or git URL, discover architecture artifacts, merge graphs.

Used by TAclaw (POST /api/v1/taclaw/run) to autonomously assess any codebase or IaC repo.
"""

from __future__ import annotations

import difflib
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from chatbot.adapters import detect_adapter
from chatbot.adapters.base import ArchEdge, ArchitectureGraph, ArchNode, BaseAdapter

logger = logging.getLogger(__name__)

# Files we'll never try to parse (too large, binary, or not architecture-related)
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build"}
_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".class", ".jar", ".war", ".so", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".lock", ".sum", ".mod",
}
MAX_FILES = 200
MAX_FILE_SIZE = 512 * 1024  # 512KB


@dataclass
class CrawledArtifact:
    path: Path
    adapter: BaseAdapter
    content: bytes


class RepoCrawler:
    """Walk a directory, detect adapters for each file, and merge graphs."""

    def crawl(self, root: Path) -> List[CrawledArtifact]:
        """Walk root recursively, returning artifacts where an adapter claims can_handle()."""
        artifacts: List[CrawledArtifact] = []
        seen_count = 0

        for file_path in _walk(root):
            if seen_count >= MAX_FILES:
                logger.warning("TAclaw: MAX_FILES (%d) reached, stopping crawl", MAX_FILES)
                break

            try:
                stat = file_path.stat()
            except OSError:
                continue

            if stat.st_size == 0 or stat.st_size > MAX_FILE_SIZE:
                continue

            try:
                content = file_path.read_bytes()
            except OSError:
                continue

            try:
                adapter = detect_adapter(str(file_path), content)
            except ValueError:
                continue  # no adapter claimed this file

            artifacts.append(CrawledArtifact(path=file_path, adapter=adapter, content=content))
            seen_count += 1
            logger.debug("TAclaw: found %s via %s", file_path.name, type(adapter).__name__)

        return artifacts

    def merge_graphs(self, graphs: List[ArchitectureGraph]) -> ArchitectureGraph:
        """
        Merge multiple ArchitectureGraphs into one composite graph.

        Deduplicates nodes by label similarity (difflib, cutoff=0.85).
        Labels merged edges with the source format.
        """
        if not graphs:
            return ArchitectureGraph(
                title="empty",
                nodes=[],
                edges=[],
                source_format="composite",
            )
        if len(graphs) == 1:
            return graphs[0]

        merged_nodes: List[ArchNode] = []
        node_labels: List[str] = []   # parallel to merged_nodes
        id_remap: dict[str, str] = {}  # old_id (per-graph) → canonical merged id

        merged_edges: List[ArchEdge] = []

        for graph in graphs:
            local_remap: dict[str, str] = {}
            for node in graph.nodes:
                # Fuzzy dedup: if a nearly-identical label already exists, reuse its id
                matches = difflib.get_close_matches(node.label, node_labels, n=1, cutoff=0.85)
                if matches:
                    canonical_idx = node_labels.index(matches[0])
                    local_remap[node.id] = merged_nodes[canonical_idx].id
                else:
                    merged_nodes.append(node)
                    node_labels.append(node.label)
                    local_remap[node.id] = node.id

            for edge in graph.edges:
                src = local_remap.get(edge.source, edge.source)
                tgt = local_remap.get(edge.target, edge.target)
                label = f"{edge.label or ''} [{graph.source_format}]".strip()
                merged_edges.append(ArchEdge(source=src, target=tgt, label=label or None))

        source_formats = list(dict.fromkeys(g.source_format for g in graphs))
        return ArchitectureGraph(
            title=f"composite ({len(graphs)} sources)",
            nodes=merged_nodes,
            edges=merged_edges,
            source_format="composite",
            adapter_metadata={
                "source_formats": source_formats,
                "source_count": len(graphs),
                "original_node_counts": [len(g.nodes) for g in graphs],
            },
        )


def _walk(root: Path) -> Iterator[Path]:
    """Yield files recursively, skipping known non-architecture directories."""
    for entry in root.iterdir():
        if entry.is_dir():
            if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                continue
            yield from _walk(entry)
        elif entry.is_file():
            if entry.suffix in _SKIP_EXTENSIONS:
                continue
            yield entry


def clone_repo(git_url: str, target_dir: Path) -> Path:
    """Shallow-clone a git repo into target_dir. Raises RuntimeError on failure."""
    if not shutil.which("git"):
        raise RuntimeError("git not found on PATH — cannot clone remote repo")

    result = subprocess.run(
        ["git", "clone", "--depth=1", "--single-branch", git_url, str(target_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
    return target_dir
