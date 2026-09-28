---
name: riff
description: Coordinate one or more independent AI harness peers for consultation, discussion, or delegation. Use when the user explicitly asks to ask, consult, compare, debate, review with, or delegate to Claude Code, Codex, Pi, Hermes, Qwen, another model, multiple agents, or another instance of the same harness. Also use for a requested cross-model second opinion or roundtable. Do not trigger for ordinary solo work or incidental mentions of agents, models, CLIs, delegation, or debate.
---

# Riff collaboration

Coordinate independent peers without treating any harness or model as the
authority. The current interactive harness is the driver: it chooses participants,
mediates follow-ups, verifies claims, and synthesizes. The bundled coordinator owns
processes, sessions, artifacts, timeouts, and records; do not hand-roll native CLI
calls for anything an adapter supports.

## Load the relevant knowledge

Resolve `RIFF_ROOT` to the directory containing this file. Read only what the
decision in front of you needs:

- [references/PLAYBOOK.md](references/PLAYBOOK.md) — before a consequential consult,
  a multi-peer synthesis, or a delegation whose output will be integrated.
- [references/PROTOCOLS.md](references/PROTOCOLS.md) — discussions, several
  participants, stopping, write-capable delegation.
- [references/HARNESSES.md](references/HARNESSES.md) — only the section for the
  harness you are choosing parameters for, debugging, or recovering.
- [references/DESIGN.md](references/DESIGN.md) — when changing Riff itself.
- [references/NOTES.md](references/NOTES.md) — why a decision was made; field
  evidence.

## Keep the peer relationship honest

A second model is worth consulting only when its view is independent and its claims
are checked. So:

- Withhold your own answer when the point is a second opinion (`driver_position:
  withheld`); a shared view anchors the peer and cannot be unshared in a follow-up.
  When the task is to critique your proposal, send it as `provided` and never call
  the result independent.
- Record what you expect before consulting (`driver_prediction`); it is stored,
  never sent, and lets the synthesis say honestly whether the peer changed your view.
- Invite the peer to reject the question's framing. Direct its attention ("check
  for lost-update races"); do not give it a persona.
- Weigh evidence, not fluency, confidence, agreement, or model reputation. Driver
  and worker are coordination roles, not capability ranks.

## Decide whether and how to use it

Peer turns are slow and costly: Codex peers took a median 11 minutes per turn in the
field, Claude peers about 4. Do not use Riff for questions answerable in one read,
to avoid thinking the problem through yourself, or for first drafts, where a critic
pulls toward premature convergence. It is not coding-only: strategy, research
framing, and naming decisions often benefit most.

- **Consult** — one or more independent analyses. Default to one peer.
- **Discuss** — bounded, driver-mediated rounds with explicit native sessions;
  default three settled turns per participant.
- **Delegate** — a bounded artifact or task under a written contract.

Obey an explicit user roster. When asked only for "another model," pick one
complementary available peer and say which. Never fan out silently because several
harnesses are installed.

## Run

```bash
python3 "$RIFF_ROOT/scripts/riff.py" capabilities
python3 "$RIFF_ROOT/scripts/riff.py" validate --request request.json
python3 "$RIFF_ROOT/scripts/riff.py" run --request request.json
```

Fix what `validate` warns about before an expensive run; each warning names the
remedy. `run` prints a `started` line with the run ID on stderr before it blocks,
and its final JSON carries `next_steps` — follow them even if these instructions are
no longer in your context.

```json
{
  "version": 1,
  "mode": "consult",
  "task": "Find the strongest unsupported assumption in this design.",
  "origin_harness": "claude",
  "participants": [
    {"id": "codex-review", "harness": "codex", "cwd": "/abs/repo", "tools": "read",
     "params": {"reasoning_effort": "high"}}
  ],
  "driver_position": "withheld",
  "driver_prediction": "Expect the cache invalidation path. A deeper structural flaw would change the plan.",
  "context_refs": ["docs/design.md"],
  "acceptance_criteria": ["Cite file:line for each concern"],
  "out_of_scope": ["Do not propose a rewrite of the storage layer"]
}
```

