# Riff design

Riff is a shared Agent Skill plus a deterministic local coordinator for
cross-harness collaboration. It preserves the original project's accumulated
epistemic and delegation knowledge while generalizing the original Claude→Codex
dyad into a driver-neutral, multi-participant system.

## Contents

- [Purpose and boundary](#purpose-and-boundary)
- [Knowledge architecture](#knowledge-architecture)
- [Coordination topology](#coordination-topology)
- [Contracts and adapters](#contracts-and-adapters)
- [State and observability](#state-and-observability)
- [Authority](#authority)
- [Testing strategy](#testing-strategy)
- [Deliberate non-goals](#deliberate-non-goals)

## Purpose and boundary

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
- recursive-invocation prevention; and
- automatic run and turn records.

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
always-active     mode-specific
     │               │
     └──────┬────────┘
            ▼
 coordinator/adapters + focused tests
```

Promote a lesson rather than merely moving text: observation → general principle →
runtime rule → executable invariant → regression test. Keep volatile harness flags
in `HARNESSES.md` and their authoritative behavior in adapter tests.

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

`run.json` stores coordination metadata, task digest, references, status, and driver
verification. It does not duplicate full prompts or artifacts. Turn records store a
prompt digest, artifact path/hash, native session handle, timing, usage, and error.

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
items, persona wording, the driver's view inside a withheld task, an
independent-first run without a `driver_prediction`, and fan-out beyond five
participants. They warn rather than reject because each pattern has honest false
positives. `driver_prediction` is stored in the manifest and never sent to a peer;
with `verify --view-changed` it makes "did consulting change the decision?" a
recorded fact rather than a recollection (`RIF-EPISTEMIC-003`).

An initial `run` returns both the aggregate run result and the result of the turns
it just executed; these are identical on round one. A later `reply` keeps them
separate: `turn_result` describes that reply, while `result` is recomputed across
the latest state of every participant. A successful follow-up therefore cannot
launder another participant's failure into overall success.

For Pi, `progress` can inspect the RPC stream log and native JSONL while a turn is
active. Its default view exposes operational metadata—event/update counts, block
types, character counts, and tool names—without copying thinking or answer text
into coordinator output. The RPC log supplies low-latency deltas; the session JSONL
supplies durable continuation records and may lag until an assistant/tool boundary.
Short content previews require an explicit flag. Preallocated run UUIDs make the
run addressable from a second shell before the blocking `run` command settles.

Participant mutations use per-participant advisory locks, run aggregates use a run
lock, and JSON state is written through unique fsynced temporary files followed by
atomic replacement. This prevents concurrent replies from exceeding their round
bound or corrupting shared manifests.

## Authority

Tool scope has four shared values: `none`, `read`, `read+web`, and `write`.
`read+web` is read-only file access plus outbound network fetch (web search and
URL fetch); it grants no write, shell, or edit authority. Adapters report
whether the scope is native, sandboxed, or prompt-enforced, and each adapter
supports only the scopes it can enforce natively — unsupported scopes fail
closed at command construction (as of this writing only Claude Code supports
`read+web`, via `WebSearch`/`WebFetch` in its `--tools` allowlist). Riff does
not imply authority from a mode name.

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
`tests/behavior_cases.json` holds scenarios drawn from field failures, each tied to
a rule and to observable expectations; run each with and without the change under
test, judge the transcript and run manifest rather than the driver's summary, and
keep private results outside the repository; publish only approved, sanitized lessons. A change that does not move a behavior case is not yet
justified by evidence.

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
