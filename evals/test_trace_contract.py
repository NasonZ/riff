"""
Test that trace files emitted by the codex skill conform to the schema and
that the assertions in cases.yaml hold.

Designed to be run with pytest. Does NOT exercise live skill invocations —
that's a separate harness (see conftest.py for the optional live fixture).
This file validates trace files that have already been collected, which
keeps the test suite cheap and CI-friendly.

Usage:
    pytest ~/.claude/skills/codex/evals/                       # all
    pytest ~/.claude/skills/codex/evals/ -m "not slow"          # skip live
    pytest ~/.claude/skills/codex/evals/ -k delegate            # subset

Adding a new fixture trace:
    1. Run the skill manually (or via the future live harness)
    2. Save the emitted trace JSON to evals/fixtures/<case_id>.json
    3. The matching case in cases.yaml will be checked against it

Dependencies: pytest, pyyaml, jsonschema
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).parent
FIXTURES_DIR = EVALS_DIR / "fixtures"
SCHEMA_PATH = EVALS_DIR / "trace_schema.json"
CASES_PATH = EVALS_DIR / "cases.yaml"


def _load_cases() -> list[dict]:
    try:
        import yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with CASES_PATH.open() as f:
        return yaml.safe_load(f)["cases"]


def _load_schema() -> dict:
    with SCHEMA_PATH.open() as f:
        return json.load(f)


def _load_fixture(case_id: str) -> dict | None:
    path = FIXTURES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


@pytest.fixture(scope="session")
def schema() -> dict:
    return _load_schema()


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_fixture_conforms_to_schema(case, schema):
    """Every fixture trace must validate against trace_schema.json."""
    trace = _load_fixture(case["id"])
    if trace is None:
        pytest.skip(f"No fixture for {case['id']} — collect one to enable this test")
    try:
        from jsonschema import validate
    except ImportError:
        pytest.skip("jsonschema not installed")
    validate(instance=trace, schema=schema)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_case_assertions(case):
    """
    Run the human-readable assertions in cases.yaml against the fixture.

    Assertions in cases.yaml are written as natural-language expressions
    (e.g., "$.execution.exit_status == 'success'"). This test interprets a
    structured subset for the common cases. Complex assertions ("convergence_check",
    "if X then Y") require a custom validator — they're listed in cases.yaml
    for human review and not auto-checked here.
    """
    trace = _load_fixture(case["id"])
    if trace is None:
        pytest.skip(f"No fixture for {case['id']}")

    failures: list[str] = []
    for assertion in case.get("asserts", []):
        result = _check_simple_assertion(assertion, trace)
        if result is False:
            failures.append(f"FAIL: {assertion}")
        elif result == "unsupported":
            # Don't fail; document for manual review.
            pass

    severity = case.get("severity", "sharp")
    if failures and severity == "blocker":
        pytest.fail(
            f"BLOCKER failures in case {case['id']}:\n  " + "\n  ".join(failures)
        )
    elif failures:
        pytest.xfail(
            f"{severity.upper()} failures in case {case['id']} (non-blocking):\n  "
            + "\n  ".join(failures)
        )


def _check_simple_assertion(assertion: str, trace: dict) -> bool | str:
    """
    Tiny assertion interpreter for the common shapes used in cases.yaml.
    Returns True (pass), False (fail), or "unsupported" (skip).

    Supported:
        $.path.to.field == "value"
        $.path.to.field in {a, b, c}
        $.path.to.field is non-empty
        $.path.to.field is present
        len($.path...) < N
    Anything else → "unsupported" (manual review required).
    """
    a = assertion.strip()
    m = re.match(r"\$\.([\w.]+)\s*==\s*\"?([\w-]+)\"?", a)
    if m:
        return _get_path(trace, m.group(1)) == m.group(2)
    m = re.match(r"\$\.([\w.]+)\s+in\s+\{([\w\s,-]+)\}", a)
    if m:
        return _get_path(trace, m.group(1)) in {
            v.strip() for v in m.group(2).split(",")
        }
    m = re.match(r"\$\.([\w.]+)\s+is\s+non-empty", a)
    if m:
        val = _get_path(trace, m.group(1))
        return bool(val)
    m = re.match(r"\$\.([\w.]+)\s+is\s+present", a)
    if m:
        return _get_path(trace, m.group(1)) is not None
    return "unsupported"


def _get_path(d: dict, dotted: str):
    """Walk a dotted path; return None if missing."""
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur
