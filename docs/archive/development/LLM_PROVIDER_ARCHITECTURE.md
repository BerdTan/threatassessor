# Multi-Provider LLM Architecture

**Date:** 2026-05-09  
**Context:** Flexible provider abstraction for LLM as Judge (Phase 3C)  
**Requirement:** Support OpenRouter, AWS Bedrock, Anthropic direct, Azure OpenAI, Vertex AI

---

## Current State Analysis

### Existing Implementation (`agentic/llm.py`)

**Strengths:**
- ✅ Uses LiteLLM (supports 100+ providers)
- ✅ Simple interface: `generate_response()` and `generate_response_with_system()`
- ✅ Error handling and logging

**Limitations:**
- ❌ Hard-coded to OpenRouter only (`get_openrouter_api_key()`)
- ❌ OpenRouter-specific headers hard-coded
- ❌ No provider selection mechanism
- ❌ No cost tracking or fallback logic
- ❌ Cannot mix providers (e.g., OpenRouter for analysis, Bedrock for verification)

**Usage Pattern:**
```python
from agentic.llm import generate_response_with_system

response = generate_response_with_system(
    prompt="Analyze this architecture...",
    system_message="You are a security expert...",
    model="openrouter/google/gemma-4-26b-a4b-it:free"
)
```

---

## Design Principles

### 1. Provider Abstraction (Strategy Pattern)

**Goal:** Swap providers without changing caller code

```python
# Before (hard-coded)
response = generate_response(prompt, model="openrouter/...")

# After (provider-agnostic)
response = llm_client.generate(prompt, provider="bedrock", model="claude-sonnet-4")
```

### 2. LiteLLM as Foundation

**Why LiteLLM:**
- Supports 100+ providers (OpenRouter, Bedrock, Azure, Anthropic, Vertex, etc.)
- Unified API across providers
- Built-in retry logic and error handling
- Active maintenance

**Architecture:**
```
┌─────────────────────────────────────────────┐
│         Application Layer                   │
│  (ground_truth_generator, llm_mitre_analyzer)│
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│      LLMClient (New Abstraction)            │
│  - Provider selection                       │
│  - Cost tracking                            │
│  - Fallback logic                           │
│  - Validation mode (LLM as Judge)           │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│         LiteLLM (Unified API)               │
│  - OpenRouter provider                      │
│  - AWS Bedrock provider                     │
│  - Anthropic provider                       │
│  - Azure OpenAI provider                    │
│  - Vertex AI provider                       │
└─────────────────────────────────────────────┘
```

### 3. Configuration-Driven

**Provider configuration in `.env` or `config.yaml`:**
```env
# Primary provider (analysis)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free

# Verification provider (LLM as Judge) - Using Bedrock API Key (recommended)
LLM_VERIFIER_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_API_KEY=AKabcdef123...  # Get from AWS Console → Bedrock → API Keys
BEDROCK_MODEL=anthropic.claude-sonnet-4-20250514-v1:0

# Fallback providers
LLM_FALLBACK_PROVIDERS=anthropic,azure
ANTHROPIC_API_KEY=sk-ant-...
AZURE_OPENAI_KEY=...
```

### 4. Cost and Performance Tracking

**Metrics per provider:**
- Total tokens used
- Estimated cost
- Latency (p50, p95, p99)
- Error rate
- Success rate

---

## Implementation Plan

### Phase 1: Provider Abstraction Layer (3-4 hours)

**File:** `agentic/llm_client.py` (replaces `agentic/llm.py`)

#### 1.1 Provider Configuration

