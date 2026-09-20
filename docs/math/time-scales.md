# Time scales

**Implemented in:** `core/time/scales.py`
**Tests:** `tests/test_time_and_tle.py`

## Scales used

| Scale | Role here |
|---|---|
| UTC | The only scale exposed at the API boundary. Discontinuous: contains leap seconds. |
| TAI | Continuous. `TAI − UTC` is an integer number of leap seconds. |
| TT | Continuous, `TT = TAI + 32.184 s`. Used for all interval arithmetic. |
| UT1 | Tied to Earth rotation, `UT1 = UTC + ΔUT1`, with `|ΔUT1| < 0.9 s`. Drives the TEME→ITRF rotation. |

## Rules the code enforces

**Naive datetimes are refused.** `ensure_utc` raises rather than assuming a
timezone. A silently mis-assumed local time is a one- or two-hour error.

**Intervals are computed on TT, never on UTC.**

```
Δt_seconds = ((tt_b.whole − tt_a.whole) + (tt_b.fraction − tt_a.fraction)) × 86400
```

Naive UTC subtraction across 2016-12-31 23:59:60 reports 1 s where 2 s
elapsed. Pinned by `test_interval_arithmetic_counts_the_leap_second_of_2016`.

**Julian dates are kept in two parts** (whole day + fraction). A single IEEE
double at JD ≈ 2.46 × 10⁶ has a resolution of about 4 × 10⁻¹⁰ days ≈ 40 µs.
At 7 km/s that is 0.3 mm of position — irrelevant operationally, but enough to
make a 30 s sampling grid visibly non-uniform and to swamp a verification
tolerance of 2 × 10⁻⁷ km. Every grid and offset therefore uses
`ts.tt_jd(whole, fraction)`.

## Units

| Symbol | Unit |
|---|---|
| `step_s`, `seconds` | s (SI seconds, continuous) |
| `.whole`, `.fraction` | days |
| `ΔUT1` | s |

## Assumptions

A-TIME-1 (bundled leap-second table), A-TIME-2 (built-in ΔUT1 approximation),
A-TIME-3 (TT for arithmetic). See `assumptions.md`.

## Source

IERS Conventions (2010), chapter 1. Skyfield's time documentation for the
concrete implementation of the scale conversions.
