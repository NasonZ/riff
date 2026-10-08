---
name: riff
description: Coordinate one or more independent AI harness peers for consultation, discussion, or delegation. Use when the user explicitly asks to ask, consult, compare, debate, review with, or delegate to Claude Code, Codex, Pi, Hermes, Qwen, another model, multiple agents, or another instance of the same harness. Also use for a requested cross-model second opinion or roundtable. Do not trigger for ordinary solo work or incidental mentions of agents, models, CLIs, delegation, or debate.
---

# Riff collaboration

Bring model peers into the work to contribute an independent assessment, develop
an idea, challenge a framing, or complete a bounded task. Give each enough context
to contribute and room to change the direction of the work.

You are the driver: the agent the user is working with in this session. Your CLI
or app is the harness. Choose participants, mediate follow-ups, and take
responsibility for the conclusions and changes you bring back to the user. Driver
and peer are coordination roles, not capability ranks; either can find the better
framing.

The bundled coordinator handles processes, exact native sessions, artifacts,
timeouts, and records. Use it for operations an adapter supports. Those records
also support learning from real runs: preserve what was checked, what changed,
and what remains uncertain without forcing the conversation into a fixed report.

## Choose the contribution

Use the user's purpose to shape the request. An independent check needs your answer
withheld; critique needs the proposal itself; early exploration needs room to
extend possibilities before judging them. A useful result can be a better question
or an unresolved distinction, as well as a decision or a patch.

Engage with the peer's reasons: a distinction or connection may open a direction
neither of you started with. Follow up to develop what it enables, examine an
assumption, or find evidence that would distinguish the possibilities. Additional
turns and agreement are not themselves progress.

- **Consult**: an assessment or contribution, usually from one peer.
- **Discuss**: follow-up rounds to develop ideas or resolve questions; default
  three settled turns per participant, with no obligation to use every round.
- **Delegate**: a bounded artifact or task under an explicit contract.

Peer turns can take many minutes. Use them when another perspective or a separate
piece of work is worth that cost. Obey an explicit user roster. When asked only for
“another model,” pick one complementary available peer and say which. Do not fan
out simply because several harnesses are installed.

