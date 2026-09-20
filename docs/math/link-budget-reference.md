# Verification reference for the Phase 5 link budget

Before any RF code is written, this is the external case it must reproduce.
A link budget that only agrees with itself proves nothing.

## Source

Otto Koudelka, *Link Budget Calculations*, ITU-R / ITU Prague workshop on
small satellites, 2015.
<https://www.itu.int/en/ITU-R/space/workshops/2015-prague-small-sat/Presentations/ITU-linkbudget.pdf>

Chosen because it is an ITU-hosted teaching case, publicly downloadable, and
gives the **whole chain** from EIRP to margin rather than isolated formulas.
UHF rather than X-band, which is fine: the chain is identical and the
atmospheric terms are small, so it isolates the core arithmetic. A second,
X-band case must be added before Phase 5 is called done, because P.618/P.676
only become significant there.

## The case (downlink)

| Quantity | Value | Unit |
|---|---|---|
| Frequency | 438 | MHz |
| Satellite EIRP | −4 | dBW |
| Slant range | 1 000 | km |
| Free-space path loss | 145.3 | dB |
| Polarization loss | 1.5 | dB |
| Pointing loss | 0.5 | dB |
| Ionospheric loss | 0.7 | dB |
| Atmospheric attenuation | 2.0 | dB |
| LNB noise temperature | 120 | K |
| Input loss | 1 | dB |
| System noise temperature | 510.4 | K |
| Earth-station G/T | −9.07 | dB/K |
| C/N (downlink) | 12.53 | dB |
| Bandwidth | 200 | kHz |
| Data rate | 100 (rate-½ coding) | kbit/s |
| Achieved Eb/N₀ | 15.34 | dB |
| Required Eb/N₀ (BER 1e−6) | 7 | dB |
| **System margin** | **8.34** | **dB** |

## Independent checks already done on the reference itself

A reference is only useful once it has been checked, not merely copied.

**FSPL.** `32.44 + 20·log₁₀(d_km) + 20·log₁₀(f_MHz)`
= `32.44 + 20·log₁₀(1000) + 20·log₁₀(438)` = `32.44 + 60.00 + 52.83` =
**145.27 dB**. Matches the quoted 145.3 dB. The constant 32.44 is specific to
km and MHz; with other units it changes.

**Margin.** `15.34 − 7 = 8.34 dB`. Consistent.

**Eb/N₀ — a 0.2 dB discrepancy to resolve.**
`Eb/N₀ = C/N + 10·log₁₀(B / R_b)` = `12.53 + 10·log₁₀(200 000 / 100 000)`
= `12.53 + 3.01` = **15.54 dB**, where the slide states 15.34 dB.

The gap is small and almost certainly rounding somewhere upstream in the
slide's own chain (the quoted C/N is given to two decimals from values that
are not). **It is not to be waved away.** When Phase 5 lands, the test must
either reproduce 15.34 by following the source's exact intermediate values, or
state in the test itself which figure it targets and why. An unexplained
0.2 dB is exactly the kind of thing that becomes 2 dB later.

## What the Phase 5 test must do

1. Reproduce every line above, each to a documented tolerance.
2. Fail the build if any line moves — golden-value regression.
3. Cover the pieces this case does *not* exercise, with their own references:
   parabolic antenna gain with realistic efficiency (η ≈ 0.5–0.65), ITU-R
   P.676 gaseous attenuation, ITU-R P.618 rain, and elevation-dependent
   antenna noise temperature.
4. Sample the budget **along the pass**, not at peak elevation only: FSPL at
   the horizon and at the peak differ by 8–10 dB for LEO.

## Still needed

An X-band (≈8 GHz) published case with atmospheric terms included. Candidates
to check: a published CubeSat mission design report, or the NASA DSN
Telecommunications Link Design Handbook (810-005), which is public and
contains full worked examples.
