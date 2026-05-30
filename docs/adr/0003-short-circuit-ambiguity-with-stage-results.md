# Short Circuit Ambiguity With Stage Results

Workflow stages that can detect ambiguity will return typed stage results rather
than raising or guessing. The **Question Interpreter**, **Semantic Router**, and
**Data Requester** can each return a `NonAnswer` immediately when they detect an
ambiguity, and the workflow runner will short-circuit instead of letting
downstream stages infer missing meaning.

> **Amended by [ADR-0006](0006-semantic-router-owns-available-data-resolution.md).**
> The **Data Requester** no longer detects ambiguity: all Available Data
> cardinality resolution (dataset and table) now lives in the **Semantic
> Router**, and `NonAnswerStage.DATA_REQUESTER` is removed. The short-circuit
> pattern itself is unchanged.
