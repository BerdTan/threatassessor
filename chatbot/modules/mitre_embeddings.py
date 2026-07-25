"""
Semantic search for MITRE ATT&CK techniques using embeddings.

This module provides:
- Embedding cache generation for all MITRE techniques
- Semantic search using cosine similarity
- Cache persistence to JSON for fast loading

Cache generation time: ~10-15 minutes (823 techniques, rate limited to 20 req/min)
Cache size: ~13MB (823 techniques × 2048 dimensions)
"""

import json
import os
import logging
from typing import List, Dict, Tuple, Optional
from chatbot.modules.embeddings import get_embedding, cosine_similarity
from chatbot.modules.mitre import MitreHelper, get_mitre_helper

logger = logging.getLogger(__name__)

# Default cache location — .npz is the canonical output; .json accepted as legacy input
DEFAULT_CACHE_PATH = "chatbot/data/technique_embeddings.npz"
_LEGACY_JSON_PATH  = "chatbot/data/technique_embeddings.json"


def _npz_path(filepath: str) -> str:
    """Return the .npz path regardless of whether caller passed .json or .npz."""
    return filepath.replace(".json", ".npz") if filepath.endswith(".json") else filepath


def build_technique_text(technique: dict) -> str:
    """
    Build searchable text representation of a MITRE technique.

    Args:
        technique: MITRE technique dict with name, description, external_id

    Returns:
        Concatenated text optimized for embedding generation

    Format:
        "{external_id}: {name}. {description}"

    Example:
        "T1059.001: PowerShell. PowerShell is a powerful interactive..."
    """
    external_id = technique.get("external_id", "")
    name = technique.get("name", "")
    description = technique.get("description", "")

    # Combine fields with clear separators for better embedding
    text = f"{external_id}: {name}. {description}"

    return text


def build_technique_embeddings(
    mitre: MitreHelper,
    progress_callback: Optional[callable] = None
) -> Dict[str, dict]:
    """
    Generate embeddings for all MITRE techniques.

    Args:
        mitre: MitreHelper instance with loaded MITRE data
        progress_callback: Optional function(current, total, technique_id) called after each embedding

    Returns:
        Dict mapping technique_id to:
        {
            "external_id": "T1059.001",
            "name": "PowerShell",
            "text": "T1059.001: PowerShell. PowerShell is...",
            "embedding": [0.123, -0.456, ...],  # 2048 dimensions
            "dimension": 2048
        }

    Note:
        - Takes 10-15 minutes due to rate limiting (20 req/min)
        - Progress logged every 10 techniques
        - Failed embeddings are logged but don't stop the process
    """
    techniques = mitre.get_techniques()
    total = len(techniques)

    logger.info(f"Building embeddings for {total} MITRE techniques...")
    logger.info("This will take ~10-15 minutes due to rate limiting (20 req/min)")
    print(f"\n🔄 Building embedding cache for {total} techniques...")
    print(f"   Estimated time: 10-15 minutes (rate limited to 20 req/min)\n")

    cache = {}
    success_count = 0
    failure_count = 0

    for i, technique in enumerate(techniques, 1):
        technique_id = technique.get("id")
        external_id = technique.get("external_id", "Unknown")

        try:
            # Build searchable text
            text = build_technique_text(technique)

            # Generate embedding (rate limited automatically)
            embedding = get_embedding(text)

            # Store in cache
            cache[technique_id] = {
                "external_id": external_id,
                "name": technique.get("name", ""),
                "text": text,
                "embedding": embedding,
                "dimension": len(embedding)
            }

            success_count += 1

            # Progress logging
            if i % 10 == 0 or i == total:
                logger.info(f"Progress: {i}/{total} techniques embedded ({success_count} success, {failure_count} failed)")
                print(f"   ✓ {i}/{total} techniques embedded ({success_count} success, {failure_count} failed)")

            # Optional progress callback
            if progress_callback:
                progress_callback(i, total, external_id)

        except Exception as e:
            failure_count += 1
            logger.error(f"Failed to embed technique {external_id}: {str(e)}")
            print(f"   ⚠️  Failed to embed {external_id}: {str(e)}")
            # Continue with next technique

    logger.info(f"Embedding generation complete: {success_count} success, {failure_count} failed")
    print(f"\n✅ Cache generation complete: {success_count}/{total} techniques embedded\n")

    return cache


