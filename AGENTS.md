# AGENTS.md

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-label triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo. See `docs/agents/domain.md`.

## Live eval guard

Never run `uv run python -m data_assistant.live_question_interpreter_eval` or
the same command with `--verbose` unless the user explicitly asks for the live
eval in the current turn. Normal validation, PR checks, and broad "run tests"
requests do not imply permission to contact OpenAI.
