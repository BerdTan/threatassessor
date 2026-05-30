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
echo "4. API key..."
python3 -c "
import os, sys
if os.path.exists('.env'):
    for line in open('.env'):
        if line.strip() and '=' in line and not line.startswith('#'):
            k,v = line.strip().split('=',1); os.environ[k]=v
key = os.getenv('OPENROUTER_API_KEY','')
assert len(key) > 10, 'API key missing or too short'
print(f'  Key configured ({len(key)} chars)')
"

echo ""
echo "5. OpenRouter connection + embedding call..."
python3 -c "
import os, requests, sys, time
if os.path.exists('.env'):
    for line in open('.env'):
        if line.strip() and '=' in line and not line.startswith('#'):
            k,v = line.strip().split('=',1); os.environ[k]=v
from chatbot.modules.rate_limiter import get_rate_limit_stats
api_key = os.getenv('OPENROUTER_API_KEY')

r = requests.get('https://openrouter.ai/api/v1/models',
    headers={'Authorization': f'Bearer {api_key}'}, timeout=10)
assert r.status_code == 200, f'Models endpoint: {r.status_code}'
print(f'  Connected ({len(r.json()[\"data\"])} models available)')

from chatbot.modules import embeddings as emb_mod
from chatbot.modules.mitre_embeddings import get_embedding_model
model = get_embedding_model()
t0 = time.time()
resp = requests.post('https://openrouter.ai/api/v1/embeddings',
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
    json={'model': model, 'input': 'test'}, timeout=30)
assert resp.status_code == 200, f'Embedding call: {resp.status_code} {resp.text[:80]}'
dims = len(resp.json()['data'][0]['embedding'])
print(f'  Embedding OK — {dims} dims in {time.time()-t0:.2f}s')
"

echo ""
echo "=== ALL SYSTEMS OK ==="
