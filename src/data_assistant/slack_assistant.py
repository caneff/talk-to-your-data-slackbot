"""Slack Assistant surface adapter for the Data Assistant.

This module is the thin Slack edge between Slack's Bolt ``Assistant`` container
and the core Data Assistant workflow (interpret -> route -> authorize -> prepare
-> reason -> compose). It replaces the classic-bot DM boundary (see ADR-0015).

The adapter is split in two:

* ``AssistantAdapter`` -- a frozen, pure dataclass with two handler methods
  (``on_thread_started``, ``on_user_message``). It receives Slack's transient
  utilities (``say``, ``set_status``, ``set_suggested_prompts``) as injected
  callables, so it is fully testable with fakes and never touches a live API.
* ``register_assistant_handlers`` -- a thin Bolt wiring shim that builds a Bolt
  ``Assistant``, registers two listeners that forward to the adapter, and mounts
  it on the app via ``app.use(assistant)``. The shim is intentionally untested:
  the adapter carries the behavior.

The interpret->compose pipeline, its evals, and the Non-Answer path are
UNCHANGED -- divergence is contained to this Slack edge.
"""

from __future__ import annotations

import collections.abc as collections_abc
import contextlib
import dataclasses
import logging
import typing

import duckdb

import data_assistant.access_controller as access_controller
import data_assistant.workflow.contracts as contracts

logger = logging.getLogger(__name__)

GREETING = (
    "Hi! I answer questions about the retail operations data — orders, products, "
    "customers, stores, support, inventory. Pick a prompt below or ask your own. "
    "I'll only answer what the data supports."
)

# Provisional — rehearsed set locked in #101. Delivered dynamically via
# set_suggested_prompts (NOT manifest static). All three are summarize-intent and
# answerable today; deliberately no top-N "which ... highest" (that is #102).
SUGGESTED_PROMPTS: tuple[dict[str, str], ...] = (
    {
        "title": "Revenue by region",
        "message": "What was total net revenue by store region in Q1 2026?",
    },
    {
        "title": "Customers by loyalty tier",
        "message": "What was customer count by loyalty tier for all time?",
    },
    {
        "title": "Tickets by issue category",
        "message": "What was support ticket count by issue category in April 2026?",
    },
)

RUNTIME_FALLBACK_MESSAGE = (
    "Something went wrong while answering your question. Please try again in a bit."
)
"""Adapter-level last-resort reply posted when an unexpected exception crashes
the answer path. This is a Runtime Fallback Message, NOT a Non-Answer Response:
it never routes through the Non-Answer Catalog and carries no reason or next
step. The Assistant transient status auto-clears when this reply is sent, so no
manual status clear is needed."""


SlackWorkflowResult: typing.TypeAlias = contracts.WorkflowResult

AnswerPath: typing.TypeAlias = collections_abc.Callable[
    [
        duckdb.DuckDBPyConnection,
        str,
        contracts.InternalIdentity,
        contracts.ProgressSink,
    ],
    SlackWorkflowResult,
]

ConnectionFactory: typing.TypeAlias = collections_abc.Callable[
    [], contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]
]

AssistantIdentityResolver: typing.TypeAlias = collections_abc.Callable[
    [str], contracts.InternalIdentity
]


class StatusSetter(typing.Protocol):
    """Injected Slack ``set_status`` callable (transient assistant status)."""

    def __call__(self, status: str) -> None:
        """Set the transient assistant status for the current thread."""


class Sayer(typing.Protocol):
    """Injected Slack ``say`` callable (posts a threaded assistant reply)."""

    def __call__(
        self,
        text: str,
        *,
        blocks: collections_abc.Sequence[contracts.SlackBlock] | None = None,
    ) -> None:
        """Post a reply into the assistant thread."""


class SuggestedPromptsSetter(typing.Protocol):
    """Injected Slack ``set_suggested_prompts`` callable."""

    def __call__(self, *, prompts: list[dict[str, str]]) -> None:
        """Offer suggested prompts in the assistant thread."""


def default_identity(user: str) -> contracts.InternalIdentity:
    """Map a Slack user id into the workflow contract without org policy."""
    return contracts.InternalIdentity(identity_id=f"slack_user:{user}")


def dev_identity(user: str) -> contracts.InternalIdentity:
    """Use the local allowed identity for manual development smoke testing."""
    del user
    return access_controller.DEFAULT_LOCAL_ALLOWED_IDENTITY


