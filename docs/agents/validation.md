# Validation gate

Before opening or updating a PR — and whenever a skill says "run validation",
"validate", "run the checks", or "make sure it's green" — all five of these
commands must pass. Treat them as a single gate: a PR is not ready while any one
is red.

| Command                          | Gate                                  |
| -------------------------------- | ------------------------------------- |
| `uv run pytest`                  | Tests pass                            |
| `uv run pyright`                 | Type check clean (strict mode)        |
| `uv run ruff check .`            | Lint clean (`E,F,I,B,UP`)             |
| `uv run ruff format --check .`   | Formatting clean (no diff)            |
| `uv build --wheel`               | Package wheel builds cleanly          |

Run tool commands through the pinned project environment where applicable, and
build the wheel from the checked-out project. Keep every run fake, mocked,
network-free, and cost-free — see the Paid OpenAI API guard in
[AGENTS.md](../../AGENTS.md).

## Fixing a red formatting gate

`ruff format --check` only reports; it never edits. To make it green, run the
formatter and commit the result:

```
uv run ruff format .
```

Do not hand-format around it or carve out exceptions. The repo is formatted
repo-wide; new code is expected to land already formatted.

## Notes for workers and handoffs

- This is the canonical list. Do not infer validation commands ad hoc or treat
  `ruff format` or wheel build as optional — both are part of the gate.
- There is currently no CI workflow or pre-commit hook enforcing this; the gate
  is enforced by the agent workflow. Keep this file as the single source of
  truth so every skill (TDD, handle-next-issue worker handoffs, review) gates on
  the same five commands.
