# Achievable data volume

**Implemented in:** `core/datavol/volume.py`
**Tests:** `tests/test_data_volume.py`

## The formula that is wrong

```
bytes = data_rate × pass_duration          ← overstates capacity, always
```

It ignores four real subtractions, and all four go the same way.

## The formula used

```
closing_s = Σ intervals where link margin ≥ 0
usable_s  = max(0, closing_s − setup_s − acquisition_s)
bytes     = data_rate_bps × usable_s × framing_efficiency / 8
```

| Term | Meaning | Unit | Default |
|---|---|---|---|
| `closing_s` | interval where the link actually closes | s | from the sampled budget |
| `setup_s` | antenna slew and configuration | s | 0 |
| `acquisition_s` | carrier, symbol and frame lock | s | 0 |
| `framing_efficiency` | delivered bytes per channel byte | — | 1.0 |
| `data_rate_bps` | **information** bit rate | bit/s | required |

## Why each term exists

**Closing interval, not AOS-to-LOS.** Free-space loss at the horizon is 8–13 dB
worse than at the peak for a LEO pass. A link sized for mid-pass does not close
at the edges. `compute_data_volume` therefore takes a `PassLinkBudget`, not a
duration: it is not possible to call it with a peak-only figure by accident.

The interval is integrated trapezoidally between samples rather than by
counting samples, so the answer does not depend on the sampling step — pinned
by comparing an 11-point and a 201-point sampling of the same pass.

**Acquisition.** Carrier lock, symbol lock and frame sync take tens of seconds
after the link first closes. Typically 30–60 s for a CubeSat ground system,
but it is a property of the specific receiver, so there is no default.

**Setup and slew.** Consumed before the contact starts.

**Framing efficiency.** The channel rate is not the delivered information rate:
CCSDS framing, Reed–Solomon parity, attached sync markers and retransmission
all take a share. CCSDS 131.0-B and 132.0-B are the references for the frame
structures; 130.1-G for coding.

## Every default is neutral, on purpose

`framing_efficiency = 1.0`, `acquisition_s = 0`, `setup_s = 0`. An unstated
overhead surfaces as an optimistic number the user can see and challenge,
never as a plausible-looking invented one. A neutral profile is explicitly
flagged in `assumptions[]` as *an optimistic upper bound, not an expected
delivery*.

## Gigabytes are decimal

`1 GB = 10⁹ bytes`, not 2³⁰. A mission requirement quoted as "2 GB" means
2 × 10⁹ bytes; treating it as GiB would silently inflate every requirement by
7.4%.

## Inverse

`required_contact_seconds` answers "how long a contact do I need?" and returns
a required **closing** interval with overhead already added back. It inverts
`compute_data_volume` exactly; pinned by a round-trip test.

Worked case: 2 GB at 25 Mbit/s, 85% efficiency, 75 s overhead →
`2e9 × 8 / (25e6 × 0.85) = 752.94 s`, plus 75 s = **827.94 s**.
Ignoring the overheads gives 640 s — a 188 s underestimate, which is the
difference between a plan that works and one that does not.

## Limits of validity

- **Constant rate.** Adaptive coding and modulation are not modelled. A system
  that steps its rate with elevation will deliver more than this predicts.
- **One uninterrupted contact.** Splitting a requirement across passes is
  `accumulate`, which consumes contacts in the order given. It does **not**
  choose which passes to use: ranking is the scheduler's job (Phase 9), and
  burying a policy decision inside an arithmetic helper would hide it.
- **No retransmission model.** Losses due to ARQ are expected to be folded
  into `framing_efficiency` by the user.

## Verification approach

There is no published reference case for this layer the way there is for SGP4
or the link budget — achievable volume depends on a specific ground system's
overheads. The tests therefore pin properties and inverse consistency instead:
strict reduction versus the naive figure, exact round-trip through the
inverse, independence from sampling density, and attribution of every
reduction to a named cause. Stated plainly rather than dressed up as
verification against an authority that does not exist.
