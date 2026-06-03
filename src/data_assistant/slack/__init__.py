"""Slack Assistant surface package facade.

Thin re-export facade (ADR-0009, mirroring ``question_interpreter/__init__.py``)
exposing ONLY the public surface external callers consume. Internal helpers
(leading underscore) and test-only names stay private to their submodules; tests
import the real submodules directly.

The Slack edge is split one job per module:

* ``prompts``  -- strings, action-id vocabulary, triage-flag mirror.
* ``blocks``   -- pure Block-Kit *constructors*.
* ``payloads`` -- inbound-payload extraction, pure cores, block *readers*
  (one-way ``payloads -> blocks``; ``blocks`` never imports ``payloads``).
* ``adapter``  -- the pure ``AssistantAdapter`` + its contracts.
* ``wiring``   -- the Bolt live-API shims (nothing imports ``wiring``).
"""

from data_assistant.interaction_record import RUNTIME_FALLBACK_MESSAGE
from data_assistant.slack.adapter import (
    AnswerPath,
    AssistantAdapter,
    AssistantIdentityResolver,
    ConnectionFactory,
    SlackWorkflowResult,
    StatusSetter,
    default_identity,
    dev_identity,
)
from data_assistant.slack.blocks import build_runtime_fallback_blocks
from data_assistant.slack.wiring import register_assistant_handlers

__all__ = [
    "RUNTIME_FALLBACK_MESSAGE",
    "AnswerPath",
    "AssistantAdapter",
    "AssistantIdentityResolver",
    "ConnectionFactory",
    "SlackWorkflowResult",
    "StatusSetter",
    "build_runtime_fallback_blocks",
    "default_identity",
    "dev_identity",
    "register_assistant_handlers",
]
