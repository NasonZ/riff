# Riff

Two models can know much of the same material and still approach a problem
differently. A distinction, analogy, or objection from one can give the other a
new direction to explore. Riff is built around that exchange: bringing different
semantic spaces into conversation, with room for either participant to change
the framing.

Inspired by Andrej Karpathy's [LLM Council](https://github.com/karpathy/llm-council),
which combines independent responses, peer review, and synthesis, Riff brings
collaboration into ongoing agent work. Claude Code, Codex, Pi, and Hermes can
consult, discuss, or delegate to one another through one shared Agent Skill.

You stay in the conversation with the agent you're already using. Ask it to bring
in a peer, and it gives that peer the context it needs in a separate session. It
reads the response and follows up: perhaps to develop a promising idea, question
an assumption, or work through a disagreement. Either participant can suggest a
different direction.

We call your coordinating agent the **driver**. Its job is to bring the exchange
back to you with a considered view: what each participant contributed, what it
recommends and why, and what still needs checking. If a peer delivers code, the
driver reviews the changes and checks the result before integrating it. A clear
task can also go to a smaller or local model, leaving expensive model calls and
the driver's context available for the parts that need them.

Take an illustrative example: you're building a field-notes app with Claude Code.
Its users need to record observations and correct entries while they're offline.
When their devices reconnect, those changes need to come together without losing
anyone's work. You ask Claude to explore the design with Codex. Here's how that
riff might unfold:

> **You:** Work through the offline sync design with Codex before we implement it.
> We mustn't silently lose anyone's observations.
>
> **Codex:** We could use a CRDT—a data structure that merges concurrent edits—so
> researchers can edit the same notebook offline. We'd still need to decide how
> conflicting corrections should appear.
>
> **Claude, to Codex:** Do these all need to be edits to shared state? Two people
> recording different observations should keep both. A correction needs to say
> which earlier entry it corrects. Could we sync those records without merging
> their text?
>
> **Codex:** Yes: give each observation its own ID and make corrections new records
> referring to it. Devices exchange records; the notebook view assembles them.
> That avoids a general text-merge engine. But two corrections to the same entry
> can still disagree—we've preserved the conflict, not resolved it.
>
> **Claude, to Codex:** Then show both corrections and let a researcher reconcile
> them. Does that choice also need to survive another offline edit?
>
> **Codex:** Record which corrections the reconciliation considered. If another
> arrives later, it remains visibly unresolved. Otherwise a delayed sync could
> silently make a decision look more complete than it was.
>
> **Claude, to you:** Codex proposed automatic merging; I suggested separating
> observations from corrections. Its follow-up exposed the delayed-correction
> case. I'd first prototype two devices correcting the same entry, then a third
> correction arriving after reconciliation. That will exercise the proposed
> sync rules; we still need to see whether researchers understand the history.

The useful move is from “merge edits” to “preserve observations and corrections.”
That changes which solutions are worth considering. Following its consequences
then reveals the delayed-correction case to investigate. The
[playbook](references/PLAYBOOK.md#develop-an-idea) shows how to develop such an
opening; the [design rationale](references/NOTES.md#inquiry-across-perspectives)
connects it to inquiry, perspective-taking, and the limits of model agreement.

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
cd ~/src/riff
python3 scripts/riff.py capabilities
```

Riff requires Python 3.11+ with no third-party Python dependencies. Peers use their
installed harnesses and configured providers. If you have older peer skills
installed, follow the [migration notes](references/HARNESSES.md#migrate-overlapping-skills-safely) to
avoid competing triggers.

## Ask for a peer

In a fresh session, ask naturally:

- “Get Codex's independent take on why this test is flaky.”
- “Discuss this early idea with Claude and help me see what it could become.”
- “Discuss with Claude what we could learn from a prototype versus an experiment.”
- “Have Pi investigate the parser failure, then check its findings.”
- “Delegate this fix to Codex in a worktree and review the result.”

Riff defaults to one peer. You can name several, select models or providers, or
ask for another instance of the same harness. **Consult** gets an assessment or
contribution; **discuss** continues through bounded rounds; **delegate** assigns a
task with an explicit scope and acceptance checks. The driver handles the request
format and coordinator commands.

What you share changes the task. Withhold your diagnosis to ask for an independent
explanation; share your draft to ask for critique; supply the aims and constraints
when you want to develop an idea without a preferred answer. These choices leave
different openings for the peer, without deciding what it will conclude. See
[choosing the contribution](references/PLAYBOOK.md#choose-the-contribution).

More discussion does not by itself make an answer better. Models can share a blind
spot or persuade one another into a mistake. Riff asks the driver to engage with
the peer's reasons, pursue useful differences, and check consequential claims
against evidence. An exploration may instead leave you with a better question or
a possibility worth trying. [Research and limits](references/NOTES.md#research-and-limits)
explains the basis for these choices and what remains unmeasured.

## Match the model to the work

Discussion can sharpen an idea into a plan another model can execute. A capable
driver can work through the uncertain parts, then give a smaller model a bounded
task with the relevant inputs, constraints, and acceptance checks. Clear
instructions make more work suitable for delegation; they also make the result
easier to assess.

For example: “Work out the change with Claude, then have Pi use my local Qwen
model to implement it in a worktree. Review the diff and run the agreed checks.”
Riff supports explicit model and provider choices, including local inference
through Pi; the driver makes the routing decision.

This can reduce paid inference and, when the smaller model and hardware suit the
task, finish the work faster. The peer's tool calls and intermediate work stay in
its own session; the driver reads the result and inspects supporting material as
needed, preserving space in its context for the wider task. Judge the savings
over the completed task, including briefing, follow-ups, retries, and verification.
See [delegation quality](references/PLAYBOOK.md#delegation-quality) for the contract
and [local inference](references/HARNESSES.md#local-inference-servers) for setup.

## Why a skill and a coordinator?

The skill teaches the choices that make collaboration useful: when to withhold
your answer, when to share a proposal, how to develop an idea without forcing
agreement, and how to assess what comes back. The coordinator handles processes,
exact native sessions, artifacts, timeouts, tool scopes, and records. Follow-ups
return to the same peer session, and partial failures remain visible.

Each agent runs through a **harness**: the CLI or app that gives it tools and
manages its session. Riff connects these harnesses through a local coordinator.

```text
your agent (in Claude Code / Codex / Pi / Hermes)
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

When did a peer change the direction of the work? Which follow-ups developed an
idea, and which merely prolonged agreement? Riff's run and turn records give you
material to investigate these questions: participants and models, artifacts,
failures, usage, the driver's starting expectation or uncertainty, and subsequent
checks and decisions.

Their value depends on distinguishing a completed turn from a correct answer, an
executed check from an asserted inspection, and an adopted idea from a verified
claim. The skill asks the driver to record only what it checked and what the peer
contributed. Riff labels reported inspections as asserted and commands it ran as
executed. A rejected suggestion can be worth revisiting for the reasoning that
ruled it out.

Records stay in your configured local storage for your own use. Riff does not
upload them to this repository or a shared dataset. Your selected harnesses and
providers still process the task and context you send to peers. Sharing the
records requires your explicit permission.

They can inform private field reviews and, with curation, skill optimization or
model post-training. The current records are an evidence index, not a self-contained
training dataset: reconstructing an exchange also needs its artifacts and available
native/driver transcripts. Riff does not
automatically optimize skills or train models. See
[the learning-loop design](references/DESIGN.md#learning-from-runs) for the current
boundary, evaluation on separate tasks, and proposed next steps.

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
