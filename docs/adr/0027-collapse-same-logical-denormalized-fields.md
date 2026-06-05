# Collapse Same-Logical Denormalized Semantic Fields

## Status

Accepted

## Context

The richer retail **Semantic Layer** denormalizes some dimensions onto multiple
**Dataset Tables**. For example, `store region` exists on `demo_orders` and
`demo_stores`; `order date` exists on `demo_orders` and `demo_order_lines`; and
`product category` exists on both product and order-line tables. These repeated
fields are intentional copies of the same business-facing **Semantic Field** so a
metric can be answered from the table that already contains both the metric and
the dimension.

The current **Provider Proposal Validation** logic rejects any field label with
more than one candidate before **Semantic Router** runs. That means a correct
provider proposal such as `group_by = "store region"` for "What was total net
revenue by store region in Q1 2026?" returns `INVALID_PROVIDER_OUTPUT` even
though the provider used an approved field label and the later table matcher can
choose `demo_orders` because it contains both `total net revenue` and
`store_region`.

This is a trust-boundary bug, not a provider bug. A duplicate label can mean two
different things:

- the same logical **Semantic Field** copied onto multiple tables, which should
  collapse to one business field label in the trusted **Question Frame**; or
- genuinely different fields that share a label, which should remain an
  internal layer-configuration ambiguity.

The codebase has no join-path model today. **Semantic Router** only matches a
single **Dataset Table** that already contains the requested metric plus all
requested fields. This decision therefore covers denormalized copies and
metric-compatible table selection, not cross-table joins.

## Decision

Duplicate-label **Semantic Field** candidates collapse to one logical field only
when all candidates share the same identity tuple:

- `field_id`
- `source_column`
- `data_type`
- exact set of allowed `operations`

When that tuple matches, the repeated fields are one logical **Semantic Field**
available on multiple **Dataset Tables**. **Provider Proposal Validation**
accepts the label, validates operation support and typed values against that
collapsed logical field, and emits the canonical field label in the trusted
**Question Frame**.

The physical table copy is selected later by **Semantic Router**. It evaluates
**Dataset Tables** and chooses the canonical `SemanticMatch` whose table contains
the requested metric and compatible field copy. For example:

- `total net revenue by store region` resolves to `demo_orders.store_region`
  because `total net revenue` lives on `demo_orders`.
- `store count by store region` resolves to `demo_stores.store_region` because
  `store count` lives on `demo_stores`.

No join is implied. If the metric table does not contain a compatible copy of
the requested field, the existing **Semantic Router** table-cardinality behavior
applies.

If a label has multiple identity tuples, it is genuinely ambiguous layer
configuration. Provider output is still structurally valid, so this condition
must not be classified as `INVALID_PROVIDER_OUTPUT`. A follow-up behavior slice
owns the exact reason code and copy, but the principle is locked here: report a
truthful internal field-configuration ambiguity and do not tell the user to
rephrase a correct business label.

## Consequences

The **Question Interpreter** stops treating same-logical denormalized dimensions
as provider failures. Shared-label retail questions can reach **Semantic
Router**, where the existing metric-compatible table matching can resolve the
right table copy.

The identity tuple intentionally includes operation set. Two fields with the
same label, `field_id`, `source_column`, and type but different allowed
operations are not the same logical field contract. Collapsing them would make a
field appear safely usable for operations that are not approved everywhere the
label appears.

The decision preserves ADR-0008. Provider Proposal Validation still owns field
operation validation and filter-value typing; it simply validates against a
collapsed logical field when repeated candidates are provably the same field.
Downstream stages continue to receive typed `FieldValue`s.

The decision preserves ADR-0006. **Semantic Router** still owns **Available
Data** resolution all the way down to one `SemanticMatch`. This ADR does not move
table selection into the interpreter; it removes an earlier false reject so the
router can do its existing job.

The decision preserves ADR-0005 and ADR-0007. The new genuinely-ambiguous case
needs structured Non-Answer classification and catalog-owned copy. It should be
implemented as a Non-Answer reason distinct from `INVALID_PROVIDER_OUTPUT`,
because the provider did not return malformed output.

## Alternatives considered

- **Reject every duplicate label during Provider Proposal Validation.**
  Rejected: this is current behavior and it breaks denormalized fields even when
  they are intentional copies of the same logical field.
- **Collapse by label only.** Rejected: two different business fields can share a
  label. Label-only collapse would silently answer with the wrong meaning.
- **Collapse by `field_id` only.** Rejected: it misses source-column, type, and
  operation-contract drift. A copied identifier with different physical or
  operation semantics is not safe to treat as one field.
- **Add joins now and select an owning dimension table.** Rejected: the Semantic
  Layer has no join-path schema and current retrieval reads one table. This
  issue is about letting denormalized table copies work; join planning would be
  a separate architectural change.
