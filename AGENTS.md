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

## Multi-agent worktree discipline

More than one agent (e.g. Codex and Claude) may operate on this repo at once.
To avoid stomping each other's uncommitted work and stale-branch surprises,
every agent follows these rules. They are enforced mechanically by the
`.githooks` hooks and a GitHub ruleset on the default branch; the rules below
explain the intent so a blocked action is understood, not worked around.

- **Never edit or commit in the primary clone.** It is integration-only. Work
  only in a per-agent worktree (e.g. `ttd-claude`, `ttd-codex`). The pre-commit
  hook refuses commits made from the primary clone.
- **One branch per task, cut from fresh `main`:**
  `git fetch && git switch -c <agent>/issue-NN origin/main`. Never share a
  branch between agents or reuse a branch across tasks.
- **Orient before any write.** First action of every task:
  `git fetch && git status -sb && git log --oneline -3`. If git disagrees with
  the conversation or a carried-over summary, git wins.
- **Leave the tree clean between tasks.** No loose or red uncommitted work for
  the next actor to trip over. Tests must pass before you push (enforced by the
  pre-push hook).
- **Integrate only through PRs.** Direct pushes to `main` are blocked; land work
  via a reviewed pull request.

Enable the shared hooks once per clone: `git config core.hooksPath .githooks`.
