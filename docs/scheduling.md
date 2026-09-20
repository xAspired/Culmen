# Scheduling

**Implemented in:** `core/scheduling/scheduler.py`
**Tests:** `tests/test_scheduler.py`

## The problem, stated honestly

Choosing a set of non-overlapping contacts across several satellites, stations
and antennas that satisfies prioritised, deadline-bound data requirements is
interval scheduling with resource constraints. The general case is **NP-hard**.

Culmen does not ship a solver that looks optimal and is not. It ships a
greedy, deterministic, **explainable** scheduler, and says so in its output.

## Algorithm

1. Rank every candidate by a documented total ordering.
2. Walk the ranking once. Take a contact when its antenna is free (turnaround
   included) and it still contributes to an unmet requirement.
3. Record, for every contact **not** taken, the specific reason.

Step 3 is the point. A plan you cannot interrogate is a plan you cannot trust,
and "why was my pass dropped?" is the question an operator actually asks.
Every candidate ends up either in `scheduled` or in `rejected` with a reason —
pinned by a test.

## The ranking policy

Lower sorts first:

| # | Criterion | Why |
|---|---|---|
| 1 | `priority` | The operator's own ordering. Nothing computed may override an explicitly stated priority. |
| 2 | deadline, ascending | Earlier deadline is more urgent. No deadline sorts last. |
| 3 | delivered bytes, **descending** | Among equally urgent contacts, move the most data. This is the greedy step. |
| 4 | AOS, ascending | Earlier first: frees later antenna time, keeps the plan readable. |
| 5 | identity key | Makes the result byte-for-byte reproducible when everything above ties. |

Criterion 5 is not decoration. Without it, set or dict iteration order could
leak into the plan, and two runs on the same input could differ. A test
shuffles the candidate list twenty times and asserts the plan is identical.

### What is deliberately *not* in the ranking

**Link margin.** A contact closing at +3 dB and one closing at +20 dB deliver
the same bytes. Margin is a validity question, already settled by the
validator, not a ranking one. Ranking on it would quietly prefer
high-elevation passes even when a lower one does the job perfectly well.

## Rejection reasons

| Reason | Meaning |
|---|---|
| `INVALID` | the validator failed it (the failed check names are in the detail) |
| `ANTENNA_BUSY` | the antenna is already booked, turnaround included |
| `SATELLITE_BUSY` | the spacecraft is already downlinking in that window |
| `REQUIREMENT_ALREADY_MET` | earlier contacts already satisfied that requirement |
| `AFTER_DEADLINE` | the contact ends after the requirement's deadline |
| `DELIVERS_NOTHING` | the link never closes long enough to move data |

## Two resources, not one

The scheduler books **antennas and satellites**.

A spacecraft has one transmitter. Pointing two dishes at it receives the same
downlink twice; it does not double the data. Booking only antennas made the
scheduler assign the same pass to every free dish and report a requirement
satisfied that was not — found by running `examples/03_schedule.py`, not by
reasoning about the code, which is the usual way this class of bug surfaces.

Antenna bookings carry turnaround on both sides. Satellite bookings do not:
the constraint there is simple non-overlap, since nothing has to slew.

## Contacts that are individually insufficient

The validator answers *"can **this one contact** satisfy the requirement?"* and
correctly returns INVALID when a 3 GB requirement meets a 1.4 GB pass.

The scheduler must not treat that as disqualifying, because accumulating
across contacts is exactly its job. `ACCUMULABLE_FAILURES` names the checks
whose failure is forgiven — currently `data_capacity` alone. Every other
failure genuinely disqualifies: a link that does not close, a frequency the
antenna cannot receive, or a pass after the deadline is not made acceptable by
adding more of them. A contact failing *both* an accumulable and a real check
is still rejected.

Without this distinction any multi-pass requirement would be permanently
unsatisfiable: each contact rejected for being individually too small, and the
requirement then reported unmet.

## Turnaround

`turnaround_s` is the minimum gap the same antenna needs between contacts, and
it is charged on **both** sides: a dish needs time to slew away from one
satellite and onto the next, whichever order they come in.

The default is 0, which is unrealistic, so a schedule built with it carries a
note saying exactly that. Same principle as the RF and data-volume layers: the
optimistic default is visible and labelled, never a silent invented value.

## Greedy is not optimal, with a worked example

A single 1.2 GB contact overlaps two shorter 0.9 GB contacts. Greedy takes the
biggest one first and ends with 1.2 GB where 1.8 GB was available.

This is a **property, not a bug to hide**. `tests/test_scheduler.py` contains
exactly this case and asserts the suboptimal outcome, so nobody later mistakes
the scheduler for an optimiser. The rejection list is what lets an operator
see the trade and override it with priorities.

If a genuinely optimal plan is ever needed, the right move is an explicit
integer-programming formulation behind a separate entry point, so the cost
(solver dependency, runtime, non-obvious failure modes) is chosen rather than
inherited.

## Not modelled

- **Ground-station availability windows** — maintenance, prior bookings by
  other users.
- **Satellite-side constraints** — onboard storage, power, thermal duty cycle,
  the fact that data must be *acquired* before it can be downlinked.
- **Partial contacts** — a contact is taken whole or not at all; splitting one
  across the boundary of another is not considered.
- **Cost** — commercial ground-station-as-a-service pricing plays no part.
