# Riff

Riff lets Claude Code, Codex, Pi, and Hermes consult, discuss, or delegate to one
another through one shared Agent Skill. Bring in a peer to notice something you
missed, develop an idea further, challenge the question, or take on a bounded task.

The current interactive harness is the driver. It gives peers context, follows up,
and takes responsibility for what it adopts. Any participant can change the
framing; being the driver does not make its first answer the right one.

For example, an exploratory exchange might look like this:

> **You:** Discuss this documentation idea with Codex. Help develop it before we
> choose a structure.
>
> **Peer contribution:** These readers may need different starting points: some
> want to accomplish a task, while others want to understand the underlying model.
>
> **Driver:** Would two entrances make readers choose before they know what they need?
>
> **Peer:** They might. The same reader could start with a task and need an
> explanation halfway through. Try a task walkthrough with explanations at those
> points, and compare it with separate entrances.

The follow-up turns an audience distinction into two concrete structures to try.
A review might instead uncover a defect; a delegation might deliver a patch with
checks the driver can run.

## Install one shared copy

Keep one source checkout and link it into the common Agent Skills directory:

```bash
git clone https://github.com/NasonZ/riff ~/src/riff
mkdir -p ~/.agents/skills ~/.claude/skills
ln -s ~/src/riff ~/.agents/skills/riff
ln -s ~/src/riff ~/.claude/skills/riff
```

Codex and Pi discover `~/.agents/skills`. Claude Code follows the Claude skill
symlink. Configure Hermes to trust the shared directory in `~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs:
    - ~/.agents/skills
```

Check which harnesses are available:

```bash
python3 scripts/riff.py capabilities
```

Riff requires Python 3.11+ with no third-party Python dependencies. Peers use their
installed harnesses and configured providers. If you have older peer skills installed, follow the
[migration notes](references/HARNESSES.md#migrate-overlapping-skills-safely) to
avoid competing triggers.

## Ask for a peer

In a fresh session, ask naturally:

- “Get Codex's independent take on why this test is flaky.”
- “Discuss this early idea with Claude and help me see what it could become.”
- “Have Pi investigate the parser failure, then check its findings.”
- “Delegate this fix to Codex in a worktree and review the result.”

Riff defaults to one peer. You can name several, select models or providers, or
ask for another instance of the same harness. **Consult** gets an assessment or
contribution; **discuss** continues through bounded rounds; **delegate** assigns a
task with an explicit scope and acceptance checks. The driver handles the request
format and coordinator commands.

## Why a skill and a coordinator?

The skill teaches the choices that make collaboration useful: when to withhold
your answer, when to share a proposal, how to develop an idea without forcing
agreement, and how to assess what comes back. The coordinator handles processes,
exact native sessions, artifacts, timeouts, tool scopes, and records. Follow-ups
return to the same peer session, and partial failures remain visible.

```text
current driver (Claude Code / Codex / Pi / Hermes)
                       │ shared Riff skill
                       ▼
                local coordinator
                 ├── Claude Code
                 ├── Codex
                 ├── Pi ── local or hosted models
                 └── Hermes
```

| Harness | Sessions | Model controls | Tool scopes |
|---|---|---|---|
| Claude Code | Explicit session UUID | model, effort, configured provider | none/read/read+web/write |
| Codex | Explicit thread ID | model, reasoning effort, OpenAI/local mode | sandboxed none/read/read+web/write |
| Pi | Persistent JSONL RPC | provider, model, thinking | none/read/write |
| Hermes | Explicit quiet-CLI session | provider, model, max turns | none/read; read is prompt-enforced; write disabled |

Use Pi for llama.cpp/vLLM-hosted models when tools and sessions are needed. See
[harness notes](references/HARNESSES.md) for controls and enforcement details.

## Learn from the work

Riff keeps run records in your configured local storage for your own use. It does
not upload them to this repository or a shared dataset. Your selected harnesses
and providers still process the task and context you send to peers.

Those records can help you improve future collaboration. Run and turn
records connect participants, artifacts, failures, usage, the driver's initial
expectations, and subsequent checks and decisions. They support field reviews and
skill optimization; curated trajectories could also support model post-training.

Those uses depend on distinguishing a completed turn from a correct answer, an
executed check from an asserted inspection, and an adopted idea from a verified
claim. The driver records what it actually checked and what the peer contributed.

The current records are an evidence index, not a self-contained training dataset:
reconstructing an exchange also needs its artifacts and available native/driver
transcripts. Riff does not automatically optimize skills or train models. See
[the learning-loop design](references/DESIGN.md#learning-from-runs) for the current
boundary and proposed next steps.

## Use the coordinator directly

Most users can let the driver handle this. For a direct consult, save a request as
`request.json`, replacing the working directory and context path with your own:

```json
{
  "version": 1,
  "mode": "consult",
  "task": "Assess this design's assumptions. Explain any better framing.",
  "origin_harness": "claude",
  "participants": [
    {"id": "codex-review", "harness": "codex", "cwd": "/absolute/project/path",
     "tools": "read", "params": {"reasoning_effort": "high"}}
  ],
  "driver_position": "withheld",
  "driver_prediction": "Expect migration ordering to be the main weakness.",
  "context_refs": ["docs/design.md"],
  "acceptance_criteria": ["Support factual concerns with file:line evidence"],
  "out_of_scope": ["Implementation changes"]
}
```

```bash
python3 scripts/riff.py validate --request request.json
python3 scripts/riff.py run --request request.json
```

Read the returned artifact files, then follow the result's `next_steps`. For a
consult where you inspected the cited code, a record might be:

```bash
python3 scripts/riff.py verify --run-id <uuid> --verifier claude \
  --result passed --check "Compared the migration claim with src/migrate.py" \
  --view-changed yes --note "The ordering concern holds; implementation is pending."
```

Only record that inspection after doing it. `--check` is an asserted inspection;
`--run` executes a check and records its exit code. Use `--result not_performed`
when nothing was checked, and `--integrated` only after applying a change or
adopting a decision. [Protocols](references/PROTOCOLS.md#record-the-outcome) cover
exploration, partial verification, and delegation.

`run` prints its ID on stderr before blocking. For long runs or a driver with a
per-call time limit, use `run --detach`, then bounded `wait --run-id <uuid>` calls.
Use `progress --run-id <uuid>` for live Pi metadata; `--previews` opts into content.
Continue with `reply --run-id <uuid> --participant <id> --prompt "..."`.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests cover request contracts, coordinator behavior, and fake harness processes.
Fresh-agent behavior checks are separate: passing a process test does not establish
that a model follows the skill well. See [testing strategy](references/DESIGN.md#testing-strategy)
and [isolated test seams](references/HARNESSES.md#diagnostics-and-test-seams).

Start with [the playbook](references/PLAYBOOK.md) for collaboration choices,
[protocols](references/PROTOCOLS.md) for operational detail, and
[design lessons](references/NOTES.md) for the rationale behind decisions.

Riff uses the MIT License.