```python
"""
Multi-provider LLM client using LiteLLM.

Supports: OpenRouter, AWS Bedrock, Anthropic, Azure OpenAI, Vertex AI
"""

import logging
from typing import Optional, Dict, Any, List, Literal
from dataclasses import dataclass
from enum import Enum
import litellm
from agentic.helper import (
    load_env,
    get_openrouter_api_key,
    get_aws_bedrock_api_key,
    get_aws_region,
    get_llm_provider,
    get_llm_verifier_provider
)
import os

logger = logging.getLogger(__name__)

# Provider types
class LLMProvider(str, Enum):
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
    # OpenRouter free tier fallback chain (if primary rate-limited)
    LLMProvider.OPENROUTER_FALLBACK: [
        "openrouter/google/gemma-4-26b-a4b-it:free",       # Try first (best quality)
        "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # Fallback (works ~33% time)
    ],
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
                api_key=get_openrouter_api_key(),  # Use helper
                extra_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "MITRE-ThreatModeling"
                }
            )
        
        elif provider == LLMProvider.BEDROCK:
            return cls(
                provider=provider,
                api_key=get_aws_bedrock_api_key(),  # Use helper (bearer token)
                region=get_aws_region(),            # Use helper (default: us-east-1)
                cost_per_1k_tokens=0.003  # Claude Sonnet 4 pricing
            )
        
        elif provider == LLMProvider.ANTHROPIC:
            return cls(
                provider=provider,
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                cost_per_1k_tokens=0.003  # Claude Sonnet 4 pricing
            )
        
        elif provider == LLMProvider.AZURE:
            return cls(
                provider=provider,
                api_key=os.getenv("AZURE_OPENAI_KEY"),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
        
        elif provider == LLMProvider.VERTEX:
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
            # Check GCP credentials
            return os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None
        
        return False
```

#### 1.2 LLM Client Class

```python
@dataclass
class LLMResponse:
    """Structured response from LLM."""
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    cost_usd: float
    latency_seconds: float
    metadata: Dict[str, Any]

@dataclass
class LLMUsageStats:
    """Cumulative usage statistics."""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_seconds: float = 0.0
    provider_stats: Dict[LLMProvider, Dict[str, Any]] = None

    def __post_init__(self):
        if self.provider_stats is None:
            self.provider_stats = {}


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
        >>> client = LLMClient(primary_provider="bedrock")
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
            provider_str = get_llm_provider()  # Use helper (default: openrouter)
            primary_provider = LLMProvider(provider_str)
        
        self.primary_provider = primary_provider
        self.primary_config = ProviderConfig.from_env(primary_provider)
        
        # Load fallback providers
        if fallback_providers is None:
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
            verifier_str = get_llm_verifier_provider()  # Use helper (optional)
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
        import time
        
        # Determine provider and config
        if provider is None:
            provider = self.primary_provider
            config = self.primary_config
        else:
            config = self._get_config(provider)
        
        # Determine model
        if model is None:
            model = PROVIDER_MODELS[provider][quality]
        
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Attempt generation with fallback
        # Special case: OpenRouter free tier has model-level fallback
        if provider == LLMProvider.OPENROUTER and model is None:
            models_to_try = PROVIDER_MODELS.get(LLMProvider.OPENROUTER_FALLBACK, [
                PROVIDER_MODELS[LLMProvider.OPENROUTER][quality]
            ])
        else:
            models_to_try = [model if model else PROVIDER_MODELS[provider][quality]]
        
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
                    if content is None:
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
                
                except Exception as e:
                    logger.warning(f"Model {attempt_model} failed: {e}")
                    last_error = e
                    # Try next model in OpenRouter fallback chain
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
            verification_prompt: Prompt template for verification
            **kwargs: Additional args for generate()
        
        Returns:
            LLMResponse with verification result
        
        Example:
            >>> analysis = "This architecture has 3 attack paths..."
            >>> result = client.verify(
            ...     analysis=analysis,
            ...     architecture=mermaid_diagram,
            ...     verification_prompt="Validate this threat analysis..."
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


# Backward-compatible functions
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
```

---

## Usage Examples

### Example 1: Basic Usage (OpenRouter with Automatic Fallback)

