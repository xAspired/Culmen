# ADR 0002 — Skyfield rather than the raw `sgp4` package

**Status:** Accepted

## Context

SGP4 produces state vectors in TEME (True Equator, Mean Equinox) of date.
TEME is neither J2000/GCRS nor Earth-fixed. Getting from TEME to a topocentric
azimuth and elevation requires:

- TEME → ITRF via GMST and polar motion
- WGS84 geodetic station position (not geocentric)
- correct time scales: UTC input, UT1 for Earth rotation, TT for the
  ephemeris, and leap-second handling that does not treat UTC as continuous

Empirically this is where the overwhelming majority of errors in this domain
originate. The `sgp4` package supplies the propagator and nothing else, so
choosing it means writing all of the above by hand.

## Decision

Use `skyfield` for propagation, frame conversion, topocentric reduction and
time scales. Keep `sgp4` as a transitive dependency; it is what Skyfield calls
underneath, and its bundled Vallado verification data is used as our ground
truth.

`SatelliteState` exposes the raw TEME vectors alongside ITRF and geodetic, so
the propagator can still be verified against published TEME test vectors.

## Consequences

- We depend on Skyfield's internal representation in one place: the
  epoch-relative propagation path used for verification needs Skyfield's
  private leap-second accessor to reproduce its UTC fraction bit-for-bit.
  Isolated in `core/orbit/propagator.py::_leap_seconds` with a fallback.
- The timescale is built with `builtin=True`, so no network access is needed
  and results are reproducible. See A-TIME-1 and A-TIME-2 in
  `docs/math/assumptions.md`.
- Astropy is **not** adopted: Skyfield covers what we need, and Astropy is a
  heavy dependency for no marginal benefit here.

## Alternatives rejected

- **Raw `sgp4` plus hand-written frame code.** Maximum control, maximum risk,
  and it would consume the project's budget on a solved problem.
- **Orekit via a JVM bridge.** Agency-grade and genuinely excellent, but a
  Java runtime in the dependency chain is a heavy price for a Python tool.
