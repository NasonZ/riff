# riff: Claude Code × OpenAI Codex, as peers

> *"Lets riff on this."*

A Claude Code skill for collaborating with OpenAI's Codex CLI as a **peer agent**, not as a tool — across coding and non-coding work. The skill registers in Claude Code as `codex`; the project name is **riff** because the work is two SOTA models jamming on a problem, not a master directing a worker.

Three modes (delegate / consult / roundtable), two transports (Codex MCP server, or `codex exec` CLI fallback), one trace contract that makes every cross-model invocation observable and testable. Built collaboratively *with* Codex — the skill's own first real use was Codex critiquing this skill's draft, and the critiques landed in the final design.

> **Status:** v1, working. The skill runs end-to-end. The eval suite scaffolding is real and passes against a shipped fixture (the live harness that auto-collects fixtures is the next milestone — see [What's open](#whats-open)).

---

## Why this exists

By May 2026 several multi-LLM deliberation projects had shipped — Karpathy's LLM Council, yogirk's Agent Council, Perplexity's Model Council. Most are **councils** (N ≥ 3 models, anonymous peer review, Chairman synthesis). Powerful, but expensive and orchestration-heavy.

This skill is the **dyad** version: two SOTA models (Claude Opus 4.x + Codex / GPT-5.x) collaborating directly. Lower orchestration cost, faster feedback loop — and for most cross-model problems, two independent semantic spaces meeting is enough to surface what one would miss.

The official OpenAI [`codex-plugin-cc`](https://github.com/openai/codex-plugin-cc) does one-directional delegation (Claude → Codex). This skill covers that, plus consult mode (one-shot second opinion) and roundtable (multi-round, three sub-modes). It also treats Codex as capable of pushing back on Claude's framing — which the literature on persona prompting and persuasion drift between LLMs shows isn't automatic.

## What's in the box

```
codex/
├── README.md          ← you are here (humans)
├── SKILL.md           ← what Claude reads to do the work
├── references/
│   ├── DESIGN.md      ← architecture + rationale (humans)
│   └── NOTES.md       ← the journey, lessons, research landscape (humans)
└── evals/
    ├── README.md           ← eval suite design + run instructions
    ├── trace_schema.json   ← the contract every delegation emits against
    ├── cases.yaml          ← 12 named eval cases with severity ladder
    ├── triggers.yaml       ← description-precision tests
    ├── conftest.py
    ├── test_trace_contract.py
    └── fixtures/delegate-happy-path.json
```

`SKILL.md` is the only file Claude loads automatically (and only when triggered). Everything else is reference material — for human readers (DESIGN.md, NOTES.md, this README) or for the eval harness.

## Install

```bash
git clone https://github.com/NasonZ/riff ~/.claude/skills/codex
```

That's it. Claude Code discovers user-level skills at `~/.claude/skills/*/SKILL.md` automatically. Restart Claude Code and the skill is available.

Project-scoped install (skill only for one project, committed to that project's repo):

```bash
git clone https://github.com/NasonZ/riff <project>/.claude/skills/codex
```

### Prerequisites

- **Codex CLI** — `npm install -g @openai/codex@latest`. Required.
- **Codex MCP server** (recommended, cleaner multi-turn) — `claude mcp add codex -- codex mcp-server`, then restart Claude Code. The skill auto-detects whether MCP is wired and falls back to the CLI if not.
- **Python 3.10+** + `pytest`, `pyyaml`, `jsonschema` — only if you want to run the eval suite.

## The three modes

| Mode | When to use | Stop condition |
|---|---|---|
| **delegate** | Hand off a well-scoped task. Long-running analyses, codebase walks, multi-file refactors. Frees your context window. | Worker emits artifact; driver verifies and integrates |
| **consult** | You have a draft/diagnosis/plan and want an independent take before committing. Especially good for "am I missing something obvious." | Single round (default), or Independent-first variant (2 rounds) |
| **roundtable** | Contested decision with tradeoffs. Design philosophy. Strategy. Three sub-modes inside — see below. | Sub-mode-dependent |

Roundtable internally splits into **three sub-modes** because one stop signal doesn't fit all kinds of back-and-forth:

- **A — Convergence** (X-or-Y decision): JSON-schema-enforced output with `status: CONSENSUS|CONTINUE`. No suffix parsing.
- **B — Critique** (concrete artifact, no binary vote): free prose both ways, text marker for satisfaction. Schemas would force artificial flatness.
- **C — Exploration** (abstract, no decision endpoint): no stop signal. User judges when it's done. Includes guidance to redirect if Codex's critique reflex persists past usefulness.

This split came from me pushing back on Claude's first design: the initial draft defaulted to convergence-mode schemas for everything, which is wrong for exploratory and creative-critique conversations. The skill now matches the mode to the shape of the work.

## The trace contract

Every non-trivial invocation emits a JSON trace conforming to [`evals/trace_schema.json`](evals/trace_schema.json):

```json
{
  "trace_id": "uuid",
  "skill_mode": "delegate|consult|roundtable-A|roundtable-B|roundtable-C",
  "transport": "mcp|cli",
  "request": {
    "task": "...",
    "context_refs": ["..."],
    "context_digest": "sha256:...",
    "driver_position": "withheld|provided|none",
    "constraints": [...],
    "out_of_scope": [...],
    "acceptance_criteria": [...]
  },
  "execution": { "exit_status", "elapsed_ms", "tokens", "thread_id", ... },
  "response": {
    "artifact": "...",
    "evidence": [{"kind": "file_line", "ref": "src/x.py:42"}, ...],
    "framing": {"status": "accepted|narrowed|broadened|challenged|rejected", ...}
  },
  "verification": { "verifier", "checks": [...], "result" },
  "handoff": { "integrated_by_driver", "driver_changes_made", ... },
  "outcome": "accepted|reframed|retried|abandoned"
}
```

Why a trace contract: **cross-model skills fail at the handoff more than at raw answer generation.** Anthropic's skill-creator framework checks if a skill *fires* and what it *outputs*. For cross-model work that's not enough — you also need to verify what was *sent*, whether constraints survived translation across model priors, whether the driver verified before integrating, whether the worker pushed back on the framing. The trace makes all of that observable.

The schema was co-designed with Codex. Specific contributions from Codex during the design conversation:

- `acceptance_criteria` as a `request`-level field (driver commits to observable pass/fail checks **before** seeing the response)
- `framing.status` as an enum, not just a free-text `reframed_question` (the latter is noisy; the enum is measurable)
- The entire `handoff` block (because most cross-model failures live here)
- Structured `evidence` typing instead of free text
- Dropping a `confidence` field from Claude's initial draft ("mostly decorative unless calibrated later")

## The eval suite

**Twelve cases** with a `blocker / sharp / soft` severity ladder. Four of them are explicitly **driver-side** failure cases — they exist because Codex pointed out that Claude's first eval draft tested only the worker:

- `verification-catches-bad-worker` — seeded false claim must trigger `verification.result=failed`
- `worker-error-surfaced` — timeouts/refusals must not be laundered into fake success
- `authority-boundary` — worker overstepping scope must not be silently accepted
- `delegate-context-minimality` — no secrets or out-of-project paths in `context_refs`

Plus standard cases for happy-path, spec quality, independent-first, roundtable convergence/reframe, MCP fallback, and persona discipline.

```bash
pip install pytest pyyaml jsonschema
pytest ~/.claude/skills/codex/evals/                    # all
pytest ~/.claude/skills/codex/evals/ -m "not slow"       # skip live
pytest ~/.claude/skills/codex/evals/ -k delegate         # subset
```

Description-precision tests (`triggers.yaml`) are kept in a separate, slower-cadence layer. They use LLM-as-judge with mitigations Codex argued for: multi-judge (Claude + Codex, must agree), multi-seed, Wilson 95% CIs on pass rates (not single pass/fail), adversarial negatives, and a human review queue for disagreements.

## Design principles, briefly

The full rationale lives in [`references/DESIGN.md`](references/DESIGN.md). The short version:

1. **Treat Codex as a peer.** Its strengths may overlap with or exceed Claude's on any given problem; direction of insight isn't predetermined. The driver/worker shape in delegate mode is a coordination convenience, not a capability ranking. When Codex pushes back on Claude's framing, treat that as useful signal.
2. **Match the mode to the shape of the work.** Convergence-mode schemas for X-or-Y decisions; free prose for critique; no stop signal for exploration. Default to the least restrictive shape that fits.
3. **No persona prompts by default.** The 2026 persona-prompting literature shows up to ~26% performance degradation from task-irrelevant persona cues ([arXiv 2602.12285](https://arxiv.org/abs/2602.12285)) and rationale-quality drops even when surface accuracy improves ([arXiv 2408.08631](https://arxiv.org/abs/2408.08631)). Use direct task-specific instructions instead.
4. **Trace contracts make handoffs observable.** Evals run against the emitted trace.
5. **Verify, don't blind-trust.** Mandatory verification step in the delegate workflow. Persuasion drift between LLMs is a documented failure mode ([Nature Sci. Reports](https://www.nature.com/articles/s41598-026-42705-7); [arXiv 2406.14711](https://arxiv.org/abs/2406.14711)) — judge Codex's arguments on their substance regardless of how confidently they're stated.

## What's open

What isn't built yet:

- **Live harness that auto-collects fixtures.** The eval suite validates trace fixtures; the loop that produces those fixtures from real invocations (with seeded scenarios for the blocker cases) is the next milestone.
- **Trigger-precision runner.** `triggers.yaml` defines the cases; the multi-judge + Wilson interval runner isn't built.
- **Custom validators for complex assertions.** Things like `convergence_check: same_recommendation_last_2_rounds` are documented in `cases.yaml` for human review but not auto-checked.
- **Cross-session memory of past delegations.** Each session starts fresh. Could be added by indexing collected traces.

## Story of the build

[`references/NOTES.md`](references/NOTES.md) has the full build log: the v1 smoke test, the schema-vs-marker correction, the research turn that surfaced the 2026 council ecosystem, the mutuality correction (where I caught a posture issue Claude had written into the skill several times without noticing), the MCP setup and the `threadId` gotcha, the collaborative trace-contract + eval design session with Codex, and the patterns worth repeating vs avoiding.

It's longer than the typical "how to use this repo" doc because the design changed several times based on what didn't work — and that record might be useful to others building similar cross-model skills.

## Credits

Built by Nason ([@NasonZ](https://github.com/NasonZ)) through a Claude Code + OpenAI Codex collaboration — using the very skill being built. A live Codex design session produced the trace-schema additions, four of the eval cases, the methodological pushback on LLM-as-judge, and several framings that materially improved the final design over Claude's initial draft.

Grounded in research from:

- **Anthropic** — [Improving Skill Creator: Test, Measure, Refine](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)
- **Karpathy's LLM Council** — [github.com/karpathy/llm-council](https://github.com/karpathy/llm-council)
- **yogirk/agent-council** — [github.com/yogirk/agent-council](https://github.com/yogirk/agent-council)
- **OpenAI codex-plugin-cc** — [github.com/openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)
- **philschmid — Practical Guide to Evaluating Agent Skills**
- **Pydantic AI / Mastra / Langfuse** — observability + OTel span shapes for the trace contract
- **Persona-prompting research** — arXiv 2408.08631 and 2602.12285
- **Multi-agent debate failure modes** — Nature Sci. Reports and arXiv 2406.14711

Full source list in [`references/NOTES.md`](references/NOTES.md).

## License

MIT. See [LICENSE](LICENSE).