def save_embeddings_json(cache: Dict[str, dict], filepath: str = DEFAULT_CACHE_PATH):
    """
    Save embedding cache as float16 compressed numpy archive (.npz).

    Accepts a .json or .npz filepath; always writes .npz.
    Metadata (external_id, name, text) saved to a companion _meta.json sidecar (~200 KB).

    Args:
        cache: Embedding cache dict from build_technique_embeddings()
        filepath: Destination path (.npz preferred; .json redirected to .npz automatically)
    """
    import numpy as np

    npz_out = _npz_path(filepath)
    os.makedirs(os.path.dirname(os.path.abspath(npz_out)), exist_ok=True)

    keys  = list(cache.keys())
    vecs  = np.array([cache[k]["embedding"] for k in keys], dtype=np.float16)
    metas = {k: {kk: vv for kk, vv in cache[k].items() if kk != "embedding"} for k in keys}

    np.savez_compressed(npz_out, keys=np.array(keys), embeddings=vecs)

    meta_path = npz_out.replace(".npz", "_meta.json")
    with open(meta_path, "w") as f:
        json.dump(metas, f, separators=(",", ":"))

    size_mb = os.path.getsize(npz_out) / (1024 * 1024)
    meta_kb = os.path.getsize(meta_path) / 1024
    logger.info(f"Embedding cache saved: {npz_out} ({size_mb:.1f} MB) + meta ({meta_kb:.0f} KB)")
    print(f"✅ Cache saved: {npz_out} ({size_mb:.1f} MB) + {os.path.basename(meta_path)} ({meta_kb:.0f} KB)")


def load_embeddings_json(filepath: str = DEFAULT_CACHE_PATH) -> Dict[str, dict]:
    """
    Load embedding cache. Prefers .npz; falls back to legacy .json.

    Args:
        filepath: Path to .npz or .json cache file

    Returns:
        Embedding cache dict mapping technique_id → {external_id, name, text, embedding, dimension}

    Raises:
        FileNotFoundError: If neither .npz nor .json cache exists
    """
    import numpy as np

    npz_path  = _npz_path(filepath)
    json_path = filepath if filepath.endswith(".json") else _LEGACY_JSON_PATH

    if os.path.exists(npz_path):
        d     = np.load(npz_path, allow_pickle=False)
        keys  = d["keys"].tolist()
        vecs  = d["embeddings"].astype(np.float32)
        meta_path = npz_path.replace(".npz", "_meta.json")
        metas = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
        cache = {k: {**metas.get(k, {}), "embedding": vecs[i].tolist(), "dimension": vecs.shape[1]}
                 for i, k in enumerate(keys)}
        size_mb = os.path.getsize(npz_path) / (1024 * 1024)
        logger.info(f"Loaded {len(cache)} technique embeddings from {npz_path} ({size_mb:.1f} MB)")
        return cache

    if os.path.exists(json_path):
        with open(json_path) as f:
            cache = json.load(f)
        size_mb = os.path.getsize(json_path) / (1024 * 1024)
        logger.info(f"Loaded {len(cache)} technique embeddings from legacy JSON {json_path} ({size_mb:.1f} MB)")
        return cache

    raise FileNotFoundError(
        f"Embedding cache not found at {npz_path} (or legacy {json_path}). "
        f"Run /build-embeddings-cache to generate it."
    )


def semantic_search(
    query: str,
    cache: Dict[str, dict],
    top_k: int = 10,
    min_score: float = 0.0
) -> List[Tuple[str, str, str, float]]:
    """
    Search MITRE techniques using semantic similarity.

    Args:
        query: Natural language query (e.g., "PowerShell script execution")
        cache: Embedding cache from load_embeddings_json()
        top_k: Number of top results to return (default: 10)
        min_score: Minimum similarity score threshold (default: 0.0, range: -1 to 1)

    Returns:
        List of tuples: (technique_id, external_id, name, similarity_score)
        Sorted by similarity score (highest first)

    Example:
        >>> results = semantic_search("attacker uses PowerShell", cache, top_k=5)
        >>> for tid, ext_id, name, score in results:
        ...     print(f"{ext_id} - {name}: {score:.3f}")
        T1059.001 - PowerShell: 0.856
        T1059.003 - Windows Command Shell: 0.723
        ...

    Note:
        - Query embedding generated in real-time (~1-2s)
        - Cosine similarity used for matching
        - Scores >0.5 typically indicate good matches
        - Scores >0.7 indicate strong matches
    """
    logger.info(f"Semantic search: '{query}' (top_k={top_k}, min_score={min_score})")

    # Generate embedding for query
    try:
        query_embedding = get_embedding(query)
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {str(e)}")
        raise RuntimeError(f"Could not generate embedding for query: {str(e)}")

    # Calculate similarity scores
    results = []

    for technique_id, data in cache.items():
        technique_embedding = data.get("embedding")

        if not technique_embedding:
            logger.warning(f"No embedding found for technique {technique_id}")
            continue

        # Calculate cosine similarity
        similarity = cosine_similarity(query_embedding, technique_embedding)

        # Apply minimum score threshold
        if similarity >= min_score:
            results.append((
                technique_id,
                data.get("external_id", "Unknown"),
                data.get("name", "Unknown"),
                similarity
            ))

    # Sort by similarity (highest first)
    results.sort(key=lambda x: x[3], reverse=True)

    # Return top K results
    top_results = results[:top_k]

    logger.info(f"Found {len(results)} matches above threshold, returning top {len(top_results)}")

    if top_results:
        logger.debug(f"Top result: {top_results[0][1]} - {top_results[0][2]} (score: {top_results[0][3]:.3f})")

    return top_results


def get_or_build_cache(
    mitre: MitreHelper,
    cache_path: str = DEFAULT_CACHE_PATH,
    force_rebuild: bool = False
) -> Dict[str, dict]:
    """
    Get embedding cache, building it if necessary.

    Args:
        mitre: MitreHelper instance
        cache_path: Path to cache file
        force_rebuild: If True, rebuild cache even if it exists

    Returns:
        Embedding cache dict

    Note:
        - First call builds cache (~10-15 min)
        - Subsequent calls load from disk (instant)
        - Use force_rebuild=True to regenerate cache after MITRE data updates
    """
    if force_rebuild or not os.path.exists(cache_path):
        if force_rebuild:
            logger.info("Force rebuild requested, regenerating cache...")
        else:
            logger.info("Cache not found, building for first time...")

        cache = build_technique_embeddings(mitre)
        save_embeddings_json(cache, cache_path)
        return cache
    else:
        logger.info("Loading existing cache...")
        return load_embeddings_json(cache_path)


# Convenience function for quick searches
def search_techniques(
    query: str,
    mitre: MitreHelper,
    cache_path: str = DEFAULT_CACHE_PATH,
    top_k: int = 10,
    min_score: float = 0.5
) -> List[Dict]:
    """
    High-level semantic search with automatic cache management.

    Args:
        query: Natural language query
        mitre: MitreHelper instance
        cache_path: Path to embedding cache
        top_k: Number of results
        min_score: Minimum similarity score (0.5 = decent match, 0.7 = strong match)

    Returns:
        List of dicts with technique details and scores:
        [
            {
                "technique_id": "attack-pattern--...",
                "external_id": "T1059.001",
                "name": "PowerShell",
                "similarity_score": 0.856,
                "description": "PowerShell is a powerful...",
                "tactics": ["execution"],
                "platforms": ["Windows"]
            },
            ...
        ]

    Example:
        >>> from chatbot.modules.mitre import MitreHelper, get_mitre_helper
        >>> mitre = get_mitre_helper()
        >>> results = search_techniques("attacker uses PowerShell", mitre, top_k=5)
        >>> print(results[0]["external_id"], results[0]["name"])
        T1059.001 PowerShell
    """
    # Load or build cache
    cache = get_or_build_cache(mitre, cache_path)

    # Perform semantic search
    raw_results = semantic_search(query, cache, top_k, min_score)

    # Enrich with full technique details
    enriched_results = []

    for technique_id, external_id, name, score in raw_results:
        # Get full technique details from MITRE
        technique = mitre.find_technique(external_id)

        if not technique:
            logger.warning(f"Could not find technique {external_id} ({name}) in MITRE data")
            continue

        if technique:
            # Extract tactics from kill_chain_phases
            tactics = []
            if "kill_chain_phases" in technique:
                tactics = [phase["phase_name"] for phase in technique["kill_chain_phases"]]

            enriched_results.append({
                "technique_id": technique_id,
                "external_id": external_id,
                "name": name,
                "similarity_score": score,
                "description": technique.get("description", ""),
                "tactics": tactics,
                "platforms": technique.get("x_mitre_platforms", [])
            })

    return enriched_results


if __name__ == "__main__":
    # Test semantic search
    print("Testing semantic search module...\n")

    from chatbot.modules.mitre import MitreHelper, get_mitre_helper

    # Initialize MITRE
    print("Loading MITRE data...")
    mitre = get_mitre_helper()
    print(f"Loaded {len(mitre.get_techniques())} techniques\n")

    # Test cache building (or loading)
    print("Getting embedding cache...")
    cache = get_or_build_cache(mitre)
    print(f"Cache ready with {len(cache)} techniques\n")

    # Test search
    query = "attacker uses PowerShell to execute malicious scripts"
    print(f"Query: '{query}'\n")

    results = search_techniques(query, mitre, top_k=5, min_score=0.5)

    print(f"Top {len(results)} results:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['external_id']} - {result['name']}")
        print(f"   Score: {result['similarity_score']:.3f}")
        print(f"   Tactics: {', '.join(result['tactics'])}")
        print(f"   Description: {result['description'][:100]}...")
        print()

    print("✅ Semantic search test complete")
