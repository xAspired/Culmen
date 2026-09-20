"""Time-scale handling and TLE ingestion.

These are the two places where a silent error propagates into every later
number, so both are pinned hard: naive datetimes are refused rather than
guessed at, interval arithmetic runs on a continuous scale, and element sets
are validated (checksum, line pairing, satellite-number agreement) before
anything is propagated.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.orbit.tle import (
    TLE_AGE_REJECT_DAYS,
    TLE_AGE_WARN_DAYS,
    Tle,
    TleError,
    parse_tle_text,
    tle_checksum,
)
from core.time.scales import (
    UTC,
    add_seconds,
    ensure_utc,
    iter_datetimes,
    seconds_between,
    time_range,
    to_time,
)

# --- time ------------------------------------------------------------------


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError, match="naive"):
        ensure_utc(datetime(2024, 1, 1, 12, 0))


def test_aware_non_utc_datetimes_are_normalised():
    rome = timezone(timedelta(hours=2))
    got = ensure_utc(datetime(2024, 6, 1, 14, 0, tzinfo=rome))
    assert got == datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    assert got.tzinfo is UTC


def test_interval_arithmetic_counts_the_leap_second_of_2016():
    """From 2016-12-31 23:59:59 UTC to 2017-01-01 00:00:00 UTC is TWO seconds.

    A leap second (23:59:60) sat between them. Naive UTC subtraction reports
    one second, which is how leap seconds quietly corrupt propagation.
    """
    before = datetime(2016, 12, 31, 23, 59, 59, tzinfo=UTC)
    after = datetime(2017, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert (after - before).total_seconds() == 1.0  # what naive arithmetic says
    assert seconds_between(before, after) == pytest.approx(2.0, abs=1e-6)


def test_add_seconds_is_the_inverse_of_seconds_between():
    t0 = datetime(2024, 3, 1, 0, 0, tzinfo=UTC)
    for dt_s in (0.5, 60.0, 86400.0, 30 * 86400.0):
        assert seconds_between(t0, add_seconds(t0, dt_s)) == pytest.approx(dt_s, abs=1e-6)


def test_time_range_is_uniform_and_within_bounds():
    start = datetime(2024, 3, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    t = time_range(start, end, 30.0)
    assert len(t.tt) == 121
    # Measured on the two-part Julian date: the collapsed ``t.tt`` float only
    # resolves about 40 us at this epoch, which is the reason the grid is
    # built from (whole, fraction) in the first place.
    frac = t.tt_fraction
    spacing = [(b - a) * 86400.0 for a, b in zip(frac, frac[1:], strict=False)]
    assert all(s == pytest.approx(30.0, abs=1e-9) for s in spacing)
    assert to_time(start).tt == pytest.approx(float(t.tt[0]), abs=1e-12)


def test_time_range_rejects_a_reversed_or_zero_window():
    start = datetime(2024, 3, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        time_range(start, start, 30.0)
    with pytest.raises(ValueError):
        time_range(start, start + timedelta(hours=1), 0.0)


def test_iter_datetimes_yields_aware_utc():
    start = datetime(2024, 3, 1, tzinfo=UTC)
    out = list(iter_datetimes(start, start + timedelta(minutes=2), 60.0))
    assert len(out) == 3
    assert all(d.tzinfo is UTC for d in out)


# --- TLE -------------------------------------------------------------------

# Vallado's verification element set for catalogue number 5; a published
# reference, not a hand-written string.
L1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
L2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def test_checksum_matches_the_published_element_set():
    assert tle_checksum(L1) == int(L1[68])
    assert tle_checksum(L2) == int(L2[68])


def test_parsed_fields():
    tle = Tle(L1, L2, name="VANGUARD")
    assert tle.norad_id == 5
    assert tle.classification == "U"
    assert tle.cospar_id == "1958-002B"
    assert tle.inclination_deg == pytest.approx(34.2682)
    assert tle.eccentricity == pytest.approx(0.1859667)
    assert tle.mean_motion_rev_day == pytest.approx(10.82419157)
    assert tle.revolution_number == 41366


def test_epoch_decodes_to_the_expected_instant():
    """Epoch 00179.78495062 is day 179 of 2000 plus 0.78495062 of a day."""
    tle = Tle(L1, L2)
    epoch = tle.epoch_utc
    assert epoch.tzinfo is UTC
    assert epoch.year == 2000 and epoch.month == 6 and epoch.day == 27
    day_start = datetime(2000, 6, 27, tzinfo=UTC)
    assert seconds_between(day_start, epoch) == pytest.approx(
        0.78495062 * 86400.0, abs=1e-3
    )


def test_two_digit_year_pivots_at_57():
    """57-99 mean 19xx, 00-56 mean 20xx -- the Space-Track convention."""
    assert Tle(L1, L2).epoch_utc.year == 2000
    old1 = L1[:18] + "80" + L1[20:]
    old1 = old1[:68] + str(tle_checksum(old1))
    assert Tle(old1, L2).epoch_utc.year == 1980


def test_corrupted_checksum_is_rejected():
    bad = L1[:68] + str((int(L1[68]) + 1) % 10)
    with pytest.raises(TleError, match="checksum"):
        Tle(bad, L2)


def test_mismatched_satellite_numbers_are_rejected():
    other = "2 00006  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
    other = other[:68] + str(tle_checksum(other))
    with pytest.raises(TleError, match="satellite number"):
        Tle(L1, other)


def test_truncated_line_is_rejected():
    with pytest.raises(TleError, match="chars"):
        Tle(L1[:40], L2)


def test_age_is_reported_and_bucketed():
    tle = Tle(L1, L2)
    fresh = add_seconds(tle.epoch_utc, 3600.0)
    assert tle.age_days(fresh) == pytest.approx(1.0 / 24.0, abs=1e-6)
    assert tle.age_warning(fresh) is None

    stale = add_seconds(tle.epoch_utc, (TLE_AGE_WARN_DAYS + 1) * 86400.0)
    assert "warn above" in tle.age_warning(stale)

    ancient = add_seconds(tle.epoch_utc, (TLE_AGE_REJECT_DAYS + 1) * 86400.0)
    assert "not usable" in tle.age_warning(ancient)


def test_parse_3le_text_picks_up_names():
    text = f"VANGUARD 1\n{L1}\n{L2}\n"
    (tle,) = parse_tle_text(text, source="test")
    assert tle.name == "VANGUARD 1"
    assert tle.source == "test"


def test_parse_2le_text_without_names():
    (tle,) = parse_tle_text(f"{L1}\n{L2}\n")
    assert tle.name is None


def test_parse_rejects_an_orphan_line():
    with pytest.raises(TleError):
        parse_tle_text(f"{L1}\n")
    with pytest.raises(TleError):
        parse_tle_text("not a tle at all\n")
