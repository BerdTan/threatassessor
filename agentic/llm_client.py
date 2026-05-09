"""
Multi-provider LLM client using LiteLLM.

Supports: OpenRouter, AWS Bedrock, Anthropic, Azure OpenAI, Vertex AI

Features:
- Provider abstraction (easy to switch providers)
- Automatic fallback (OpenRouter free tier: Gemma → Nemotron → Bedrock)
- Cost tracking and usage statistics
- LLM as Judge verification workflow
- Backward-compatible wrappers for existing code

Usage:
    >>> from agentic.llm_client import LLMClient
    >>> client = LLMClient()
    >>> response = client.generate(
    ...     prompt="Analyze this architecture...",
    ...     system_message="You are a threat analyst."
    ... )
    >>> print(response.content)
"""

import logging
import time
from typing import Optional, Dict, Any, List, Literal
from dataclasses import dataclass, field
from enum import Enum

import litellm
from litellm.exceptions import RateLimitError

from agentic.helper import (
    load_env,
    get_openrouter_api_key,
    get_aws_bedrock_api_key,
    get_aws_region,
    get_llm_provider,
    get_llm_verifier_provider
)

logger = logging.getLogger(__name__)

# Provider types
class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENROUTER = "openrouter"
    BEDROCK = "bedrock"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    VERTEX = "vertex"


# Model configurations per provider
PROVIDER_MODELS = {
    LLMProvider.OPENROUTER: {
        "default": "openrouter/google/gemma-4-26b-a4b-it:free",
        "high_quality": "openrouter/anthropic/claude-sonnet-4",
        "fast": "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    },
    LLMProvider.BEDROCK: {
        "default": "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
        "high_quality": "bedrock/us.anthropic.claude-opus-4-20250514-v1:0",
        "fast": "bedrock/us.anthropic.claude-haiku-4-20250514-v1:0"
    },
    LLMProvider.ANTHROPIC: {
        "default": "anthropic/claude-sonnet-4-20250514",
        "high_quality": "anthropic/claude-opus-4-20250514",
        "fast": "anthropic/claude-haiku-4-20250514"
    },
    LLMProvider.AZURE: {
        "default": "azure/gpt-4",
        "high_quality": "azure/gpt-4-turbo",
        "fast": "azure/gpt-35-turbo"
    },
    LLMProvider.VERTEX: {
        "default": "vertex_ai/claude-sonnet-4@20250514",
        "high_quality": "vertex_ai/claude-opus-4@20250514",
        "fast": "vertex_ai/claude-haiku-4@20250514"
    }
}

# OpenRouter free tier fallback chain (if primary rate-limited)
OPENROUTER_FALLBACK_MODELS = [
    "openrouter/google/gemma-4-26b-a4b-it:free",       # Try first (best quality)
    "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # Fallback
]


@dataclass
class ProviderConfig:
    """Configuration for a specific LLM provider."""
    provider: LLMProvider
    api_key: Optional[str] = None
    region: Optional[str] = None  # For AWS Bedrock
    endpoint: Optional[str] = None  # For custom endpoints
    extra_headers: Optional[Dict[str, str]] = None
    cost_per_1k_tokens: Optional[float] = None  # For cost tracking

    @classmethod
    def from_env(cls, provider: LLMProvider) -> "ProviderConfig":
        """Load provider config from environment variables using helper functions."""
        load_env()

        if provider == LLMProvider.OPENROUTER:
            return cls(
                provider=provider,
                api_key=get_openrouter_api_key(),
                extra_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "MITRE-ThreatModeling"
                }
            )

        elif provider == LLMProvider.BEDROCK:
            return cls(
                provider=provider,
                api_key=get_aws_bedrock_api_key(),  # Bearer token
                region=get_aws_region(),
                cost_per_1k_tokens=0.003  # Claude Sonnet 4 pricing
            )

        elif provider == LLMProvider.ANTHROPIC:
            import os
            return cls(
                provider=provider,
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                cost_per_1k_tokens=0.003  # Claude Sonnet 4 pricing
            )

        elif provider == LLMProvider.AZURE:
            import os
            return cls(
                provider=provider,
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )

        elif provider == LLMProvider.VERTEX:
            import os
            return cls(
                provider=provider,
                api_key=None,  # Vertex uses GCP credentials
                region=os.getenv("GCP_REGION", "us-central1")
            )

        else:
            raise ValueError(f"Unknown provider: {provider}")

    def validate(self) -> bool:
        """Validate provider configuration."""
        if self.provider == LLMProvider.OPENROUTER:
            return self.api_key is not None

        elif self.provider == LLMProvider.BEDROCK:
            # Bedrock API key is recommended (bearer token)
            return self.api_key is not None

        elif self.provider == LLMProvider.ANTHROPIC:
            return self.api_key is not None

        elif self.provider == LLMProvider.AZURE:
            return self.api_key is not None and self.endpoint is not None

        elif self.provider == LLMProvider.VERTEX:
            import os
            # Check GCP credentials
            return os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None

        return False


