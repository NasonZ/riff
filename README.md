# Riff

When one agent reads a problem, you get one reading, and you cannot see what it
filled in. An underspecified request gets completed anyway, and the result looks
finished whether or not the agent understood you. Riff lets the coding agent you
are working with bring in a second agent, briefed from the sources and without the
first agent's answer. Where the two readings differ, you have somewhere to look.
Where they agree, you still check what matters. You direct what is worth
investigating and decide what the difference means.

Riff is engineered diligence: the ordinary habits of a careful colleague, written
down as rules the agents follow.

Your agent is the **driver**: it briefs the second agent, reads what comes back,
follows up and answers for the result. The second agent is the **peer**. Each runs
in a harness: the CLI or app, such as Claude Code or Codex, that gives an agent its
tools and session. Claude Code, Codex, Pi and Hermes share one Agent Skill and a
local coordinator, which launches peers and keeps the records. A peer keeps its own
session, which the driver can return to, so an exchange develops over several turns
instead of restarting from a retelling.

A riff is one such exchange: a brief, separate readings, a comparison, and an
account that comes back to you with what is yours to settle. It might catch a
mistake, develop an idea, or change what you need to find out before you build.

![A notebook sketch turns from circle to cone to triangle, unfolds to reveal a straight path, then folds back with the path intact.](assets/riff-sketchbook.avif)

