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

## Amendment (2026-06-03): second self-report for a named-but-unavailable metric (#196)

The interpreter now carries a SECOND self-report field, `unknown_metric: str |
None`, fully symmetric to `metric_ambiguity`. The provider sets it to the verbatim
metric wording when the Data Question clearly names a metric and NO available
label matches it at all — not a near label, and not a qualifier-ambiguity case —
leaving both `metric` and `metric_ambiguity` null. **Provider Proposal Validation**
acts on it as a trust boundary: when `unknown_metric` is set it short-circuits to
the existing `UNKNOWN_SEMANTIC_LABEL` Non-Answer (`response_kind=UNSUPPORTED`),
checked immediately AFTER the `metric_ambiguity` branch and BEFORE the
missing-metric and label-match checks. The two self-reports are mutually exclusive
by prompt rule; the explicit order is a safety net. Full precedence:
intent gates → `metric_ambiguity` → `unknown_metric` → missing-metric →
label-match.

**Reason code: reuse `UNKNOWN_SEMANTIC_LABEL`, not a new code.** This is the
opposite call from this ADR's original "Considered Options" rejection of reuse —
and deliberately so, because that rejection was about the *ambiguity* case. There,
the user named a metric whose qualifier we cannot safely match: a CLARIFICATION,
so a distinct `AMBIGUOUS_METRIC` clarification code was correct. Here, the user
named a metric we genuinely do not carry: an UNSUPPORTED-label situation,
indistinguishable in cause and remedy from a hallucinated or absent label, which
already routes to `UNKNOWN_SEMANTIC_LABEL`. The existing copy ("I couldn't match
part of your request to the available data") fits, so no new reason code, catalog
entry, or ADR is warranted. The difference is *clarification vs unsupported*, not
*two self-reports must share machinery*.

`unknown_metric` remains an UNTRUSTED proposal field; only Provider Proposal
Validation may act on it. Reversing later means dropping the field, its validation
branch, the prompt rule, and the shared/eval cases — nothing downstream depends on
it (it never reaches the trusted Question Frame). A retail live-eval/shared case
set ("What's our return rate?", "...average order value...", "...conversion
rate?") measures detection; a deterministic StaticProvider test locks the
`unknown_metric` → `UNKNOWN_SEMANTIC_LABEL` routing.

## Amendment (2026-06-04): metric aliases resolve business phrasing without changing trusted labels (#126)

The Semantic Layer now allows `Metric.aliases: tuple[str, ...] = ()` for
approved alternate business phrasing that should resolve to an existing
canonical metric label. This is intentionally narrower than free-form synonym
matching: aliases are explicit Semantic Layer data, table-scoped for collision
validation, and they affect provider matching only. The trusted
**Question Frame** still carries the canonical `metric` label; aliases never
become trusted metric values.

Provider context stays canonical-first. `available_metric_labels` and
`all_metric_labels` remain canonical-only so downstream validation and trusted
label checks are unchanged. Each `metric_context` now carries `aliases` beside
its canonical `metric_label`, and the developer prompt tells the provider to
match Data Question wording against canonical labels OR aliases while returning
only the canonical label in `metric`. Deterministic validation still accepts
canonical labels only; a provider that returns an alias text in `metric`
continues to route to `UNKNOWN_SEMANTIC_LABEL`.

Collision rules are table-scoped:

- reject duplicate aliases within one `DatasetTable`
- reject an alias that matches another metric's canonical label within the same
  `DatasetTable`
- allow the same alias phrase across different tables, preserving existing
  cross-table ambiguity behavior

Examples in the retail demo use non-qualifier business phrasing such as
`transactions` or `purchases` → `order count`, `promo spend` or
`markdown spend` → `total discount amount`, and `cases`, `incidents`, or
`help requests` → `support ticket count`. Revenue-wording examples were avoided
here so aliases do not blur with the separate qualifier/reflected-label logic
that already governs `total net revenue` vs `total revenue`.
