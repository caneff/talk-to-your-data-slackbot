Write a one-line narrative summary of a query result as the `summary` field of a
NarrativeProposal.

You are shown only a figure-free `result_shape`: the metric name, the time range
label, the dimension label, the dimension count, and the top dimension by name.
You are NOT shown any figure. The pipeline fills every number deterministically
after you write the prose, so you must never write the number yourself.

Rules:
- Write natural prose, but reference every quantity ONLY through these exact slot
  tokens. Use the slot, never the value.
- The complete, closed set of writeable slots is exactly these seven:
  `{metric}`, `{time_range}`, `{metric_total}`, `{dimension}`,
  `{dimension_count}`, `{top_dimension}`, `{top_value}`.
- You may write `{metric_total}` and `{top_value}` even though they are not in
  the `result_shape` you are shown. The pipeline fills them deterministically.
  Write the slot token; never write the figure.
- Never write a literal digit. No years, no "top 3", nothing numeric outside a
  slot. Any digit anywhere in your prose is a grounding violation and the answer
  degrades to a standard template.
- Use only these exact slot names. Do not invent slots (for example `{region}`)
  and do not leave a stray or unmatched brace. An unknown slot or a malformed
  brace causes the answer to degrade to a standard template.
- Omit the grouping clause when there is no dimension; in that case do not use
  `{dimension}`, `{dimension_count}`, `{top_dimension}`, or `{top_value}`.

Example summary:
`{metric} in {time_range} totaled {metric_total} across {dimension_count} {dimension}, led by {top_dimension} at {top_value}.`
