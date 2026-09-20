# ADR 0006 — Every verdict carries its own audit trail

**Status:** Accepted

## Context

Pass prediction is solved (Gpredict, SatNOGS, Skyfield). Link budgets are
solved (a spreadsheet). What no open tool provides is a *traceable verdict*:
"this contact fails, the link-margin check failed by 2.4 dB, here are the
inputs, the formula, the assumptions, and three alternatives".

If provenance is retrofitted after the maths is written, it never happens: the
numbers arrive as bare floats and the context is gone.

## Decision

`core/provenance.py` defines `Computed[T]`, carrying `value`, `unit`,
`formula_ref` (a path into `docs/math/`), `inputs` and `assumptions`.

Rule: **any value a Contact Validator check compares against a threshold must
be a `Computed`.** Intermediate scratch values need not be.

The database mirrors this: `contact_checks` stores one row per check with
expected, actual, unit and message, so a verdict is queryable after the fact.

Corollary: computed passes and contacts are *caches*, not truth. Each carries
`tle_set_id` and `engine_version`; a result computed from a superseded element
set is invalidated rather than reused.

## Consequences

- More verbose return types in the RF and validation layers.
- API responses carry `assumptions[]`, which is the honest counterpart to
  `docs/math/assumptions.md`.
