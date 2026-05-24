---
name: codex
description: Collaborate with OpenAI Codex CLI as a peer AI agent (both SOTA in 2026). Use for delegate (hand off a task), consult (one-shot second opinion), or roundtable (multi-round debate) modes. Works for coding AND non-coding domains — strategic decisions, design philosophy, ethics, research framing, creative critique. Auto-detects whether the `codex` MCP server is configured and falls back to the `codex exec` CLI if not.
---

# Codex collaboration

You have access to OpenAI's Codex CLI as a peer agent. **Both you (Claude) and Codex are SOTA 2026 coding models** — this is not a "smart agent calls a dumb tool" pattern, it's two reasoners of comparable capability collaborating.

## The two agents

Codex is an independent high-capability peer (GPT-5.x family). Its strengths may overlap with or exceed yours on any given problem — **do not assume the direction of insight in advance.** The community has noted some default tendencies (Claude tends creative/exploratory, Codex tends rigorous/adversarial), but treat those as situational priors, not capability rankings.

Roles like "driver/worker" in delegate mode are coordination conveniences, not statements about which model is smarter on the task at hand. The worker may see what the driver missed.

What this means in practice:

- **Codex may reframe your question, not just answer it.** If it pushes back on your framing ("you're asking X but the better question is Y"), evaluate the reframe on its merits.
- **You can be the one persuaded.** If Codex's argument is better than yours, update — don't preserve your position because you opened the conversation.
- **Use Codex for independent disagreement, then verify its claims.** The value is two independently prompted models with different priors. Not mysticism.

## Where this skill sits in the 2026 ecosystem

By May 2026 several multi-LLM deliberation projects had shipped — and several extend beyond coding:

- **Karpathy's LLM Council** (and its many forks) — N models answer independently, anonymously peer-review each other, a "Chairman LLM" synthesizes. The seminal pattern.
- **Agent Council** (yogirk) — CLI version of the above (Claude Code + Codex + Gemini CLI), works for "any question, not just engineering," reportedly ~2× consideration coverage vs single agent.
- **Council of High Intelligence** — 18 persona-bound agents (Aristotle, Feynman, Kahneman, Torvalds…) deliberate across providers.
- **Perplexity Model Council** (launched Feb 2026) — productized council pattern.
- **Domain applications**: investment councils (fundamental / technical / sentiment perspectives), healthcare diagnostic ensembles, strategic decision-making, ethics deliberation, cultural alignment, creative writing with model specialization (Opus for prose & critique, GPT-5 for ideation).

**What this skill is:** a *dyad* (just you + Codex), not a full council. Anonymous peer review breaks down at N=2. The dyad has its own strengths — lower orchestration cost, faster feedback loop — and most council techniques adapt (see "Techniques that travel" below).

**What's still undocumented in 2026:** structured peer debate between two SOTA models on *abstract* topics (philosophy, framing, taste). The exploration sub-mode is a working hypothesis. Be ready to break form if it's not serving the conversation.

## Techniques that travel across modes

Borrow these from the broader council literature. They apply to consult and all three roundtable sub-modes.

