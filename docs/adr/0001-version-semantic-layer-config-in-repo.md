# Version Semantic Layer Config in Repo

For v1, Semantic Layer definitions will live as versioned configuration in this
repo, such as `semantic_layer/datasets/*.yaml`, rather than in a database UI or
external semantic service. This keeps dataset definitions, metrics, joins,
permissions, freshness metadata, and example questions reviewable with the
application code while leaving room to move to dbt metadata or a dedicated
service later.
