"""
Test tool calling with Bedrock and OpenRouter

Tests that LLM can call functions/tools before implementing Tester agent.
"""

import json
import logging
from agentic.llm_client import LLMClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_add(a: int, b: int) -> int:
    """Simple test function: add two numbers."""
    return a + b


def test_tool_calling_with_provider(provider: str, model: str = None):
    """
    Test tool calling with specific provider.

    Args:
        provider: "bedrock" or "openrouter"
        model: Optional model override

    Returns:
        Dict with test results
    """
    print(f"\n{'='*70}")
    print(f"Testing Tool Calling: {provider.upper()}")
    print(f"{'='*70}\n")

    # Define tool schema
    tool_schema = {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers together and return the sum",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "First number"
                    },
                    "b": {
                        "type": "integer",
                        "description": "Second number"
                    }
                },
                "required": ["a", "b"]
            }
        }
    }

    # Initialize client
    client = LLMClient()

    # Prepare request
    system_message = "You are a helpful assistant. Use the add_numbers tool when asked to add numbers."
    prompt = "What is 15 plus 27? Please use the add_numbers tool to calculate this."

    print(f"Provider: {provider}")
    print(f"Model: {model or 'default'}")
    print(f"Prompt: {prompt}")
    print(f"\nCalling LLM...\n")

    try:
        # Call LLM with tool
        response = client.generate(
            prompt=prompt,
            system_message=system_message,
            model=model,
            tools=[tool_schema],
            temperature=0.0
        )

        # Check response type
        print(f"Response type: {type(response)}")
        print(f"Has tool_calls: {hasattr(response, 'tool_calls')}")

        # Check if LLM called tool
        if hasattr(response, 'tool_calls') and response.tool_calls:
            print(f"\n✅ SUCCESS: LLM called tool!")

            tool_call = response.tool_calls[0]
            print(f"\nTool Call Details:")
            print(f"  Function: {tool_call.function.name}")
            print(f"  Arguments: {tool_call.function.arguments}")

            # Parse and execute
            args = json.loads(tool_call.function.arguments)
            result = test_add(args['a'], args['b'])

            print(f"\nExecution:")
            print(f"  add_numbers({args['a']}, {args['b']}) = {result}")

            return {
                "success": True,
                "provider": provider,
                "model": model or "default",
                "tool_called": tool_call.function.name,
                "arguments": args,
                "result": result,
                "supports_tool_calling": True
            }

        elif hasattr(response, 'content'):
            print(f"\n⚠️  LLM did NOT call tool - responded with text instead:")
            print(f"\n{response.content}\n")

            return {
                "success": False,
                "provider": provider,
                "model": model or "default",
                "error": "LLM did not use tool - answered directly",
                "response": response.content,
                "supports_tool_calling": False
            }

        else:
            print(f"\n❌ FAILED: Unknown response format")
            print(f"Response: {response}")

            return {
                "success": False,
                "provider": provider,
                "model": model or "default",
                "error": "Unknown response format",
                "supports_tool_calling": False
            }

    except Exception as e:
        print(f"\n❌ FAILED: Exception occurred")
        print(f"Error: {str(e)}\n")

        import traceback
        traceback.print_exc()

        return {
            "success": False,
            "provider": provider,
            "model": model or "default",
            "error": str(e),
            "supports_tool_calling": False
        }


if __name__ == "__main__":
    print("\n" + "="*70)
    print("TOOL CALLING TEST SUITE")
    print("="*70)

    results = {}

    # Test 1: Bedrock (should work - Claude supports tools)
    print("\n[TEST 1] Bedrock with Claude Sonnet")
    results["bedrock"] = test_tool_calling_with_provider(
        provider="bedrock",
        model="bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    )

    # Test 2: OpenRouter (may not work with free tier)
    print("\n[TEST 2] OpenRouter with Nemotron")
    results["openrouter"] = test_tool_calling_with_provider(
        provider="openrouter",
        model="openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    )

    # Summary
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70 + "\n")

    for provider, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        supports = "Yes" if result.get("supports_tool_calling") else "No"

        print(f"{provider.upper()}: {status}")
        print(f"  Supports tool calling: {supports}")

        if result["success"]:
            print(f"  Tool called: {result['tool_called']}")
            print(f"  Result: {result['arguments']['a']} + {result['arguments']['b']} = {result['result']}")
        else:
            print(f"  Error: {result.get('error', 'Unknown')}")

        print()

    # Recommendation
    print("="*70)
    print("RECOMMENDATION")
    print("="*70 + "\n")

    if results["bedrock"]["success"]:
        print("✅ Use Bedrock for Phase 3C agents (tool calling works)")
        print("   Model: bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    elif results["openrouter"]["success"]:
        print("✅ Use OpenRouter for Phase 3C agents (tool calling works)")
        print("   Model: openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
    else:
        print("❌ Neither provider supports tool calling")
        print("   Need to rethink approach or find alternative provider")

    print()
