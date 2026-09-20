# Declared assumptions and simplifications

Every simplification Culmen makes is listed here. Nothing is simplified
silently. Where a value is returned through the API, the relevant entries also
appear in that response's `assumptions[]`.

This file grows as phases land. Entries are never deleted, only amended with
the phase in which the simplification was removed.

---

## Time

**A-TIME-1 — Leap-second table is the one bundled with Skyfield.**
The timescale is built with `builtin=True`, so the library works offline and
deterministically. The table is frozen at the Skyfield release date. No leap
second has been announced beyond it, so it is exact for present-day epochs; a
future leap second requires a Skyfield upgrade.
*Impact:* none today; one second if a future leap second is missed.

**A-TIME-2 — ΔUT1 comes from Skyfield's built-in approximation.**
We do not download IERS finals. Earth rotation uses UT1, and ΔUT1 can reach
±0.9 s; the built-in fit keeps the residual well below that.
*Impact:* sub-kilometre in along-longitude ground-track position; negligible
at the ~0.01° look-angle tolerance we test to.
*Removal:* optional IERS finals ingestion, post-MVP.

**A-TIME-3 — All interval arithmetic runs on the continuous TT scale.**
UTC is not continuous. `seconds_between` and `add_seconds` convert to TT,
compute, and convert back, using two-part Julian dates because a single float
at JD ≈ 2.46 × 10⁶ resolves only about 40 µs.

## Orbit

**A-ORB-1 — SGP4 only.**
No numerical propagator, no manoeuvre modelling. SGP4 is the propagator the
TLE data format is defined against; using a "better" propagator on TLE input
is a category error, not an improvement.

**A-ORB-2 — The TLE epoch is interpreted as UTC**, per AIAA 2006-6753.

**A-ORB-3 — TLE age is reported, and flagged past 7 days.**
SGP4 error grows roughly with the square of time from epoch. Past 7 days a
warning is attached to every pass; past 30 days the element set is declared
unusable. These thresholds are conventions, not physics.
*Impact:* at 7 days a LEO along-track error of order kilometres is normal,
which moves AOS by seconds to tens of seconds.

## Frames and geometry

**A-GEO-1 — SGP4 output is TEME, converted to ITRF by Skyfield.**
TEME is neither J2000 nor Earth-fixed. Conversion uses GMST and polar motion.

**A-GEO-2 — Latitude is WGS84 geodetic throughout.**
Geodetic and geocentric latitude differ by up to ≈ 0.19° (≈ 21 km on the
surface). Pinned by a test.

**A-GEO-3 — Elevations are geometric; atmospheric refraction is NOT modelled.**
Near the horizon refraction raises apparent elevation by roughly 0.5°. At a
10° mask the effect on AOS/LOS is a few seconds.
*Impact:* AOS slightly late, LOS slightly early, relative to what an operator
would observe optically.
*Removal:* an optional refraction model, post-MVP.

**A-GEO-4 — The horizon is a constant elevation mask by default.**
Real sites have terrain. The station definition format already carries an
optional `horizon_profile` (azimuth → minimum elevation, linearly
interpolated and wrapped), so terrain can be supplied where it is known.
*Impact:* passes low over an obstructed azimuth may be reported as usable.

**A-GEO-5 — No antenna slew, keyhole or mechanical-limit modelling.**
A pass crossing near the zenith may be mechanically untrackable by an az/el
mount. Reported as a pass regardless.
*Removal:* Phase 7, as a Contact Validator check.

**A-GEO-6 — Solar and lunar interference are not modelled.**
Pointing near the Sun raises antenna noise temperature substantially.
*Removal:* post-MVP, as a WARN-level check.

## Pass search

**A-PASS-1 — Coarse grid plus root refinement.**
Default coarse step 30 s. A pass shorter than roughly half the coarse step can
be missed entirely. For LEO at a 10° mask this does not occur; for very high
masks or very high orbits, reduce the step.
*Mitigation:* verified against a 5 s brute-force grid in the test suite.

**A-PASS-2 — Windows clip rather than extend.**
A pass in progress at the window boundary is returned clipped and flagged. The
reported AOS/LOS is then the window edge, not the true acquisition.

---

## Not yet implemented (so: not assumed, absent)

The following affect results and are deliberately absent until their phase:

- Elevation-dependent antenna noise temperature, ITU-R P.372 (A-RF-2).
- Contact validation and verdicts (Phase 7).
- Antenna mechanical limits and slew feasibility (A-GEO-5, Phase 7).
- Scheduling conflicts and contact ranking (Phase 9).

---

## RF and data volume (Phases 5-6)

