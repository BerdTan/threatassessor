"""
agent.py - Persona/task manager for routing user input to appropriate modules

This module integrates:
- Semantic search (mitre_embeddings) for technique matching
- LLM-enhanced analysis (llm_mitre_analyzer) for refinement and attack paths
- Hybrid mitigation extraction (MITRE data + LLM prioritization)
- Scoring rubric (accuracy, relevance, confidence)
- Keyword-based fallback (mitre_template) for API failures
"""
import logging
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_template import build_threat_prompt
from chatbot.modules.mitre_embeddings import search_techniques
from chatbot.modules.llm_mitre_analyzer import analyze_scenario
from chatbot.modules.scoring import score_technique, score_mitigation

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(self, use_semantic_search: bool = True):
        """
        Initialize AgentManager with MITRE data.

        Args:
            use_semantic_search: If True, use LLM-enhanced semantic search.
                                 If False, fallback to keyword-based search.
        """
        self.mitre = MitreHelper(use_local=True)
        self.use_semantic_search = use_semantic_search
        logger.info(f"AgentManager initialized (semantic_search={use_semantic_search})")

    def handle_input(self, user_input: str, top_k: int = 5) -> dict:
        """
        Process user input and return threat assessment.

        Args:
            user_input: User's threat scenario description
            top_k: Number of top techniques to return

        Returns:
            Dict with analysis results:
            {
                "query": "Original user input",
                "mode": "semantic" or "keyword",
                "techniques": [...],           # Matched techniques with scores
                "refined_techniques": [...],   # LLM-refined (if semantic mode)
                "attack_path": {...},          # Attack chain analysis (if semantic mode)
                "mitigations": {...},          # Mitigation advice (if semantic mode)
                "prompt": "...",               # Legacy keyword prompt (if keyword mode)
                "details": [...]               # Legacy details (if keyword mode)
            }
        """
        logger.info(f"Processing input: '{user_input[:50]}...' (mode={'semantic' if self.use_semantic_search else 'keyword'})")

        if self.use_semantic_search:
            try:
                return self._semantic_threat_assessment(user_input, top_k)
            except Exception as e:
                logger.error(f"Semantic search failed: {str(e)}")
                logger.warning("Falling back to keyword-based search")
                return self._keyword_threat_assessment(user_input)
        else:
            return self._keyword_threat_assessment(user_input)

    def _semantic_threat_assessment(self, user_input: str, top_k: int = 5) -> dict:
        """
        Use semantic search + LLM analysis for threat assessment.

        Args:
            user_input: User's threat scenario
            top_k: Number of techniques to analyze

        Returns:
            Dict with semantic search results and LLM analysis
        """
        logger.info("Starting semantic threat assessment...")

        # Step 1: Semantic search for techniques
        logger.info("Step 1: Semantic search for matching techniques...")
        matched_techniques = search_techniques(
            query=user_input,
            mitre=self.mitre,
            top_k=top_k * 2,  # Get more for LLM to refine
            min_score=0.3     # Lower threshold, let LLM filter
        )

        if not matched_techniques:
            logger.warning("No techniques matched via semantic search")
            return {
                "query": user_input,
                "mode": "semantic",
                "techniques": [],
                "refined_techniques": [],
                "attack_path": {},
                "mitigations": {},
                "error": "No relevant techniques found"
            }

        logger.info(f"Found {len(matched_techniques)} techniques via semantic search")

        # Step 1.5: Extract MITRE mitigations from relationships (NEW)
        logger.info("Step 1.5: Extracting official MITRE mitigations...")
        technique_ids = [t['external_id'] for t in matched_techniques[:top_k]]
        mitre_mitigations = self.mitre.get_mitigations_for_techniques(technique_ids)
        logger.info(f"Found {len(mitre_mitigations)} unique MITRE mitigations (deduplicated)")

        # Attach mitigations to techniques for scoring
        for tech in matched_techniques:
            tech['mitigations'] = self.mitre.get_technique_mitigations(tech['external_id'])

        # Step 2: LLM-enhanced analysis (with MITRE mitigations as context)
        logger.info("Step 2: LLM analysis (refine, attack path, mitigations)...")
        analysis = analyze_scenario(
            user_input,
            matched_techniques,
            top_k,
            mitre_mitigations=mitre_mitigations  # Pass MITRE data to LLM
        )

        # Step 3: Calculate scores (NEW)
        logger.info("Step 3: Calculating accuracy/relevance/confidence scores...")

        # Score refined techniques
        refined_techniques = analysis.get("refined_techniques", [])
        for tech in refined_techniques:
            tech_mitigations = tech.get('mitigations', [])
            similarity = tech.get('similarity_score', 1.0)
            tech['scores'] = score_technique(tech, tech_mitigations, similarity)

        # Score MITRE mitigations
        for mit in mitre_mitigations:
            mit['scores'] = score_mitigation(mit)

        logger.info(f"Scored {len(refined_techniques)} techniques and {len(mitre_mitigations)} mitigations")

        # Build response
        result = {
            "query": user_input,
            "mode": "semantic",
            "techniques": matched_techniques,  # All matched techniques
            "refined_techniques": refined_techniques,  # With scores
            "attack_path": analysis.get("attack_path", {}),
            "mitigations": analysis.get("mitigations", {}),  # Now includes mitre_mitigations
            "mitre_mitigations": mitre_mitigations,  # Explicit MITRE section with scores
        }

        logger.info("Semantic threat assessment complete")
        return result

    def _keyword_threat_assessment(self, user_input: str) -> dict:
        """
        Fallback keyword-based threat assessment (legacy).

        Args:
            user_input: User's input

        Returns:
            Dict with keyword-based results (legacy format)
        """
        logger.info("Using keyword-based threat assessment (fallback mode)")

        # Extract keywords
        keywords = self.extract_keywords(user_input)
        logger.debug(f"Extracted keywords: {keywords}")

        # Build prompt using keyword matching
        prompt = build_threat_prompt(user_input, keywords, self.mitre)

        # Extract technique IDs from prompt
        import re
        technique_ids = re.findall(r'\(ID: ([^)]+)\)', prompt)

        # Get details for each technique
        details = []
        for ext_id in technique_ids:
            summary = self.mitre.get_technique_summary(ext_id)
            mitigations = self.mitre.get_mitigation_advice(ext_id)
            details.append({
                "technique_id": ext_id,
                "summary": summary,
                "mitigations": mitigations
            })

        return {
            "query": user_input,
            "mode": "keyword",
            "prompt": prompt,
            "details": details
        }

    def extract_keywords(self, user_input: str) -> list:
        """
        Simple keyword extraction (legacy, used only in fallback mode).

        Args:
            user_input: User's input text

        Returns:
            List of keywords (lowercase, filtered by stopwords)
        """
        stopwords = {"i", "am", "doing", "the", "and", "for", "with", "to", "a", "of"}
        return [
            word.lower()
            for word in user_input.split()
            if word.lower() not in stopwords and len(word) > 3
        ]


def process(user_input, history, persona, model=None):
    """
    Future: Agentic reasoning with multi-turn conversation.

    Args:
        user_input: User's message
        history: Conversation history
        persona: Agent persona/role
        model: LLM model to use

    Returns:
        Response (not implemented yet)
    """
    # Future: Agentic reasoning, then call LLM for action/response
    # response = llm.generate_response(user_input, history, persona, model)
    return None
