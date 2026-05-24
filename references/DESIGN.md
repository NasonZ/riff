# Codex skill — design

Reference doc for the codex skill at `~/.claude/skills/codex/`. For the journey that produced this design — what we tried, what changed, what's still open — see `./NOTES.md`. For operational guidance to Claude, see `../SKILL.md`. For the eval suite, see `../evals/README.md`.

## What this skill is

A Claude Code skill teaching Claude (Opus 4.x) how to collaborate with OpenAI Codex CLI (GPT-5.x) as a peer agent on coding *and* non-coding problems. Supports three modes — **delegate** (hand off a task), **consult** (one-shot second opinion), **roundtable** (multi-round back-and-forth) — across two transports: the official `codex` MCP server (preferred) and the `codex exec` CLI (fallback).

What it is **not**: a full N-model council (anonymous peer review breaks down at N=2), a coding-only tool, or a master/worker abstraction that positions Claude above Codex.

## The dyad, not the council

By May 2026 several multi-LLM deliberation projects had shipped (Karpathy's LLM Council, Agent Council, Council of High Intelligence, Perplexity Model Council). They operate on N≥3 models with anonymous peer review and a "Chairman LLM" synthesis, and report ~2× consideration coverage vs single-agent — at the cost of latency, token spend, and orchestration complexity.

We picked the **dyad** (just two agents) consciously:

- Lower orchestration cost and faster feedback loop.
- Two models with different priors can surface issues one model would miss.
- Anonymous peer review (the council's defining mechanism) requires N≥3. The dyad gets the *Independent-first* technique instead — ask the question first, share your view only after — which captures most of the anchoring-avoidance benefit.

The trade-off: we lose the council's robustness against any single model's blind spots. The dyad inherits the union of Claude's and Codex's blind spots, not the intersection.

## Three modes, three different shapes of work

| Mode | Shape | Stop signal | Primary use |
|---|---|---|---|
| **delegate** | Driver/worker — Claude plans, Codex executes a contracted task, Claude verifies | Worker emits artifact, driver verifies and integrates | Long-running analysis, codebase walks, multi-file refactors |
| **consult** | One round — share a question, get an independent take | Single response, then Claude synthesizes | Stuck on a bug, design choice, "am I missing something" |
| **roundtable** | Multi-round back-and-forth | Mode-dependent (see below) | Contested decisions, design philosophy, ethics, strategy |

The roundtable has **three sub-modes** internally because one stop-signal mechanism does not fit all back-and-forth:

- **A — Convergence** (concrete decision X or Y): JSON-schema-enforced output with `status: CONSENSUS|CONTINUE` enum. No suffix parsing. Suits concrete decisions where the output bucketizes cleanly.
- **B — Critique** (concrete artifact, no binary vote): text marker (`CONSENSUS:` / `CONTINUE:`), free prose both ways. Schema would force artificial flatness on a discussion that naturally interleaves observation + question + counter-proposal.
- **C — Exploration** (abstract, no decision): no stop signal. User decides when it's done. Includes guidance to redirect Codex if its critique reflex persists past usefulness.

## Architectural decisions and why

### Trace contract as the unit of observability

Cross-model skills fail at the handoff (driver/worker contract) more often than at raw answer generation. Anthropic's skill-creator framework checks if a skill *fires* and what it *outputs*; it doesn't inspect what was *sent* to a second model, whether constraints survived translation, whether the driver verified, whether the worker pushed back on the framing.

So every non-trivial invocation emits a JSON trace conforming to `evals/trace_schema.json`. The trace — not the raw model output — is what gets eval'd. Fields are partitioned into:

- `request` (the contract Claude gave Codex — including `driver_position: withheld|provided|none` for independent-first measurement, `context_refs` not pasted context, `context_digest` for drift detection, `acceptance_criteria` committed up-front)
- `execution` (observability — OTel-shaped: `elapsed_ms`, `exit_status`, `error_type`, `tool_calls`)
- `response` (artifact + structured `evidence` typed by kind + `framing.status` enum for reframe-detection)
- `verification` (`verifier` enum + list of `checks` with results)
- `handoff` (did the driver actually integrate? did it modify the output? what did it change?)
- `outcome` (terminal disposition: `accepted` / `reframed` / `retried` / `abandoned`)

The schema deliberately drops some "obvious" fields (`confidence`, free-text `reframed_question`) because they're noise without calibration.

### Eval suite over collected traces, not live invocations

The eval suite at `evals/` validates fixtures (collected trace JSON) against the schema and case-specific assertions. It does **not** invoke the live skill on every CI run.

Why: live invocations are expensive (LLM tokens), slow (seconds per case), and non-deterministic (LLM outputs vary across runs). A fast, deterministic suite over collected traces catches regressions in skill behavior as long as traces accumulate from real use. Live regression runs happen on a slower cadence (marked `-m slow` for the future live harness, not yet shipped).

This trade-off mirrors the difference between unit tests (cheap, deterministic, run constantly) and integration tests (expensive, less deterministic, run on a slower cadence).

### Twelve cases with a severity ladder

Eight cases would be the lazy floor; twenty would be over-engineered for a v1. Twelve hits the right shape:

- 7 delegation cases (the original purpose of the skill — getting these right matters most)
- 1 consult, 2 roundtable, 1 transport, 1 discipline

Severity ladder: `blocker` (CI fails) / `sharp` (xfail, visible but non-blocking) / `soft` (warn only). Prevents the suite from becoming all-or-nothing.

Four of the cases are explicitly **driver-side** failures (`verification-catches-bad-worker`, `worker-error-surfaced`, `authority-boundary`, `delegate-context-minimality`). These exist because, per Codex's own pushback during design, "Cross-model skills fail at the handoff and integration layer more often than at raw answer generation." Testing the worker without testing the driver gives false confidence.

### Trigger precision tests separated from the main suite

`evals/triggers.yaml` lists prompts that should/shouldn't activate the skill. Description precision gates whether the skill fires at all — Anthropic's own skill-creator improved triggering on 5/6 skills after this kind of testing.

The trigger suite runs separately (slower cadence) because it's LLM-as-judge — which has known bias issues. Mitigations:
- Multi-judge (Claude + Codex, must agree)
- Multi-seed (≥3 runs per judge)
- Wilson 95% CIs on pass rates, not single pass/fail
- Adversarial negatives — prompts that mention "codex"/"delegate" conversationally where the skill should stay silent
- Disagreements → human review queue, not auto-resolved

### No persona prompts by default

The cited 2026 papers argue against default persona prompting. Performance can degrade up to ~26% on agentic benchmarks from task-irrelevant persona cues (arXiv 2602.12285); rationale quality drops even when surface accuracy improves (arXiv 2408.08631).

The skill defaults to no persona. Task-specific attention direction ("focus on race conditions in `chat()`") is acceptable and isn't really a persona — it's a focused question. Personality role-play ("act as Aristotle", "be a senior engineer") is explicitly discouraged and enforced at the eval layer via the `persona-discipline` case (regex against the actual prompt sent to Codex).

### Treat Codex as a peer

Codex's strengths may overlap with or exceed Claude's on any given problem. Direction of insight isn't predetermined. The driver/worker role in delegate mode is a coordination convenience, not a capability ranking.

This shows up in concrete places:
- The trace's `framing.status` enum has `challenged` and `rejected` as valid worker responses — the worker can reject the driver's question framing
- The delegate workflow treats worker push-back as signal, not noise
- The "Welcome reframing" technique invites Codex to push back on the question rather than answer it
- The SKILL.md avoids wording that assumes Claude's frame is the primary one

## What's open / future work

- **No live harness yet.** `test_trace_contract.py` validates fixtures; the loop that produces fixtures by invoking the live skill end-to-end (with seeded scenarios for the four worker-failure cases) isn't built. Until it exists, those four cases — the blockers — are aspirational.
- **Only one fixture shipped.** `fixtures/delegate-happy-path.json` is a hand-authored worked example. Real fixtures accumulate as the skill gets used; the SKILL.md instructs Claude to emit traces during real work.
- **Complex assertions are unsupported.** The interpreter in `test_trace_contract.py` handles `==`, `in {...}`, `is non-empty`, `is present`. Things like `convergence_check: same_recommendation_last_2_rounds` are documented in `cases.yaml` for human review but not auto-checked yet.
- **No trigger-suite implementation.** `triggers.yaml` defines the cases; the multi-judge runner with Wilson intervals isn't built.
- **MCP `threadId` location.** Documented as top-level on Codex v0.133+ (verified live). Older client docs say `structuredContent.threadId`. Watch for this if the MCP protocol shifts.
- **No memory of past delegations across sessions.** Each session starts fresh. Codex has its own thread persistence; Claude doesn't currently use it to remember "I delegated this kind of task last week and it failed for X reason." Could be added by indexing collected traces.

## Cross-references

- `../SKILL.md` — what Claude reads to do the work
- `../evals/README.md` — eval suite operational doc, with run instructions
- `../evals/trace_schema.json` — the schema itself (annotated with `description` fields)
- `../evals/cases.yaml` — the 12 eval cases with assertions
- `../evals/triggers.yaml` — description-precision tests
- `./NOTES.md` — the journey, the research landscape, what was tried that didn't ship