**A-RF-1 — Atmospheric and rain attenuation default to zero unless computed.**
`PathLosses` accepts `atmospheric_db` and `rain_db` as inputs and defaults both
to 0 dB. `core.rf.atmosphere` computes them from ITU-R P.676 and P.618 via
ITU-Rpy, but that is an **optional** dependency (`pip install
"culmen[atmosphere]"`), so a budget built without it is optimistic by the whole
atmospheric term and says so in its `assumptions[]`.
*Impact:* at 8.2 GHz and 10 deg elevation, for Padova, the two terms are
gaseous **0.26 dB** and rain **5.5 dB** at 0.01% exceedance — about 5.8 dB of
missing margin. They are not of the same order and must not be quoted together.
*Correction:* earlier revisions of this entry, and of the README, said these
were "several dB" without separating them, which attributed rain's magnitude to
gaseous absorption. The split above was measured, and
`tests/test_atmosphere.py::test_gaseous_attenuation_at_x_band_is_small_not_several_db`
now pins it.
*Removal:* partial. The computation exists; making it non-optional would
contradict ADR 0001.

**A-RF-2 — Antenna noise temperature is constant.**
It rises steeply at low elevation and dramatically with the Sun in the beam.
*Impact:* the margin near AOS and LOS is better than reality.

**A-RF-3 — Required Eb/N0 is supplied, not derived.**
Coding gain (CCSDS 130.1-G) and implementation loss are assumed already folded
into the figure the caller gives, unless listed separately.

**A-RF-4 — Unstated losses default to 0 dB.**
Deliberate: an invented "typical" value would hide inside the margin. A budget
with no declared losses flags itself as an optimistic upper bound in its
`assumptions[]`.

**A-RF-5 — Constant data rate.**
Adaptive coding and modulation are not modelled. A system that steps its rate
with elevation delivers more than Culmen predicts.

**A-DV-1 — Framing efficiency, acquisition and setup default to neutral.**
1.0, 0 s, 0 s. Same reasoning as A-RF-4: the optimistic bound is visible and
labelled, rather than a plausible guess that is invisible.

**A-DV-2 — Overhead is charged once, at the start of a contact.**
Re-acquisition after a dropout is not modelled.

**A-DV-3 — Gigabytes are decimal.**
1 GB = 10^9 bytes. Treating a mission's "2 GB" as GiB would inflate every
requirement by 7.4%.

**A-DV-4 — `accumulate` consumes contacts in the order given.**
It does not choose which passes to use. Ranking is Phase 9's job; putting a
policy decision inside an arithmetic helper would hide it.

## Contact validation (Phase 7)

**A-VAL-1 — Scheduling conflicts are not checked.**
Two contacts competing for the same antenna is Phase 9. Validating it here
would require the validator to know about other contacts, which is a
scheduler's concern.

**A-VAL-2 — The keyhole check is a coarse proxy.**
`antenna_keyhole` compares peak elevation against a declared maximum. It does
not compute the actual azimuth rate through the peak against a pedestal's slew
limit, so it can warn on a pass a fast mount could track, and stay silent on a
marginal one (see A-GEO-5).

**A-VAL-3 — Ground-station availability is not modelled.**
Maintenance windows and prior bookings are not represented.

**A-VAL-4 — An undeclared antenna band WARNs, it does not pass.**
Unknown is not the same as compatible. Silently passing an unchecked
constraint is how a planning tool becomes untrustworthy.

**A-VAL-5 — The verdict rule is blunt by design.**
Any FAIL gives INVALID; any WARN with no FAIL gives CONDITIONALLY_VALID. There
is no weighting or scoring: a weighted score would hide which constraint
actually bound, which is the opposite of this component's purpose.

## Scheduling (Phase 9)

**A-SCHED-1 — Greedy, single pass, no backtracking.**
The general problem is NP-hard. A contact taken early can block a better
combination later. The test suite contains a concrete case where the greedy
plan is beaten, asserted as a property so nobody mistakes the scheduler for an
optimiser.

**A-SCHED-2 — The ranking is a policy, stated not hidden.**
Priority, then deadline, then delivered volume, then AOS, then identity. Link
margin is deliberately excluded: it is a validity question, already settled.

**A-SCHED-3 — Two resources are modelled: antennas and satellites.**
Antennas carry turnaround on both sides; satellites are simple non-overlap.
Nothing else is a resource — no correlator, no operator, no network capacity.

**A-SCHED-4 — Ground-station availability windows are not modelled.**
Maintenance and prior third-party bookings are invisible to the scheduler.

**A-SCHED-5 — Satellite-side constraints are not modelled.**
Onboard storage, power, thermal duty cycle, and the fact that data must be
acquired before it can be downlinked.

**A-SCHED-6 — Contacts are taken whole or not at all.**
No partial contact, no splitting one around another.

**A-SCHED-7 — Cost plays no part.**
Commercial ground-station-as-a-service pricing is not represented.