```python
from agentic.llm_client import LLMClient

# Use default provider (OpenRouter from .env)
# Automatically falls back: Gemma 4 → Nemotron 3 if rate-limited
client = LLMClient()

response = client.generate(
    prompt="Explain MITRE ATT&CK T1190",
    system_message="You are a cybersecurity expert."
)

print(response.content)
print(f"Model used: {response.model}")  # Shows which model succeeded
print(f"Cost: ${response.cost_usd:.4f}, Tokens: {response.tokens_used}")
```

**How fallback works:**
1. Try `google/gemma-4-26b-a4b-it:free` (best quality)
2. If rate-limited (429 error), try `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
3. If both fail, try fallback providers (e.g., Bedrock)

**Output example:**
```
Model used: openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
Cost: $0.0000, Tokens: 85
```

### Example 2: AWS Bedrock (Claude Sonnet 4)

**How to get AWS Bedrock API Key:**
1. Go to AWS Console → Amazon Bedrock
2. Navigate to "API Keys" in the left sidebar
3. Click "Create API Key"
4. Copy the key (format: `AKabcdef123...`)
5. Set permissions: Bedrock Model Access + specific region

**Benefits of Bedrock API Keys:**
- ✅ Simple bearer token authentication (no AWS signature calculation)
- ✅ Scoped permissions (region-specific, time-limited)
- ✅ No need for IAM access key/secret key
- ✅ Easier rotation and revocation
- 📚 [AWS Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html)

```env
# .env
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_API_KEY=AKabcdef123...  # From AWS Console → Bedrock → API Keys
BEDROCK_MODEL=anthropic.claude-sonnet-4-20250514-v1:0
```

```python
from agentic.llm_client import LLMClient, LLMProvider

client = LLMClient(primary_provider=LLMProvider.BEDROCK)

response = client.generate(
    prompt="Analyze this architecture for threats...",
    system_message="You are a threat modeling expert.",
    quality="high_quality"  # Uses Claude Sonnet 4
)
```

### Example 3: LLM as Judge (Bedrock verifies OpenRouter)

```env
# .env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...

LLM_VERIFIER_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_API_KEY=AKabcdef123...
```

```python
from agentic.llm_client import LLMClient, LLMProvider

client = LLMClient(
    primary_provider=LLMProvider.OPENROUTER,
    verifier_provider=LLMProvider.BEDROCK
)

# Generate analysis with OpenRouter (free/cheap)
analysis_response = client.generate(
    prompt=f"Analyze this architecture:\n{mermaid_diagram}",
    system_message="You are a threat analyst.",
    quality="fast"  # Use fast/cheap model
)

# Verify with Bedrock Claude Sonnet 4 (high quality)
verification = client.verify(
    analysis=analysis_response.content,
    architecture=mermaid_diagram,
    verification_prompt="""
Review this threat analysis for completeness:

Architecture:
{architecture}

Analysis:
{analysis}

Check for:
1. Missing attack paths
2. Incorrect MITRE technique mappings
3. Overlooked vulnerabilities
4. Logical inconsistencies

Provide:
- Completeness score (0-100%)
- List of issues found
- Suggestions for improvement
"""
)

print(f"Verification result:\n{verification.content}")
print(f"Total cost: ${analysis_response.cost_usd + verification.cost_usd:.4f}")
```

### Example 4: Multi-Provider Fallback

```python
from agentic.llm_client import LLMClient, LLMProvider

client = LLMClient(
    primary_provider=LLMProvider.OPENROUTER,
    fallback_providers=[
        LLMProvider.ANTHROPIC,
        LLMProvider.BEDROCK
    ]
)

# If OpenRouter fails, automatically tries Anthropic, then Bedrock
response = client.generate(
    prompt="Analyze threats...",
    quality="high_quality"
)

print(f"Provider used: {response.provider}")
```

### Example 5: Cost Tracking

```python
client = LLMClient(enable_cost_tracking=True)

# Make multiple calls
for i in range(10):
    client.generate(prompt=f"Analysis {i}...")

# Get usage stats
stats = client.get_usage_stats()
print(f"Total requests: {stats.total_requests}")
print(f"Total tokens: {stats.total_tokens}")
print(f"Total cost: ${stats.total_cost_usd:.2f}")
print(f"Average latency: {stats.total_latency_seconds / stats.total_requests:.2f}s")

