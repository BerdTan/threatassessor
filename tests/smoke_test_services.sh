#!/bin/bash
#
# Phase 2A Smoke Test: Service layer with concurrent requests
#
# Validates:
# - 3 parallel analysis requests
# - Thread safety
# - Request isolation
#

set -e

echo "=== Phase 2A Service Layer Smoke Test ==="

# Activate venv if available
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "→ Testing service imports..."
python3 -c "
from chatbot.services import ThreatAnalysisService, ValidationService
from chatbot.services.base_service import MitreCache
print('  ✓ Service imports OK')
"

echo "→ Testing concurrent analysis (3 parallel requests)..."
python3 << 'EOF'
import threading
from chatbot.services import ThreatAnalysisService

service = ThreatAnalysisService()
results = []

def analyze():
    result = service.safe_execute(
        architecture_path="tests/data/architectures/02_minimal_defended.mmd",
        include_validation=False
    )
    results.append(result)

# Launch 3 threads
threads = [threading.Thread(target=analyze) for _ in range(3)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=30)

# Validate
assert len(results) == 3, f"Expected 3 results, got {len(results)}"
assert all(r.success for r in results), "Some requests failed"
request_ids = [r.request_id for r in results]
assert len(set(request_ids)) == 3, "Request IDs not unique"

print(f"  ✓ 3 concurrent requests completed successfully")
print(f"  ✓ Request IDs: {request_ids[0][:8]}..., {request_ids[1][:8]}..., {request_ids[2][:8]}...")
EOF

echo "→ Testing MitreCache singleton..."
python3 << 'EOF'
import threading
from chatbot.services.base_service import MitreCache

cache_ids = []

def get_cache():
    cache = MitreCache()
    cache_ids.append(id(cache))

threads = [threading.Thread(target=get_cache) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()

assert len(set(cache_ids)) == 1, "MitreCache not singleton"
print(f"  ✓ MitreCache singleton verified (5 threads, 1 instance)")
EOF

echo "✓ PHASE 2A SMOKE TEST PASSED"
