# Contributing to Culmen

Thank you for considering it. This document is short and specific, because
Culmen has a few rules that are unusual and matter more than the usual ones.

## The one rule that is not negotiable

**A number without an external reference is not verified.**

Culmen is a tool people will use to decide whether a spacecraft contact will
work. A test that only checks the code against itself proves that the code
agrees with the person who wrote it, and nothing else. So:

- the propagator is checked against Vallado's official SGP4 vectors at
  2 × 10⁻⁷ km;
- the topocentric geometry is checked against an independent ECEF→ENU
  derivation that shares no code with the production path;
- the link budget is checked against a published ITU-R workshop case,
  including a documented 0.2 dB discrepancy in the source that we did **not**
  paper over by widening the tolerance.

If you add a formula, bring its reference with it. Where no external reference
exists — as with achievable data volume, which depends on a specific ground
system — say so plainly in the test module's docstring and pin properties and
inverse consistency instead. That is what
[`tests/test_data_volume.py`](tests/test_data_volume.py) does.

**Never invent a number to make something work.** A plausible-looking default
for an atmospheric loss, a station coordinate taken from memory, a tolerance
widened until green — each of these is worse than an obvious gap, because it
is invisible.

## The other rules

**Declare every simplification.** `docs/math/assumptions.md` is numbered and
grows; entries are never deleted, only amended with the phase that removed
them. If your change rests on a simplification, add an entry and return it in
the relevant `assumptions[]`.

**Units live in names.** `range_km`, `freq_hz`, `power_dbw`. A test parses
every dataclass in `core/` and fails the build on a numeric field without a
unit suffix. See [ADR 0005](docs/adr/0005-unit-suffixes-not-a-units-library.md).

**`core/` is a pure library.** No FastAPI, no database, no network, no
Pydantic. A test parses every module and fails on a forbidden import, and a CI
job installs `core/` alone and runs it. See
[ADR 0001](docs/adr/0001-core-is-a-pure-library.md).

**No AI, ever, in the product.** No model, no inference dependency, no
learned heuristic. Every output is a deterministic function of its inputs, and
the same inputs with the same `engine_version` reproduce the same numbers.
See [ADR 0007](docs/adr/0007-no-ai-in-the-product.md).

**Culmen does not transmit, and does not fetch on the user's behalf.** It is
an analysis tool. Respecting a data provider's rate limits and attribution is
the operator's responsibility, and an API that downloaded silently would hide
that from them.

**Every `formula_ref` must resolve.** A test checks that every string literal
pointing into `docs/math/` names a file that exists. An audit trail citing a
missing note is worse than none.

## Architecture decisions

Anything that changes the shape of the project gets an ADR in `docs/adr/`:
context, decision, consequences, alternatives rejected. They are never
rewritten — a decision that turns out wrong gets a new ADR superseding the
old one, because the reasoning that led there is part of the history.

Read the existing ten before proposing an eleventh; several questions that
look open have already been answered, and a few were answered by reversing an
earlier choice.

## Getting set up

```bash
./scripts/dev.sh          # venv, dependencies, API on :8000, UI on :5173
```

Before opening a pull request:

```bash
pytest                    # must be green, and offline
ruff check .
mypy                      # strict, on core/, backend/ and scripts/
cd frontend && npx tsc --noEmit && npm run build
```

The suite runs entirely offline. A test that needs a network is a test that
fails for reasons unrelated to your change.

## What makes a good pull request

- **One thing.** A renaming and a bug fix in one diff are two pull requests.
- **A test that fails before your change.** Especially for a bug: the test is
  how we know it is fixed and stays fixed.
- **The reasoning in the code.** Comments explain *why*, not what — the
  existing code is written that way and it is the main reason it is
  maintainable.
- **Honesty about what you did not verify.** "I could not check this against
  X because Y" is a valuable sentence and always welcome.

Several real defects in this project were found by running the thing rather
than by reading it: a scheduler that booked one satellite onto two antennas at
once, an optimiser that returned after a single iteration while reporting
success. If you can run it, run it.

## Reporting a problem

An issue that says what you expected, what happened, and how to reproduce it
is worth ten that say it does not work. If it concerns a numeric result,
include the inputs — every response carries its own `inputs` and
`assumptions`, so paste those.

For security, see [SECURITY.md](SECURITY.md) instead.

## Licence

Contributions are accepted under Apache-2.0, the project's own licence
([ADR 0003](docs/adr/0003-apache-2-0-license.md)). By opening a pull request
you confirm you have the right to contribute the code under those terms.

Third-party **data** is different: it keeps its own licence, which travels
with it. Do not commit catalogue data — see
[`data/README.md`](data/README.md).
