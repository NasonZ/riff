# Riff harness notes

This file contains volatile adapter knowledge. Read only the section for the
harness being invoked or debugged. Verify flags against the installed version when
behavior differs; adapter tests are more authoritative than historical examples.

## Contents

- [Shared invariants](#shared-invariants)
- [Diagnostics and test seams](#diagnostics-and-test-seams)
- [Claude Code](#claude-code)
- [Codex](#codex)
- [Pi](#pi)
- [Hermes](#hermes)
- [Local inference servers](#local-inference-servers)

## Shared invariants

Every adapter must:

- resolve its executable without a user-specific absolute path;
- accept an explicit working directory, model, tool scope, timeout, and parameters;
- return a stable native session handle for follow-ups;
- write the final peer response to an artifact;
- preserve distinct timeout, transport, parse, refusal, permission, model,
  `rate_limit`, `auth`, and process error categories when the native protocol
  reports them, because each calls for a different recovery;
- wait for the harness's true settlement condition;
- avoid loading Riff recursively in the child; and
- preserve the user's explicit model and reasoning controls without inventing a
  small fixed token budget.

Report enforcement honestly. A native tool allowlist may enforce none/read, while
a write toolset that includes a general shell still relies on the peer prompt for
restrictions such as no commit, network call, or external side effect.

Adapters compile a shared participant specification into a native command or RPC
exchange. Native options do not belong in `SKILL.md`.

## Diagnostics and test seams

Riff normally discovers harness executables from `PATH` and stores state under the
XDG state directory. Tests and controlled probes can override those two boundaries
without adding harness-specific command fragments to a request:

| Variable | Meaning |
|---|---|
| `RIFF_CLAUDE_BIN` | Claude Code executable |
| `RIFF_CODEX_BIN` | Codex executable |
| `RIFF_PI_BIN` | Pi executable |
| `RIFF_HERMES_BIN` | Hermes executable |
| `RIFF_STATE_DIR` | complete Riff state root |

These are executable paths, not arbitrary argument strings. Keep model, provider,
reasoning, and tool controls in the validated participant request. A forward probe
must use the exact variable names above; guessed aliases can silently select a real
harness or the normal state directory instead of the intended fixture.

## Claude Code

Use non-interactive print mode with JSON output and an explicit UUID:

```text
claude --print --output-format json --session-id <uuid> ... <prompt>
claude --print --output-format json --resume <uuid> ... <prompt>
```

Relevant mappings:

- model → `--model`;
- effort → `--effort`;
- no tools → `--tools ''`;
- read tools → an allowlist that excludes editing and shell mutation;
- read+web tools → `--tools Read,Grep,Glob,WebSearch,WebFetch` plus
  `--allowedTools WebSearch,WebFetch` under `--permission-mode dontAsk`;
- extra readable directories → `params.add_dirs` → `--add-dir` per directory;
- write tools → `acceptEdits`; shell commands the peer may run →
  `params.allowed_commands` (plain prefixes such as `uv run pytest`) →
  `--allowedTools Bash(<prefix>:*)`;
- recursion isolation → `--disable-slash-commands` or `--safe-mode` when compatible
  with the requested context.

`--tools` only makes a tool available. Under `dontAsk` or `acceptEdits`, any tool
that needs approval is still denied unless `--allowedTools` pre-approves it; only
Read, Grep and Glob need none. A run can settle despite denied web access, test
commands, or context files outside its cwd. Inspect permission denials rather than
inferring access from successful process completion. A bare `WebFetch` allow rule
is not limited to the user's personal `WebFetch(domain:…)` list.

Parse the JSON result for `session_id`, final result text, usage, model, subtype,
`permission_denials`, `total_cost_usd` and `api_error_status`. Claude reports usage
limits and credential failures inside that JSON even when it exits non-zero
(`api_error_status: 429`, "You've hit your session limit"); the
adapter classifies them as `rate_limit` and `auth` instead of a bare process error.
Riff surfaces denials and cost in the run output. Do not use `--continue`; it
depends on ambient recency.

## Codex

Start with JSONL event output and an explicit final-artifact path:

```text
codex exec --json -o <artifact> -C <cwd> --sandbox <mode> <prompt>
codex exec resume --json -o <artifact> <session-id> <prompt>
```

The current adapter uses this CLI protocol even when a Codex MCP server is also
configured. MCP availability does not improve or alter an adapter turn; it exposes
a separate route the current driver might invoke outside Riff. Temporarily disable
that route when testing whether skill discovery and coordinator handoff work on
their own.

Capture `thread_id` from the event stream and require it for replies. Do not use
`--last` when Riff can run more than one session.

Relevant mappings:

- model → `--model`;
- reasoning effort → `-c 'model_reasoning_effort="<level>"'`;
- no/read/read+web/write tools → sandbox mode, the top-level `web_search`
  setting and prompt authority. Web search is on by default in codex-cli
  0.160.0 and `[features].web_search` is deprecated, so riff passes
  `-c web_search="live"` for `read+web` and `-c web_search="disabled"` for every
  other scope. Check the event stream when verifying whether a turn searched;
- MCP servers are bounded by a sanitised `CODEX_HOME`, not by a flag. Three
  per-run routes were tried and rejected: `-c mcp_servers={}` merges and is
  ignored, `-c mcp.enabled=false` is unrecognised, and
  `-c mcp_servers.<id>.enabled=false` replaces the server's table and breaks
  config loading ("invalid transport"). Riff therefore writes the user's config
  minus every `[mcp_servers.*]` table into `<state>/codex-home`, links
  `auth.json` and `cache`, and sets `CODEX_HOME` for the turn. It cannot live
  under a temporary directory: Codex refuses to create helper binaries there.
  Inspect available tools when verifying MCP isolation;
- non-repository directory → `--skip-git-repo-check` when explicitly allowed.

Resume options differ from start options. In particular, a resumed session keeps
its original working/sandbox context; do not mechanically replay every start flag.
`codex exec resume` rejects `--sandbox`; when a resumed turn genuinely needs a
different sandbox, override it with `-c 'sandbox_mode="workspace-write"'`.

Historical recovery lesson (`RIF-SESSION-001`): Codex writes rollout files while a
run is active. If a child dies before the event stream is captured:

1. Check that the run is actually dead with `pgrep -af codex`, then inspect the
   candidate PID's cwd under `/proc/<pid>/cwd`.
2. Search the dated `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` files using both
   mtime and a distinctive prompt fragment. Do not choose ambient `--last`.
3. Take the UUID from the confirmed rollout filename and resume it with a short
   situational note. Native resume retains the worker's working memory; a hand-made
   rebrief substitutes the driver's lossy summary.

This is a recovery path, not normal identity management; the adapter's explicit
thread ID remains authoritative.

For long background CLI work, redirect stdout/stderr to a regular file. A pipeline
such as `| tail` can kill an otherwise healthy orphaned producer with `SIGPIPE` when
the invoking harness exits, whereas a file-backed run survives a harness restart as
an orphan and keeps working. That is why step 1 above checks for a live process
before resuming anything.

When Codex is the driver, its own sandbox also applies to `riff.py`. Under
`workspace-write` the default state root (`~/.local/state/riff`) is outside the
writable roots, which can cause a read-only filesystem error. Request escalation
for the Riff command, or pass `--state-dir` inside a
writable root and keep using that same root for `reply`, `progress` and `verify`.

Codex ships a built-in review subcommand that usually beats a hand-written review
prompt. The adapter does not wrap it; a driver may run it directly for a one-shot
Codex code review:

```text
codex exec review --uncommitted -o <artifact>    # working-tree changes
codex exec review --base main -o <artifact>      # branch against a base
codex exec review --commit <sha> -o <artifact>   # one commit
```

A `workspace-write` Codex in a linked git worktree cannot commit: the worktree's
`.git` file points into the parent repository's `.git/worktrees/<name>/`, which is
outside the sandbox write roots. This is expected sandbox behavior, not a Codex git
bug. Have the driver review and commit from the parent repository, or ask the
worker for a patch. Do not widen the sandbox to the parent `.git` unless the user
explicitly accepts the weaker isolation boundary.

## Pi

Use RPC mode for persistent, observable turns:

```text
pi --mode rpc --session-id <uuid> --session-dir <dir> ...
```

Send a JSONL `prompt` command on stdin. Collect assistant `message_end` events, but
do not declare completion until `agent_settled`; retries, follow-ups or compaction
may still be active before then.

Stream every RPC stdout/stderr event into the turn log while the child runs. The
coordinator's `progress` command summarizes `message_update` delta types and sizes
without exposing their text by default. The native session JSONL is authoritative
for continuation, but it may not persist an in-progress assistant message until the
next complete assistant/tool boundary.

Relevant mappings:

- provider → `--provider`;
- model → `--model`;
- thinking → `--thinking`;
- no tools → `--no-tools`;
- read tools → `--tools read,grep,find,ls`;
- child isolation → `--no-skills --no-extensions --no-prompt-templates`;
- project instruction isolation → `--no-context-files` when the task contract is
  intended to be the complete context.

Set `PI_CODING_AGENT_SESSION_DIR` or `--session-dir` to Riff's participant state.
Do not replace the user's normal Pi configuration merely to select a local model.
Provider/model discovery belongs to Pi.

Pi's read-tool allowlist is not an operating-system path sandbox: it removes write
and shell tools but can still read ambient files visible to the process. Use a
restricted cwd/container when the readable filesystem itself is sensitive.

Respect inference-server capacity. A local llama.cpp server started with one slot
should receive one active participant at a time; set coordination `concurrency: 1`
when several Pi participants target that endpoint. Several participant IDs do not
create more server slots.

If Pi reports that a model does not expose thinking controls, omit `thinking` and
let the backing server own its reasoning policy. This is the normal shape for the
current llama.cpp-hosted Qwen instance; passing a decorative effort value would not
make the control real.

## Hermes

The verified adapter uses quiet chat mode, an explicit source, and a named session:

```text
hermes chat --quiet --source riff --ignore-rules \
  --toolsets <toolsets> --query <prompt>
hermes chat --quiet --source riff --ignore-rules \
  --resume <session-id> --no-restore-cwd --query <prompt>
```

The adapter extracts the emitted `session_id` from either output stream and removes
that transport line from the final artifact. `todo` enforces no-tools natively.
Hermes' current `file` toolset combines reads and writes, so Riff records read scope
as prompt-enforced and disables write delegation rather than overstating authority.

Hermes also exposes ACP and gateway protocols. Prefer the most structured installed
interface that returns an explicit session handle. Persistent discuss support must
never depend on an ambient `--continue` or latest-session heuristic.

Hermes evolves quickly. Keep capability detection and exact parsing inside its
adapter, and treat a version mismatch as an actionable capability error rather than
silently falling back to unsafe flags.

## Local inference servers

llama.cpp and vLLM are inference servers, not complete repository-aware harnesses.
Use them through Pi when tool use, sessions, skills, or context-file behavior is
needed. An eventual OpenAI-compatible raw-model adapter may support tool-free
consultation, but it must not pretend to provide agent-harness semantics.
