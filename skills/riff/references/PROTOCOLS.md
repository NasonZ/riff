# Riff protocols

Read the relevant section before running a multi-turn discussion or a delegation.
The coordinator handles sessions and artifacts; this file covers request shapes,
continuation, recovery, and outcome records. For collaboration choices and their
reasons, use [the playbook](PLAYBOOK.md). The records and refusals described here
follow the habit set out in [the design](DESIGN.md#purpose-and-boundary): never
claim more than you can show.

## Contents

- [Common run contract](#common-run-contract)
- [Consult](#consult)
- [Discuss](#discuss)
- [Delegate](#delegate)
- [Several participants](#several-participants)
- [Record the outcome](#record-the-outcome)
- [Stopping](#stopping)
- [Failure and recovery](#failure-and-recovery)

## Common run contract

Keep request files outside the checkout and installed skill; they can contain
private task context. Pass their absolute paths to `validate` and `run`.

Every run has:

- an origin harness;
- one or more uniquely named participant instances;
- a mode and task;
- an explicit working directory and tool scope per participant;
- a bounded coordination policy; and
- durable artifacts and session handles.

Participant IDs identify instances, not models. `pi-a` and `pi-b` may use the same
Pi harness with different models, providers, thinking settings, or prompts.

Choose the tool scope from what the acceptance criteria require
(`RIF-AUTHORITY-002`):

- `none`: reasoning that needs no repository evidence;
- `read`: inspection of the working directory (add `params.add_dirs` for a Claude
  peer that must read elsewhere);
- `read+web`: inspection plus web search and fetch, for claims that must be checked
  against external sources (Claude and Codex peers);
- `write`: only when the user has authorised changes and the participant has an
  isolated worktree or writable directory.

A scope too narrow for the task does not fail loudly: the peer is denied, works
around the gap, and the run still settles. The run output lists `denied_tools`;
check it.

## Consult

Use consult for a single assessment or contribution: analysis, review, diagnosis,
reframing, or development of an idea.

Default flow:

1. Set `driver_position` to `withheld`, `provided`, or `none` according to the
   context you are sending. Quote the user's request in `user_request`, apart
   from your brief in `task`. Record an expectation or uncertainty in
   `driver_prediction` when useful; it is private to the driver record.
2. For an independent assessment, investigate and form your own view while the
   peer works; then collect one settled artifact from every participant.
3. Check material factual claims and assess proposals against the task's aims.
4. Record the checks, contribution, and remaining uncertainty, then synthesise.

When the user explicitly asks to critique a proposal, send the proposal on the
first turn with `driver_position: provided` and `driver_position_text`. The latter
is required; the coordinator includes it in the peer prompt and derives
`independent_first: false`. Do not add a ceremonial second turn to satisfy an
independence requirement the task does not have.

## Discuss

Use discuss for contested choices, evolving designs, critique, or exploration.
Choose whether the next contribution should develop possibilities, critique a
proposal, or resolve a decision; [the playbook](PLAYBOOK.md#choose-the-contribution)
explains the tradeoffs. These shapes share the same `discuss` mode. Use prose for
exploration and critique. When a discrete decision needs structured comparison,
request a `position` and unresolved `concerns`; a `CONSENSUS` label alone proves
nothing.

For an exploration with no prior position:

```json
{
  "version": 1,
  "mode": "discuss",
  "task": "Explore offline sync designs for a field-notes app. Researchers record observations and correct entries before reconnecting. Develop how their contributions could be preserved and presented; leave useful alternatives and open questions.",
  "origin_harness": "codex",
  "participants": [
    {"id": "claude-ideas", "harness": "claude", "cwd": "/repo", "tools": "read"}
  ],
  "driver_position": "none",
  "driver_prediction": "No preferred sync design yet; unclear which offline changes should coexist or need reconciliation.",
  "user_request": "Researchers keep losing corrections they make offline. What could sync look like?",
  "context_refs": ["docs/field-workflow.md"],
  "acceptance_criteria": ["Connect proposals to the field workflow; label assumptions about sync and researcher needs"],
  "out_of_scope": ["Implementing sync"]
}
```

If developing an existing driver proposal, use `provided` and include its text
instead. For independent comparison, collect isolated first-round artifacts before
sharing views. Follow up on the most useful opening or material disagreement in
the relevant native session; opaque extracts can help avoid prestige anchoring
when cross-reviewing several peers.

The default `max_rounds` is three settled turns per participant. Set
`coordination.max_rounds` (up to 20) when further turns are foreseeable. If the
budget is exhausted and another contribution is worth pursuing, use
`reply --extend-rounds N` to add N rounds to the run's cap, never above 20. The
manifest records the extension and the reply continues the same native session;
a new run would start a fresh session without that context. Stop sooner when
the user has enough to proceed or another round adds little. Preserve useful
alternatives and unresolved questions rather than forcing a decision. Use the
playbook's counterargument pass when agreement appears premature, not as a
mandatory extra round.

The driver mediates discussion. Participants do not recursively invoke Riff or
contact one another directly.

## Delegate

Use delegate when the desired result is an artifact or completed bounded task.
Write the seven-part contract from `PLAYBOOK.md` before launching the worker.

Available dispatch shapes:

- **Single**: one participant owns the task.
- **Broadcast**: several participants independently produce alternatives or
  analyses. Default only for read-only work.
- **Split**: participants receive distinct named subtasks.
- **Pipeline**: a declared artifact from one stage becomes input to the next.

Pipeline stages currently exchange local artifact paths, so every stage must share
the coordinator's filesystem. Use explicit content handoff instead when a future
adapter runs remotely.

For write-capable work:

- give each concurrent writer a distinct worktree or writable directory;
- keep repository metadata outside the worker's write authority where practical;
- have the driver review and integrate the diff; and
- do not let a worker commit, push, open a PR, or message external parties unless
  the user explicitly placed that action in scope.

If a task would duplicate writes across participants and no dispatch shape is
clear, stop before launching and clarify the decomposition.

A run blocks the caller until every participant settles, but prints its run ID on
stderr as soon as it starts. Wait on it for short work. For long work, or whenever
the driver's shell caps a single call, use `run --detach` and follow with bounded
`wait --run-id` calls; the detached run survives the driver's session, and `wait`
returns the same result JSON, next steps included. Do independent work in between
only when there is some; polling has a cost.

Allow for a tightening pass in the same native session when review finds a gap.
A delivery that meets the acceptance criteria does not need an extra turn.

Use discuss when the task needs conversational back-and-forth, or consult when the
output is not yet clear enough to specify. Delegation transfers a bounded task;
the driver remains responsible for its contract, assessment, and integration.

## Several participants

Use more participants only when diversity or parallelism has a concrete value.
The default consult has one peer. Do not silently fan out expensive calls because
several harnesses happen to be installed.

Useful combinations include:

- different model families answering independently;
- the same harness with different models or reasoning controls;
- the same model sampled twice to expose instability;
- one broad analysis followed by a focused verifier; and
- split repository inspection across disjoint areas.

Beyond about five concurrent participants, the driver's synthesis usually costs
more than the parallelism saves. Split larger work into sequential batches or
narrower questions.

A multi-peer discussion including two instances of the same harness:

```json
{
  "version": 1,
  "mode": "discuss",
  "task": "Compare the competing designs and surface decisive trade-offs.",
  "origin_harness": "codex",
  "participants": [
    {"id": "claude-a", "harness": "claude", "model": "sonnet", "cwd": "/repo", "tools": "read", "params": {"effort": "high"}},
    {"id": "qwen-local", "harness": "pi", "provider": "llama.cpp", "model": "qwen", "cwd": "/repo", "tools": "read"},
    {"id": "gemini-high", "harness": "pi", "provider": "google", "model": "gemini", "cwd": "/repo", "tools": "none", "params": {"thinking": "high"}}
  ],
  "coordination": {"dispatch": "broadcast", "independent_first": true, "max_rounds": 3},
  "driver_prediction": "Design B, unless the shared cache makes invalidation unsafe.",
  "user_request": "Which of the two designs should we build, and what would make you change your mind?"
}
```

Riff records each participant's harness, provider, and model; carry that identity
into the synthesis. During peer review, opaque labels can reduce prestige
anchoring, but the driver must retain provenance.
If several participants share a single-slot local inference endpoint, keep their
identities distinct but set coordinator concurrency to one.

## Record the outcome

Use `verify` after assessing the artifacts. It records checks and the driver's
outcome note; it does not turn an assessment of taste or usefulness into a factual
verification. Choose the record that matches what happened.

After inspecting a consult's decisive factual claim:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" verify --run-id <run-id> --verifier <you> \
  --result passed --check "Compared the migration-order claim with src/migrate.py" \
  --note "The concern is supported and changed my plan; implementation is pending."
```

With only `--check`, `--result` is required: `passed`, `partial`, or `failed` refers
to those named checks. The coordinator labels them `asserted`. State any remaining
unverified claims in the note rather than letting a passing check imply that the
whole artifact is correct.

For exploration where no factual or acceptance checks were performed:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" verify --run-id <run-id> --verifier <you> \
  --result not_performed \
  --note "I suggested separating observations from corrections; the peer developed the sync design and identified a correction arriving after reconciliation. Next: prototype that case. No prior preference or adoption; implementation and researcher comprehension untested."
```

This closes a pending record without claiming the ideas were verified. When you had
a prior view, say in the note whether the exchange changed it and why. A discussion
can be useful without changing a view or adopting a decision.

For delegated code, run the relevant acceptance checks and inspect the diff before
integration. Once the change is actually applied, record it, for example:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" verify --run-id <run-id> --verifier <you> \
  --run "python3 -m unittest -v" --check "Reviewed the parser diff" \
  --integrated --note "Applied the reviewed fix; adjacent refactor was left out."
```

`--run` executes commands and derives the result from exit codes unless an explicit
result is supplied. It rejects an explicit `passed` that contradicts a failing
command. `--integrated` is the driver's report of an applied change or adopted
decision, not a synonym for receiving an answer.

A record is bound to the answers it looked at. Each verification record
identifies the latest successful participant turns and artifact hashes available
when assessment starts, so a passing record for an earlier artifact does not
certify a new reply. Re-verifying preserves the prior record and writes its check
logs in a separate directory, so a later command does not replace earlier
evidence. A failed later attempt stays visible alongside any assessment of the
earlier artifact. The design explains
[why a check covers only what it saw](DESIGN.md#a-check-covers-the-answers-it-saw-and-nothing-later).

The returned `verification_scope` says where each participant stands. An attempt
is one try at a turn; the design defines the
[terms](DESIGN.md#state-and-observability) and draws
[the same sequence as a timeline](DESIGN.md#a-check-covers-the-answers-it-saw-and-nothing-later).

| Scope | The participant... |
|---|---|
| `unassessed` | succeeded on its latest attempt, and no verification is recorded yet |
| `covered` | succeeded on its latest attempt, and the latest verification record covers that turn |
| `uncovered` | succeeded on its latest attempt, and the latest verification record does not cover that turn |
| `failed` | did not succeed or never ran: its latest attempt failed, its launcher is confirmed dead mid-turn, a failed pipeline stage blocked it, or it has not started |
| `running` | has a turn in progress whose launcher is alive |
| `unknown` | cannot be assessed: a turn record or its artifact is unreadable, nothing establishes whether the launcher of an unfinished attempt is alive, or the latest verification record carries no coverage |

`covered_turns` identifies any earlier successful artifact included in the current
assessment, including after a failed attempt. That assessment may be
`not_performed`; earlier check results remain in `verification_history`.

`current` says whether the assessment matches the latest attempts. It does not
say that checks passed or that every participant succeeded:

- a new run is unassessed, with `current: false`;
- verifying after a failed attempt makes the assessment current without clearing
  that failure;
- a current `not_performed` record still means no checks were performed;
- any later attempt invalidates currency, whether it is newly reserved, successful
  or failed;
- so does a reply that overlaps executed checks: the record stays tied to its
  starting artifacts; and
- `current: null` means the scope is unknown. That happens when any participant's
  scope is `unknown`, and it includes incomplete assessment evidence, unreadable
  turn records and verification records written before coverage was recorded.

Start verification only once the run has settled. `not_performed` may acknowledge
an interrupted run without claiming that an orphan child settled or that checks
passed. A command run with `--run` is not isolated from the working directory:
another process can change files while it runs, so review the relevant diff and
environment as well as the exit code. Keep failures, corrections and reasons for
rejection: they are evidence for future evaluation as well as context for the
current user. Check logs overwritten by older versions of Riff cannot be
recovered from their recorded hashes.

## Stopping

A consult usually needs one settled artifact. Follow up when there is a useful
idea to develop, an ambiguity to examine, or a consequential claim to check.

End a discussion when the user has enough understanding or evidence for the
present purpose, another round adds little, the configured bound is reached, or
the user asks to stop. Name what remains open. Ending the exchange does not imply
that the inquiry or implementation is complete.

A disagreement about assumptions can still be investigated: work through a case
where they lead to different outcomes. If the remaining choice concerns the
user's aims or priorities, explain its consequences and ask them, rather than
spending more rounds trying to make the peers agree. Continue useful work that
does not depend on that choice. An explanation of the disagreement may itself
satisfy a request for understanding without producing a decision.

`CONSENSUS` text is not proof of convergence. For a discrete decision, inspect the
recommendation and unresolved concerns mechanically when structured output exists.
For exploration, do not force a consensus marker at all.

## Failure and recovery

Three guarantees hold however a turn ends. They are the driver's view of the
design's [state and observability](DESIGN.md#state-and-observability), which
gives the reasons.

**A failure is never reported as success.** A run where some peers failed and at
least one succeeded reports `partial`; where none succeeded it reports `failed`.
Name the missing or failed peers in your account, and never present your own
review as theirs.

**A follow-up reaches the session you mean.** `reply` uses the participant's
recorded session handle, never "the latest" session, so two runs cannot cross.

**An interrupted turn is resumed only on proof.** While a turn is unfinished,
`reply` is refused until its launcher is confirmed dead and one of two things is
true: the peer never passed
[the start gate](DESIGN.md#on-posix-a-peer-process-is-on-record-before-it-runs),
or its process group is confirmed gone. The design sets out
[each case](DESIGN.md#an-interrupted-session-is-resumed-only-on-proof-that-its-process-has-gone-or-never-ran).
Riff does not kill
orphans or retry by itself, and there is no override. A process that left its
recorded group is outside that proof.

| What happened | What to do |
|---|---|
| Timeout | A timeout is a failed turn, so it spends no round. Read the artifact first: if it is complete, treat it as the answer. If not, and its session survived, run the `reply` in `next_steps`; it asks for a concise final answer in the same session, with a longer bound. |
| `rate_limit` or `auth` | Do not retry unchanged: it fails the same way (`RIF-FAILURE-001`). Report the stated reset or the credential problem, or choose another peer. |
| Launcher died mid-turn (`interrupted`) | `wait` returns `interrupted` instead of hanging. Keep the turn's artifact, log and session handle. Check `status` or `progress` for the old peer's process group. Once it is confirmed gone, `reply` with a short note on what happened. While it is alive, check again later. If its state stays `unknown`, that participant cannot be resumed: start a new run. |
| `reply` refused as busy or running | Another operation owns that participant. Wait for it. |
| Your answer leaked into an independent first turn | Start a new run, which opens a fresh native session. A follow-up cannot undo the anchoring. |
| Rounds used up | `reply --extend-rounds N`, or synthesise. |

Limits:

- Failed turns do not spend a round, but attempts stop at twice the round budget,
  so a broken peer cannot loop.
- Proof that a process has gone exists on Linux only, within the launcher's boot
  and PID namespace. From a different namespace (another container, for example)
  or on another platform, an interrupted turn stays unknown however long you
  wait.
- A first Codex or Hermes turn that died before printing its session ID has no
  session to resume.
- Recovering one pipeline participant does not launch the queued ones.
- For Pi, `progress` shows whether the turn made progress before it timed out,
  and its session file must exist before a reply can resume it.
- There is no cancel command; bound turns with timeouts. `status`, `progress` and
  `wait` never change state.
- Older and previously migrated run records are rejected and left untouched.
  Inspect them with the version that wrote them.
