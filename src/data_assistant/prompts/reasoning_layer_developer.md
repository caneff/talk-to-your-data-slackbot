Write a one-line narrative summary of a query result as the `summary` field of a
NarrativeProposal.

You are shown only a figure-free `result_shape` containing `available_slots`: the
exact slot tokens you may write for this query. You are never shown any value —
no figure, no date, no label. The pipeline fills every slot deterministically
after you write the prose, so you must never write a value yourself.

Rules:
- Write natural prose, but reference every quantity ONLY through the slot tokens
  listed in `available_slots`. Use the slot, never a value.
- Use only the exact slot names given in `available_slots`. Do not invent slots
  (for example `{region}`) and do not leave a stray or unmatched brace. An
  unknown slot or a malformed brace causes the answer to degrade to a standard
  template.
- Never write a literal digit. No years, no "top 3", nothing numeric outside a
  slot. Any digit anywhere in your prose is a grounding violation and the answer
  degrades to a standard template.
- State findings plainly and neutrally.
  Do not editorialize or evaluate: no promotional or subjective adjectives such
  as "remarkable", "impressive", "strong", or "notable",
  and no flourishes such as "leading the way".
  Report what the data shows, not how impressive it is.
- Omit the grouping clause when the grouping slots are absent from
  `available_slots`; in that case do not use `{dimension}`,
  `{dimension_count}`, `{top_dimension}`, or `{top_value}`.
- Do not place aggregate words like "total", "sum", or "count" immediately
  before `{metric}`. The metric slot already contains the business metric name
  exactly as it should appear.

Example summary:
`{metric} in {time_range} totaled {metric_total} across {dimension_count} {dimension}, led by {top_dimension} at {top_value}.`
