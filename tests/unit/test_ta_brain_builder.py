"""
Unit tests — Stage 1: TA Brain builder (instance ingest + distiller).

All tests are deterministic: no LLM calls, no filesystem writes (except the
build_brain integration test which uses tmp_path).
"""

import json
import pytest
from pathlib import Path

from chatbot.modules.ta_brain_builder import (
    HOLD_OUT_ARCHS,
    MIN_EVIDENCE,
    build_brain,
    compute_hub_nodes,
    compute_topology_signature,
    detect_gaps,
    extract_instance,
    run_distiller,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_nodes(shapes):
    """Build parsed_nodes dict with given shapes, using shape as both key and label."""
    return {f"n{i}": {"label": f"Label{i}", "shape": s} for i, s in enumerate(shapes)}


def _make_edges(pairs, shapes):
    """Build parsed_edges list from (src_idx, tgt_idx) pairs into node keys."""
    return [{"source": f"n{s}", "target": f"n{t}"} for s, t in pairs]


def _make_instance(arch_id, arch_type, techniques, controls_missing,
                   node_count=5, aivss_composite=0.0,
                   fired_detect_rules=None, source="real"):
    return {
        "arch_id": arch_id,
        "arch_type": arch_type,
        "topology_signature": f"sig_{arch_id}",
        "node_count": node_count,
        "edge_count": 3,
        "techniques": techniques,
        "controls_missing": controls_missing,
        "hub_nodes": [],
        "aivss_composite": aivss_composite,
        "aivss_severity": "LOW",
        "fired_detect_rules": fired_detect_rules or [],
        "run_ts": "2026-08-01T00:00:00Z",
        "source": source,
    }


# ── topology_signature ────────────────────────────────────────────────────────

class TestComputeTopologySignature:
    def test_same_shapes_same_hash(self):
        nodes = _make_nodes(["rectangle", "cylinder", "circle"])
        edges = _make_edges([(0, 1), (1, 2)], nodes)
        sig_a = compute_topology_signature(nodes, edges)

        # Rename node labels — must produce identical hash
        nodes_renamed = {
            k: {"label": f"Renamed{k}", "shape": v["shape"]}
            for k, v in nodes.items()
        }
        sig_b = compute_topology_signature(nodes_renamed, edges)
        assert sig_a == sig_b

    def test_different_shapes_different_hash(self):
        nodes_a = _make_nodes(["rectangle", "cylinder"])
        nodes_b = _make_nodes(["rectangle", "rectangle"])
        edges = _make_edges([(0, 1)], nodes_a)
        assert compute_topology_signature(nodes_a, edges) != compute_topology_signature(nodes_b, edges)

    def test_different_edge_pattern_different_hash(self):
        nodes = _make_nodes(["rectangle", "cylinder", "circle"])
        edges_a = _make_edges([(0, 1), (1, 2)], nodes)
        edges_b = _make_edges([(0, 2), (1, 0)], nodes)
        assert compute_topology_signature(nodes, edges_a) != compute_topology_signature(nodes, edges_b)

    def test_empty_graph(self):
        sig = compute_topology_signature({}, [])
        assert isinstance(sig, str)
        assert len(sig) == 16

    def test_deterministic_repeated_calls(self):
        nodes = _make_nodes(["rectangle", "cylinder"])
        edges = _make_edges([(0, 1)], nodes)
        sigs = {compute_topology_signature(nodes, edges) for _ in range(5)}
        assert len(sigs) == 1  # same result every time

    def test_corpus_collision_resistance(self):
        """
        Topology signatures across corpus: structurally identical archs SHOULD
        share a signature (that's the point — same shape → same cache entry).
        Verify the hash is discriminating enough that most archs get distinct sigs,
        and that the signature never degenerates to a single hash for all archs.
        """
        report = Path(__file__).resolve().parents[2] / "report"
        if not report.exists():
            pytest.skip("report dir not available")
        sigs = []
        for arch_dir in sorted(report.iterdir()):
            if arch_dir.name.startswith("syn_") or arch_dir.name.startswith("ta_brain"):
                continue  # synthetic archs legitimately share signatures by design
            gt_path = arch_dir / "ground_truth.json"
            if not gt_path.exists():
                continue
            gt = json.loads(gt_path.read_text())
            meta = gt.get("metadata", {})
            nodes = meta.get("parsed_nodes", {})
            edges = meta.get("parsed_edges", [])
            sigs.append(compute_topology_signature(nodes, edges))
        # At least 80% of corpus archs get distinct signatures
        unique_ratio = len(set(sigs)) / len(sigs)
        assert unique_ratio >= 0.80, (
            f"Too many collisions: only {len(set(sigs))}/{len(sigs)} unique signatures"
        )
        # Never a single hash for all archs (total degeneration)
        assert len(set(sigs)) > 1


# ── compute_hub_nodes ─────────────────────────────────────────────────────────

class TestComputeHubNodes:
    def test_returns_top_n_by_out_degree(self):
        nodes = _make_nodes(["rectangle", "cylinder", "circle"])
        edges = [
            {"source": "n0", "target": "n1"},
            {"source": "n0", "target": "n2"},
            {"source": "n1", "target": "n2"},
        ]
        hubs = compute_hub_nodes(edges, nodes, top_n=2)
        assert hubs[0] == "rectangle"  # n0 has out-degree 2

    def test_empty_edges(self):
        nodes = _make_nodes(["rectangle"])
        assert compute_hub_nodes([], nodes) == []

    def test_returns_shapes_not_names(self):
        nodes = {"NodeA": {"label": "Real Name", "shape": "cylinder"}}
        edges = [{"source": "NodeA", "target": "NodeX"}]
        hubs = compute_hub_nodes(edges, nodes, top_n=1)
        assert hubs == ["cylinder"]


# ── extract_instance ──────────────────────────────────────────────────────────

class TestExtractInstance:
    def _write_arch(self, tmp_path, arch_id, gt_extra=None, gs_extra=None):
        arch_dir = tmp_path / arch_id
        arch_dir.mkdir()

        gt = {
            "architecture": arch_id,
            "metadata": {
                "architecture_type": "traditional",
                "node_count": 3,
                "edge_count": 2,
                "parsed_nodes": {"A": {"label": "A", "shape": "rectangle"},
                                 "B": {"label": "B", "shape": "cylinder"}},
                "parsed_edges": [{"source": "A", "target": "B"}],
                "run_ts": "2026-08-01T00:00:00Z",
                "run_id": f"{arch_id}_run",
            },
            "techniques": ["T1078", "T1059"],
            "controls_missing": ["mfa", "logging"],
        }
        if gt_extra:
            gt.update(gt_extra)

        gs = {
            "aivss": {"overall": {"composite": 0.5, "severity": "MEDIUM"}},
            "exploitation": {},
        }
        if gs_extra:
            gs.update(gs_extra)

        (arch_dir / "ground_truth.json").write_text(json.dumps(gt))
        (arch_dir / "governance_signals.json").write_text(json.dumps(gs))
        return arch_dir

    def test_extracts_required_fields(self, tmp_path):
        arch_dir = self._write_arch(tmp_path, "test_arch")
        inst = extract_instance(arch_dir)
        assert inst is not None
        assert inst["arch_id"] == "test_arch"
        assert inst["arch_type"] == "traditional"
        assert inst["source"] == "real"
        assert isinstance(inst["topology_signature"], str)
        assert len(inst["topology_signature"]) == 16
        assert "T1078" in inst["techniques"]
        assert "mfa" in inst["controls_missing"]
        assert inst["aivss_composite"] == 0.5

    def test_returns_none_if_files_missing(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        assert extract_instance(empty_dir) is None

    def test_returns_none_if_json_malformed(self, tmp_path):
        arch_dir = tmp_path / "bad"
        arch_dir.mkdir()
        (arch_dir / "ground_truth.json").write_text("not json{")
        (arch_dir / "governance_signals.json").write_text("{}")
        assert extract_instance(arch_dir) is None

    def test_techniques_dict_is_normalized_to_list(self, tmp_path):
        arch_dir = self._write_arch(tmp_path, "dict_tech",
                                    gt_extra={"techniques": {"T1078": {}, "T1059": {}}})
        inst = extract_instance(arch_dir)
        assert isinstance(inst["techniques"], list)
        assert "T1078" in inst["techniques"]

    def test_topology_sig_excludes_node_names(self, tmp_path):
        arch_dir_a = self._write_arch(tmp_path, "arch_a")
        arch_dir_b = tmp_path / "arch_b"
        arch_dir_b.mkdir()

        # Same shape, different node names
        gt_b = json.loads((arch_dir_a / "ground_truth.json").read_text())
        gt_b["metadata"]["parsed_nodes"] = {
            "X": {"label": "X", "shape": "rectangle"},
            "Y": {"label": "Y", "shape": "cylinder"},
        }
        gt_b["metadata"]["parsed_edges"] = [{"source": "X", "target": "Y"}]
        (arch_dir_b / "ground_truth.json").write_text(json.dumps(gt_b))
        (arch_dir_b / "governance_signals.json").write_text(
            (arch_dir_a / "governance_signals.json").read_text()
        )

        inst_a = extract_instance(arch_dir_a)
        inst_b = extract_instance(arch_dir_b)
        assert inst_a["topology_signature"] == inst_b["topology_signature"]


# ── run_distiller ─────────────────────────────────────────────────────────────

class TestRunDistiller:
    def test_produces_one_pattern_per_arch_type(self):
        instances = [
            _make_instance("a1", "web", ["T1078", "T1059"], ["mfa"]),
            _make_instance("a2", "web", ["T1078", "T1190"], ["mfa", "waf"]),
            _make_instance("a3", "agentic", ["AML.T0020"], ["rate_limiting"]),
        ]
        patterns = run_distiller(instances)
        types = {p["trigger"]["arch_type"] for p in patterns}
        assert types == {"web", "agentic"}

    def test_technique_frequency_correct(self):
        instances = [
            _make_instance("a1", "web", ["T1078", "T1059"], []),
            _make_instance("a2", "web", ["T1078", "T1190"], []),
            _make_instance("a3", "web", ["T1059"], []),
        ]
        patterns = run_distiller(instances, min_evidence=2)
        web_pat = next(p for p in patterns if p["trigger"]["arch_type"] == "web")
        freq = web_pat["predicts"]["technique_frequencies"]
        # T1078 appears 2/3 times
        assert abs(freq["T1078"] - round(2 / 3, 3)) < 0.001
        # T1059 appears 2/3 times
        assert abs(freq["T1059"] - round(2 / 3, 3)) < 0.001

    def test_min_evidence_filters_rare_techniques(self):
        instances = [
            _make_instance("a1", "web", ["T1078", "T1059"], []),
            _make_instance("a2", "web", ["T1078"], []),
            _make_instance("a3", "web", ["T1078"], []),
        ]
        patterns = run_distiller(instances, min_evidence=2)
        web_pat = next(p for p in patterns if p["trigger"]["arch_type"] == "web")
        primary = web_pat["predicts"]["techniques"]
        assert "T1078" in primary
        assert "T1059" not in primary

    def test_aivss_floor_is_minimum(self):
        instances = [
            _make_instance("a1", "web", [], [], aivss_composite=0.3),
            _make_instance("a2", "web", [], [], aivss_composite=0.7),
            _make_instance("a3", "web", [], [], aivss_composite=0.5),
        ]
        patterns = run_distiller(instances)
        web_pat = next(p for p in patterns if p["trigger"]["arch_type"] == "web")
        assert web_pat["predicts"]["aivss_floor"] == 0.3

    def test_benchmark_confidence_starts_at_one(self):
        instances = [_make_instance("a1", "web", ["T1078"], ["mfa"])]
        patterns = run_distiller(instances)
        for p in patterns:
            assert p["benchmark_confidence"] == 1.0

    def test_evidence_arch_ids_correct(self):
        instances = [
            _make_instance("arch_x", "web", ["T1078"], []),
            _make_instance("arch_y", "web", ["T1059"], []),
        ]
        patterns = run_distiller(instances)
        web_pat = next(p for p in patterns if p["trigger"]["arch_type"] == "web")
        assert set(web_pat["evidence_arch_ids"]) == {"arch_x", "arch_y"}

    def test_synthetic_instances_counted_separately(self):
        instances = [
            _make_instance("real_a", "web", ["T1078"], [], source="real"),
            _make_instance("synth_b", "web", ["T1078"], [], source="synthetic"),
        ]
        patterns = run_distiller(instances)
        web_pat = next(p for p in patterns if p["trigger"]["arch_type"] == "web")
        assert web_pat["evidence_count"] == 2
        assert web_pat["real_evidence_count"] == 1

    def test_pattern_ids_sequential(self):
        instances = [
            _make_instance("a1", "web", [], []),
            _make_instance("a2", "agentic", [], []),
            _make_instance("a3", "iot", [], []),
        ]
        patterns = run_distiller(instances)
        ids = [p["id"] for p in patterns]
        assert ids == ["BRAIN-001", "BRAIN-002", "BRAIN-003"]

    def test_empty_instances_returns_empty(self):
        assert run_distiller([]) == []


# ── detect_gaps ───────────────────────────────────────────────────────────────

class TestDetectGaps:
    def test_flags_sparse_arch_types(self):
        instances = [_make_instance(f"a{i}", "rare_type", [], []) for i in range(2)]
        patterns = run_distiller(instances)
        gaps = detect_gaps(instances, patterns)
        regions = [g["region"] for g in gaps]
        assert "arch_type:rare_type" in regions

    def test_no_gap_for_well_sampled_type(self):
        instances = [_make_instance(f"a{i}", "common", [], []) for i in range(5)]
        patterns = run_distiller(instances)
        gaps = detect_gaps(instances, patterns)
        assert not any(g["region"] == "arch_type:common" for g in gaps)

    def test_gaps_sorted_by_priority_descending(self):
        instances = (
            [_make_instance(f"rare{i}", "rare_high_risk", [], [], aivss_composite=0.9) for i in range(1)]
            + [_make_instance(f"semi{i}", "semi_rare", [], [], aivss_composite=0.1) for i in range(2)]
        )
        patterns = run_distiller(instances)
        gaps = detect_gaps(instances, patterns)
        if len(gaps) >= 2:
            assert gaps[0]["priority"] >= gaps[1]["priority"]

    def test_forced_gap_defaults_false(self):
        instances = [_make_instance("a1", "sparse", [], [])]
        patterns = run_distiller(instances)
        gaps = detect_gaps(instances, patterns)
        assert all(g["forced_gap"] is False for g in gaps)


# ── build_brain (integration) ─────────────────────────────────────────────────

class TestBuildBrain:
    def _populate_report_dir(self, report_dir, archs):
        for arch_id, arch_type, techniques, controls in archs:
            arch_dir = report_dir / arch_id
            arch_dir.mkdir(parents=True)
            gt = {
                "architecture": arch_id,
                "metadata": {
                    "architecture_type": arch_type,
                    "node_count": 4,
                    "edge_count": 3,
                    "parsed_nodes": {"A": {"label": "A", "shape": "rectangle"},
                                     "B": {"label": "B", "shape": "cylinder"}},
                    "parsed_edges": [{"source": "A", "target": "B"}],
                    "run_ts": "2026-08-01T00:00:00Z",
                    "run_id": f"{arch_id}_run",
                },
                "techniques": techniques,
                "controls_missing": controls,
            }
            gs = {"aivss": {"overall": {"composite": 0.4, "severity": "LOW"}}}
            (arch_dir / "ground_truth.json").write_text(json.dumps(gt))
            (arch_dir / "governance_signals.json").write_text(json.dumps(gs))

    def test_writes_instances_jsonl_and_brain_json(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("arch1", "web", ["T1078"], ["mfa"]),
            ("arch2", "web", ["T1059"], ["waf"]),
            ("arch3", "agentic", ["AML.T0020"], ["rate_limiting"]),
        ])
        result = build_brain(report_dir=tmp_path, hold_out=frozenset())
        assert (tmp_path / "ta_brain_instances.jsonl").exists()
        assert (tmp_path / "ta_brain.json").exists()
        assert result["ingested"] == 3

    def test_instances_jsonl_is_append_only(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("arch1", "web", ["T1078"], ["mfa"]),
        ])
        build_brain(report_dir=tmp_path, hold_out=frozenset(), incremental=False)
        build_brain(report_dir=tmp_path, hold_out=frozenset(), incremental=False)  # explicit non-incremental re-appends
        lines = (tmp_path / "ta_brain_instances.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_incremental_skips_existing(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("arch1", "web", ["T1078"], ["mfa"]),
            ("arch2", "web", ["T1059"], ["waf"]),
        ])
        build_brain(report_dir=tmp_path, hold_out=frozenset(), incremental=False)
        result2 = build_brain(report_dir=tmp_path, hold_out=frozenset(), incremental=True)
        assert result2["ingested"] == 0

    def test_hold_out_excluded_from_patterns(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("arch_train", "web", ["T1078"], ["mfa"]),
            ("arch_holdout", "unique_type", ["T9999"], ["special_control"]),
        ])
        result = build_brain(
            report_dir=tmp_path, hold_out=frozenset({"arch_holdout"})
        )
        brain = json.loads((tmp_path / "ta_brain.json").read_text())
        pattern_types = {p["trigger"]["arch_type"] for p in brain["patterns"]}
        assert "unique_type" not in pattern_types
        assert result["hold_out_instances"] == 1

    def test_pattern_version_increments(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("arch1", "web", ["T1078"], ["mfa"]),
        ])
        build_brain(report_dir=tmp_path, hold_out=frozenset())
        r2 = build_brain(report_dir=tmp_path, hold_out=frozenset())
        assert r2["pattern_version"] == 2

    def test_brain_json_has_required_keys(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("arch1", "web", ["T1078"], ["mfa"]),
        ])
        build_brain(report_dir=tmp_path, hold_out=frozenset())
        brain = json.loads((tmp_path / "ta_brain.json").read_text())
        for key in ("version", "pattern_version", "built_ts", "corpus_size",
                    "train_size", "hold_out", "patterns", "gaps"):
            assert key in brain, f"Missing key: {key}"

    def test_skips_dirs_without_required_files(self, tmp_path):
        self._populate_report_dir(tmp_path, [
            ("valid_arch", "web", ["T1078"], ["mfa"]),
        ])
        # Create an invalid dir (no JSON files)
        (tmp_path / "invalid_dir").mkdir()
        result = build_brain(report_dir=tmp_path, hold_out=frozenset())
        assert "invalid_dir" in result["skipped"]
        assert result["ingested"] == 1
