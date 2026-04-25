# Project Roadmap

## Current Status

**Phase:** Planning Complete, Ready for Implementation
**Last Validated:** 2026-04-25
**Test Results:** All systems operational (see TESTING.md)
**Next Steps:** Begin Phase 1 implementation

**Key Decisions Made:**
1. ✅ OpenRouter with free tier models (both validated)
2. ✅ JSON cache format (~13MB, acceptable)
3. ✅ Two-stage search (embeddings → LLM refinement)
4. ✅ Keyword fallback maintained for resilience
5. ✅ Progressive 5-phase implementation approach

**Ready to Implement:**
- Environment configuration (.env setup complete)
- Test suite validated (test_openrouter.py passing)
- Documentation complete (CLAUDE.md, plan file)
- Confidence level: 95%+

---

## Future Enhancements (Backlog)

### Phase 2 Features
1. **Relationship Graph Queries**
   - Query technique → tactics → related techniques
   - Find mitigation → affected techniques
   - Visualize attack paths

2. **Multi-Technique Attack Chains**
   - Identify sequence of techniques
   - Map full attack lifecycle
   - Suggest comprehensive defense strategy

3. **Platform-Aware Search**
   - Extract platform from user input (Windows, Linux, cloud)
   - Filter techniques by x_mitre_platforms
   - Prioritize platform-specific mitigations

4. **Tactic-Based Exploration**
   - "Show me Credential Access techniques"
   - "What Discovery methods exist?"
   - Browse by kill chain phase

### Optimization
1. **Query Caching**
   - Cache frequent queries (in-memory or Redis)
   - LRU eviction policy
   - Invalidate on MITRE data update

2. **Embedding Cache Optimization**
   - Compress JSON with gzip
   - Switch to binary format (msgpack, protobuf)
   - Incremental updates (only new/changed techniques)

3. **Batch Processing**
   - Process multiple user queries in parallel
   - Batch embedding calls to OpenRouter
   - Connection pooling for API requests

### Advanced Features
1. **Web UI**
   - Interactive threat modeling interface
   - Drag-and-drop technique composition
   - Export reports (PDF, JSON, STIX)

2. **Integration with SIEM**
   - Query based on security events
   - Auto-generate detection rules
   - Link to observability data

3. **Custom Embeddings**
   - Fine-tune embedding model on security data
   - Include CVE, threat intel, incident data
   - Improve domain-specific accuracy

4. **Multi-Language Support**
   - Translate user queries to English
   - Support threat scenarios in other languages
   - Localize mitigation advice
