"""Shared local DuckDB fixture for the demo app, tests, and dev runtime.

It is not a production data-loading layer: callers provide the rows they want, and this
fixture only creates the local schema, inserts those rows, and closes the in-memory
connection after use.
"""

from __future__ import annotations

import collections.abc
import contextlib

import duckdb

OrderRow = tuple[str, str | None, str | None]
OrdersConnector = collections.abc.Callable[
    [collections.abc.Iterable[OrderRow]],
    contextlib.AbstractContextManager[duckdb.DuckDBPyConnection],
]


@contextlib.contextmanager
def connect_orders(
    rows: collections.abc.Iterable[OrderRow],
) -> collections.abc.Generator[duckdb.DuckDBPyConnection]:
    """Yield an in-memory DuckDB connection containing one `orders` table.

    Each row is bound into `(order_date, region, revenue)` columns whose DuckDB
    types are `date`, `varchar`, and `decimal(12, 2)`. `None` values are allowed
    where `OrderRow` permits them so tests can model incomplete local data.
    """
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        create table orders (
            order_date date,
            region varchar,
            revenue decimal(12, 2)
        )
        """,
    )
    connection.executemany("insert into orders values (?, ?, ?)", rows)
    try:
        yield connection
    finally:
        connection.close()
