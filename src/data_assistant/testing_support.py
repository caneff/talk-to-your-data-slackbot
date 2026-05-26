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