Give every participant a unique `id`. Match tool scope to the acceptance criteria,
not just the risk: `none`, `read`, `read+web` (Claude peers only) to check external
sources, or `write` with explicit user authority. Read the artifact files; the run
JSON is a handoff, not the answer. For long turns, `progress --run-id <id>` inspects
a live run from another call. Several-peer requests are in `PROTOCOLS.md`.

## Continue a discussion

```bash
python3 "$RIFF_ROOT/scripts/riff.py" reply --run-id <run-id> --participant <id> \
  --prompt "Here is the competing argument. What changes your view, if anything?"
```

Riff resumes the exact native session; never use a harness's "continue latest".
Target follow-ups at unresolved evidence rather than replaying the conversation, and
continue a correction in the same session instead of starting a fresh run that
pretends to remember. For cross-review, collect isolated artifacts first, then send
opaque excerpts while keeping real provenance in your synthesis.

## Delegate

Write the contract before launching: goal, context references, inputs, output
contract, authority, `out_of_scope`, and `acceptance_criteria` you will actually
run. If you cannot write the acceptance criteria, consult first. Use `single`,
`split` (a distinct `participant.task` each), `pipeline` (a declared artifact feeds
the next stage), or `broadcast` for read-only alternatives only.

Put each writer in its own linked git worktree, not the main checkout, so you can
review its diff before integrating and your own edits cannot be swept into its
commit. Let a
Claude write peer run tests with `params.allowed_commands` (for example
`["uv run pytest"]`); without it the shell is denied. Riff never grants commit,
push, PR, messaging, or deployment authority implicitly.

## Verify and synthesize

Do not tell the user anything is verified until a check has run. Then record it:

```bash
python3 "$RIFF_ROOT/scripts/riff.py" verify --run-id <run-id> --verifier <you> \
  --run "uv run pytest -q" --check "Read the diff of src/parser.py" \
  --view-changed no --integrated
```

`--run` commands are executed and their exit codes recorded; the result is derived
from them, and a claimed `passed` that contradicts a failing command is rejected.
`--check` records something you inspected as asserted, never as executed. Use
`--result not_performed` when you checked nothing, and `--integrated` only once you
have actually applied the result (changed files, adopted the decision). Re-verifying
keeps the earlier record.

Report to the user in this shape, not as pasted peer output or a vote count:

```text
Riff <mode>: <participant = harness/model> · independence <withheld|provided>
Expected: <driver_prediction> · Changed my view: <yes/no — what did it>
Agreement · Disagreement · Decisive evidence
Verified: <executed checks> | Asserted: <inspections> | Not verified: <claims>
Peer limits: <denied tools, timeouts, missing participants>
Judgment: <yours>
```

## Gotchas

Each of these happened in real runs (`NOTES.md`, September 2026 field review).

- **A timeout is not a lost session.** Reply to the same participant with a short
  "write your final answer now"; all four field timeouts recovered that way, and a
  failed turn does not spend a round. The default turn timeout is 30 minutes; raise
  `timeout_seconds` for long delegations.
- **Usage-limit and auth failures do not heal on retry.** `error_type` `rate_limit`
  states the reset time; `auth` means fix credentials or pick another peer. Tell
  the user; never substitute your own review under the peer's name.
- **Denied tools leave silent gaps.** The run output lists `denied_tools`; say what
  the peer could not access. A context file outside a Claude peer's cwd needs
  `params.add_dirs`.
- **Codex as driver:** its sandbox makes the default state directory read-only;
  request escalation for `riff.py` or pass the same `--state-dir` to every command.
- **An older overlapping skill** (for example a legacy `codex` skill) can capture
  the trigger before Riff loads; see `README.md` for migration.
- **A sandboxed Codex cannot commit from a linked worktree**; the driver commits.
- **Background runs:** redirect output to a file; piping to `tail` can kill the
  child with SIGPIPE when the invoking shell exits.
