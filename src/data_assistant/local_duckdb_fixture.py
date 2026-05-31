"""Shared local DuckDB fixture for the demo app, tests, and dev runtime.

It is not a production data-loading layer: callers declare the tables and rows
they want, and this fixture only creates the local schema, inserts those rows,
and closes the in-memory connection after use.
"""

from __future__ import annotations

import collections.abc
import contextlib
import dataclasses

import duckdb

OrderRow = tuple[str, str | None, str | None]


@dataclasses.dataclass(frozen=True)
class TableSpec:
    """A table to create in the fixture: name, ordered typed columns, and rows.

    Each column is a `(name, duckdb_type)` pair. Rows are bound positionally to
    those columns, so `None` is allowed wherever the column type is nullable.
    """

    name: str
    columns: tuple[tuple[str, str], ...]
    rows: collections.abc.Iterable[tuple[object, ...]]


TablesConnector = collections.abc.Callable[
    [collections.abc.Iterable[TableSpec]],
    contextlib.AbstractContextManager[duckdb.DuckDBPyConnection],
]
OrdersConnector = collections.abc.Callable[
    [collections.abc.Iterable[OrderRow]],
    contextlib.AbstractContextManager[duckdb.DuckDBPyConnection],
]

ORDERS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("order_date", "date"),
    ("region", "varchar"),
    ("revenue", "decimal(12, 2)"),
)


@contextlib.contextmanager
def connect_tables(
    table_specs: collections.abc.Iterable[TableSpec],
) -> collections.abc.Generator[duckdb.DuckDBPyConnection]:
    """Yield an in-memory DuckDB connection seeded from `table_specs`.

    Each spec's table is created with its declared columns and types, then its
    rows are inserted positionally. The connection is closed on exit.
    """
    connection = duckdb.connect(":memory:")
    for spec in table_specs:
        column_definitions = ", ".join(
            f"{name} {column_type}" for name, column_type in spec.columns
        )
        connection.execute(f"create table {spec.name} ({column_definitions})")
        rows = list(spec.rows)
        if rows:
            placeholders = ", ".join("?" for _ in spec.columns)
            connection.executemany(
                f"insert into {spec.name} values ({placeholders})",
                rows,
            )
    try:
        yield connection
    finally:
        connection.close()


def orders_table_spec(rows: collections.abc.Iterable[OrderRow]) -> TableSpec:
    """Return the orders table-spec: the demo commerce schema plus `rows`."""
    return TableSpec(name="orders", columns=ORDERS_COLUMNS, rows=rows)


def connect_orders(
    rows: collections.abc.Iterable[OrderRow],
) -> contextlib.AbstractContextManager[duckdb.DuckDBPyConnection]:
    """Yield an in-memory DuckDB connection containing one `orders` table.

    Each row is bound into `(order_date, region, revenue)` columns whose DuckDB
    types are `date`, `varchar`, and `decimal(12, 2)`. `None` values are allowed
    where `OrderRow` permits them so tests can model incomplete local data.
    """
    return connect_tables((orders_table_spec(rows),))
