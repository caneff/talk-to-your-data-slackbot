"""Deterministic relative-window computation (ADR-0025 enforces ADR-0024).

The model classifies an `as_of`-anchored relative phrase into `{unit, count}`;
this module computes the concrete `(lower, upper)` calendar window from
`as_of_date`. The ADR-0024 convention lives here, in code: a relative window
covers the most recent COMPLETE unit(s) and excludes the in-progress unit that
contains `as_of_date` (which is the notional today, an incomplete day). Stdlib
only — quarter math is done by hand.
"""

from __future__ import annotations

import calendar
import datetime
import typing

RelativeUnit = typing.Literal["day", "month", "quarter"]


def compute_relative_window(
    *,
    as_of_date: datetime.date,
    unit: RelativeUnit,
    count: int,
) -> tuple[datetime.date, datetime.date]:
    """Return the `(lower, upper)` window for a relative classification.

    Raises ValueError for a non-positive count.
    """
    if count < 1:
        raise ValueError("relative window count must be >= 1")
    if unit == "day":
        return _day_window(as_of_date, count)
    if unit == "month":
        return _month_window(as_of_date, count)
    return _quarter_window(as_of_date, count)


def _day_window(
    as_of_date: datetime.date,
    count: int,
) -> tuple[datetime.date, datetime.date]:
    upper = as_of_date - datetime.timedelta(days=1)
    lower = as_of_date - datetime.timedelta(days=count)
    return lower, upper


def _month_window(
    as_of_date: datetime.date,
    count: int,
) -> tuple[datetime.date, datetime.date]:
    # Most recent complete month is the one before as_of's month.
    upper_year, upper_month = _shift_month(as_of_date.year, as_of_date.month, -1)
    lower_year, lower_month = _shift_month(as_of_date.year, as_of_date.month, -count)
    upper = _last_day_of_month(upper_year, upper_month)
    lower = datetime.date(lower_year, lower_month, 1)
    return lower, upper


def _quarter_window(
    as_of_date: datetime.date,
    count: int,
) -> tuple[datetime.date, datetime.date]:
    # Quarter index 0..3 for the month containing as_of.
    current_quarter = (as_of_date.month - 1) // 3
    absolute_quarter = as_of_date.year * 4 + current_quarter
    # Most recent complete quarter is the one before as_of's quarter.
    upper_year, upper_quarter = divmod(absolute_quarter - 1, 4)
    lower_year, lower_quarter = divmod(absolute_quarter - count, 4)
    upper_last_month = upper_quarter * 3 + 3
    lower_first_month = lower_quarter * 3 + 1
    upper = _last_day_of_month(upper_year, upper_last_month)
    lower = datetime.date(lower_year, lower_first_month, 1)
    return lower, upper


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + delta
    shifted_year, shifted_month_index = divmod(absolute, 12)
    return shifted_year, shifted_month_index + 1


def _last_day_of_month(year: int, month: int) -> datetime.date:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, last_day)
