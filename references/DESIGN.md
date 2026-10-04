# Riff design

Riff is a shared Agent Skill plus a deterministic local coordinator for
cross-harness collaboration. It preserves the original project's accumulated
epistemic and delegation knowledge while generalizing the original Claude→Codex
dyad into a driver-neutral, multi-participant system.

## Contents

- [Purpose and boundary](#purpose-and-boundary)
- [Knowledge architecture](#knowledge-architecture)
- [Learning from runs](#learning-from-runs)
- [Rule provenance](#rule-provenance)
- [Coordination topology](#coordination-topology)
- [Contracts and adapters](#contracts-and-adapters)
- [State and observability](#state-and-observability)
- [Authority](#authority)
- [Testing strategy](#testing-strategy)
- [Deliberate non-goals](#deliberate-non-goals)

## Purpose and boundary

Riff supports useful collaboration now and preserves evidence for improving it over
time. A peer may develop an idea, question the framing, assess a proposal, or deliver
a bounded task. The driver owns the resulting judgment without being treated as
the intellectual authority. Exploration can end with a better question rather than
agreement or a decision.

The skill owns judgment:

- when collaboration is worth its cost;
- how to elicit independent views;
- how to structure consultation, discussion, and delegation;
- how to resist persona and persuasion artifacts; and
- how to verify and synthesize.

The coordinator owns fragile mechanics:

- process launch and timeout;
- explicit native session identity;
- fan-out and pipeline ordering;
- artifact and log paths;
- recursive-invocation prevention;
- request linting and executed verification; and
- automatic run and turn records, including the driver's next steps.

That last item matters more than it looks. A driver can lose the skill's text to
context compaction mid-session; the coordinator's output is the one instruction
surface it reads on every call, so obligations that must survive (read the
artifact, verify, report denied access) travel there. They are derived from the run
itself rather than generic: a delegation asks for acceptance checks and an
integration record, a consult asks for the claims checked and how the driver's
starting expectation or uncertainty developed (quoting the baseline back), a
failure names its recovery, and a run where no peer answered asks for an honest
`not_performed`. An inspection or exploratory contribution needs a different
record from an executable acceptance check.

Adapters compile the common contract into native harness operations. Riff does not
become another model provider registry, tool runtime, sandbox, or agent framework.

## Knowledge architecture

Riff's existing know-how is an asset, not migration debris. Preserve it through
progressive disclosure:

```text
field observation / research
            │
            ▼
         NOTES.md
 evidence, failed attempts, caveats
            │
            ▼
        PLAYBOOK.md
      durable judgment
            │
     ┌──────┴────────┐
     ▼               ▼
  SKILL.md       PROTOCOLS.md
entrypoint        mode-specific
     │               │
     └──────┬────────┘
            ▼
 coordinator/adapters + focused tests
```

Promote a lesson according to what it changes: record publication-safe rationale in `NOTES.md`,
explain durable judgment in `PLAYBOOK.md`, and put always-needed guidance in
`SKILL.md`. Encode mechanical invariants in code and focused tests; evaluate
judgment through fresh-agent behavior cases. Every lesson need not become an
instruction in every layer. Keep volatile harness flags in `HARNESSES.md` and
their executable contract in adapter tests.

## Learning from runs

Run records belong to the operator and stay in their configured local storage.
They can support private review, candidate improvements, evaluation on separate
tasks, and deliberate adoption. Riff does not upload these records to this
repository or a shared dataset. Using a configured peer still sends its task and
context through that harness and provider; local record storage does not imply
local-only inference.

Skill optimization and model post-training are distinct potential consumers.
[SkillOpt](https://github.com/microsoft/SkillOpt) edits skill text using scored
trajectories while keeping model weights frozen, with a held-out validation gate
for candidate changes. Curated demonstrations or preference examples could instead
support model post-training. Riff currently supplies neither an optimizer
integration nor a training-data exporter.

The existing records connect participants, session handles, artifact paths and
hashes, failures, usage, initial expectations, checks, and integration reports.
A driver's `verify --note` can preserve a useful reframe, reasons for adopting or
rejecting it, and remaining questions. Keep execution success, verified claims,
subjective usefulness, and user feedback distinguishable. Adoption is not a label
of correctness, and rejected or failed work is useful evidence too.

These records are not self-contained replay data. Tasks and prompts are hashed;
recovering their contents depends on retained requests or native transcripts.
Driver synthesis and user feedback require the linked driver conversation. The
checkout fingerprint records HEAD and a dirty-file count, not an exact snapshot.
Skill and harness versions are not comprehensively pinned in the run record.

A future versioned export layer should assemble selected runs with recoverable
inputs, relevant artifacts and transcript excerpts, versions, outcome evidence,
and explicit missing-data markers. Exported content needs deliberate selection and
redaction rather than copying all ambient session history. The coordinator should
remain useful without an optimizer or training service.

For evaluation, separate related runs by task or project when constructing train,
validation, and test sets; follow-ups from the same problem are not independent
examples. Replay can test a proposed improvement; a historical association between
consulting and success alone cannot show that consulting caused the improvement.

## Rule provenance

Stable identifiers link guidance, observations, and tests. Their labels describe
where the rationale comes from: `[F]` operational experience, `[R]` published
research or vendor guidance, `[T]` a convention or untested hypothesis. Private
source records are not distributed; `NOTES.md` preserves reusable lessons.
They do not rank instruction authority. In particular, user authority boundaries
remain binding regardless of the label on a rule.

- `RIF-EPISTEMIC-001` [F] — elicit independently before comparison.
- `RIF-EPISTEMIC-002` [R] — confidence is not evidence.
- `RIF-EPISTEMIC-003` [T] — record the starting expectation or uncertainty when useful.
- `RIF-SESSION-001` [F] — identify sessions explicitly.
- `RIF-DELEGATE-001` [F] — verify before integration.
- `RIF-DELEGATE-002` [R] — distinguish recorded execution from reported inspection;
  assess each check's relevance and scope.
- `RIF-AUTHORITY-001` [T] — do not expand authority implicitly.
- `RIF-AUTHORITY-002` [F] — match tool scope to the acceptance criteria.
- `RIF-AUTHORITY-003` [F] — bound every tool the scope does not name.
- `RIF-CONTEXT-001` [T] — prefer references and artifacts to transcript transfer.
- `RIF-FAILURE-001` [F] — classify a peer failure before retrying it.
- `RIF-COLLECTION-001` [F] — one installed skill owns each trigger.

`tests/test_knowledge.py` checks references against this registry. Keep the source,
scope, and caveats when updating a rule; field evidence on one model or task does
not establish a universal law. New research can motivate a test before it changes
the operating guidance.

## Coordination topology

Any supported harness can be the current driver and any supported harness can be a
participant, including another instance of the same harness. This provides a
user-facing full mesh without direct N² peer connections:

```text
current driver → Riff coordinator → participant sessions
                            ├──────→ participant session
                            └──────→ participant session
```

The driver mediates every later round. Child sessions cannot recursively invoke
Riff at the default depth. This keeps permissions, provenance, cost, and synthesis
visible in one place.

### Before and after

The previous repository coupled one driver, one peer, one transport, and the
collaboration guidance in a single skill:

```text
Claude Code
  └─ MCP call → one Codex thread
       └─ hand-authored/optional trace fixture
```

The refactor keeps the guidance while replacing the fixed edge with a shared
contract and four small adapters:

```text
any current driver
  └─ RunRequest → Coordinator
                   ├─ ClaudeAdapter → explicit Claude session
                   ├─ CodexAdapter  → explicit Codex thread
                   ├─ PiAdapter     → RPC + explicit Pi session
                   └─ HermesAdapter → explicit Hermes session
                          │
                          └─ RunStore → manifest, turns, artifacts, logs
```

In code, orchestration depends only on the normalized adapter boundary:

```python
class HarnessAdapter:
    def capability(self) -> dict: ...
    def start(self, turn: TurnRequest) -> SettledTurn: ...
    def reply(self, turn: TurnRequest) -> SettledTurn: ...
```

Adding a harness therefore does not add new pairwise Claude↔X, Codex↔X, or Pi↔X
paths. It adds one compiler from the common turn contract to that harness's native
protocol.

## Contracts and adapters

The versioned JSON request names participants inline. Profiles are optional user
convenience, not a required registry. Each participant declares:

- a unique instance ID;
- harness;
- working directory and tool scope;
- optional provider/model;
- optional adapter-owned parameters; and
- optional split task or focus.

Adapters fail closed on unknown parameters. This prevents an apparently generic
`extra_args` field from becoming command injection or a silent portability trap.

Each adapter implements `capability`, `start`, and `reply`, returning a normalized
settled turn with artifact, native session handle, usage when available, authority
enforcement level, and explicit failure.

Pi is the normal bridge to llama.cpp/vLLM because it supplies agent semantics above
their inference endpoints. A raw OpenAI-compatible adapter may be added later for
tool-free consultation, but must not claim repository-agent behavior.

## State and observability

State defaults to `$XDG_STATE_HOME/riff` or `~/.local/state/riff`:

```text
runs/<run-id>/
├── run.json
├── participants/<participant-id>.json
├── participants/<participant-id>/...native state...
├── turns/<turn-id>.json
├── artifacts/<turn-id>.md
└── logs/<turn-id>.log
```

`run.json` stores coordination metadata, a task digest, references, contract fields,
the driver's prediction, lint warnings, a git fingerprint of each participant's
checkout at dispatch, status, and verification with its history. It does not
duplicate full prompts or artifacts. Turn records store a prompt digest, artifact
path and hash, native session handle, timing, usage, cost where the harness reports
it, permission denials, the checkout fingerprint at settle, and error. Comparing the
two fingerprints can reveal a changed HEAD or dirty-file count, but cannot
establish that file contents stayed unchanged while the peer was reading them.

The coordinator emits records automatically. The driver only appends verification
and integration truth; an empty, explicit `not_performed` is preferable to a
fabricated successful check. Verification distinguishes two kinds of check. A
`--run` command is executed by the coordinator, which records its exit code,
duration, output hash, and output tail; with only executed checks the result is
derived from exit codes, and a claimed `passed` that contradicts a failing command
is rejected. A `--check` string is recorded as `asserted`: the driver's statement,
honestly labelled, never presented as executed (`RIF-DELEGATE-002`).

`validate` and `run` also return lint warnings for valid requests that tend to
waste or bias a run: a delegation without acceptance criteria or out-of-scope
items; persona wording; the driver's view inside a withheld task; an
independent-first run without a `driver_prediction`; a task that needs the web
given a scope without it; a context file a Claude peer cannot read; a write peer in
a main checkout rather than a worktree; and fan-out beyond five participants.
These heuristics warn rather than reject because each pattern has legitimate
exceptions, and every message names its remedy. `driver_prediction`
is stored in the manifest and never sent to a peer;
with `verify --view-changed` it makes "did consulting change the decision?" a
recorded driver assessment rather than a later recollection (`RIF-EPISTEMIC-003`).
The field may instead state uncertainty; `driver_position: none` represents no
prior position and does not require a prediction. `view_changed` remains null
when not applicable. A useful exploration with no checks can record
`not_performed` and its contribution in `note`, without claiming verification.

An initial `run` returns both the aggregate run result and the result of the turns
it just executed; these are identical on round one. A later `reply` keeps them
separate: `turn_result` describes that reply, while `result` is recomputed across
the latest state of every participant. A successful follow-up therefore cannot
launder another participant's failure into overall success. Only settled turns
spend a participant's `max_rounds`; a failed turn being recovered does not, and
attempts are capped at twice the budget so a broken peer cannot loop.

For Pi, `progress` can inspect the RPC stream log and native JSONL while a turn is
active. Its default view exposes operational metadata—event/update counts, block
types, character counts, and tool names—without copying thinking or answer text
into coordinator output. The RPC log supplies low-latency deltas; the session JSONL
supplies durable continuation records and may lag until an assistant/tool boundary.
Short content previews require an explicit flag. `run` prints its run ID on stderr
before it blocks, so the run is addressable from a second shell at once; a
preallocated `--run-id` remains available for callers that want to choose it.
`run --detach` starts the coordinator in its own process group and returns at once,
and `wait` blocks for a bounded time (nine minutes by default) before returning
either the settled result or "still running". A child backgrounded by a driver's
tool can otherwise die when the driver session ends. Choose wait bounds within
the calling harness's per-call limit.

Participant mutations use per-participant advisory locks, run aggregates use a run
lock, and JSON state is written through unique fsynced temporary files followed by
atomic replacement. This prevents concurrent replies from exceeding their round
bound or corrupting shared manifests.

## Authority

Tool scope has four shared values: `none`, `read`, `read+web`, and `write`.
`read+web` is read-only file access plus outbound network fetch (web search and
URL fetch); it grants no write, shell, or edit authority. Adapters report
whether the scope is native, sandboxed, or prompt-enforced, and each adapter
rejects unsupported scopes at command construction. Enforcement limits remain
visible: Hermes read scope is prompt-enforced, and Codex sandboxing does not
remove every tool that a narrower scope asks the peer to avoid. Claude Code and
Codex support `read+web`. On Claude it needs both halves of its permission model:
`--tools` to expose
WebSearch and WebFetch, and `--allowedTools` to pre-approve them under the
non-interactive permission mode. Exposure alone looks correct and fails silently;
see `HARNESSES.md`. Riff does not imply authority from a mode name.

Codex inverts that problem. Its CLI enables web search by *default*, so a scope
that does not name the web has to switch it off, or `read` silently grants
outbound network. Riff therefore pins the top-level `web_search` setting in both
directions.

MCP is in no scope, for either harness, and both needed a fix. Claude takes
`--strict-mcp-config`, which uses only servers named by `--mcp-config` — and riff
names none. Codex has no per-run equivalent, so riff keeps a sanitised
`CODEX_HOME` beside its own state: a copy of the user's config with every
`[mcp_servers.*]` table removed, with auth and the model cache linked so
credentials and model resolution are unchanged. A settled Codex turn reports
`adapter_metadata.mcp_servers_suppressed`.

The contract rejects:

- concurrent writers sharing a working directory;
- write-capable broadcast;
- ambiguous split delegation;
- unsupported harness parameters; and
- recursion at the configured depth.

Native sandbox and permission systems remain authoritative. The driver retains
responsibility for reviewing changes and for every external side effect.

## Testing strategy

Use dependency-free `unittest` tests in four layers:

1. Contract tests for ambiguity, authority boundaries, and request warnings.
2. Coordinator tests with in-memory fake adapters for session isolation,
   independent-first prompts, partial failure, traces, replies, round limits, and
   executed verification.
3. Process tests using fake executables for each adapter's command and output
   protocol.
4. Knowledge tests: every cited `RIF-*` identifier is defined with a basis,
   `SKILL.md` links resolve one level deep, long references open with contents, and
   the forward-test datasets are well formed.

Keep live model tests opt-in. A passing fixture schema is not proof that the skill
actually invoked a peer correctly. Do not keep aspirational cases that permanently
skip or assertions the runner silently ignores.

Two datasets drive forward tests with fresh agents; neither runs in CI because each
costs model calls. `tests/trigger_cases.json` holds should- and should-not-trigger
prompts, weighted toward near-misses; rerun it after any description change.
`tests/behavior_cases.json` holds scenarios drawn from field failures and explicit
design aims, with their basis labelled and tied to observable expectations. Run
each with and without the change under test and judge the transcript and run
manifest rather than the driver's summary. Keep private results outside the
repository; publish only explicitly approved, sanitized findings. Passing
deterministic checks establishes the mechanics, not an improvement in model
behavior. Compare old and new skills in fresh sessions across intended
drivers, inspecting contributions, synthesis, limitations, time, and token use.
Exploration cases also assess whether a useful reframe survives and whether the
response fits the user's question. Report unmeasured changes as unmeasured.

Operators may use their own run store as a private evaluation corpus. Manifests
record mode, participants, timing, results, warnings, verification kinds,
predictions, and whether the view changed. Linking those records to private
driver transcripts requires the operator's access and permission. A public
behavior case or design lesson should not contain the underlying private record.

## Deliberate non-goals

- No direct peer-to-peer mesh or recursive councils.
- No required profile/configuration registry.
- No hard-coded model roster or small reasoning-token budget.
- No MCP or A2A dependency for local execution.
- No silent multi-model fan-out.
- No model-majority voting as final judgment.
- No default persona role-play.
- No implicit write, commit, push, deployment, or messaging authority.
- No durable background daemon or cross-process cancellation API in v1.
