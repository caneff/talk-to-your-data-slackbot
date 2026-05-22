# Split Semantic Layer Dataset and Table Config

Semantic Layer config will split **Curated Dataset** definitions from **Dataset
Table** definitions. Dataset YAML files describe dataset identity, table
membership, general information types, freshness context, and example questions;
table YAML files describe physical columns plus table-level metrics and
dimensions. MVP retrieval may use a local DuckDB instance for tests and
development, but DuckDB stores data for retrieval, not Semantic Layer
definitions.
