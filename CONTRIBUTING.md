# Contributing to pgdbm

First off, thank you for considering contributing to pgdbm! It's people like you that make pgdbm such a great tool.

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [conduct@pgdbm.org](mailto:conduct@pgdbm.org).

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

* **Use a clear and descriptive title** for the issue to identify the problem
* **Describe the exact steps which reproduce the problem** in as many details as possible
* **Provide specific examples to demonstrate the steps**
* **Describe the behavior you observed after following the steps**
* **Explain which behavior you expected to see instead and why**
* **Include details about your configuration and environment**

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

* **Use a clear and descriptive title** for the issue to identify the suggestion
* **Provide a step-by-step description of the suggested enhancement**
* **Provide specific examples to demonstrate the steps**
* **Describe the current behavior** and **explain which behavior you expected to see instead**
* **Explain why this enhancement would be useful**

### Pull Requests

* Fill in the required template
* Do not include issue numbers in the PR title
* Include screenshots and animated GIFs in your pull request whenever possible
* Follow the Python style guides
* Include thoughtfully-worded, well-structured tests
* Document new code
* End all files with a newline

## Development Setup

### Prerequisites

- Python 3.9 or higher
- PostgreSQL 12 or higher
- uv (recommended) or pip

### Setting Up Your Development Environment

1. Fork and clone the repository:
```bash
git clone https://github.com/yourusername/pgdbm.git
cd pgdbm
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies with uv:
```bash
uv pip install -e ".[dev]"
```

Or with pip:
```bash
pip install -e ".[dev]"
```

4. Set up pre-commit hooks:
```bash
pre-commit install
```

5. Create a test database:
```bash
createdb pgdbm_test
```

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=pgdbm --cov-report=html
```

Run specific test file:
```bash
pytest tests/test_core.py
```

Run with verbose output:
```bash
pytest -v
```

### Code Style

We use several tools to maintain code quality:

- **Black** for code formatting
- **Ruff** for linting
- **mypy** for type checking

Run all checks:
```bash
# Format code
black src tests

# Run linter
ruff check src tests

# Type checking
mypy src
```

Or use pre-commit to run all checks:
```bash
pre-commit run --all-files
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files with `test_` prefix
- Use descriptive test names that explain what is being tested
- Use fixtures for common setup
- Aim for at least 80% code coverage

Example test:
```python
async def test_connection_retry(test_db_manager):
    """Test that connection retries work correctly."""
    # Arrange
    config = DatabaseConfig(
        host="invalid-host",
        retry_attempts=3,
        retry_delay=0.1
    )

    # Act & Assert
    with pytest.raises(ConnectionError) as exc_info:
        db = AsyncDatabaseManager(config)
        await db.connect()

    assert exc_info.value.attempts == 3
```

### Documentation

- Update documentation for any changed functionality
- Add docstrings to all public functions and classes
- Include code examples in docstrings
- Update the API reference if you add new public APIs

### Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

Example:
```
Add connection retry logic with exponential backoff

- Implement retry mechanism in AsyncDatabaseManager.connect()
- Add configuration options for retry behavior
- Include exponential backoff with configurable parameters
- Add tests for retry logic

Fixes #123
```

## Project Structure

```
pgdbm/
├── src/
│   └── pgdbm/
│       ├── __init__.py      # Package exports
│       ├── core.py          # Core database functionality
│       ├── migrations.py    # Migration management
│       ├── monitoring.py    # Performance monitoring
│       ├── testing.py       # Test utilities
│       ├── errors.py        # Custom exceptions
│       └── fixtures/        # Pytest fixtures
├── tests/
│   ├── test_core.py         # Core functionality tests
│   ├── test_migrations.py   # Migration tests
│   └── integration/         # Integration tests
├── docs/                    # Documentation
├── benchmarks/             # Performance benchmarks
└── examples/               # Example projects
```

## Release Process

1. Update version in `src/pgdbm/__init__.py`
2. Update CHANGELOG.md
3. Create a pull request with the version bump
4. After merging, create a GitHub release
5. The CI/CD pipeline will automatically publish to PyPI

## Getting Help

- Check the [documentation](https://pgdbm.readthedocs.io)
- Look through existing [issues](https://github.com/yourusername/pgdbm/issues)
- Ask questions in [discussions](https://github.com/yourusername/pgdbm/discussions)
- Reach out on [Discord](https://discord.gg/pgdbm)

## Recognition

Contributors will be recognized in the following ways:

- Added to the CONTRIBUTORS file
- Mentioned in release notes for significant contributions
- Given credit in the documentation for major features

Thank you for contributing to pgdbm! 🎉
