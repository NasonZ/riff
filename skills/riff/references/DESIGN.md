# Riff design

Riff separates the judgment involved in collaboration from the mechanics of
running it. A shared Agent Skill guides what to ask, how to follow up, and how to
assess the result. A deterministic local coordinator manages peer sessions,
artifacts, failures, and records across supported harnesses.

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
a bounded task. The driver is responsible for the resulting judgment and
integration; any participant can contribute the better framing. Exploration can
end with a better question rather than agreement or a decision.

The skill guides the driver’s choices:

- when collaboration is worth its cost;
- how to elicit independent views;
- how to structure consultation, discussion, and delegation;
- how to resist persona and persuasion artifacts; and
- how to verify and synthesise.

The coordinator owns fragile mechanics:

- process launch and timeout;
- explicit native session identity;
- fan-out and pipeline ordering;
- artifact and log paths;
- recursive-invocation prevention;
- request linting and executed verification; and
- automatic run and turn records, including the driver's next steps.

Context compaction can remove the skill's text mid-session. The coordinator
therefore returns the driver's next steps with the result: read the artifact,
check the relevant claims, and report denied access. These obligations remain
available at the point where the driver needs to act. They are derived from the run
itself rather than generic: a delegation asks for acceptance checks and an
integration record, a consult asks for the claims checked and how the driver's
starting expectation or uncertainty developed (quoting the baseline back), a
failure names its recovery, and a run where no peer answered asks for an honest
`not_performed`. An inspection or exploratory contribution needs a different
record from an executable acceptance check.

Adapters compile the common contract into native harness operations. Riff does not
become another model provider registry, tool runtime, sandbox, or agent framework.

## Knowledge architecture

Each document serves a different stage of the work, from understanding a design
choice to applying it in a run:

```text
sanitised lesson / public research
            │
            ▼
         NOTES.md
 reusable rationale and caveats
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

Promote a lesson according to what it changes: record publication-safe rationale
in `NOTES.md`, explain durable judgment in `PLAYBOOK.md`, and put guidance needed on every run in
`SKILL.md`. Encode mechanical invariants in code and focused tests; evaluate
judgment through fresh-agent behaviour cases. Every lesson need not become an
instruction in every layer. Keep volatile harness flags in `HARNESSES.md` and
their executable contract in adapter tests. Keep private source evidence outside
the repository; a reusable lesson does not require publishing its source record.

References are available to readers and agents, but availability is not evidence
of use. `SKILL.md` routes the driver to relevant sections; the coordinator does not
automatically load the reference collection into every peer. A trace showing a
file read establishes access to its text, not understanding or application. Keep
the entrypoint sufficient for ordinary work, and use behavioural review to see
whether deeper guidance changes the decisions and contributions it was meant to
inform.

## Learning from runs

Run records belong to the operator and stay in their configured local storage.
They can support private review, candidate improvements, evaluation on separate
tasks, and deliberate adoption. Riff does not upload these records to this
repository or a shared dataset. Using a configured peer still sends its task and
context through that harness and provider; local record storage does not imply
local-only inference.

Skill optimisation and model post-training are distinct potential consumers.
[SkillOpt](https://github.com/microsoft/SkillOpt) edits skill text using scored
trajectories while keeping model weights frozen, with a held-out validation gate
for candidate changes. Curated demonstrations or preference examples could instead
support model post-training. Riff currently supplies neither an optimiser
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

The records do identify where that material lives. Each harness names its session
in the environment of commands it runs, so a run and each turn record the driver
session that launched them. The driver's own transcript holds the launching tool
call, whose result carries the run ID and each turn's artifact path. Each turn
also records the byte range it appended to the peer's native session file, with a
digest of that file at settle and its last entry ID; for Hermes, which stores
sessions in a database, it records the message IDs the turn added. An importer can therefore
nest each peer episode under the driver call that started it without matching
on timestamps or prompt text. A resumed turn whose start was not observed records
no start offset rather than claiming the whole file.

A future versioned export layer should assemble selected runs with recoverable
inputs, relevant artifacts and transcript excerpts, versions, outcome evidence,
and explicit missing-data markers. Exported content needs deliberate selection and
redaction rather than copying all ambient session history. The coordinator should
remain useful without an optimiser or training service.

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

- `RIF-EPISTEMIC-001` [F]: elicit independently before comparison.
- `RIF-EPISTEMIC-002` [R]: confidence is not evidence.
- `RIF-EPISTEMIC-003` [T]: record the starting expectation or uncertainty when useful.
- `RIF-SESSION-001` [F]: identify sessions explicitly.
- `RIF-DELEGATE-001` [F]: verify before integration.
- `RIF-DELEGATE-002` [R]: distinguish recorded execution from reported inspection;
  assess each check's relevance and scope.
- `RIF-AUTHORITY-001` [T]: do not expand authority implicitly.
- `RIF-AUTHORITY-002` [F]: match tool scope to the acceptance criteria.
- `RIF-AUTHORITY-003` [F]: bound every tool the scope does not name.
- `RIF-CONTEXT-001` [T]: prefer references and artifacts to transcript transfer.
- `RIF-FAILURE-001` [F]: classify a peer failure before retrying it.
- `RIF-COLLECTION-001` [F]: one installed skill owns each trigger.

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

Riff began as a Claude→Codex dyad. The earlier design coupled one driver, one peer,
one transport, and the collaboration guidance in a single skill:

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

In code, orchestration depends only on the normalised adapter boundary:

```python
class HarnessAdapter:
    def capability(self) -> dict: ...
    def execute(self, turn: TurnRequest) -> SettledTurn: ...
