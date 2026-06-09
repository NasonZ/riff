# riff

A Claude Code skill for working with OpenAI's Codex CLI as a **peer**, not a tool, across coding and non-coding work. It registers in Claude Code as `codex`. The name **riff** is the point: two frontier models exploring a problem across both their semantic spaces, rather than one directing the other as a subordinate.

Three modes (delegate, consult, roundtable). Two transports (the Codex MCP server, or `codex exec` on the CLI as a fallback). One trace contract, so every cross-model invocation is inspectable and testable.

> **Status:** v1, works end to end. The eval scaffolding is real and passes against a shipped fixture. The live harness that auto-collects fixtures is the next thing to build (see [What's open](#whats-open)).

## Install

```bash
git clone https://github.com/NasonZ/riff ~/.claude/skills/codex
```

Claude Code picks up user-level skills from `~/.claude/skills/*/SKILL.md` on its own. Restart it and you're done. Want it scoped to a single project instead? Clone into `<project>/.claude/skills/codex`.

### Prerequisites

- **Codex CLI**, required: `npm install -g @openai/codex@latest`
- **Codex MCP server**, recommended for cleaner multi-turn: `claude mcp add codex -- codex mcp-server`, then restart Claude Code. The skill figures out whether MCP is wired up and falls back to the CLI if it isn't.
- **Python 3.10+** with `pytest`, `pyyaml`, `jsonschema`, only if you want to run the evals.

## Why a dyad and not a council

Most multi-LLM deliberation projects are councils: N ≥ 3 models, anonymous peer review, a chairman to synthesize. Karpathy's LLM Council, yogirk's Agent Council, Perplexity's Model Council. They're powerful, but the orchestration cost is high and it scales with N.

riff is the dyad. Two frontier models (Claude Opus 4.x and Codex / GPT-5.x) collaborating directly. Lower orchestration cost, a tighter feedback loop, and for most cross-model problems two independent semantic spaces meeting is enough to surface what either would miss on its own.

OpenAI's [`codex-plugin-cc`](https://github.com/openai/codex-plugin-cc) does one-directional delegation, Claude to Codex. riff covers that, plus consult (a one-shot independent read) and roundtable (multi-round, three sub-modes). It also treats Codex as able to reframe Claude's question, not just answer it, which the literature on persona drift and persuasion between LLMs says isn't automatic.

## The three modes

| Mode | When to use | Stop condition |
|---|---|---|
| **delegate** | Hand off a well-scoped task: long-running analyses, codebase walks, multi-file refactors. Frees your context window. | Worker emits an artifact; driver verifies and integrates |
| **consult** | You have a draft, diagnosis, or plan and want an independent read before committing. Good for "am I missing something obvious." | Single round by default, or independent-first (2 rounds) |
| **roundtable** | A contested decision with real tradeoffs: design philosophy, strategy, taxonomy. Three sub-modes, below. | Depends on the sub-mode |

Roundtable splits three ways because one stop signal doesn't fit every kind of back-and-forth:

- **A. Convergence** (an X-or-Y decision): JSON-schema-enforced output with `status: CONSENSUS|CONTINUE`. No suffix parsing.
- **B. Critique** (a concrete artifact, no binary vote): free prose both ways, with a text marker for "I'm satisfied." A schema here would just flatten things artificially.
- **C. Exploration** (abstract, no decision endpoint): no stop signal at all. You decide when it's done. There's guidance to redirect if Codex's critique reflex outlasts its usefulness.

## The trace contract

Every non-trivial call emits a JSON trace against [`evals/trace_schema.json`](evals/trace_schema.json):

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

Cross-model skills fail at the handoff more than at answer generation. Anthropic's skill-creator framework checks whether a skill *fires* and what it *outputs*. For cross-model work that's not enough. You also need what was *sent*, whether constraints survived translation across the other model's priors, whether the driver verified before integrating, and whether the worker pushed back on the framing or deferred to it. The trace makes all of that observable, and the evals run against it.

A few choices in the schema worth knowing about:

- `acceptance_criteria` lives at the `request` level, so the driver commits to observable pass/fail checks *before* it sees the response.
- `framing.status` is an enum rather than free text, because "the model reframed the question" is only useful if you can measure it.
- The `handoff` block is first-class, since that's where most cross-model failures actually happen.
- `evidence` is typed (`kind` + `ref`), not a blob of prose.
- There's no `confidence` field. It's decorative until it's calibrated, so it's gone.

## The eval suite

**Twelve cases** on a `blocker / sharp / soft` severity ladder. Four of them test the *driver*, not the worker, which is the part most eval setups skip:

- `verification-catches-bad-worker`: a seeded false claim has to trip `verification.result=failed`.
- `worker-error-surfaced`: timeouts and refusals can't get laundered into fake success.
- `authority-boundary`: a worker overstepping its scope can't be waved through silently.
- `delegate-context-minimality`: no secrets or out-of-project paths in `context_refs`.

The rest cover the happy path, spec quality, independent-first, roundtable convergence and reframing, MCP fallback, and persona discipline.

```bash
pip install pytest pyyaml jsonschema
pytest ~/.claude/skills/codex/evals/                 # all
pytest ~/.claude/skills/codex/evals/ -m "not slow"   # skip live
pytest ~/.claude/skills/codex/evals/ -k delegate     # a subset
```

The description-precision tests (`triggers.yaml`) sit in a separate, slower layer. They use LLM-as-judge, but with guardrails against its usual failure modes: two judges (Claude and Codex) that have to agree, multiple seeds, Wilson 95% intervals on pass rates instead of a single pass/fail, adversarial negatives, and a human queue for the disagreements.

## Design principles

Full rationale is in [`references/DESIGN.md`](references/DESIGN.md). Short version:

1. **Codex is a peer.** It can be sharper than Claude on any given problem, and which side the good idea comes from isn't decided up front. It's a two-way street. The driver/worker split in delegate mode is just coordination, not a ranking.
2. **Match the mode to the shape of the work.** Schemas for X-or-Y calls, free prose for critique, no stop signal for open exploration. Default to the loosest shape that still fits.
3. **No persona prompts by default.** The 2026 research shows up to ~26% performance drop from task-irrelevant persona cues ([arXiv 2602.12285](https://arxiv.org/abs/2602.12285)), and rationale quality slips even when surface accuracy goes up ([arXiv 2408.08631](https://arxiv.org/abs/2408.08631)). Give direct, task-specific instructions instead.
4. **Traces make handoffs observable.** The evals score the emitted trace, not just the final answer.
5. **Verify, don't blind-trust.** The delegate workflow has a mandatory verification step. Persuasion drift between LLMs is a real, documented failure mode ([Nature Sci. Reports](https://www.nature.com/articles/s41598-026-42705-7); [arXiv 2406.14711](https://arxiv.org/abs/2406.14711)), so judge Codex's arguments on the merits no matter how confidently they're stated.

## Repository layout

```
codex/
├── README.md          ← this file (humans)
├── SKILL.md           ← what Claude reads to do the work
├── references/
│   ├── DESIGN.md      ← architecture + rationale
│   └── NOTES.md       ← build log, lessons, research landscape
└── evals/
    ├── README.md           ← eval suite design + run instructions
    ├── trace_schema.json   ← the contract every delegation emits against
    ├── cases.yaml          ← 12 named eval cases with severity ladder
    ├── triggers.yaml       ← description-precision tests
    ├── conftest.py
    ├── test_trace_contract.py
    └── fixtures/delegate-happy-path.json
```

`SKILL.md` is the only file Claude loads on its own, and only when something triggers it. Everything else is reference material or eval harness.

## What's open

- **A live harness that auto-collects fixtures.** The evals validate trace fixtures today; the loop that produces those fixtures from real runs (with seeded scenarios for the blocker cases) is the next milestone.
- **The trigger-precision runner.** `triggers.yaml` has the cases; the multi-judge + Wilson-interval runner that consumes them isn't built yet.
- **Custom validators for the harder assertions.** Checks like `convergence_check: same_recommendation_last_2_rounds` are written down in `cases.yaml` for human review but aren't auto-checked.
- **Cross-session memory.** Every session starts cold right now. Indexing collected traces would fix that.

## Credits

Built by Nason ([@NasonZ](https://github.com/NasonZ)) in a Claude Code + OpenAI Codex collaboration. Grounded in:

- Anthropic, [Improving Skill Creator: Test, Measure, Refine](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)
- Karpathy's [LLM Council](https://github.com/karpathy/llm-council)
- [yogirk/agent-council](https://github.com/yogirk/agent-council)
- OpenAI's [codex-plugin-cc](https://github.com/openai/codex-plugin-cc)
- philschmid, Practical Guide to Evaluating Agent Skills
- Pydantic AI / Mastra / Langfuse, for the observability and OTel span shapes behind the trace contract
- Persona-prompting research, arXiv 2408.08631 and 2602.12285
- Multi-agent debate failure modes, Nature Sci. Reports and arXiv 2406.14711

Full source list in [`references/NOTES.md`](references/NOTES.md).

## License

MIT. See [LICENSE](LICENSE).
