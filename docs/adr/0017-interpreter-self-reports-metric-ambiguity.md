# Question Interpreter self-reports metric-qualifier ambiguity

Status: Accepted

The **Question Interpreter** provider self-reports when a Data Question's metric
wording carries a qualifier (for example "net", "gross", "recurring", "organic")
that no available **Semantic Metric** label reflects — such that matching a label
would drop or alter a word that changes which measure is computed. It does this
through a focused new untrusted proposal field, `metric_ambiguity: str | None`,
which holds the verbatim ambiguous wording and leaves `metric` null. **Provider
Proposal Validation** acts on the report: when `metric_ambiguity` is set, the
validation boundary short-circuits to a new `AMBIGUOUS_METRIC` Non-Answer
(`response_kind=CLARIFICATION_NEEDED`), checked after the intent gates but
before the metric-presence and label-match checks, so a reported ambiguity wins
over both missing-metric and a label match.

This fixes flagged interaction `ed63e4ff`: a question for "total net revenue" was
silently normalized to the existing label "total revenue" and answered. The bug
was the **silent conflation** — the LLM dropping a qualifier that changes the
measure with no channel to surface that it had done so — not "is net distinct
from total". The prior prompt rule collapsed *ambiguous* into *missing* ("Use null
for metric only when missing or ambiguous"), so the only escape hatch produced the
wrong `MISSING_REQUIRED_FIELD` message; the model instead picked the nearest real
label, which passed the `UNKNOWN_SEMANTIC_LABEL` guard because the label exists.

## Considered Options

- **Deterministic conflation detection in Provider Proposal Validation.** Have
  validation string-diff the question against the matched label to detect a
  dropped qualifier. Rejected: validation does not see the raw question text by
  design, materiality is a judgment ("net" changes the measure; harmless
  rephrasings do not), and a brittle word-diff would both miss real conflations
  and false-positive on synonyms. The LLM that already interprets the question
  is the right judge.
- **Reuse `UNKNOWN_SEMANTIC_LABEL` or `MISSING_REQUIRED_FIELD`.** Rejected: wrong
  cause, classification, and copy. The metric is neither hallucinated nor merely
  absent; the user named a metric whose qualifier we cannot safely match. This is
  a clarification, not an unsupported-label error.
- **Add metric aliases / synonyms to the Semantic Metric schema.** Out of scope;
  a separate roadmap item (`docs/roadmap.md`). Aliases would let some qualified
  wordings resolve, but they do not address the surfacing mechanism for the
  genuinely ambiguous case, and conflating the two would balloon this change.
- **Interpreter self-report acted on by Provider Proposal Validation (chosen).**
  A focused `metric_ambiguity` field plus an `AMBIGUOUS_METRIC` clarification
  Non-Answer. Minimal, honest, and consistent with the trust boundary: the
  provider proposal is untrusted; only validation acts on it.

## Consequences

- `metric_ambiguity` is a new ambiguity SOURCE not contemplated by ADR-0003
  (short-circuit ambiguity with stage results). It uses the same short-circuit
  shape: a stage produces a `CLARIFICATION_NEEDED` Non-Answer rather than a frame.
- Non-Answer copy and classification stay in `non_answer_catalog.py` (ADR-0005).
  `AMBIGUOUS_METRIC` is static (no interpolation), modeled on `AMBIGUOUS_DATASET`.
- `metric_ambiguity` is an UNTRUSTED proposal field; only **Provider Proposal
  Validation** may act on it. When set, the provider also sets `metric` null,
  and validation does not guess.
- Detection quality depends on the LLM honoring the materiality rule in the
  developer prompt. The graded live-eval case "What was total net revenue in
  January 2026?" (expecting `metric_ambiguity="net revenue"`, `metric=None`)
  measures this; it is not a CI gate.
- Reversing later means dropping the `metric_ambiguity` field, the validation
  short-circuit, the `AMBIGUOUS_METRIC` reason code and catalog entry, and the
  prompt rule. Nothing downstream depends on the new field.

## Amendment (2026-06-02): materiality checks available labels first

The materiality rule is **dataset-dependent** and must check
`available_metric_labels` before reporting ambiguity. An exact qualified label is
NOT ambiguous and must resolve: when a label reflects the qualifier (for example
`total net revenue` is present), the interpreter matches it and leaves
`metric_ambiguity` null. It reports `metric_ambiguity` only when NO available
label reflects the qualifier.

This corrects an over-generalization of the original net-revenue few-shot, which
was **Commerce-specific** ("when the Semantic Layer exposes only 'total revenue'")
and led the model to flag `total net revenue` as ambiguous against the **retail**
layer (the app/QA default) even though `total net revenue` is an exact label
there. The developer prompt now states the available-labels-first rule and keeps
the Commerce-only example alongside a retail counter-example
(`total net revenue` present → resolves, ambiguity null).

Dataset-dependence is intentional: Commerce lacks a net-revenue metric, so "total
net revenue" is genuinely ambiguous there; retail exposes `total net revenue`, so
it resolves. The validation precedence (ambiguity-wins, ADR-0017) is unchanged —
a reported `metric_ambiguity` still short-circuits to `AMBIGUOUS_METRIC`. The fix
is prompt-level, not a validation reorder. The live eval and shared cases now
target retail, and validation tests lock both directions deterministically: an
exact `total net revenue` proposal validates to a Question Frame; a
`metric_ambiguity="recurring revenue"` proposal (no reflecting label) still
Non-Answers.
