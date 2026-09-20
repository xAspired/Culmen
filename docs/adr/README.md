# Architecture Decision Records

One file per decision, numbered, never rewritten. A decision that turns out
wrong gets a new ADR that supersedes the old one; the old one stays, because
the reasoning that led to it is part of the project's history.

Format: context, decision, consequences, alternatives rejected.

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-core-is-a-pure-library.md) | `core/` is a pure library with no web, database or network dependency | Accepted |
| [0002](0002-skyfield-over-raw-sgp4.md) | Use Skyfield rather than the raw `sgp4` package | Accepted |
| [0003](0003-apache-2-0-license.md) | License the code Apache-2.0 | Accepted |
| [0004](0004-no-postgis-in-v1.md) | No PostGIS in V1 | Accepted |
| [0005](0005-unit-suffixes-not-a-units-library.md) | Unit suffixes in names, enforced by test, instead of a units library | Accepted |
| [0006](0006-explainable-verdicts-as-the-core-product.md) | Every verdict carries its own audit trail | Accepted |
| [0007](0007-no-ai-in-the-product.md) | No AI/ML of any kind inside Culmen | Accepted |
| [0008](0008-project-name.md) | The project is called Culmen | Accepted |
| [0009](0009-api-before-persistence.md) | The API ships before the database | Accepted |
| [0010](0010-no-3d-globe-in-v1.md) | No 3D globe in V1; validated SVG charts instead | Accepted |
