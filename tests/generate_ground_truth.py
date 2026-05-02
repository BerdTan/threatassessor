#!/usr/bin/env python3
"""
Semi-Automated Ground Truth Generator

Uses LLM + parser to generate initial ground truth labels, then prompts
human for validation/correction. Reduces manual effort from 30min → 10min per architecture.

Process:
1. Parse .mmd file with existing parser
2. Use LLM to generate initial labels (controls, attack paths, MITRE techniques)
3. Display to human for review
4. Human validates/corrects
5. Save validated JSON

Usage:
    python3 tests/generate_ground_truth.py tests/data/architectures/06_azure_3tier.mmd
"""

import sys
import json
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from chatbot.parsers.mermaid_parser import parse_mermaid_file
from tests.data.architectures.control_detection import detect_controls_in_architecture
from agentic.llm import LLMClient


GROUND_TRUTH_TEMPLATE = """
You are a security architecture expert. Analyze this Mermaid architecture diagram and generate ground truth labels for validation testing.

**Architecture Diagram:**
```mermaid
{mermaid_content}
```

**Parsed Structure:**
- Nodes: {node_count}
- Edges: {edge_count}
- Subgraphs: {subgraph_count}

**Automatically Detected Controls:**
{detected_controls}

**Task:** Generate ground truth JSON with:

1. **controls_present**: List of security controls visible in diagram (review auto-detected list)
2. **controls_missing**: List of critical missing controls for this architecture type
3. **expected_attack_paths**: 3-5 realistic attack paths with:
   - entry: Entry point node ID
   - target: Target node ID (database, sensitive data)
   - path: List of node IDs from entry to target
   - techniques: List of MITRE ATT&CK technique IDs
   - rationale: Why this path is exploitable

4. **expected_risk_score**: Overall risk (0-100, higher = worse)
5. **expected_defensibility**: How well-defended (0-100, higher = better)
6. **rapids_assessment**: Risk scores for 6 categories:
   - ransomware: {{"risk": 0-100, "defensibility": 0-100, "rationale": "..."}}
   - application_vulns: {{...}}
   - phishing: {{...}}
   - insider_threat: {{...}}
   - dos: {{...}}
   - supply_chain: {{...}}

7. **rationale**: 2-3 sentence summary of architecture's security posture

**Output format:** Valid JSON matching schema. Use node IDs exactly as they appear in parsed structure.

**Scoring Guidelines:**
- Flat network, no controls = risk 90-100, defensibility 5-10
- Some controls, segmentation = risk 40-60, defensibility 40-60
- Defense-in-depth, multiple layers = risk 20-40, defensibility 70-90
"""


def generate_initial_labels(mmd_file: str, use_llm: bool = True) -> dict:
    """
    Generate initial ground truth labels using parser + LLM.

    Args:
        mmd_file: Path to .mmd architecture file
        use_llm: Whether to use LLM for generation (vs just parser)

    Returns:
        dict: Initial ground truth structure
    """
    # Parse architecture
    with open(mmd_file, 'r') as f:
        mermaid_content = f.read()

    parsed = parse_mermaid_file(mmd_file)

    # Convert to list format for control detection
    nodes = [
        {"id": node_id, "label": node_data.get("label", node_id)}
        for node_id, node_data in parsed["nodes"].items()
    ]
    edges = [
        {"source": edge["source"], "target": edge["target"], "label": edge.get("label") or ""}
        for edge in parsed["edges"]
    ]
    subgraphs = [
        {"id": sg_id, "label": sg_data.get("label", sg_id)}
        for sg_id, sg_data in parsed.get("subgraphs", {}).items()
    ]

    # Auto-detect controls
    control_result = detect_controls_in_architecture(nodes, edges, subgraphs)
    detected_controls = control_result["controls_present"]

    print(f"\n📊 Parsed Architecture:")
    print(f"   Nodes: {len(nodes)}")
    print(f"   Edges: {len(edges)}")
    print(f"   Subgraphs: {len(subgraphs)}")
    print(f"   Auto-detected controls: {detected_controls}\n")

    if not use_llm:
        # Return minimal structure without LLM
        return {
            "architecture": Path(mmd_file).name,
            "description": "",
            "controls_present": detected_controls,
            "controls_missing": [],
            "expected_attack_paths": [],
            "expected_risk_score": 50,
            "expected_defensibility": 50,
            "rapids_assessment": {},
            "rationale": "",
        }

    # Use LLM to generate comprehensive labels
    prompt = GROUND_TRUTH_TEMPLATE.format(
        mermaid_content=mermaid_content,
        node_count=len(nodes),
        edge_count=len(edges),
        subgraph_count=len(subgraphs),
        detected_controls=json.dumps(detected_controls, indent=2),
    )

    print("🤖 Generating initial labels with LLM...")
    print("   (This may take 30-60 seconds)\n")

    try:
        client = LLMClient()
        response = client.chat([{"role": "user", "content": prompt}])

        # Extract JSON from response (may be wrapped in ```json blocks)
        response_text = response.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        generated = json.loads(response_text)

        # Ensure architecture field matches filename
        generated["architecture"] = Path(mmd_file).name

        return generated

    except Exception as e:
        print(f"⚠️  LLM generation failed: {e}")
        print("   Falling back to manual entry...\n")
        return generate_initial_labels(mmd_file, use_llm=False)