# Per-provider breakdown
for provider, pstats in stats.provider_stats.items():
    print(f"\n{provider}:")
    print(f"  Requests: {pstats['requests']}")
    print(f"  Cost: ${pstats['cost_usd']:.2f}")
```

---

## Migration Strategy (llm.py → llm_client.py)

### Current State: `agentic/llm.py`

**Existing functionality:**
- ✅ `generate_response()` - Simple prompt generation
- ✅ `generate_response_with_system()` - With system message
- ✅ OpenRouter integration with LiteLLM
- ✅ Basic error handling
- ❌ Hard-coded to OpenRouter only
- ❌ No provider abstraction
- ❌ No cost tracking
- ❌ No fallback logic beyond single provider

**Current usage in codebase:**
```bash
# Find all usages
grep -r "from agentic.llm import" --include="*.py"
# Expected: chatbot/modules/llm_mitre_analyzer.py, tests/, etc.
```

### Migration Approach: **Replace, Not Duplicate**

**Strategy:** `llm_client.py` will **replace** `llm.py` (not coexist)

**Rationale:**
1. Avoid confusion (single source of truth)
2. Prevent duplicate code maintenance
3. Force migration to better architecture
4. Cleaner codebase

### Step-by-Step Migration

#### Phase 1: Implement `llm_client.py` with Backward Compatibility

**File:** `agentic/llm_client.py` (new)

**Includes legacy wrapper functions:**
```python
# At bottom of llm_client.py
def generate_response(prompt: str, model: str = None, **kwargs) -> str:
    """Legacy wrapper - maintains backward compatibility."""
    client = get_client()
    response = client.generate(prompt=prompt, model=model, **kwargs)
    return response.content

def generate_response_with_system(prompt: str, system_message: str, **kwargs) -> str:
    """Legacy wrapper - maintains backward compatibility."""
    client = get_client()
    response = client.generate(
        prompt=prompt, 
        system_message=system_message, 
        **kwargs
    )
    return response.content
```

**Benefits:**
- ✅ Existing code continues to work
- ✅ Can import from `agentic.llm_client` instead of `agentic.llm`
- ✅ Gradual migration path

#### Phase 2: Deprecate `llm.py`

**File:** `agentic/llm.py` (updated)

**Convert to thin wrapper with deprecation warning:**
```python
"""
DEPRECATED: Use agentic.llm_client instead.

This module is maintained for backward compatibility only.
All new code should use:
    from agentic.llm_client import LLMClient, generate_response_with_system
"""

import warnings
from agentic.llm_client import (
    generate_response as _generate_response,
    generate_response_with_system as _generate_response_with_system,
    get_available_models as _get_available_models
)

