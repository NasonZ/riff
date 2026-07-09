# Codex skill — build notes

These notes preserve the build log for riff: what I asked for, what Claude Code drafted, where Codex pushed back, and what changed as a result. Companion to `./DESIGN.md` (the reference) and `../SKILL.md` (the operational guidance to Claude).

Longer than DESIGN.md because the design changed several times based on what didn't work, and the record of what didn't work matters — both for me and for anyone building similar cross-model skills.

## Starting point

I'd built a similar skill before — Claude-orchestrates-Codex for delegation and round-table discussions — but lost it. I wanted to rebuild, but first asked Claude what was available in May 2026 that wasn't there last time.

Web search surfaced:

- **OpenAI's official `codex-plugin-cc`** — Claude Code plugin (not skill) providing `/codex:rescue`, `/codex:review`, etc. + an autonomous `codex-rescue` subagent. One-directional (Claude → Codex), not bidirectional.
- **`skills-directory/skill-codex`** — small open-source skill wrapping `codex exec`. Closest match to what I wanted to rebuild.
- **`tuannvm/codex-mcp-server`** — community wrapper fixing a then-current bug in the official Codex MCP server where `conversationId` wasn't returned.
- **`mkXultra/ai-cli-mcp`** — MCP server running multiple CLI agents in background.

I decided to build my own, treating the official plugin as inspiration rather than dependency.

## The CLI primitives we settled on

After verifying against `codex --help` and `codex exec --help` (v0.133):

```bash
codex exec --sandbox read-only -o /tmp/out.md "<prompt>"   # one-shot
codex exec --json ... | head -1                            # session ID at first event's thread_id
codex exec resume "<sid>" -o /tmp/out.md "<followup>"      # explicit follow-up
codex exec resume --last -o /tmp/out.md "<followup>"       # convenience, single-thread only
codex exec --output-schema schema.json ...                 # structured response
codex exec review --uncommitted | --base main | --commit X # built-in code review
codex mcp-server                                           # MCP server mode
```

A few things tripped Claude up that ended up in the SKILL.md "Common failures":
- `--ask-for-approval` is on `codex` (interactive), not `codex exec`
- `--sandbox` is exec-only; `codex exec resume` inherits sandbox from the original session
- `codex exec resume <SID> <FLAGS>` fails — flags go BEFORE the SID
- `jq` isn't everywhere; the SKILL uses `python3 -c` for JSON extraction
- The OpenAI Responses `web_search` tool isn't enabled by a flag on `codex exec` — use `-c "tools.web_search=true"`

## v1 — the simple skill

Three modes (delegate / consult / roundtable), self-bootstrapping transport detection (MCP if available, CLI fallback), context-budget rules ("write to `-o file`, then summarize, never paste full transcripts"). Roundtable had ONE stop signal — text marker `CONSENSUS:` / `CONTINUE:`.

Smoke test: Claude invoked the skill on itself ("consult mode: review my SKILL.md"). It worked. Codex came back with five concrete findings, three of which were genuinely sharper than what Claude had written. That established the skill's basic mechanics.

## The first real correction — schema vs marker

Codex's review of v1 recommended `--output-schema` for roundtable stop signals (force `{status, position, concerns}` JSON, no suffix parsing). Claude patched it in.

