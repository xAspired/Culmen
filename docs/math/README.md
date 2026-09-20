# Mathematical notes

One file per formula. Each must state:

1. the formula, in the exact form the code uses
2. the units of every symbol
3. the source (book, paper or standard, with section or equation number)
4. the assumptions it rests on
5. its limits of validity
6. the test that pins it, by name

A formula in `core/` without a note here, and a note without a test, are both
build failures waiting to be written.

## Index

| Note | Covers | Phase |
|---|---|---|
| [assumptions.md](assumptions.md) | Every declared simplification, project-wide | all |
| `time-scales.md` | UTC / UT1 / TT, leap seconds, two-part Julian dates | 1 |
| `sgp4-and-teme.md` | SGP4 output frame and its conversion to ITRF | 1 |
| `geodetic.md` | WGS84 geodetic ↔ ECEF, Bowring's method | 2 |
| `topocentric.md` | ECEF → ENU, azimuth, elevation, range, range rate | 2 |
| `pass-search.md` | Root finding for AOS/LOS, peak refinement | 3 |
| `fspl.md` | Free-space path loss | 5 |
| `atmosphere.md` | ITU-R P.676 gaseous and P.618 rain attenuation | 5 |
| `antenna-gain.md` | Parabolic gain, efficiency, dBi/dBd | 5 |
| `noise.md` | System noise temperature, G/T, reference planes | 5 |
| `cn0-ebn0.md` | C/N₀, Eb/N₀, coding gain, margin | 5 |
| `data-volume.md` | Framing efficiency, lock time, negative-margin exclusion | 6 |

Notes for Phases 1–3 are written alongside the code they describe; the
Phase 5+ entries are placeholders naming what must exist before that code is
merged.
