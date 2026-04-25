# Documentation Structure

```
DEV-TEST/
│
├── CLAUDE.md                    # 🎯 START HERE - Lean baseline with quick reference
│   ├── Project overview
│   ├── Quick start guide
│   ├── Module quick reference
│   └── Links to detailed docs
│
├── docs/                        # 📚 Detailed technical documentation
│   ├── INDEX.md                 # Navigation guide
│   ├── ARCHITECTURE.md          # System design, tech stack, decisions
│   ├── OPERATIONS.md            # Workflows, troubleshooting, security
│   ├── TESTING.md               # Test strategies and validation
│   ├── ROADMAP.md               # Current status and future plans
│   └── REFERENCES.md            # External links and resources
│
└── .claude/skills/              # ⚡ Automated operations (skills)
    ├── validate-integration.md  # Run integration tests
    └── build-embeddings-cache.md # Generate embedding cache

```

## Philosophy

**CLAUDE.md** = Baseline context for Claude to understand the project and start coding
- Concise (146 lines vs 605 before)
- Quick reference for common tasks
- Links to detailed docs when needed

**docs/** = Deep dive technical documentation
- Organized by concern (architecture, operations, testing, etc.)
- Detailed procedures and troubleshooting
- Updated during development

**.claude/skills/** = Executable operations
- Common commands converted to skills
- Reduces permission prompts
- Reusable across conversations

## When to Read What

| Situation | Read This |
|-----------|-----------|
| Just starting | CLAUDE.md → Getting Started |
| Understanding architecture | docs/ARCHITECTURE.md |
| Setting up environment | docs/OPERATIONS.md |
| Writing tests | docs/TESTING.md |
| Planning features | docs/ROADMAP.md |
| Troubleshooting | docs/OPERATIONS.md → Troubleshooting |
| Need external docs | docs/REFERENCES.md |
| Running tests | Use `/validate-integration` skill |
| Building cache | Use `/build-embeddings-cache` skill |

## Benefits

✅ **Faster Claude Context Loading** - CLAUDE.md is 76% smaller  
✅ **Better Organization** - Concerns separated by topic  
✅ **Easier Maintenance** - Update only relevant sections  
✅ **Reusable Commands** - Skills for common operations  
✅ **Clearer Navigation** - INDEX.md guides you  
✅ **Reduced Permission Prompts** - Skills pre-approved  

## Navigation

Start with [INDEX.md](INDEX.md) for detailed navigation guide.
