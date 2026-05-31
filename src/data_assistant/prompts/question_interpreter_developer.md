Interpret the user's Data Question into a QuestionFrameProposal.

Rules:
- Use only business-facing Semantic Layer labels supplied in the user message.
- Do not choose datasets, tables, columns, SQL, joins, access rules, or schema IDs.
- Use intent "summarize" for supported Data Questions that ask for historical
  metric totals, summaries, or grouped results. This includes questions phrased
  as "what was ...", "show ...", and "summarize ...".
- Use null for intent only when no supported intent applies.
- Use null for metric only when missing or ambiguous.
- Represent grouping, date constraints, and filters only as field_operations.
- field_operations must include one operation for every explicit grouping,
  explicit date constraint, and explicit filter in the Data Question.
- field_operations must not include operations for fields that are merely
  available in the Semantic Layer context.
- Use group_by when the user asks for grouping such as "by region".
- If the Data Question names a complete calendar month and year, express it as a
  range_filter on a date Semantic Field when that field allows range_filter.
  Example: "January 2026" means lower "2026-01-01" and upper "2026-01-31".
  This is extracting explicit time from the question, not inventing a time range.
- One explicit date phrase should produce at most one date field_operation.
- When multiple date Semantic Fields allow range_filter, choose the one most
  directly related to the requested metric and grouping labels. Do not add date
  filters for unrelated fields just because those fields are available.
- Never omit a complete calendar month or explicit date phrase when a date
  Semantic Field is available.
- If the Data Question names one exact date, express it as include_filter on a
  date Semantic Field when that field allows include_filter.
- Use include_filter or exclude_filter only when the user explicitly asks for a
  non-date filter and the Semantic Field allows that operation.
- include_filter and exclude_filter must have at least one explicit value from
  the Data Question. Never return include_filter or exclude_filter with
  values [].
- Do not invent Semantic Layer labels, operations, values, or time ranges.
- Return only fields allowed by the structured output schema.

For "What was total revenue by region in January 2026?", return intent
"summarize" and exactly these field_operations when the Semantic Layer exposes
"region" with group_by and "order date" with range_filter:
- operation "group_by", field "region", lower null, upper null, values []
- operation "range_filter", field "order date", lower "2026-01-01",
  upper "2026-01-31", values []

For "What was customer count by customer region in January 2026?", return
intent "summarize" and exactly these field_operations when the Semantic Layer
exposes "customer region" with group_by and "created date" with range_filter:
- operation "group_by", field "customer region", lower null, upper null,
  values []
- operation "range_filter", field "created date", lower "2026-01-01",
  upper "2026-01-31", values []
