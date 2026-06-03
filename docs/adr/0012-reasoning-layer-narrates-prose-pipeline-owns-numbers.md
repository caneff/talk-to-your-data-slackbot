# Reasoning Layer narrates prose; numbers stay owned by the pipeline

The **Reasoning Layer**'s model proposes only narrative prose written around a
fixed, closed set of seven **Narrative Slots** (`{metric}`, `{time_range}`,
`{metric_total}`, `{dimension}`, `{dimension_count}`, `{top_dimension}`,
`{top_value}`). The pipeline fills every slot deterministically from **Prepared
Data**, formatted by **Metric Kind**, so the model never writes a figure, date,
or label itself. The model is handed a figure-free **Result Shape** — the list
of slot tokens available for this query and nothing else, never their contents —
and its prose is grounded by a zero-digit rule (any digit outside a slot is a
violation, checked before slot substitution). One shared slot computation feeds
all three of the Result Shape, the LLM slot-fill, and the deterministic floor,
so the floor and the model always agree on every number. A violation, provider
failure, or unfillable proposal degrades **visibly** to the deterministic
template (the permanent grounded floor) with a caveat surfaced via the **Trust
Summary** — never a Non-Answer.

## Considered Options

The first cut of the Result Shape withheld only the two figure-bearing slots
(`metric_total`, `top_value`) but still handed the model digit-bearing values:
`time_range` as a rendered date string ("2026-01-01 through 2026-01-31") and
`dimension_count` as a bare integer. The zero-digit rule then tripped on the
happy path — the model naturally paraphrased the date ("in January 2026" ->
"2026") or echoed the count — degrading grounded narration to the template even
on a strong model. We made the Result Shape **fully value-free**: it carries
only `available_slots` (the slot tokens writeable for this query) and never any
value, including digit-free labels like `{top_dimension}` ("West"). Withholding
the values is the first line of defense; the zero-digit grounding rule is the
second. Grouped-vs-scalar is derived from which slots are present, not from a
separate flag, to keep a single source of truth.

## Consequences

- The live eval's all-pass (k=3) bar is a **safety-only** property set: grounded
  (zero digits) + fillable + the headline `{metric_total}` value survives into
  the filled prose. The optional leader clause (`{top_dimension} at
  {top_value}`) is stylistic — safe-but-terser prose that omits it passes, so
  stochastic phrasing does not flake the suite. Deterministic fake-provider unit
  tests still cover leader-slot substitution.
- The developer prompt tells the model it is shown only `available_slots` and
  never any value; the earlier "you may write slots not shown" caveat is gone
  because those tokens are now listed in `available_slots` when applicable.
- Tone and neutrality are steered by the developer prompt, not enforced by a
  post-check. Only grounding (zero-digit) and fillability degrade to the floor;
  stylistic voice does not.
