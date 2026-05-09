---
skill: check-deprecation
description: Check for deprecated imports, broken modules, and deprecation warnings across codebase
---

# Check Deprecation Skill

This skill validates that no code is using deprecated imports or patterns, and that all modules can be imported without triggering deprecation warnings.

## Usage

When user asks to:
- "check for deprecation"
- "validate imports"
- "check for breaks"
- "verify no deprecated code"
- "test for import errors"
- "check modules still work"

## What This Checks

1. ✅ **Deprecated import patterns** - Grep for known deprecated imports
2. ✅ **Module import test** - Try importing each module individually
3. ✅ **Deprecation warnings** - Run with warnings enabled
4. ✅ **Test suite** - Verify tests pass
5. ✅ **Common anti-patterns** - Check for other deprecated patterns

---

## Implementation

```bash
#!/bin/bash
set -e

cd /mnt/c/BACKUP/DEV-TEST

# Activate virtual environment if exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║              DEPRECATION & IMPORT CHECK                               ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

ISSUES_FOUND=0

# ============================================================================
# CHECK 1: Deprecated Import Patterns
# ============================================================================
echo "🔍 Check 1: Deprecated Import Patterns"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Known deprecated patterns
DEPRECATED_PATTERNS=(
    "from agentic.llm import generate_response"
    "from agentic.llm import generate_response_with_system"
    "from agentic.llm import LLMClient"
    "import agentic.llm"
)

FOUND_DEPRECATED=0

for pattern in "${DEPRECATED_PATTERNS[@]}"; do
    echo -n "Checking: '$pattern' ... "
    
    # Search in Python files, exclude deprecated wrapper itself
    MATCHES=$(grep -r "$pattern" \
        --include="*.py" \
        --exclude="llm.py" \
        --exclude-dir=".venv" \
        --exclude-dir="archive" \
        --exclude-dir="__pycache__" \
        . 2>/dev/null || true)
    
    if [ -n "$MATCHES" ]; then
        echo "❌ FOUND"
        echo "$MATCHES" | sed 's/^/   /'
        FOUND_DEPRECATED=1
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    else
        echo "✅ OK"
    fi
done

if [ $FOUND_DEPRECATED -eq 0 ]; then
    echo ""
    echo "✅ No deprecated imports found"
else
    echo ""
    echo "⚠️  Deprecated imports detected - see above"
    echo "   Action: Replace with 'from agentic.llm_client import LLMClient'"
fi

echo ""

# ============================================================================
# CHECK 2: Module Import Test (All Chatbot Modules)
# ============================================================================
echo "🔍 Check 2: Module Import Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

MODULES=(
    "chatbot.modules.agent"
    "chatbot.modules.architecture_analyzer"
    "chatbot.modules.confidence_scoring"
    "chatbot.modules.embeddings"
    "chatbot.modules.ground_truth_generator"
    "chatbot.modules.layered_defense"
    "chatbot.modules.llm_mitre_analyzer"
    "chatbot.modules.mitre"
    "chatbot.modules.mitre_embeddings"
    "chatbot.modules.rate_limiter"
    "chatbot.modules.rapids_driven_controls"
    "chatbot.modules.residual_risk"
    "chatbot.modules.self_validation"
    "chatbot.modules.threat_report"
    "agentic.llm_client"
    "agentic.llm"
    "agentic.helper"
)

IMPORT_FAILURES=0

for module in "${MODULES[@]}"; do
    echo -n "Testing: $module ... "
    
    if python3 -c "import warnings; warnings.simplefilter('error', DeprecationWarning); import $module" 2>/dev/null; then
        echo "✅ OK"
    else
        echo "❌ FAILED"
        echo "   Error details:"
        python3 -c "import $module" 2>&1 | sed 's/^/   /'
        IMPORT_FAILURES=$((IMPORT_FAILURES + 1))
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

echo ""

if [ $IMPORT_FAILURES -eq 0 ]; then
    echo "✅ All modules import successfully"
else
    echo "⚠️  $IMPORT_FAILURES module(s) failed to import"
fi

echo ""

# ============================================================================
# CHECK 3: Deprecation Warnings (With Warning Mode)
# ============================================================================
echo "🔍 Check 3: Deprecation Warnings"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Running sample imports with deprecation warnings enabled..."
echo ""

WARNINGS_OUTPUT=$(python3 -W default::DeprecationWarning -c "
import sys
sys.path.insert(0, '.')

# Test importing key modules that might trigger warnings
modules_to_test = [
    'chatbot.modules.ground_truth_generator',
    'chatbot.modules.llm_mitre_analyzer',
    'tests.generate_ground_truth',
]

warnings_found = []
for mod in modules_to_test:
    try:
        __import__(mod)
    except Exception as e:
        warnings_found.append(f'{mod}: {e}')

if warnings_found:
    print('WARNINGS DETECTED:')
    for w in warnings_found:
        print(f'  - {w}')
else:
    print('NO_WARNINGS')
" 2>&1)

if echo "$WARNINGS_OUTPUT" | grep -q "DeprecationWarning"; then
    echo "⚠️  Deprecation warnings detected:"
    echo "$WARNINGS_OUTPUT" | sed 's/^/   /'
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
elif echo "$WARNINGS_OUTPUT" | grep -q "NO_WARNINGS"; then
    echo "✅ No deprecation warnings"
else
    echo "⚠️  Check output:"
    echo "$WARNINGS_OUTPUT" | sed 's/^/   /'
fi

echo ""

# ============================================================================
# CHECK 4: Test Suite Execution
# ============================================================================
echo "🔍 Check 4: Test Suite Execution"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Running pytest with deprecation warnings..."
echo ""

# Run pytest on key test files
if command -v pytest &> /dev/null; then
    # Run a quick subset of tests
    TEST_FILES=(
        "tests/test_semantic_search.py::test_import_modules"
        "tests/test_stage1_validation.py::test_embedding_response_format"
    )
    
    TEST_PASSED=0
    
    for test_file in "${TEST_FILES[@]}"; do
        if [ -f "$(echo $test_file | cut -d: -f1)" ]; then
            echo -n "Testing: $test_file ... "
            
            if pytest "$test_file" -W error::DeprecationWarning -q 2>/dev/null; then
                echo "✅ PASS"
            else
                echo "❌ FAIL"
                pytest "$test_file" -W default::DeprecationWarning --tb=short 2>&1 | tail -20 | sed 's/^/   /'
                TEST_PASSED=1
                ISSUES_FOUND=$((ISSUES_FOUND + 1))
            fi
        fi
    done
    
    echo ""
    
    if [ $TEST_PASSED -eq 0 ]; then
        echo "✅ Test suite passes"
    else
        echo "⚠️  Some tests failed - see above"
    fi
else
    echo "⚠️  pytest not found - skipping test suite check"
    echo "   Install: pip install pytest"
fi

echo ""

# ============================================================================
# CHECK 5: Common Anti-Patterns
# ============================================================================
echo "🔍 Check 5: Common Anti-Patterns"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ANTI_PATTERNS_FOUND=0

# Check for direct litellm.completion calls (should use LLMClient)
echo -n "Checking for direct litellm.completion() calls ... "
DIRECT_LITELLM=$(grep -r "litellm.completion(" \
    --include="*.py" \
    --exclude="llm_client.py" \
    --exclude="llm.py" \
    --exclude-dir=".venv" \
    --exclude-dir="archive" \
    . 2>/dev/null || true)

if [ -n "$DIRECT_LITELLM" ]; then
    echo "⚠️  FOUND"
    echo "$DIRECT_LITELLM" | sed 's/^/   /'
    ANTI_PATTERNS_FOUND=1
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    echo "✅ OK"
fi

# Check for old provider config patterns
echo -n "Checking for old OPENROUTER_API_KEY hardcoded usage ... "
HARDCODED_KEY=$(grep -r 'os.getenv("OPENROUTER_API_KEY")' \
    --include="*.py" \
    --exclude="helper.py" \
    --exclude="embeddings.py" \
    --exclude-dir=".venv" \
    --exclude-dir="archive" \
    . 2>/dev/null || true)

if [ -n "$HARDCODED_KEY" ]; then
    echo "⚠️  FOUND"
    echo "$HARDCODED_KEY" | sed 's/^/   /'
    echo "   Note: Consider using helper.get_openrouter_api_key()"
    ANTI_PATTERNS_FOUND=1
else
    echo "✅ OK"
fi

echo ""

if [ $ANTI_PATTERNS_FOUND -eq 0 ]; then
    echo "✅ No anti-patterns detected"
else
    echo "⚠️  Anti-patterns found - consider refactoring"
fi

echo ""

# ============================================================================
# FINAL SUMMARY
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "                        SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $ISSUES_FOUND -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED"
    echo ""
    echo "Status: READY FOR COMMIT"
    echo ""
    echo "Verified:"
    echo "  ✓ No deprecated imports"
    echo "  ✓ All modules import successfully"
    echo "  ✓ No deprecation warnings"
    echo "  ✓ Test suite passes"
    echo "  ✓ No anti-patterns detected"
else
    echo "⚠️  ISSUES DETECTED: $ISSUES_FOUND"
    echo ""
    echo "Status: NEEDS ATTENTION"
    echo ""
    echo "Review the output above and fix issues before committing."
    echo ""
    echo "Common fixes:"
    echo "  • Replace 'from agentic.llm import' with 'from agentic.llm_client import'"
    echo "  • Update deprecated function calls"
    echo "  • Fix broken imports"
    echo "  • Update tests to use new patterns"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Exit with error code if issues found
exit $ISSUES_FOUND
```

