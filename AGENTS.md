# Repository Guidelines

## Project Structure & Module Organization
pgdbm's runtime code lives under `src/pgdbm/`, split across focused modules: `core.py` handles connection orchestration, `migrations.py` wraps schema evolution, `testing.py` and `fixtures/` expose helpers, and `cli/` contains the packaged entrypoint. Tests live in `tests/`, mirroring the public API and reusing helpers under `tests/helpers.py`. Long-form docs and decision records belong in `docs/`, and runnable reference apps are in `examples/`. Distribution artefacts are staged in `dist/`; exclude the directory from commits unless you are publishing a release.

## Build, Test, and Development Commands
- `uv sync` installs the dev environment from `pyproject.toml` and `uv.lock`.
- `pip install -e ".[dev]"` is the fallback when uv is unavailable.
- `uv run pytest` executes the full test matrix defined in `pyproject.toml`.
- `uv run pre-commit run --all-files` enforces Black, Ruff, isort, and mypy.
- `uv build` or `python -m build` produces distributable wheels via Hatchling.

## Coding Style & Naming Conventions
Format Python with Black at a 100-character line limit, and keep imports sorted using the bundled isort profile (both run through pre-commit). Ruff linting is active for pycodestyle, flake8-bugbear, and pyupgrade rules, so resolve warnings instead of suppressing them. Use 4-space indentation, type annotate public functions, and prefer descriptive async names such as `AsyncDatabaseManager` or `create_shared_pool`. Avoid wildcard imports, keep module-level constants upper snake case, and align CLI command names with the existing `pgdbm` namespace.

## Testing Guidelines
Pytest discovers files named `test_*.py` under `tests/` with asyncio support enabled. Import `pgdbm.fixtures.conftest` in `tests/conftest.py` to gain the isolation fixtures (`test_db`, `test_db_with_schema`, `test_db_with_tables`)—each test then runs against a fresh database. Reach for `test_db_isolated` only when you need the faster transaction/savepoint flow; it now yields a `TransactionManager` that guarantees rollback after the most recent bugfix. Mark long-running cases with `@pytest.mark.slow` and database-bound ones with `@pytest.mark.integration`; developers can opt out via `pytest -m "not slow"`. Use `pytest --cov src/pgdbm --cov-report=term-missing` to maintain visibility into coverage and prevent regressions. Integration suites expect PostgreSQL 12+; configure credentials with `TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`, and `TEST_DB_PASSWORD`.

## Library Integration Patterns
Modules should support both standalone and embedded usage. Accept either a connection string or an injected `AsyncDatabaseManager`, always run module-specific migrations with a unique `module_name`, and reference tables via the `{{tables.*}}` template so SQL adapts to schema prefixes. In shared-pool mode, schema isolation happens when queries are prepared (string substitution), not via `search_path`, so every statement must use the template helpers. Parent applications create a single shared pool and hand out schema-bound managers—`AsyncDatabaseManager(pool=shared_pool, schema="module")`—allowing multiple libraries to coexist without cross-table conflicts; library composition is cooperative, meaning the host app (or top-level library) is responsible for constructing managers for any nested modules it wires together.

## Commit & Pull Request Guidelines
Follow the Conventional Commits style already in history (`fix:`, `docs:`, `chore:`) with imperative subjects under 72 characters and focused diffs. Each PR should include a concise summary, reference related issues, and call out schema or API impacts. Attach test evidence such as `pytest` output or coverage summaries, and update docs or examples whenever behaviour changes. Screenshots or logs are helpful when showcasing CLI output or migration results.

# Agent Instructions (dispatcher)

This repo uses `bdh` (BeadHub) for coordination and issue tracking.

Keep this file stable and minimal: the active project policy (invariants + role playbooks) lives on the server and is shown via `bdh :policy`.

## Start Here (Every Session)

```bash
bdh :status                 # who am I? (alias/workspace/role) + team status
bdh :inbox --json           # check mail
bdh :policy                 # invariants + your role playbook
bdh ready --json            # find unblocked work
```

If `bdh :policy` isn’t available in your installed `bdh` yet, build and use the repo version:

```bash
make bdh
./bdh/bdh :policy
```

## Minimal Rules

- Use `bdh` (not `bd`) so work is coordinated and synced.
- Default to mail (`bdh :send`) for coordination; use chat (`bdh :chat`) only when blocked/urgent.
- Respond immediately to WAITING notifications — someone is blocked.
- Don’t overwrite other agents’ work without coordinating first.

## Critical: don’t impersonate another workspace

`bdh` derives your identity from the `.beadhub` file in the current worktree.

- Only run `bdh` from the worktree that contains **your** `.beadhub`.
- If you `cd` into another worktree/repo and run `bdh`, you may impersonate that workspace’s agent.

## Auth / tenant scoping (security)

When auth is enabled, BeadHub APIs are project-scoped via `X-Project-ID` (not `project_slug`). Ensure your `.beadhub` has a valid `project_id` (re-run `bdh :init` if needed).

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bdh sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