@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    cost_usd: float
    latency_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMUsageStats:
    """Cumulative usage statistics."""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_seconds: float = 0.0
    provider_stats: Dict[LLMProvider, Dict[str, Any]] = field(default_factory=dict)


class LLMClient:
    """
    Multi-provider LLM client with fallback support.

    Features:
    - Provider abstraction (OpenRouter, Bedrock, Anthropic, Azure, Vertex)
    - Automatic fallback on failure
    - Cost tracking
    - Performance metrics
    - Validation mode (LLM as Judge)

    Example:
        >>> client = LLMClient(primary_provider=LLMProvider.BEDROCK)
        >>> response = client.generate(
        ...     prompt="Analyze this architecture...",
        ...     system_message="You are a security expert..."
        ... )
        >>> print(response.content)
    """

    def __init__(
        self,
        primary_provider: Optional[LLMProvider] = None,
        fallback_providers: Optional[List[LLMProvider]] = None,
        verifier_provider: Optional[LLMProvider] = None,
        enable_cost_tracking: bool = True
    ):
        """
        Initialize LLM client with provider configuration.

        Args:
            primary_provider: Main provider (default: from env LLM_PROVIDER)
            fallback_providers: List of fallback providers
            verifier_provider: Provider for LLM as Judge validation
            enable_cost_tracking: Track token usage and cost
        """
        load_env()

        # Load primary provider from environment using helper
        if primary_provider is None:
            provider_str = get_llm_provider()  # Default: openrouter
            primary_provider = LLMProvider(provider_str)

        self.primary_provider = primary_provider
        self.primary_config = ProviderConfig.from_env(primary_provider)

        # Load fallback providers
        if fallback_providers is None:
            import os
            fallback_str = os.getenv("LLM_FALLBACK_PROVIDERS", "")
            fallback_providers = [
                LLMProvider(p.strip())
                for p in fallback_str.split(",")
                if p.strip()
            ]

        self.fallback_providers = fallback_providers
        self.fallback_configs = {
            p: ProviderConfig.from_env(p)
            for p in fallback_providers
        }

        # Load verifier provider (for LLM as Judge) using helper
        if verifier_provider is None:
            verifier_str = get_llm_verifier_provider()
            if verifier_str:
                verifier_provider = LLMProvider(verifier_str)

        self.verifier_provider = verifier_provider
        self.verifier_config = (
            ProviderConfig.from_env(verifier_provider)
            if verifier_provider else None
        )

        # Validate configurations
        if not self.primary_config.validate():
            raise ValueError(
                f"Primary provider {primary_provider} not configured. "
                f"Check environment variables."
            )

        # Usage tracking
        self.enable_cost_tracking = enable_cost_tracking
        self.usage_stats = LLMUsageStats()

        logger.info(f"LLMClient initialized: primary={primary_provider}, "
                   f"fallbacks={fallback_providers}, verifier={verifier_provider}")

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        quality: Literal["default", "high_quality", "fast"] = "default",
        **kwargs
    ) -> LLMResponse:
        """
        Generate LLM response with automatic provider fallback.

        Args:
            prompt: User prompt
            system_message: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            provider: Override provider (default: use primary)
            model: Override model (default: provider's default model)
            quality: Model quality tier ("default", "high_quality", "fast")
            **kwargs: Additional args passed to LiteLLM

        Returns:
            LLMResponse with content and metadata

        Raises:
            RuntimeError: If all providers fail
        """
        # Determine provider and config
        if provider is None:
            provider = self.primary_provider
            config = self.primary_config
        else:
            config = self._get_config(provider)

        # Determine model(s) to try
        # Special case: OpenRouter free tier has model-level fallback
        if provider == LLMProvider.OPENROUTER and model is None:
            models_to_try = OPENROUTER_FALLBACK_MODELS
        else:
            if model is None:
                model = PROVIDER_MODELS[provider][quality]
            models_to_try = [model]

        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        # Attempt generation with fallback (provider level)
        providers_to_try = [provider] + [
            p for p in self.fallback_providers if p != provider
        ]

        last_error = None
        for attempt_provider in providers_to_try:
            attempt_config = self._get_config(attempt_provider)

            # Use OpenRouter fallback models if applicable
            if attempt_provider == LLMProvider.OPENROUTER and attempt_provider == provider:
                attempt_models = models_to_try
            else:
                attempt_models = [PROVIDER_MODELS[attempt_provider][quality]]

            # Try each model for this provider
            for attempt_model in attempt_models:
                try:
                    logger.info(f"Attempting LLM call: provider={attempt_provider}, model={attempt_model}")

                    start_time = time.time()
                    response = self._call_litellm(
                        messages=messages,
                        model=attempt_model,
                        config=attempt_config,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs
                    )
                    latency = time.time() - start_time

                    # Extract response
                    content = response.choices[0].message.content

                    # Handle None content (Nemotron edge case)
                    if content is None:
                        logger.warning(f"Model {attempt_model} returned None content, trying next...")
                        raise RuntimeError("LLM returned None content")

                    # Calculate cost
                    tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else 0
                    cost_usd = self._calculate_cost(tokens_used, attempt_config)

                    # Track usage
                    if self.enable_cost_tracking:
                        self._track_usage(attempt_provider, tokens_used, cost_usd, latency)

                    logger.info(f"LLM call successful: {len(content)} chars, "
                              f"{tokens_used} tokens, ${cost_usd:.4f}, {latency:.2f}s")

                    return LLMResponse(
                        content=content,
                        provider=attempt_provider,
                        model=attempt_model,
                        tokens_used=tokens_used,
                        cost_usd=cost_usd,
                        latency_seconds=latency,
                        metadata={"response": response}
                    )

                except (RateLimitError, RuntimeError) as e:
                    logger.warning(f"Model {attempt_model} failed: {type(e).__name__}")
                    last_error = e
                    # Try next model in fallback chain
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error with {attempt_model}: {type(e).__name__}: {e}")
                    last_error = e
                    continue

        # All providers and models failed
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    def verify(
        self,
        analysis: str,
        architecture: str,
        verification_prompt: str,
        **kwargs
    ) -> LLMResponse:
        """
        Use LLM as Judge to verify analysis quality.

        Args:
            analysis: Generated threat analysis to verify
            architecture: Original architecture description
            verification_prompt: Prompt template for verification (use {architecture}, {analysis})
            **kwargs: Additional args for generate()

        Returns:
            LLMResponse with verification result

        Example:
            >>> analysis = "This architecture has 3 attack paths..."
            >>> result = client.verify(
            ...     analysis=analysis,
            ...     architecture=mermaid_diagram,
            ...     verification_prompt="Validate this: {analysis}"
            ... )
        """
        if self.verifier_provider is None:
            raise ValueError(
                "Verifier provider not configured. "
                "Set LLM_VERIFIER_PROVIDER in environment."
            )

        # Format verification prompt
        full_prompt = verification_prompt.format(
            architecture=architecture,
            analysis=analysis
        )

        system_message = """You are a security verification expert. Your role is to:
1. Validate threat analysis completeness
2. Check for logical inconsistencies
3. Identify missing attack paths
4. Verify MITRE technique mappings
5. Suggest improvements

Be critical but constructive."""

        return self.generate(
            prompt=full_prompt,
            system_message=system_message,
            provider=self.verifier_provider,
            quality="high_quality",  # Use best model for verification
            **kwargs
        )

    def _get_config(self, provider: LLMProvider) -> ProviderConfig:
        """Get configuration for a provider."""
        if provider == self.primary_provider:
            return self.primary_config
        elif provider in self.fallback_configs:
            return self.fallback_configs[provider]
        else:
            # Dynamically load config
            return ProviderConfig.from_env(provider)

    def _call_litellm(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: ProviderConfig,
        **kwargs
    ):
        """Call LiteLLM with provider-specific configuration."""
        # Set API key if needed
        if config.api_key:
            litellm.api_key = config.api_key

        # Provider-specific setup
        extra_kwargs = {}

        if config.provider == LLMProvider.OPENROUTER:
            extra_kwargs["extra_headers"] = config.extra_headers

        elif config.provider == LLMProvider.BEDROCK:
            # Use Bedrock API key (bearer token authentication)
            if config.api_key:
                extra_kwargs["api_key"] = config.api_key
            extra_kwargs["aws_region_name"] = config.region

        elif config.provider == LLMProvider.AZURE:
            extra_kwargs["api_base"] = config.endpoint

        # Call LiteLLM
        return litellm.completion(
            model=model,
            messages=messages,
            **extra_kwargs,
            **kwargs
        )

    def _calculate_cost(self, tokens: int, config: ProviderConfig) -> float:
        """Calculate estimated cost in USD."""
        if config.cost_per_1k_tokens is None:
            return 0.0
        return (tokens / 1000) * config.cost_per_1k_tokens

    def _track_usage(
        self,
        provider: LLMProvider,
        tokens: int,
        cost: float,
        latency: float
    ):
        """Track usage statistics."""
        self.usage_stats.total_requests += 1
        self.usage_stats.total_tokens += tokens
        self.usage_stats.total_cost_usd += cost
        self.usage_stats.total_latency_seconds += latency

        if provider not in self.usage_stats.provider_stats:
            self.usage_stats.provider_stats[provider] = {
                "requests": 0,
                "tokens": 0,
                "cost_usd": 0.0,
                "latency_seconds": 0.0
            }

        stats = self.usage_stats.provider_stats[provider]
        stats["requests"] += 1
        stats["tokens"] += tokens
        stats["cost_usd"] += cost
        stats["latency_seconds"] += latency

    def get_usage_stats(self) -> LLMUsageStats:
        """Get cumulative usage statistics."""
        return self.usage_stats

    def reset_usage_stats(self):
        """Reset usage statistics."""
        self.usage_stats = LLMUsageStats()


