# pgdbm Skills

Claude Code skills for using pgdbm effectively without needing to read documentation.

## Quick Start

**New to pgdbm?** Start with these in order:

1. **`pgdbm:using-pgdbm`** - Mental model (one pool/many schemas/templates)
2. **`pgdbm:choosing-pattern`** - Which pattern for your use case?
3. **Implementation skill** - Follow decision from #2:
   - `pgdbm:shared-pool-pattern` - Multi-service apps
   - `pgdbm:dual-mode-library` - PyPI packages
4. **`pgdbm:testing-database-code`** - Write tests
5. **`pgdbm:common-mistakes`** - Avoid footguns

## Skills Overview

### Core Skills (Start Here)

**`pgdbm:using-pgdbm`**
- Mental model and core principles
- Complete API reference (AsyncDatabaseManager, AsyncMigrationManager)
- Why patterns exist (connection limits, portability)
- Template syntax explained
- Working examples

**`pgdbm:choosing-pattern`**
- Decision tree for pattern selection
- <30 second pattern choice
- Comparison table
- When to use which pattern

### Implementation Skills

**`pgdbm:shared-pool-pattern`**
- Complete setup for multi-service apps
- FastAPI integration
- Migration management
- Pool sizing guide
- Dependency injection pattern

**`pgdbm:dual-mode-library`**
- Complete template for PyPI packages
- Standalone + shared pool modes
- Ownership tracking
- Conditional cleanup
- Multi-library composition

### Testing & Quality

**`pgdbm:testing-database-code`**
- Fixture selection decision tree
- All 6 fixtures explained
- Usage examples
- Performance comparison
- Testing patterns

**`pgdbm:common-mistakes`**
- Rationalization table
- Red flags for each mistake
- Symptom-based debugging
- Self-check questions

## Skill Relationships

```
pgdbm:using-pgdbm (Mental Model)
    ↓
pgdbm:choosing-pattern (Decision Tree)
    ↓
    ├─ pgdbm:shared-pool-pattern (Multi-service)
    ├─ pgdbm:dual-mode-library (PyPI packages)
    └─ (pgdbm:standalone-service - not yet implemented)
    ↓
pgdbm:testing-database-code (Testing)
    ↓
pgdbm:common-mistakes (Prevention)
```

## Design Philosophy

These skills follow the **completeness principle**:
- Agents don't have access to pgdbm docs
- All API signatures included in skills
- All critical patterns documented
- No need to explore codebase or read docs
- Following superpowers:writing-skills TDD methodology

## Usage Notes

**For Claude Code agents:**
- Skills are self-contained references
- Cross-references use skill names (e.g., `pgdbm:using-pgdbm`)
- All skills tested with baseline/green methodology
- Optimized for rapid decision-making

**For developers:**
- Skills can be used as quick reference even without Claude
- Decision trees help choose patterns
- Code examples are copy-paste ready
- Symptom-based debugging sections help troubleshoot

## What's Not Included

These skills were deprioritized (covered by existing skills):

- `pgdbm:standalone-service` - Simple case, covered in `using-pgdbm`
- `pgdbm:core-api-reference` - Complete API included in `using-pgdbm`
- `pgdbm:migrations-api-reference` - Migration API included in `using-pgdbm`

The current 5 skills cover all critical use cases.

## Future Additions

Potential skills for later (based on user feedback):
- `pgdbm:monitoring-performance` - Query monitoring, pool stats
- `pgdbm:multi-tenant-saas` - Deep dive on tenant isolation
- `pgdbm:troubleshooting` - Common errors and solutions
- `pgdbm:migration-strategies` - Advanced migration patterns

## Testing Methodology

All skills created following TDD approach from `superpowers:writing-skills`:
1. RED: Baseline testing without skill
2. GREEN: Write skill, test with skill
3. REFACTOR: Close loopholes if found

## File Sizes

| Skill | Lines | Words | Purpose |
|-------|-------|-------|---------|
| using-pgdbm | 408 | ~3200 | Mental model + API |
| choosing-pattern | 288 | ~2100 | Pattern selection |
| shared-pool-pattern | 417 | ~2500 | Multi-service impl |
| dual-mode-library | 449 | ~2800 | PyPI package impl |
| testing-database-code | 507 | ~3000 | Test fixtures |
| common-mistakes | 360 | ~2400 | Anti-patterns |

Total: ~2429 lines, ~16k words - complete pgdbm reference without docs.

## Contributing

To add skills:
1. Follow TDD methodology (RED-GREEN-REFACTOR)
2. Test baseline without skill
3. Write skill addressing baseline failures
4. Verify skill improves agent efficiency
5. Commit following conventional commits format
