# Antenna gain

**Implemented in:** `core/rf/link.py::parabolic_gain_dbi`
**Tests:** `tests/test_link_budget.py`

## Circular aperture

```
G = 10·log₁₀( η · (π·D/λ)² )     [dBi]      λ = c/f
```

| Symbol | Meaning | Unit |
|---|---|---|
| `D` | aperture diameter | m |
| `λ` | wavelength | m |
| `η` | aperture efficiency | dimensionless, 0 < η ≤ 1 |

## Efficiency is never 1.0

Real dish efficiency is **0.5–0.65** once illumination taper, spillover,
blockage and surface error are accounted for. The default here is 0.55.

Assuming η = 1.0 inflates the gain by `−10·log₁₀(0.55) ≈ 2.6 dB` — an error
that flows straight into the margin and makes a failing link look like a
passing one. Pinned by `test_assuming_unit_efficiency_inflates_gain_by_2_6_db`.

## dBi versus dBd

```
dBd = dBi − 2.15
```

2.15 dB is the gain of a half-wave dipole over an isotropic radiator. Mixing
the two references is a silent 2.15 dB error. Both conversions live in
`core/units.py` and are tested.

## Worked value

3 m dish at 8.2 GHz, η = 0.55:
λ = 36.56 mm, πD/λ = 257.8, `10·log₁₀(0.55 · 257.8²)` = **45.63 dBi**.

Doubling the diameter adds exactly 6.02 dB — asserted.

## Not modelled in V1

- Beamwidth and pointing-error-to-loss conversion (pointing loss is an input).
- Surface-error (Ruze) loss beyond what the efficiency factor absorbs.
- Sidelobe patterns.
