# Question Interpreter Uses a Package Facade

## Status

Accepted

## Context

`question_interpreter.py` grew into a broad module spanning four concerns:
untrusted provider proposal shapes, Semantic Layer context construction, the
OpenAI provider, and **Provider Proposal Validation**, which validates and types
provider output into a trusted Question Frame.

The repo already has packages such as `semantic_layer/` and `workflow/` whose
`__init__.py` files stay empty apart from docstrings. Those packages are used as
namespaces: callers intentionally import qualified submodules such as
`schema.SemanticLayer` or `runner.run_workflow`.

The Question Interpreter is different. Callers consume it as one capability via
`import data_assistant.question_interpreter as question_interpreter`, then reach
the proposal contract, provider construction, semantic context, and
`interpret_question` through that unit-of-use surface.

## Decision

A package's `__init__.py` shape follows how the package is consumed.

Unit-of-use packages expose a thin re-export facade. Namespace packages keep an
empty `__init__.py` and require qualified submodule imports at call sites.

`data_assistant.question_interpreter` is a unit-of-use package, so its
`__init__.py` re-exports the public proposal contracts, OpenAI provider builder,
Semantic Layer context builder, and `interpret_question`. `semantic_layer/` and
`workflow/` remain namespace packages.

This keeps existing `question_interpreter.X` call sites stable while allowing
the internal modules to split by responsibility. The provider seam from
[ADR-0004](0004-defer-llm-orchestration-framework.md) remains in place, and the
**Provider Proposal Validation** boundary affirmed by
[ADR-0008](0008-question-interpreter-owns-filter-value-typing.md) remains owned by
the Question Interpreter.

## Consequences

Two `__init__.py` shapes now coexist, but they follow one rule instead of an
accidental inconsistency: facade for a unit-of-use package, empty namespace for
packages whose submodules are the intended surface.

The facade keeps call sites stable across the mechanical split and gives the
package freedom to rename or regroup internal modules later without forcing
import churn outside the package.
