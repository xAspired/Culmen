# C/N₀, Eb/N₀, margin and Doppler

**Implemented in:** `core/rf/link.py`
**Tests:** `tests/test_link_budget.py`

## The chain

```
C/N₀  [dB-Hz] = EIRP − L_fs − L_other + G/T − k
Eb/N₀ [dB]    = C/N₀ − 10·log₁₀(R_b)
margin [dB]   = Eb/N₀ − Eb/N₀_required
```

with `k = 10·log₁₀(1.380649×10⁻²³) = −228.599 dBW/(Hz·K)`, the Boltzmann
constant in decibels. Subtracting a negative number adds 228.6 dB — worth
stating explicitly, since a sign slip here is a 457 dB error and therefore
obvious, while forgetting the term entirely is not.

## R_b is the information bit rate

**Not** the symbol rate, and **not** the channel rate after coding. At rate-½
coding the two differ by a factor of two, which is 3 dB. The required Eb/N₀
is taken as already including coding gain unless the caller lists it
separately.

`CCSDS 130.1-G` is the reference for coding gains (Reed–Solomon, turbo, LDPC).

## No data rate means no Eb/N₀

`compute_link_budget` returns `None` for Eb/N₀ and margin when no data rate is
given. Returning 0.0 would read as a closed link in every downstream check.

## Doppler

```
Δf = −f · v_r / c
```

negative while receding. At 8.2 GHz with ±7.5 km/s of range rate this is about
±205 kHz.

Doppler does **not** affect the power budget. It sets the receiver's
acquisition and tracking bandwidth, so Culmen reports it rather than
ignoring it. Relativistic terms are neglected (below 10⁻⁹ of the carrier at
LEO velocities).

## Sampling along the pass — not optional

Free-space loss at the horizon and at maximum elevation differ by **8–13 dB**
for a LEO pass (2300 km versus 500 km slant range). A budget evaluated only at
peak elevation overestimates achievable data volume systematically.

`PassLinkBudget` therefore makes the worst case, the best case, the FSPL
spread and the *closing seconds* first-class. `closing_seconds()` uses
trapezoidal attribution between samples rather than counting samples, so the
answer does not depend on the sampling step — asserted by comparing a 10-point
and a 100-point sampling of the same pass.

This is what Phase 6 will consume: data volume must integrate only over the
interval where the margin is non-negative.

## Reference

`link-budget-reference.md` — ITU-R small-satellite workshop case, including
the documented 0.2 dB discrepancy in the source's own Eb/N₀ figure.
