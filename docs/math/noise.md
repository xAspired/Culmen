# Noise temperature and G/T

**Implemented in:** `core/rf/link.py`
**Tests:** `tests/test_link_budget.py`

## System noise temperature

Referred to the **antenna output plane**:

```
L      = 10^(L_line[dB]/10)              (loss as a linear ratio ≥ 1)
T_line = (L − 1) · T_ambient             (T_ambient = 290 K by default)
T_sys  = T_ant + T_line + L · T_LNA      [K]
```

Note the `L ·` on the LNA term: a lossy line before the amplifier both adds
its own noise **and** multiplies the amplifier's contribution when referred
back to the antenna.

## G/T

```
G/T [dB/K] = G [dBi] − 10·log₁₀(T_sys [K])
```

## The reference-plane trap

The same physical system has a different `T_sys` at the antenna flange than at
the LNA input, and `G/T` must be referred to the **same plane** as the losses
used in the budget. Getting this wrong is a routine 1–2 dB error that never
looks obviously wrong.

`Receiver` therefore accepts **either** an explicit `g_over_t_dbk` **or** the
pair `(gain_dbi, system_noise_temp_k)` — never both. Supplying both is
rejected at construction rather than silently preferring one.

## Noise figure versus noise temperature

```
T = T₀ · (10^(NF[dB]/10) − 1)            T₀ = 290 K
```

Never add noise figures and temperatures without converting first.

## Verified against

The ITU reference case: a 120 K LNB behind 1 dB of input loss giving
T_sys = 510.4 K and G/T = −9.07 dB/K. The test back-solves the implied antenna
temperature, confirms the arithmetic reproduces the published figure, and
checks the implied antenna temperature is itself physically sensible — a
reference is only useful once it has been checked, not merely copied.

## Not modelled in V1 (A-GEO-6)

- Elevation dependence of `T_ant`. Antenna noise temperature rises steeply at
  low elevation; V1 treats it as constant and says so.
- Sun and Moon in the beam, which raise `T_ant` dramatically.
- Rain-induced noise temperature increase (couples to ITU-R P.618).
