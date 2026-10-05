# Riff protocols

Read the relevant section before running a multi-turn discussion or a delegation.
The coordinator handles sessions and artifacts; this file covers request shapes,
continuation, recovery, and outcome records. For collaboration choices and their
reasons, use [the playbook](PLAYBOOK.md).

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

- `none` — reasoning that needs no repository evidence;
- `read` — inspection of the working directory (add `params.add_dirs` for a Claude
  peer that must read elsewhere);
- `read+web` — inspection plus web search and fetch, for claims that must be checked
  against external sources (Claude and Codex peers);
- `write` — only when the user has authorized changes and the participant has an
  isolated worktree or writable directory.

A scope too narrow for the task does not fail loudly: the peer is denied, works
around the gap, and the run still settles. The run output lists `denied_tools`;
check it.

## Consult

Use consult for a single assessment or contribution: analysis, review, diagnosis,
reframing, or development of an idea.

Default flow:

1. Set `driver_position` to `withheld`, `provided`, or `none` according to the
   context you are sending. Record an expectation or uncertainty in
   `driver_prediction` when useful; it is private to the driver record.
2. Collect one settled artifact from every participant.
3. Check material factual claims and assess proposals against the task's aims.
4. Record the checks, contribution, and remaining uncertainty, then synthesize.

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

The default `max_rounds` is three settled turns per participant. Stop sooner when
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

- **Single** — one participant owns the task.
- **Broadcast** — several participants independently produce alternatives or
  analyses. Default only for read-only work.
- **Split** — participants receive distinct named subtasks.
- **Pipeline** — a declared artifact from one stage becomes input to the next.

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
  "driver_prediction": "Design B, unless the shared cache makes invalidation unsafe."
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
  --view-changed yes --note "The concern is supported; implementation is pending."
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

This closes a pending record without claiming the ideas were verified. Omit
`--view-changed` when there was no prior view to compare; when there was one, record
`yes` or `no` and explain the contribution. A discussion can be useful without
changing a view or adopting a decision.

For delegated code, run the relevant acceptance checks and inspect the diff before
integration. Once the change is actually applied, record it, for example:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" verify --run-id <run-id> --verifier <you> \
  --run "python3 -m unittest discover -s tests" --check "Reviewed the parser diff" \
  --integrated --note "Applied the reviewed fix; adjacent refactor was left out."
```

`--run` executes commands and derives the result from exit codes unless an explicit
result is supplied. It rejects an explicit `passed` that contradicts a failing
command. `--integrated` is the driver's report of an applied change or adopted
decision, not a synonym for receiving an answer. Re-verifying preserves the prior
record. Keep failures, corrections, and reasons for rejection: they are evidence
for future evaluation as well as context for the current user.

## Stopping

Stop a consult after the first settled artifact unless a specific ambiguity needs
a reply.

Stop a discussion when any of these holds:

- the action-relevant disagreements are resolved;
- remaining disagreement is explained by values or assumptions rather than facts;
- another round produces no useful development, distinction, or material evidence;
- the configured round bound is reached; or
- the user asks to stop.

`CONSENSUS` text is not proof of convergence. For a discrete decision, inspect the
recommendation and unresolved concerns mechanically when structured output exists.
For exploration, do not force a consensus marker at all.

## Failure and recovery

Surface participant failure without laundering it into overall success. A run may
settle with partial results when at least one participant succeeds; the synthesis
must name missing or failed perspectives.

Use explicit native session handles for follow-ups. Never select “the latest”
session when two runs can coexist.

If a process is interrupted:

1. Determine whether it is still running before starting another instance.
2. Preserve its artifact, log, and native session handle.
3. Resume the native session with a short situational message.
4. Restart only when the session cannot be recovered.

If an intended independent-first prompt accidentally included the driver's answer,
start a fresh native session. A follow-up cannot undo the initial anchoring.

A timeout is a failed turn, not necessarily a lost session. Reply to the same
participant asking for a concise final answer when its native session remains
recoverable. Failed turns do not spend `max_rounds`, so recovery never
costs the discussion a round; attempts are capped at twice the round budget. For Pi,
`riff.py progress` shows whether the turn made progress before it timed out, and the
native session file must exist before a reply can resume it.

Classify a failure before retrying it (`RIF-FAILURE-001`). `rate_limit` and `auth`
fail identically on an unchanged retry: report the stated reset or the credential
problem, or choose another peer, and never present a self-review as the missing
peer's. A `reply` to a participant whose turn is still running is refused; if the
coordinator that launched it has died, the turn counts as interrupted and can be
resumed.

Riff v1 does not expose a separate cross-process cancellation command. Use bounded
turn timeouts, and treat an interrupted driver as a recovery event: confirm whether
each child is still alive before resuming or restarting it. A future durable runner
must make cancellation reach every child and record it per participant.
