# Short Circuit Ambiguity With Stage Results

Workflow stages that can detect ambiguity will return typed stage results rather
than raising or guessing. The **Question Interpreter**, **Semantic Router**, and
**Data Requester** can each return a `NonAnswer` immediately when they detect an
ambiguity, and the workflow runner will short-circuit instead of letting
downstream stages infer missing meaning.