def final_response_from_workflow_result(
    result: SlackWorkflowResult,
) -> contracts.FinalResponse:
    """Return the core workflow result's user-facing Final Response.

    Renders both real answers and Non-Answers to a ``FinalResponse`` (text +
    Trust-Summary blocks); the adapter just ``say``s whatever this returns.
    """
    if isinstance(result, contracts.FinalResponse):
        return result
    return result.final_response


@dataclasses.dataclass(frozen=True)
class AssistantAdapter:
    """Pure adapter from Slack Assistant events to the Data Assistant workflow."""

    connection_factory: ConnectionFactory
    answer_path: AnswerPath
    internal_identity_resolver: AssistantIdentityResolver = default_identity

    def on_thread_started(
        self,
        *,
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
    ) -> None:
        """Greet the user and offer the provisional suggested prompts."""
        say(GREETING)
        set_suggested_prompts(prompts=[dict(prompt) for prompt in SUGGESTED_PROMPTS])

    def on_user_message(
        self,
        *,
        text: str,
        user: str,
        channel: str,
        thread_ts: str,
        set_status: StatusSetter,
        say: Sayer,
    ) -> None:
        """Run the pipeline for one user message and reply in the thread.

        ``channel`` and ``thread_ts`` are used only for the maintainer log line;
        ``say`` and ``set_status`` are already bound to the thread by Bolt. The
        transient status auto-clears when ``say`` posts the reply (both the
        success and the fallback path), so there is no manual status clear.
        """
        internal_identity = self.internal_identity_resolver(user)
        try:
            with self.connection_factory() as connection:
                result = self.answer_path(
                    connection,
                    text,
                    internal_identity,
                    set_status,
                )
            final_response = final_response_from_workflow_result(result)
            say(final_response.text, blocks=final_response.blocks or None)
        except Exception as error:
            # Bootcamp deviation: we also log the raw question text (`text`).
            # A real production Slack bot would NOT log the question text because
            # it is user-provided free text that may contain sensitive or
            # business values (see CONTEXT.md: "Log the Decision Trail, not raw
            # Prepared Data or sensitive values"). The stack trace stays in logs
            # only and never reaches the Slack user.
            logger.exception(
                "Slack Assistant Adapter failed to answer "
                "(channel=%s thread_ts=%s user=%s exception_type=%s question=%s)",
                channel,
                thread_ts,
                user,
                type(error).__name__,
                text,
            )
            # Log first, then deliver the Runtime Fallback Message. If this `say`
            # itself raises we let it propagate: the maintainer log already
            # exists. The fallback is NOT a Non-Answer.
            say(RUNTIME_FALLBACK_MESSAGE)


def register_assistant_handlers(
    *,
    app: typing.Any,
    adapter: AssistantAdapter,
) -> None:
    """Wire the adapter into a Bolt ``Assistant`` container (thin shim).

    This is the only live-API-shaped code in the module and is intentionally
    untested: it forwards Bolt's injected utilities to the pure adapter. Bolt
    injects listener arguments by exact name (verified against slack_bolt
    1.28.0): ``say``, ``set_status``, ``set_suggested_prompts``, ``context``.
    ``context.user_id`` / ``context.channel_id`` / ``context.thread_ts`` carry
    the routing identifiers.
    """
    from slack_bolt import Assistant

    # Typed as Any: Bolt's decorator signatures are loosely typed and would
    # otherwise leak "partially unknown" through this shim.
    assistant: typing.Any = Assistant()

    def _thread_started(
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
    ) -> None:
        adapter.on_thread_started(
            say=say,
            set_suggested_prompts=set_suggested_prompts,
        )

    def _user_message(
        payload: dict[str, typing.Any],
        context: typing.Any,
        set_status: StatusSetter,
        say: Sayer,
    ) -> None:
        adapter.on_user_message(
            text=payload.get("text", ""),
            user=context.user_id or "",
            channel=context.channel_id or "",
            thread_ts=context.thread_ts or "",
            set_status=set_status,
            say=say,
        )

    # Bolt injects listener arguments by exact name (verified against slack_bolt
    # 1.28.0 kwargs injection): thread_started gets `say`/`set_suggested_prompts`;
    # user_message gets `payload`/`context`/`set_status`/`say`.
    assistant.thread_started(_thread_started)
    assistant.user_message(_user_message)

    # assistant_thread_context_changed is intentionally NOT handled: we rely on
    # Bolt's default in-memory thread-context store. This is deliberate, not an
    # oversight.

    app.use(assistant)
