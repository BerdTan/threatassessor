---
name: mmd
description: Generate, edit, validate, and parse Mermaid (.mmd) architecture diagrams for ThreatAssessor. Use when asked to create or modify an architecture diagram, check MMD syntax, extract nodes/edges from an existing diagram, or prepare a .mmd file for analysis by the engine. Covers both context graphs (.claude/graphs/) and architecture diagrams (tests/data/architectures/).
---

# MMD Skill

Two diagram families in this repo — know which one you're working on:

| Family | Location | Purpose |
|---|---|---|
| **Architecture diagrams** | `tests/data/architectures/*.mmd` | Input to the threat analysis engine — gets parsed, scored, generates reports |
| **Context graphs** | `.claude/graphs/*.mmd` | Navigation aids for Claude Code — not processed by the engine |

The rules differ by family. Read the right section below.

---

## Architecture diagrams (engine input)

### What the engine expects

The parser (`chatbot/parsers/mermaid_parser.py`) accepts:

- **First line:** `flowchart LR` / `flowchart TD` / `flowchart TB` — no `graph` mode
- **Node shapes:** `[label]` rect, `(label)` round, `((label))` circle, `[(label)]` cylinder (database), `{label}` diamond
- **Edges:** `-->`, `---`, `<-->`, `--|label|-->` (labelled), `-.->` (dashed)
- **Subgraphs:** `subgraph SubgraphName[Display Name]` … `end` — give every subgraph a unique ID
- **Comments:** `%% text` — ignored by parser
- **No frontmatter** — the engine reads raw MMD; a YAML `---` block will cause a parse error

### Node naming rules (canonicalisation table)

`chatbot/modules/node_label_canonicaliser.py` maps variant labels to canonical keywords that `TRAVERSAL_TECHNIQUES` recognises. Use canonical labels where possible — the engine assigns more accurate techniques:

| Prefer | Instead of |
|---|---|
| `Load Balancer` | ALB, ELB, NLB, Ingress Controller |
| `Database` | UserDB, OrderDB, Primary DB, Replica, Firestore, DynamoDB, CosmosDB |
| `Firewall` | WAF, DDoS Protection |
| `User` | Visitors/Employees, Internet Users, Citizens, Browser, End Users |
| `LLM` | ML Model, AI Model, Model Endpoint, LLM Gateway |
| `Server` | Consensus Engine, Peer Nodes, Validator Node |
| `Queue` | Pub/Sub, PubSub, Event Hub, SNS, SQS |
| `Storage` | Data Lake, Data Store, S3 Bucket |
| `Controller` | PLC, SCADA, IoT Hub |
| `Sensor` | IoT Devices, RFID |

**Do not** rename if the variant is the diagram's primary concept (e.g. a blockchain arch should keep `Validator Node` — the canonicaliser handles it automatically).

### Structural rules for good threat coverage

1. **Entry points must connect outward.** External actors (`User`, `Browser`, `Internet`) need at least one outbound edge into the system — they become attack origins.
2. **Sensitive targets must be reachable.** Databases, secrets stores, and queues with no inbound path generate no attack paths.
3. **Every node needs at least one edge.** Orphan nodes (no edges at all) are flagged by the validator and contribute zero techniques.
4. **Use subgraphs for layers.** Grouping nodes into `Edge_Layer`, `Application_Layer`, `Database_Layer` etc. improves path narrative quality.
5. **Hub nodes trigger pivot coverage.** A traversal node (non-entry, non-target) with `out_degree ≥ 3` gets T1570 (Lateral Tool Transfer) + T1021 (Remote Services) injected automatically and +0.05 criticality boost.

### Generate workflow

1. **Draft the diagram.** Start from the architectural layers (edge → app → data → monitoring). Aim for 8–20 nodes for good coverage without noise.
2. **Write to file.** Save as `tests/data/architectures/<name>.mmd` (for engine input) or a temp path for quick checks.
3. **Validate.** Run:
   ```bash
   python3 .claude/skills/mmd/scripts/validate_arch.py tests/data/architectures/<name>.mmd
   ```
   Checks: first-line keyword, orphan nodes, subgraph structure, no frontmatter.
4. **Parse check.** Dry-run the engine parser to confirm node/edge extraction:
   ```bash
   python3 .claude/skills/mmd/scripts/parse_mmd.py tests/data/architectures/<name>.mmd
   ```
   Prints node count, edge count, entry/target candidates.
5. **Run analysis** (optional, needs LLM):
   ```bash
   ./demo_deterministic_engine.sh --validate-orphan tests/data/architectures/<name>.mmd
   ```

### Edit workflow

When modifying an existing architecture diagram:
1. Read the current file.
2. Check orphan status: `python3 scripts/validation/check_orphans.py <arch_name>`
3. Make changes — preserve existing node IDs if referenced in reports.
4. Re-validate with `validate_arch.py`.
5. Re-run `parse_mmd.py` to confirm the change had the intended structural effect.

### Parse an existing diagram

To extract nodes/edges without running the full engine:

```bash
python3 .claude/skills/mmd/scripts/parse_mmd.py <path-to-file.mmd>
```

Output:
```
Nodes (12):  Users, APIGateway, LoadBalancer, AuthService, ...
Edges (15):  Users→APIGateway, APIGateway→LoadBalancer, ...
Entry candidates:  Users, MobileApp
Target candidates: UserDB, AccessLogDB, Cache
Hub nodes (out≥3): LoadBalancer(4), AccessControlAPI(3)
Subgraphs (4): Edge_Gateway, Application_Layer, Database_Layer, IoT_Layer
```

---

## Context graphs (.claude/graphs/)

These are **curated relationship maps**, not engine input. Different rules apply.

### Validation

After any edit to a `.claude/graphs/*.mmd` file, always run:

```bash
python3 .claude/skills/codemap/scripts/validate_graphs.py
```

This catches the six failure modes that cause rendering errors:
1. YAML frontmatter multi-line values
2. `graph` mode with inter-subgraph edges (must use `flowchart`)
3. `<br/>` inside edge labels
4. Literal `\n` in node labels
5. Duplicate node IDs
6. Reserved Mermaid keywords as node IDs

### Which graph to update

| Changed | Update |
|---|---|
| Module inputs/outputs | `pipeline.mmd` |
| Stage order, new stage, new sink | `harness.mmd` |
| Tab data source, new API route | `dashboard-tabs.mmd` |
| New skill, workflow sequence | `skills.mmd` |
| Any of the above (top-level) | `master.mmd` |

### Format requirements

Every context graph needs:
- YAML frontmatter with `title`, `updated`, and a single-line `note` (multi-line YAML values break rendering)
- `flowchart` mode (not `graph`) — subgraph IDs are used in edges
- `classDef` + `class` lines at the bottom for semantic colour coding

---

## Quick reference — common errors

| Error | Cause | Fix |
|---|---|---|
| Parse returns 0 nodes | `graph TD` instead of `flowchart TD` | Change first line |
| 0 attack paths | Entry node has no outbound edges, or target unreachable | Add connecting edges |
| val_pct gap | Node label not in canonicaliser | Add to `_SYNONYM_PAIRS` in `node_label_canonicaliser.py` |
| YAML parse error (context graph) | Multi-line `note:` value | Collapse to one quoted line |
| Rendering artefact (context graph) | Subgraph ID in edge | Use `flowchart` mode |
