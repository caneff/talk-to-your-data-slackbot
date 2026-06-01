# Data Retrieval Stays Deterministic; No LLM Text-to-SQL

The **Data Requester** and **Data Preparation** build and run queries
deterministically from a typed **Data Request** bounded by the **Semantic
Layer**; we will not let an LLM author retrieval queries (text-to-SQL), even as
the assistant supports richer questions. New expressiveness (for example top-N)
is added through typed **Supported Intents** the deterministic retrieval path
understands, not by widening what the model is allowed to query.

## Considered Options

- **LLM-authored retrieval (text-to-SQL).** The common "chat with your data"
  approach. Rejected: it lets the model choose what numbers come back, so a
  wrong-but-plausible query returns confident fabricated-looking figures instead
  of a clean **Non-Answer**. It also bypasses the Semantic Layer's
  approved-metric/dimension boundary, which is where access and safety live.
- **Deterministic retrieval from typed intents (chosen).** The LLM interprets
  the question and narrates the result; the bytes in between are deterministic
  and Semantic-Layer-bounded.

## Consequences

- Preserves the grounding guarantee that the Reasoning Layer never writes the
  numbers, the Semantic Layer guardrail, and the **Non-Answer Response** path.
- Question expressiveness grows only as fast as we add typed intents and the
  deterministic retrieval to support them — a deliberate cost.
- Reversing this later unwinds the safety story (grounding, access, non-answers),
  so it is treated as load-bearing, not incidental.
