# ADR 0008 — The project is called Culmen

**Status:** Accepted
**Supersedes:** the working name "GroundLink"

## Context

The project was drafted under the working name *GroundLink*. That name is
already in use in aviation for aircraft-to-ground data transfer systems. Not
an automatic legal obstacle, but a poor foundation for a public repository, a
package name and eventually a domain — and renaming later costs far more than
renaming before the first public commit.

## Decision

**Culmen.**

In astronomy, *culmination* is the moment a body reaches its highest point
above the horizon. That is precisely the maximum-elevation instant of a pass:
the single geometric fact from which slant range, free-space loss, link margin
and achievable data volume all follow. *Culmen* is the Latin root — summit,
highest point.

The name therefore describes what the tool reasons about, rather than
gesturing at the domain.

Practical checks at the time of the decision:

- free on PyPI
- short, unambiguous to type, pronounceable in both English and Italian
- no collision found in aerospace or ground-segment software

Known non-conflicts, recorded so nobody is surprised: "culmen" is also a term
in ornithology (the ridge of a bird's upper beak) and in anatomy (part of the
cerebellum). Neither is a software or aerospace use.

## Consequences

- Package name, CLI command and documentation all use `culmen` / `Culmen`.
- The Python package inside the repository remains `core`: the library is the
  project's core, and prefixing every import with the project name would add
  nothing (ADR 0001).
- A trademark search and a check of the GitHub namespace remain the owner's
  responsibility; neither was possible from the environment where this
  decision was drafted.

## Alternatives rejected

- **GroundLink** — the working name; prior use in aviation.
- **Overpass**, **Downlink**, **Perigee**, **Nadir**, **Apsis** — all already
  taken on PyPI, and the first collides with the well-known OpenStreetMap
  Overpass API.