I pushed back: **schemas are too restrictive for abstract discussions.** A 3-field schema works for "X or Y" decisions (Codex's principal-engineer mode fits). It doesn't work for design philosophy, communication regimens, or anything where the right move is to ask a clarifying question, propose a third framing, or think out loud.

Outcome: roundtable got **three sub-modes**, not one. Convergence (schema), Critique (text marker), Exploration (no stop signal). The schema is no longer the default — it's one option of three, picked by conversation shape.

Lesson: Claude took Codex's schema recommendation without asking "is this conversation's shape a fit for schemas?" first. Deferring to the second model isn't the same as engaging with it.

## The broader-research turn

I asked: "do similar research on delegation patterns as that's what the original vision of the skill was — it's not just discussions right." Also: "i'd pull back on persona injection... it can lead to the model acting to meet the character instead of being productive or insightful."

This sent Claude searching beyond coding workflows. The big finds:

**The 2026 council ecosystem** — richer than Claude's first pass surfaced:
- Karpathy's LLM Council (the seminal pattern: N models independently → anonymous peer review → Chairman synthesizes)
- yogirk/agent-council (CLI version with Claude Code + Codex + Gemini CLI; "any question, not just engineering"; ~2× consideration coverage)
- 0xNyk/council-of-high-intelligence (18 persona-bound agents; Aristotle, Feynman, Kahneman, Torvalds…)
- Perplexity Model Council (productized, Feb 2026)
- Domain applications: investment councils, healthcare diagnostic ensembles, ethics deliberation, cultural alignment, creative writing with model-specialization splits

**The driver/worker pattern** as the canonical Claude+Codex topology (April 2026): Claude (Opus 4.7) plans + holds architecture + decides what to delegate. Codex (GPT-5.x) executes long terminal-shaped work and reports back. Frameworks like BEADS + Metaswarm v0.11 wrap this with spawn/handoff/return bookkeeping.

**Persona prompting research** — vindicated my instinct strongly:
- arXiv 2408.08631 "Persona is a Double-edged Sword" — performance can rise on subjective tasks but rationale quality drops
- arXiv 2602.12285 — up to **26.2% performance degradation** on agentic benchmarks from task-irrelevant persona cues
- Direct quote: persona prompting "comes at the cost of explanation quality while failing to mitigate underlying biases"

Outcome: Claude added a `Where this skill sits in the 2026 ecosystem` section to SKILL.md acknowledging this is a *dyad*, not a council, and what each gives up. Claude added "Techniques that travel across modes" — Independent-first, Welcome reframing, Adversarial-influence awareness, Devil's advocate — borrowed from council literature but workable at N=2. Persona injection got pulled back hard: default is no persona, with research citations.

The non-coding use cases got broadened explicitly: strategic decisions, research framing, ethics, creative critique, naming/taxonomy/API design.

## The mutuality correction

I pushed back again, more sharply: "codex can be smarter than u in some regards so its a 2 way street, its there to also offer different perspectives etc you both have vast knowledge on philosophy, coding, problem solving etc so the goal is to enable a richer exploration of both ur semantic spaces."

This caught a posture Claude had been writing into the skill without noticing — phrases like "redirect Codex toward X" or "lens-redirect Codex" presupposed that Claude's frame was the one that mattered. Even calling Codex "peer" while telling Claude to redirect it was contradictory.

Outcome: Claude rewrote the "two agents" section to emphasize mutuality. Tendencies (Claude=creative, Codex=rigor) are statistical, not destinies. Driver/worker is a coordination convenience, not a capability ranking. Codex may reframe Claude's question — that's signal, not noise. Either model can be the one persuaded.

Lesson: posture leaks into prose in ways the author doesn't notice. Claude wouldn't have caught "redirect Codex toward X" without my correction. Worth re-reading agent-produced work for posture, not just content.

## MCP setup and the threadId gotcha

I set up the MCP transport: `claude mcp add codex -- codex mcp-server`. After restart, MCP tools `mcp__codex__codex` and `mcp__codex__codex-reply` became available.

Claude smoke-tested. The MCP tool returned `{"threadId": "…", "content": "..."}` — `threadId` at the **top level**, not at `structuredContent.threadId` as community docs (and the SKILL.md) had claimed. Fixed in two places. Older clients may still see the `structuredContent` path; current spec on Codex v0.133+ puts it top-level.

The smoke test was also the first time the skill's "Welcome reframing" principle got used in practice. Claude asked Codex to push back on the SKILL.md framing — it did, with three substantive critiques (overclaiming parity, internal inconsistency in the persona section, "quasi-ideological" tone). All three were right. Claude applied them. That's what the skill is supposed to enable.

## The Anthropic blog turn

I asked Claude to read https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills in depth and "discuss with codex" — and to make sure Codex had research access so it'd build its own picture rather than mirror Claude's.

The blog post: skills as testable software artifacts. Evals as unit tests for skills. Benchmark mode (pass rate, time, tokens). Multi-agent parallel eval. Comparator agents (LLM-as-judge A/B). Description-precision testing (Anthropic improved triggering on 5/6 of their own skills using this). The "what" vs "how" hint — SKILL.md may evolve from procedural instructions toward natural-language outcome descriptions.

Claude's take: this is the missing engineering layer. The skill at this point had been refined purely from interactive feedback — no evals, no regression detection, description tuned by intuition. The blog post supplied that workflow.

Codex's independent take (via MCP, with `tools.web_search=true` enabled so it could read the post itself) added concrete things Claude had missed:

1. **Description-precision testing is too shallow for cross-model skills.** It checks *when* the skill fires, not whether the driver/worker contract survived translation across model priors.
2. **Per-hop metrics** — delegation precision/recall, handoff-loss rate, worker-output acceptance accuracy, verification catch rate, disagreement handling, model-swap robustness. These don't exist in single-model eval frameworks.
3. **A delegation trace contract** — every delegation emits structured JSON the eval can score, not just the final answer.
4. **LLM judges are not ground truth** — for cross-model skills, prefer artifact-based checks (tests, diffs, reproductions, citations, traces).
5. **Persona discipline as eval variable** — not just prose recommendation.
6. **Pydantic AI's multi-agent framing** as a structural reference Claude had missed.

This was a genuine "Codex was better than Claude here" moment. Most of those went straight into the trace schema and eval cases.

## Building the trace contract and eval suite — collaborative design

I said: "lets build a small eval suite and add a well thought out trace contract." Critical word: "thought out." Don't just dump fields.

Claude drafted: trace schema (10 fields), 8 eval cases, pytest harness, `triggers.yaml` for description precision. Sent to Codex in the existing thread (its second turn in the same conversation).

Codex returned a tight critique with concrete improvements:
- Add `acceptance_criteria` to request (observable pass/fail checks committed up-front)
- Add `exit_status`/`error_type` to execution (failures categorical, not binary)
- Restructure verification into `verifier` enum + list of `checks`
- New `handoff` block — `integrated_by_driver`, `driver_changes_made`, `worker_output_modified` (because cross-model skills fail at handoff more than at answer generation)
- Make `evidence` typed (`kind` + `ref`), not free text
- Drop `confidence` — uncalibrated, decorative
- Split `reframed_question` into `framing.status` enum + optional text
- Case 4 weak — substring matching for "Claude's position" will false-pass; replace with `driver_position` enum
- Case 5 weak — "CONSENSUS" is easy to emit without actual convergence; require mechanical check
- Four missing cases: `delegate-context-minimality`, `worker-error-surfaced`, `verification-catches-bad-worker`, `authority-boundary`
- Use pytest, not standalone script ("standalone scripts rot into mini test frameworks")
- LLM-as-judge for triggers: multi-judge + multi-seed + Wilson intervals + adversarial negatives + manual disagreement queue

All landed in the final design. The eval suite README itemizes which contributions came from Codex.

## What was built

```
~/.claude/skills/codex/
├── README.md          — GitHub-facing showpiece (humans)
├── SKILL.md           — operational guidance to Claude (~300 lines)
├── references/
│   ├── DESIGN.md      — architecture reference (humans)
│   └── NOTES.md       — this file (humans)
└── evals/
    ├── README.md
    ├── trace_schema.json
    ├── cases.yaml
    ├── triggers.yaml
    ├── conftest.py
    ├── test_trace_contract.py
    └── fixtures/
        └── delegate-happy-path.json
```

The pytest suite runs (`2 passed, 22 skipped in 0.38s`). 2 = both tests against the one shipped fixture; 22 = the other 11 cases skipping cleanly because no fixture exists yet. The infrastructure works; the proof of skill quality accumulates as real traces get collected.

## What's still open

Documented in DESIGN.md under "What's open / future work." Short version:
- Live harness that produces fixtures from real invocations (the four blocker cases need this)
- Implementation of the trigger-precision LLM-as-judge runner
- Custom validators for the complex assertion shapes (`convergence_check`, etc.)
- Cross-session memory of past delegations (currently each session starts fresh)

## Patterns worth repeating

- **Skill on itself as a smoke test.** Asking Codex to review the SKILL.md was the first time the skill ran for real, and it surfaced bugs in the skill (the `threadId` location, the persona section's internal inconsistency, the overclaim of parity) that no theoretical review would have caught.
- **Independent-first when consulting Codex on big design questions.** Claude shouldn't share its position upfront. On the Anthropic blog discussion, Codex's independent take added things Claude's own framing didn't have.
- **Treating Codex's pushback on framing as the primary value.** Often the most useful thing Codex did was point out a better question than the one Claude asked. The trace contract's `framing.status` enum exists because this pattern showed up repeatedly.
- **User correction as a signal to look harder at posture, not just prose.** The mutuality correction caught a posture issue Claude had written into the skill several times without noticing. Worth re-reading agent-produced work for posture, not just content.

## Patterns to avoid

- **Deferring to Codex's recommendations without engaging.** When Codex first recommended `--output-schema` for roundtables, Claude took it. Should have asked "is the conversation's shape a fit for schemas?" first.
- **Defaulting to council patterns at N=2.** The literature is rich and tempting, but most of it assumes N≥3. The dyad has its own shape; force-fitting council mechanics produces ceremony.
- **Letting eval suites grow open-ended.** Twelve cases hit the right shape; twenty would have been over-engineered for a v1. The temptation to add more is real and should be resisted until the existing ones have real fixtures.

## Sources (consolidated)

Used during this build:

- [Anthropic — Improving Skill Creator: Test, Measure, Refine](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)
- [Karpathy's LLM Council](https://github.com/karpathy/llm-council)
- [yogirk/agent-council](https://github.com/yogirk/agent-council)
- [skills-directory/skill-codex](https://github.com/skills-directory/skill-codex)
- [OpenAI codex-plugin-cc](https://github.com/openai/codex-plugin-cc)
- [philschmid — Practical Guide to Evaluating Agent Skills](https://www.philschmid.de/testing-skills)
- [pytest-skill-engineering](https://github.com/sbroenne/pytest-skill-engineering)
- [Persona is a Double-edged Sword (arXiv 2408.08631)](https://arxiv.org/abs/2408.08631)
- [Persona-induced agent degradation (arXiv 2602.12285)](https://arxiv.org/abs/2602.12285)
- [Persuasion-driven adversarial influence in multi-agent debate (Nature Sci. Reports)](https://www.nature.com/articles/s41598-026-42705-7)
- [MultiAgent Collaboration Attack (arXiv 2406.14711)](https://arxiv.org/abs/2406.14711)
- [Pydantic AI multi-agent applications](https://pydantic.dev/docs/ai/guides/multi-agent-applications/)
- [Mastra AI Tracing](https://mastra.ai/docs/observability/ai-tracing/overview)
- [Langfuse — OpenTelemetry for LLM Observability](https://langfuse.com/integrations/native/opentelemetry)
- [Codex CLI docs (exec, mcp-server)](https://developers.openai.com/codex/cli)
- Codex (GPT-5.x) — via the skill, in this very session