[What a riff looks like](#what-a-riff-looks-like) ·
[Ask for a peer](#ask-for-a-peer) ·
[What the driver does](#what-the-driver-does) ·
[How it works](#how-it-works) · [Install](#install)

## What a riff looks like

*A synthetic exchange. Watch what each participant takes "slow" to mean.*

> **You:** CI is slowing development down. Before we pay for more runners, you and
> Codex look at the workflow and recent runs separately. Help me understand what
> would actually improve the working day.

*Claude briefs Codex with the workflow, the retained run logs and the question,
without its own diagnosis, and investigates while Codex works.*

> **Claude, first assessment:** The integration tests set the length of a clean
> run. Splitting them across jobs would shorten the wait for all checks to pass,
> at the cost of repeated setup.
>
> **Codex:** Queueing matters too, especially when several revisions arrive at
> once; more capacity would help there. But job length and queue time don't tell us
> which waits actually interrupt development.

> **You:** While the agent is implementing, I rarely wait for a full run. What hurts
> is coming back after review, finding a failure, and going round another
> edit-and-check cycle. Look at that.

> **Claude, to Codex:** Then we should follow failed changes through to their fix,
> rather than rank jobs by length. What would tell a capacity problem from a
> feedback problem?
>
> **Codex:** Trace when the change was pushed, when the first useful failure
> appeared, when the fix was pushed, and when everything passed. If useful
> failures arrive late, running failure-prone tests earlier may help. If they
> arrive early but take several attempts to diagnose, faster runners fix only part
> of the delay. Either way, the full suite stays the acceptance check.

> **Claude, to you:** My first proposal targeted the longest job. Codex's reading and
> your account of the working day give us a better measure: time to a useful next
> action, alongside time until everything passes. I'll reconstruct a few failed
> changes before proposing any change. The logs can establish the timings; which
> delays mattered is your call.
>
> **You:** Show me those first. Then we'll choose what to try.

Neither first assessment was careless; each measured a real part of the wait. The
request had left open what "slow" meant, and the two readings filled that gap with
different measures. Their difference gave you somewhere to look, and you supplied
the meaning. The same applies beyond CI: before optimising a measure, ask which
decision it is meant to serve.

The shape of that riff:

```text
you       ask: the purpose, the constraints, what is worth investigating
           │
driver     briefs the peer from the sources, its own answer withheld
           ├──────────────────────────────┐
           ▼                              ▼
           investigates                   peer investigates
           │                              │
           └──────────── compare ─────────┘
                           │
           a difference: somewhere to look
           agreement: still check what matters
                           │
you       decide what the difference means and direct the next step
```

The separate first readings were a **consult**. The follow-up became a
**discussion**. **Delegation** would follow once the investigation has named a
change worth trying and the checks that would test it. That arc is typical: Riff suits
work whose criterion still has to be discovered, and a riff often ends with the
check that makes handing the work over safe. Use follows checkability elsewhere
too: across 207,049 research sessions, scientists used Claude two to four times
more than their time on a task would predict where success is easy to verify and
feedback is fast, and barely at all where it is not
([Anthropic, 5 November 2026](https://www.anthropic.com/research/how-researchers-use-claude#how-use-relates-to-capabilities)).
Other riffs start elsewhere: a critique of a draft, an early idea taken further, or
a task already ready to hand over.

## Ask for a peer

Ask your agent in plain language and it takes the driver's part. Driver and peer
are roles, not ranks; either may find the better approach. Choose the mode by the
contribution you want from the peer: an assessment, an idea developed, or a piece
of work finished. One task can use more than one mode:

| Mode | Use it for | Example |
|---|---|---|
| **Consult** | A separately formed assessment, or a single contribution | "You and Codex each diagnose this failure. Keep our current guess out of its brief." |
| **Discuss** | Developing an idea or tracing a disagreement through follow-up | "Work through this design with Claude. Show me what each approach makes possible and what we still need to check." |
| **Delegate** | A bounded task with an agreed output and checks | "Have Pi use my local Qwen model to write the script that pulls last week's slow requests out of the gateway logs into a CSV, in a worktree. Check its output against the three requests we timed by hand before you hand it back." |

One peer is the default. You can name the harness, model and provider;
if you ask only for "another model", the driver chooses one available peer and
tells you which. Discussions allow three completed turns per participant by
default, failed turns not counted; the request can set another bound, and the
driver can stop sooner.

Delegate when the brief can state the goal, context, inputs, expected output,
authority, exclusions and acceptance checks. For code changes, the driver gives
the worker a separate worktree, reviews the diff and runs the checks before
integrating; a gap found in review goes back to the same worker session. A
bounded task may suit a smaller or local model, whose tool calls stay out of the
driver's context; assess any saving across briefing, retries and review.

Several peers can investigate the same question independently, work concurrently
on named subtasks, or run as a pipeline in which one response becomes the next
input. More peers and more rounds do not themselves mean progress; beyond five
participants the coordinator warns that synthesis usually costs more than the
extra answers return.

See [choosing the contribution](skills/riff/references/PLAYBOOK.md#choose-the-contribution),
[delegation quality](skills/riff/references/PLAYBOOK.md#delegation-quality) and
[several participants](skills/riff/references/PROTOCOLS.md#several-participants).

## What the driver does

In the example, the two readings could differ because Codex's brief carried the
sources and not Claude's diagnosis, and the difference was worth following because
the request had left "slow" open. Both followed Riff's rules, the habits of a
careful colleague made explicit: get a second reading before committing, keep it
independent, ask for reasons when the readings differ, and say what was assumed
when the request left a gap. Riff adds structure, so the habits hold under time
pressure and leave a record.

The skill states the habits to the agents as rules, in the order a riff runs: what
goes into the brief, how the driver works while the peer does, what happens with
what comes back, and what returns to you. They hold in every mode, whether a
consult asks for an independent assessment or a critique, a discussion takes an
idea further, or a delegated task comes back as a diff. Each rule answers a
particular way an exchange goes wrong. The evidence is summarised here and examined
with its limits in
[research and limits](skills/riff/references/NOTES.md#research-and-limits).

**Say what was assumed.** Before anything is briefed, the driver separates what you
asked from its reading of it, and where competing readings would change the work it
says so rather than building one of them into every participant's brief. The gap a
request leaves is the first place an exchange goes wrong. Across 20,574 coding-agent
sessions, Tang et al. attributed about 15% of the identified misalignment episodes
to underspecified instructions ([revised 31 August 2026](https://arxiv.org/html/2605.29442v2)).
On Ambig-DS's prediction-target suite, tested frontier agents silently chose
unintended targets in 39–63% of ambiguous runs
([Stoisser et al., 10 May 2026](https://arxiv.org/html/2605.09698)). In both
studies an agent that filled a gap seldom said so.

**Brief from the sources.** The peer receives the goal, the constraints, its
authority and the original material, not the driver's summary of them. In a
controlled study, summaries passed between agents kept the facts but dropped the
rules for using them, and a handoff that stated the rules explicitly was respected
far better downstream ([Wang et al., Aug 2026](https://arxiv.org/abs/2608.29028)).
What else the brief carries depends on the contribution wanted. For a critique it
carries the proposal; for a discussion, the aims and the idea to develop; for an
independent assessment it leaves the driver's diagnosis out, because a peer that
has read it is checking it rather than forming its own. The driver's own
expectation goes in the private record either way.

**Choose the peer for the contribution.** A bounded task may suit a smaller or
local model; a different assessment wants a different family. Rubric-based judges
favour their own and their family's outputs
([Pombal et al., revised 3 August 2026](https://arxiv.org/html/2604.06996v3)), so
another family removes that one bias. It does not make two readings independent:
models trained on similar material share premises, which is why agreement is
checked below rather than trusted.

**Form your own view before reading the peer's.** For an independent assessment
the driver investigates while the peer works and settles its own reading first.
Two readings formed this way can differ; a reading formed after another mostly
cannot, and a later follow-up does not undo the anchoring. For a critique or a
delivered piece of work, the driver's attention goes to the proposal or the diff
instead.

**Develop the contribution.** Whatever comes back, a distinction, an objection, an
idea or a disagreement, the follow-up pursues what it changes or what causes it
rather than a verdict on who was right. A consequential difference points at
evidence, an assumption, a priority or an error. Agreement counts for less than it
appears to: on three natural-language
inference datasets, nine judges from seven model families carried about two
independent votes' worth of information
([Kohli, 28 May 2026](https://arxiv.org/abs/2605.29800)). Models that share
premises reach the same conclusions, so agreement on anything that matters still
gets checked.

**Check the reasoning.** Before adopting anything, the driver inspects
the cited code and sources, runs checks when authorised, and judges a proposal by
its reasoning and its fit to the task, because a model can be moved by a confident
argument whether or not it is right. A coherent argument for a wrong option flipped seven
frontier models off correct answers in 17.5–97.3% of cases across 57 MMLU
subjects, with no social pressure involved
([*Who Flips?*, 14 June 2026](https://arxiv.org/abs/2606.16011)). Peer agreement
misleads an initially correct model more easily than it corrects a wrong one, and
authority labels raise adoption whether or not the endorsed answer is right
([*Easier to Mislead Than to Correct*, 1 June 2026](https://arxiv.org/abs/2606.01637)).

**Return an account, and leave the decision with you.** The driver says what each
participant contributed, what was checked, what remains uncertain and what is worth
doing next, and where the participants differ on something only you can settle, it
puts the difference to you as a question.
Karpathy's case for partial autonomy is to keep the work inspectable and let the
person choose how much to hand over
([*Software Is Changing (Again)*, Jun 2025](https://www.youtube.com/watch?v=LCEmiRjPEtQ)),
and his [LLM Council](https://github.com/karpathy/llm-council) inspired Riff's
separate answers and comparison. The same steering appears at larger scale:
OpenAI's researchers redirected agent groups from intermediate findings during its
Navier–Stokes work ([8 September 2026](https://openai.com/index/navier-stokes-solution/)).

**What this evidence does not show.** These are instructions to the agents, not
guarantees of their behaviour. None of the studies tests Riff, and none shows that
Riff beats a strong single agent given the same evidence, tools and budget. In
some debate settings majority voting accounts for most of the gain
([*Debate or Vote?*, 2025](https://arxiv.org/abs/2508.17536)), so compare a riff
with simpler ways of spending the same budget; each extra session costs briefing,
runtime and review. Whether an exchange revealed a useful possibility, corrected a
consequential error or improved the eventual work remains a question for each run.

## How it works

The skill carries the rules; the local coordinator does the mechanics around them.
At the brief, it launches the peer in its harness with the tool scope the request
allows. While the peer works, it keeps the exact native session handle, so a
follow-up resumes that session rather than retelling it, and it bounds the turns.
When a turn completes, it saves the response as an artifact and records failures
and outcomes for the account that comes back to you. Changing harness need not
change the model.

```text
you: purpose, constraints, direction
                 ↕
        your agent (the driver)
                 │
          shared Riff skill
                 │
          local coordinator
          ├── Claude Code
          ├── Codex
          ├── Pi → local or hosted models
          └── Hermes
```

The driver mediates follow-ups; peers cannot invoke Riff themselves at the default
depth, and a resumed session stays within the harness's own context limits.

| Harness | Model controls | Supported tool scopes |
|---|---|---|
| Claude Code | Model, effort, configured provider | `none`, `read`, `read+web`, `write` |
| Codex | Model, reasoning effort, OpenAI or local mode | `none`, `read`, `read+web`, `write`; uses native sandboxing |
| Pi | Provider, model, thinking | `none`, `read`, `write` |
| Hermes | Provider, model, max turns | `none`, `read`; read is prompt-enforced and write is disabled |

Pi is the verified route to llama.cpp and vLLM servers, and the one with a write
scope for delegating to a local model. Hermes can also run a provider defined in
its own config, read-only. The
[harness notes](skills/riff/references/HARNESSES.md) cover setup and enforcement.
Another harness is one adapter: a class that reports what the harness supports and
turns the common turn request into that harness's native command and session
handle, added to the registry in `skills/riff/scripts/riff_core/adapters`. The
[adapter contract](skills/riff/references/DESIGN.md#contracts-and-adapters) sets
out what it must return.

A completed turn can still have lacked important evidence. The coordinator records
denied tools, failed participants and timeouts so the driver can tell you, and
returns next steps with every result so that recovery survives the driver losing
the skill text to compaction.

Riff does not create worktrees for writers; it rejects overlapping working
directories for concurrent writers and warns about writers in a main checkout.
Tool scopes are not a containment boundary: enforcement differs by harness, and
Pi's read tools are not a filesystem sandbox. Claude Code and Codex peers run
without your configured MCP servers, and Codex web search is off unless the scope
includes it. Riff grants no implicit commit, push, PR, messaging or deployment
authority.

## Install

Riff needs Python 3.11+ and no third-party packages. Install and configure the
harnesses you want first; peers run through them and their providers. The skill is
the [`skills/riff`](skills/riff) folder, so linking it keeps this README, the film
and the tests out of your agents' skill directories.

Keep one checkout and link the skill into each harness:

```bash
mkdir -p ~/src ~/.agents/skills "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
git clone https://github.com/NasonZ/riff ~/src/riff
ln -s ~/src/riff/skills/riff ~/.agents/skills/riff
ln -s ~/src/riff/skills/riff "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/riff"
```

`git pull` in the checkout then updates every harness at once. Codex and Pi
discover `~/.agents/skills`, and Claude Code its own skills directory. For Hermes,
add the shared directory to `~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs:
    - ~/.agents/skills
```

If you only use Riff from Pi, you can install it as a Pi package instead. Pi
clones the repository from GitHub, loads only `skills/riff`, and updates it with
`pi update --extensions`:

```bash
pi install git:github.com/NasonZ/riff
```

Use one route or the other for Pi; with both, Pi finds two copies of the skill.

Check which harness executables Riff can find and which controls it supports:

```bash
python3 ~/.agents/skills/riff/scripts/riff.py capabilities
```

This checks discovery and adapter capabilities, not authentication or model access.
If older peer skills are installed, follow the
[migration notes](skills/riff/references/HARNESSES.md#migrate-overlapping-skills-safely).
A sandboxed Codex driver also needs the
[state-directory setup](skills/riff/references/HARNESSES.md#codex).

## Records stay local

Each run leaves a record on your machine, so the account the driver gives you can
be checked later. State defaults to `$RIFF_STATE_DIR` when set, otherwise `$XDG_STATE_HOME/riff` or
`~/.local/state/riff`. Each run keeps participant details, artifacts, session
handles, failures, and usage where the harness reports it, plus the driver's
starting expectation and later checks, decisions or open questions when supplied.

Riff has no record-upload service, but peer harnesses still send task context
through their configured providers: local storage does not mean local inference.
Keep the state directory private and outside the source checkout, since artifacts
and logs can contain source material, paths and command output. The records are an
evidence index, not a replay; reconstruction also needs the retained inputs, native
transcripts and the driver's conversation. See
[learning from runs](skills/riff/references/DESIGN.md#learning-from-runs).

## Development

The skill lives in `skills/riff`; tests and this README sit outside it so that
installs carry only what an agent needs. From the repository root:

```bash
python3 -m unittest -v
```

Tests cover request contracts, coordinator behaviour, adapter protocols using fake
processes, and documentation invariants. They do not show that models follow the
skill well or that collaboration improves outcomes.

- [Skill](skills/riff/SKILL.md): the driver's operating instructions.
- [Playbook](skills/riff/references/PLAYBOOK.md): choosing and developing contributions.
- [Protocols](skills/riff/references/PROTOCOLS.md): requests, follow-ups and records.
- [Harness notes](skills/riff/references/HARNESSES.md): controls, setup and enforcement.
- [Design](skills/riff/references/DESIGN.md): architecture and evaluation boundaries.
- [Design lessons](skills/riff/references/NOTES.md): rationale and research.

Riff uses the MIT License.
