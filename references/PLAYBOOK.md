# Riff collaboration playbook

This file holds the durable judgment that makes Riff more than a process launcher.
Use it when choosing the kind of contribution to ask for, handling disagreement,
or assessing a consequential result. Operational commands live in `SKILL.md` and
[the protocols](PROTOCOLS.md).

## Contents

- [Peer stance](#peer-stance)
- [Choose the contribution](#choose-the-contribution)
- [Develop an idea](#develop-an-idea)
- [Independent-first elicitation](#independent-first-elicitation)
- [Framing and disagreement](#framing-and-disagreement)
- [Personas and focused attention](#personas-and-focused-attention)
- [Persuasion and synthesis](#persuasion-and-synthesis)
- [Delegation quality](#delegation-quality)
- [Verification and integration](#verification-and-integration)
- [Context and artifacts](#context-and-artifacts)
- [How knowledge compounds](#how-knowledge-compounds)

## Peer stance

Treat every participant as an independent reasoner, not as a capability rank.
`driver` and `worker` describe coordination positions. They do not imply that the
driver is smarter, owns the truth, or should preserve its initial view.

A useful peer can:

- reject a false premise;
- narrow or broaden the question;
- identify missing evidence;
- propose a different method;
- disagree with the driver after seeing its reasoning; or
- produce a result that the driver ultimately rejects after verification.

Evaluate these moves on their substance. Do not reward obedience or disagreement
for its own sake.

## Choose the contribution

Match the peer's contribution to the stage and purpose of the work. An early idea
may benefit from alternatives, a useful connection, or a sharper question. A formed
proposal may need critique. A consequential diagnosis may need an independent
assessment. A well-specified task may be ready for delegation.

These are choices within consult, discuss, and delegate, not additional API modes.
The same conversation can move from developing possibilities to comparing them.
Make that change explicit when the user is ready to decide.

| Purpose | Useful request | Context to share |
|---|---|---|
| Independent assessment | “What explains this failure?” | Evidence and constraints; withhold your diagnosis |
| Critique | “Where does this proposal fail?” | The proposal, its aims, and relevant evidence |
| Exploration | “What could this idea become?” | The seed idea, audience, constraints, and open questions |
| Delegation | “Deliver this bounded result.” | Inputs, authority, output contract, and acceptance checks |

The contribution can also change the kind of work being done. In research, a peer
could turn “Which explanation fits?” into “What observation would distinguish
these explanations?” In naming, it could uncover competing ideas of what the
product is for, opening a positioning discussion before generating more names.
In strategy, a neglected stakeholder's needs could change which tradeoffs matter.
Follow a useful opening rather than requiring every exchange to produce options
to rank. Direct attention to the question rather than an expert persona.

## Develop an idea

Early collaboration can help produce a first draft. Ask the peer to extend the
promising parts, surface alternatives, or connect the idea to something useful.
Premature ranking can close possibilities before they are understood; equally,
exploration should not conceal a factual problem that undermines the premise.

For example, “Review this rough documentation concept” leaves the contribution
ambiguous. “Develop ways readers could enter this material; explain what each
would help them understand” gives the peer a constructive task. If the peer
distinguishes task-oriented and concept-oriented reading, explore how those needs
interact: “Walk a newcomer through one task. Where would they need an explanation,
and how could the page offer it?”

The walkthrough might suggest explanations at decision points within a task,
alongside a separate conceptual guide for readers seeking an overview. Ask the
peer to sketch a difficult transition in each structure. That makes the tradeoff
concrete enough to critique: does the inline explanation interrupt progress, or
does the separate guide require too much switching? A distinction has become a
design choice with a way to investigate it.

Carry forward useful questions, connections, and alternatives. When a choice is
needed, name what would help make it. Stop when the user has enough to proceed,
another round adds little, or the agreed bound is reached; the useful outcome may
be a new way to understand the problem or a next experiment.

If a peer defaults to fault-finding, clarify the contribution you need in the same
session. If that still produces little useful development, report the limitation
rather than spending further rounds trying to force the conversation.

## Independent-first elicitation

When the purpose is a genuinely independent check, withhold the driver's proposed
answer during the first turn. Send the question, constraints, relevant evidence,
and requested output shape. Share the driver's view only after the peer has
committed to an initial analysis.

This is most valuable when:

- a decision is consequential;
- the driver may have anchored on one explanation;
- the problem admits several plausible abstractions; or
- model/provider diversity is part of the reason for consulting.

Do not apply it mechanically. If the task is to critique a concrete proposal, the
proposal is essential input. Set `driver_position: provided` with
`driver_position_text`; the coordinator derives `independent_first: false` unless
you explicitly supplied a contradictory setting. If there is no driver position,
use `none`; you can still collect separate first-round contributions.

Record a private baseline in `driver_prediction` when it helps interpret the result.
For a diagnosis, name what you expect and what would change it. For exploration,
state your uncertainty: “No preferred structure yet; unclear whether task or
concept should organize the material.” This field is never sent to peers. Leave it
empty when there is nothing useful to record rather than manufacturing certainty.
The record should distinguish starting without a view from changing an existing one.

For several participants, isolate first-round prompts from one another. Optional
cross-review happens only after the independent artifacts exist. When prestige or
provider anchoring matters, present peer artifacts under opaque labels during the
review round while retaining true identities in the run trace.

Independent-first can lead into convergence: collect the peer's initial analysis,
then share a revised position and ask what remains unresolved. This sequence gives
a broader framing room to emerge before the conversation focuses on agreement.

## Framing and disagreement

Invite reframing explicitly:

> If the question is framed incorrectly, explain why and propose the better
> question before answering.

When a peer reframes the task, distinguish five outcomes:

- `accepted`: it answered the supplied question;
- `narrowed`: it reduced scope to make the question answerable;
- `broadened`: it identified a larger governing problem;
- `challenged`: it answered provisionally while disputing an assumption;
- `rejected`: it concluded that answering the requested question would mislead.

Do not silently discard a reframe. The synthesis should say whether the driver
accepted it, rejected it with reasons, or needs more evidence.

Disagreement is useful when it changes the evidence, assumptions, causal model, or
trade-off analysis. Repeatedly restating positions is not productive discussion.

## Personas and focused attention

Default to neutral prompts. Avoid task-irrelevant role play such as “act as
Aristotle” or “you are a legendary engineer.” Personas can cause a model to perform
a character instead of inspecting the problem.

Focused attention is different and useful:

- “Check specifically for lost-update races.”
- “Evaluate whether these citations support the causal claim.”
- “Look for assumptions that fail under eventual consistency.”

These instructions constrain the object of attention rather than inventing an
identity. Use several focused passes when distinct failure classes matter; do not
confuse artificial personalities with independent evidence.

## Persuasion and synthesis

Fluency, confidence, repetition, and model reputation are not evidence. During
synthesis, compare claims using:

1. directly inspectable evidence;
2. reproducible commands or tests;
3. explicit assumptions;
4. causal or logical support; and
5. acknowledged gaps.

Convergence among models is reassuring only when their errors are plausibly
independent. Several participants using the same underlying model or source may
repeat the same mistake. Record harness, provider, and model when available so the
driver can judge how independent the samples really were.

Use a devil's-advocate pass only when a decision appears prematurely settled. Ask
for the strongest concrete counterargument, not theatrical contrarianism. Stop if
the pass produces no new evidence or unresolved concern.

The driver owns the final synthesis. Explain who contributed what and what context
they saw; how the exchange changed or developed your view; and what you would
adopt, reject, or investigate next, with reasons. Support that judgment with the
decisive evidence and checks, meaningful agreement or disagreement, and limitations
such as denied access or failed participants. Choose prose or structure to suit
the user's task.

A short exploratory synthesis might be: “Codex suggested explanations within the
task walkthrough after we questioned whether newcomers could choose between two
entrances. I'd sketch that transition alongside the separate-guide option; we
haven't tested either with readers.” This attributes the contribution, explains
the next step, and leaves its status clear. Keep the run's outcome record even
when the user-facing response is brief.

## Delegation quality

A delegate begins without the driver's conversational context. Give it a contract:

1. **Goal** — one observable outcome.
2. **Context** — only the necessary paths, constraints, and prior decisions.
3. **Inputs** — concrete files, URLs, commands, or artifacts.
4. **Output contract** — the expected artifact and its shape.
5. **Authority** — allowed tools, writable roots, and external side effects.
6. **Out of scope** — tempting adjacent work it must not perform.
7. **Acceptance criteria** — checks the driver will actually run.

Narrow specifications outperform invitations to “improve the codebase.” A clean
contract is also a diagnostic: if the driver cannot state the output and acceptance
criteria, the work may need a consult before it is ready to delegate.

A delegate can push back on the contract. Treat a justified reframe as signal, not
insubordination. Reissue a corrected contract when necessary rather than forcing
work against a false premise.

## Verification and integration

Never integrate a consequential peer result solely because the peer says it
succeeded. Verification belongs to the driver or an external mechanism with access
to ground truth.

Match the check to the claim. Code behavior calls for relevant tests and diff
inspection; factual claims call for checking cited code or primary sources. A
framing, name, or design proposal calls for assessment against the user's aims,
with the reasons and remaining uncertainty stated plainly. Agreement among models
and user preference are useful observations, not proof of factual correctness.

When a command can test a material claim, `verify --run` records the execution and
exit code (`RIF-DELEGATE-002`). An inspection recorded with `--check` remains an
assertion by the driver. Judge both by their relevance and scope: a passing test
of unrelated behavior does not outweigh a source inspection that exposes the
defect. LLM judges can help prioritize review but are not ground truth.

For an exchange that develops ideas without factual or acceptance checks, use
`--result not_performed` and preserve the contribution and open questions in
`--note`. Where some claims were checked, record those checks and their limits.
Distinguish developing a possibility, changing a view, and adopting a decision;
they say different things about the outcome. The
[outcome examples](PROTOCOLS.md#record-the-outcome) show how to record each.

When verification fails, preserve the peer's native session and send a focused
follow-up. Do not restart from a compressed summary unless the native session is
unrecoverable.

## Context and artifacts

Protect the driver's context window:

- reference files instead of pasting their full contents;
- ask peers to write final artifacts rather than returning event streams;
- read summaries first, then inspect supporting material selectively;
- retain native session handles for follow-ups; and
- keep one artifact directory per run and participant.

Do not place secrets, `.env` files, unrelated home-directory paths, or full private
transcripts into peer prompts or traces. Store artifact paths and hashes in traces;
embed full content only when explicitly requested and safe. Keep operational
records outside the source repository. Learning from a private run does not grant
permission to publish its contents, identifiers, statistics, or personal context.

## How knowledge compounds

Each run has two useful outputs: its contribution to the current task and evidence
about how the collaboration worked. Record the checks, corrections, adoption or
rejection, and unresolved questions while the context is available. A failure or a
rejected suggestion can be as informative as an adopted one.

Keep these observations distinct. `view_changed` is the driver's report, an exit
code measures the command that ran, and a user preference expresses a preference.
None is a general quality score. The coordinator captures mechanical facts; the
driver's `--note` supplies the outcome and rationale those facts cannot express.

Field reviews can turn recurring observations into candidate skill changes and
behavior cases. Test the changes on separate tasks before treating them as
improvements. [Learning from runs](DESIGN.md#learning-from-runs) describes the
current trace boundary, possible optimization and post-training uses, and the
[rule provenance registry](DESIGN.md#rule-provenance) used across docs and tests.
