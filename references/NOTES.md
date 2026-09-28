# Riff field and build notes

These notes preserve Riff's evidence trail: the original Claude→Codex skill, the
questions that shaped it, peer and user corrections, failed approaches, research,
and the later driver-neutral refactor. They complement
[the design](DESIGN.md), [the playbook](PLAYBOOK.md), and
[the operational skill](../SKILL.md).

This file is intentionally longer than the operational documents. The design
changed several times because real use contradicted a clean-looking abstraction;
preserving those contradictions is how future changes avoid repeating them.

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

## August 2026 — from dyad to driver-neutral Riff

The next design question was whether the collaboration shape could work from
Claude Code, Codex, Pi, or Hermes; target one or several peers; and launch several
instances of the same harness with different model or reasoning settings. The first
temptation was to replace the long skill with a generic runner and a very small set
of instructions. The user correctly pushed back: the accumulated know-how is the
valuable part of Riff and should not be destroyed to make the hot file small.

That correction produced a layered design:

- `SKILL.md` is the compact operating constitution.
- `PLAYBOOK.md` preserves durable epistemic and delegation judgment.
- `PROTOCOLS.md` preserves mode-specific workflows and stopping behavior.
- `HARNESSES.md` isolates volatile CLI and session knowledge.
- the coordinator makes fragile mechanics executable;
- focused tests protect the invariants; and
- this file continues to preserve field history, failed approaches, and sources.

The original Qwen peer runner supplied the first proven adapter mechanics: Pi RPC,
explicit sessions, `agent_settled`, artifact handoff, and isolated state. Those were
generalized rather than discarded. The original Riff supplied independent-first,
mutuality, reframing, persona restraint, persuasion awareness, delegation contracts,
verification, and context hygiene. Each was retained in the hot skill, playbook,
protocol, code, or tests according to how universal and mechanical it is.

### Corrections to the v1 evaluation approach

The v1 notes above accurately record what was built, but later inspection showed
that “the infrastructure works” was too generous:

- eleven of twelve cases had no fixture and therefore skipped;
- the single fixture was hand-authored;
- the assertion interpreter silently ignored most of the interesting assertions;
- the skill required a trace that no deterministic runner emitted; and
- the schema could represent only one Codex peer and one transport.

The refactor replaces that suite with standard-library tests over the request
contract, coordinator, and fake harness processes. No checked-in case is considered
passing because it was skipped. A small trigger dataset remains separate for fresh
agent forward-testing.

### Topology decision

“Full mesh” now means any supported harness can be the current driver and can invoke
any supported participant. Peers do not establish direct N² connections. The shared
coordinator mediates sessions and later rounds, which prevents recursive councils
and keeps authority, provenance, and synthesis visible.

### Protocol decision

The July 2026 MCP changes reinforced explicit handles and stateless coordination,
but Riff does not require MCP. Native local adapters are the dependable first layer.
The internal run/session/artifact model can later be exposed through MCP Tasks or
A2A without changing skill behavior.

### Live self-audit and trace observability

The first parallel self-audit used Claude Code and the local Qwen model through Pi.
Claude settled normally. Qwen exceeded the coordinator's ten-minute turn timeout,
but its Pi session already contained dozens of structured message, thinking, and
tool-result records. Resuming that exact session with a short “stop inspecting and
synthesize” prompt recovered a complete audit without rerunning the analysis.

This exposed an important observability distinction: process settlement, model
activity, and session recoverability are separate facts. File growth alone is a
weak progress signal when Pi already provides a structured live trace. Riff now
offers metadata-first Pi progress inspection and preserves failed native session
handles for exact-session recovery.

The two audits also found concrete coordinator defects: path-unsafe IDs, reply
races, adapter exceptions escaping pipeline/reply settlement, partial results being
overwritten by a successful follow-up, fabricated verification success with no
checks, Pi stderr backpressure, non-unique atomic temp names, and authority
degradation hidden from the compact result. Each finding became a code invariant
and focused regression test rather than another aspirational eval case.

### Driver-side forward probes

Adapter smoke tests prove that the coordinator can launch a peer; they do not prove
that each proposed driver can discover the skill, translate its instructions into a
request, and execute the coordinator. A later completion audit therefore used a
deterministic Codex-shaped probe process and real fresh driver sessions:

