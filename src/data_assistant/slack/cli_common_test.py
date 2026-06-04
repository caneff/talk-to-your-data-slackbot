"""Tests for the shared CLI helpers both Slack entrypoints reuse.

``cli_common`` owns the argparse plumbing duplicated across the Socket Mode
entrypoint and the QA driver: the shared data-source arg group, the
seed-requires-duckdb guard, and the connection-factory-from-args builder. It
depends one-directionally on ``composition`` (never the reverse).
"""

from __future__ import annotations

import argparse
import pathlib

import pytest

import data_assistant.slack.cli_common as cli_common
import data_assistant.slack.composition as composition


def _parser_with_data_source_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    cli_common.add_data_source_args(parser)
    return parser


def test_add_data_source_args_defaults_to_retail_semantic_layer() -> None:
    """Both entrypoints default --semantic-layer-path to the retail layer."""
    parser = _parser_with_data_source_args()

    args = parser.parse_args([])

    assert args.env_file is None
    assert args.semantic_layer_path == composition.RETAIL_SEMANTIC_LAYER_PATH
    assert args.duckdb_path is None
    assert args.seed_sql_path is None


def test_add_data_source_args_parses_explicit_values(
    tmp_path: pathlib.Path,
) -> None:
    parser = _parser_with_data_source_args()
    seed = tmp_path / "seed.sql"

    args = parser.parse_args(
        [
            "--env-file",
            ".env.test",
            "--semantic-layer-path",
            str(tmp_path / "layer"),
            "--duckdb-path",
            ":memory:",
            "--seed-sql-path",
            str(seed),
        ]
    )

    assert args.env_file == pathlib.Path(".env.test")
    assert args.semantic_layer_path == tmp_path / "layer"
    assert args.duckdb_path == ":memory:"
    assert args.seed_sql_path == seed


def test_enforce_seed_requires_duckdb_rejects_seed_without_duckdb() -> None:
    parser = _parser_with_data_source_args()
    args = parser.parse_args(["--seed-sql-path", "seed.sql"])

    with pytest.raises(SystemExit):
        cli_common.enforce_seed_requires_duckdb(parser, args)


def test_enforce_seed_requires_duckdb_allows_seed_with_duckdb() -> None:
    parser = _parser_with_data_source_args()
    args = parser.parse_args(
        ["--duckdb-path", ":memory:", "--seed-sql-path", "seed.sql"]
    )

    # No raise: the guard is satisfied when --duckdb-path accompanies the seed.
    cli_common.enforce_seed_requires_duckdb(parser, args)


def test_connection_factory_from_args_no_flags_builds_retail_default() -> None:
    """No flags wires the retail seed into :memory: (app-run default)."""
    parser = _parser_with_data_source_args()
    args = parser.parse_args([])

    connection_factory = cli_common.connection_factory_from_args(args)

    with connection_factory() as connection:
        row = connection.execute("select count(*) from demo_orders").fetchone()

    assert row is not None
    assert row[0] > 0


def test_connection_factory_from_args_explicit_duckdb_opts_out_of_seed(
    tmp_path: pathlib.Path,
) -> None:
    """An explicit --duckdb-path with its own seed opts out of the retail seed."""
    parser = _parser_with_data_source_args()
    seed = tmp_path / "seed.sql"
    seed.write_text(
        "create table demo_value (value integer); insert into demo_value values (7);",
        encoding="utf-8",
    )
    args = parser.parse_args(
        ["--duckdb-path", ":memory:", "--seed-sql-path", str(seed)]
    )

    connection_factory = cli_common.connection_factory_from_args(args)

    with connection_factory() as connection:
        row = connection.execute("select value from demo_value").fetchone()

    assert row == (7,)
