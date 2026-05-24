"""
pytest configuration for the codex skill eval suite.

Defines markers so individual eval types can be skipped:
    -m "not slow"   skips live invocations
    -m "mcp"        only runs MCP-transport tests
    -m "cli"        only runs CLI-transport tests
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: tests that invoke the live skill")
    config.addinivalue_line("markers", "mcp: tests specific to MCP transport")
    config.addinivalue_line("markers", "cli: tests specific to CLI transport")
    config.addinivalue_line("markers", "trigger: description-precision tests")