def display_for_review(labels: dict):
    """Display generated labels for human review."""
    print("="*80)
    print("GENERATED GROUND TRUTH - REVIEW & VALIDATE")
    print("="*80)
    print(json.dumps(labels, indent=2))
    print("="*80)


def interactive_validation(labels: dict) -> dict:
    """
    Interactively validate/correct generated labels.

    Returns:
        dict: Validated ground truth
    """
    print("\n📝 Review the generated labels above.\n")
    print("Options:")
    print("  [a] Accept as-is")
    print("  [e] Edit JSON manually")
    print("  [c] Correct specific fields")
    print("  [q] Quit without saving")

    choice = input("\nYour choice: ").strip().lower()

    if choice == 'a':
        return labels

    elif choice == 'e':
        print("\nOpening JSON for manual editing...")
        # Save to temp file and open in editor
        import tempfile
        import subprocess

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(labels, f, indent=2)
            temp_path = f.name

        # Open in editor (use EDITOR env var or default to nano)
        editor = subprocess.os.environ.get('EDITOR', 'nano')
        subprocess.call([editor, temp_path])

        # Load edited version
        with open(temp_path, 'r') as f:
            labels = json.load(f)

        subprocess.os.unlink(temp_path)
        return labels

    elif choice == 'c':
        print("\nCorrect fields:")
        print("  1. controls_present")
        print("  2. controls_missing")
        print("  3. expected_risk_score")
        print("  4. expected_defensibility")
        print("  5. Done")

        field_choice = input("Field to correct (1-5): ").strip()

        if field_choice == '1':
            print(f"\nCurrent: {labels['controls_present']}")
            new_value = input("New value (JSON list): ").strip()
            labels['controls_present'] = json.loads(new_value)

        elif field_choice == '2':
            print(f"\nCurrent: {labels['controls_missing']}")
            new_value = input("New value (JSON list): ").strip()
            labels['controls_missing'] = json.loads(new_value)

        elif field_choice == '3':
            current = labels['expected_risk_score']
            new_value = input(f"Risk score (0-100, current: {current}): ").strip()
            labels['expected_risk_score'] = int(new_value)

        elif field_choice == '4':
            current = labels['expected_defensibility']
            new_value = input(f"Defensibility (0-100, current: {current}): ").strip()
            labels['expected_defensibility'] = int(new_value)

        elif field_choice == '5':
            return labels

        # Recurse for more corrections
        return interactive_validation(labels)

    elif choice == 'q':
        print("❌ Aborted without saving")
        sys.exit(0)

    else:
        print("Invalid choice, try again")
        return interactive_validation(labels)


def main():
    parser = argparse.ArgumentParser(
        description="Generate ground truth labels for architecture diagrams"
    )
    parser.add_argument(
        "mmd_file",
        type=str,
        help="Path to .mmd architecture file"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM generation, use parser only"
    )
    parser.add_argument(
        "--auto-accept",
        action="store_true",
        help="Skip validation, accept LLM output as-is"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path (default: tests/data/ground_truth/<name>.json)"
    )

    args = parser.parse_args()

    # Validate input file exists
    if not Path(args.mmd_file).exists():
        print(f"❌ File not found: {args.mmd_file}")
        sys.exit(1)

    # Generate initial labels
    labels = generate_initial_labels(args.mmd_file, use_llm=not args.no_llm)

    # Display for review
    display_for_review(labels)

    # Validate (unless auto-accept)
    if not args.auto_accept:
        labels = interactive_validation(labels)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        mmd_name = Path(args.mmd_file).stem
        output_path = Path("tests/data/ground_truth") / f"{mmd_name}.json"

    # Save validated ground truth
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(labels, f, indent=2)

    print(f"\n✅ Ground truth saved to: {output_path}")

    # Run validation to verify
    print(f"\n🧪 Running validation test...\n")
    import subprocess
    result = subprocess.run(
        ["python3", "tests/validate_parser_harness.py"],
        env={**subprocess.os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("✅ Validation passed!")
    else:
        print("⚠️  Validation issues detected:")
        print(result.stdout)


if __name__ == "__main__":
    main()
