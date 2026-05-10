#!/usr/bin/env python3
"""
Test script for multi-provider LLM functionality.

Tests:
1. Provider configuration validation
2. Basic LLM generation (OpenRouter, Bedrock, Anthropic)
3. Cost tracking and usage statistics
4. Fallback mechanism
5. LLM as Judge verification mode

Usage:
    # Test all configured providers
    python3 scripts/test_llm_providers.py

    # Test specific provider
    python3 scripts/test_llm_providers.py --provider bedrock

    # Test verification mode
    python3 scripts/test_llm_providers.py --test-verify

    # Verbose output
    python3 scripts/test_llm_providers.py -v
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agentic.llm_client import (
    LLMClient,
    LLMProvider,
    ProviderConfig,
    LLMResponse,
    ACTIVE_PROVIDERS,
    INACTIVE_PROVIDERS,
    OPENROUTER_FALLBACK_MODELS
)
from agentic.helper import load_env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Test prompts
TEST_PROMPT_SIMPLE = "Say 'Hello, World!' and nothing else."

TEST_PROMPT_MITRE = """Explain MITRE ATT&CK technique T1190 (Exploit Public-Facing Application) in 2-3 sentences."""

TEST_ARCHITECTURE_MERMAID = """graph TD
    Internet[Internet] --> WAF[WAF]
    WAF --> LB[Load Balancer]
    LB --> WebApp[Web Application]
    WebApp --> API[API Server]
    API --> DB[(Database)]
"""

TEST_ANALYSIS = """
This architecture has the following attack paths:

1. Internet → WAF → Load Balancer → Web Application
   - MITRE T1190: Exploit Public-Facing Application
   - Risk: High (direct internet exposure)

2. Web Application → API Server → Database
   - MITRE T1213: Data from Information Repositories
   - Risk: Critical (access to sensitive data)

Recommended controls:
- WAF with OWASP Top 10 rules
- Network segmentation between API and DB
- Database encryption at rest
"""

VERIFICATION_PROMPT = """
Review this threat analysis for completeness:

ARCHITECTURE:
{architecture}

ANALYSIS:
{analysis}

Check for:
1. Missing attack paths
2. Incorrect MITRE technique mappings
3. Overlooked vulnerabilities
4. Missing control recommendations

Provide a brief assessment (2-3 sentences) with completeness score (0-100%).
"""


class TestResult:
    """Test result tracking."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.passed = False
        self.error: Optional[str] = None
        self.duration: float = 0.0
        self.details: Dict = {}

    def __repr__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        error_msg = f" - {self.error}" if self.error else ""
        return f"{status} {self.test_name} ({self.duration:.2f}s){error_msg}"