- Claude Code invoked its `Skill` tool for `riff`, validated the request, launched
  the probe, and read the artifact.
- Pi, backed by the local Qwen model, discovered and read the global Agent Skill,
  then performed the same flow.
- Hermes loaded Riff from its configured trusted external skill directory and
  completed the flow.
- Codex started from a neutral non-repository directory, resolved the global Riff
  skill, and completed the flow. This also exercised another Codex instance as a
  participant shape.

The probe deliberately removed nested model quality and cost from the test while
leaving skill discovery, request construction, process launch, parsing, state, and
artifact handoff real.

This test found a defect that unit and earlier live happy paths had missed. During
the Pi run, Qwen replaced the supplied probe with a similar fake that emitted
`thread.started` and an artifact but no `turn.completed`. The Codex adapter accepted
it. That meant an incomplete or truncated Codex JSONL stream could masquerade as a
settled turn. Riff now requires the native settlement event, retains a thread ID
seen before timeout, records Codex usage, and has a regression test for both the
incomplete-stream and timeout cases.

The forward probes also showed that agents naturally placed the global
`--state-dir` option after the subcommand. The CLI now accepts and documents both
orders. This is a useful field lesson: a mechanically valid interface can still be
agent-hostile when its option placement conflicts with the command grammar models
have learned from most CLIs.

### Trigger-collision migration audit

A fresh Claude Code negative probe that merely asked how Codex stores sessions did
not invoke Riff. The first implicit positive probe—“ask a Codex peer”—did invoke a
skill, but selected the installed legacy `codex` skill rather than Riff. Instructions
inside Riff could not repair that outcome because skill selection had already
happened.

The migration therefore preserved the old Claude skill while setting
`disable-model-invocation: true`, disabled Hermes' overlapping builtin `codex`
skill, and moved the old standalone `qwen-peer` directory to a recoverable archive
outside scanned roots. A fresh implicit positive probe then selected `riff`, read
the playbook, constructed a versioned request, and ran the coordinator. The old
skills were not deleted, so explicit rollback remains possible.

That retest uncovered a second interface lesson. The probe asked the driver to use
an isolated fake executable, but the driver guessed `CODEX_PATH` and
`RIFF_STATE_HOME` instead of Riff's real `RIFF_CODEX_BIN` and `RIFF_STATE_DIR`
seams. It consequently launched the installed Codex in read-only mode. The genuine
turn still settled correctly—with an explicit thread ID, `turn.completed`, usage,
native-sandbox authority, and a hashed artifact—but a deterministic probe should
never depend on guessed environment names. The supported override names are now
documented in `HARNESSES.md`.

The legacy Claude skill also had a connected user-level Codex MCP server. Disabling
model invocation on the skill did not disable those raw MCP tools, so the MCP
definition was archived and temporarily removed for a clean test. In a fresh
MCP-absent Claude session, Claude selected Riff, validated a request, invoked the
coordinator against a deterministic Codex-shaped process, read the artifact, and
reported the run's limitations accurately. The turn settled on `turn.completed`
with the expected explicit session handle. This isolates and proves the
Claude→Riff→adapter path without claiming that a stub validates model quality.

### September 2026 — the `read+web` scope gap (RIF-AUTHORITY-002)

Field evidence from the agex `telem_refresh.md` consult (run
`e1cb9833-5da4-4a3d-8637-cf4dea34ef58`): the task explicitly required web
verification of cited GitHub claims, but the only usable scope was `read`
(`--tools Read,Grep,Glob`), which excludes `WebSearch`/`WebFetch` by
construction. The peer's six fetch attempts were all permission-denied. The
peer handled the gap well — it disclosed the tool limitation in section 0 of
its artifact and fell back to the repo's own pinned source inspection — and
the driver closed the two remaining unverified claims via the GitHub API.
The synthesis stayed honest because the permission boundary was visible in
the artifact, but the acceptance criterion was still unmet by the participant
itself.

Lessons:

- **Scope must match the task's acceptance criteria, not just its risk.**
  A review that must verify external citations needs web access; declaring
  `read` silently converts a verifiable task into an unverifiable one.
