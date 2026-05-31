# Question Interpreter Owns Filter-Value Typing

## Status

Accepted

## Context

The Question Interpreter coerces provider-proposed filter values into typed
Python values (`datetime.date`, `decimal.Decimal`, `str`) in
`_coerce_field_value`, branching on each Semantic Field's `data_type`. Bad
values are rejected at this boundary with an `INVALID_PROVIDER_OUTPUT`
Non-Answer.

This raised a question (issue #48): once a query-building engine such as
PandasAI is introduced, that engine is the natural owner of "this string is a
date / this is a decimal", so a parallel coercion layer in the interpreter
could become legacy the moment such an engine lands.

Two facts shape the decision:

- **No query engine exists.** ADR-0004 deferred the LLM-orchestration /
  query-building framework indefinitely, and CONTEXT.md lists `PandasAI` under
  the terms to avoid. Locking the contract against a hypothetical engine means
  guessing at capabilities that aren't here.
- **Typed values are load-bearing today.** The typed `FieldValue`s flow through
  the Question Frame and Data Request to `data_preparation._filter_sql`, which
  binds them as DuckDB query parameters (`connection.execute(query,
  filter_parameters)`). Coercion is not a throwaway parallel layer; it is what
  makes parameter binding type-correct right now.

The stable thing to reason about is therefore not the future engine but the
**trust boundary**: the Question Interpreter is where untrusted LLM provider
output enters the system.

## Decision

The Question Interpreter validates *and* fully types provider-proposed filter
values at the trust boundary. `QuestionFrame.field_operations` carry validated,
typed `FieldValue`s (`datetime.date | decimal.Decimal | str`) as a durable
contract; downstream stages consume typed values and never re-parse strings.

The issue's "duplicates the engine's typing" concern is rejected as a category
error: rejecting untrusted provider output and constructing a retrieval query
are distinct responsibilities. The interpreter rejects values that cannot be a
valid date/decimal for the requested field; an engine types values to build a
query. These do not duplicate, so there is nothing to deduplicate by moving
coercion downstream.

No code moves under this decision. `_coerce_field_value`, the `FieldValue`
alias, and the `INVALID_PROVIDER_OUTPUT` Non-Answer behavior are unchanged.

## Consequences

Invalid-value rejection stays at the trust boundary, on the Non-Answer surface,
where the user-facing failure path already lives. The typed-value contract that
DuckDB parameter binding depends on is affirmed rather than weakened.

If a future query engine ever specifically needs raw, untyped strings, that is a
deliberate change that supersedes this ADR — not a hedge baked into the contract
now. Until then, "the interpreter emits typed values" is the rule a future
change must justify breaking, not an acknowledged debt.

## Alternatives considered

- **Move coercion behind retrieval (interpreter passes raw values, engine types
  them).** Rejected: it pulls invalid-value rejection downstream, away from the
  Non-Answer surface and the trust boundary, and there is no engine to receive
  raw values today.
- **Split: interpreter validates coercibility but does not produce final typed
  values.** Rejected: it frames typed emission as provisional and documents an
  intent to undo something that currently works (DuckDB parameter binding),
  against a component that may never arrive in the assumed shape. It adds
  ambiguity to a clean contract for no present benefit.