---

## Expected Output (All Pass)

```
╔═══════════════════════════════════════════════════════════════════════╗
║              DEPRECATION & IMPORT CHECK                               ║
╚═══════════════════════════════════════════════════════════════════════╝

🔍 Check 1: Deprecated Import Patterns
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Checking: 'from agentic.llm import generate_response' ... ✅ OK
Checking: 'from agentic.llm import generate_response_with_system' ... ✅ OK
Checking: 'from agentic.llm import LLMClient' ... ✅ OK
Checking: 'import agentic.llm' ... ✅ OK

✅ No deprecated imports found

🔍 Check 2: Module Import Test
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Testing: chatbot.modules.agent ... ✅ OK
Testing: chatbot.modules.architecture_analyzer ... ✅ OK
Testing: chatbot.modules.confidence_scoring ... ✅ OK
Testing: chatbot.modules.embeddings ... ✅ OK
Testing: chatbot.modules.ground_truth_generator ... ✅ OK
Testing: chatbot.modules.layered_defense ... ✅ OK
Testing: chatbot.modules.llm_mitre_analyzer ... ✅ OK
Testing: chatbot.modules.mitre ... ✅ OK
Testing: chatbot.modules.mitre_embeddings ... ✅ OK
Testing: chatbot.modules.rate_limiter ... ✅ OK
Testing: chatbot.modules.rapids_driven_controls ... ✅ OK
Testing: chatbot.modules.residual_risk ... ✅ OK
Testing: chatbot.modules.self_validation ... ✅ OK
Testing: chatbot.modules.threat_report ... ✅ OK
Testing: agentic.llm_client ... ✅ OK
Testing: agentic.llm ... ✅ OK
Testing: agentic.helper ... ✅ OK

✅ All modules import successfully

🔍 Check 3: Deprecation Warnings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running sample imports with deprecation warnings enabled...

✅ No deprecation warnings

🔍 Check 4: Test Suite Execution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running pytest with deprecation warnings...

Testing: tests/test_semantic_search.py::test_import_modules ... ✅ PASS
Testing: tests/test_stage1_validation.py::test_embedding_response_format ... ✅ PASS

✅ Test suite passes

🔍 Check 5: Common Anti-Patterns
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Checking for direct litellm.completion() calls ... ✅ OK
Checking for old OPENROUTER_API_KEY hardcoded usage ... ✅ OK

✅ No anti-patterns detected

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ ALL CHECKS PASSED

Status: READY FOR COMMIT

Verified:
  ✓ No deprecated imports
  ✓ All modules import successfully
  ✓ No deprecation warnings
  ✓ Test suite passes
  ✓ No anti-patterns detected

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Expected Output (Issues Found)

```
╔═══════════════════════════════════════════════════════════════════════╗
║              DEPRECATION & IMPORT CHECK                               ║
╚═══════════════════════════════════════════════════════════════════════╝

