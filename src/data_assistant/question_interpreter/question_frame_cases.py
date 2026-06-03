"""Compatibility wrapper for old Question Frame case imports.

Use `data_assistant.question_interpreter.provider_proposal_cases` for new code.
"""

from data_assistant.question_interpreter.provider_proposal_cases import (
    SHARED_PROVIDER_PROPOSAL_CASES,
    SHARED_QUESTION_FRAME_CASES,
    SharedProviderProposalCase,
    SharedQuestionFrameCase,
)

__all__ = [
    "SHARED_PROVIDER_PROPOSAL_CASES",
    "SHARED_QUESTION_FRAME_CASES",
    "SharedProviderProposalCase",
    "SharedQuestionFrameCase",
]
