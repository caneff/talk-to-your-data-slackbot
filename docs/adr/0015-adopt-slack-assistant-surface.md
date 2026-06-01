# Adopt the Slack Assistant Surface

The **Slack Runtime Adapter** will target Slack's Assistant surface ("Agents &
AI Apps") rather than a plain bot DM: the app gains `assistant:write` and the
assistant view in its manifest, and the runtime moves from `app.event("message")`
to Bolt's `Assistant` container (`thread_started`, `user_message`). This is a
deliberate divergence from the classic-bot manifest the course provides and from
the earlier DM-only MVP scope.

## Considered Options

- **Stay a classic bot (course manifest).** On the paved path; status would be a
  posted-then-updated message and suggested prompts would be ad-hoc buttons via
  `interactivity`. Rejected for the demo: no native transient status, and the app
  presents as a chatbot rather than an assistant.
- **Adopt the Assistant surface (chosen).** Native transient `setStatus` that
  auto-clears on reply, `setSuggestedPrompts`, and a dedicated assistant pane —
  the surface purpose-built for "chat with your data." The project is an
  Assistant by Slack's own taxonomy (conversational, reactive, reasons over data,
  not autonomous), so this names the app what it already is.

## Consequences

- Diverges from the course's provided manifest; requires adding `assistant:write`,
  enabling the assistant view, and reinstalling the app.
- Rewires the Slack edge to the `Assistant` container and introduces a
  `thread_started` lifecycle (greeting + suggested prompts) with no analog in the
  prior request/response flow.
- The interpret → route → authorize → prepare → reason → compose pipeline, its
  evals, and the **Non-Answer Response** path are unaffected; the divergence is
  contained to the Slack edge.
- Reversing later means reinstalling under the classic-bot manifest and restoring
  the `message.im` handler.
