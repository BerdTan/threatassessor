#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

[ -f .venv/bin/activate ] && source .venv/bin/activate

ISSUES=0

echo "=== Check 1: Deprecated import patterns ==="
for pat in \
    "from agentic.llm import generate_response" \
    "from agentic.llm import generate_response_with_system" \
    "from agentic.llm import LLMClient" \
    "import agentic.llm"; do
    echo -n "  '$pat' ... "
    HITS=$(grep -r "$pat" --include="*.py" --exclude="llm.py" \
          --exclude-dir=".venv" --exclude-dir="archive" --exclude-dir="__pycache__" . 2>/dev/null || true)
    if [ -n "$HITS" ]; then echo "FOUND"; echo "$HITS" | sed 's/^/    /'; ISSUES=$((ISSUES+1)); else echo "OK"; fi
done

echo ""
echo "=== Check 2: Module imports ==="
MODULES=(
  chatbot.modules.ground_truth_generator chatbot.modules.threat_analyst
  chatbot.modules.threat_report chatbot.modules.exhaustive_mitigation_mapper
  chatbot.modules.self_validation chatbot.modules.residual_risk
  chatbot.modules.completeness_validator chatbot.modules.mitre
  chatbot.modules.mitre_embeddings chatbot.modules.embeddings
  chatbot.modules.rate_limiter chatbot.modules.patterns.ai_pattern
  chatbot.modules.pattern_registry chatbot.modules.ssp_mapper
  chatbot.api.app chatbot.api.routes.streaming chatbot.api.routes.reports
  agentic.llm_client agentic.helper
)
for m in "${MODULES[@]}"; do
    echo -n "  $m ... "
    if python3 -c "import $m" 2>/dev/null; then echo "OK"; else
        echo "FAILED"; python3 -c "import $m" 2>&1 | head -3 | sed 's/^/    /'; ISSUES=$((ISSUES+1))
    fi
done

echo ""
echo "=== Check 3: Deprecation warnings ==="
OUT=$(python3 -W error::DeprecationWarning -c "
import chatbot.modules.ground_truth_generator, chatbot.modules.mitre
print('OK')
" 2>&1 || true)
echo "  $OUT"
echo "$OUT" | grep -q "DeprecationWarning" && ISSUES=$((ISSUES+1))

echo ""
echo "=== Check 4: Unit tests ==="
if command -v pytest &>/dev/null && [ -d tests/unit ]; then
    pytest tests/unit/ -q --tb=short 2>&1 | tail -5 || ISSUES=$((ISSUES+1))
else
    echo "  (pytest or tests/unit not available — skipped)"
fi

echo ""
echo "=== Check 5: Anti-patterns ==="
echo -n "  Direct litellm.completion() ... "
HITS=$(grep -r "litellm\.completion(" --include="*.py" --exclude="llm_client.py" \
       --exclude-dir=".venv" --exclude-dir="archive" . 2>/dev/null || true)
[ -n "$HITS" ] && { echo "FOUND"; echo "$HITS" | sed 's/^/    /'; ISSUES=$((ISSUES+1)); } || echo "OK"

echo ""
echo "=== Summary: $ISSUES issue(s) found ==="
exit $ISSUES
