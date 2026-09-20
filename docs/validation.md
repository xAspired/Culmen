# The Contact Validator

**Implemented in:** `core/validation/contact.py`
**Tests:** `tests/test_contact_validator.py`
**Decision record:** [ADR 0006](adr/0006-explainable-verdicts-as-the-core-product.md)

This is the component Culmen exists for. Everything beneath it computes
numbers; this turns them into a decision that can be acted on and argued with.

## Verdicts

| Verdict | Rule |
|---|---|
| `VALID` | every check passed |
| `CONDITIONALLY_VALID` | nothing failed, but at least one check warned |
| `INVALID` | at least one check failed |

`SKIPPED` never changes the verdict on its own, but is always reported. A
check that could not run is information, not silence.

## Check catalogue

Checks run cheapest-and-most-fundamental first. A failure that makes later
checks meaningless marks them `SKIPPED` rather than inventing a result: if the
satellite is never visible, "link margin: FAIL" is noise.

| Check | Fails when | Warns when |
|---|---|---|
| `satellite_visibility` | no pass above the mask | — |
| `minimum_elevation` | peak below the mount's mechanical limit | — |
| `antenna_keyhole` | — | peak above the mount's trackable elevation |
| `frequency_compatibility` | transmit frequency outside the antenna's band | the antenna declares no band |
| `tle_freshness` | element set > 30 days from epoch | > 7 days |
| `link_margin` | **worst-case** margin below the requirement | — |
| `data_capacity` | delivered bytes below the requirement | — |
| `deadline` | contact ends after the deadline | — |

### Two of these deserve emphasis

**`link_margin` uses the worst case along the pass, never the peak.** Free-space
loss at the horizon is 8–13 dB worse than at maximum elevation. Validating at
the peak would pass a link that does not close at the edges of the very pass
being validated. A test pins this by choosing a threshold between the
worst-case and best-case margin and asserting the verdict is INVALID.

**`frequency_compatibility` warns rather than passes when no band is declared.**
Unknown is not the same as compatible. Silently passing an unchecked
constraint is how a tool becomes untrustworthy.

## Suggestions

Rule-derived from the check that actually failed, and each one carries a
number taken from *this* contact. There is no fixed list printed regardless of
the failure, and nothing is generated (ADR 0007).

A real INVALID verdict:

```
INVALID
  satellite_visibility     PASS     pass of 10.0 min above the mask  [expected > 0 s, actual 600.0 s]
  minimum_elevation        PASS     peak elevation 47.3 deg clears the limit
  antenna_keyhole          PASS     pass stays below the mount's keyhole
  frequency_compatibility  PASS     transmit frequency is inside the antenna's receive band
  tle_freshness            PASS     element set is 0.5 days from epoch
  link_margin              FAIL     worst-case margin across the pass, at 2300 km slant range
                                    [expected +40.0 dB, actual +20.9 dB]
  data_capacity            FAIL     short by 97.605 GB  [expected 99.000 GB, actual 1.395 GB]
  deadline                 SKIPPED  requirement declares no deadline

Suggested alternatives:
  - reduce the data rate: a 19.1 dB deficit is recovered by dividing the rate by 81.09
  - raise the elevation mask: the worst case is at 2300 km slant range; the best sample has +34.2 dB
  - increase antenna gain: 19.1 dB needs the dish diameter multiplied by 9.00
  - use another ground station: one with a higher G/T, or a better view of this orbit
  - use additional passes: this contact delivers 1.395 GB; about 71 contacts would be needed
  - choose a higher-elevation pass: short by 97.605 GB
  - reduce the acquisition or setup time: overhead currently costs 75 s of this contact
```

The dish-diameter and rate-divisor figures are derived from the deficit
(`10^(Δ/20)` and `10^(Δ/10)` respectively), not looked up from a table of
generic advice.

## Provenance

A validation carries the assumptions of every layer it rests on — the RF
reference-plane caveat, the information-rate caveat from the data-volume
layer, and any warnings attached to the pass itself. It also records
`engine_version`, so a cached verdict can be invalidated when the engine
changes (ADR 0006).

## Not checked in V1

- **Scheduling conflicts.** Two contacts competing for one antenna is Phase 9;
  putting it here would mean the validator needs to know about other contacts,
  which is a scheduler's job.
- **Slew feasibility in detail.** The keyhole check is a coarse proxy; the
  actual azimuth rate through the peak is not computed against a pedestal's
  rate limit.
- **Sun in the beam**, which raises antenna noise temperature (A-GEO-6).
- **Ground station availability windows** (maintenance, prior bookings).
