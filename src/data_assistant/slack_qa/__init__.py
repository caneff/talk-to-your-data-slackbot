"""QA tooling for the Slack product (battery, preflight, and the QA driver).

This is internal tooling, not a public surface: callers import the real
submodules directly (no facade re-exports). The dependency arrow runs
``slack_qa`` -> ``slack`` (tooling depends on product), never the reverse.
"""
