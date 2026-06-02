# Version Semantic Layer Config in Repo

For v1, Semantic Layer definitions will live as versioned configuration in this
repo (originally at `semantic_layer/datasets/*.yaml`; see Amendment below for the
current location), rather than in a database UI or
external semantic service. This keeps dataset definitions, metrics, joins,
permissions, freshness metadata, and example questions reviewable with the
application code while leaving room to move to dbt metadata or a dedicated
service later.

## Amendment (2026-06-02, #131)

The original decision stands: Semantic Layer config is versioned in this repo. The
config dir has moved from the repo root to `examples/commerce_smoke/semantic_layer/`.
Commerce is now framed as an *example* layer — not a privileged or production
config — living alongside other examples (e.g. `examples/retail_ops_demo/`). A
no-arg `load_semantic_layer()` default still exists for zero-config library and
test loads; it now resolves to the relocated path. A follow-up (#132) introduces a
two-tier default in which the app run loads the retail layer while library/test
loads keep the Commerce example.