Match the model to the work as well as the perspective. A clear, bounded task may
suit a smaller or local model, leaving costly reasoning and driver context for
uncertainty and review. Account for briefing, retries, and verification when
judging the saving; see [delegation quality](references/PLAYBOOK.md#delegation-quality).

## Prepare the context

Set `driver_position` honestly:

- `withheld` for an independent assessment: send the question and evidence without
  your proposed answer. A later follow-up cannot undo initial anchoring.
- `provided` for critique or development of your proposal: put the current view in
  `driver_position_text`. Riff derives `independent_first: false`.
- `none` when you have no position to provide or withhold.

Use `driver_prediction` to record your starting expectation or uncertainty. It stays
in the driver record and is never sent to the peer. For exploration, “No preferred
sync design yet; unclear which offline changes should coexist or need
reconciliation” is a useful baseline. Do not invent a prediction or a change of
mind to complete a record.

Invite reframing and direct attention to the problem (“check for lost-update
races”) rather than assigning a persona. Assess factual claims by their evidence
and ideas by their reasoning and fit to the user's aims; confidence, model
reputation, and agreement do not establish either.

Resolve `RIFF_ROOT` to the directory containing this file. Load detail when needed:

- [references/PLAYBOOK.md](references/PLAYBOOK.md): choosing between exploration,
  critique, and independent assessment; handling disagreement or a consequential
  synthesis. The ordinary one-peer workflow is below.
- [references/PROTOCOLS.md](references/PROTOCOLS.md): multi-turn discussions,
  multiple participants, write delegation, or recording different kinds of outcome.
- [references/HARNESSES.md](references/HARNESSES.md): the relevant harness section
  when choosing adapter parameters, debugging, or recovering.
- [references/DESIGN.md](references/DESIGN.md): changing Riff or working with its
  traces and evaluation design.
- [references/NOTES.md](references/NOTES.md): reusable design lessons.

## Run

```bash
python3 "$RIFF_ROOT/scripts/riff.py" capabilities
python3 "$RIFF_ROOT/scripts/riff.py" validate --request request.json
python3 "$RIFF_ROOT/scripts/riff.py" run --request request.json
```

Review validation warnings before an expensive run: fix a real mismatch, or explain
why a heuristic does not apply. `run` returns artifact paths and `next_steps`; follow
that handoff even if the skill text has left your context. For long runs or shells
with a per-call limit, use `run --detach` and bounded `wait --run-id <id>` calls.
Repeat `wait` while it reports `running`; its default bound is about nine minutes.

A one-peer independent assessment (replace the paths with the task's real inputs):

```json
{
  "version": 1,
  "mode": "consult",
  "task": "Assess this design's assumptions. Explain any better framing.",
  "origin_harness": "claude",
  "participants": [
    {"id": "codex-review", "harness": "codex", "cwd": "/abs/repo", "tools": "read",
     "params": {"reasoning_effort": "high"}}
  ],
  "driver_position": "withheld",
  "driver_prediction": "Expect the cache invalidation path. A structural flaw would change the plan.",
  "context_refs": ["docs/design.md"],
  "acceptance_criteria": ["Support factual concerns with file:line evidence"],
  "out_of_scope": ["Implementation changes"]
}
```

Give every participant a unique `id`. Match tool scope to the task: `none` for
reasoning without tools, `read` for inspection, `read+web` (Claude and Codex) for
external sources, or `write` for authorized changes. Read the returned artifacts;
the run JSON is a handoff, not the peer's answer. `progress --run-id <id>` can
inspect a live run from another call.

## Continue or delegate

For example, a peer proposes merging offline edits to a shared field notebook.
Follow up to explore whether the data could have a simpler shape:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" reply --run-id <run-id> --participant <id> \
  --prompt "Could observations coexist as separate records, with corrections referring to earlier entries? Work through two offline corrections to the same entry and what the researcher would see after sync."
```

Follow the question that remains: develop a promising idea, examine a disagreement,
or correct a defect. Riff resumes the exact native session; never use “continue
latest.” For an independent multi-peer comparison, collect isolated first artifacts
before sharing excerpts, retaining provenance when using opaque labels.

For delegation, write the goal, context, inputs, output contract, authority,
`out_of_scope`, and acceptance checks before launching. If the output cannot yet be
specified, consult first. Read the delegation section of `PROTOCOLS.md` for dispatch
shapes. Put each code writer in its own linked git worktree so you can review its
diff and keep your changes separate. Claude write peers need explicit test-command
prefixes in `params.allowed_commands`. Riff never grants commit, push, PR,
messaging, or deployment authority implicitly.

## Assess, record, and respond

Check material factual claims against code, tests, or sources before relying on
them. Assess proposals against the user's aims and explain your judgment. A useful
idea is not thereby a verified fact. For a consult where you checked cited code:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" verify --run-id <run-id> --verifier <you> \
  --result passed --check "Compared the cited claim with src/parser.py" \
  --view-changed yes --note "The peer found a case my diagnosis missed; fix pending."
```

Record only what you did. `--run` executes a check and derives the result from exit
codes; `--check` records an inspection as asserted and requires `--result` when no
command runs. With no checks, use `--result not_performed --note "..."` to preserve
what the exchange contributed and what remains open. `--view-changed yes|no` records
a change to an existing view; omit it when not applicable and explain in the note.
Use `--integrated` only once you actually apply a change or adopt a decision.
Re-verifying preserves the prior record. See `PROTOCOLS.md` for further examples.

Lead with what the exchange makes possible for the user's work: a recommendation,
a useful question, a design to try, or a checked result. Attribute the peer's
contribution, explain what it changed or opened up, preserve material disagreement,
and distinguish checks from judgments and unknowns. Disclose denied access, failed
participants, and other limitations that affect the result. Give your resulting judgment or the
next useful question; a short consult can need only a few sentences. Keep a useful
outcome record even when the user-facing response is brief. Records are private
operator data: do not copy runs, transcripts, identifiers, or personal context into
public docs, fixtures, commits, or external services without explicit permission
for that disclosure.

## Gotchas

- **A timeout can leave a recoverable session.** Reply to the same participant with
  a short request to finish. Failed turns do not spend a round. The default turn
  timeout is 30 minutes; use the recovery command in `next_steps` to raise it.
- **Usage-limit and auth failures do not heal on unchanged retries.** Report the
  cause and the stated reset time when available, or select another peer within
  the user's scope. Never present your own review as the missing peer's work.
- **Denied tools leave silent gaps.** Check `denied_tools`. Inputs outside a Claude
  peer's cwd need `params.add_dirs`; a settled turn can still lack that evidence.
- **Codex as driver:** the default state directory may be outside its writable
  roots. See `HARNESSES.md` for sandbox and state-directory setup.
- **An older overlapping skill** can capture a trigger before Riff loads; see
  `HARNESSES.md` for migration.
- **A sandboxed Codex cannot commit from a linked worktree**; the driver handles
  authorized integration.
- **A backgrounded run can die with the driver session.** Use `run --detach` plus
  `wait` for long work. Never pipe Riff output to `tail`; SIGPIPE can kill the run
  when the invoking shell exits.