# Singleton instance (for backward compatibility)
_default_client: Optional[LLMClient] = None

def get_client() -> LLMClient:
    """Get default LLM client instance."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


# Backward-compatible functions (maintain existing API)
def generate_response(
    prompt: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    **kwargs
) -> str:
    """
    Backward-compatible generate_response function.

    Legacy wrapper around LLMClient.generate().

    Args:
        prompt: Input prompt for the LLM
        model: Model identifier (optional, uses default)
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate
        **kwargs: Additional arguments passed to LiteLLM

    Returns:
        Generated text response

    Example:
        >>> response = generate_response("Explain MITRE ATT&CK T1059.001")
    """
    client = get_client()
    response = client.generate(
        prompt=prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    return response.content


def generate_response_with_system(
    prompt: str,
    system_message: str,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    **kwargs
) -> str:
    """
    Backward-compatible generate_response_with_system function.

    Legacy wrapper around LLMClient.generate().

    Args:
        prompt: User prompt
        system_message: System prompt to guide LLM behavior
        model: Model identifier (optional, uses default)
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate
        **kwargs: Additional arguments passed to LiteLLM

    Returns:
        Generated text response

    Example:
        >>> system = "You are a cybersecurity expert."
        >>> response = generate_response_with_system("Explain T1059.001", system)
    """
    client = get_client()
    response = client.generate(
        prompt=prompt,
        system_message=system_message,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    return response.content


def get_available_models() -> List[str]:
    """
    Get list of available LLM models.

    Returns:
        List of model identifiers from PROVIDER_MODELS
    """
    models = []
    for provider_models in PROVIDER_MODELS.values():
        if isinstance(provider_models, dict):
            models.extend(provider_models.values())
    return models
