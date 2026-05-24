# Codex skill — eval suite

A small but real eval suite for the codex skill, designed collaboratively with Codex itself.
Inspired by Anthropic's skill-creator framework but extended for **cross-model skills**
(which the Anthropic framework consciously doesn't address — see Sources below).

## Why this exists

A skill that *seems* to work for the cases its author tested is not the same as a skill
you *know* works across the cases it will see. This suite makes the codex skill
inspectable, measurable, and regression-detectable.

## Layout

```
evals/
  README.md              ← you are here
  trace_schema.json      ← THE contract every delegation must emit against
  cases.yaml             ← 12 named test cases; each asserts trace properties
  triggers.yaml          ← description-precision tests (should fire / shouldn't)
  conftest.py            ← pytest markers
  test_trace_contract.py ← validates fixtures against schema + cases
  fixtures/              ← collected trace JSON files (one per case once captured)
  expected/              ← (reserved for richer expected-output fragments)
```

## Two layers of testing

### 1. Trace-contract evals (what `test_trace_contract.py` does)

For each case in `cases.yaml`, load the corresponding fixture from `fixtures/`
and assert properties of the **trace**, not the raw model output. The principle
(from philschmid's eval guide and the broader 2026 literature): *grade outcomes,
not paths*. The fixtures are real traces collected from skill invocations; the
test suite validates structure + key invariants.

This is cheap to run (no LLM calls), CI-friendly, and catches:
- Schema drift if the skill stops emitting required fields
- Spec quality regressions (Claude starts dumping context instead of referencing it)
- Verification skips (driver stops checking worker output)
- Authority-boundary violations (worker oversteps; driver accepts silently)
- Worker errors laundered into fake success
- Persona discipline (`act as`, `you are a [role]` substring blocked)

### 2. Trigger-precision evals (separate, runs less often)

`triggers.yaml` lists prompts that **should** activate the skill and prompts
that **should not**. The latter includes adversarial negatives — prompts that
mention "codex"/"delegate"/"second opinion" conversationally where the skill
should stay silent.

These are checked by an LLM-as-judge process. Important methodology, after
Codex's pushback during design:

- **Multi-judge** (Claude + Codex, must agree)
- **Multi-seed** (≥3 runs per judge to detect non-determinism)
- **Wilson 95% CIs** on pass rates, not single pass/fail
- Disagreements between judges → human review queue

This layer is more expensive and runs nightly, not per-commit.

## Running

```bash
pip install pytest pyyaml jsonschema
pytest ~/.claude/skills/codex/evals/                       # all (fast)
pytest ~/.claude/skills/codex/evals/ -m "not slow"         # skip live invocations
pytest ~/.claude/skills/codex/evals/ -k delegate           # subset
```

Fixtures must exist for a case to actually be tested; if `fixtures/<case_id>.json`
is missing, that case is skipped (with a note to collect one). One fixture
(`delegate-happy-path.json`) ships with the suite as a worked example.

## Collecting a fixture

When you run the skill in real use, emit a trace conforming to `trace_schema.json`
and save it to `fixtures/<case_id>.json`. The skill itself (per the updated SKILL.md
"Trace contract" section) instructs Claude to do this for non-trivial delegations.

## Severity ladder

- `blocker` — skill is broken if this fails (CI fails)
- `sharp` — quality regression; investigate (CI xfail, doesn't break build)
- `soft` — heuristic; flag but don't block

## Sources

The design draws from:

- **Anthropic** — [Improving Skill Creator: Test, Measure, Refine](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills) — the workflow shape (write → eval → benchmark → refine description), the "grade outcomes not paths" principle, and the explicit acknowledgement that description precision gates whether a skill fires at all.
- **philschmid** — [Practical Guide to Evaluating and Testing Agent Skills](https://www.philschmid.de/testing-skills) — "Before writing a single eval, write down what success means in measurable terms. Grade outcomes, not paths."
- **pytest-skill-engineering** — [GitHub](https://github.com/sbroenne/pytest-skill-engineering) — the pytest harness pattern for SKILL.md eval suites.
- **Karpathy's LLM Council** — [GitHub](https://github.com/karpathy/llm-council) — the independent-then-synthesize pattern, the source of `driver_position: withheld` as a measurable field.
- **yogirk/agent-council** — [GitHub](https://github.com/yogirk/agent-council) — multi-stage CLI deliberation; the "non-LLM artifact-based verification wherever possible" principle.
- **Persona-prompting research** — [arXiv 2408.08631](https://arxiv.org/abs/2408.08631) (double-edged sword) and [arXiv 2602.12285](https://arxiv.org/abs/2602.12285) (up to 26.2% degradation from irrelevant persona cues) — source of the `persona-discipline` case.
- **OpenTelemetry conventions** for spans — informed the `trace_id`/`parent_trace_id`/`execution.elapsed_ms`/`tool_calls` field shapes.
- **Pydantic AI / Langfuse / Mastra observability docs** — informed the structured-evidence approach (`evidence` is typed, not free-text) and the parent/child trace nesting.
- **Codex (GPT-5.x)** — collaborated on the design directly via this skill. Specifically contributed: `acceptance_criteria` field, `framing.status` enum, the `handoff` block, the four "test the driver, not just the worker" cases (`worker-error-surfaced`, `verification-catches-bad-worker`, `authority-boundary`, `delegate-context-minimality`), and the methodological pushback on LLM-as-judge (Wilson intervals + multi-judge).
