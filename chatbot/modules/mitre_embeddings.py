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
from chatbot.modules.mitre import MitreHelper

logger = logging.getLogger(__name__)

# Default cache location
DEFAULT_CACHE_PATH = "chatbot/data/technique_embeddings.json"


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
    Save embedding cache to JSON file.

    Args:
        cache: Embedding cache dict from build_technique_embeddings()
        filepath: Path to save JSON file (default: chatbot/data/technique_embeddings.json)

    Note:
        - Creates parent directories if needed
        - File size: ~13MB for 823 techniques
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, 'w') as f:
        json.dump(cache, f, indent=2)

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    logger.info(f"Embedding cache saved to {filepath} ({file_size_mb:.1f} MB)")
    print(f"✅ Cache saved to {filepath} ({file_size_mb:.1f} MB)")


def load_embeddings_json(filepath: str = DEFAULT_CACHE_PATH) -> Dict[str, dict]:
    """
    Load embedding cache from JSON file.

    Args:
        filepath: Path to JSON file (default: chatbot/data/technique_embeddings.json)

    Returns:
        Embedding cache dict

    Raises:
        FileNotFoundError: If cache file doesn't exist
        ValueError: If cache file is invalid
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Embedding cache not found at {filepath}. "
            f"Run build_technique_embeddings() first or use /build-embeddings-cache skill."
        )

    with open(filepath, 'r') as f:
        cache = json.load(f)

    technique_count = len(cache)
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)

    logger.info(f"Loaded {technique_count} technique embeddings from {filepath} ({file_size_mb:.1f} MB)")

    return cache


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
        >>> from chatbot.modules.mitre import MitreHelper
        >>> mitre = MitreHelper(use_local=True)
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
        technique = mitre.get_technique_by_id(technique_id)

        if technique:
            enriched_results.append({
                "technique_id": technique_id,
                "external_id": external_id,
                "name": name,
                "similarity_score": score,
                "description": technique.get("description", ""),
                "tactics": mitre.get_tactics_for_technique(external_id),
                "platforms": technique.get("x_mitre_platforms", [])
            })

    return enriched_results


if __name__ == "__main__":
    # Test semantic search
    print("Testing semantic search module...\n")

    from chatbot.modules.mitre import MitreHelper

    # Initialize MITRE
    print("Loading MITRE data...")
    mitre = MitreHelper(use_local=True)
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
