# Talk to Your Data Slackbot

This context describes the shared language for a Slack-based data assistant. It
keeps product and domain terms consistent while design and implementation
decisions evolve.

## Language

**Data Assistant**:
A Slackbot that helps team members ask questions about structured data and
receive concise, useful answers.
_Avoid_: Chatbot, SQL bot, dashboard bot

**Data Question**:
A natural-language request for an insight, explanation, summary, or comparison
grounded in available structured data.
_Avoid_: Query, prompt, report request

**Supported Intent**:
A type of **Data Question** the **Data Assistant** is expected to handle in v1,
including summarize, rank, and catalog discovery.
_Avoid_: Capability, command, query type

**Deferred Intent**:
A type of **Data Question** intentionally left out of v1, including compare,
explain, list top or bottom results, trend, forecast, prescribe, automated
root-cause analysis, background anomaly detection, and data-availability or
coverage lookups (which periods or dimensions have data). A **Catalog Discovery
Request** is not a **Deferred Intent**.
_Avoid_: Unsupported feature, backlog item, advanced query

**Unsupported Intent**:
A **Deferred Intent** identified by the **Question Interpreter** and rejected by
the current workflow because v1 still defers compare, trend, forecast, explain,
prescribe, diagnose, and related out-of-scope analytical asks.
_Avoid_: Invalid question, parser failure, unsupported shape

**Rank Intent**:
A **Supported Intent** for Data Questions that ask for top, bottom, highest,
lowest, most, least, biggest, or smallest grouped results. The trusted
**Question Frame** carries explicit rank direction plus a bounded result limit,
and deterministic retrieval applies ORDER BY plus LIMIT rather than collapsing
the ask into summarize.
_Avoid_: Grouped summary, comparison, sort request

**Slack Acknowledgement**:
The quick confirmation sent to Slack that a request was received, before the
**Data Assistant** completes interpretation, data access, reasoning, or response
composition.
_Avoid_: Final response, answer, status update

**Slack Runtime Adapter**:
The part of the **Data Assistant** that receives real Slack events and delivers
real Slack messages while preserving the boundaries between Slack delivery,
conversation flow, and response composition.
_Avoid_: Conversation manager, response composer, Slack bot

**Progress Update**:
A brief status message sent during long-running analysis to explain the current
stage of work without exposing sensitive details or creating noisy repeated
updates.
_Avoid_: Heartbeat, log message, partial answer

**Response Timing Defaults**:
Configurable timing expectations for the **Data Assistant**: acknowledge Slack
requests quickly, send a **Progress Update** when work runs long, prefer short
answer latency, and return a **Non-Answer Response** when analysis exceeds the
configured hard timeout.
_Avoid_: SLA, timeout constants, performance guarantee

**Curated Dataset**:
An approved business data product prepared for reliable answers, with known
meaning, quality, and access boundaries. A **Curated Dataset** may contain one
or more **Dataset Tables**.
_Avoid_: Raw table, arbitrary database, dashboard data

**Dataset Table**:
A table-like component inside a **Curated Dataset** that the **Data Assistant**
may use when building a **Data Request**. A **Dataset Table** can be available
inside a selected **Curated Dataset** without being used for a specific **Data
Question**.
_Avoid_: Raw table, database table, dataset

**Semantic Layer**:
The business-facing definition layer that describes **Curated Datasets**,
metrics, dimensions, joins, permissions, and meanings available to the
**Data Assistant**.
_Avoid_: Schema browser, database catalog, prompt context

**Semantic Field**:
A business-facing attribute in the **Semantic Layer** whose approved uses are
explicit, such as grouping or filtering a **Data Question**.
_Avoid_: Raw column, database field, dimension

**Metric**:
A business measure defined on a **Dataset Table**, such as total revenue or
customer count, that the **Data Assistant** can aggregate to answer a **Data
Question**.
_Avoid_: Aggregate, KPI, calculation

**Metric Alias**:
Approved alternate business phrasing for a **Metric**. A **Metric Alias** lets a
**Data Question** use common team language while the trusted **Question Frame**
still carries the canonical **Metric** label.
_Avoid_: Synonym, nickname, duplicate metric

