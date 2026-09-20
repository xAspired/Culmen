# Atmospheric attenuation — ITU-R P.676 and P.618

Covers `core/rf/atmosphere.py`. Phase 5.

Culmen **does not reimplement** either Recommendation. P.676 rests on tables of
spectroscopic line data for oxygen and water vapour; P.618 on global rainfall
maps. Transcribing either would produce numbers that look authoritative and are
wrong. This note therefore documents the *interface, the units, the validity
limits and the verification strategy* — not a derivation.

## What is computed

| Quantity | Symbol | Unit | Source |
|---|---|---|---|
| Gaseous slant-path attenuation | `A_g` | dB | ITU-R P.676 (oxygen + water vapour) |
| Rain attenuation, exceeded p% of an average year | `A_r` | dB | ITU-R P.618 |

Both are added to the link budget as path losses:

```
L_total_dB = FSPL + A_g + A_r + polarization + pointing + ionospheric + implementation
```

See [`fspl.md`](fspl.md) and [`link-budget-reference.md`](link-budget-reference.md).

## Implementation

[ITU-Rpy](https://github.com/inigodelportillo/ITU-Rpy), an independent
implementation of the ITU-R Recommendations, is called through a thin wrapper.
It is an **optional** dependency:

```bash
pip install "culmen[atmosphere]"
```

Without it, `core/` still imports and runs (ADR 0001), and the two terms stay
inputs defaulting to 0 dB — an optimistic budget that says so in its
`assumptions[]` (A-RF-1).

## Units at the boundary

ITU-Rpy takes **GHz** and **degrees**; Culmen carries **Hz** and degrees
(ADR 0005). The wrapper divides by 1e9 at the call and nowhere else. ITU-Rpy
returns an `astropy` quantity; `.value` is taken in dB.

| Symbol | Meaning | Unit |
|---|---|---|
| `f` | frequency | GHz at the call, Hz in Culmen |
| `el` | elevation above the local horizon | degrees |
| `rho` | surface water-vapour density | g/m³ |
| `P` | surface pressure | hPa |
| `T` | surface temperature | K |
| `hs` | station height above mean sea level | km |
| `p` | percentage of an average year the rain figure is exceeded | % |

Defaults are the ITU-R P.835 mean annual global reference atmosphere:
1013.25 hPa, 288.15 K, 7.5 g/m³.

## The exceedance percentage is part of the answer

`A_r` is a **statistic**, not a value. `p = 0.01` means "exceeded 0.01% of an
average year", i.e. 99.99% availability. The figure moves by several dB between
0.1% and 0.001%, so it is returned inside `assumptions[]` alongside the number.
A margin quoted without its availability target is not a margin.

Validity: P.618's rain model is defined for `0.001 ≤ p ≤ 5`. Outside that,
`AtmosphereConditions` raises rather than extrapolating silently.

## Limits of validity

- **Elevation.** P.676's approximate slant-path method is recommended for
  **5°–90°**. Culmen still answers below 5° — a planner asking about a horizon
  grazer deserves a number — but appends an assumption saying the figure is an
  extrapolation that understates the true path length. At and below 0° the
  models are undefined and the wrapper raises.
- **Frequency.** The models used here run to 1000 GHz; above that the wrapper
  raises.
- **Meteorology.** Surface conditions are assumed constant along the path. A
  site with a measured vertical profile should supply its own.
- **Time.** The gaseous figure is a mean condition, not a worst case. The rain
  figure is a long-term statistic and says nothing about any particular pass.
- **Not modelled here:** cloud and fog attenuation (P.840), tropospheric
  scintillation (P.618 §2.4), and ionospheric effects (A-RF-4).

## The magnitudes, and a correction

These were measured for Padova (45.4064°N, 11.8768°E, 12 m) at 8.2 GHz:

| Elevation | Gaseous, P.676 | Rain, P.618 @ 0.01% |
|---|---|---|
| 90° | 0.045 dB | — |
| 40° | 0.070 dB | 2.32 dB |
| 20° | 0.132 dB | 3.50 dB |
| 10° | 0.260 dB | 5.55 dB |
| 5° | 0.517 dB | 8.88 dB |

Earlier revisions of this project's `assumptions.md` and README said the
atmosphere was worth "several dB at 8.2 GHz and 10°" without separating the two
terms. That attributed rain's magnitude to gaseous absorption — an
order-of-magnitude error in the term a reader would most likely reach for.
The table above is the correction; A-RF-1 records it.

At Ka-band the picture inverts in severity: 20 GHz rain at 10° is about
39 dB, which is why X-band downlinks persist.

## Verification

There is no single published case to check against, and asserting the constants
ITU-Rpy returns would only pin today's output of somebody else's code. The
tests in `tests/test_atmosphere.py` check the **physics** and the **wiring**
instead:

| Test | Property |
|---|---|
| `test_gaseous_attenuation_follows_the_cosecant_law` | `A(el) ≈ A(90°)/sin(el)` — catches radians-for-degrees and transposed arguments |
| `test_gaseous_attenuation_rises_sharply_at_the_water_vapour_line` | 22.235 GHz resonance is resolved |
| `test_more_humid_air_attenuates_more` | monotone in `rho` |
| `test_gaseous_attenuation_at_x_band_is_small_not_several_db` | pins the correction above |
| `test_rain_dominates_gas_at_x_band` | the ratio, not the values |
| `test_rain_attenuation_grows_as_the_availability_target_tightens` | monotone in `p` |
| `test_rain_attenuation_is_far_worse_at_ka_band` | monotone in frequency |
| `test_a_dry_climate_attenuates_less_than_a_wet_one` | the rainfall maps are actually being consulted |
| `test_the_models_validity_floor_is_declared_not_hidden` | the 5° limit travels with the number |
| `test_computing_the_atmosphere_changes_a_real_margin` | end to end, against a 0 dB default |

The cosecant check is the strongest of these: almost any miswiring of units or
argument order breaks it immediately.
