#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

[ -f .venv/bin/activate ] && source .venv/bin/activate

echo "=== Quick Integration Test ==="
echo ""

echo "1. Dependencies..."
python3 -c "
import sys
for dep in ['litellm','numpy','dotenv','requests']:
    try: __import__(dep); print(f'  {dep}: OK')
    except ImportError: print(f'  {dep}: MISSING'); sys.exit(1)
"

echo ""
echo "2. Rate limiter..."
python3 -c "
from chatbot.modules.rate_limiter import get_rate_limit_stats
s = get_rate_limit_stats()
print(f'  {s[\"recent_requests\"]}/{s[\"max_requests\"]} requests used')
"

echo ""
echo "3. MITRE data..."
python3 -c "
from chatbot.modules.mitre import MitreHelper
m = MitreHelper(use_local=True)
t = m.get_techniques()
count = len(t)
assert count >= 835, f'Only {count} techniques — expected ≥835'
print(f'  {count} techniques, {len(m.get_tactics())} tactics')
"

echo ""
echo "4. OpenRouter API key + embedding call..."
python3 -c "
import os, requests, sys, time
if os.path.exists('.env'):
    for line in open('.env'):
        if line.strip() and '=' in line and not line.startswith('#'):
            k,v = line.strip().split('=',1); os.environ[k]=v
key = os.getenv('OPENROUTER_API_KEY','')
assert len(key) > 10, 'OPENROUTER_API_KEY missing or too short'
print(f'  Key configured ({len(key)} chars)')

r = requests.get('https://openrouter.ai/api/v1/models',
    headers={'Authorization': f'Bearer {key}'}, timeout=10)
assert r.status_code == 200, f'Models endpoint: {r.status_code}'
print(f'  Connected ({len(r.json()[\"data\"])} models available)')

from chatbot.modules.embeddings import DEFAULT_EMBEDDING_MODEL as model
t0 = time.time()
resp = requests.post('https://openrouter.ai/api/v1/embeddings',
    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    json={'model': model, 'input': 'test'}, timeout=30)
assert resp.status_code == 200, f'Embedding call: {resp.status_code} {resp.text[:80]}'
dims = len(resp.json()['data'][0]['embedding'])
print(f'  Embedding OK — {dims} dims in {time.time()-t0:.2f}s')
"

echo ""
echo "5. LLM providers (primary + configured fallbacks)..."
python3 - <<'PYEOF'
import os, time, sys
if os.path.exists('.env'):
    for line in open('.env'):
        if line.strip() and '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1); os.environ[k] = v

from agentic.llm_client import LLMClient, LLMProvider

client = LLMClient()
primary = client.primary_provider
fallbacks = list(client.fallback_configs.keys())
verifier = client.verifier_provider

providers_to_test = [primary] + fallbacks
if verifier and verifier not in providers_to_test:
    providers_to_test.append(verifier)

PROBE = "Reply with exactly: OK"

any_fail = False
for p in providers_to_test:
    label = p.value
    tag = "(primary)" if p == primary else ("(verifier)" if p == verifier else "(fallback)")
    try:
        t0 = time.time()
        resp = client.generate(PROBE, provider=p, max_tokens=10)
        elapsed = time.time() - t0
        content = (resp.content or "").strip()[:40]
        print(f"  {label} {tag}: OK — \"{content}\" in {elapsed:.1f}s")
    except Exception as e:
        print(f"  {label} {tag}: FAIL — {e}", file=sys.stderr)
        any_fail = True

if any_fail:
    sys.exit(1)
PYEOF

echo ""
echo "=== ALL SYSTEMS OK ==="
