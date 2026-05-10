#!/usr/bin/env python3
"""
Quick validation script for LLM provider configuration.

Tests current .env setup for multi-provider architecture.
Validates environment-driven configuration model.

Usage:
    python3 scripts/validate_llm_config.py
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agentic.helper import load_env

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_env_vars():
    """Check required environment variables."""
    logger.info("=" * 60)
    logger.info("Checking Environment Configuration")
    logger.info("=" * 60)

    load_env()

    results = {}

    # Check Primary Provider
    llm_provider = os.getenv("LLM_PROVIDER", "openrouter")
    logger.info(f"ℹ️  LLM_PROVIDER (primary): {llm_provider}")

    # Check Fallback Providers
    fallback_providers = os.getenv("LLM_FALLBACK_PROVIDERS", "")
    if fallback_providers:
        logger.info(f"ℹ️  LLM_FALLBACK_PROVIDERS: {fallback_providers}")
    else:
        logger.info("ℹ️  LLM_FALLBACK_PROVIDERS: Not configured")

    # Check Verifier Provider
    llm_verifier = os.getenv("LLM_VERIFIER_PROVIDER")
    if llm_verifier:
        logger.info(f"ℹ️  LLM_VERIFIER_PROVIDER: {llm_verifier}")
    else:
        logger.info("ℹ️  LLM_VERIFIER_PROVIDER: Not configured (optional)")

    logger.info("")
    logger.info("Checking Provider Credentials:")
    logger.info("-" * 60)

    # Check OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_models = os.getenv("OPENROUTER_ACTIVE_MODELS")
    if openrouter_key:
        logger.info("✅ OPENROUTER_API_KEY: Configured")
        if openrouter_models:
            logger.info(f"   OPENROUTER_ACTIVE_MODELS: {openrouter_models}")
        else:
            logger.info("   OPENROUTER_ACTIVE_MODELS: Using default (nemotron)")
        results["openrouter"] = True
    else:
        logger.warning("❌ OPENROUTER_API_KEY: Not found")
        results["openrouter"] = False

    # Check Bedrock API Key
    bedrock_key = os.getenv("AWS_BEDROCK_API_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model = os.getenv("BEDROCK_MODEL")

    if bedrock_key:
        logger.info("✅ AWS_BEDROCK_API_KEY: Configured")
        logger.info(f"   AWS_REGION: {aws_region}")
        if bedrock_model:
            logger.info(f"   BEDROCK_MODEL: {bedrock_model}")
        results["bedrock"] = True
    else:
        logger.warning("❌ AWS_BEDROCK_API_KEY: Not found")
        results["bedrock"] = False

    # Check Anthropic (optional)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        logger.info("✅ ANTHROPIC_API_KEY: Configured (optional)")
        results["anthropic"] = True
    else:
        logger.info("ℹ️  ANTHROPIC_API_KEY: Not configured (optional)")
        results["anthropic"] = False

    # Check Azure (optional)
    azure_key = os.getenv("AZURE_OPENAI_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_endpoint:
        logger.info("✅ AZURE_OPENAI: Configured (optional)")
        results["azure"] = True
    else:
        logger.info("ℹ️  AZURE_OPENAI: Not configured (optional)")
        results["azure"] = False

    # Check Vertex (optional)
    vertex_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if vertex_creds:
        logger.info("✅ VERTEX_AI: Configured (optional)")
        results["vertex"] = True
    else:
        logger.info("ℹ️  VERTEX_AI: Not configured (optional)")
        results["vertex"] = False

    logger.info("")
    return results


def test_openrouter():
    """Test OpenRouter connection."""
    logger.info("=" * 60)
    logger.info("Testing OpenRouter Connection")
    logger.info("=" * 60)

    try:
        from agentic.llm_client import LLMClient, LLMProvider

        logger.info("Sending test prompt to OpenRouter...")

        client = LLMClient(primary_provider=LLMProvider.OPENROUTER)
        response = client.generate(
            prompt="Say 'Hello from OpenRouter!' and nothing else.",
            system_message="You are a helpful assistant.",
            max_tokens=50,
            temperature=0.0
        )

        logger.info("✅ OpenRouter connection successful!")
        logger.info(f"Response: {response.content}")
        logger.info(f"Provider used: {response.provider.value}")
        logger.info(f"Model: {response.model}")
        return True

    except Exception as e:
        logger.error(f"❌ OpenRouter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bedrock_credentials():
    """Test Bedrock API key format."""
    logger.info("=" * 60)
    logger.info("Testing Bedrock API Key Format")
    logger.info("=" * 60)

    bedrock_key = os.getenv("AWS_BEDROCK_API_KEY")

    if not bedrock_key:
        logger.warning("⚠️  AWS_BEDROCK_API_KEY not configured")
        logger.info("   To configure:")
        logger.info("   1. AWS Console → Amazon Bedrock → API Keys")
        logger.info("   2. Create API Key → Copy key")
        logger.info("   3. Add to .env: AWS_BEDROCK_API_KEY=AKabcdef123...")
        return False

    # Basic format validation
    if len(bedrock_key) < 20:
        logger.warning("⚠️  AWS_BEDROCK_API_KEY seems too short")
        return False

    # Check if it's a valid bearer token format
    if bedrock_key.startswith("ABSK") or bedrock_key.startswith("AK"):
        logger.info("✅ AWS_BEDROCK_API_KEY format looks valid")
        logger.info(f"   Key prefix: {bedrock_key[:6]}...")
        logger.info(f"   Key length: {len(bedrock_key)} characters")
        return True
    else:
        logger.warning("⚠️  AWS_BEDROCK_API_KEY format unexpected")
        logger.info("   Expected format: AKabcdef123... or ABSKxyz...")
        return False


def test_litellm_installed():
    """Check if LiteLLM is installed."""
    logger.info("=" * 60)
    logger.info("Checking Dependencies")
    logger.info("=" * 60)

    try:
        import litellm
        version = getattr(litellm, '__version__', 'unknown')
        logger.info(f"✅ LiteLLM installed: v{version}")
        installed_litellm = True
    except ImportError:
        logger.warning("❌ LiteLLM not installed")
        logger.info("   Install: pip install litellm")
        installed_litellm = False

    try:
        import boto3
        version = boto3.__version__
        logger.info(f"✅ boto3 installed: v{version}")
        installed_boto3 = True
    except ImportError:
        logger.warning("❌ boto3 not installed (required for Bedrock)")
        logger.info("   Install: pip install boto3")
        installed_boto3 = False
    except AttributeError:
        logger.info("✅ boto3 installed: version check unavailable")
        installed_boto3 = True

    logger.info("")
    return installed_litellm and installed_boto3


def print_summary(results):
    """Print test summary."""
    logger.info("=" * 60)
    logger.info("Configuration Summary")
    logger.info("=" * 60)

    # Dependencies
    if results.get("dependencies", False):
        logger.info("✅ Dependencies: All required packages installed")
    else:
        logger.warning("⚠️  Dependencies: Missing packages (install with pip)")

    # Configured providers
    configured_providers = []
    if results.get("openrouter", False):
        configured_providers.append("openrouter")
        logger.info("✅ OpenRouter: Configured")
    if results.get("bedrock_format", False):
        configured_providers.append("bedrock")
        logger.info("✅ Bedrock: Configured")
    if results.get("anthropic", False):
        configured_providers.append("anthropic")
        logger.info("✅ Anthropic: Configured (optional)")
    if results.get("azure", False):
        configured_providers.append("azure")
        logger.info("✅ Azure: Configured (optional)")
    if results.get("vertex", False):
        configured_providers.append("vertex")
        logger.info("✅ Vertex AI: Configured (optional)")

    if not configured_providers:
        logger.warning("⚠️  No providers configured!")
    else:
        logger.info(f"\nConfigured providers: {', '.join(configured_providers)}")

    # Working status
    if results.get("openrouter_working", False):
        logger.info("✅ OpenRouter: Tested and working")

    logger.info("")

    # Overall status
    has_primary = results.get("openrouter", False) or results.get("bedrock_format", False)
    all_pass = results.get("dependencies", False) and has_primary

    if all_pass:
        logger.info("🎉 Configuration valid! Multi-provider system ready.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Run full tests: python3 scripts/test_llm_providers.py")
        logger.info("2. Test specific provider: python3 scripts/test_llm_providers.py --provider bedrock")
        logger.info("3. Test LLM as Judge: python3 scripts/test_llm_providers.py --test-verify")
        logger.info("")
        logger.info("Configuration tips:")
        logger.info("- Change primary: Set LLM_PROVIDER in .env")
        logger.info("- Add fallback: Set LLM_FALLBACK_PROVIDERS=bedrock,anthropic")
        logger.info("- Custom models: Set OPENROUTER_ACTIVE_MODELS=model1,model2")
    else:
        logger.warning("⚠️  Configuration incomplete. Please fix issues above.")
        logger.info("")
        logger.info("Common fixes:")
        logger.info("- Install dependencies: pip install litellm boto3")
        logger.info("- Add API keys to .env file")
        logger.info("- Configure at least one provider (OpenRouter or Bedrock)")
        logger.info("- Verify API key format (AWS Bedrock should start with 'AK' or 'ABSK')")

    logger.info("")


def main():
    """Main entry point."""
    logger.info("")
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║       LLM Provider Configuration Validator                 ║")
    logger.info("║       (Environment-Driven Multi-Provider System)           ║")
    logger.info("╚════════════════════════════════════════════════════════════╝")
    logger.info("")

    results = {}

    # Test 1: Check environment variables
    env_results = check_env_vars()
    results.update(env_results)

    # Test 2: Check dependencies
    results["dependencies"] = test_litellm_installed()

    # Test 3: Test OpenRouter (only if configured)
    if results.get("openrouter", False) and results.get("dependencies", False):
        openrouter_works = test_openrouter()
        results["openrouter_working"] = openrouter_works

    # Test 4: Test Bedrock API key format
    results["bedrock_format"] = test_bedrock_credentials()

    # Print summary
    print_summary(results)

    # Exit with error code if any critical checks failed
    has_provider = results.get("openrouter", False) or results.get("bedrock_format", False)
    critical_pass = results.get("dependencies", False) and has_provider
    sys.exit(0 if critical_pass else 1)


if __name__ == "__main__":
    main()