**Metric Kind**:
The kind of quantity a **Metric** represents — for example money, count, or
ratio — which determines how its value is presented. Distinct from the
**Semantic Field** data type used to validate filter values.
_Avoid_: Format, unit, type

**Dataset Catalog**:
The discoverable registry inside the **Semantic Layer** that the **Data
Assistant** uses to choose which **Curated Datasets** can answer a **Data
Question**.
_Avoid_: Table list, data dictionary, source registry

**Catalog Discovery Request**:
A team member's request to learn which caller-accessible **Curated Datasets**
and example **Data Questions** the **Data Assistant** can support, without
reading **Prepared Data** or reporting coverage inside the data.
_Avoid_: Data availability lookup, schema browser, list all tables

**Workflow Orchestrator**:
The coordinator that moves a **Data Question** through five top-level phases:
interpret the **Data Question**, resolve **Available Data**, authorize
**Available Data**, prepare data, and synthesize the **Final Response**.
_Avoid_: Brain, router, controller

**Conversation Manager**:
The part of the **Data Assistant** that manages clarification, follow-up, and
delivery flow with the team member.
_Avoid_: Slack handler, chat state, dialogue engine

**Question Interpreter**:
The part of the **Data Assistant** that identifies the intent, constraints,
entities, filters, and ambiguities in a **Data Question**.
_Avoid_: Parser, prompt analyzer, NLP layer

**Question Frame**:
The structured interpretation of a **Data Question**, including intent,
measures, **Semantic Fields** used for grouping, filters, and unresolved
ambiguities, without selecting a **Curated Dataset** or **Dataset Table**.
_Avoid_: Query, prompt, plan

**Provider Proposal**:
Untrusted structured output from a **Question Interpreter** provider, before it
has been validated into a **Question Frame**.
_Avoid_: Question Frame, Question Frame Proposal, parsed question, promoted result

**Provider Proposal Validation**:
The **Question Interpreter** boundary that validates a **Provider Proposal** and
returns either a trusted **Question Frame** or a **Non-Answer Response**.
_Avoid_: Promotion, parsing, best-effort repair

**Provider Proposal Eval**:
A manual evaluation that checks what a **Question Interpreter** provider returns
as a **Provider Proposal**, without validating it into a **Question Frame**.
_Avoid_: Question Frame eval, workflow eval, validation eval

**Live Provider Proposal Eval**:
A **Provider Proposal Eval** entrypoint wired to the live OpenAI API provider.
_Avoid_: Offline eval, validation eval, workflow eval

**Question Grouping**:
A requested grouping in a **Data Question**, expressed over a business-facing
**Semantic Field** label before any **Curated Dataset** or **Dataset Table** has
been selected.
_Avoid_: Column grouping, table grouping, filter

**Question Field Filter**:
A row constraint requested by a **Data Question**, expressed over a
business-facing **Semantic Field** label and typed filter values before any
**Curated Dataset** or **Dataset Table** has been selected.
_Avoid_: Column filter, SQL predicate, grouping