- **A missing scope is a Riff defect, not a driver workaround.** The fix was
  a fourth shared scope value `read+web` (read-only file access plus outbound
  network fetch; no write/shell/edit), enforced natively by the Claude Code
  `--tools` allowlist (`Read,Grep,Glob,WebSearch,WebFetch`,
  `--permission-mode dontAsk`). Codex, Pi, and Hermes adapters fail closed
  with a clear validation error until they gain native enforcement. Contract
  change: `models.py` `Tools` literal and participant validation; capability
  reporting now advertises per-harness `tool_scopes`, so drivers should check
  `capabilities` before requesting a scope.
- **Related identifier:** RIF-AUTHORITY-001 (do not expand authority
  implicitly) still governs; `read+web` is a *narrower* expansion than
  `write`, and only where the native harness can enforce the boundary.

### September 2026 — field review of 127 runs

The first measurement of Riff in real use rather than in probes, following the
test–measure–refine method of Anthropic's skill-creator work: characterize real
behavior before changing the skill, and justify each change by an observed failure.
Corpus: every run under the state root from 2026-08-15 to 2026-09-28 (127 runs, 190
turns, about 27 peer-hours), 121 linked to driver transcripts by run ID. Pairings:
Claude→Codex 60, Codex→Claude 58, one Claude→(Codex + Pi/Qwen 3.8 27B) broadcast, and
two runs driven by Pi on the local Qwen 3.8 27B. A stratified sample of 44 runs was
reviewed against a fixed rubric (trigger, request quality, peer output, driver
handling, verification record against the transcript, outcome, friction) by four
independent reviewers. Evidence and per-run reviews live outside the repository in
`~/riff-field-review-2026-09/`.

What worked:

- Peer quality was high wherever a peer ran: almost every artifact cited file:line
  evidence, most reframed the question, and in 11 of 11 Codex-driven consults the
  driver acted on the findings (8 with new regression tests). Spot-checked citations
  were exact. Independent-first consults were the highest-value runs.
- Exact-session recovery works: all four timed-out turns were recovered by a reply.
- Drivers usually did verify in practice, and those checks caught real peer defects
  (a JSON-schema form OpenAI strict mode rejects, a cache lookback error, missing
  rules in a prompt, statistics pooled across two models). Where Codex drivers
  recorded verification, the record matched the transcript every time.
- Qwen 3.8 27B worked both ways. As a peer on an identical prompt it matched Codex
  on substance at about a tenth of the tokens and four times the latency, and more
  of the shipped fixes originated with it than with Codex; it missed one bypass
  Codex found. As a driver it followed the playbook, synthesized, changed its view
  on three points, and checked claims itself. Its errors were the characteristic
  small-model ones: a tool scope that did not match the task, a verification record
  that overstated its checks, and claimed continuity it did not have.

What failed, and what changed:

- **The skill fell out of context.** Claude drivers recorded verification in 7 of
  61 runs against 52 of 58 for Codex drivers. 50 of those Claude runs came from one
  session: 3 of 5 recorded before an auto-compaction, 0 of 45 after, because only
  another skill was re-attached. Later the driver told the user rendered figures had
  "never been viewed" when it had approved them. Change: obligations now travel in
  the tool output (`next_steps` with the exact `riff.py` path, `unverified_runs`),
  which survives compaction where skill text does not (`RIF-DELEGATE-002`).
- **Verification was the driver's word.** Change: `verify --run` executes checks and
  records exit codes; `--check` is labelled asserted; re-verifying keeps history
  instead of overwriting an earlier negative check.
