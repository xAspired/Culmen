# ADR 0005 — Unit suffixes in names, not a units library

**Status:** Accepted

## Context

Unit confusion is a leading cause of error in this domain: km vs m, Hz vs MHz,
dBW vs dBm, 10·log₁₀ vs 20·log₁₀. A units library such as `pint` makes units
explicit at runtime.

## Decision

Do not adopt `pint`. Instead:

1. Every numeric name carries a unit suffix: `range_km`, `freq_hz`,
   `power_dbw`, `gain_dbi`, `el_deg`. This is mandatory, not stylistic.
2. `tests/test_architecture.py` parses every dataclass in `core/` and fails
   the build on a numeric field without a unit suffix.
3. Conversions live in one place, `core/units.py`, with `db10` and `db20` as
   distinct functions so the power/amplitude distinction cannot be fudged.
4. Every formula gets a note in `docs/math/` and a test against a known value.

## Consequences

- The check is syntactic: it catches a missing suffix, not a wrong one.
  `range_km` assigned a value in metres still passes. Numerical regression
  tests against external references are what catch that.
- No runtime overhead, no wrapper types leaking through every signature.

## Alternatives rejected

- **`pint` throughout.** Genuine safety, but it slows numerical inner loops,
  complicates NumPy vectorisation and infects every function signature.