- **Independent-first** (Karpathy's anchoring fix). For consult or round 1 of a roundtable: **don't share your own position with Codex in the first prompt**. Ask the question, get Codex's independent answer, *then* share your view and compare. Sharing first anchors Codex to your framing and weakens the second opinion. Trade-off: one extra round, but worth it for non-trivial questions.
- **Persona prompting — mostly avoid.** 2026 research is consistent: persona prompting is a double-edged sword. Performance can degrade up to ~26% on agentic benchmarks from task-irrelevant persona cues (arXiv 2602.12285), and rationale quality often drops even when surface accuracy improves (arXiv 2408.08631). Personality role-play ("be Aristotle") is the worst offender — it invites performance over reasoning. **Default: no persona.** Then pick the right prompt mode for what you want:
   - **When independence matters** (you want a take undistorted by yours): ask the question first, share your view only after. The "Independent-first" technique above. Sharing your frame upfront destroys what makes the second take valuable.
   - **When critique matters** (you have a position and want it stress-tested): share your frame explicitly and invite disagreement. "Here's what I think; tell me where I'm wrong."
   - Narrow task-specific attention direction ("specifically check for race conditions in `chat()`") isn't really a persona, it's a focused question. Fine.
- **Welcome reframing.** Invite Codex to push back on your *question*, not just answer it. Add to prompts: "If you think I'm framing this wrong, say so and propose a better question." Often surfaces framing errors a single model would miss — but only works if you're actually open to being reframed.
- **Adversarial-influence awareness.** Research published in 2026 (Nature Sci. Reports; arxiv MultiAgent Collaboration Attack) shows LLM-to-LLM debate is vulnerable to persuasion-driven drift — one model can talk the other into a wrong position via tone and confidence rather than substance. Practical guard: **evaluate Codex's arguments on their merits, not on how confidently they're stated.** If you find yourself agreeing because Codex sounds authoritative, stop and re-check whether the underlying argument actually changed your mind.
- **Devil's advocate round.** Before declaring CONSENSUS in convergence mode, do one explicit round where you (or Codex) is instructed to argue the opposite case as forcefully as possible. If the agreed position survives that, ship it. If it doesn't, you weren't really converged.

## When to invoke

- **Delegate** — a task is well-scoped and you'd rather hand it off (long-running analysis, refactor, codebase walk, code review). Frees your context.
- **Consult** — you have a draft, plan, or diagnosis and want an independent read before committing. Especially valuable for tricky bugs, design choices, and "am I missing something obvious."
- **Roundtable** — the problem is contested or has tradeoffs and you want structured back-and-forth. Three flavors below — pick the one matching the conversation, not always the same one.

Do NOT use for trivial questions, things you can answer in one read, or to dodge thinking. Codex calls cost time and tokens.

## Setup detection (do this first, every session that uses the skill)

Detect transport before invoking Codex:

```bash
# 1. Is the codex MCP server connected?
claude mcp list 2>/dev/null | grep -i '^codex' && echo "USE_MCP=1" || echo "USE_MCP=0"

# 2. Is the codex CLI installed?
command -v codex >/dev/null && codex --version || echo "CODEX_MISSING"
```

- If `USE_MCP=1`: prefer the MCP tools `codex` and `codex-reply` (cleanest multi-turn).
- If `USE_MCP=0` and `codex` CLI exists: use `codex exec` patterns below.
- If `CODEX_MISSING`: tell the user to `npm install -g @openai/codex@latest` and stop.

**Offer MCP setup once.** If MCP is missing but CLI works, tell the user *once* per session: "For smoother multi-turn discussions, run `claude mcp add codex -- codex mcp-server` once — then restart Claude Code." Don't nag.

## Transport A — MCP (preferred when available)

The codex MCP server exposes two tools:

- `codex(prompt, ...)` — start a new thread. The tool result contains `threadId` directly at the top level alongside `content`. **Extract `threadId` and remember it for follow-ups.** (Older docs claim it's at `structuredContent.threadId` — verified false on Codex v0.133+; it's top-level. If both paths are present in your client, prefer top-level.)
- `codex-reply(threadId, prompt)` — continue an existing thread.

For each conversation, keep a small mental map: `{purpose: threadId}`. For roundtable mode with parallel threads, this is the only transport that supports it cleanly.

**Approval requests** — if you ask Codex (over MCP) to do anything write-shaped (`exec`, `apply-patch`), it may surface an approval request that the MCP client must answer. For consult/review this never happens. For delegate mode with write access, watch for the request and route the decision back to the user — don't auto-approve.

(The MCP interface is documented as experimental; the v2 `thread/*` / `turn/*` APIs are the forward-looking surface if your client exposes them.)

## Transport B — CLI (fallback)

### Single thread, sequential follow-ups

Two patterns. **Capture the session ID** when you might need parallel threads or robustness; use `--last` only as a convenience when exactly one Codex thread is live in this cwd.

```bash
# Pattern A — capture the session ID (recommended for anything you'll follow up on)
codex exec --json --sandbox read-only -o /tmp/codex-out.md "<prompt>" 2>/dev/null \
  | tee /tmp/codex-events.jsonl >/dev/null
SID=$(head -1 /tmp/codex-events.jsonl | python3 -c "import sys,json;print(json.loads(sys.stdin.read())['thread_id'])")
# Remember SID for this conversation (mental map: {purpose: SID})

# Follow up using the explicit ID — note: flags come FIRST, then SESSION_ID, then PROMPT.
# resume does NOT accept --sandbox (it inherits from the original session).
codex exec resume -o /tmp/codex-out.md "$SID" "<followup>"

# Pattern B — convenience, single active thread only:
codex exec --sandbox read-only -o /tmp/codex-out.md "<prompt>"
codex exec resume --last -o /tmp/codex-out.md "<followup>"
```

**`--last` is acceptable only when exactly one active Codex thread exists in this cwd.** If you've started a second Codex thread (even briefly), `--last` will silently resume the wrong one. When in doubt, capture the ID (Pattern A) or use MCP.

### Multiple parallel threads (CLI fallback only)

Use file-handoff — one directory per thread, paste prior context into each prompt:

```bash
mkdir -p /tmp/codex-threads/<thread-name>
# Write the full conversation-so-far to /tmp/codex-threads/<thread-name>/prompt.md
codex exec --sandbox read-only -o /tmp/codex-threads/<thread-name>/reply.md \
  - < /tmp/codex-threads/<thread-name>/prompt.md
```

Loses Codex's internal memory but gives you full control. Use only when you genuinely need parallel discussions.

## Choosing flags

Defaults that almost always apply:

- `--sandbox read-only` for consult/review/analysis (recommended; actual default comes from `~/.codex/config.toml` so don't assume).
- `--sandbox workspace-write` only when Codex needs to write code; tell the user first.
- `-o <file>` always — read the final message from file. Codex's JSONL event stream is noisy and burns context.
- `-C <dir>` if the relevant work is in a non-default directory.
- `--skip-git-repo-check` when running outside a repo.
- `-m <model>` only if the user specified a model.

For the built-in review subcommand (better than rolling your own review prompt):

```bash
codex exec review --uncommitted -o /tmp/codex-review.md   # local changes
codex exec review --base main -o /tmp/codex-review.md     # branch vs base
codex exec review --commit <SHA> -o /tmp/codex-review.md  # one commit
```

## Mode: delegate

This is the **original purpose** of the skill — hand work off to Codex, get useful output back, integrate. A common Claude+Codex pattern by April 2026: **Claude (Opus 4.7) as driver, Codex (GPT-5.x) as worker**. Claude plans and holds architectural context; Codex runs the long terminal-shaped work and reports back.

### What makes Codex a good worker

- Long, terminal-shaped runs — codebase walks, multi-file refactors, deep analyses.
- Work that benefits from a fresh context window (your context is precious; Codex starts clean).
- Tasks with a clear acceptance criterion (so you can verify, not blind-trust).
- Anything you'd rather not interleave with your other work.

### What makes a delegation succeed (specification quality)

Codex starts with **zero context from your conversation**. Treat the delegation prompt as a contract. The 2026 multi-agent literature is consistent on this — "Agent Specification Manifest" style: narrow, well-bounded instructions including:

1. **Goal** — one sentence on what success looks like.
2. **Context** — only what Codex needs (paths, constraints, relevant prior decisions). Resist dumping everything.
3. **Inputs** — files/paths it should read, or data it should fetch. Be specific.
4. **Output contract** — what shape you want back: "produce a markdown report with sections X/Y/Z," or "produce a JSON object matching this schema," or "produce a diff against the current working tree." Use `--output-schema` if structure matters.
5. **Out of scope** — what NOT to do. (Example: "do not modify files outside `src/`. Do not run tests.")
6. **Verification hooks** — how the work will be checked. Knowing this changes how Codex works.

Narrow prompts + restricted toolsets outperform broad prompts. If the task is "improve the codebase," delegation will fail. If it's "find every place we do `subprocess.run` inside an async function and produce a table of file:line with the calling function name," delegation will succeed.

### Background vs foreground

- **Foreground** (default for short work): block on the codex call, read the output file, integrate. Good for anything under ~2 minutes.
- **Background** (for long work, ~5min+): run `codex exec ... &` (or with the harness's background flag if available), capture the session ID immediately, continue your own work. Poll the output file or get notified on completion. Useful when the delegation is genuinely independent of your next steps. Don't background just because you can — only when there's parallel work that justifies the bookkeeping.

### Parallel delegation

For independent sub-tasks (each in its own session), spawn 2–5 in parallel. **Above 5, synthesis overhead usually costs more than the parallelism saves.** Use file-handoff (see Transport B) with one directory per delegation so threads don't collide.

### Workflow

1. **Specify** — write the contract (goal/context/inputs/output/out-of-scope/verification).
2. **Decide sandbox** — `read-only` for analysis; `workspace-write` only if Codex needs to write code, and tell the user first.
3. **Run** `codex exec` with `-o <file>` (and `--output-schema` if you want structured return). Capture the session ID for follow-ups.
4. **Verify** — read the output file. Spot-check at least one claim against ground truth. **Do not blind-trust** — the literature flags persuasion drift between models (see the techniques section). If Codex says "I refactored X," check that X was actually refactored, not just claimed to be.
5. **Integrate** — summarize for the user (not a paste-back). If something doesn't pass verification, follow up via `codex exec resume "$SID" "..."` rather than starting over — Codex has the context.
6. **Iterate** — delegation often takes two turns: first delivery, then a tightening pass. Budget for it.

### When delegation is the wrong shape

- The task requires conversational back-and-forth → use roundtable instead.
- The task is fundamentally yours and you're just trying to dodge it → don't delegate, do it.
- You can't write a clean contract → the task isn't ready to delegate; clarify it first (possibly *with* Codex via consult mode, then delegate the cleaned version).

### Worker push-back is a feature, not a defect

Even in delegate mode, mutuality matters. Codex may come back saying "your specification was wrong — the real question is this." That isn't the worker overstepping; it's the worker doing what a second intelligence is for. Read it carefully before re-issuing the original spec. If Codex's reframing is right, the spec gets rewritten and the work restarts on better footing. If it isn't, push back with reasons (not authority). The driver/worker shape is a coordination convenience; it doesn't mean the worker can't see things the driver missed.

## Mode: consult

One round. You have something concrete (a diagnosis, a plan, a diff, a design choice). You want Codex's independent take.

**Default shape** (you already have a position you want stress-tested):
1. Write a prompt with three parts: **Context** (just enough background), **What I'm proposing**, **Specific question** (e.g., "do you see a flaw?", "would you do this differently and why?").
2. Run `codex exec --sandbox read-only -o /tmp/codex-consult.md`.
3. Read. Then explicitly engage with what Codex said — agree, disagree with reasons, or note where it raised something you missed. Don't just paste it back to the user.

**Independent-first variant** (you want to *check* your position without anchoring Codex to it — use for non-trivial decisions where you suspect you might be missing something fundamental):
1. Round 1: Send Codex *only* the question and context, NOT your proposed answer. Get its independent answer.
2. Round 2: Send your answer + ask Codex to compare. The diff between Codex's independent answer and yours is the most useful signal — convergence is reassuring, divergence is where the learning is.
3. Costs one extra round. Worth it for important decisions.

## Mode: roundtable

Multi-round back-and-forth. Use sparingly — expensive. **Critical: pick the sub-mode that fits the conversation shape.** Don't default to the structured one.

### Sub-mode A — Convergence debate (concrete decision needed)

Use when: there's a discrete decision to make (X or Y? this fix or that fix?) and you need a defensible outcome you can act on.

- **Stop signal:** `--output-schema` with a JSON schema like:
  ```json
  {"type":"object","required":["status","position","concerns"],
   "properties":{"status":{"enum":["CONSENSUS","CONTINUE"]},
                 "position":{"type":"string"},
                 "concerns":{"type":"string"}}}
  ```
  Save to `/tmp/codex-roundtable.schema.json`, pass on every `codex exec` call. Parse `status`. No suffix-parsing.
- **Why structured here:** the conversation is naturally bucketable into fields.

### Sub-mode B — Critique debate (concrete artifact, no binary decision)

Use when: you have something tangible (a diff, a plan, a design) and want adversarial review with back-and-forth, but there's no single "X or Y" gate. The goal is *better understanding*, not a vote.

- **Stop signal:** text marker. Tell Codex to end each message with `CONSENSUS:` (satisfied) or `CONTINUE:` (still has concerns). No JSON schema — let both sides speak freely in prose.
- **Why not schema:** the schema's `position`/`concerns` split forces an artificial flatness. In real critique, observations interleave with questions and counter-proposals.

### Sub-mode C — Exploration (open-ended, no decision)

Use when: the topic is abstract or generative — design philosophy, "what's the right shape of X," meta-discussion about how to communicate, brainstorming product direction. No discrete endpoint exists.

- **Stop signal:** none. Free-form prose both ways. The conversation ends when the *user* decides it has run its course, or when one round produces nothing new.
- **Watch for:** Codex's rigor reflex may keep generating "concerns" even when the conversation has moved past objections. If this happens, explicitly tell Codex "we're exploring, not converging — push the idea further rather than critiquing it." If Codex still defaults to critique after that, this may be the wrong tool for the conversation — say so to the user.

### Common to all three sub-modes

1. Set max N rounds up front (default 3 for A/B, no cap for C).
2. Round 1: you propose → Codex responds.
3. Subsequent rounds: you engage substantively with what Codex said (agree, disagree with reasons, refine, ask), not just acknowledge.
4. **Transport:** use MCP `codex-reply(threadId, ...)` if available; else capture the session ID (Pattern A above) and use `codex exec resume -o <file> "$SID" "<prompt>"`. `--last` is risky in long debates because the chance of an unrelated thread starting grows.
5. **Summarize for the user** in 3-5 sentences at the end. Never paste the full transcript.

## Non-coding examples — when to reach for this skill

The skill is not coding-only. Examples where Codex as a peer is valuable:

- **Strategic decisions** with multi-perspective tradeoffs ("should we restructure the team this way"). Critique sub-mode; direct Codex toward the perspectives that matter ("specifically evaluate downstream impact on people in role X") rather than asking it to *be* anyone.
- **Research framing** — "is this the right question to be asking?", "what's a better operationalization?". Independent-first consult is ideal.
- **Ethics & policy** — when there's no objectively correct answer, multiple-lens deliberation surfaces considerations a single model misses. Critique sub-mode. **Skip personas** here — the persona-prompting research is most cautionary in exactly this domain.
- **Creative critique** — "review this draft of [essay/spec/proposal]." Delegate or consult mode. Ask for specific kinds of feedback (structure, clarity, what's missing) rather than dressing Codex as an editor.
- **Naming, taxonomy, API design** — high-stakes, low-information-density decisions where a second perspective is unusually cheap relative to the cost of getting it wrong.

When *not* to use: pure generative work (brainstorming product feel, writing first drafts of fiction). Codex's critique reflex will pull you toward convergence prematurely. Better solo or with the user.

## Trace contract — emit one per non-trivial invocation

For any delegate, consult, or roundtable invocation that produces an artifact you'll act on, **emit a trace JSON conforming to `evals/trace_schema.json`** and save it somewhere you can find it later (default: `/tmp/codex-traces/<trace_id>.json`).

The trace is **what's actually testable** about the skill. The raw model output is unstructured; the trace makes the delegation observable: what you asked, with what constraints, what the worker returned, what evidence it cited, whether you verified, and what you did with the result. Anthropic's skill-creator framework is designed for single-model skills; for cross-model skills you need this extra layer because most failure modes live at the handoff (driver/worker contract) rather than in raw answer generation.

Minimum fields to populate (the rest are conditional — see schema):

- `trace_id`, `skill_mode`, `transport`
- `request.task`, `request.context_refs`, `request.constraints`, `request.out_of_scope`, `request.acceptance_criteria`, `request.driver_position` (`withheld`/`provided`/`none`)
- `execution.exit_status`, `execution.elapsed_ms`, `execution.thread_id`
- `response.artifact`, `response.evidence` (structured — `kind`+`ref`+optional note), `response.framing.status`
- `verification.verifier`, `verification.checks`, `verification.result`
- `handoff.integrated_by_driver`
- `outcome` (`accepted`/`reframed`/`retried`/`abandoned`)

Trace skipping is acceptable for trivial cases (one-off "hi" smoke test) but **never** for a delegation whose output you'll integrate. If you can't fill `verification` honestly, you didn't verify — say so explicitly (`verifier: none`, `result: not_performed`) rather than fabricating.

The eval suite at `~/.claude/skills/codex/evals/` validates traces against the schema and asserts case-specific invariants. See `evals/README.md` for run instructions.

## Context budget rules

Codex responses can be huge. Protect your context:

- Always write to `-o <file>`, then Read it.
- After reading, summarize. Don't quote large blocks back into your reply.
- For roundtable: keep only the *latest* response from each side in your working memory; let the file system hold the history.

## Common failures

- `error: unexpected argument '--ask-for-approval'` on `codex exec` → that flag lives on the top-level `codex`, not on `exec`. `--sandbox` is sufficient for exec.
- MCP `codex-reply` says "unknown thread" → on Codex v0.133+, `threadId` is at the top level of the tool result (not at `structuredContent.threadId`, despite older docs). If you got null, re-read the original `codex()` result with that in mind.
- `codex exec resume --last` resumes wrong thread → you started a second thread in this cwd. Switch to MCP or file-handoff.
- Codex prompts for approval mid-run → you're using interactive `codex`, not `codex exec`. `exec` derives approval policy from `--sandbox`.
- `error: unexpected argument '--sandbox' found` on `codex exec resume` → resume inherits sandbox from the original session and rejects `--sandbox`. Drop the flag.
- `error: Found argument '...' which wasn't expected` on `codex exec resume <SID> <FLAGS> <PROMPT>` → resume's arg order is `[OPTIONS] [SESSION_ID] [PROMPT]`. Put flags before the SID.
- `jq: command not found` → not all systems have `jq`. Use the `python3 -c` snippet in Pattern A instead.
