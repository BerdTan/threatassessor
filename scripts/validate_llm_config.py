#!/usr/bin/env python3
"""
Quick validation script for LLM provider configuration.

Tests current .env setup before implementing multi-provider architecture.
Uses existing agentic/llm.py module.

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

    # Check OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        logger.info("✅ OPENROUTER_API_KEY: Configured")
        results["openrouter"] = True
    else:
        logger.warning("❌ OPENROUTER_API_KEY: Not found")
        results["openrouter"] = False

    # Check Bedrock API Key
    bedrock_key = os.getenv("AWS_BEDROCK_API_KEY")
    aws_region = os.getenv("AWS_REGION")

    if bedrock_key and aws_region:
        logger.info("✅ AWS_BEDROCK_API_KEY: Configured")
        logger.info(f"✅ AWS_REGION: {aws_region}")
        results["bedrock"] = True
    else:
        if not bedrock_key:
            logger.warning("❌ AWS_BEDROCK_API_KEY: Not found")
        if not aws_region:
            logger.warning("❌ AWS_REGION: Not found")
        results["bedrock"] = False

    # Check LLM Provider setting
    llm_provider = os.getenv("LLM_PROVIDER", "openrouter")
    logger.info(f"ℹ️  LLM_PROVIDER: {llm_provider}")

    # Check LLM Verifier setting
    llm_verifier = os.getenv("LLM_VERIFIER_PROVIDER")
    if llm_verifier:
        logger.info(f"ℹ️  LLM_VERIFIER_PROVIDER: {llm_verifier}")
    else:
        logger.info("ℹ️  LLM_VERIFIER_PROVIDER: Not configured (optional)")

    logger.info("")
    return results


def test_openrouter():
    """Test OpenRouter connection."""
    logger.info("=" * 60)
    logger.info("Testing OpenRouter Connection")
    logger.info("=" * 60)

    try:
        from agentic.llm import generate_response_with_system

        logger.info("Sending test prompt to OpenRouter...")

        response = generate_response_with_system(
            prompt="Say 'Hello from OpenRouter!' and nothing else.",
            system_message="You are a helpful assistant.",
            model="openrouter/google/gemma-4-26b-a4b-it:free",
            max_tokens=50,
            temperature=0.0
        )

        logger.info("✅ OpenRouter connection successful!")
        logger.info(f"Response: {response}")
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

    if results.get("dependencies", False):
        logger.info("✅ Dependencies: All required packages installed")
    else:
        logger.warning("⚠️  Dependencies: Missing packages (install with pip)")

    if results.get("openrouter", False):
        logger.info("✅ OpenRouter: Configured and working")
    else:
        logger.warning("⚠️  OpenRouter: Not configured or failed")

    if results.get("bedrock_format", False):
        logger.info("✅ Bedrock: API key format valid")
    else:
        logger.warning("⚠️  Bedrock: API key not configured or invalid format")

    logger.info("")

    all_pass = all([
        results.get("dependencies", False),
        results.get("openrouter", False),
        results.get("bedrock_format", False)
    ])

    if all_pass:
        logger.info("🎉 All checks passed! Ready for multi-provider implementation.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Implement agentic/llm_client.py (multi-provider client)")
        logger.info("2. Run: python3 scripts/test_llm_providers.py")
        logger.info("3. Test LLM as Judge: python3 scripts/test_llm_providers.py --test-verify")
    else:
        logger.warning("⚠️  Some checks failed. Please fix configuration issues above.")
        logger.info("")
        logger.info("Common fixes:")
        logger.info("- Install dependencies: pip install litellm boto3")
        logger.info("- Add API keys to .env file")
        logger.info("- Verify API key format (AWS Bedrock should start with 'AK' or 'ABSK')")

    logger.info("")


def main():
    """Main entry point."""
    logger.info("")
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║       LLM Provider Configuration Validator                 ║")
    logger.info("║       (Pre-implementation validation)                      ║")
    logger.info("╚════════════════════════════════════════════════════════════╝")
    logger.info("")

    results = {}

    # Test 1: Check environment variables
    env_results = check_env_vars()
    results.update(env_results)

    # Test 2: Check dependencies
    results["dependencies"] = test_litellm_installed()

    # Test 3: Test OpenRouter (only if configured)
    if results.get("openrouter", False):
        openrouter_works = test_openrouter()
        results["openrouter_working"] = openrouter_works

    # Test 4: Test Bedrock API key format
    results["bedrock_format"] = test_bedrock_credentials()

    # Print summary
    print_summary(results)

    # Exit with error code if any critical checks failed
    critical_pass = results.get("dependencies", False) and results.get("openrouter", False)
    sys.exit(0 if critical_pass else 1)


if __name__ == "__main__":
    main()