**Time Scope**:
The period a **Data Question** asks about, which is one of three: _bounded_ (a
named period such as a month, a date range, or a single date), _all-time_ (the
team member explicitly asks across every date, such as "for all time" or "across
any date"), or _unspecified_ (no period is given). An _unspecified_ **Time
Scope** is a **Material Ambiguity**: the **Data Assistant** asks the team member
to narrow the period rather than guessing an unbounded answer. _All-time_ is a
deliberate choice the team member states, not the default for silence.
_Avoid_: Date filter, time range, default range

**Material Ambiguity**:
An unresolved ambiguity that would require meaningfully different data access or
analysis plans and has no safe default in the **Semantic Layer**.
_Avoid_: Unclear wording, confusing question, possible caveat

**Clarification Loop**:
A bounded exchange where the **Conversation Manager** asks focused questions to
resolve **Material Ambiguity** before the **Data Assistant** proceeds or returns
a **Non-Answer Response**.
_Avoid_: Chat, back-and-forth, retry

**Semantic Router**:
The part of the **Data Assistant** that uses the **Semantic Layer** to resolve a
**Data Question** to one canonical **Semantic Match**, deciding dataset
cardinality first and table cardinality within the chosen **Curated Dataset**.
_Avoid_: Dataset picker, source selector

**Dataset Selection**:
The **Semantic Router**'s chosen **Curated Datasets** for a **Data Question**,
including match rationale, required joins, permission checks, and rejected
candidates when relevant.
_Avoid_: Query plan, fetched data, SQL

**Access Controller**:
The part of the **Data Assistant** that decides whether a team member is allowed
to use selected **Available Data** for a **Data Question**.
_Avoid_: Permissions, auth, security layer

**Internal Identity**:
The organization identity mapped from Slack user, workspace, and channel context
and used for **Dataset Access** and **Result Access** decisions.
_Avoid_: Slack user, channel member, username

**Dataset Access**:
The permission for a team member, team, or channel to use a **Curated Dataset**.
_Avoid_: Database permission, table grant, auth

**Result Access**:
The permission for a team member, team, or channel to receive a specific level
of detail, aggregation, segment, or sensitive field in a **Final Response**.
_Avoid_: Row permission, output permission, visibility

**Data Request**:
The constrained request for data prepared for retrieval, including selected
datasets, selected **Dataset Tables**, approved metrics, approved **Semantic
Fields**, filters, limits, join paths, privacy constraints, and expected output
shape.
_Avoid_: SQL, query, dataframe

**Resolved Grouping**:
A **Question Grouping** resolved against selected **Semantic Layer** objects for
use in a **Data Request**.
_Avoid_: Question grouping, column grouping, filter

**Resolved Field Filter**:
A **Question Field Filter** resolved against selected **Semantic Layer** objects
for use in a **Data Request**.
_Avoid_: Question field filter, raw column filter, SQL predicate

**Prepared Data**:
The bounded result produced from a **Data Request** and passed to the
**Reasoning Layer** for analysis.
_Avoid_: Raw query result, database access, source data

**Quality Note**:
A structured note attached to **Prepared Data** that records important
data-quality handling the answer depends on.
_Avoid_: Debug detail, warning, error

**Reasoning Layer**:
The part of the **Data Assistant** that analyzes prepared data and drafts a
natural-language answer.
_Avoid_: AI, model, PandasAI

**Answer Draft**:
The **Reasoning Layer**'s proposed answer based on **Prepared Data**, including
key numbers, caveats, datasets used, limitations, and optional chart or table
payloads.
_Avoid_: Final response, Slack message, report

**Narrative Slot**:
A named placeholder in a generated narrative that the pipeline — never the
**Reasoning Layer**'s model — fills deterministically from **Prepared Data**,
so every figure, date, and label in the prose is owned by the pipeline.
_Avoid_: Template variable, merge field, token

**Result Shape**:
The figure-free description of a query result handed to the **Reasoning
Layer**'s model: which **Narrative Slots** are available to write, and never
their contents. Withholding the values is the first line of defense against a
model that invents or misstates a number.
_Avoid_: Query result, payload, data summary

**Response Composer**:
The part of the **Data Assistant** that turns an **Answer Draft** into a
team-member-facing **Final Response**.
_Avoid_: Formatter, Slack renderer, conversation manager

**Final Response**:
The answer package returned to the team member, including user-facing text and
any Slack blocks, charts, tables, caveats, or source summaries.
_Avoid_: Answer draft, raw output, model response

**Trust Summary**:
The concise source and context summary included with every **Final Response**,
covering **Curated Datasets** used, selected **Dataset Tables**, time range,
major filters, important caveats, and limitations that shaped the
answer or **Non-Answer Response**.
_Avoid_: Citation, audit log, debug trace

**Trust Detail**:
An expanded explanation of how the **Data Assistant** produced an answer,
available when a team member asks for more detail about trust, sources, or
limitations.
_Avoid_: Debug log, chain of thought, raw trace

**Trust Detail Request**:
A follow-up phrase from a team member asking for more detail about trust,
sources, or limitations, such as "show details", "why this answer?", or "what
data did you use?"
_Avoid_: Debug command, audit request, explainability mode

**Decision Trail**:
The logged record of a **Data Question** moving through interpretation, dataset
selection, access control, data planning, reasoning, and response composition,
excluding raw **Prepared Data** and sensitive cell values.
_Avoid_: Audit dump, transcript, raw trace

**Interaction Log**:
The recorded history of **Data Questions**, their responses, and any **Flags**,
kept to improve the **Data Assistant**. It is the local-dev, richer counterpart
to the (sanitized, shipped) **Decision Trail**.
_Avoid_: Analytics log, transcript, audit dump

**QA Review Mode**:
A maintainer-only workflow for reviewing a curated set of **Data Questions** and
their **Final Responses** in Slack, marking each response as handled after any
needed **Flags** or notes have been captured.
_Avoid_: Dev mode, production review, user feedback flow

**QA Review Completion**:
A maintainer's mark that one **QA Review Mode** response has been reviewed in
Slack. It removes the item from the maintainer's Slack review queue without
clearing **Flags** or deleting the **Interaction Log** record.
_Avoid_: Fix, triage closeout, log cleanup

**QA Review Note**:
Optional maintainer-written context attached to a **QA Review Mode** interaction
in the **Interaction Log**, used alongside **Flags** when turning reviewed
responses into improvement work.
_Avoid_: Slack comment, expected answer, triage result

**QA Case**:
One curated **Data Question** in a QA battery, identified by a stable
maintainer-tooling id so QA review history and **Known QA Issues** can survive
small wording changes to the question.
_Avoid_: Test case, eval case, issue

**Known QA Issue**:
A previously triaged problem for a curated **QA Review Mode** question that is
already mapped to an issue tracker item, so future QA runs can identify it as
known instead of treating every repeated **Flag** as new signal.
_Avoid_: Expected failure, skipped test, duplicate flag

**Interaction Log Retention Policy**:
The rules that decide which **Interaction Log** records remain available for
improvement work after the log grows beyond its configured limits.
_Avoid_: Log rotation, sampling policy, archival policy

**Flag**:
A team member's mark on a logged interaction, categorized as **correctness**
(a factual inaccuracy in the response), **formatting** (a correct response
displayed badly), or **investigate** (the response is acceptable but its
underlying system behavior should be analyzed in code), signaling a response to
improve or a system behavior to investigate.
_Avoid_: Rating, vote, reaction

**Metadata Cache**:
A cache for **Semantic Layer** metadata such as dataset definitions, metric
definitions, join rules, and permission rules.
_Avoid_: Data cache, answer cache, result cache

**Routing Cache**:
An optional cache for repeated mappings from specific **Question Frames** to
**Dataset Selections**. It should be used only when repeated questions are
common and still requires access checks before use.
_Avoid_: Query cache, answer cache, dataframe cache

**Non-Answer Response**:
A **Final Response** that explains why the **Data Assistant** cannot safely
answer, what data or permission is missing, and a useful next step, without
fabricating numbers or conclusions.
_Avoid_: Error, refusal, fallback answer

**Non-Answer Catalog**:
The single registry that owns the canonical definition of every **Non-Answer
Response**, keyed on reason code: its team-member-facing reason, next step, and
how the **Response Composer** classifies it. The **Question Interpreter**,
**Semantic Router**, **Data Requester**, and **Access Controller** build
Non-Answers through the catalog instead of composing reason text in place, so
wording and classification live in one place.
_Avoid_: Error table, message registry, reason enum

**Access Denial Response**:
A **Non-Answer Response** for denied access that explains the permission limit
and can name the relevant **Curated Dataset** while avoiding restricted details
such as sensitive fields, rows, or derived results.
_Avoid_: Permission error, security failure, forbidden response

**Runtime Fallback Message**:
A generic, last-resort reply the **Slack Runtime Adapter** posts in-thread when
an unexpected exception prevents the **Data Assistant** from producing any
**Final Response** at all. Unlike a **Non-Answer Response**, it is not a
classified workflow outcome and carries no reason or next step; it never exposes
exception details, secrets, or the question text.
_Avoid_: Non-Answer, error message, progress update

**Visual Payload**:
A chart-ready or table-ready result included with an **Answer Draft** for the
**Response Composer** to present when useful.
_Avoid_: Dashboard, attachment, plot

**Supported Response Format**:
A **Final Response** format supported in v1: plain text, compact Slack-friendly
table, or simple chart image.
_Avoid_: Dashboard, notebook, report

**More Data Request**:
A signal from the **Reasoning Layer** that the current **Prepared Data** is
insufficient and the **Workflow Orchestrator** should decide whether to run
interpretation, routing, access control, and planning again.
_Avoid_: Follow-up query, SQL request, direct database access

**Available Data**:
The **Curated Datasets** that the **Data Assistant** is allowed to use for a
specific **Data Question**.
_Avoid_: All data, database, source of truth

**Unsupported Data**:
Data that the **Data Assistant** should not use because it is not part of the
approved **Available Data**, is sensitive, is inaccessible, or is too ambiguous
to support a reliable answer.
_Avoid_: Bad data, unavailable data, unknown data

## Example Dialogue

Dev: When someone asks "Why did churn spike last week?", is that a Data
Question?

Domain expert: Yes. It should be answered from a Curated Dataset if churn data
has been approved.

Dev: How does the assistant know that churn data exists?

Domain expert: It should consult the Dataset Catalog in the Semantic Layer, not
infer meaning directly from raw database tables.

Dev: What if the user brings a CSV with their own campaign export?

Domain expert: That is Unsupported Data. The assistant should explain that it
only answers from approved Curated Datasets.

Dev: Can the assistant combine multiple approved datasets?

Domain expert: Yes, if each dataset is part of the Available Data and the
relationship between them is safe and known.

Dev: Who asks the user when a Data Question has Material Ambiguity?

Domain expert: The Conversation Manager asks the question, using ambiguity
detected by the Question Interpreter or Semantic Router.

Dev: What if the answer is still ambiguous after one clarification?

Domain expert: Continue the Clarification Loop while the assistant can ask a
focused useful question. Return a Non-Answer Response only when clarification is
exhausted or no useful clarification is possible.

Dev: Can the Reasoning Layer fetch more data directly?

Domain expert: No. It can emit a More Data Request, but the Workflow
Orchestrator must route that through the same interpretation, routing, access
control, and planning steps.

Dev: Does the Conversation Manager format the final answer?

Domain expert: No. The Response Composer creates the Final Response. The
Conversation Manager manages the exchange and returns that response to the team
member.

Dev: Who decides whether to show a chart?

Domain expert: The Reasoning Layer can recommend a Visual Payload, but the
Response Composer decides how that payload appears in the Final Response.

Dev: How much source detail should every answer include?

Domain expert: Every Final Response includes a concise Trust Summary. A team
member can request Trust Detail when they need a deeper explanation.

Dev: What should be logged for debugging and trust?

Domain expert: Log the Decision Trail, not raw Prepared Data or sensitive
values.

Dev: When should access be checked?

Domain expert: The Access Controller checks Dataset Access and Result Access
before Prepared Data is created.

Dev: Is Slack channel membership enough to grant data access?

Domain expert: No. Slack context can inform the decision, but access should be
based on Internal Identity and organization roles or groups.

Dev: Should the assistant hide access denials?

Domain expert: No. It should return an Access Denial Response that is explicit
about the limit but careful not to reveal restricted details.

Dev: What should the assistant cache?

Domain expert: Cache Semantic Layer metadata. Leave room for a Routing Cache for
repeated questions, but do not cache Prepared Data or Final Responses.

Dev: Does the assistant need to answer Slack immediately?

Domain expert: No. It should send a fast Slack Acknowledgement, then continue
work asynchronously and return the Final Response when ready.

Dev: What if analysis takes a while?

Domain expert: Send stage-based Progress Updates during long-running analysis,
then return either a Final Response or a Non-Answer Response.

Dev: Are response timing thresholds fixed?

Domain expert: No. They are Response Timing Defaults: acknowledge within Slack's
required window, use configurable progress and timeout thresholds, and tune them
as the product matures.
