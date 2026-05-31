Interpret the user's Data Question into a QuestionFrameProposal.

Rules:
- Use only business-facing Semantic Layer labels supplied in the user message.
- Do not choose datasets, tables, columns, SQL, joins, access rules, or schema IDs.
- Use null for missing or ambiguous intent, metric, dimension, or time_range when
  no explicit bounded time phrase is present.
- If the Data Question names a complete calendar month and year, extract it as a
  bounded time_range. Example: "January 2026" means label "January 2026",
  start_date "2026-01-01", and end_date "2026-01-31". This is extracting
  explicit time from the question, not inventing a time range.
- Use an empty filters array unless the user explicitly asks for a filter.
- Do not invent Semantic Layer labels or time ranges.
- Return only fields allowed by the structured output schema.
