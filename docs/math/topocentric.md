# Topocentric look angles

**Implemented in:** `core/geometry/station.py`
**Tests:** `tests/test_geometry.py`

## Definition

Given the satellite and station positions in ITRF, the line-of-sight vector
`d = r_sat − r_station` is rotated into the station's local East-North-Up
frame:

```
ê = (−sin λ,           cos λ,          0     )
n̂ = (−sin φ cos λ,    −sin φ sin λ,    cos φ )
û = ( cos φ cos λ,      cos φ sin λ,    sin φ )

E = d·ê     N = d·n̂     U = d·û

range = |d|
az    = atan2(E, N)   mod 360°      (from north, clockwise through east)
el    = asin(U / |d|)
```

with φ **geodetic** latitude (see `geodetic.md`).

## Range rate

```
ṙ = (d · ḋ) / |d|
```

positive when receding. This is the quantity that drives Doppler; it is
verified against a central finite difference of the range itself, rather than
re-derived independently, in `test_range_rate_matches_numerical_derivative_of_range`.

## Verification strategy

The production path goes through Skyfield. The test re-derives az/el/range by
the explicit rotation above, starting from the ITRF state vectors, sharing no
code with the production path. Agreement to 10⁻⁴ degrees across five stations
spanning equatorial, mid-latitude, polar and southern sites means both the
frame conversion and the reduction are right, not merely self-consistent.

Azimuth is ill-conditioned within a degree of the zenith (E and N both → 0)
and is not compared there.

## Assumptions

**Elevations are geometric.** No atmospheric refraction is applied; near the
horizon refraction raises the apparent elevation by roughly 0.5°. See A-GEO-3.

## Units

`az_deg`, `el_deg` in degrees; `range_km` in km; `range_rate_km_s` in km/s.
