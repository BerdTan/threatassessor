---
name: arch-to-graph
description: Parse a .mmd architecture diagram and render it side-by-side with the in-memory graph representation (adjacency list + hub scores). Use when explaining how the engine sees an architecture, writing blog visuals, or debugging why a node is or isn't flagged as a hub/entry/target.
---

# arch-to-graph

Converts a `.mmd` architecture diagram into the side-by-side representation used in the Part 12 blog: source diagram on the left, adjacency list + hub scores on the right.

## When to use

- Writing a blog post or doc that explains how TA sees an architecture
- Debugging why a node is or isn't flagged as hub/entry/target
- Generating the "architecture is already a graph" visual for any arch

## Usage

```bash
python3 .claude/skills/arch-to-graph/scripts/arch_to_graph.py <path-to-file.mmd>

# With ground_truth.json for real hub scores (uses attack-path-derived unique-successor counts)
python3 .claude/skills/arch-to-graph/scripts/arch_to_graph.py <path-to-file.mmd> \
  --ground-truth report/<arch-name>/ground_truth.json
```

## Output format

```
Architecture diagram (.mmd)               Graph in memory (adjacency list)
─────────────────────────────             ──────────────────────────────────
flowchart TB                              nodes:
  Users((Users))                            Users       → [APIGateway]
  APIGateway[API Gateway]                   APIGateway  → [OrderService, PaymentService]
  ...                                       ...

  Users --> APIGateway                    hub score (unique successors):
  APIGateway --> OrderService               APIGateway: 3  ← fan-out point
  ...                                       Users: 1  ← entry, not hub
```

Left column: the raw `.mmd` source lines (stripped of subgraph wrappers for legibility).
Right column: adjacency list from parsed edges + hub scores.

Hub score is:
- With `--ground-truth`: unique successor count across all attack paths (the real engine metric)
- Without: out-degree from parsed edges (structural proxy — same idea, no attack path data)

Nodes are annotated:
- `← fan-out point` — hub (unique successors ≥ 3, not infra, not entry)
- `← entry, not hub` — entry-point keyword match, in-degree 0
- `← target` — sensitive-target keyword match
- `← infra` — routing/forwarding node excluded from hub scoring

## Paste-ready output

The script prints a fenced code block suitable for pasting directly into a blog draft or doc. Copy from the ` ``` ` markers.

## Related

- `.claude/skills/mmd/scripts/parse_mmd.py` — the underlying parser this wraps
- `chatbot/modules/graph_index.py` — production graph index (uses attack-path data)
- Blog Part 12: https://medium.com/@breadtan/the-graph-that-ate-its-own-architecture-0186760253fe
