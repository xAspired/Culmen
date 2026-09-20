# ADR 0009 — The API ships before the database

**Status:** Accepted

## Context

The original plan put PostgreSQL alongside the API from the start, with tables
for satellites, stations, passes and contacts.

Working through Phases 5 to 9 changed the picture. ADR 0006 established that
computed passes and contacts are a **cache of a calculation**, keyed by the
element set and the engine version. A cache that outlives its inputs is worse
than no cache: it returns confident, stale answers.

That leaves very little that genuinely wants persisting today:

- **Ground stations** already have a durable, versioned, human-editable home:
  the YAML definition format, which is deliberately a small standard of its
  own and works in git.
- **Element sets** are supplied by the caller and are, by construction,
  short-lived — the tool warns past 7 days and refuses past 30.
- **Passes, budgets, verdicts and plans** are recomputed in milliseconds from
  those two, and must be recomputed whenever either changes.

## Decision

Ship the HTTP API with an in-process registry: stations loaded from the YAML
directory, element sets held in memory for the life of the process. No
database, no migrations, no ORM.

`docker compose up` starts one service.

## Consequences

- A restart loses imported element sets. Acceptable: they are a few kilobytes
  the caller already has, and re-importing is one request.
- No horizontal scaling of the registry. Also acceptable at this stage; the
  compute endpoints (`/link-budget/compute`,
  `/data-volume/required-duration`) are entirely stateless and scale freely.
- The infrastructure layer (`backend/app/infrastructure/`) already exists as
  the seam where a repository implementation will go, so adding persistence
  later does not touch the services or the routes.

## When this should be revisited

The moment any of these becomes real:

- stations defined through the API rather than on disk, by more than one user;
- saved plans that must survive a restart and be shared;
- an audit trail of verdicts kept for compliance — which is exactly what the
  `contact_checks` table in the Phase 0 schema was for.

At that point the Phase 0 schema is the starting point, not a fresh design,
and SQLAlchemy 2.0 with Alembic from the first migration (ADR 0004 still
stands: no PostGIS).

## Alternatives rejected

- **Postgres now.** A dependency, a compose service, a migration tool and a
  repository layer, in exchange for persisting values that must be invalidated
  on almost every change.
- **SQLite as a middle ground.** Same conceptual cost, and it would quietly
  become the production answer.
