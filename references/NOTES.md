# Riff design lessons

This file records reusable design rationale. Private conversations, run histories,
project details, and evaluation reports belong outside the public repository.
Examples here describe collaboration patterns, not a published user dataset.

## Conversation shape

A fixed decision schema is useful when comparing discrete choices. Exploration
needs room for questions, connections, and reframing before there is a decision to
encode. Choose the output form for the task; a consensus marker does not establish
that the participants resolved their disagreement.

Driver and peer describe coordination roles. Either participant can identify the
better framing, and either can be persuaded. The driver remains responsible for
what it adopts. Neutral prompts with focused questions leave more room for useful
reasoning than task-irrelevant personas.

Withhold a proposed answer when seeking an independent assessment. Supply it when
asking for critique of that proposal. Record uncertainty honestly when there is no
prior view. These are different starting conditions, not levels of rigor.

## Handoffs that survive lost context

A driver can lose the skill text during context compaction. The coordinator's
result therefore carries the next action: read artifacts, inspect denied access,
check relevant claims, and record the outcome. The command should be executable
with the returned run ID and state directory.

Different tasks need different outcome records. Code changes need acceptance
checks and diff inspection. A factual consult may need source inspection. An
exploratory exchange may yield a useful question without verifying a claim.
Preserve these distinctions rather than treating every settled turn as success.

## Recoverable sessions

A timeout does not necessarily destroy a native session. Preserve explicit handles,
confirm that the old process has stopped, and resume that session when supported.
A summary used to start a new session loses context that native continuation keeps.
Failed attempts should be bounded without spending the allowance for substantive
settled turns.

Long runs need a detached process and bounded waits when the driver's tool-call
lifetime is shorter than the peer's work. Direct output to files; a pipeline whose
reader exits can terminate the producer with SIGPIPE.

## Authority and observability

Exposing a tool and granting permission to use it can be separate operations.
Conversely, a harness can enable tools by default that the request never named.
Adapters must account for both directions and disclose enforcement limits.
A settled process can still have been denied the evidence it needed.

Classify authentication, usage-limit, timeout, and transport failures before
choosing a recovery. Retrying unchanged credentials or an exhausted quota adds
cost without resolving the cause.

State transitions and process protocols belong in deterministic tests. Skill
selection, contribution quality, and synthesis need behavioral evaluation. Use
synthetic or explicitly publication-approved material for shared fixtures; keep
private evaluation evidence in the operator's own storage.

## Learning under the operator's control

Records can support an operator's own review, skill optimization, or curated
post-training work. These are optional downstream uses, not permission to publish
runs, copy private transcripts into documentation, or upload them to a service.
The public repository should preserve the lesson without exposing the source
conversation or making private evidence a dependency for readers.

See [the design](DESIGN.md#learning-from-runs) for the data boundary and
[the playbook](PLAYBOOK.md) for applying these lessons.

## Further reading

- [Agent Skills best practices](https://agentskills.io/skill-creation/best-practices)
- [Anthropic skill-authoring guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Prompt-caching reference](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/prompt-caching.md)
- [SkillOpt](https://github.com/microsoft/SkillOpt)
- [AISI: sandbox information discovery](https://www.aisi.gov.uk/blog/what-can-sandboxed-ai-agents-learn-about-their-evaluation-environments)
- [AISI: securing evaluation environments](https://www.aisi.gov.uk/blog/building-a-more-secure-environment-for-evaluating-dangerous-capabilities)
- [AISI: limits of asynchronous monitoring](https://www.aisi.gov.uk/blog/stress-testing-asynchronous-monitoring-of-ai-coding-agents)
- [AISI: evaluating unintended shortcuts](https://www.aisi.gov.uk/blog/cheating-behaviour-in-frontier-model-evaluations)

These references inform design and evaluation choices; they do not establish that
Riff's behavioral scenarios pass on a particular model or harness version.