```

Adding a harness therefore does not add new pairwise Claude↔X, Codex↔X, or Pi↔X
paths. It adds one compiler from the common turn contract to that harness's native
protocol. `TurnRequest.is_reply` selects a new or continued native turn.

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

Each adapter implements `capability`, `start`, and `reply`, returning a normalised
settled turn with artifact, native session handle, usage when available, authority
enforcement level, and explicit failure.

Pi is the normal bridge to llama.cpp/vLLM because it supplies agent semantics above
their inference endpoints. A raw OpenAI-compatible adapter may be added later for
tool-free consultation, but must not claim repository-agent behaviour.

## State and observability

State defaults to `$XDG_STATE_HOME/riff` or `~/.local/state/riff`:

```text
runs/<run-id>/
├── run.json
├── participants/<participant-id>/...native state...
├── turns/<turn-id>.json
├── artifacts/<turn-id>.md
├── logs/<turn-id>.log
├── verification/<verification-id>/check-<number>.log
└── launch/{request.json,stdout.log,stderr.log}  # detached runs
```

Treat the state directory as private data, including artifacts, raw process logs,
verification output, and native sessions. Detached runs retain their complete
launch request in an owner-only `launch/request.json`. Credential-key redaction
applies to arbitrary participant `params`, execution `usage`, and `adapter_metadata`
dictionaries. Domain keys such as participant IDs and coverage maps are preserved.
Redaction does not sanitise arbitrary prose, paths, command output, or transcripts. Prompt hashes
in manifests do not make the other stored material anonymous or safe to publish.

Riff restricts its `runs/`, launch-input, and `codex-home/` directories to their owner
on POSIX systems when writing them. Public readers never create directories, change
permissions, or acquire writable locks. This does not
isolate peers running as that same user. Keep state outside source checkouts and
shared or automatically synced directories; use the operating system's access
controls where POSIX modes are not sufficient. The Codex home contains a filtered
copy of local configuration and links to authentication and cache data.

The coordinator has no telemetry or automatic record-upload service. Peer
harnesses use their configured providers and can transmit task context or use
network tools within their granted capabilities. Sharing or exporting records
requires explicit selection, review, and permission from the data owner.

`run.json` is the sole writable execution authority (`schema_version: 2`). It
contains static coordination metadata, ordered participant specifications and native
continuation handles, ordered attempt reservations/outcomes, initial dispatch and
launch disposition, and assessment history. Status, aggregate results, and round
counts are derived views rather than separately writable fields. Full launch
requests stay in the private launch-input file; ordinary prompt records contain
digests. Detailed terminal turn JSON, logs, and artifacts are evidence exports;
a terminal file alone cannot promote an uncommitted attempt to success. Turn records store a prompt digest, artifact
path and hash, native session handle, timing, usage, cost where the harness reports
it, permission denials, the checkout fingerprint at settle, and error, together
with the driver session and the turn's position in the native session file
described under [learning from runs](#learning-from-runs). Comparing the
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

Verification records have distinct identifiers and log directories. Their coverage
binds the assessment to participant turns and artifact hashes observed before
checks begin. Status derives currentness from the latest turns instead of storing
a flag that a reply could invalidate silently. A later failed attempt does not
erase evidence about an earlier artifact or inherit its passing result. A fresh
assessment can acknowledge that failure and become current while the participant
still shows as failed; this clears the reminder without inventing success. Missing
coverage or unreadable evidence leaves the assessment scope unknown.

The coordinator snapshots coverage under the run lock, executes commands without
holding that lock, and compares the current state when recording. A reply during
checks leaves the record tied to the starting snapshot. This protects attribution,
not the working tree: checkout fingerprints are limited observations, and neither
artifact hashes nor a passing command prove that files stayed unchanged. `status`
reads one atomically replaced control document without locking or writing. One
captured control snapshot feeds each response. Referenced evidence may disappear
independently and is then reported as unknown. Routine status uses the recorded
artifact hash and checks availability; it does not rehash current artifact contents.
A newly reserved attempt invalidates assessment currency before it has a terminal
file. Only `not_performed` may acknowledge an interrupted run with an unsettled
child; passing checks cannot certify an active orphan.

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
it just executed. These can differ even during initial fanout if a reply overlaps
another initial participant. `turn_result` and `ok` describe the operation just
performed; `result` and `status` describe the whole run, including pending dispatch
and newer replies. A successful follow-up therefore cannot
launder another participant's failure into overall success. Only settled turns
spend a participant's `max_rounds`; a failed turn being recovered does not, and
attempts are capped at twice the budget so a broken peer cannot loop. Every durable
reservation counts as attempted. Dependency-blocked pipeline work is a dispatch
disposition with failure evidence, and consumes no launched attempt.

For Pi, `progress` can inspect the RPC stream log and native JSONL while a turn is
active. Its default view exposes operational metadata (event and update counts,
block types, character counts, and tool names) without copying thinking or answer
text into coordinator output. The RPC log supplies low-latency deltas; the session JSONL
supplies durable continuation records and may lag until an assistant/tool boundary.
Short content previews require an explicit flag. `run` prints its run ID on stderr
before it blocks, so the run is addressable from a second shell at once; a
preallocated `--run-id` remains available for callers that want to choose it.
`run --detach` creates control state before spawning a gated coordinator and returns
`starting`. The worker validates its launch token and process identity before
claiming initial dispatch. A published living worker remains `starting` until that
claim. `wait` blocks for a bounded time (nine minutes by default), returning the
settled result, `starting`/`running`, or a truthful `interrupted`/`unknown` observation;
a failed startup includes captured stderr. A child backgrounded by a driver's
tool can otherwise die when the driver session ends. Choose wait bounds within
the calling harness's per-call limit.

All initial, pipeline, and reply execution uses one attempt lifecycle under a
participant ownership lock. Concurrent operations on the same participant fail
fast as busy. Lock ordering is participant lock, then a short run mutation lock;
execution and verification commands never hold the mutation lock. Reservations
carry a unique attempt ID, owner token, owner process identity, evidence baseline,
known session handle, and assigned paths. Observations and terminal commits require
the same current attempt, token, and active phase. Late evidence remains attached
to its own attempt and cannot overwrite another attempt or native handle. A null
terminal handle preserves an already observed handle.

Every attempt records its launch model before spawning. Native POSIX commands use
an isolated, constant Python exec trampoline that reads exactly one release byte
and exits on EOF. Child identity and running disposition are committed before
release. Native Windows commands use direct `Popen` so Riff retains the actual
native process handle and exit status; that model has no pre-release guarantee.
Unexpected direct-launch supervision or publication failures remain unproven even
when no child identity reached control. A normal native failed completion can
still be recorded as finished.

Detached coordinators use a direct Python child on all platforms. The internal
worker reads its release byte before any control mutation, then validates its
actual identity, claim token and request digest. EOF before release cannot claim
dispatch or start a native turn. Public manifest views omit the internal claim
token.

POSIX failure cleanup signals only an owned new-session group whose leader is
still unreaped. TERM, a bounded nonreaping grace period, and KILL all precede the
final wait. A zombie leader still pins its group ID, so leader exit alone never
skips KILL on a failure path. Already-reaped group IDs never authorise signals
from a `/proc` snapshot. Cleanup is idempotent; uncertain post-reap cleanup stays
unproven unless separate observations establish exit. Embedding hosts must leave
Riff child reaping to its owning `Popen`: external SIGCHLD handlers or `wait(-1)`
reapers must not reap those children. On Windows timeout cleanup targets the real
native process handle, with escalation; descendant-group cleanup is unproven.

After termination, pipe capture drains for at most half a second before closing;
a log marker records any inherited pipe still open at that limit. Escaped
processes are not signalled. Later output is unavailable, and background writers
may encounter a closed pipe. A successfully settled Pi process gets an orderly
shutdown period with concurrent output draining. Once it exits successfully, its
background group members are preserved. Normal exits of the one-shot adapters
also leave surviving descendants alone; they do not inspect or signal them.

Linux recovery identities include PID, start ticks, boot ID, and PID namespace.
Strong observations require the same PID namespace and boot as the launcher.
Recycled PIDs are distinct; zombies count as gone. A live member of the recorded
process group blocks recovery even if its leader exited. Foreign namespaces,
inaccessible identities, or missing identity fields mean unknown, never gone.
Processes that deliberately leave the recorded process group are outside this
proof. Other platforms have alive-only liveness hints for healthy execution;
absence or inaccessibility remains unknown. Non-Linux POSIX hints use signal zero
only for records without Linux identity metadata. Windows uses a safe process
handle query, never `os.kill(pid, 0)`. These hints support ordinary waiting and
never authorise recovery.

The three one-shot adapters use threaded streaming on Windows anonymous pipes.
Pi RPC remains POSIX-only. Native Windows and macOS execution have not been
validated by the Linux test suite. No automatic restart, orphan killing, or
recovery bypass is offered. Only a recorded exec-gated reservation with a confirmed
dead owner can use the never-released shortcut. Direct or unspecified launch
models need positive child/group exit proof; missing child identity stays unknown.
A running interrupted attempt likewise requires a confirmed dead owner, confirmed
child/group exit, and a known native handle before reply. Recovery records
interruption and reserves the next attempt atomically. Queued pipeline work is
never automatically continued after a crash.

Only current run records with complete attempt history are supported. Older and
previously migrated records are left untouched and rejected with an actionable
error. Inspect those archives with the version that created them; start a new run
for current work. There is no automatic migration or legacy counter reconstruction.

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
`--strict-mcp-config`, which uses only servers named by `--mcp-config`, and Riff
names none. Codex has no per-run equivalent, so Riff keeps a sanitised
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

Riff is a coordinator, not a hostile-agent containment boundary. Children inherit
the launching environment and use the operator's harness configuration and
credentials. A worktree separates edits but does not isolate a user's files,
processes, credentials, or network. Prompt-enforced limits and disabled web-search
tools do not establish an OS-level network boundary. For untrusted work, launch
the harnesses inside an appropriately isolated environment with selected inputs,
scoped credentials, and independently enforced network restrictions.

Artifacts, source files, web pages, and tool output may carry prompt injections.
The driver must assess their claims without promoting embedded instructions into
authority. Logs and after-the-fact review can aid detection; they cannot prevent
an action that already ran. Riff provides no synchronous security monitor, and
same-user processes may modify its state or the tests used for verification.
Artifact hashes and passing commands alone are not tamper-proof attestations.

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
prompts, weighted towards near-misses; rerun it after any description change.
`tests/behavior_cases.json` holds scenarios drawn from field failures and explicit
design aims, with their basis labelled and tied to observable expectations. Run
each with and without the change under test and judge the transcript and run
manifest rather than the driver's summary. Keep private results outside the
repository; publish only explicitly approved, sanitised findings. Passing
deterministic checks establishes the mechanics, not an improvement in model
behaviour. Compare old and new skills in fresh sessions across intended
drivers, inspecting contributions, synthesis, limitations, time, and token use.
Exploration cases also assess whether a useful reframe survives and whether the
response fits the user's question. Also examine whether the driver develops the
reframe's consequences, recognises when the purpose changes, and returns a choice
of aims to the user instead of resolving it by model agreement. Retaining a peer's
phrase or reporting `view_changed` does not establish any of these behaviours.

For discussion, inspect the exchange as well as its individual answers: what was
challenged, how the other participant answered, and what changed in the reasoning or
artifact. A first-answer defect does not establish that discussion cannot resolve
it; a repaired answer does not erase the original error or the cost of repair.
Distinguish a peer challenge from a self-review prompt. When evaluating a repair,
compare the revised work with the original objection and check whether it answers
it, rather than treating acknowledgement or agreement as resolution. A
counterexample, deduction, or better representation can advance the work using
evidence already available; additional retrieval or execution is needed when the
remaining claim requires it.

Where possible, follow the work beyond the immediate synthesis. A corrected claim
may still support an unsuitable deliverable; a passing targeted check may leave
the next stage blocked. Trace which contribution changed the later work and what
was independently checked there. Locate where an unsupported assumption entered
or a qualification was lost: the brief, the exchange, the driver's synthesis, or
subsequent implementation. Use that distinction to identify what may need
improving. Keep that account separate from a causal claim:
selected successful stories cannot establish an advantage over a strong solo
agent with the same evidence, tools, and budget. Report unmeasured changes as
unmeasured.

Operators may use their own run store as a private evaluation corpus. Manifests
record mode, participants, timing, results, warnings, verification kinds,
predictions, and whether the view changed. Linking those records to private
driver transcripts requires the operator's access and permission. A public
behaviour case or design lesson should not contain the underlying private record.

## Deliberate non-goals

- No direct peer-to-peer mesh or recursive councils.
- No required profile/configuration registry.
- No hard-coded model roster or small reasoning-token budget.
- No MCP or A2A dependency for local execution.
- No silent multi-model fan-out.
- No model-majority voting as final judgment.
- No default persona role-play.
- No implicit write, commit, push, deployment, or messaging authority.
- No durable background daemon or cross-process cancellation API.
