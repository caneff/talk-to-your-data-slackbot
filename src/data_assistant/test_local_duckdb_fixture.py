from __future__ import annotations

import data_assistant.local_duckdb_fixture as local_duckdb_fixture


def test_connect_tables_builds_arbitrary_non_orders_tables() -> None:
    inventory = local_duckdb_fixture.TableSpec(
        name="inventory",
        columns=(
            ("sku", "varchar"),
            ("quantity", "integer"),
        ),
        rows=(
            ("A-1", 5),
            ("B-2", 0),
        ),
    )
    employees = local_duckdb_fixture.TableSpec(
        name="employees",
        columns=(("name", "varchar"),),
        rows=(("Ada",),),
    )

    with local_duckdb_fixture.connect_tables((inventory, employees)) as connection:
        inventory_rows = connection.execute(
            "select sku, quantity from inventory order by sku"
        ).fetchall()
        employee_rows = connection.execute("select name from employees").fetchall()

    assert inventory_rows == [("A-1", 5), ("B-2", 0)]
    assert employee_rows == [("Ada",)]


def test_connect_orders_builds_orders_table_with_typed_schema() -> None:
    rows = (
        ("2026-01-03", "North", "1200.00"),
        ("2026-01-20", None, "500.00"),
    )

    with local_duckdb_fixture.connect_orders(rows) as connection:
        fetched = connection.execute(
            "select region, revenue from orders order by order_date"
        ).fetchall()

    assert fetched[0][0] == "North"
    assert fetched[1][0] is None
