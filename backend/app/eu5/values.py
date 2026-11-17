"""Value conversions for the EU5 binary format."""
from __future__ import annotations

HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365  # Paradox calendar: no leap years
YEAR_OFFSET = 5000  # i32 dates count hours since -5000.1.1
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# i32 values in this range (years 0..2000) are treated as dates.
DATE_MIN = YEAR_OFFSET * DAYS_PER_YEAR * HOURS_PER_DAY
DATE_MAX = (YEAR_OFFSET + 2000) * DAYS_PER_YEAR * HOURS_PER_DAY
# Keys that hold i32 values that sometimes fall in the date range but are not dates.
NOT_DATE_KEYS = frozenset({"random", "seed", "random_seed", "random_count", "enable"})

FIXED5_SCALE = 100_000


def format_date(hours: int) -> str:
    days, hour = divmod(hours, HOURS_PER_DAY)
    years, day_of_year = divmod(days, DAYS_PER_YEAR)
    month = 0
    while day_of_year >= _MONTH_DAYS[month]:
        day_of_year -= _MONTH_DAYS[month]
        month += 1
    text = f"{years - YEAR_OFFSET}.{month + 1}.{day_of_year + 1}"
    return f"{text}.{hour}" if hour else text


def looks_like_date(key: str | None, value: int) -> bool:
    return DATE_MIN <= value <= DATE_MAX and key not in NOT_DATE_KEYS
