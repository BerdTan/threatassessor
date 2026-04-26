"""
OpenRouter embeddings client with rate limiting.

Provides embedding generation using OpenRouter's free tier:
- Model: nvidia/llama-nemotron-embed-vl-1b-v2:free
- Dimensions: 2048
- Rate limit: 20 requests/minute (handled automatically)
"""

import os
import numpy as np
import requests
from typing import List, Union
import logging
from chatbot.modules.rate_limiter import rate_limited
from agentic.helper import get_openrouter_api_key

logger = logging.getLogger(__name__)

# OpenRouter API configuration
EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"


@rate_limited(max_retries=3, base_delay=2.0)
def get_embedding(
    text: str,
    model: str = DEFAULT_EMBEDDING_MODEL
) -> List[float]:
    """
    Get embedding vector for a single text using OpenRouter.

    Args:
        text: Input text to embed
        model: Embedding model name (default: nvidia/llama-nemotron-embed-vl-1b-v2:free)

    Returns:
        List of floats representing the embedding vector (2048 dimensions)

    Raises:
        RuntimeError: If API call fails after 3 retries
        ValueError: If API key is not configured

    Note:
        Rate limited to 20 requests/minute automatically via @rate_limited decorator
    """
    api_key = get_openrouter_api_key()
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not found in environment. "
            "Please add to .env file: OPENROUTER_API_KEY=your_key_here"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",  # Required by OpenRouter
        "X-Title": "MITRE-Chatbot"
    }

    payload = {
        "model": model,
        "input": text
    }

    try:
        response = requests.post(
            EMBEDDING_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        data = response.json()
        embedding = data["data"][0]["embedding"]

        logger.debug(f"Generated embedding with {len(embedding)} dimensions")
        return embedding

    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def get_embeddings_batch(
    texts: List[str],
    model: str = DEFAULT_EMBEDDING_MODEL
) -> List[List[float]]:
    """
    Get embeddings for multiple texts.

    Args:
        texts: List of input texts to embed
        model: Embedding model name (default: nvidia/llama-nemotron-embed-vl-1b-v2:free)

    Returns:
        List of embedding vectors, one per input text

    Note:
        Calls get_embedding() for each text sequentially.
        Rate limiting handled automatically (20 req/min).
        For 823 techniques: ~41 minutes with rate limiting.
    """
    embeddings = []
    total = len(texts)

    logger.info(f"Generating embeddings for {total} texts...")

    for i, text in enumerate(texts, 1):
        try:
            embedding = get_embedding(text, model)
            embeddings.append(embedding)

            if i % 10 == 0 or i == total:
                logger.info(f"Progress: {i}/{total} embeddings generated")

        except Exception as e:
            logger.error(f"Failed to embed text {i}/{total}: {str(e)}")
            # After 3 retries failed, log and continue
            embeddings.append([])  # Empty embedding for failed texts

    return embeddings


def cosine_similarity(emb1: List[float], emb2: List[float]) -> float:
    """
    Calculate cosine similarity between two embedding vectors.

    Args:
        emb1: First embedding vector
        emb2: Second embedding vector

    Returns:
        Similarity score between -1 and 1 (higher = more similar)
        Returns 0.0 if either embedding is empty

    Formula:
        similarity = (A · B) / (||A|| * ||B||)
    """
    if not emb1 or not emb2:
        return 0.0

    # Convert to numpy arrays for efficient computation
    a = np.array(emb1)
    b = np.array(emb2)

    # Cosine similarity formula
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))
