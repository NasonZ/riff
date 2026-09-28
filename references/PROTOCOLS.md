# Riff protocols

Read the relevant section before running a multi-turn discussion or a delegation.
The coordinator handles sessions and artifacts; these protocols govern what to ask
and how to interpret the result.

## Contents

- [Common run contract](#common-run-contract)
- [Consult](#consult)
- [Discuss](#discuss)
- [Delegate](#delegate)
- [Several participants](#several-participants)
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
  against external sources (Claude peers only);
- `write` — only when the user has authorized changes and the participant has an
  isolated worktree or writable directory.

A scope too narrow for the task does not fail loudly: the peer is denied, works
around the gap, and the run still settles. The run output lists `denied_tools`;
check it.

## Consult

Use consult for one-shot independent analysis, review, diagnosis, or reframing.

Default flow:

1. Record `driver_prediction`, then send the task and necessary evidence without
   the driver's proposed answer.
2. Collect one settled artifact from every participant.
3. Inspect claims and evidence.
4. Compare with the recorded prediction.
5. Verify material claims, record the verification, and synthesize.

When the user explicitly asks to critique a proposal, send the proposal on the
first turn and record `driver_position: provided`. Do not add a ceremonial second
turn just to satisfy independent-first.

## Discuss

Use discuss for contested choices, evolving designs, critique, or exploration.
Riff preserves the useful distinctions from its original roundtable modes without
making them separate public commands:

- **Convergence** — a concrete decision is required. Track the current
  recommendation and unresolved dissent. Structured output fits this shape: ask
  for a `status` (`CONSENSUS` or `CONTINUE`), the current `position`, and the
  unresolved `concerns`, and read those fields rather than parsing a suffix.
- **Critique** — improve a concrete artifact. Preserve prose and stop when no
  material concern remains. Do not force a schema: real critique interleaves
  observations, questions, and counter-proposals, and a position/concerns split
  flattens it.
- **Exploration** — understand a space rather than force agreement. Stop when
  marginal insight falls or the round budget is reached. Some peers default to
  critique even here. Say so plainly: “we are exploring, not converging — extend
  the idea rather than critique it.” If the reflex persists, that peer is the
  wrong tool for this conversation; tell the user rather than grinding on.

Pick the shape that matches the conversation; do not default to convergence
because it is the most structured. Before declaring convergence on a discrete
decision, the devil's-advocate pass in `PLAYBOOK.md` is the cheap check that the
agreement is real.

Default flow:

1. Obtain independent first-round artifacts.
2. Let the driver identify the most important divergence.
3. Send targeted follow-ups to the relevant native sessions.
4. Optionally show opaque peer extracts for cross-review.
5. Stop after at most three settled turns per participant (the default
   `max_rounds`) unless the user requests more.
6. Synthesize; do not use a majority vote as a substitute for judgment.

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
stderr as soon as it starts. Wait on it for short work. For long work, background it
with output redirected to a file and inspect it with `progress --run-id`, but only
when the driver has genuinely independent work to do; backgrounding has a
bookkeeping cost.

Expect delegation to take two turns: a first delivery, then a tightening pass
through the same native session.

A delegation is the wrong shape when the task needs conversational back-and-forth
(discuss instead), when it is the driver's own work being avoided, or when the
driver cannot write a clean contract (consult first, then delegate the clarified
task).

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

## Stopping

Stop a consult after the first settled artifact unless a specific ambiguity needs
a reply.

Stop a discussion when any of these holds:

- the action-relevant disagreements are resolved;
- remaining disagreement is explained by values or assumptions rather than facts;
- another round produces no material new evidence;
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
participant asking for a concise final answer; in the field every timed-out turn
was recovered this way. Failed turns do not spend `max_rounds`, so recovery never
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
