# Free-space path loss and EIRP

**Implemented in:** `core/rf/link.py`
**Tests:** `tests/test_link_budget.py`

## EIRP

```
EIRP [dBW] = P_tx [dBW] + G_tx [dBi] − L_line,tx [dB]
```

`P_tx [dBW] = 10·log₁₀(P_tx [W])` — a **power**, so 10·log₁₀, never 20.
Line loss is entered as a positive number of decibels and subtracted; a
negative "loss" is rejected at construction.

## Free-space path loss

```
L_fs [dB] = 32.4478 + 20·log₁₀(d [km]) + 20·log₁₀(f [MHz])
```

Returned as a **positive** number and subtracted in the chain, so the sign
convention cannot drift between call sites.

### The constant depends on the units

`32.4478 = 20·log₁₀(4π/c) + 20·log₁₀(10³ · 10⁶)`. It is derived in the test,
not memorised. Other common forms:

| Units | Constant |
|---|---|
| km, MHz | +32.4478 |
| km, GHz | +92.45 |
| m, Hz | −147.55 |

Using the wrong constant for the units is a 30–60 dB error. Both arguments in
the code carry their unit in the name and the conversion happens internally.

### Behaviour worth pinning

- Doubling the range costs exactly 6.02 dB.
- Doubling the frequency costs exactly 6.02 dB.

Both are asserted, because they catch a 10·log₁₀/20·log₁₀ slip instantly.

## Assumptions

- Free space: no atmosphere, no obstruction, far field.
- Isotropic spreading over a sphere of radius `d`.
- Transmitter on boresight; off-pointing belongs in `pointing_db`.

Atmospheric, rain, polarization, pointing, ionospheric and implementation
losses are **separate inputs**, defaulting to zero. Zero is optimistic by
construction, and a budget with no declared losses says so in its
`assumptions[]` rather than looking clean.

## Limits of validity

Far field only: `d > 2D²/λ`. At 8.2 GHz a 3 m dish has a far-field distance of
about 490 m, so any satellite pass is comfortably beyond it.

## Source

Standard link equation; see also ITU-R P.525 for the free-space calculation.
Reference case: `link-budget-reference.md`.
