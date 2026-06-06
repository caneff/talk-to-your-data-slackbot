"""Bolt live-API wiring shims (intentionally untested).

This is the only live-API-shaped code in the package: it builds a Bolt
``Assistant`` container and the ``block_actions`` / ``view`` listeners, forwards
Bolt's injected utilities to the pure adapter and the pure cores in
``payloads``, then performs the effect. Each closure is thin -- ack -> parse
(``payloads``) -> pure core -> effect -- and is NOT a generic dispatch table:
Bolt injects ``say`` / ``respond`` / ``client`` / ``context`` by EXACT parameter
name, so the listener parameter names are load-bearing and preserved verbatim.
Nothing imports this module.
"""

from __future__ import annotations

import collections.abc as collections_abc
import typing

import data_assistant.interaction_log as interaction_log
from data_assistant.slack.adapter import (
    AssistantAdapter,
    Sayer,
    StatusSetter,
    SuggestedPromptsSetter,
)
from data_assistant.slack.payloads import (
    action_target,
    apply_flag,
    apply_qa_done,
    apply_qa_review_note_save,
    build_qa_review_note_modal,
    message_blocks,
    qa_done_target,
    render_note_saved_blocks,
    str_at,
)
from data_assistant.slack.prompts import (
    ACTION_ID_TO_CATEGORY,
    QA_ADD_NOTE_ACTION_ID,
    QA_DONE_ACTION_ID,
    QA_REVIEW_NOTE_CALLBACK_ID,
    toggle_interaction_flag_for_triage,
)


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
    the routing identifiers. ``thread_started`` also takes ``context`` so the
    adapter can record the (channel, thread_ts) pointer the QA driver reads.
    """
    from slack_bolt import Assistant

    # Typed as Any: Bolt's decorator signatures are loosely typed and would
    # otherwise leak "partially unknown" through this shim.
    assistant: typing.Any = Assistant()

    def _thread_started(
        context: typing.Any,
        say: Sayer,
        set_suggested_prompts: SuggestedPromptsSetter,
    ) -> None:
        adapter.on_thread_started(
            say=say,
            set_suggested_prompts=set_suggested_prompts,
            channel=context.channel_id or "",
            thread_ts=context.thread_ts or "",
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

    _register_message_actions(app=app, adapter=adapter)


def _register_message_actions(
    *,
    app: typing.Any,
    adapter: AssistantAdapter,
) -> None:
    """Wire the flag buttons' ``block_actions`` listeners (thin untested shim).

    For each flag ``action_id`` we register a Bolt action listener that, over
    Socket Mode: ``ack()``s first, reads the embedded ``interaction_id`` from
    the button ``value`` and the clicked message's ``blocks`` from ``body``,
    binds the ``flag_store`` seam to the log-backed toggle helper, then
    delegates to the pure ``apply_flag`` for the re-rendered blocks. All
    behavior lives in ``apply_flag``; this shim is the only live-API-shaped
    code here and is intentionally untested.

    Bolt's ``respond`` is bound to the action's ``response_url``; calling
    ``respond(blocks=..., replace_original=True)`` RE-RENDERS the same Assistant
    reply in place so the answer + buttons stay while button state updates.
    ``replace_original=True`` is deliberate: the Assistant surface does NOT show
    ``response_url`` ephemerals inline (they leak into the History pane as
    unread items), so editing the message is the only non-spammy way to confirm.
    Verified against the ``slack_bolt`` 1.28.0 ``Respond.__call__`` signature
    (``blocks`` / ``replace_original`` keywords).
    """

    def _flag_action(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        respond: typing.Any,
    ) -> None:
        ack()
        action_id, interaction_id = action_target(body)

        def flag_store(
            target_id: str,
            category: str,
        ) -> interaction_log.ToggleFlagResult:
            return toggle_interaction_flag_for_triage(
                interaction_id=target_id,
                category=category,
                log_path=adapter.log_path,
            )

        new_blocks = apply_flag(
            action_id=action_id,
            interaction_id=interaction_id,
            blocks=message_blocks(body),
            flag_store=flag_store,
        )
        if new_blocks is None:
            return
        # replace_original=True RE-RENDERS the same Assistant reply in place so
        # the answer + buttons stay while the selected button state updates. The
        # Assistant surface does not show response_url ephemerals inline (they
        # leak into the History pane as unread items), so editing the message is
        # the only way to confirm without spamming a separate notification.
        respond(blocks=new_blocks, replace_original=True)

    # Register one listener per flag action_id (the single source of truth).
    for flag_action_id in ACTION_ID_TO_CATEGORY:
        app.action(flag_action_id)(_flag_action)

    def _qa_done_action(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        client: typing.Any,
    ) -> None:
        ack()
        apply_qa_done(
            body=body,
            delete_message=lambda channel, ts: client.chat_delete(
                channel=channel,
                ts=ts,
            ),
        )

    app.action(QA_DONE_ACTION_ID)(_qa_done_action)

    def _qa_add_note_action(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        client: typing.Any,
    ) -> None:
        ack()
        _, interaction_id = action_target(body)
        trigger_id = str_at(body, "trigger_id")
        if not interaction_id or not trigger_id:
            return
        record = interaction_log.find_interaction(interaction_id, path=adapter.log_path)
        existing_note = ""
        if record is not None:
            note_value = record.get("qa_review_note")
            if isinstance(note_value, str):
                existing_note = note_value
        channel_id, message_ts = qa_done_target(body)
        client.views_open(
            trigger_id=trigger_id,
            view=build_qa_review_note_modal(
                interaction_id=interaction_id,
                existing_note=existing_note,
                channel_id=channel_id,
                message_ts=message_ts,
                message_text=str_at(body, "message", "text"),
            ),
        )

    app.action(QA_ADD_NOTE_ACTION_ID)(_qa_add_note_action)

    def _qa_review_note_submit(
        ack: collections_abc.Callable[[], None],
        body: dict[str, typing.Any],
        client: typing.Any,
    ) -> None:
        ack()
        result = apply_qa_review_note_save(
            body=body,
            note_store=lambda interaction_id, note: interaction_log.save_qa_review_note(
                interaction_id,
                note,
                path=adapter.log_path,
            ),
        )
        if result is None:
            return
        channel_id = typing.cast("str | None", result.get("channel_id"))
        message_ts = typing.cast("str | None", result.get("message_ts"))
        if not channel_id or not message_ts:
            return
        history = client.conversations_history(
            channel=channel_id,
            latest=message_ts,
            oldest=message_ts,
            inclusive=True,
            limit=1,
        )
        messages = history.get("messages")
        if not isinstance(messages, list) or not messages:
            return
        first_message = typing.cast("list[object]", messages)[0]
        if not isinstance(first_message, dict):
            return
        message = typing.cast("dict[str, object]", first_message)
        raw_blocks = message.get("blocks")
        blocks = render_note_saved_blocks(raw_blocks)
        kwargs: dict[str, object] = {
            "channel": channel_id,
            "ts": message_ts,
            "blocks": blocks,
        }
        message_text = result.get("message_text")
        if isinstance(message_text, str) and message_text:
            kwargs["text"] = message_text
        client.chat_update(**kwargs)

    app.view(QA_REVIEW_NOTE_CALLBACK_ID)(_qa_review_note_submit)
