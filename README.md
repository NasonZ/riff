# Riff

*There are places your thinking hasn't been yet.*

Riff lets the agent you're working with bring in another. Claude Code, Codex, Pi,
and Hermes can consult, discuss with, or delegate to one another through one
shared Agent Skill, each peer in its own session. Your agent follows up on what
comes back, then tells you what changed and what still needs checking.

Suppose you're building a field-notes app with Claude Code. Researchers record
observations and correct entries offline, and nothing may be lost when their
devices reconnect. You ask Claude to work through the sync design with Codex:

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

A single second opinion would have ended at the CRDT. The follow-up changed what
was being synced, and that exposed the case worth prototyping first. Riff is built
for that follow-up; Andrej Karpathy's [LLM Council](https://github.com/karpathy/llm-council),
which combines independent responses, peer review, and synthesis, inspired it.

Your agent is the **driver**. It carries the exchange, checks consequential claims,
and answers to you for what it brings back. A peer that writes code works in its
own worktree, and the driver reviews the diff before integrating it.

[Install Riff](#install-one-shared-copy) · [Ask for a peer](#ask-for-a-peer) ·
[Match the model to the work](#match-the-model-to-the-work)

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

Riff needs Python 3.11+ and no third-party packages; peers use your installed
harnesses and configured providers. If older peer skills are installed, follow
the [migration notes](references/HARNESSES.md#migrate-overlapping-skills-safely)
so they don't compete for the same requests.

## Ask for a peer

In a fresh session, ask naturally:

- “Get Codex's independent take on why this test is flaky.”
- “Discuss this early idea with Claude and help me see what it could become.”
- “Have Pi investigate the parser failure, then check its findings.”
- “Delegate this fix to Codex in a worktree and review the result.”

One peer is the default. Name several for a roundtable, choose models or
providers, or ask for a second instance of the same harness. **Consult** asks for
an assessment, **discuss** continues over bounded rounds, and **delegate** hands
over a scoped task with acceptance checks.

What you share shapes the answer: withhold your diagnosis to get an independent
one, share a draft to have it critiqued, or give only the aims and constraints to
explore. More rounds don't make an answer right. Models share blind spots and can
talk each other into mistakes, so the driver weighs reasons and checks evidence
rather than counting agreement. See
[choosing the contribution](references/PLAYBOOK.md#choose-the-contribution) and
[research and limits](references/NOTES.md#research-and-limits).

## Match the model to the work

Once discussion has turned an idea into a bounded task, a smaller or local model
may be enough: “Work out the change with Claude, then have Pi use my local Qwen
model to implement it in a worktree. Review the diff and run the agreed checks.”
The peer's tool calls stay in its own session, leaving the driver's context for
the wider task. Judge the saving over the whole task, including briefing, retries,
and review. See [delegation quality](references/PLAYBOOK.md#delegation-quality)
and [local inference](references/HARNESSES.md#local-inference-servers).

## How it works

The skill carries the judgment: what to withhold or share, how to develop an idea
without forcing agreement, and how to assess the result. A local coordinator
handles the mechanics: processes, exact native sessions, artifacts, timeouts, tool
scopes, and records. Follow-ups return to the same peer session, and failures stay
visible. Each agent runs in a **harness**, the CLI or app that gives it tools and
a session.

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

Use Pi for llama.cpp/vLLM-hosted models. [Harness notes](references/HARNESSES.md)
cover controls and enforcement.

## Records stay local

Each run records its participants and models, artifacts, failures, usage, the
driver's starting expectation, and what the driver later checked or adopted. The
records stay in your local state directory, and Riff uploads nothing; the
harnesses you choose still send peers the task and its context. They let you
review when a peer changed the work, but they are an evidence index, not a
training dataset. See
[learning from runs](references/DESIGN.md#learning-from-runs).

## Use the coordinator directly

The driver normally writes requests for you. For a direct consult, save this as
`request.json` with your own paths:

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

Read the artifact files it returns, then follow its `next_steps`. After checking
the cited code, record what you did:

```bash
python3 scripts/riff.py verify --run-id <uuid> --verifier claude \
  --result passed --check "Compared the migration claim with src/migrate.py" \
  --view-changed yes --note "The ordering concern holds; implementation is pending."
```

`--check` records an inspection as asserted; `--run` executes a command and
records its exit code. Use `--result not_performed` when nothing was checked.
For long runs, use `run --detach` and then bounded `wait --run-id <uuid>` calls;
continue with `reply`. [Protocols](references/PROTOCOLS.md) cover the rest.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests cover request contracts, coordinator behavior, and fake harness processes;
they don't show that a model follows the skill well, which needs fresh-agent
checks. See [testing strategy](references/DESIGN.md#testing-strategy).
[The playbook](references/PLAYBOOK.md) explains the collaboration choices and
[design lessons](references/NOTES.md) the reasoning behind them.

Riff uses the MIT License.
