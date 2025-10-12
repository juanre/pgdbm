"""Tests for pgdbm CLI functionality."""

import subprocess
import sys
from pathlib import Path

import pytest


def test_cli_requires_click():
    """Test that CLI is only available when click is installed."""
    # This test runs with click installed (it's in dev dependencies)
    # We just verify the import works
    try:
        from pgdbm.cli import main

        assert main is not None
    except ImportError:
        pytest.skip("CLI not available (click not installed)")


def test_cli_help():
    """Test that CLI help works."""
    result = subprocess.run(
        [sys.executable, "-m", "pgdbm.cli.main", "--help"], capture_output=True, text=True
    )

    # Should succeed and show help
    assert result.returncode == 0
    assert "pgdbm - PostgreSQL Database Manager CLI" in result.stdout
    assert "Database management commands" in result.stdout


def test_cli_version():
    """Test that CLI version command works."""
    result = subprocess.run(
        [sys.executable, "-m", "pgdbm.cli.main", "--version"], capture_output=True, text=True
    )

    # Should show version
    assert result.returncode == 0
    assert "pgdbm, version" in result.stdout


def test_cli_generate_config_dry_run(tmp_path):
    """Test config generation in a temp directory."""
    # Change to temp directory
    original_cwd = Path.cwd()

    try:
        # Use tmp_path for test
        import os

        os.chdir(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "pgdbm.cli.main", "generate", "config"],
            capture_output=True,
            text=True,
        )

        # Should create pgdbm.toml
        assert result.returncode == 0
        assert (tmp_path / "pgdbm.toml").exists()

        # Check content
        content = (tmp_path / "pgdbm.toml").read_text()
        assert "[project]" in content
        assert "[environments.dev]" in content

    finally:
        os.chdir(original_cwd)


def test_cli_subcommands():
    """Test that all main subcommands are available."""
    subcommands = ["db", "migrate", "schema", "dev", "generate"]

    for cmd in subcommands:
        result = subprocess.run(
            [sys.executable, "-m", "pgdbm.cli.main", cmd, "--help"], capture_output=True, text=True
        )

        # Each subcommand should have help
        assert result.returncode == 0, f"Failed for command: {cmd}"
        assert "--help" in result.stdout