🔍 Check 1: Deprecated Import Patterns
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Checking: 'from agentic.llm import generate_response' ... ❌ FOUND
   chatbot/modules/old_module.py:10:from agentic.llm import generate_response

⚠️  Deprecated imports detected - see above
   Action: Replace with 'from agentic.llm_client import LLMClient'

🔍 Check 2: Module Import Test
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Testing: chatbot.modules.agent ... ✅ OK
Testing: chatbot.modules.old_module ... ❌ FAILED
   Error details:
   ModuleNotFoundError: No module named 'deprecated_lib'

⚠️  1 module(s) failed to import

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  ISSUES DETECTED: 2

Status: NEEDS ATTENTION

Review the output above and fix issues before committing.

Common fixes:
  • Replace 'from agentic.llm import' with 'from agentic.llm_client import'
  • Update deprecated function calls
  • Fix broken imports
  • Update tests to use new patterns

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## What Gets Checked

### Check 1: Deprecated Import Patterns
Searches for known deprecated patterns:
- `from agentic.llm import generate_response` ❌
- `from agentic.llm import generate_response_with_system` ❌
- `from agentic.llm import LLMClient` ❌
- `import agentic.llm` ⚠️ (acceptable only if for wrapper)

**Should be:** `from agentic.llm_client import LLMClient`

