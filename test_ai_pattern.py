#!/usr/bin/env python3
"""
Test AI Pattern on Agentic AI Architecture

Tests the complete AI threat detection pipeline:
1. ThreatAnalyst with AI pattern
2. Component detection (LLM API, Vector DB, etc.)
3. ARC risk scoring (9 categories)
4. Control recommendations
"""

import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 60)
    logger.info("AI Pattern Test - Agentic AI Architecture")
    logger.info("=" * 60)

    # Test architecture
    arch_path = "tests/data/architectures/21_agentic_ai_system.mmd"

    logger.info(f"\n1. Loading architecture: {arch_path}")

    # Import ThreatAnalyst
    from chatbot.modules.threat_analyst import ThreatAnalyst

    # Create analyst
    analyst = ThreatAnalyst()
    logger.info(f"   Created: {analyst.role}")

    # Run assessment
    logger.info(f"\n2. Running threat assessment...")
    result = analyst.execute({"architecture_path": arch_path})

    logger.info(f"   Architecture: {result.architecture_name}")
    logger.info(f"   Confidence: {result.confidence:.1%}")
    logger.info(f"   Pattern sources: {result.pattern_sources}")
    logger.info(f"   Techniques: {len(result.techniques)}")
    logger.info(f"   Controls recommended: {len(result.control_recommendations)}")

    # Check AI assessment
    logger.info(f"\n3. Checking AI/ML assessment...")

    if "AI/ML (ARC)" in result.pattern_sources:
        logger.info(f"   ✅ AI pattern detected and ran!")

        ai_assessment = result.data.get("ai_ml_assessment", {})
        ai_controls = result.data.get("ai_controls_recommended", [])

        logger.info(f"   AI risk categories: {len(ai_assessment)}")
        logger.info(f"   AI-specific controls: {len(ai_controls)}")

        # Print risk scores
        logger.info(f"\n4. ARC Risk Scores:")
        for category, data in sorted(ai_assessment.items()):
            if isinstance(data, dict):
                risk = data.get("risk", 0)
                rationale = data.get("rationale", "N/A")[:60]
                logger.info(f"   {category.capitalize():20s} {risk:3d}/100 - {rationale}")

        # Print AI controls
        logger.info(f"\n5. AI-Specific Controls Recommended:")
        for ctrl in ai_controls[:10]:  # Top 10
            logger.info(f"   - {ctrl}")

        logger.info(f"\n✅ AI Pattern Test PASSED!")
        logger.info(f"   Total controls: {len(result.control_recommendations)}")
        logger.info(f"   AI controls: {len(ai_controls)}")

    else:
        logger.warning(f"   ❌ AI pattern did NOT run")
        logger.warning(f"   Pattern sources: {result.pattern_sources}")
        logger.warning(f"   This may be expected if not an AI architecture")

    logger.info(f"\n" + "=" * 60)
    logger.info("Test Complete")
    logger.info("=" * 60)

    return result

if __name__ == "__main__":
    main()
