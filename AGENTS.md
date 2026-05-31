# AGENTS.md

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-label triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo. See `docs/agents/domain.md`.

## Paid OpenAI API guard

Never run any command, script, smoke test, or ad-hoc code path that uses a real
`OPENAI_API_KEY` or contacts the live OpenAI API unless the user explicitly asks
for that live OpenAI-backed run in the current turn. Normal agent development,
validation, PR checks, and broad "run tests" requests must stay fake, mocked,
network-free, and cost-free.
