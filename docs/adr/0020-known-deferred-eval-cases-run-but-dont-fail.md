# Known-Deferred Eval Cases Run But Don't Fail The Suite

## Status

Accepted

## Context

The shared Question Frame cases (`question_frame_cases.SHARED_QUESTION_FRAME_CASES`)
include a band of cases whose `expected.intent` is an analytical intent the
pipeline does not yet support — `trend`, `forecast`, `explain`, `prescribe`
(issues #44–47). The model is not asked to produce a correct supported answer
for these; the interpreter is expected to classify the intent, but the rest of
the pipeline cannot yet act on it. As a result these cases reliably "fail" the
field-level meaning comparison in the live eval.

Two forces collide:

- The coverage guard
  (`test_shared_cases_cover_every_deferred_intent_once_classified`) deliberately
  keeps every deferred intent present and classified, so we must **not** delete
  or weaken these cases. Issue #158 made the do-not-disable rule explicit:
  cases stay in the suite so we keep exercising the classifier and keep seeing
  the day the model improves.
- Left untouched, every one of these cases lands in the streamed failures JSONL
  snapshot and pushes `report.failed` above zero, so the run exits nonzero. The
  signal that matters — a *new* regression on a supported case — drowns in
  expected noise, and the failures snapshot is polluted with cases nobody is
  going to fix today.

The obvious tools are `pytest.skip`/`xfail`, but the live eval is a manual
runner, not a pytest case, and skipping stops surfacing the moment the model
starts getting a deferred case right. We want suppress-but-run, not skip.

## Decision

Add a `deferred: bool = False` marker to `SharedQuestionFrameCase` (threaded
into `LiveEvalCase`), set `deferred=True` on the four known-deferred-intent
cases, and branch the run loop on it:

1. **A deferred case that still mismatches** is recorded in a separate
   `LiveEvalReport.known_deferred` bucket. It is **not** counted in
   `report.failed` and is **not** written to the failures JSONL snapshot. The
   run reports it (`Known-deferred: N`) but exits 0 when these are the only
   "failures".

2. **A deferred case that now fully passes** is a **tripwire**: recorded in
   `LiveEvalReport.tripwires`, surfaced prominently as
   `[TRIPWIRE] <case> now passes — remove deferred=True`, and it makes `main`
   exit nonzero. The model improved; the marker is now lying and must be
   removed (which moves the case back into the normal pass/fail population).

The honesty guard (`test_deferred_cases_have_unsupported_unclassified_intent`)
asserts one direction only: every `deferred=True` case has an
`expected.intent` that is unsupported and not-yet-classified — not `None`, not
the supported `"summarize"`, and not the classified-but-unsupported `"rank"`.
The converse is intentionally not asserted: `rank` is unsupported but is
already correctly classified, so rank cases are legitimately *not* deferred.

The coverage guard is untouched: `expected.intent` is unchanged on every case,
so all deferred intents stay present and classified.

## Consequences

The deferred cases keep running on every live-eval pass, so the classifier
stays exercised and the failures snapshot stops carrying expected noise. A
green run now means "no regression on supported cases", and a real regression
is no longer buried. The day the model starts answering a deferred intent, the
tripwire fails the run loudly and tells us exactly which marker to delete —
turning model improvement into an action item instead of silence (the failure
mode `pytest.skip`/`xfail` would have introduced).

The tradeoff is a small amount of bespoke runner state (two extra report
buckets and one branch) instead of leaning on a standard test framework
mechanism. That cost buys the suppress-but-still-surface behavior the standard
mechanisms cannot give a manual runner, and it composes with the existing
streamed-failures contract (ADR-0008's trust boundary and ADR-0011's explicit
time scope are unaffected — only which cases reach the snapshot changes).