- **Scopes silently failed.** Every `read+web` WebFetch/WebSearch was denied, write
  peers could not run a single test, and inputs outside a Claude peer's cwd were
  unreadable, while the runs reported success. `--tools` only exposes a tool; under
  `dontAsk`/`acceptEdits` it also needs `--allowedTools` (confirmed with a live probe
  against a domain absent from the user's allowlist). Change: `read+web`
  pre-approves web tools; `add_dirs` and `allowed_commands` adapter params; denied
  tools surface in run output; `validate` warns on a web task without web scope and
  on context files outside a Claude peer's cwd (`RIF-AUTHORITY-002`).
- **Failures were mislabelled and retried.** Three 429 session limits surfaced as
  "claude exited with status 1" although the JSON said why and when it resets; three
  401s were retried unchanged. Change: `rate_limit`/`auth` classification from the
  payload and error text, with next steps that say not to retry (`RIF-FAILURE-001`).
- **Recovery cost rounds.** A timeout consumed a round and blocked a real
  disagreement round. Change: only settled turns spend `max_rounds`; attempts are
  capped at twice the budget. The default turn timeout is 1800 s (Codex peers: median
  11 min, p90 31 min).
- **Contracts were thin.** `out_of_scope` was empty in 121 of 121 runs; 21 of 36
  delegations lacked acceptance criteria; none of 8 Claude-driven write delegations
  used a worktree, and one driver commit swept in unfinished peer edits. Change:
  `validate` warnings for each, including `write-in-main-checkout`; the SKILL.md
  example now carries every contract field and is tested to validate warning-free.
- **Mechanics were agent-hostile.** `run` printed nothing until it settled, so
  drivers hunted for run IDs with `ls -t` and wrote polling loops; `driver_position`
  errors failed validation ten times in the sample; `independent_first` stayed true beside a
  provided position; a reply to a running turn failed unnoticed. Change: a `started`
  event on stderr; errors that name the remedy; `independent_first` derived from a
  provided position; replies refused while a turn is live and allowed once its
  coordinator has died; a git fingerprint of each peer's checkout at dispatch and
  settle, since reviews ran while the driver edited the same files.

Not yet addressed: a `wait`/`--detach` pair to replace ad-hoc polling; cost in
dollars for non-Claude peers (Claude's `total_cost_usd` is now recorded); typed
per-claim checklists that would help weaker drivers most; and the behavior cases in
`tests/behavior_cases.json` have not yet been run with and without these changes, so
the fixes are justified by observed failures but their effect is not yet measured.

### September 2026 — behavior-case measurement

The field review justified each change by an observed failure; this measured
whether the changes work. Each case in `tests/behavior_cases.json` ran once per
driver direction — Claude Sonnet driving GPT-6 Luna and Luna driving Sonnet — in
isolated repositories and state directories. The before-arm is the field corpus,
because the pre-refinement code was never committed and cannot be re-run. Full
results: `~/riff-field-review-2026-09/measure/RESULTS.md`.

All eight cases passed for both drivers, four of them only after a fix the
measurement itself produced. Headline contrasts with the field: verification survived a
driver that never loaded the skill (field: 0 of 45 after compaction); `read+web`
fetched with zero denials (field: every fetch denied); zero tool denials in 19 turns;
every failure classified; `out_of_scope` in 10 of 14 driver-built runs (field: 0 of
121); `driver_prediction` in 14 of 14.

What the measurement found and fixed:

- **Long blocking runs died with non-interactive Claude drivers.** Claude Code's
  shell pushed a many-minute `run` into the background, and `claude -p` killed it at
  session end (2 of 2 first attempts). `run --detach` plus a bounded `wait` fixed it;
  both reruns completed. This also answers the field's ad-hoc polling loops.
- **An allowed-command prefix the peer never saw.** The driver allowed `python -m
  unittest discover`; the peer ran `python3 -m unittest tests/...`, and every call was
  denied. The peer prompt now lists the exact prefixes.
- **Recovery under the bound that just expired.** Replies inherit the previous
  timeout, so an 8-second turn was retried twice at 8 seconds. The timeout next step
  now proposes a longer `--timeout-seconds`; the rerun recovered in one reply.

A second round closed the verification gaps. The verify next step had always
offered a test command, which consults rarely have, so consult drivers recorded
nothing. Next steps now derive from the run: consults are asked for the claims they
checked and whether the quoted prediction changed; delegations for acceptance checks
and integration; runs with no answer for `not_performed`. The five sessions that had
left verification pending all recorded it on rerun, with `view_changed` set on every
successful consult. The same round found `capabilities` misleading — a driver
concluded the Codex model could not be pinned because only adapter-specific keys were
listed — and it now names the shared participant fields.

Still open: one consult claimed `--integrated` with nothing applied. With one session
per case per driver, these are observations, not rates.