### Check 2: Module Import Test
Attempts to import each module individually to catch:
- Missing dependencies
- Broken imports
- Syntax errors
- Circular dependencies

**Tests all modules in:**
- `chatbot.modules.*` (14 modules)
- `agentic.*` (3 modules)

### Check 3: Deprecation Warnings
Runs Python with deprecation warnings enabled to catch:
- DeprecationWarning from standard library
- Custom deprecation warnings (from our wrapper)
- Future deprecation notices

### Check 4: Test Suite Execution
Runs subset of pytest tests to verify:
- Tests still pass with new code
- No test failures from deprecated imports
- Test imports work correctly

### Check 5: Common Anti-Patterns
Checks for patterns that should be refactored:
- Direct `litellm.completion()` calls (should use `LLMClient`)
- Hardcoded API key access (should use `helper.py` functions)
- Other deprecated patterns specific to this codebase

---

## Success Criteria

**Ready for commit when:**
- ✅ No deprecated import patterns found
- ✅ All modules import successfully
- ✅ No deprecation warnings triggered
- ✅ Test suite passes
- ✅ No anti-patterns detected

**Exit code:** 0 = success, >0 = issues found (for CI/CD integration)

---

## Timing

- **Expected runtime:** ~2 minutes
- Faster than full test suite (~10-15 min)
- Longer than quick-test (~15 sec)

**Breakdown:**
- Check 1 (grep): ~5 seconds
- Check 2 (imports): ~30 seconds
- Check 3 (warnings): ~20 seconds
- Check 4 (tests): ~60 seconds
- Check 5 (patterns): ~5 seconds

---

## When to Use

**Use `/check-deprecation` when:**
- ✅ After major refactoring (like LLM client migration)
- ✅ Before committing large changes
- ✅ After dependency updates
- ✅ Before merging to main branch
- ✅ When adding new modules
- ✅ After Python version upgrade

**Also useful for:**
- Pre-commit hooks (automated)
- CI/CD pipeline validation
- Code review preparation
- Periodic codebase health checks

---

## Comparison with Other Skills

| Skill | Time | Focus | Use Case |
|-------|------|-------|----------|
| `/quick-test` | ~15s | Basic functionality | Quick sanity check |
| `/check-deprecation` | ~2min | Import health + deprecations | After refactoring |
| `/validate-integration` | ~3min | Full API integration | Comprehensive validation |
| `/housekeep-docs` | ~15min | Documentation | Pre-commit docs check |

---

## Failure Handling

**If deprecated imports found:**
1. Review the file and line number
2. Replace with correct import:
   ```python
   # OLD (deprecated)
   from agentic.llm import generate_response
   
   # NEW (correct)
   from agentic.llm_client import LLMClient
   client = LLMClient()
   response = client.generate(prompt="...")
   ```
3. Re-run `/check-deprecation`

**If module import fails:**
1. Check error message for missing dependency
2. Install missing package: `pip install <package>`
3. Fix import paths if relocated
4. Check for circular dependencies

**If deprecation warnings appear:**
1. Review warning message for details
2. Update to use new API
3. If intentional (testing wrapper), that's OK
4. Document why if keeping deprecated code

**If tests fail:**
1. Run full test suite: `pytest tests/ -v`
2. Fix failing tests
3. Update test patterns to use new imports
4. Re-run `/check-deprecation`

**If anti-patterns found:**
1. Refactor to use LLMClient abstraction
2. Use helper functions instead of direct os.getenv()
3. Follow established patterns in codebase
4. Document exceptions if needed

---

## Integration with CI/CD

Can be used in GitHub Actions:

```yaml
# .github/workflows/check-deprecation.yml
name: Check Deprecation

on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Check for deprecations
        run: bash .claude/skills/check-deprecation.md
```

---

## Notes

- ✅ Excludes `.venv`, `archive/`, `__pycache__` from checks
- ✅ Excludes deprecated wrapper files themselves (llm.py, llm_client.py)
- ✅ Non-destructive - only reads, doesn't modify files
- ✅ Fast feedback - identifies issues in ~2 minutes
- ✅ Can be run repeatedly without side effects
- ⚠️ Requires pytest installed for full test suite check
- 💡 Exit code indicates pass/fail for automation

---

**Skill Version:** 1.0  
**Created:** 2026-05-09  
**Estimated Time:** ~2 minutes
