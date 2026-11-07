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

An encounter with another perspective can change what becomes noticeable in a
familiar problem. A different representation may bring a relationship into view;
an analogy may make a new approach imaginable. In Riff, the practical possibility
is that one contribution changes what another participant can usefully consider
next. Developing an analogy or counterexample can produce a question neither
initial answer contained. The driver must be open to that change as well.
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
the conclusions and changes it brings back to the user. Neutral prompts with
focused questions leave more room for useful reasoning than task-irrelevant
personas.

A shared brief can preserve a mistaken purpose through otherwise careful work.
Checking each claim does not establish that the participants answered the question
the user meant. Treat the meaning of the request as something that may need
clarifying, especially when different readings imply different work. A user's
redirection can change the inquiry itself, not merely select among the models'
existing answers. This is a design rationale for making assumptions visible and
returning choices of purpose to the user, not a requirement to ask about every
ordinary implementation choice.

Withhold a proposed answer when seeking an independent assessment. Supply it when
asking for critique of that proposal. Record uncertainty honestly when there is no
prior view. These are different starting conditions, not levels of rigour.
For an independent comparison, the driver needs a considered assessment of its own;
separate sessions alone do not supply one. Likewise, a change of view is not the
only useful outcome. Participants can develop an explanation, identify a missing
question, or expose a choice that belongs to the user.

## Handoffs that survive lost context

A driver can lose the skill text during context compaction. The coordinator's
result therefore carries the next action: read artifacts, inspect denied access,
check relevant claims, and record the outcome. The command should be executable
with the returned run ID and state directory.

Different tasks need different outcome records. Code changes need acceptance
checks and diff inspection. A factual consult may need source inspection. An
exploratory exchange may yield a useful question without verifying a claim.
Preserve these distinctions rather than treating every settled turn as success.
Preserve the conditions on the evidence too: which uses are authorised, what a
check actually covers, and which conclusions remain provisional. A handoff that
retains the facts but loses those conditions can change the meaning of the work.
Wang et al.'s [handoff study](https://arxiv.org/html/2608.29028) tests one such
failure; its limits and single-agent comparison are discussed below.

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
selection, contribution quality, and synthesis need behavioural evaluation. Use
synthetic or explicitly publication-approved material for shared fixtures; keep
private evaluation evidence in the operator's own storage.

## Learning under the operator's control

Records can support an operator's own review, skill optimisation, or curated
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
- **Interpreting the request.** Tang et al., [*How Coding Agents Fail Their
  Users*](https://arxiv.org/html/2605.29442v2), revised 31 August 2026, analyses
  20,574 sessions and attributes 15.36% of its identified misalignment episodes to
  underspecified instructions. Its unit is a breakdown visible through developer
  pushback, not every unnoticed failure; causes are annotated from logs, not
  experimentally established. Most episodes have no observable resolution in the
  transcript. For Riff, this motivates preserving the user's purpose and following
  later corrections, while resisting claims about success based only on the end of a
  peer turn. It does not establish a general failure rate or show that a second
  agent would have prevented those breakdowns.
- **Execution can succeed under the wrong interpretation.** Stoisser et al.,
  [*Ambig-DS*](https://arxiv.org/html/2605.09698), published 10 May 2026, removes
  decisive framing information from data-science tasks. On its prediction-target
  suite, tested frontier agents silently commit to unintended targets in 39–63% of
  ambiguous runs, despite producing valid submissions. An idealised clarification
  oracle recovers much of the loss, but the tested policies do not reliably balance
  asking on ambiguous tasks with restraint on specified ones. This supports
  examining consequential interpretations before comparing solutions. The suite
  constructs ambiguity around two framing variables; it neither estimates its
  prevalence in ordinary work nor tests realistic conversations with stakeholders.
- **Handoffs must preserve conditions of use.** Wang et al., [*Facts Without
  Rules*](https://arxiv.org/html/2608.29028), published August 2026, finds that
  compression can preserve operational facts while losing the audience and
  disclosure rules attached to them. In controlled downstream tests, explicit rules
  reduce leakage substantially compared with vague caution. A single agent given the
  original material with natural-language markers still leaks more than an agent
  given a handoff that makes those rules operational. The contrast concerns the form
  of the instructions, not an inherent safety advantage for either topology. Riff's
  practical inference is to carry constraints and authority beside the facts they
  govern, and retain access to the original sources. That guidance is not an
  enforcement guarantee: the study's strongest intervention uses a gold-derived
  audience allowlist, and inaccurate boundary extraction weakens it. Synthetic
  scenarios and simulated audiences limit claims about deployment.
- **Potential gains from debate.** Du et al.,
  [*Improving Factuality and Reasoning in Language Models through Multiagent Debate*](https://arxiv.org/abs/2305.14325),
  reports improvements on its evaluated reasoning and factuality tasks. It
  provides evidence that exchanges can help under particular conditions, without
  establishing a general advantage for discussion or open-ended exploration.
- **More reasoning is not enough.**
  [*Debate or Vote?*](https://arxiv.org/abs/2508.17536) finds that majority voting
  accounts for most of the gain in its evaluated debate settings. Its theoretical
  result depends on a specified model of belief updates. The practical implication
  is to compare against simpler ways of spending the same budget, and investigate
  what the interaction actually adds.
- **Different names do not ensure independent errors.** Kohli's [*Nine Judges, Two
  Effective Votes*](https://arxiv.org/html/2605.29800) published 28 May 2026, tests
  nine judges from seven families on three natural-language inference datasets and
  finds about two independent votes' worth of information. Its best single judge
  matches or outperforms the panel. Replication on a pairwise preference task
  extends the finding, but open-ended generation and code review remain outside that
  result's scope. Riff uses disagreement to identify what to investigate; agreement
  still needs examination of the underlying evidence and assumptions. This is a
  reason to inspect contributions, not to assume a fixed discount for every
  collection of models.
- **Judges can favour familiar outputs.** Pombal et al., [*Self-Preference Bias in
  Rubric-Based Evaluation*](https://arxiv.org/html/2604.06996v3), revised 3 August
  2026, finds self- and family-preference even with programmatically verifiable
  rubrics on instruction-following and coding tasks; strength varies by model and
  dataset. Combining judges mitigates rather than eliminates the bias, and shared
  errors remain. This motivates a different-family assessment where useful and
  checking the underlying claim directly when possible. Rubric grading is not
  collaborative problem-solving: the result does not show that same-family peers
  always agree, or that choosing another family establishes independence.
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

Human direction can also develop the inquiry rather than only approve its final
answer. In its [Navier–Stokes research
account](https://openai.com/index/navier-stokes-solution/), published 8 September
2026, OpenAI describes reallocating agents after an intermediate Euler result, then
consolidating insights into follow-up prompts across groups. This illustrates
steering from what the agents discover. It is an organisation's report of a large
research effort with an internal model, not a controlled comparison of coordination
methods or evidence that Riff's small exchanges will reproduce its outcomes.

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
Riff's behavioural scenarios pass on a particular model or harness version.
