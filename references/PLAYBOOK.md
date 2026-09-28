# Riff collaboration playbook

This file holds the durable judgment that makes Riff more than a process launcher.
Read it before a consequential consult, a multi-round discussion, a synthesis of
several peers, or a delegation whose result will be integrated.

## Contents

- [Peer stance](#peer-stance)
- [Independent-first elicitation](#independent-first-elicitation)
- [Where peers help](#where-peers-help)
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
proposal is essential input. Label that shape as critique rather than pretending it
is independent-first.

For several participants, isolate first-round prompts from one another. Optional
cross-review happens only after the independent artifacts exist. When prestige or
provider anchoring matters, present peer artifacts under opaque labels during the
review round while retaining true identities in the run trace.

Independent-first composes well with convergence. In one hardening-design session,
the first round withheld the driver's analysis and the peer surfaced a broader
structural issue the driver had missed; the second round shared the driver's
revised position and the peer returned consensus plus concrete amendments. The
value came from the sequence. Skipping straight to convergence would have hidden
that the question was framed too narrowly.

## Where peers help

Coding review, diagnosis, and bounded delegation are the common case, but a peer
is often worth more outside code:

- **Strategic decisions** with several stakeholders or trade-offs — use critique,
  and direct attention (“evaluate the downstream effect on people in role X”)
  rather than asking the peer to be anyone.
- **Research framing** — “is this the right question?” or “what is a better
  operationalization?” Independent-first consult fits best.
- **Ethics and policy** where no answer is objectively correct — several lenses
  surface considerations one model misses. Avoid personas especially here.
- **Written work** such as essays, specs, and proposals — ask for specific kinds
  of feedback (structure, clarity, what is missing) rather than casting an editor.
- **Naming, taxonomy, and API design** — high-stakes, low-information decisions
  where a second perspective is cheap relative to the cost of a poor choice.

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

The driver owns the final synthesis. It should report:

- meaningful agreement;
- material disagreement;
- decisive evidence;
- remaining uncertainty; and
- the driver's resulting judgment.

Do not concatenate peer outputs and call it synthesis.

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

Prefer, in order:

- tests, type checks, linters, or reproducible commands;
- inspection of diffs and changed files;
- direct checks against cited code or primary sources;
- comparison with an independently produced artifact; and
- explicit acknowledgment that verification was not performed.

LLM judges can help prioritize review but are not ground truth. A trace is useful
only when it records what really happened; never fabricate checks to complete a
schema. Prefer a check the coordinator executes (`verify --run`) to one you state
(`--check`): the first records an exit code, the second only your word
(`RIF-DELEGATE-002`). Say "verified" to the user only after a check has run; in the
field, drivers announced verification before running anything, and after losing
the record to a context compaction told the user figures had "never been viewed"
when they had been.

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
embed full content only when explicitly requested and safe.

## How knowledge compounds

Preserve each significant lesson through five layers:

1. Capture the observation and evidence in `NOTES.md`.
2. Generalize durable judgment in this playbook.
3. Put always-needed behavior in `SKILL.md`.
4. Encode fragile mechanics in the coordinator or an adapter.
5. Add a focused regression test for executable invariants.

Use stable identifiers when a lesson spans layers. Each carries its basis: `[F]`
observed in Riff runs (evidence in `NOTES.md`), `[R]` published research or vendor
guidance not yet observed here, `[T]` convention or an untested bet. A `[T]` or
`[R]` rule bends more readily than an `[F]` one; say why when bending any of them.

- `RIF-EPISTEMIC-001` [F] — elicit independently before comparison.
- `RIF-EPISTEMIC-002` [R] — confidence is not evidence.
- `RIF-EPISTEMIC-003` [T] — record the prediction before consulting.
- `RIF-SESSION-001` [F] — identify sessions explicitly.
- `RIF-DELEGATE-001` [F] — verify before integration.
- `RIF-DELEGATE-002` [R] — an executed check outranks an asserted one.
- `RIF-AUTHORITY-001` [T] — do not expand authority implicitly.
- `RIF-AUTHORITY-002` [F] — match tool scope to the acceptance criteria.
- `RIF-CONTEXT-001` [T] — prefer references and artifacts to transcript transfer.
- `RIF-FAILURE-001` [F] — classify a peer failure before retrying it.
- `RIF-COLLECTION-001` [F] — one installed skill owns each trigger.

`tests/test_knowledge.py` fails when a document cites an identifier this list does
not define.

New research does not automatically become policy. Record its scope and caveats,
observe it in real use, then promote it from `[R]` or `[T]` to `[F]` when it
repeatedly improves outcomes.
