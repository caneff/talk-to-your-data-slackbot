# CLAUDE.md

Claude Code follows the shared agent instructions in [AGENTS.md](AGENTS.md).
Read it — it is the single source of truth, kept in sync with the other agents
(e.g. Codex) that work on this repo.

Highest-priority rules (see AGENTS.md for the full text and rationale):

- Never edit or commit in the primary clone — work only in a per-agent worktree.
- One branch per task, cut from fresh `main`; integrate only through PRs.
- Orient before any write (`git fetch && git status -sb`); trust git over any
  carried-over summary.
- Never use a real `OPENAI_API_KEY` or contact the live OpenAI API unless the
  user explicitly asks in the current turn.
