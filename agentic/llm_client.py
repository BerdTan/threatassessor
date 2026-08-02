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
import os
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
    """Supported LLM providers.

    Values must match the keys in agentic/providers.PROVIDER_MANIFEST.
    To add a new provider: add to PROVIDER_MANIFEST first, then add the
    enum value here. The elif chains in from_env/validate/_call_litellm
    are gone — all logic reads from the manifest.
    """
    OPENROUTER = "openrouter"
    BEDROCK    = "bedrock"
    ANTHROPIC  = "anthropic"
    AZURE      = "azure"
    VERTEX     = "vertex"


from agentic.providers import PROVIDER_MANIFEST as _PM

# PROVIDER_MODELS — derived from manifest, kept for backward compatibility
PROVIDER_MODELS = {
    LLMProvider(name): manifest["models"]
    for name, manifest in _PM.items()
    if manifest.get("active", False) and name in [p.value for p in LLMProvider]
}

# OpenRouter free tier fallback chain (backward compat alias)
OPENROUTER_FALLBACK_MODELS = [
    _PM["openrouter"]["models"]["default"],
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
        """Load provider config from the manifest. No elif chains — all providers
        are configured in agentic/providers.PROVIDER_MANIFEST."""
        from agentic.providers import get_manifest, resolve_api_key, base_url_for
        load_env()

        m = get_manifest(provider.value)
        if not m:
            raise ValueError(
                f"Unknown provider '{provider.value}'. "
                f"Add it to agentic/providers.PROVIDER_MANIFEST first."
            )

        api_key  = resolve_api_key(provider.value)
        region   = os.getenv(m["region_env"]) if m.get("region_env") else None
        endpoint = base_url_for(provider.value) or None

        return cls(
            provider          = provider,
            api_key           = api_key,
            region            = region,
            endpoint          = endpoint,
            extra_headers     = dict(m.get("extra_headers", {})) or None,
            cost_per_1k_tokens = m.get("cost_per_1k"),
        )

    def validate(self) -> bool:
        """Validate provider configuration against the manifest."""
        from agentic.providers import get_manifest
        m = get_manifest(self.provider.value)
        if not m:
            return False

        key_env = m.get("api_key_env")
        if key_env is None:
            # No key needed (Vertex GCP credentials, local Ollama)
            # For Vertex: check GOOGLE_APPLICATION_CREDENTIALS separately
            if self.provider.value == "vertex":
                return os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None
            return True   # local provider, no key required

        return self.api_key is not None


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

        # Load fallback providers from environment
        if fallback_providers is None:
            import os
            fallback_str = os.getenv("LLM_FALLBACK_PROVIDERS", "")
            if fallback_str:
                # Use explicit fallback from env
                fallback_providers = [
                    LLMProvider(p.strip())
                    for p in fallback_str.split(",")
                    if p.strip()
                ]
            else:
                # No fallback configured
                fallback_providers = []

        self.fallback_providers = fallback_providers

        # Load configs for fallback providers (skip if no valid credentials)
        self.fallback_configs = {}
        for p in fallback_providers:
            try:
                config = ProviderConfig.from_env(p)
                if config.validate():
                    self.fallback_configs[p] = config
                else:
                    logger.warning(f"Fallback provider {p.value} has invalid configuration, skipping")
            except Exception as e:
                logger.warning(f"Failed to load fallback provider {p.value}: {e}")

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
                f"Primary provider {primary_provider.value} not configured. "
                f"Check environment variables."
            )

        # Usage tracking
        self.enable_cost_tracking = enable_cost_tracking
        self.usage_stats = LLMUsageStats()

        # Log configuration
        configured_providers = [primary_provider.value]
        if self.fallback_configs:
            configured_providers.extend([p.value for p in self.fallback_configs.keys()])

        logger.info(f"LLMClient initialized: primary={primary_provider.value}, "
                   f"fallbacks={[p.value for p in fallback_providers]}, "
                   f"verifier={verifier_provider.value if verifier_provider else None}")
        logger.info(f"Configured providers: {configured_providers}")

    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
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
        # Apply config defaults when caller didn't specify
        if temperature is None or max_tokens is None:
            try:
                from chatbot.config import get_settings as _gs_llm
                _llm_cfg = _gs_llm().llm
                if temperature is None:
                    temperature = _llm_cfg.temperature
                if max_tokens is None:
                    max_tokens = _llm_cfg.max_tokens
            except Exception:
                if temperature is None:
                    temperature = 0.7
                if max_tokens is None:
                    max_tokens = 1000

        # Determine provider and config
        if provider is None:
            provider = self.primary_provider
            config = self.primary_config
        else:
            config = self._get_config(provider)

        # Determine model(s) to try
        # Special case: OpenRouter free tier has model-level fallback
        if provider == LLMProvider.OPENROUTER and model is None:
            # Check if user configured custom models in .env
            import os
            custom_models = os.getenv("OPENROUTER_ACTIVE_MODELS", "")
            if custom_models:
                # User specified models: "model1:free,model2:free"
                models_to_try = [
                    f"openrouter/{m.strip()}"
                    for m in custom_models.split(",")
                    if m.strip()
                ]
            else:
                # Use default fallback chain
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
        """Call LiteLLM. All provider-specific config read from the manifest —
        no elif chains. Adding a new provider only requires editing providers.py."""
        from agentic.providers import get_manifest

        if config.api_key:
            litellm.api_key = config.api_key

        m = get_manifest(config.provider.value) or {}
        extra_kwargs: dict = {}

        # Headers (e.g. OpenRouter HTTP-Referer)
        if config.extra_headers:
            extra_kwargs["extra_headers"] = config.extra_headers

        # Base URL override — applies when base_url_env is set or provider has a custom base_url
        if config.endpoint:
            extra_kwargs["api_base"] = config.endpoint

        # Region (AWS Bedrock)
        if config.region:
            extra_kwargs["aws_region_name"] = config.region
            # Bedrock bearer token passed as api_key kwarg (not litellm.api_key global)
            if config.api_key:
                extra_kwargs["api_key"] = config.api_key

        # Any extra static litellm kwargs declared in manifest
        extra_kwargs.update(m.get("litellm_kwargs", {}))

        return litellm.completion(
            model=model,
            messages=messages,
            drop_params=True,
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
