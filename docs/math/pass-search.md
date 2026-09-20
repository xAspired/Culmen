# Pass search: AOS, LOS and maximum elevation

**Implemented in:** `core/passes/finder.py`
**Tests:** `tests/test_passes.py`

## Problem

Find every interval where

```
f(t) = elevation(t) − mask(azimuth(t))  >  0
```

AOS and LOS are by definition the roots of `f`; the maximum elevation is the
minimum of `−elevation` inside the interval.

`mask` may depend on azimuth (terrain profile), so `f` is evaluated against
the mask looked up at the current azimuth, not against a constant.

## Method

1. **Coarse grid.** Evaluate `f` every 30 s by default, vectorised. A 1 s grid
   over 30 days × 20 satellites × 10 stations does not scale; a 30 s grid is
   far below the duration of any LEO pass.
2. **Bracket and refine.** Each sign change of `f` between consecutive grid
   points brackets exactly one root. Brent's method refines it to 1 ms.
3. **Peak.** Bounded golden-section search on `−elevation` between AOS and LOS.

## A precision trap worth recording

Both `scipy.optimize.brentq` and `minimize_scalar(method="bounded")` combine an
absolute tolerance with a *relative* one. Run directly on Julian dates
(≈ 2.45 × 10⁶), the relative term is of order 0.04 days — an order of
magnitude wider than an entire pass. The bounded minimiser then returns after
a single iteration and reports success, giving a peak elevation several
degrees too low.

All refinement therefore runs on **seconds relative to the window start**.
`test_reported_maximum_is_the_real_maximum` compares against 1 s dense
sampling and is what caught this.

## Correctness checks in the suite

- AOS and LOS lie on the mask to within 10⁻⁴ degrees.
- The reported peak matches a 1 s dense scan to 10⁻³ degrees.
- The coarse search finds exactly the same passes as a 5 s brute-force grid,
  with boundaries agreeing within the brute-force resolution.
- Passes are ordered and non-overlapping.
- A raised mask yields a subset of the passes found with a lower mask.

## Limits

A pass shorter than roughly half the coarse step can be missed (A-PASS-1). A
pass straddling a window boundary is clipped and flagged (A-PASS-2); its
reported AOS or LOS is the window edge, not the true acquisition.

## Units

`coarse_step_s`, `duration_s` in seconds; angles in degrees; all instants are
timezone-aware UTC.
