# WGS84 geodetic ↔ ECEF

**Implemented in:** `core/geometry/station.py` (via Skyfield's `wgs84`)
**Independent reference implementation and tests:** `tests/test_geometry.py`

## Ellipsoid

| Parameter | Value |
|---|---|
| `a` (semi-major) | 6 378 137.0 m (exact by definition) |
| `1/f` (flattening) | 298.257 223 563 |
| `b = a(1−f)` | ≈ 6 356 752.314 245 m |
| `e² = f(2−f)` | ≈ 6.694 379 990 × 10⁻³ |

## Geodetic → ECEF (closed form)

```
N = a / sqrt(1 − e² sin²φ)
x = (N + h) cos φ cos λ
y = (N + h) cos φ sin λ
z = (N(1 − e²) + h) sin φ
```

with φ **geodetic** latitude, λ longitude, h height above the ellipsoid.

## ECEF → geodetic (Bowring)

```
p  = sqrt(x² + y²)
θ  = atan2(z·a, p·b)
φ  = atan2(z + e'²·b·sin³θ,  p − e²·a·cos³θ)        e'² = (a²−b²)/b²
λ  = atan2(y, x)
h  = p / cos φ − N
```

Single-pass Bowring is accurate to well under a millimetre for terrestrial
heights; no iteration is needed here.

## The trap

**Geodetic latitude ≠ geocentric latitude.** The maximum difference is about
0.192° near 45°, which is roughly 21 km along the surface. Station
coordinates on any map are geodetic. `test_geodetic_and_geocentric_latitude_differ_by_up_to_about_0p19_deg`
pins this difference so the distinction cannot quietly disappear.

## Units

`lat_deg`, `lon_deg` in degrees; `alt_m` in metres; ECEF in km at the API
boundary, metres internally in the conversion.

## Source

NIMA TR8350.2 (WGS84). Bowring, B. R., "Transformation from spatial to
geographical coordinates", *Survey Review* 23 (1976). Vallado, Algorithm 51.
