# Riff design lessons

This file records reusable design rationale. Private conversations, run histories,
project details, and evaluation reports belong outside the public repository.
Examples here describe collaboration patterns, not a published user dataset.

## Contents

- [Inquiry across perspectives](#inquiry-across-perspectives)
- [Conversation shape](#conversation-shape)
- [Handoffs that survive lost context](#handoffs-that-survive-lost-context)
- [Recoverable sessions](#recoverable-sessions)
- [Authority and observability](#authority-and-observability)
- [Learning under the operator's control](#learning-under-the-operators-control)
- [Research and limits](#research-and-limits)
- [Further reading](#further-reading)

## Inquiry across perspectives

Riff's motivating idea is richer exploration through an exchange between models.
“Semantic spaces” names the associations, distinctions, examples, and possible
framings they can bring to a problem. It is an intuition for designing the
interaction, not a claim that Riff measures their internal representations or
that different model names imply independent knowledge or errors.

The interesting possibility is that one contribution changes what the other
participant can usefully consider next. An analogy can suggest a design; a
counterexample can expose an assumption; developing either can produce a question
neither initial answer contained. The driver must be open to that change as well.
Calling another model a peer means little if every follow-up steers it back to the
driver's original framing.

There is a connection here to philosophical and scientific inquiry. Peirce
distinguished forming an explanatory hypothesis, deriving its consequences, and
testing it through experience. That distinction helps keep invention and warrant
separate: a promising idea deserves development, while a factual claim needs
appropriate evidence. Conversation can contribute to each stage, including the
design of an experiment; agreement cannot substitute for its result.
[Peirce, *Pragmatism: Instinct and Abduction*](https://www.textlog.de/7658.html).

Perspective-taking adds another practical discipline: consider what the other
participant has seen, which assumptions its answer depends on, and what would
make the contribution intelligible or useful to it. This is a design principle
for communicating across different contexts. Riff does not require a claim about
models possessing human minds. The research below offers related ideas and
limited empirical results, rather than a proof of Riff's effectiveness.

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

## Research and limits

The sources support different parts of the rationale. Their tasks, models, and
interaction protocols matter; none establishes that a Riff discussion improves
every task, or that the current skill outperforms a strong single-agent baseline.

- **Collaborative thought.** Collins et al.,
  [*Building Machines that Learn and Think with People*](https://arxiv.org/abs/2408.03943),
  develops a research agenda for partners that model the task, the world, and their
  collaborators. It covers planning and creation as well as answering questions.
  This motivates attention to mutual understanding; it is a perspective on
  human–AI collaboration, not an evaluation of Riff's cross-model exchanges.
- **Perspective-taking.** Wilf et al.,
  [*Think Twice*](https://aclanthology.org/2024.acl-long.451/), improves performance
  on theory-of-mind tasks by filtering information according to what a character
  knows. The relevant lesson is to keep perspectives and access to evidence
  distinct. Applying it to peer context is a design inference, not a result the
  paper tested.
- **Potential gains from debate.** Du et al.,
  [*Improving Factuality and Reasoning in Language Models through Multiagent Debate*](https://arxiv.org/abs/2305.14325),
  reports improvements on its evaluated reasoning and factuality tasks. It
  provides evidence that exchanges can help under particular conditions, without
  establishing a general advantage for discussion or open-ended exploration.
- **More reasoning is not enough.**
  [*Debate or Vote?*](https://arxiv.org/abs/2508.17536) finds that majority voting
  accounts for much of the gain in its evaluated debate settings. Its theoretical
  result depends on a specified model of belief updates. The practical implication
  is to compare against simpler ways of spending the same budget, and investigate
  what the interaction actually adds.
- **Persuasion can defeat judgment.**
  [*MultiAgent Collaboration Attack*](https://arxiv.org/abs/2406.14711) and
  [*When collaboration fails*](https://www.nature.com/articles/s41598-026-42705-7)
  study adversarial influence within model debates. They motivate assessing reasons
  and evidence rather than confidence or consensus. Their attack settings do not
  measure the frequency of such failures in ordinary Riff use.
- **A persona is not a perspective.**
  [*Persona is a Double-edged Sword*](https://arxiv.org/abs/2408.08631) finds that
  role-playing can help or harm reasoning under its tested conditions.
  [*From Biased Chatbots to Biased Agents*](https://arxiv.org/abs/2602.12285)
  examines performance changes from task-irrelevant demographic role assignments.
  These findings motivate Riff's preference for concrete questions over invented
  identities; they do not show that every role instruction is harmful.

For Riff, the empirical questions remain specific: did the exchange reveal a
useful possibility, correct a consequential error, or improve the eventual work?
What did it cost compared with another solo pass, independent answers, or direct
delegation? Run records can help investigate those questions. Changing a view,
agreeing with a peer, and liking an idea remain distinct from demonstrating that
the resulting work is better.

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