def generate_response(*args, **kwargs):
    warnings.warn(
        "agentic.llm.generate_response is deprecated. "
        "Use agentic.llm_client.LLMClient instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return _generate_response(*args, **kwargs)

def generate_response_with_system(*args, **kwargs):
    warnings.warn(
        "agentic.llm.generate_response_with_system is deprecated. "
        "Use agentic.llm_client.LLMClient instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return _generate_response_with_system(*args, **kwargs)

def get_available_models():
    warnings.warn(
        "agentic.llm.get_available_models is deprecated.",
        DeprecationWarning,
        stacklevel=2
    )
    return _get_available_models()
```

**Benefits:**
- ✅ No breaking changes
- ✅ Clear deprecation warnings guide migration
- ✅ Single source of truth (`llm_client.py`)

#### Phase 3: Update Existing Code (Optional, Non-Blocking)

**Files to update:**
- `chatbot/modules/llm_mitre_analyzer.py`
- `scripts/validate_llm_config.py`
- Any tests using `agentic.llm`

**Before:**
```python
from agentic.llm import generate_response_with_system

response = generate_response_with_system(
    prompt="Analyze...",
    system_message="You are...",
    model="openrouter/google/gemma-4-26b-a4b-it:free"
)
```

**After:**
```python
from agentic.llm_client import LLMClient

client = LLMClient()
response = client.generate(
    prompt="Analyze...",
    system_message="You are...",
    quality="default"  # Auto-selects model based on provider
)
```

**Or (backward compatible):**
```python
from agentic.llm_client import generate_response_with_system

response = generate_response_with_system(
    prompt="Analyze...",
    system_message="You are...",
    model="openrouter/google/gemma-4-26b-a4b-it:free"
)
```

#### Phase 4: Remove `llm.py` (Future Cleanup)

**When:** After Phase 3C complete + all tests pass

**Action:**
1. Delete `agentic/llm.py`
2. Update imports in remaining files
3. Run full test suite

**No rush:** Can keep deprecated wrapper indefinitely if needed

---

## Migration Guide

### Step 1: Install Dependencies

```bash
pip install boto3  # For AWS Bedrock
pip install anthropic  # For Anthropic direct API (optional)
pip install azure-openai  # For Azure (optional)
```

Update `requirements.txt`:
```
litellm==1.73.6
boto3>=1.34.0  # AWS Bedrock
anthropic>=0.25.0  # Anthropic direct (optional)
```

### Step 2: Update Imports (Backward Compatible)

**Option A:** Keep existing code working (no changes needed)
```python
from agentic.llm import generate_response_with_system  # Still works!
```

**Option B:** Use new client (recommended)
```python
from agentic.llm_client import LLMClient, LLMProvider

client = LLMClient()
response = client.generate(...)
```

### Step 3: Configure Providers

**For AWS Bedrock:**
```env
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_API_KEY=AKabcdef123...  # Get from AWS Console → Bedrock → API Keys
```

**For Verification (LLM as Judge):**
```env
LLM_VERIFIER_PROVIDER=bedrock
```

### Step 4: Update Modules (Ground Truth Generator)

**Before:**
```python
from agentic.llm import generate_response_with_system

response = generate_response_with_system(
    prompt=prompt,
    system_message=system,
    model="openrouter/google/gemma-4-26b-a4b-it:free"
)
```

**After (for LLM as Judge):**
```python
from agentic.llm_client import LLMClient, LLMProvider

client = LLMClient(verifier_provider=LLMProvider.BEDROCK)

# Generate analysis
analysis = client.generate(
    prompt=prompt,
    system_message=system,
    quality="fast"  # Use cheap model
)

# Verify with high-quality model
verification = client.verify(
    analysis=analysis.content,
    architecture=mermaid_diagram,
    verification_prompt=verification_template
)
```

---

## Testing Plan

### Validation Test Script (`scripts/test_llm_providers.py`)

**Quick validation script for testing LLM provider functionality:**

```bash
# Test all configured providers
python3 scripts/test_llm_providers.py

# Test specific provider (Bedrock)
python3 scripts/test_llm_providers.py --provider bedrock

# Test LLM as Judge verification mode
python3 scripts/test_llm_providers.py --test-verify

# Verbose output with full responses
python3 scripts/test_llm_providers.py -v
```

**Tests performed:**
1. ✅ Provider configuration validation (API keys, regions)
2. ✅ Basic generation (simple prompt)
3. ✅ MITRE-specific prompt (threat modeling context)
4. ✅ Cost tracking and usage statistics
5. ✅ Fallback mechanism (multi-provider)
6. ✅ LLM as Judge verification (two-model workflow)

**Output:**
- Console: Pass/fail status with timing and cost metrics
- JSON: `test_results_llm_providers.json` with detailed results

**Example output:**
```
============================================================
LLM Provider Test Suite
============================================================
Testing providers: ['bedrock', 'openrouter']

✅ bedrock configuration valid
✅ bedrock generation successful
   Tokens: 15, Cost: $0.0001, Latency: 1.23s
✅ bedrock MITRE prompt successful
✅ Cost tracking successful
   Requests: 3, Tokens: 250, Cost: $0.0008
✅ Fallback mechanism working
   Provider used: bedrock

============================================================
Test Summary
============================================================
Total: 8 tests
Passed: 8 ✅
Failed: 0 ❌

🎉 All tests passed!

Results exported to: test_results_llm_providers.json
```

### Unit Tests (`tests/test_llm_client.py`)

```python
import pytest
from agentic.llm_client import LLMClient, LLMProvider, ProviderConfig

def test_provider_config_openrouter():
    config = ProviderConfig.from_env(LLMProvider.OPENROUTER)
    assert config.provider == LLMProvider.OPENROUTER
    assert config.extra_headers is not None

def test_provider_config_bedrock():
    config = ProviderConfig.from_env(LLMProvider.BEDROCK)
    assert config.provider == LLMProvider.BEDROCK
    assert config.region is not None

def test_llm_client_basic():
    client = LLMClient(primary_provider=LLMProvider.OPENROUTER)
    response = client.generate(prompt="Hello", max_tokens=10)
    assert len(response.content) > 0
    assert response.provider == LLMProvider.OPENROUTER

def test_llm_client_fallback():
    # Configure with non-existent primary, valid fallback
    client = LLMClient(
        primary_provider=LLMProvider.OPENROUTER,
        fallback_providers=[LLMProvider.ANTHROPIC]
    )
    # Should fall back if primary fails
    response = client.generate(prompt="Hello")
    assert len(response.content) > 0

def test_cost_tracking():
    client = LLMClient(enable_cost_tracking=True)
    client.generate(prompt="Test", max_tokens=100)
    stats = client.get_usage_stats()
    assert stats.total_requests > 0
    assert stats.total_tokens > 0

def test_verify_mode():
    client = LLMClient(
        primary_provider=LLMProvider.OPENROUTER,
        verifier_provider=LLMProvider.BEDROCK
    )
    
    analysis = "This architecture has 3 attack paths..."
    architecture = "graph TD..."
    
    verification = client.verify(
        analysis=analysis,
        architecture=architecture,
        verification_prompt="Verify: {analysis}"
    )
    
    assert len(verification.content) > 0
    assert verification.provider == LLMProvider.BEDROCK
```

### Integration Tests

```bash
# Test OpenRouter
LLM_PROVIDER=openrouter python3 -m pytest tests/test_llm_client.py -k openrouter -v

# Test AWS Bedrock
LLM_PROVIDER=bedrock python3 -m pytest tests/test_llm_client.py -k bedrock -v

# Test LLM as Judge
LLM_VERIFIER_PROVIDER=bedrock python3 -m pytest tests/test_llm_client.py -k verify -v
```

---

## Phase 3C Integration (LLM as Judge)

### Verification Workflow

```python
def generate_architecture_analysis_with_verification(
    mermaid_diagram: str,
    use_verification: bool = True
) -> Dict[str, Any]:
    """
    Generate threat analysis with optional LLM-based verification.
    
    Returns:
        {
            "analysis": {...},
            "verification": {...} | None,
            "confidence_adjustment": float
        }
    """
    from agentic.llm_client import LLMClient, LLMProvider
    
    # Initialize client with verifier
    client = LLMClient(
        primary_provider=LLMProvider.OPENROUTER,
        verifier_provider=LLMProvider.BEDROCK if use_verification else None
    )
    
    # Generate analysis (cheap model)
    analysis_prompt = f"Analyze threats in this architecture:\n{mermaid_diagram}"
    analysis_response = client.generate(
        prompt=analysis_prompt,
        system_message="You are a threat modeling expert.",
        quality="fast",
        max_tokens=2000
    )
    
    result = {
        "analysis": parse_analysis(analysis_response.content),
        "verification": None,
        "confidence_adjustment": 1.0,
        "cost_usd": analysis_response.cost_usd
    }
    
    # Verify with high-quality model
    if use_verification:
        verification_response = client.verify(
            analysis=analysis_response.content,
            architecture=mermaid_diagram,
            verification_prompt=VERIFICATION_TEMPLATE,
            max_tokens=1500
        )
        
        verification_result = parse_verification(verification_response.content)
        result["verification"] = verification_result
        result["confidence_adjustment"] = verification_result["completeness_score"] / 100.0
        result["cost_usd"] += verification_response.cost_usd
        
        logger.info(f"Verification: completeness={verification_result['completeness_score']}%, "
                   f"issues={len(verification_result['issues'])}")
    
    return result
```

### Verification Prompt Template

```python
VERIFICATION_TEMPLATE = """
You are a security verification expert reviewing a threat analysis.

ARCHITECTURE:
{architecture}

THREAT ANALYSIS TO VERIFY:
{analysis}

VERIFICATION TASKS:

1. COMPLETENESS CHECK
   - Are all entry points analyzed? (Internet, Partners, RemoteAccess, etc.)
   - Are all sensitive targets covered? (Databases, APIs, Admin Portals)
   - Are internal components (orphan nodes) considered?
   
2. ATTACK PATH VALIDATION
   - Are attack paths logically sound?
   - Are hop sequences realistic?
   - Are there missing obvious paths?
   
3. MITRE TECHNIQUE ACCURACY
   - Are MITRE technique IDs correct?
   - Do techniques match the attack context?
   - Are techniques missing for any paths?
   
4. CONTROL RECOMMENDATION QUALITY
   - Do recommended controls address identified threats?
   - Are controls appropriate for the architecture type?
   - Are critical gaps overlooked?
   
5. LOGICAL CONSISTENCY
   - Do RAPIDS threat scores align with attack path severity?
   - Is residual risk calculation reasonable?
   - Are there contradictions in the analysis?

OUTPUT FORMAT (JSON):
{
  "completeness_score": <0-100>,
  "issues": [
    {
      "category": "completeness|attack_path|mitre|controls|logic",
      "severity": "critical|high|medium|low",
      "description": "...",
      "suggestion": "..."
    }
  ],
  "strengths": ["..."],
  "overall_assessment": "..."
}
"""
```

---

## Effort Estimate

| Task | Description | Effort |
|------|-------------|--------|
| 1. Core LLMClient class | Provider abstraction, config, generate() | 2h |
| 2. Provider-specific setup | Bedrock, Anthropic, Azure configs | 1h |
| 3. Cost tracking | Usage stats, token counting | 0.5h |
| 4. Verification mode | verify() method, prompt template | 1h |
| 5. Backward compatibility | Wrapper functions, migration | 0.5h |
| 6. Unit tests | Provider configs, fallback, verify | 1h |
| 7. Integration tests | Test with real providers | 1h |
| 8. Documentation | Usage examples, migration guide | 1h |
| **TOTAL** | | **8 hours** |

---

## Deliverables

1. **`agentic/llm_client.py`** - New multi-provider client (500+ lines)
2. **`scripts/test_llm_providers.py`** - Validation test script (450+ lines) ⭐ **NEW**
3. **`tests/test_llm_client.py`** - Comprehensive test suite (300+ lines)
4. **Updated `requirements.txt`** - Add boto3, anthropic (optional)
5. **Updated `.env.example`** - Show provider configuration with Bedrock API Key
6. **Migration guide** - In this document
7. **Phase 3C integration** - Ready for LLM as Judge implementation

---

## Success Criteria

✅ **Backward compatibility:** Existing code works without changes  
✅ **Multi-provider support:** OpenRouter, Bedrock, Anthropic, Azure, Vertex  
✅ **LLM as Judge ready:** verify() method with verification prompt  
✅ **Cost tracking:** Per-provider token and cost monitoring  
✅ **Automatic fallback:** Graceful degradation if provider fails  
✅ **Comprehensive tests:** >80% code coverage  
✅ **Documentation:** Clear usage examples and migration guide  

---

**Document Version:** 1.0  
**Date:** 2026-05-09  
**Status:** Design Complete - Ready for Implementation  
**Estimated Effort:** 8 hours
