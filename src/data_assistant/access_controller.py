"""Dataset-level access control for the Data Assistant."""

from __future__ import annotations

import data_assistant.non_answer_catalog as non_answer_catalog
import data_assistant.workflow.contracts as contracts

DEFAULT_LOCAL_ALLOWED_IDENTITY = contracts.InternalIdentity(
    identity_id="local_development_user",
)


def authorize_dataset_access(
    dataset_selection: contracts.DatasetSelection,
    internal_identity: contracts.InternalIdentity,
) -> contracts.StageResult[contracts.DatasetSelection]:
    """Allow or deny access to the selected Curated Dataset set."""
    for dataset in dataset_selection.selected_datasets:
        allowed_identity_ids = dataset.dataset_access.allowed_identity_ids
        if internal_identity.identity_id not in allowed_identity_ids:
            return non_answer_catalog.access_denied_non_answer(
                dataset.dataset_id,
                stage=contracts.NonAnswerStage.ACCESS_CONTROLLER,
            )

    return contracts.Success(dataset_selection)
