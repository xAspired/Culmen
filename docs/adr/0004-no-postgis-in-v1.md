# ADR 0004 — No PostGIS in V1

**Status:** Accepted

## Context

PostGIS was in the original stack. The work here is time-varying 3D geometry,
not spatial querying: propagation, frame rotation, root finding. None of it
touches the database.

## Decision

PostgreSQL, no PostGIS. Ground stations store `lat_deg`, `lon_deg`, `alt_m` as
plain float columns.

## Consequences

- One less extension to install, version and containerise.
- A future "find stations within X km of a point" feature would want PostGIS.
  Adding it then is a migration, not a rewrite.

## Alternatives rejected

- **PostGIS now, "we'll need it eventually".** It buys `GEOGRAPHY(POINT)` and
  nothing else today, at the cost of a heavier dependency and a larger error
  surface.
