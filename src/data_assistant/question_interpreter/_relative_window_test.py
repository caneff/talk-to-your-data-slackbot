"""Pin the ADR-0024 relative-window convention in code (ADR-0025).

The interpreter — not the model — computes the calendar window from
`as_of_date`. Every row of the ADR-0024 pinned table is asserted here against
`as_of_date = 2026-06-30`, the last day of June AND of Q2, so both the
in-progress month and the in-progress quarter are excluded.
"""

from __future__ import annotations

import datetime

import pytest

import data_assistant.question_interpreter._relative_window as relative_window

_AS_OF = datetime.date(2026, 6, 30)


@pytest.mark.parametrize(
    ("unit", "count", "lower", "upper"),
    [
        ("day", 1, datetime.date(2026, 6, 29), datetime.date(2026, 6, 29)),
        ("day", 7, datetime.date(2026, 6, 23), datetime.date(2026, 6, 29)),
        ("day", 30, datetime.date(2026, 5, 31), datetime.date(2026, 6, 29)),
        ("month", 1, datetime.date(2026, 5, 1), datetime.date(2026, 5, 31)),
        ("month", 2, datetime.date(2026, 4, 1), datetime.date(2026, 5, 31)),
        ("quarter", 1, datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)),
        ("quarter", 3, datetime.date(2025, 7, 1), datetime.date(2026, 3, 31)),
    ],
)
def test_compute_relative_window_pins_adr_0024_rows(
    unit: relative_window.RelativeUnit,
    count: int,
    lower: datetime.date,
    upper: datetime.date,
) -> None:
    assert relative_window.compute_relative_window(
        as_of_date=_AS_OF,
        unit=unit,
        count=count,
    ) == (lower, upper)


def test_month_window_crosses_a_year_boundary() -> None:
    # as_of in January: "last two months" reaches back into the prior year.
    assert relative_window.compute_relative_window(
        as_of_date=datetime.date(2026, 1, 15),
        unit="month",
        count=2,
    ) == (datetime.date(2025, 11, 1), datetime.date(2025, 12, 31))


def test_quarter_window_crosses_a_year_boundary() -> None:
    # as_of in Q1: "last quarter" is Q4 of the prior year.
    assert relative_window.compute_relative_window(
        as_of_date=datetime.date(2026, 2, 10),
        unit="quarter",
        count=1,
    ) == (datetime.date(2025, 10, 1), datetime.date(2025, 12, 31))


def test_count_must_be_positive() -> None:
    with pytest.raises(ValueError):
        relative_window.compute_relative_window(
            as_of_date=_AS_OF,
            unit="day",
            count=0,
        )
