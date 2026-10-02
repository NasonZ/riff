# Riff

Riff lets Claude Code, Codex, Pi, and Hermes consult, discuss, or delegate to one
another through one shared Agent Skill.

It combines two things:

- accumulated guidance for productive cross-model collaboration; and
- a deterministic coordinator for processes, native sessions, artifacts, timeouts,
  permissions, and traces.

The current interactive harness remains the driver. Peers return independent
artifacts; the driver verifies and synthesizes them.

```text
Claude Code / Codex / Pi / Hermes
               │ current driver
               ▼
          shared Riff skill
               │
               ▼
         local coordinator
        ┌──────┼──────┐
        ▼      ▼      ▼
     Claude  Codex    Pi ── local or hosted models
                       └── Hermes
```

## Why both a skill and code?

The skill contains the judgment that made the original Riff useful:

- independent-first elicitation;
- openness to reframing;
- peer rather than master/subordinate posture;
- persona and persuasion discipline;
- bounded discussion;
- explicit delegation contracts; and
- verification before integration.

The coordinator makes fragile mechanics reproducible:

- unique participant and session identity;
- multiple instances of the same harness;
- native start and resume;
- Pi `agent_settled` handling;
- parallel fan-out and sequential pipelines;
- write-directory collision guards and request warnings;
- recursion limits;
- verification checks it executes itself; and
- automatic privacy-conscious run records whose output tells the driver what to do
  next, so the obligations survive even if the skill text leaves its context.

See [the playbook](references/PLAYBOOK.md),
[protocols](references/PROTOCOLS.md), [harness notes](references/HARNESSES.md),
and [design](references/DESIGN.md).

## Supported adapters

| Harness | Start/reply | Model controls | Tool scope |
|---|---|---|---|
| Claude Code | Explicit session UUID | model, effort, configured provider, extra read dirs, allowed test commands | none/read/read+web/write |
| Codex | Explicit thread ID | model, reasoning effort, OpenAI/local mode | sandboxed none/read/read+web/write |
| Pi | Persistent JSONL RPC | provider, model, thinking | none/read/write |
| Hermes | Explicit quiet-CLI session | provider, model, max turns | none/read; write disabled |

Use Pi for llama.cpp/vLLM-hosted models when agent features are required. Those
servers supply inference, while Pi supplies sessions, tools, and settlement.

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

### Migrate overlapping skills safely

Skill selection happens before Riff's body can arbitrate a collision. After Riff
passes a live validation, make older broad-triggering `codex` or `qwen-peer` skills
non-automatic while keeping them recoverable:

- In Claude Code, add `disable-model-invocation: true` to an old skill's frontmatter
  if it should remain available for explicit invocation.
- In Hermes, add an overlapping builtin name to `skills.disabled` while keeping
  `riff` available through `external_dirs`.
- Move a superseded directory outside scanned skill roots instead of deleting it
  until the migration has been exercised from every intended driver.

Then use a fresh session for both a positive prompt (for example, “ask a Codex peer
to review this”) and a negative prompt that merely mentions Codex. Confirm the
positive case selects Riff and the negative case stays solo.

A configured Codex MCP server is separate from the old skill. Riff's current Codex
adapter uses `codex exec` JSONL, so a connected MCP remains a parallel raw route
that Claude could choose directly. For a strict migration probe, temporarily
disable or remove that MCP after preserving its definition, then restore it later
only if a deliberate escape hatch is wanted.

## Check the installation

```bash
python3 scripts/riff.py capabilities
python3 -m unittest discover -s tests -v
```

No third-party Python dependency is required.

For deterministic driver probes, the supported executable overrides are
`RIFF_CLAUDE_BIN`, `RIFF_CODEX_BIN`, `RIFF_PI_BIN`, and `RIFF_HERMES_BIN`; use
`RIFF_STATE_DIR` for isolated state. See
[the harness notes](references/HARNESSES.md#diagnostics-and-test-seams).

## Request example

```json
{
  "version": 1,
  "mode": "consult",
  "task": "Find the strongest flaw in this proposed design.",
  "origin_harness": "claude",
  "participants": [
    {
      "id": "codex-review",
      "harness": "codex",
      "cwd": "/absolute/project/path",
      "tools": "read",
      "params": {"reasoning_effort": "high"}
    },
    {
      "id": "qwen-local",
      "harness": "pi",
      "provider": "llama.cpp",
      "model": "qwen",
      "cwd": "/absolute/project/path",
      "tools": "read"
    }
  ],
  "coordination": {
    "dispatch": "broadcast",
    "independent_first": true,
    "max_rounds": 3
  },
  "driver_prediction": "The migration ordering; anything deeper changes the plan.",
  "context_refs": ["docs/design.md"],
  "constraints": ["Do not modify files"],
  "acceptance_criteria": ["Cite file:line for each concern"],
  "out_of_scope": ["Do not propose a storage rewrite"]
}
```

Run it:

```bash
python3 scripts/riff.py validate --request request.json   # errors and warnings
python3 scripts/riff.py run --request request.json        # prints the run ID first
```

The result points to participant artifacts and the run manifest, lists any tools a
peer was denied, and carries `next_steps` for the driver. Continue a native session
with `riff.py reply`, then record verification; `--run` commands are executed and
their exit codes recorded, while `--check` text is labelled as asserted:

```bash
python3 scripts/riff.py verify --run-id <uuid> --verifier claude \
  --run "python3 -m unittest discover -s tests" --check "Read the diff" --integrated
```

`run` prints the run ID on stderr before it blocks. For long runs, or a driver whose
shell caps one call's duration, use `run --detach` and then `wait --run-id <uuid>`
(bounded; call again while it reports running). For long Pi/Qwen turns, inspect the
run from another shell:

```bash
python3 scripts/riff.py progress --run-id <uuid> --participant qwen-local
```

The default live view reports RPC delta and durable-session metadata without
exposing reasoning or answer contents. `--previews` explicitly opts into short
content previews.

## Development

Keep tests focused on invariants. Process tests use fake harness executables, so
they validate command construction, parsing, persistence, and settlement without
spending model tokens. Live model smoke tests are opt-in and should exercise every
driver direction before old installed skills are retired.

Riff uses the MIT License.
