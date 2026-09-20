# SGP4 and the TEME frame

**Implemented in:** `core/orbit/propagator.py`, `core/orbit/tle.py`
**Tests:** `tests/test_sgp4_vallado.py`

## The one thing to get right

SGP4 returns position and velocity in **TEME** — True Equator, Mean Equinox of
date. TEME is:

- **not** J2000 / GCRS — it uses the true equator and a mean equinox, so it
  differs from J2000 by precession, nutation and the equation of the equinoxes
- **not** ECEF / ITRF — it does not rotate with the Earth

Treating TEME as J2000 introduces an error that grows with the time from the
J2000 epoch. Treating it as Earth-fixed is wrong by up to a full Earth
rotation. Both mistakes are common.

## TEME → ITRF

```
r_PEF  = R_z(θ_GMST) · r_TEME          (θ_GMST from UT1)
r_ITRF = W(x_p, y_p) · r_PEF           (polar motion)
```

Delegated to Skyfield (ADR 0002). The velocity transformation additionally
carries the `ω_earth × r` term; omitting it is a ~0.46 km/s error at the
equator.

## Epoch-relative propagation

SGP4 is natively parameterised by minutes since the element-set epoch, which
is also how the verification vectors are published. `states_at_minutes_from_epoch`
offsets the two-part TAI fraction so the UTC fraction SGP4 receives matches
the element set bit-for-bit; going through `datetime` instead would truncate
at 1 µs and leave a residual of order 10⁻⁵ km, masking real defects.

## Verification

Against `SGP4-VER.TLE` / `tcppver.out` (Vallado et al., AIAA 2006-6753),
compared **in TEME**, matched **in file order** (several satellites appear more
than once with different element sets), at a tolerance of **2 × 10⁻⁷** in km
and km/s — the same tolerance the `sgp4` package uses.

## Units

| Symbol | Unit |
|---|---|
| position | km |
| velocity | km/s |
| `minutes` since epoch | min |
| `tle_age_days` | days |

## Limits of validity

SGP4 is only meaningful applied to TLE-derived mean elements, and its error
grows roughly with the square of time from epoch. See A-ORB-3: age is reported
on every pass, warned past 7 days, declared unusable past 30.

## Source

Vallado, Crawford, Hujsak & Kelso, *Revisiting Spacetrack Report #3*,
AIAA 2006-6753 (2006).
