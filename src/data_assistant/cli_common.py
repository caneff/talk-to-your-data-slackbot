"""Shared argparse plumbing for the Slack entrypoints.

Both Slack entrypoints accept the same data-source flags (``--env-file``,
``--semantic-layer-path``, ``--duckdb-path``, ``--seed-sql-path``), enforce the
same seed-requires-duckdb guard, and build their connection factory from those
args the same way. This module owns that plumbing. It depends one-directionally
on ``composition`` (for the retail constants + the connection-factory builder);
``composition`` never imports back.

Flat layout for now -- this moves into ``slack/`` in a later issue (I5).
"""

from __future__ import annotations

import argparse
import pathlib

import data_assistant.composition as composition


def add_data_source_args(parser: argparse.ArgumentParser) -> None:
    """Add the data-source arg group both Slack entrypoints share.

    ``--semantic-layer-path`` defaults to the retail app-run layer for both
    entrypoints. A no-flag run loads retail either way, so there is no
    behavioral difference to parameterize.
    """
    parser.add_argument(
        "--env-file",
        type=pathlib.Path,
        default=None,
        help="dotenv file to load before startup. Defaults to .env.",
    )
    parser.add_argument(
        "--semantic-layer-path",
        type=pathlib.Path,
        default=composition.RETAIL_SEMANTIC_LAYER_PATH,
        help=(
            "Semantic Layer directory to load. Defaults to the retail app-run "
            "layer (examples/retail_ops_demo/semantic_layer/)."
        ),
    )
    parser.add_argument(
        "--duckdb-path",
        type=str,
        default=None,
        help=(
            "DuckDB database location. Defaults to an in-memory database seeded "
            "with the retail demo data."
        ),
    )
    parser.add_argument(
        "--seed-sql-path",
        type=pathlib.Path,
        default=None,
        help=(
            "SQL file to run whenever the DuckDB connection opens. Defaults to "
            "the retail demo seed (only when --duckdb-path is also unset)."
        ),
    )


def enforce_seed_requires_duckdb(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    """Reject ``--seed-sql-path`` unless ``--duckdb-path`` is also given."""
    if args.seed_sql_path is not None and args.duckdb_path is None:
        parser.error("--seed-sql-path requires --duckdb-path")


def connection_factory_from_args(
    args: argparse.Namespace,
) -> composition.ConnectionFactory:
    """Build the connection factory from parsed data-source args.

    No flags: build the retail app-run default (retail seed in :memory:),
    consuming the shared retail path constants so there is exactly one source of
    truth. An explicit ``--duckdb-path`` opts out of the retail seed unless
    ``--seed-sql-path`` is also given (the seed-requires-duckdb guard enforces
    that pairing).
    """
    if args.duckdb_path is None:
        return composition.build_duckdb_connection_factory(
            composition.RETAIL_DUCKDB_PATH,
            seed_sql_path=composition.RETAIL_SEED_SQL_PATH,
        )
    return composition.build_duckdb_connection_factory(
        args.duckdb_path,
        seed_sql_path=args.seed_sql_path,
    )
