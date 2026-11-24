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
integration record, a consult quotes back each peer's stated limits and the user's
words and asks for the claims checked, a failure names its recovery, and a run
where no peer answered asks for an honest `not_performed`. An inspection or
exploratory contribution needs a different record from an executable acceptance
check.

One habit runs through both halves: never claim more than you can show. The skill
asks it of the agents, and the coordinator holds itself to it. It appears at four
levels, and each keeps apart two things that are easy to merge:

```text
level         kept apart
user          what they said            what the driver read into it
peer          what it checked           what it could not tell
driver        what it ran               what it only asserts
coordinator   what the record proves    what is unknown
```

Most of the rules below are this habit applied at one level. `user_request` and the
peer's closing limits serve the first two rows, the verification record the third,
and the attempt history the fourth;
[state and observability](#state-and-observability) takes the mechanics in turn.
Wherever Riff could round an uncertainty up to a fact, it records the uncertainty.

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

The four levels of [purpose and boundary](#purpose-and-boundary) run across those
documents. To follow one level through the repository, read along its row:

| Level | The agent's rule | The reasons | The mechanics | The commands |
|---|---|---|---|---|
| User: what they said, what the driver read into it | [Prepare the context](../SKILL.md#prepare-the-context) | [What the exchange is for](PLAYBOOK.md#what-the-exchange-is-for), [conversation shape](NOTES.md#conversation-shape) | [The request and the handoff](#the-request-and-the-handoff-keep-the-users-words-and-the-peers-limits-in-view) | [Consult](PROTOCOLS.md#consult) |
| Peer: what it checked, what it could not tell | [Assess, record, and respond](../SKILL.md#assess-record-and-respond) | [Persuasion and synthesis](PLAYBOOK.md#persuasion-and-synthesis), [handoffs](NOTES.md#handoffs-that-survive-lost-context) | [The request and the handoff](#the-request-and-the-handoff-keep-the-users-words-and-the-peers-limits-in-view) | [Common run contract](PROTOCOLS.md#common-run-contract) |
| Driver: what it ran, what it only asserts | [Assess, record, and respond](../SKILL.md#assess-record-and-respond) | [Verification and integration](PLAYBOOK.md#verification-and-integration) | [A check covers the answers it saw](#a-check-covers-the-answers-it-saw-and-nothing-later) | [Record the outcome](PROTOCOLS.md#record-the-outcome) |
| Coordinator: what the record proves, what is unknown | [Gotchas](../SKILL.md#gotchas) | [Recoverable sessions](NOTES.md#recoverable-sessions), [authority and observability](NOTES.md#authority-and-observability) | [State and observability](#state-and-observability) | [Failure and recovery](PROTOCOLS.md#failure-and-recovery), [shared invariants](HARNESSES.md#shared-invariants) |

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
- `RIF-CONTEXT-002` [F]: give the peer the user's own words apart from the driver's
  brief; peers built faithfully on a driver's misreading when the brief was all
  they saw.
- `RIF-SYNTHESIS-001` [F]: carry each peer's stated limits and "cannot tell"
  answers into the account to the user; agreement under one brief and rubric is
  agreement, not a verdict.
- `RIF-PROPORTION-001` [F]: in a series of reviews on the same work, the driver asks
  whether earlier additions still earn their place as well as what is missing;
  loops that only ask for gaps accumulate machinery. This is the driver's call, not
  a standing peer instruction, which would bias every review towards cutting.
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

This section gives the mechanics behind the table in
[purpose and boundary](#purpose-and-boundary). Most of it is the coordinator's
row: what the coordinator itself may say about a run. Riff reports what it
observed, and where it could observe nothing it reports `unknown`. It does not
round `unknown` up to `gone`, a finished-looking file up to a result, or a passing
check up to a verdict on a later answer.

Five guarantees follow, each with a subsection below:

1. One record is the authority; every status is derived from it.
2. On POSIX, a peer process is on record before it runs.
3. An interrupted session is resumed only on proof that its process has gone or
   never ran.
4. Riff signals only what it can prove it owns.
5. A check covers the answers it saw, and nothing later.

The running example is the smallest run there is: Claude, the driver, starts one
Codex peer called `codex-review`.

Five terms recur. A *turn* is one prompt to one participant and the answer to it.
An *attempt* is one try at a turn. A turn that completes without error is
*settled*, and a run is settled once every participant has finished, successfully
or not. A
*round* is a settled turn counted against `max_rounds`. The *owner* of an attempt
is the coordinator process that launched it; the protocols call it the launcher.

### One record is the authority; every status is derived from it

State defaults to `$XDG_STATE_HOME/riff` or `~/.local/state/riff`:

```text
runs/<run-id>/
├── run.json                  the control record: the only authority
├── participants/<participant-id>/...native state...
├── turns/<turn-id>.json      evidence: what one turn returned
├── artifacts/<turn-id>.md    evidence: the peer's answer
├── logs/<turn-id>.log        evidence: raw process output
├── verification/<verification-id>/check-<number>.log
└── launch/{request.json,stdout.log,stderr.log}  # detached runs
```

`run.json` (`schema_version: 2`) is the only file Riff writes as the authority on
what happened. It holds the static coordination settings, each participant's
specification and native session handle in order, an ordered list of attempts
with their outcomes, how the initial dispatch and launch went, and the history of
assessments. An *attempt* is one try at one turn: reserved before launch, running
once its process is on record, finished once its outcome is committed.

The record has no status field to go stale. Status, the aggregate result and the
round counts are views: Riff derives them on every read, from that history and
from what it can observe of the recorded processes and files at that moment. The
turn file, log and artifact are *evidence exports*: Riff writes them first and commits
the outcome to `run.json` second. A crash between the two leaves an interrupted
attempt with a finished-looking file beside it, and that file alone never
promotes the attempt to success.

Reading is safe at any time. `run.json` is replaced atomically, so `status` reads
one whole document without locking or writing, and one captured snapshot feeds
each response. The evidence a record refers to can disappear independently of it,
and is then reported as `unknown`. Routine status trusts the recorded artifact hash and checks
that the file is still there. It does not rehash the contents.

A turn record stores a prompt digest, the artifact path and hash, the native
session handle, timing, usage, cost where the harness reports it, permission
denials, the checkout fingerprint at settle, and any error, together with the
driver session and the turn's position in the native session file described under
[learning from runs](#learning-from-runs). Full launch requests stay in the
private launch-input file; ordinary prompt records hold digests. The dispatch
fingerprint is taken once, when the run is created, so a reply has none of its
own start. Comparing the
fingerprint taken at dispatch with the one taken at settle can reveal a changed
HEAD or dirty-file count. It cannot show that file contents stayed unchanged
while the peer was reading them.

A result reports the operation and the run separately. `turn_result` and `ok`
describe the operation just performed; `result` and `status` describe the whole
run, including pending dispatch and newer replies. The two can differ even during the
initial fan-out, if the driver replies to one participant while another's first
turn is still running. A
successful follow-up therefore cannot launder another participant's failure into
overall success.

Rounds are counted from the same history. Only settled turns spend a
participant's `max_rounds`; a failed turn being recovered does not, and attempts
are capped at twice the budget so a broken peer cannot loop. Every durable
reservation counts as an attempt towards that cap. Pipeline work blocked by a failed dependency is
recorded as a dispatch disposition with its failure evidence, and consumes no
launched attempt.

Only current run records with complete attempt history are supported. Older and
previously migrated records are left untouched and rejected with an actionable
error. Inspect those archives with the version that created them, and start a new
run for current work. There is no automatic migration and no reconstruction of
legacy counters.

### On POSIX, a peer process is on record before it runs

An *attempt* and its phases are defined under
[the first guarantee](#one-record-is-the-authority-every-status-is-derived-from-it).
Each harness's launch command is in [the harness notes](HARNESSES.md).

This rules out one failure: Riff dies, and a peer it started is still working
with nothing on disk to say which process it is.

```text
reserve    run.json gains attempt codex-review-001-3f2a9c1e, with    phase: reserved
           Riff's own process as owner, the session handle if one
           is known, and the paths the turn will write
spawn      Codex is started behind a gate and cannot run yet
record     the child's identity is written to the attempt            phase: running
release    the gate opens and Codex starts work
settle     Codex exits; Riff writes the turn file, then commits      phase: finished
           the outcome to run.json
```

The gate is a small, constant Python program, run in isolated mode, that reads
exactly one release byte and then replaces itself with the harness command. On
end-of-file, or any other byte, it exits. Riff writes the byte only after the
child's identity and its running state are committed. So a peer that is running
is on record, and a peer that is not on record never ran.

The guarantee stops at POSIX. On Windows Riff launches the harness directly with
`Popen`, which keeps the real native process handle and exit status. That model
has no gate, and so no guarantee before release: an unexpected failure while
supervising or publishing a direct launch stays unproven even when no child
identity reached the record. A normal
failed completion can still be recorded as finished. Every attempt records its
launch model before it spawns, because recovery depends on which one it was.

One lifecycle serves first turns, pipeline stages and replies, under a
per-participant ownership lock. A second operation on the same participant fails
fast as busy. Locks are taken in a fixed order, the participant lock and then a
short run-mutation lock, and neither peer execution nor a verification command
ever holds the mutation lock.

A reservation carries a unique attempt ID, an owner token, the owner's process
identity, an evidence baseline, the known session handle and its assigned paths.
Later observations and the terminal commit must present the same current attempt,
the same token and an active phase. Evidence that arrives late stays attached to
its own attempt and cannot overwrite another attempt or its native handle, and a
terminal result with no handle keeps the handle already observed.

Detached runs use the same handshake one level up, and on every platform.
`run --detach` creates the control record before it spawns the worker and returns
`starting`. The worker is a direct Python child with no gate program in front of
it: it reads its own release byte, which Riff writes only after publishing the
worker's identity, before any change to the record. It then validates its actual
identity, its launch token and the digest of the request before it claims the
initial dispatch. End-of-file before release
can neither claim dispatch nor start a native turn, and a worker that is alive
and published stays `starting` until it makes that claim. Public views of the
manifest omit the token.

To follow a run: `run` prints its run ID on stderr before it blocks, so the run
is addressable from a second shell at once, and a caller that wants to choose the
ID can preallocate it with `--run-id`. `wait` blocks for a bounded time, nine
minutes by default, and returns the settled result, `starting` or `running`, or a
truthful `interrupted` or `unknown`; a failed startup includes the captured
stderr. Detaching exists because a child backgrounded by a driver's tool can die
when the driver's session ends. Choose wait bounds within the calling harness's
per-call limit.

### An interrupted session is resumed only on proof that its process has gone or never ran

The gate and the attempt phases come from
[the previous guarantee](#on-posix-a-peer-process-is-on-record-before-it-runs).
What a driver does after a crash is in
[failure and recovery](PROTOCOLS.md#failure-and-recovery).

Riff observes a recorded process as one of three things: `alive`, `gone` or
`unknown`. `unknown` is an answer in its own right. It never counts as `gone`, and
it never authorises a resume.

Suppose Riff dies while `codex-review` is working. What `reply` may do next
depends on how far the attempt had reached:

```text
Riff died...                  phase; owner as observed   reply is...
before recording the child    reserved; gone             allowed, given a session handle:
                                                         the gate never opened
after recording the child     running; gone              refused until the peer's process
                                                         group is proved gone
after the turn file,          running; gone,             the same; the file is never
before the commit             a turn file on disk        linked to the attempt, and the
                                                         next reply records the attempt
                                                         as interrupted
Riff is alive, or its state   reserved or running;       refused: the turn may still
cannot be established         alive or unknown           be running
```

Every `gone` in this table is a Linux observation; no other platform reports one.

The phase is stored; the owner's state is observed each time the record is read.
A reply also needs a known native session handle, and the example shows why that
matters. Codex's thread ID is read from its output, so a first Codex turn that
died before printing it has nothing to resume. The same holds for Hermes. Claude
and Pi fix their session ID before launch. The shortcut in the first row, for a
peer that was never released, exists only for gated launches: a direct or unspecified launch model needs
positive proof that the child and its group exited, and a missing child identity
stays unknown. Recovery records the interruption and reserves the next attempt in
one atomic step. Riff offers no automatic restart, no orphan killing and no
bypass, and queued pipeline work is never continued automatically after a crash.

What counts as proof depends on the platform. On Linux a recovery identity includes
the PID, its start ticks, the boot ID and the PID namespace, and a strong observation needs
the same namespace and boot as the launcher. A recycled PID is therefore a
different process, and a zombie counts as gone. A live member of the recorded
process group blocks recovery even after its leader has exited. A foreign
namespace, an inaccessible identity or a missing identity field means `unknown`,
never `gone`. A process that deliberately leaves its recorded group is outside
the proof.

Other platforms give hints only, and their recorded identity is just a PID. A
non-Linux POSIX system probes it with signal zero, and only for records that
carry no Linux identity fields. Windows uses a
safe process-handle query, never `os.kill(pid, 0)`. A hint can say `alive`, which
is enough to keep waiting on a healthy run; absence or inaccessibility stays
`unknown`. Hints never authorise recovery, so on those platforms a turn whose
owner died stays `unknown` and that participant cannot be resumed.

### Riff signals only what it can prove it owns

The per-harness consequences are in
[shared invariants](HARNESSES.md#shared-invariants).

When a turn fails on POSIX, Riff cleans up the peer's process group, and it is
strict about which group that is. Each peer starts as the leader of a new
session. Riff signals that group only while the leader is still unreaped: an
unreaped leader pins its group ID, so the number cannot have passed to another
group. The sequence is TERM, a bounded grace period that does not reap, then
KILL, all before the final wait. A zombie leader still pins its group, so the
leader's exit alone never skips KILL on a failure path. Once a child has been
reaped, its group ID never authorises a signal, whatever a `/proc` snapshot
shows. Cleanup is idempotent, and cleanup that became uncertain after a reap
stays unproven unless separate observations establish the exit.

A host that embeds Riff must leave reaping to the `Popen` that owns each child:
an external SIGCHLD handler or a `wait(-1)` reaper must not reap those children.
Once something else has reaped a child, Riff can no longer prove the group is its
own, so it sends no signal and the group's exit stays unproven.
On Windows, timeout cleanup targets the real native process handle, with
escalation, while cleanup of that process's descendants is unproven.

Output capture is bounded on the same principle. After termination Riff drains
the pipes for at most half a second and then closes them, and a log marker
records any inherited pipe still open at that limit. Processes that escaped the
group are not signalled; their later output is unavailable, and a background
writer may meet a closed pipe. A Pi process that settles successfully gets an
orderly shutdown period with its output drained concurrently, and once it exits
successfully its background group members are preserved. The one-shot adapters
likewise leave surviving descendants alone on a normal exit: they neither
inspect nor signal them.

### A check covers the answers it saw, and nothing later

This is the driver's row of the table: what the driver ran, and what it only
asserts. The driver's rule is in
[SKILL.md](../SKILL.md#assess-record-and-respond), the reasons are in
[verification and integration](PLAYBOOK.md#verification-and-integration), and the
commands and their output fields are in
[record the outcome](PROTOCOLS.md#record-the-outcome).

The coordinator emits its records automatically. The driver adds only what it
verified and what it integrated, and an empty, explicit `not_performed` is
preferable to a fabricated successful check.

Checks come in two kinds (`RIF-DELEGATE-002`). A `--run` command is executed by
the coordinator, which records its exit code, duration, output hash and output
tail. With only executed checks the result is derived from the exit codes, and a
claimed `passed` that contradicts a failing command is rejected. A `--check`
string is recorded as `asserted`: the driver's statement, honestly labelled and
never presented as executed.

Each verification record has its own identifier and log directory, and is bound
to what it looked at: the participant turns and artifact hashes observed before
the checks began. That binding is its *coverage*. Whether the record is *current*
is derived from the latest attempts each time status is read. It is deliberately
not a stored flag, which a later reply could invalidate silently.

```text
codex-review answers (turn 1)        unassessed    current: false
the driver verifies                  covered       current: true
the driver replies; turn 2 arrives   uncovered     current: false
                                     the pass on turn 1 stands and says
                                     nothing about turn 2
the driver verifies again            covered       current: true
```

The timeline assumes that turn 2 succeeds and that nothing changes while the
checks run. While turn 2 is running the scope reads `running`; if it fails,
`failed`.

A later failed attempt neither erases the evidence about an earlier artifact nor
inherits its passing result. A fresh assessment can acknowledge that failure and
become current while the participant still shows as failed; the record is then
current without inventing success. Missing coverage or unreadable evidence leaves
the assessment scope `unknown`.

The procedure protects attribution. Riff snapshots coverage under the run lock,
executes the commands without holding it, and compares the current state when it
records. A reply during the checks leaves the record tied to its starting
snapshot, and a newly reserved attempt invalidates currency before it has a
terminal file. The working tree is another matter: checkout fingerprints are
limited observations, and neither an artifact hash nor a passing command proves
that files stayed unchanged.

Verification needs a settled run, with one exception. Only `not_performed` may
acknowledge an interrupted run with an unsettled child, or a run that failed to
start; a passing check cannot certify an active orphan.

### The request and the handoff keep the user's words and the peer's limits in view

These are the user's and the peer's rows of the table. The driver's rules are in
[SKILL.md](../SKILL.md#prepare-the-context), and the reasons are in
[what the exchange is for](PLAYBOOK.md#what-the-exchange-is-for) and
[persuasion and synthesis](PLAYBOOK.md#persuasion-and-synthesis).

`validate` and `run` return
lint warnings for valid requests that tend to waste or bias a run:

- a delegation without acceptance criteria or out-of-scope items;
- persona wording;
- the driver's view inside a withheld task;
- a consult or discussion without the user's words in `user_request`;
- a task that needs the web given a scope without it;
- a context file a Claude peer cannot read;
- a write peer in a main checkout rather than a worktree; and
- fan-out beyond five participants.

These are heuristics, so they warn and do not reject: each pattern has legitimate
exceptions, and every message names its remedy.

The peer prompt places `user_request`, the user's words as the driver quoted them,
above the driver's brief, and asks the peer to say where the brief departs from
them (`RIF-CONTEXT-002`). Consult and discuss peers are also asked to close with a
"Limits and open conditions" section. After a turn, `next_steps` quotes that
section, or names its absence, and echoes the user's words, so both are in front
of the driver as it writes to the user (`RIF-SYNTHESIS-001`); a follow-up in those
modes asks for the section again. The manifest keeps `user_request` in clear, as it
does `driver_prediction`, because `next_steps` quotes it; the task itself stays a
digest.

`driver_prediction` is stored in the manifest and never sent to a peer. It commits
the driver to a view before it reads the peer's, and the verify note records
whether that view changed (`RIF-EPISTEMIC-003`). The field may state uncertainty
instead; `driver_position: none` represents no prior position and does not require
a prediction. A useful exploration with no checks can record `not_performed` and
its contribution in `note`, without claiming verification.

A turn that timed out after writing its artifact reports the bytes written, and
the driver reads them before recovering the session. The record still shows the
turn as failed; treating the artifact as the answer is the driver's judgement.
Only a timeout is treated this way: other failures can leave error text in the
artifact.

### State stays local and private to its owner

What the records can and cannot be used for is under
[learning from runs](#learning-from-runs); what a peer is allowed to do is under
[authority](#authority).

Treat the state directory as private data, including artifacts, raw process logs,
verification output and native sessions. Detached runs retain their complete
launch request in an owner-only `launch/request.json`. Redaction replaces the
values of credential-shaped keys in arbitrary participant `params`, execution
`usage` and `adapter_metadata` dictionaries, and preserves domain keys such as
participant IDs and coverage maps. It does not sanitise arbitrary prose, paths,
command output or transcripts, and the prompt hashes in a manifest do not make
the other stored material anonymous or safe to publish.

On POSIX systems Riff restricts its `runs/`, launch-input and `codex-home/`
directories to their owner when it writes them. Public readers never create
directories, change permissions or acquire writable locks. None of this isolates
peers running as that same user. Keep state outside source checkouts and shared
or automatically synced directories, and use the operating system's access
controls where POSIX modes are not sufficient. The Codex home contains a filtered
copy of local configuration and links to authentication and cache data.

The coordinator has no telemetry and no automatic record-upload service. Peer
harnesses use their configured providers and can transmit task context, or use
network tools, within their granted capabilities. Sharing or exporting records
requires explicit selection, review and permission from the data owner.

### A live Pi turn can be watched without copying its text

For Pi, `progress` can inspect the RPC stream log and the native JSONL while a
turn is active. Its default view exposes operational metadata (event and update
counts, block types, character counts and tool names) and copies no thinking or
answer text into coordinator output; short content previews require an explicit
flag. The RPC log supplies low-latency deltas, while the session JSONL supplies
durable continuation records and may lag until an assistant or tool boundary.

### The guarantees are strongest on Linux

| Platform | Launch | Cleanup on failure | Recovery after a crash |
|---|---|---|---|
| Linux | behind the gate | the owned process group, while its leader is unreaped | on proof of exit, within the launcher's boot and PID namespace |
| Other POSIX | behind the gate | the same | none: liveness hints only |
| Windows | direct, keeping the real process handle and exit status | through that handle; descendants unproven | none: liveness hints only |

The three one-shot adapters use threaded streaming on Windows anonymous pipes,
and Pi RPC remains POSIX-only. Native Windows and macOS execution have not been
validated by the Linux test suite.

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
phrase or reporting a changed view does not establish any of these behaviours.

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
predictions, and the driver's outcome notes. Linking those records to private
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
