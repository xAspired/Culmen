"""Time handling.

Every timestamp inside Culmen is a timezone-aware UTC ``datetime``.
Naive datetimes are rejected at the boundary, never silently interpreted.

Earth rotation runs on UT1, not UTC; UTC also contains leap seconds, so it is
not a continuous scale and must never be used for arithmetic on intervals that
may span one. We delegate the scale bookkeeping (UTC -> TAI -> TT, and dUT1)
to Skyfield's Timescale.

By default the timescale is built from Skyfield's *bundled* leap-second table
(``builtin=True``), so the library works fully offline and deterministically.
That table is frozen at the Skyfield release date; since no leap second has
been announced beyond it, this is exact for present-day epochs. Skyfield's
built-in timescale approximates dUT1 by a polynomial/table fit, giving a
sub-second UT1 error which maps to well under 1 km of along-longitude error.
Declared in docs/math/assumptions.md, not hidden.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC as _UTC
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
from skyfield.api import load
from skyfield.timelib import Time, Timescale

#: Re-exported so callers get their UTC from one place.
UTC = _UTC


@lru_cache(maxsize=1)
def timescale() -> Timescale:
    """Process-wide Skyfield Timescale, built from bundled leap-second data."""
    return load.timescale(builtin=True)


def ensure_utc(dt: datetime) -> datetime:
    """Reject naive datetimes; normalise aware ones to UTC."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            "naive datetime rejected: Culmen requires timezone-aware UTC datetimes"
        )
    return dt.astimezone(UTC)


def to_time(dt: datetime) -> Time:
    """Aware datetime -> Skyfield Time."""
    return timescale().from_datetime(ensure_utc(dt))


def to_times(dts: list[datetime]) -> Time:
    """List of aware datetimes -> single vectorised Skyfield Time."""
    return timescale().from_datetimes([ensure_utc(d) for d in dts])


def from_time(t: Time) -> datetime:
    """Skyfield Time -> aware UTC datetime."""
    dt: datetime = t.utc_datetime()
    return dt.replace(tzinfo=UTC)


def time_range(start: datetime, end: datetime, step_s: float) -> Time:
    """Uniform vectorised Time grid over [start, end], inclusive of ``start``.

    The grid is built on the continuous TT Julian date, not by adding
    timedeltas to UTC, so a leap second inside the window cannot distort it.
    """
    start = ensure_utc(start)
    end = ensure_utc(end)
    if end <= start:
        raise ValueError(f"end ({end}) must be after start ({start})")
    if step_s <= 0.0:
        raise ValueError(f"step_s must be positive, got {step_s}")

    ts = timescale()
    t0 = ts.from_datetime(start)
    span_s = seconds_between(start, end)
    # The tolerance keeps an exactly-divisible span (e.g. one hour at 30 s)
    # from losing its final point to floating-point round-off.
    n = int(np.floor(span_s / step_s + 1e-9)) + 1
    offsets_days = np.arange(n, dtype=float) * (step_s / 86400.0)
    # Two-part Julian date: a single float at JD ~2.46e6 resolves only to
    # about 40 us, which would make a 30 s grid visibly non-uniform.
    return ts.tt_jd(t0.whole, t0.tt_fraction + offsets_days)


def iter_datetimes(start: datetime, end: datetime, step_s: float) -> Iterator[datetime]:
    """Plain-Python equivalent of :func:`time_range`, for tests and CLI output."""
    for dt in time_range(start, end, step_s).utc_datetime():
        yield dt.replace(tzinfo=UTC)


def seconds_between(a: datetime, b: datetime) -> float:
    """Elapsed seconds from ``a`` to ``b`` on the continuous TT scale.

    Using TT rather than UTC subtraction means a leap second in between is
    counted as the physical second it is, instead of vanishing. The difference
    is taken on the two-part Julian date (whole day + fraction), because a
    single float at JD ~2.46e6 resolves only to about 40 microseconds.
    """
    ta, tb = to_time(a), to_time(b)
    return float(((tb.whole - ta.whole) + (tb.tt_fraction - ta.tt_fraction)) * 86400.0)


def add_seconds(dt: datetime, seconds: float) -> datetime:
    """Advance by physical seconds on the continuous TT scale."""
    t = to_time(dt)
    return from_time(timescale().tt_jd(t.whole, t.tt_fraction + seconds / 86400.0))


__all__ = [
    "UTC",
    "timescale",
    "ensure_utc",
    "to_time",
    "to_times",
    "from_time",
    "time_range",
    "iter_datetimes",
    "seconds_between",
    "add_seconds",
    "timedelta",
]
