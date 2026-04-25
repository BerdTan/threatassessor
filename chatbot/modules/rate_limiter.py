"""
Rate limiting utilities for OpenRouter API calls.

OpenRouter free tier limits: 20 requests per minute
This module provides decorators and utilities to handle rate limiting gracefully.
"""

import time
import functools
from typing import Callable, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API calls.

    OpenRouter free tier: 20 requests/minute
    Strategy: Track request timestamps, enforce delay if needed
    """

    def __init__(self, max_requests: int = 20, time_window: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in time window (default: 20)
            time_window: Time window in seconds (default: 60)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_times = deque(maxlen=max_requests)
        self._lock = False  # Simple lock for single-threaded usage

    def wait_if_needed(self):
        """
        Wait if rate limit would be exceeded by next request.
        Uses sliding window algorithm.
        """
        if self._lock:
            time.sleep(0.1)  # Brief wait if another call is in progress
            return self.wait_if_needed()

        self._lock = True

        try:
            current_time = time.time()

            # Remove requests outside time window
            while self.request_times and current_time - self.request_times[0] > self.time_window:
                self.request_times.popleft()

            # Check if we've hit the limit
            if len(self.request_times) >= self.max_requests:
                oldest_request = self.request_times[0]
                time_since_oldest = current_time - oldest_request

                if time_since_oldest < self.time_window:
                    # Need to wait
                    wait_time = self.time_window - time_since_oldest + 1  # +1 for safety margin
                    logger.info(f"Rate limit approaching. Waiting {wait_time:.1f}s...")
                    print(f"   ⏱️  Rate limit: waiting {wait_time:.1f}s (max {self.max_requests} req/{self.time_window}s)")
                    time.sleep(wait_time)

                    # Clear old entries after waiting
                    current_time = time.time()
                    while self.request_times and current_time - self.request_times[0] > self.time_window:
                        self.request_times.popleft()

            # Record this request
            self.request_times.append(time.time())

        finally:
            self._lock = False

    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        current_time = time.time()
        recent_requests = sum(1 for t in self.request_times if current_time - t <= self.time_window)

        return {
            "max_requests": self.max_requests,
            "time_window": self.time_window,
            "recent_requests": recent_requests,
            "remaining": max(0, self.max_requests - recent_requests)
        }


# Global rate limiter instance for OpenRouter
openrouter_limiter = RateLimiter(max_requests=20, time_window=60)


def rate_limited(max_retries: int = 5, base_delay: float = 2.0):
    """
    Decorator to rate-limit API calls with exponential backoff on errors.

    Args:
        max_retries: Maximum number of retry attempts (default: 5)
        base_delay: Base delay for exponential backoff in seconds (default: 2.0)

    Usage:
        @rate_limited(max_retries=5, base_delay=2.0)
        def api_call():
            # Your API call here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Enforce rate limit before attempting
            openrouter_limiter.wait_if_needed()

            last_exception = None

            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    return result

                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Check if it's a rate limit error
                    is_rate_limit = (
                        '429' in error_msg or
                        'rate limit' in error_msg or
                        'too many requests' in error_msg
                    )

                    # Check if it's a server error (5xx)
                    is_server_error = any(code in error_msg for code in ['500', '502', '503', '504'])

                    # Decide whether to retry
                    should_retry = is_rate_limit or is_server_error

                    if not should_retry:
                        # Non-retryable error, raise immediately
                        logger.error(f"Non-retryable error in {func.__name__}: {e}")
                        raise

                    # Calculate exponential backoff
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)

                        if is_rate_limit:
                            # For rate limits, use longer delay
                            delay = max(delay, 60)  # At least 1 minute
                            logger.warning(f"Rate limit hit in {func.__name__}. Waiting {delay:.1f}s before retry {attempt + 1}/{max_retries}")
                            print(f"   ⚠️  Rate limit hit! Waiting {delay:.1f}s... (retry {attempt + 1}/{max_retries})")
                        else:
                            logger.warning(f"Server error in {func.__name__}. Waiting {delay:.1f}s before retry {attempt + 1}/{max_retries}")
                            print(f"   ⚠️  Server error. Waiting {delay:.1f}s... (retry {attempt + 1}/{max_retries})")

                        time.sleep(delay)
                    else:
                        # Max retries exceeded
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")
                        print(f"   ❌ Max retries ({max_retries}) exceeded")
                        raise last_exception

            # Should not reach here, but just in case
            raise last_exception

        return wrapper
    return decorator


def batch_with_rate_limit(items: list, batch_size: int = 3, process_fn: Callable = None) -> list:
    """
    Process items in batches with rate limiting between batches.

    Args:
        items: List of items to process
        batch_size: Number of items per batch (default: 3 for OpenRouter)
        process_fn: Function to process each batch, should accept list and return list

    Returns:
        List of results in same order as input items
    """
    results = []

    total_batches = (len(items) + batch_size - 1) // batch_size

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_num = i // batch_size + 1

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)")
        print(f"   Processing batch {batch_num}/{total_batches} ({len(batch)} items)...")

        # Rate limiter will handle waiting if needed
        openrouter_limiter.wait_if_needed()

        batch_results = process_fn(batch)
        results.extend(batch_results)

        # Small delay between batches to be conservative
        if i + batch_size < len(items):
            time.sleep(0.5)

    return results


def get_rate_limit_stats() -> dict:
    """Get current rate limit statistics."""
    return openrouter_limiter.get_stats()


if __name__ == "__main__":
    # Test the rate limiter
    print("Testing rate limiter (20 req/min)...")

    @rate_limited(max_retries=3, base_delay=2.0)
    def test_api_call(n: int):
        print(f"  API call {n}")
        if n == 5:
            raise Exception("429: Rate limit exceeded")
        return f"Result {n}"

    # Test normal calls
    for i in range(10):
        result = test_api_call(i)
        print(f"  → {result}")
        stats = get_rate_limit_stats()
        print(f"  Stats: {stats['recent_requests']}/{stats['max_requests']} requests in last {stats['time_window']}s")

    print("\n✅ Rate limiter test complete")
