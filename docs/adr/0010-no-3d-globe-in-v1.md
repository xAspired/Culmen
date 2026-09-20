# ADR 0010 — No 3D globe in V1; SVG charts instead

**Status:** Accepted
**Supersedes:** the CesiumJS choice recorded in the Phase 0 review

## Context

The initial technical review picked CesiumJS for the frontend: a globe, ground
tracks and visibility cones come ready-made, and rewriting them in Three.js
would be wasted effort. That reasoning still holds *for a globe*.

What changed is the cost of having one at all:

1. **A globe needs imagery.** Cesium's default basemap is Cesium ion, which
   needs an access token. Culmen's whole posture is that it works offline and
   fetches nothing on the user's behalf — the timescale is bundled, the
   verification data ships with a dependency, the API refuses to call
   CelesTrak for you. A frontend that cannot draw its main view without a
   third-party account contradicts that.
2. **It is a large dependency** (tens of megabytes of assets) for a view that
   answers one question: does this orbit come over my station.
3. **It is not where the value is.** The questions Culmen exists to answer —
   will the link close, how much data moves, which check failed — are answered
   by the sky plot, the two time series and the verdict table, none of which
   need a globe.

## Decision

Build the V1 frontend with hand-written SVG:

- **sky plot** — az/el polar view, mask ring drawn, the below-mask part of the
  track dimmed rather than hidden;
- **two stacked time series** — elevation and link margin, sharing a time axis
  but never a y-axis (see below);
- **ground track** — equirectangular graticule, no basemap;
- **verdict table** — the checks, in full, with expected and actual.

React 19 + TypeScript + Vite. No charting library: the four charts are a few
hundred lines of SVG and adding a library would mean adopting its defaults —
the dual axes, the rainbow palettes — that this project specifically avoids.

Two rules the charts follow, both deliberate:

- **One y-scale per chart, never two.** Elevation and margin are separate
  charts. A dual-axis plot invites the reader to see a correlation the data
  does not assert.
- **The colour palette is validated, not chosen by eye.** The three
  categorical slots in use clear the colour-vision-deficiency separation and
  contrast gates against the dark surface. Status is never carried by colour
  alone: every badge pairs a glyph with its colour.

## Consequences

- No 3D view of visibility cones, no time-animated satellite. An operator who
  wants that has Gpredict and STK; Culmen is not competing there.
- The frontend builds to ~250 kB of JavaScript and serves from the API process
  itself, so `docker compose up` remains one service on one URL.
- The equirectangular projection has one real trap, handled: longitude wraps
  at ±180 and a naive polyline draws a streak across the map. The path is
  split wherever consecutive samples jump more than 180°.

## When to revisit

If the project grows a real need for 3D — visibility cones, conjunction
geometry, antenna keyhole shown in space rather than asserted by a check —
Cesium comes back, as an optional route that degrades to the SVG views when no
token is configured. The ADR to write then supersedes this one.
