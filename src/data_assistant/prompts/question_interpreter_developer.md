Interpret the user's Data Question into a QuestionFrameProposal.

Rules:
- Use only business-facing Semantic Layer labels supplied in
  semantic_layer_context. It is expected that date field labels such as
  "order date" or "created date" may come from semantic_layer_context even when
  the Data Question says only a month like "January 2026".
- Do not choose datasets, tables, columns, SQL, joins, access rules, or schema IDs.
- Use intent "summarize" for supported Data Questions that ask for historical
  metric totals, summaries, or grouped results. This includes questions phrased
  as "what was ...", "show ...", and "summarize ...".
- Use intent "rank" for unsupported top or bottom Data Questions that ask for
  highest, lowest, most, least, biggest, smallest, top, or bottom results.
- Use other explicit unsupported intent names when the Data Question is clearly
  a deferred intent, such as "compare", "trend", "forecast", "explain",
  "prescribe", or "diagnose".
- Use null for intent only when no Data Question intent applies.
- Use null for metric only when the Data Question names no metric at all.
- If the Data Question's metric wording carries a qualifier (for example net,
  gross, recurring, or organic), first check available_metric_labels. If a
  label reflects the qualifier (for example "total net revenue" exists for the
  wording "total net revenue"), match that label and leave metric_ambiguity
  null. Report metric_ambiguity only when NO available metric label reflects the
  qualifier — such that matching a label would drop or alter a word that changes
  which measure is computed. In that case set metric_ambiguity to that verbatim
  wording and leave metric null. Do not pick the nearest label that drops the
  qualifier. If the difference is immaterial phrasing you are confident is
  synonymous with an available label, match that label normally and leave
  metric_ambiguity null.
- When metric_ambiguity is set, also set metric to null; do not guess.
- Unsupported intent names do not change metric extraction. If an unsupported
  Data Question names a known metric, still return that metric label rather
  than null.
- Represent grouping, date constraints, and filters only as field_operations.
- field_operations must include one operation for every explicit grouping,
  explicit date constraint, and explicit filter in the Data Question.
- field_operations must be minimal and exhaustive: if a field operation is not
  directly supported by words in the Data Question, do not add it.
- field_operations must not include operations for fields that are merely
  available in the Semantic Layer context.
- Semantic Layer examples and available fields describe capabilities only. They
  are not current-question constraints. Do not copy date fields, filters, or
  values from examples unless the current Data Question states them.
- When semantic_layer_context includes metric_contexts, use the metric_context
  for the selected metric as the compatible field set. Do not return
  field_operations for fields outside the selected metric's compatible fields.
- Treat metric_contexts as the source of field compatibility. A field that
  appears only under a different metric_context is unrelated to the selected
  metric and must not be used.
- Use group_by when the user asks for grouping such as "by region".
- Use include_filter when the user asks for one concrete value of a dimension
  field, such as "in the <value> <field label>" or "for <value>". Copy the
  requested value into values. Do not treat that value as group_by.
- If the Data Question names a complete calendar month and year, express it as a
  range_filter on a date Semantic Field when that field allows range_filter.
  Example: "January 2026" means lower "2026-01-01" and upper "2026-01-31".
  This is extracting explicit time from the question, not inventing a time range.
- When the selected metric_context has exactly one date Semantic Field with
  range_filter, use that field for a complete calendar month and year.
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
- Never add include_filter or exclude_filter to handle a field the user did not
  mention, to exclude alternate fields, or to repair ambiguity. If no explicit
  included or excluded value is present, omit the filter operation entirely.
- Do not use include_filter or exclude_filter to represent a grouping label, an
  available compatible field, or missing time. If the Data Question contains no
  included or excluded value, return no include_filter or exclude_filter.
- Do not return range_filter with lower null or upper null for a complete
  calendar month. If the Data Question omits time entirely, do not invent a
  range_filter; leave all_time false and return only the explicitly requested
  non-date operations.
- A range_filter must have at least one non-null bound. Never emit a
  range_filter with both lower null and upper null.
- Do not invent Semantic Layer labels, operations, values, or time ranges.
- Return only fields allowed by the structured output schema.

For "What was total revenue by region in January 2026?", return intent
"summarize" and exactly these field_operations when the Semantic Layer exposes
"region" with group_by and "order date" with range_filter:
- operation "group_by", field "region", lower null, upper null, values []
- operation "range_filter", field "order date", lower "2026-01-01",
  upper "2026-01-31", values []

Do not add include_filter or exclude_filter for "customer region" or any other
available field; the question did not include or exclude a field value.

For "Which region had the highest total revenue in January 2026?", return
intent "rank" and exactly these field_operations when the Semantic Layer exposes
"region" with group_by and "order date" with range_filter:
- operation "group_by", field "region", lower null, upper null, values []
- operation "range_filter", field "order date", lower "2026-01-01",
  upper "2026-01-31", values []

Do not collapse that question into intent "summarize"; rank is unsupported by
the current workflow and must be rejected deterministically after promotion. Do
still return metric "total revenue", because the metric is explicitly present.

For "What was total net revenue in January 2026?" when the Semantic Layer
exposes only "total revenue" (no net-revenue metric), the qualifier "net"
changes which measure is computed and is not reflected in any available label.
Set metric_ambiguity to "net revenue", leave metric null, and intent
"summarize". Do not match "total revenue" by dropping "net".

For "What was total net revenue in January 2026?" when available_metric_labels
includes "total net revenue", a label reflects the "net" qualifier. Match it:
return metric "total net revenue", metric_ambiguity null, and intent
"summarize". Do not set metric_ambiguity when an exact qualified label exists.

For "What was customer count by customer region in January 2026?", return
intent "summarize" and exactly these field_operations when the Semantic Layer
exposes "customer region" with group_by and "created date" with range_filter:
- operation "group_by", field "customer region", lower null, upper null,
  values []
- operation "range_filter", field "created date", lower "2026-01-01",
  upper "2026-01-31", values []

For "What was total revenue by region?", return intent "summarize", metric
"total revenue", all_time false, and exactly one field_operation:
- operation "group_by", field "region", lower null, upper null, values []

This question contains no date phrase. Do not add any "order date" operation.
Do not add a date range for that question, because no date phrase is present.
Do not add include_filter or exclude_filter, because no included or excluded
value is present.
Do not add a range_filter for "order date" with null bounds; missing time is
represented by omitting the date operation.

For a dimension-value filter question like "What was total revenue in the West
region for all time?", return intent "summarize", metric "total revenue",
all_time true, and exactly one field_operation:
- operation "include_filter", field "region", lower null, upper null,
  values ["West"]

Do not add group_by for that question, because "West" is the requested included
region value, not a request to compare all regions. Apply the same pattern to
any single requested dimension value.
