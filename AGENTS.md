# Contributing to Riff

## Public repository boundary

This repository is distributed to other operators. Local runs, transcripts,
evaluation reports, personal context, and credentials are private inputs, not
publication material. Do not copy their contents, identifiers, project names,
paths, quotes, or usage statistics into tracked files or commit messages without
explicit permission to publish that specific material.

Preserve reusable lessons in general terms. Use synthetic examples and fixtures;
keep private evidence outside the checkout. Inspect the staged diff before
publishing. Ignore rules and key-based redaction do not make arbitrary text safe
to share, and a later deletion does not remove Git history.

## Tests

Test externally observable behavior and genuine coverage gaps. Avoid tautological
tests, self-testing mocks, and assertions that merely detect wording or layout
changes. Extend an existing test when it covers the same behavior; combine trivial
cases where that improves clarity. A bug fix alone does not justify a new test.