class LLMProviderTester:
    """Test suite for LLM providers."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[TestResult] = []
        load_env()

    def run_all_tests(self, provider: Optional[str] = None):
        """Run all tests."""
        logger.info("=" * 60)
        logger.info("LLM Provider Test Suite")
        logger.info("=" * 60)

        if provider:
            providers = [LLMProvider(provider)]
        else:
            # Detect configured providers
            providers = self._detect_configured_providers()

        logger.info(f"Testing providers: {[p.value for p in providers]}")
        logger.info("")

        # Test 1: Provider configuration
        for prov in providers:
            self._test_provider_config(prov)

        # Test 2: Basic generation
        for prov in providers:
            self._test_basic_generation(prov)

        # Test 3: MITRE-specific prompt
        for prov in providers:
            self._test_mitre_prompt(prov)

        # Test 4: Cost tracking
        self._test_cost_tracking()

        # Test 5: Fallback mechanism
        if len(providers) > 1:
            self._test_fallback(providers)

        # Print summary
        self._print_summary()

    def test_verification_mode(self):
        """Test LLM as Judge verification."""
        logger.info("=" * 60)
        logger.info("LLM as Judge Verification Test")
        logger.info("=" * 60)

        result = TestResult("verification_mode")

        try:
            import time
            start = time.time()

            # Initialize client with verifier
            verifier_provider_str = os.getenv("LLM_VERIFIER_PROVIDER")
            if not verifier_provider_str:
                result.error = "LLM_VERIFIER_PROVIDER not configured"
                self.results.append(result)
                logger.error(f"❌ {result.error}")
                return

            verifier_provider = LLMProvider(verifier_provider_str)
            primary_provider_str = os.getenv("LLM_PROVIDER", "openrouter")
            primary_provider = LLMProvider(primary_provider_str)

            logger.info(f"Primary: {primary_provider.value}, Verifier: {verifier_provider.value}")

            client = LLMClient(
                primary_provider=primary_provider,
                verifier_provider=verifier_provider,
                enable_cost_tracking=True
            )

            # Generate analysis (with primary provider)
            logger.info("Generating analysis...")
            analysis_response = client.generate(
                prompt=f"Analyze this architecture:\n{TEST_ARCHITECTURE_MERMAID}",
                system_message="You are a threat modeling expert.",
                quality="fast",
                max_tokens=500
            )

            logger.info(f"Analysis generated ({len(analysis_response.content)} chars)")
            if self.verbose:
                logger.info(f"Content:\n{analysis_response.content[:200]}...")

            # Verify with verifier provider
            logger.info("Running verification...")
            verification_response = client.verify(
                analysis=TEST_ANALYSIS,
                architecture=TEST_ARCHITECTURE_MERMAID,
                verification_prompt=VERIFICATION_PROMPT,
                max_tokens=300
            )

            result.duration = time.time() - start
            result.passed = True
            result.details = {
                "analysis_provider": analysis_response.provider.value,
                "analysis_tokens": analysis_response.tokens_used,
                "analysis_cost": analysis_response.cost_usd,
                "verification_provider": verification_response.provider.value,
                "verification_tokens": verification_response.tokens_used,
                "verification_cost": verification_response.cost_usd,
                "total_cost": analysis_response.cost_usd + verification_response.cost_usd,
                "verification_content_length": len(verification_response.content)
            }

            logger.info(f"✅ Verification completed")
            logger.info(f"   Analysis: {result.details['analysis_provider']} "
                       f"({result.details['analysis_tokens']} tokens, "
                       f"${result.details['analysis_cost']:.4f})")
            logger.info(f"   Verification: {result.details['verification_provider']} "
                       f"({result.details['verification_tokens']} tokens, "
                       f"${result.details['verification_cost']:.4f})")
            logger.info(f"   Total cost: ${result.details['total_cost']:.4f}")

            if self.verbose:
                logger.info(f"\nVerification result:\n{verification_response.content}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ Verification test failed: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()

        self.results.append(result)

    def _detect_configured_providers(self) -> List[LLMProvider]:
        """Detect which providers are configured."""
        providers = []

        # Check OpenRouter
        if os.getenv("OPENROUTER_API_KEY"):
            providers.append(LLMProvider.OPENROUTER)

        # Check Bedrock
        if os.getenv("AWS_BEDROCK_API_KEY"):
            providers.append(LLMProvider.BEDROCK)

        # Check Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            providers.append(LLMProvider.ANTHROPIC)

        # Check Azure
        if os.getenv("AZURE_OPENAI_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
            providers.append(LLMProvider.AZURE)

        # Check Vertex AI
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            providers.append(LLMProvider.VERTEX)

        return providers

    def _test_provider_config(self, provider: LLMProvider):
        """Test provider configuration validation."""
        result = TestResult(f"config_{provider.value}")

        try:
            import time
            start = time.time()

            config = ProviderConfig.from_env(provider)
            is_valid = config.validate()

            result.duration = time.time() - start
            result.passed = is_valid
            result.details = {
                "provider": provider.value,
                "has_api_key": config.api_key is not None,
                "region": config.region,
                "endpoint": config.endpoint
            }

            if is_valid:
                logger.info(f"✅ {provider.value} configuration valid")
            else:
                result.error = "Configuration validation failed"
                logger.warning(f"⚠️  {provider.value} configuration invalid")

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ {provider.value} config test failed: {e}")

        self.results.append(result)

    def _test_basic_generation(self, provider: LLMProvider):
        """Test basic LLM generation."""
        result = TestResult(f"generate_{provider.value}")

        try:
            import time
            start = time.time()

            client = LLMClient(primary_provider=provider)
            response = client.generate(
                prompt=TEST_PROMPT_SIMPLE,
                max_tokens=50,
                temperature=0.0
            )

            result.duration = time.time() - start
            result.passed = len(response.content) > 0
            result.details = {
                "provider": response.provider.value,
                "model": response.model,
                "tokens": response.tokens_used,
                "cost": response.cost_usd,
                "latency": response.latency_seconds,
                "content_length": len(response.content)
            }

            logger.info(f"✅ {provider.value} generation successful")
            logger.info(f"   Tokens: {result.details['tokens']}, "
                       f"Cost: ${result.details['cost']:.4f}, "
                       f"Latency: {result.details['latency']:.2f}s")

            if self.verbose:
                logger.info(f"   Response: {response.content}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ {provider.value} generation failed: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()

        self.results.append(result)

    def _test_mitre_prompt(self, provider: LLMProvider):
        """Test MITRE-specific prompt."""
        result = TestResult(f"mitre_{provider.value}")

        try:
            import time
            start = time.time()

            client = LLMClient(primary_provider=provider)
            response = client.generate(
                prompt=TEST_PROMPT_MITRE,
                system_message="You are a cybersecurity expert specializing in MITRE ATT&CK.",
                max_tokens=200,
                temperature=0.3
            )

            result.duration = time.time() - start

            # Check if response mentions key terms
            content_lower = response.content.lower()
            has_t1190 = "t1190" in content_lower or "exploit" in content_lower
            has_context = "application" in content_lower or "public-facing" in content_lower

            result.passed = has_t1190 and has_context
            result.details = {
                "provider": response.provider.value,
                "tokens": response.tokens_used,
                "cost": response.cost_usd,
                "has_technique_reference": has_t1190,
                "has_context": has_context,
                "content_length": len(response.content)
            }

            if result.passed:
                logger.info(f"✅ {provider.value} MITRE prompt successful")
            else:
                result.error = "Response missing expected MITRE content"
                logger.warning(f"⚠️  {provider.value} MITRE response incomplete")

            if self.verbose:
                logger.info(f"   Response: {response.content}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ {provider.value} MITRE test failed: {e}")

        self.results.append(result)

    def _test_cost_tracking(self):
        """Test cost tracking functionality."""
        result = TestResult("cost_tracking")

        try:
            import time
            start = time.time()

            client = LLMClient(enable_cost_tracking=True)

            # Make several calls
            for i in range(3):
                client.generate(
                    prompt=f"Test message {i}",
                    max_tokens=20,
                    temperature=0.0
                )

            stats = client.get_usage_stats()

            result.duration = time.time() - start
            result.passed = (
                stats.total_requests == 3 and
                stats.total_tokens > 0
            )
            result.details = {
                "total_requests": stats.total_requests,
                "total_tokens": stats.total_tokens,
                "total_cost": stats.total_cost_usd,
                "provider_count": len(stats.provider_stats)
            }

            logger.info(f"✅ Cost tracking successful")
            logger.info(f"   Requests: {result.details['total_requests']}, "
                       f"Tokens: {result.details['total_tokens']}, "
                       f"Cost: ${result.details['total_cost']:.4f}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ Cost tracking test failed: {e}")

        self.results.append(result)

    def _test_fallback(self, providers: List[LLMProvider]):
        """Test fallback mechanism."""
        result = TestResult("fallback_mechanism")

        try:
            import time
            start = time.time()

            # Use first provider as primary, rest as fallbacks
            client = LLMClient(
                primary_provider=providers[0],
                fallback_providers=providers[1:]
            )

            # This should succeed even if primary fails
            response = client.generate(
                prompt="Hello",
                max_tokens=10,
                temperature=0.0
            )

            result.duration = time.time() - start
            result.passed = len(response.content) > 0
            result.details = {
                "primary": providers[0].value,
                "fallbacks": [p.value for p in providers[1:]],
                "provider_used": response.provider.value
            }

            logger.info(f"✅ Fallback mechanism working")
            logger.info(f"   Provider used: {result.details['provider_used']}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ Fallback test failed: {e}")

        self.results.append(result)

    def _print_summary(self):
        """Print test summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("Test Summary")
        logger.info("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        for result in self.results:
            logger.info(str(result))

        logger.info("")
        logger.info(f"Total: {len(self.results)} tests")
        logger.info(f"Passed: {passed} ✅")
        logger.info(f"Failed: {failed} ❌")

        if failed == 0:
            logger.info("")
            logger.info("🎉 All tests passed!")

        # Export results to JSON
        self._export_results()

    def _export_results(self):
        """Export test results to JSON."""
        output = {
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "results": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "duration": r.duration,
                    "error": r.error,
                    "details": r.details
                }
                for r in self.results
            ]
        }

        output_file = "test_results_llm_providers.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"\nResults exported to: {output_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test multi-provider LLM functionality"
    )
    parser.add_argument(
        "--provider",
        choices=["openrouter", "bedrock", "anthropic", "azure", "vertex"],
        help="Test specific provider only"
    )
    parser.add_argument(
        "--test-verify",
        action="store_true",
        help="Test LLM as Judge verification mode"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    tester = LLMProviderTester(verbose=args.verbose)

    if args.test_verify:
        tester.test_verification_mode()
    else:
        tester.run_all_tests(provider=args.provider)

    # Exit with error code if any tests failed
    failed = sum(1 for r in tester.results if not r.passed)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
