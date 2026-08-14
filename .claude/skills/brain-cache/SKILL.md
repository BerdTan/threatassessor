---
name: brain-cache
description: TA Brain TACO cache inspection and management — stats, pre-warm from corpus, evict stale entries, record feedback signals. Run after brain-grow to refresh the cache or diagnose cache hit rates.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Brain Cache

Inspect and manage the TACO cache layer. The cache sits between callers and the pattern KG — same topology → instant hit; variant topology → KG bypass.

## Run

```bash
# Stats (default)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-cache/scripts/brain-cache.py

# Pre-warm from all corpus instances
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-cache/scripts/brain-cache.py --pre-warm

# Evict stale entries (after a brain-grow bumps pattern_version)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-cache/scripts/brain-cache.py --evict-stale

# Record feedback for a cached topology signature
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-cache/scripts/brain-cache.py --feedback confirmed --sig <topology_sig>
```

## What it shows (--stats)

| Field | Description |
|-------|-------------|
| Total entries | All cached topology × mode combinations |
| Total hits | How many times callers got a cache hit |
| Stale entries | Entries with pattern_version older than current brain |
| By arch type | Entry count per architecture type |
| By pattern version | Distribution of entries across versions |

## Flags

| Flag | Description |
|------|-------------|
| `--stats` | Print cache statistics (default) |
| `--pre-warm` | Populate cache for all corpus instances (infer + patterns modes) |
| `--evict-stale` | Remove entries older than current pattern_version |
| `--feedback confirmed\|wrong --sig SIG` | Record a feedback signal for a topology signature |

## Failure fixes

| Error | Fix |
|-------|-----|
| `ta_brain_cache.json not found` | Cache not yet built — run `--pre-warm` or trigger a `brain-grow` |
| `ta_brain.json not found` | Brain not initialised — run `brain-grow` first |
| Pre-warm adds 0 entries | All topology sigs already cached at current pattern version |
| Stale count = 0 after grow | Cache was already evicted or pattern_version didn't change |

## Notes

- Stale entries are still served but trigger a KG re-lookup (then refreshed). Evicting them forces fresh lookups immediately.
- Pre-warm is cheap: it queries the KG for known topologies and writes results to the cache file.
- Run `--evict-stale` then `--pre-warm` after any `brain-grow` to keep the cache fresh.

## Related skills

- `/brain-grow` — full rebuild that bumps pattern_version (makes entries stale)
- `/brain-infer` — uses the cache; warm cache = faster infer calls
