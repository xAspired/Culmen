# ADR 0001 — `core/` is a pure library

**Status:** Accepted

## Context

The original architecture put the scientific code inside the backend
application, under `backend/app/domain/`. That arrangement makes the physics
reachable only through the web application: tests need an app context, the
database creeps into function signatures, and eventually somebody computes a
link budget inside a route handler because it is expedient.

The scientific engine is also the part of this project with the longest
useful life. It should be usable from a notebook, a CLI, a batch job or
someone else's software, none of which want FastAPI.

## Decision

`core/` is a standalone Python library:

- no imports from `backend/`, FastAPI, SQLAlchemy, Alembic, or any HTTP client
- no database access, no network access, no file I/O except reading the
  ground-station definition format
- installable and fully testable on its own

`backend/` depends on `core/`. The reverse is forbidden and is enforced by
`tests/test_architecture.py`, which parses every module in `core/` and fails
the build on a forbidden import. A rule that is not tested is a preference.

## Consequences

- The CLI exists partly as a forcing function: anything the CLI cannot do
  without a database does not belong in `core/`.
- Some duplication between `core/` dataclasses and Pydantic DTOs in
  `backend/app/schemas/`. Accepted: the boundary is worth the mapping code.
- Persistence concerns (caching a computed pass, invalidating it when the TLE
  changes) live entirely above `core/`.

## Alternatives rejected

- **Domain layer inside the backend.** Cheaper initially, but couples the
  physics to the web framework and to the database session lifecycle.
- **Separate repository for the engine.** Premature; it costs release
  coordination before there is anything to coordinate.
