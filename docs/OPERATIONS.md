# Operational Procedures

## Environment Configuration

### Required Variables (`.env`)

```bash
# OpenRouter API Key (required for LLM + embeddings)
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# Optional: OpenAI for ADK examples
OPENAI_API_KEY=sk-xxxxx

# Optional: Neo4j for agentic features
NEO4J_IMPORT_DIR=/path/to/neo4j/import
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=yourpassword
```

### Template (`.env.example`)

Create this file to document required variables without exposing secrets.

## Data Files

### MITRE ATT&CK Database
- **Path:** `chatbot/data/enterprise-attack.json`
- **Size:** ~39MB
- **Format:** STIX 2.1 JSON
- **Update Frequency:** Quarterly (MITRE releases)
- **When to Update:** Check https://github.com/mitre/cti

### Technique Embeddings Cache
- **Path:** `chatbot/data/technique_embeddings.json`
- **Size:** ~6-8MB
- **Format:** JSON `{"T1059": [0.123, 0.456, ...], ...}`
- **Dimensions:** ~1024 (nvidia/llama-nemotron-embed-vl-1b-v2:free)
- **Generation Time:** ~2-5 minutes (API rate limits)
- **Regenerate When:**
  - MITRE data updated
  - Embedding model changed
  - Cache corrupted/missing

## Development Workflow

### Adding New Features
1. **Plan:** Document in CLAUDE.md backlog section
2. **Design:** Update architecture diagrams if needed
3. **Implement:** Follow module structure and patterns
4. **Test:** Add unit + integration tests
5. **Document:** Update README.md and this file
6. **Review:** Test with diverse scenarios

### Updating MITRE Data

**Quick Method (Recommended):**
```bash
# Use the skill - handles download, validation, backup, and reminder
/update-mitre-data
```

**Manual Method:**
```bash
# 1. Download latest version
cd /mnt/c/BACKUP/DEV-TEST
wget -O chatbot/data/enterprise-attack.json.new https://raw.githubusercontent.com/mitre/cti/refs/heads/master/enterprise-attack/enterprise-attack.json

# 2. Validate download
python3 -c "import json; data=json.load(open('chatbot/data/enterprise-attack.json.new')); print(f'Valid JSON with {len([o for o in data[\"objects\"] if o.get(\"type\")==\"attack-pattern\"])} techniques')"

# 3. Backup old file
mkdir -p chatbot/data/backups
cp chatbot/data/enterprise-attack.json chatbot/data/backups/enterprise-attack.json.$(date +%Y%m%d_%H%M%S).bak

# 4. Replace with new file
mv chatbot/data/enterprise-attack.json.new chatbot/data/enterprise-attack.json

# 5. Regenerate embedding cache (REQUIRED - takes 10-15 min)
/build-embeddings-cache

# 6. Run test suite to verify
python test_openrouter.py

# 7. Update version/date in README.md
```

**Update Frequency:**
- MITRE releases updates quarterly (Q1, Q2, Q3, Q4)
- Check https://attack.mitre.org/resources/updates/ for announcements
- GitHub: https://github.com/mitre/cti/commits/master/enterprise-attack

**⚠️  CRITICAL:** After updating MITRE data, you MUST regenerate the embedding cache. The old cache will not work correctly with new/changed techniques.

**Backup Location:**
- Automatic backups stored in: `chatbot/data/backups/`
- Format: `enterprise-attack.json.YYYYMMDD_HHMMSS.bak`
- Keep last 3-5 backups for rollback capability

### Model Experimentation
**To try different OpenRouter models:**

1. Edit `agentic/llm.py`: Change model name
2. Edit `chatbot/modules/embeddings.py`: Change embedding model
3. Regenerate embedding cache if embedding model changed
4. Test with standard scenarios
5. Compare quality vs. performance vs. cost

**Models to try:**
- LLM: anthropic/claude-3-haiku, meta-llama/llama-3-70b-instruct
- Embeddings: openai/text-embedding-3-small (if budget allows)

## Troubleshooting

### Embedding Cache Missing or Outdated
**Symptom:** "Falling back to keyword search: embedding cache not found" or poor search results after MITRE update

**Solution:**
```bash
# Use the skill (recommended - handles rate limiting)
/build-embeddings-cache

# Or manual command
python -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; from chatbot.modules import embeddings; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre, embeddings); save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')"
```

**Note:** Takes 10-15 minutes due to rate limiting (20 req/min). This is normal.

### OpenRouter API Errors
**Symptom:** 429 (rate limit) or 5xx errors

**Solution:**
- Check OpenRouter status page
- Verify API key is valid
- Wait and retry (exponential backoff built-in)
- Check free tier limits

### Poor Technique Matching
**Symptom:** Irrelevant techniques returned

**Debugging:**
1. Check semantic search scores (should be >0.5)
2. Verify embedding cache is up-to-date
3. Test with explicit technique names
4. Try different embedding model
5. Adjust similarity threshold in code

### Slow Response Times
**Symptom:** >5 second responses

**Debugging:**
1. Check OpenRouter API latency
2. Verify embedding cache loaded (not regenerating each time)
3. Profile code to find bottleneck
4. Consider caching frequent queries

## Security Considerations

### API Keys
- **Storage:** .env file (gitignored)
- **Access:** Only via environment variables
- **Rotation:** Support key rotation without code changes

### MITRE Data Integrity
- **Source:** Official MITRE CTI GitHub repo
- **Validation:** Check file size, parse for corruption
- **Updates:** Manual download and validation before replacing

### Input Validation
- **User Input:** Sanitize before passing to LLM
- **Technique IDs:** Validate against known ID format (T\d{4}(.\d{3})?)
- **API Responses:** Validate structure before parsing
