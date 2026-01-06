# pgdbm Skills

Claude Code skills for using pgdbm effectively without needing to read documentation.

## Quick Start

**New to pgdbm?** Start with these in order:

1. **`pgdbm:using-pgdbm`** - Mental model (one pool/many schemas/templates)
2. **`pgdbm:choosing-pattern`** - Which pattern for your use case?
3. **Implementation skill** - Follow decision from #2:
   - `pgdbm:shared-pool-pattern` - Multi-service apps
   - `pgdbm:dual-mode-library` - PyPI packages
   - `pgdbm:standalone-service` - Simple services
4. **`pgdbm:testing-database-code`** - Write tests
5. **`pgdbm:common-mistakes`** - Avoid footguns

**Need complete API?** Use these reference skills:
- **`pgdbm:core-api-reference`** - ALL AsyncDatabaseManager methods
- **`pgdbm:migrations-api-reference`** - ALL AsyncMigrationManager methods

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

**`pgdbm:standalone-service`**
- Simple single-service setup
- FastAPI integration
- Background worker pattern
- Environment configuration

### API Reference Skills

**`pgdbm:core-api-reference`**
- Complete AsyncDatabaseManager API (ALL methods)
- Complete DatabaseConfig parameters
- TransactionManager API
- Bulk operations, Pydantic integration
- SSL, timeouts, retry configuration

**`pgdbm:migrations-api-reference`**
- Complete AsyncMigrationManager API (ALL methods)
- Migration file format and naming
- Checksum validation
- Development methods
- Migration table schema

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
    └─ pgdbm:standalone-service (Simple services)
    ↓
pgdbm:testing-database-code (Testing)
    ↓
pgdbm:common-mistakes (Prevention)

API Reference (as needed):
├─ pgdbm:core-api-reference (AsyncDatabaseManager & DatabaseConfig)
└─ pgdbm:migrations-api-reference (AsyncMigrationManager)
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

## Complete Skill Set

All 9 planned skills are now implemented with complete API coverage.

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
| using-pgdbm | 399 | 1479 | Mental model + quick ref |
| choosing-pattern | 288 | 1251 | Pattern selection |
| shared-pool-pattern | 417 | 1222 | Multi-service impl |
| dual-mode-library | 449 | 1336 | PyPI package impl |
| standalone-service | 291 | 707 | Simple service impl |
| testing-database-code | 507 | 1478 | Test fixtures |
| common-mistakes | 360 | 1407 | Anti-patterns |
| core-api-reference | 732 | 2343 | Complete AsyncDatabaseManager |
| migrations-api-reference | 727 | 2121 | Complete AsyncMigrationManager |

**Total: 4,170 lines, 13,344 words** - complete pgdbm reference without needing docs.

## Contributing

To add skills:
1. Follow TDD methodology (RED-GREEN-REFACTOR)
2. Test baseline without skill
3. Write skill addressing baseline failures
4. Verify skill improves agent efficiency
5. Commit following conventional commits format
