# Documentation Index

This directory contains detailed technical documentation for the DEV-TEST Chatbot project.

## Core Documentation

### [ARCHITECTURE.md](ARCHITECTURE.md)
System architecture, design decisions, and technical specifications.

**Contains:**
- High-level system design diagram
- Technology stack details (LLM services, MITRE data, Python stack)
- Complete module structure and APIs
- Key design decisions and trade-offs
- Performance expectations and benchmarks
- Known limitations

**Read this when:**
- Understanding how the system works
- Making architectural decisions
- Optimizing performance
- Planning new features

### [OPERATIONS.md](OPERATIONS.md)
Operational procedures, workflows, and troubleshooting.

**Contains:**
- Environment configuration
- Data file management
- Development workflows (adding features, updating data, experimenting with models)
- Troubleshooting guides
- Security considerations

**Read this when:**
- Setting up development environment
- Troubleshooting issues
- Updating MITRE data
- Switching LLM models
- Handling security concerns

### [MAINTENANCE.md](MAINTENANCE.md)
Regular maintenance tasks and procedures.

**Contains:**
- Updating MITRE ATT&CK data (quarterly)
- Managing backups and rollbacks
- Regenerating embedding cache
- Health checks and monitoring
- Scheduled maintenance checklist
- Emergency rollback procedures

**Read this when:**
- MITRE releases new version
- Need to update MITRE data
- Managing backups
- Performing routine maintenance
- Troubleshooting after updates

### [TESTING.md](TESTING.md)
Testing strategies, scenarios, and validation results.

**Contains:**
- Testing strategy (unit, integration)
- Standard test scenarios with expected results
- Validation results from integration tests
- How to run tests

**Read this when:**
- Writing tests
- Validating changes
- Verifying system functionality
- Debugging test failures

### [ROADMAP.md](ROADMAP.md)
Current status and future enhancement plans.

**Contains:**
- Current implementation status
- Key decisions made
- Future enhancement backlog (Phase 2+)
- Optimization opportunities
- Advanced features planned

**Read this when:**
- Planning new features
- Understanding project direction
- Prioritizing work
- Checking implementation status

### [RATE_LIMITING.md](RATE_LIMITING.md) ⭐ CRITICAL
Comprehensive rate limiting guide for OpenRouter free tier (20 req/min).

**Contains:**
- OpenRouter free tier limits (20 req/min hard limit)
- Rate limiter implementation details
- Usage patterns and best practices
- Error handling strategies (429, 5xx retries)
- Performance expectations (10-15 min cache generation)
- Troubleshooting guide

**Read this when:**
- Implementing any OpenRouter API calls
- Debugging rate limit errors (429)
- Optimizing batch processing
- Generating embedding cache
- Understanding performance bottlenecks

**Also see:** [QUICK_START_RATE_LIMITING.md](QUICK_START_RATE_LIMITING.md) for quick reference

### [REFERENCES.md](REFERENCES.md)
External links and resources.

**Contains:**
- MITRE ATT&CK resources
- OpenRouter documentation
- LiteLLM guides
- Google ADK references
- Contact information

**Read this when:**
- Need external documentation
- Looking up API references
- Finding support channels

## Skills (Automated Operations)

Located in `.claude/skills/`:

### validate-integration
Run comprehensive integration tests to validate all components.

**When to use:**
- After environment setup
- Before starting development
- After major changes
- Troubleshooting connectivity

### build-embeddings-cache
Generate embedding cache for MITRE techniques (one-time, ~3 min).

**When to use:**
- Initial setup (required)
- After updating MITRE data
- After changing embedding model
- Cache corruption recovery

## Quick Navigation

**Getting Started:**
1. Read main [CLAUDE.md](../CLAUDE.md) for overview
2. Follow "Getting Started" section for setup
3. Use `/validate-integration` skill to verify
4. Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand system

**During Development:**
- Reference [ARCHITECTURE.md](ARCHITECTURE.md) for module APIs
- Follow [OPERATIONS.md](OPERATIONS.md) workflows
- Add tests per [TESTING.md](TESTING.md) guidelines
- Update [ROADMAP.md](ROADMAP.md) for new features

**Troubleshooting:**
1. Check [OPERATIONS.md](OPERATIONS.md) troubleshooting section
2. Run `/validate-integration` skill
3. Check [TESTING.md](TESTING.md) for test scenarios
4. Review [REFERENCES.md](REFERENCES.md) for external docs

---

*This index is maintained to help navigate the documentation structure.*
