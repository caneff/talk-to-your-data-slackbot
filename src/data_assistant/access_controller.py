"""Dataset-level access control for the Data Assistant."""

from __future__ import annotations

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
            return contracts.NonAnswer(
                stage="access_controller",
                reason=(
                    "You do not have access to the "
                    f"{dataset.dataset_id} Curated Dataset."
                ),
                unresolved_ambiguities=(),
                next_step=(
                    "Ask a data owner to grant Dataset Access or ask about "
                    "available data."
                ),
                datasets=(dataset.dataset_id,),
            )

    return contracts.Success(dataset_selection)
