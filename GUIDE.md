<img src="docs/images/icon-512.png" alt="Culmen" width="96" align="right">

# Culmen, explained from zero

*Italian version: [`GUIDE.it.md`](GUIDE.it.md) — versione italiana.*

This guide assumes **no background at all** — not in orbital mechanics, not in
radio, not in satellite operations. If you know what EIRP and G/T are, you
want [`docs/math/`](docs/math/) instead; this file is the other door.

Everything here is explained in the order the software itself computes it, so
by the end you will not only know what the words mean — you will know which
part of Culmen produces each number and where to look when one seems wrong.

**Contents**

1. [The problem in one page](#1-the-problem-in-one-page)
2. [Where is the satellite? — orbits and TLEs](#2-where-is-the-satellite--orbits-and-tles)
3. [Can I see it? — passes, azimuth, elevation](#3-can-i-see-it--passes-azimuth-elevation)
4. [Will the radio link work? — the link budget](#4-will-the-radio-link-work--the-link-budget)
5. [How much data fits? — data volume](#5-how-much-data-fits--data-volume)
6. [Which contact is best? — validation and scheduling](#6-which-contact-is-best--validation-and-scheduling)
7. [The glossary](#7-the-glossary)
8. [Why every number carries its own paperwork](#8-why-every-number-carries-its-own-paperwork)
9. [What Culmen deliberately is not](#9-what-culmen-deliberately-is-not)

---

## 1. The problem in one page

A satellite in low orbit circles the Earth roughly every 90 minutes. Your
ground station — a dish or an antenna bolted to a roof — sits in one place. The
satellite is only *reachable* when it is above your local horizon, which
happens a few times a day, for about ten minutes at a time.

When it is up there, four separate things have to be true before you actually
get your data:

1. **Geometry.** The satellite must be above the horizon, and high enough that
   buildings, hills and the antenna's own mechanical limits don't block it.
2. **Radio physics.** The signal must arrive strong enough, relative to the
   noise, for the receiver to decode it. This is not guaranteed by visibility:
   plenty of perfectly visible passes are radio-impossible.
3. **Time.** The link must stay good for long enough to move the data you have.
4. **Resources.** You have one antenna and possibly several satellites, all of
   which want it at overlapping times.

Culmen answers all four, and — this is its actual reason to exist — when the
answer is *no*, it tells you **which of the four failed, by how much, and what
would fix it**. Plenty of software will draw you a pass. Very little will tell
you that the pass was 4.2 dB short on margin and that a 4.5 m dish instead of a
3 m one would close it.

**One definition before anything else**, because half of this guide depends
on it:

> **dB (decibel).** A way of writing ratios that turns multiplication into
> addition. +3 dB means "about twice as much". +10 dB means "ten times as
> much". +20 dB is a hundred times, +30 dB a thousand. Minus signs mean
> division: −3 dB is half.
>
> Radio engineers use it because a signal is multiplied and divided by a dozen
> factors between the transmitter and the receiver — power, antenna focus,
> distance, rain — and the numbers involved span twenty orders of magnitude.
> In decibels, that whole chain becomes a column of numbers you add up. That
> column is the *link budget*, and it is literally why the word "budget" is
> used: it looks like accounting, because it is.

---

## 2. Where is the satellite? — orbits and TLEs

### 2.1 The input: a TLE

Satellite positions are published as a **TLE** — a *Two-Line Element set*. It
is exactly what the name says: two lines of 69 characters, a fixed-width format
from the 1960s that is still the universal currency of orbital data. A real one
looks like this:

```
ISS (ZARYA)
1 25544U 98067A   24015.50000000  .00016717  00000-0  30474-3 0  9993
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49309239432299
```

Every field means something (inclination, eccentricity, mean motion, drag), but
you do not need to read it by hand. What you *do* need to know is the three
things that bite people:

- **A TLE is a snapshot, and it goes stale.** It describes the orbit at one
  instant — its *epoch* — and the further you predict from that instant, the
  worse the answer. Culmen warns above **7 days** of age and refuses above
  **30**. In the example run below you will see `TLE age at AOS: +0.08 days`:
  that is a healthy TLE.
- **A TLE only works with the matching maths.** It is not a list of
  coordinates; it is a set of parameters for one specific algorithm, **SGP4**.
  Feed it to anything else and you get numbers that look fine and are wrong.
- **TLEs come from somewhere, with rules attached.** Culmen fetches them from
  [CelesTrak](https://celestrak.org/) via `scripts/fetch_tle.py`, which
  enforces a minimum 3-hour interval between fetches and identifies itself —
  because a public service that has to rate-limit you is a public service you
  are abusing. The downloaded files are **not** committed to this repository;
  see [`data/README.md`](data/README.md).

### 2.2 The propagator: SGP4

**SGP4** (*Simplified General Perturbations, model 4*) is the algorithm that
turns a TLE plus a time into a position and velocity. It accounts for the fact
that the Earth is not a point mass — it bulges at the equator, which slowly
rotates the orbit — and for atmospheric drag.

Culmen does not reimplement it. It uses the standard `sgp4` library and checks
it against the **official Vallado verification vectors**, the reference test
case the algorithm's own maintainers publish. Culmen agrees with them to
**2 × 10⁻⁷ km** — 0.2 millimetres. That is not a number to brag about; it is
the number that proves the wiring is right, because getting a frame or a time
scale wrong produces errors of *kilometres*, not millimetres.

### 2.3 The trap that catches everyone: reference frames

This is the single most common source of silently wrong answers in this
domain, so it gets its own section.

A position is meaningless without saying *what it is measured against*. There
are three frames in play:

| Frame | Fixed relative to | Used for |
|---|---|---|
| **TEME** | the stars (roughly) | what SGP4 outputs |
| **ITRF / ECEF** | the rotating Earth | where your ground station is |
| **Geodetic** | — | latitude, longitude, altitude |

**SGP4 gives you TEME.** TEME is *True Equator, Mean Equinox* — an
inertial-ish frame that does **not** rotate with the Earth. Your ground station
is in Padova, which *does* rotate with the Earth, at about 465 m/s at the
equator. Subtract one from the other without converting and your satellite
appears to be in the wrong place by hundreds of kilometres, in a way that looks
plausible enough to ship.

Worse, TEME is also **not** J2000 — the other common inertial frame — despite
being nearly identical to it. The difference is small enough to pass a casual
sanity check and large enough to ruin a pass prediction.

Culmen converts TEME → ITRF explicitly, using Earth rotation angle and polar
motion, and [`docs/math/sgp4-and-teme.md`](docs/math/sgp4-and-teme.md) writes
out the conversion. **If you take one thing from this guide, take this one.**

### 2.4 The other trap: what "latitude" means

There are two latitudes, and they are not the same number.

- **Geocentric latitude** is the angle from the equator to a line drawn to the
  centre of the Earth.
- **Geodetic latitude** — the one on every map, GPS and station datasheet — is
  the angle from the equator to the *local vertical*, the direction a plumb
  line hangs.

They differ because the Earth is an ellipsoid, squashed by about one part in
298. At mid-latitudes the gap reaches **0.19°**, which on the ground is about
**21 km**. Point an antenna with the wrong one and a narrow beam misses
entirely. Culmen uses **WGS84 geodetic** throughout — the GPS standard — and
converts with Bowring's method
([`docs/math/geodetic.md`](docs/math/geodetic.md)).

### 2.5 And time is not simple either

Three complications, all of which Culmen handles and all of which are worth
knowing about:

- **UTC is discontinuous.** It occasionally inserts a *leap second* to stay in
  step with the Earth's slightly irregular rotation. Subtracting two UTC
  timestamps across one gives an answer that is one second wrong. Internally
  Culmen works in continuous time scales and only presents UTC.
- **Floating-point precision runs out.** A Julian Date today is about
  2 460 000. A 64-bit float at that magnitude resolves about **40
  microseconds** — and the satellite moves 30 cm in that time. Culmen carries
  dates as **two numbers** (whole days + fraction), which is standard practice
  and not optional.
- **Naive timestamps are refused.** A datetime without a timezone is an
  ambiguity waiting to become a bug, so Culmen raises rather than guessing UTC.

---

## 3. Can I see it? — passes, azimuth, elevation

### 3.1 The vocabulary

A **pass** is one continuous period during which the satellite is above your
station's horizon. It is described by:

| Term | Meaning |
|---|---|
| **AOS** | *Acquisition of Signal* — the pass starts |
| **LOS** | *Loss of Signal* — the pass ends |
| **Azimuth** | compass direction to the satellite: 0° = North, 90° = East, 180° = South, 270° = West |
| **Elevation** | angle above the horizon: 0° = on the horizon, 90° = straight overhead |
| **Culmination** | the moment of maximum elevation — the highest point of the pass |
| **Range** | straight-line distance to the satellite, in km |
| **Range rate** | how fast that distance is changing; negative = approaching |

> The project is named after **culmination** — the highest point of a pass, the
> moment everything is at its best. `Culmen` is the Latin word.

Azimuth and elevation together are the **look angles**: exactly the two numbers
you would dial into a rotator to point at the thing. Computing them means
converting the satellite's Earth-fixed position into a local **ENU** frame
(East-North-Up) centred on your station, which is the topocentric reduction in
[`docs/math/topocentric.md`](docs/math/topocentric.md).

### 3.2 A real pass, from the bundled example data

This is genuine output from `python examples/01_passes.py`, for the ISS over
Padova:

```
Padova: 3 pass(es) for NORAD 28057

Highest pass: 2006-06-26 20:40:09Z -> 20:50:25Z, 10.3 min, peak 82.8 deg
TLE age at AOS: +0.08 days

  time        az      el    range_km   range_rate_km_s
  20:40:09   161.3   10.0     2316.6     -6.627
  20:42:01   160.1   23.1     1593.9     -6.177
  20:43:53   155.3   49.9      982.2     -4.280
  20:44:49   138.5   73.8      808.2     -1.680
  20:45:45     8.6   72.7      812.8     +1.837
  20:47:37   350.1   33.3     1277.4     +5.609
  20:50:25   347.8   10.0     2333.0     +6.623
```

Read it and the physics falls out:

- The satellite **rises in the south-southeast** (az 161°) and **sets in the
  north-northwest** (az 348°). One pass, one sweep across the sky.
- **Range varies by a factor of nearly three** — 2317 km at the horizon, 808 km
  overhead. Hold that thought; section 4 is entirely about what that costs you.
- **Range rate flips sign at culmination**, from −6.6 km/s (approaching) to
  +6.6 km/s (receding). That sign change *is* the culmination, and it is what
  the pass finder actually solves for.
- **Azimuth swings 130° in under two minutes** around the peak. A high pass
  looks ideal and is mechanically brutal: this is where rotators lose track.
- The pass starts and ends at exactly **10.0°** because that is Padova's
  configured minimum elevation, not because the satellite appeared there.

### 3.3 How Culmen finds passes (and the bug that taught us to test it)

Finding AOS and LOS means finding where elevation crosses your threshold, and
finding culmination means finding where its derivative is zero. Culmen samples
coarsely, then refines with a root-finder (Brent) for the crossings and a
bounded search for the peak.

There is a real trap here, and it bit this project. Numerical solvers use
tolerances that are partly *relative* to the magnitude of the input. Feed one a
Julian Date of 2 460 000 and the relative tolerance works out to about **0.04
days — an hour**, which is longer than the entire pass. The solver returned
after a single iteration, reported **success**, and gave peak elevations up to
**17° too low**.

The fix: refine in **seconds relative to the start of the window**, never in
absolute dates. The test that caught it —
`test_reported_maximum_is_the_real_maximum` — brute-forces the true maximum and
compares. It is in the suite permanently.

That is the flavour of this whole project: the dangerous bugs are not crashes,
they are plausible wrong numbers.

### 3.4 The horizon is not flat

Real stations have trees, buildings and hills. Culmen supports a **horizon
profile**: a minimum elevation per azimuth sector, so you can say "10°
everywhere, except 25° to the northeast where the building is". A pass that is
geometrically visible but blocked by that profile is reported as blocked, not
as usable.

Two simplifications are declared rather than hidden: elevations are
**geometric**, with no atmospheric refraction model (refraction lifts objects
near the horizon by roughly half a degree), and the horizon profile is a step
function between sectors.

---

## 4. Will the radio link work? — the link budget

Geometry says the satellite is up there. This section asks whether you can
actually hear it. The answer is a single number called **margin**, and
everything below is the arithmetic that leads to it.

### 4.1 The chain, in words

Power leaves the satellite's transmitter. Its antenna concentrates it in your
direction. It spreads out over the distance. A little is absorbed by the
atmosphere and, if it is raining, quite a lot more. Your antenna collects some
of it. Your receiver adds noise of its own. What matters at the end is not how
much signal arrived — it is **how much signal arrived compared to the noise**.

### 4.2 Term by term

**EIRP — Effective Isotropic Radiated Power**, in dBW.

> How strong the transmission is *in your direction*. It is the transmitter's
> power plus the antenna's gain, minus losses in the cabling.
>
> "Isotropic" means "radiating equally in all directions" — the imaginary
> reference antenna that everything is compared against. EIRP answers: *how
> powerful would a bare isotropic radiator have to be, to put this much signal
> where I'm standing?*
>
> `EIRP_dBW = transmit_power_dBW + antenna_gain_dBi − losses_dB`

**Antenna gain**, in dBi.

> An antenna does not create power; it *focuses* it, like a torch reflector.
> Gain is how much more signal you get in the favoured direction than an
> isotropic radiator would give — hence the "i" in **dBi**.
>
> For a parabolic dish it depends on the dish area, the wavelength and an
> efficiency factor (typically 0.5–0.7, because no dish is perfectly
> illuminated):
>
> `G_dBi = 10·log₁₀(η · (π·D/λ)²)`
>
> A 3 m dish at 8.2 GHz with 60% efficiency gives **46.0 dBi** — about 40 000×
> concentration. Bigger dish or higher frequency means more gain, and also a
> narrower beam, which is why big dishes need good pointing.
>
> Watch out for **dBd**, an older unit referenced to a dipole rather than an
> isotropic radiator: `dBi = dBd + 2.15`. Mixing them costs you 2.15 dB of
> imaginary margin.

**FSPL — Free-Space Path Loss**, in dB.

> The big one. Signal spreads over the surface of an expanding sphere, so the
> power density falls as the square of distance. In practical units:
>
> `FSPL_dB = 32.4478 + 20·log₁₀(distance_km) + 20·log₁₀(frequency_MHz)`
>
> For our ISS pass at 8.2 GHz: **178.0 dB at the horizon** (2317 km) versus
> **166.3 dB at 600 km**. That is a **12 dB swing** — a factor of 16 in
> received power — *within a single ten-minute pass*.
>
> This is why Culmen computes the budget **along the pass** rather than once.
> A budget evaluated only at culmination will tell you a link works that in
> fact drops out at both ends.

**Atmospheric and rain attenuation**, in dB.

> The air absorbs radio energy — mostly oxygen and water vapour — and rain
> absorbs a great deal more. Both get worse at low elevation, because a
> shallower path spends longer in the atmosphere.
>
> The two are **not** of the same size, and confusing them is a genuine
> mistake this project made and corrected. For Padova at 8.2 GHz and 10°
> elevation:
>
> | | |
> |---|---|
> | Gaseous absorption (ITU-R P.676) | **0.26 dB** |
> | Rain (ITU-R P.618, 0.01% of a year) | **5.55 dB** |
>
> Gas is a rounding error at X-band. **Rain is what eats your margin.** At
> 20 GHz the same rain costs about **39 dB**, which is the entire reason
> X-band downlinks still exist.
>
> Rain attenuation is a *statistic*, not a value: "0.01% exceedance" means
> "this much or worse, 0.01% of an average year" — i.e. 99.99% availability.
> The number changes by several dB between 0.1% and 0.001%, so **a margin
> quoted without its availability target is not a margin**. Culmen returns the
> percentage alongside the figure, every time.

**G/T — Gain over Temperature**, in dB/K.

> The single figure of merit for a receiving station: how much it focuses,
> divided by how much noise it adds. Two stations with the same dish can differ
> by 10 dB here if one has a cold, quiet amplifier and the other doesn't.
>
> `G/T = antenna_gain_dBi − 10·log₁₀(system_noise_temperature_K)`
>
> "Temperature" is not the weather. Noise power is proportional to an
> equivalent temperature, so engineers quote noise *as* a temperature in
> kelvin — the sum of the sky, the ground the antenna partly sees, the
> amplifier and the cabling. It rises steeply at low elevation, because a
> low-pointing antenna sees warm ground. (Culmen currently treats it as
> constant and says so: assumption A-RF-2.)

**C/N₀ — Carrier to Noise-density ratio**, in dB-Hz.

> Everything above, combined into one number:
>
> `C/N₀ = EIRP − FSPL − other_losses + G/T − k`
>
> where `k` is **Boltzmann's constant**, −228.6 dBW/(Hz·K), a constant of
> nature that converts a temperature into a noise power. The odd unit dB-Hz is
> because this is a ratio *per hertz of bandwidth*.

**Eb/N₀ — Energy per bit over noise density**, in dB.

> C/N₀ describes the channel. Eb/N₀ describes whether your *data* survives it,
> and it is the number receivers are actually specified against:
>
> `Eb/N₀ = C/N₀ − 10·log₁₀(data_rate_bps)`
>
> Doubling your data rate costs exactly 3 dB. That is the fundamental trade of
> the whole field: **speed versus reach**.

**Margin**, in dB. The answer.

> `Margin = Eb/N₀_achieved − Eb/N₀_required`
>
> Positive means the link closes. Negative means it does not. A few dB of
> margin is prudent; zero is a coin flip, because every input has uncertainty.

### 4.3 The whole thing, with real numbers

A 20 W X-band downlink (13 dBW), 12 dBi satellite antenna, 25 Mbps, into a 3 m
dish with a 150 K system, requiring 4 dB Eb/N₀. These are real outputs from
Culmen's own code:

| | at 600 km (high) | at 2000 km (low) |
|---|---|---|
| FSPL | 166.29 dB | 176.74 dB |
| C/N₀ | 111.19 dB-Hz | 100.73 dB-Hz |
| Eb/N₀ | 37.21 dB | 26.75 dB |
| **Margin** | **+33.21 dB** | **+22.75 dB** |

Both close comfortably — and the *same link* is 10.5 dB better at the top of
the pass than at the edges, purely from distance. Now subtract the 5.8 dB of
atmosphere from section 4.2 at that low elevation, and a link with thinner
margins starts failing exactly where it looked fine on paper.

### 4.4 Which is verified against what

The link budget is checked against a **published ITU-R workshop case**. It
agrees to within **0.2 dB**, and that 0.2 dB is a documented inconsistency *in
the published source* which this project did **not** paper over by widening the
tolerance. That decision is in [`CONTRIBUTING.md`](CONTRIBUTING.md), because it
is the house style: a discrepancy you can explain is worth more than a green
test you cannot.

---

## 5. How much data fits? — data volume

Now the simple part, which is simple only because the hard parts came first.

You know when the link closes and when it stops closing. The **closing
interval** is the portion of the pass where margin is positive — which may be
shorter than the pass itself, and that difference is the point.

```
usable_seconds = closing_interval − acquisition_time − setup_time
bits           = usable_seconds × data_rate × framing_efficiency
```

- **Acquisition time**: the receiver needs a moment to lock onto the carrier
  and achieve bit synchronisation. It is not free.
- **Framing efficiency**: not every transmitted bit is your data. Protocol
  framing, error-correcting codes and synchronisation markers all consume
  capacity. A CCSDS frame with Reed-Solomon coding might deliver ~92% payload.
  Culmen makes you state this rather than assuming 100%.

For the real ISS pass above — 618 seconds, minus 20 s acquisition and 10 s
setup, at 25 Mbps with 92% framing:

```
588 s × 25 000 000 bit/s × 0.92 = 13.52 Gbit = 1.69 GB
```

Note **GB = 10⁹ bytes**, decimal, as used throughout telecommunications — not
2³⁰. Mixing the two is a 7% error, which is exactly the size of the effect
people go looking for when a downlink "underperforms".

Culmen also inverts the calculation: given a volume you must move, how many
seconds of contact do you need? That is what turns "the pass is 10 minutes
long" into "you need three passes".

**Honesty note:** unlike SGP4 and the link budget, there is no external
reference case to verify data volume against — it depends entirely on a
specific ground system. The test module says so in its own docstring and pins
mathematical properties and inverse consistency instead. Where Culmen cannot
verify against the world, it says so.

---

## 6. Which contact is best? — validation and scheduling

### 6.1 The Contact Validator

This is the component the whole project exists for. It takes a candidate
contact and runs every check independently, and each returns **PASS**,
**FAIL**, **WARN** or **SKIPPED** — with its expected value, its actual value,
and the gap:

- is the peak elevation above the mission minimum?
- is the contact long enough?
- does the link close, with enough margin?
- can the antenna mechanically track it (slew rate, keyhole, limits)?
- can the required data volume actually fit?
- is the TLE fresh enough to trust this prediction?

The checks combine into a verdict — **VALID**, **CONDITIONALLY_VALID** or
**INVALID** — and, crucially, into **suggestions derived from the check that
failed**. Not generic advice: if the margin check failed by 4.2 dB, the
suggestion is computed from that 4.2 dB.

`SKIPPED` deserves emphasis. If you did not supply antenna slew limits, the
slew check does not quietly pass — it reports that it could not run. A verdict
that looks validated but silently skipped half its checks is the exact failure
mode this project is built to prevent.

### 6.2 The scheduler

You have several satellites, one or two antennas, and overlapping passes.
Assigning them optimally is an NP-hard problem in general, so Culmen uses a
**greedy** algorithm: rank the candidates, take the best one that still fits,
repeat.

Two properties matter more than optimality:

- **It is deterministic.** Ranking uses a total order with an identity
  tie-break, so the same inputs always produce the same schedule. A planner
  that reshuffles between runs is unusable regardless of how good its answers
  are.
- **It is honest about being suboptimal.** Assumption A-SCHED-1 says so, and a
  test *demonstrates a case where greedy is beaten*. Culmen ships with a
  failing-by-design example of its own weakness.

The scheduler books both the antenna **and** the satellite as resources. That
sounds obvious; it was a real bug, found by running
`examples/03_schedule.py` and noticing one satellite booked onto two antennas
at the same instant, double-counting its data.

---

## 7. The glossary

| Term | Expansion | In one line |
|---|---|---|
| **AOS / LOS** | Acquisition / Loss of Signal | The start and end of a pass |
| **Azimuth** | — | Compass bearing to the satellite (0° = North) |
| **C/N₀** | Carrier to Noise-density | Signal quality of the channel, dB-Hz |
| **CCSDS** | Consultative Committee for Space Data Systems | The body that standardises space data protocols |
| **dB** | Decibel | Ratios as additions; +3 dB ≈ double, +10 dB = ×10 |
| **dBi / dBd** | — | Antenna gain vs isotropic / vs dipole; `dBi = dBd + 2.15` |
| **dBW / dBm** | — | Power vs 1 watt / vs 1 milliwatt |
| **Eb/N₀** | Energy per bit / noise density | Whether your *data* survives; what receivers are specified in |
| **ECEF / ITRF** | Earth-Centred Earth-Fixed | Frame that rotates with the Earth |
| **EIRP** | Effective Isotropic Radiated Power | How strong the transmission is in your direction |
| **Elevation** | — | Angle above the horizon; 90° = overhead |
| **ENU** | East-North-Up | Local frame centred on your station |
| **FSPL** | Free-Space Path Loss | Loss from distance alone; the dominant term |
| **Geodetic latitude** | — | Map/GPS latitude, from the local vertical |
| **G/T** | Gain over Temperature | A receiving station's figure of merit, dB/K |
| **ITU-R** | International Telecommunication Union, Radiocommunication Sector | Publishes the propagation models (P.676, P.618, P.372) |
| **Keyhole** | — | The blind cone overhead where an az/el mount cannot slew fast enough |
| **LEO** | Low Earth Orbit | ~200–2000 km; ~90 min per orbit |
| **NORAD ID** | — | The five-digit catalogue number of an object |
| **Pass** | — | One continuous period above the horizon |
| **Range rate** | — | Rate of change of distance; drives Doppler shift |
| **SGP4** | Simplified General Perturbations 4 | The algorithm a TLE is made for |
| **TEME** | True Equator, Mean Equinox | SGP4's output frame — neither J2000 nor Earth-fixed |
| **TLE** | Two-Line Element set | The 1960s format satellite orbits are published in |
| **UTC / TAI / TT / UT1** | — | Time scales; only UTC has leap seconds |
| **WGS84** | World Geodetic System 1984 | The ellipsoid GPS uses; Culmen's reference |
| **X-band / Ka-band** | — | ~8 GHz / ~20–30 GHz; Ka is faster and far more rain-sensitive |

---

## 8. Why every number carries its own paperwork

Every computed quantity in Culmen is a `Computed` object carrying, alongside
the value: its **unit**, a **reference** to the documented formula, the
**inputs** it was derived from, and the **assumptions** it rests on.

This is not bureaucracy. If a tool tells you a contact will work and it does
not, the only useful question is *which step was wrong* — and you cannot answer
that from a bare number. Every API response carries this trail, which is why
bug reports for this project can simply paste it.

Three house rules follow from the same instinct, and they are enforced by tests
that fail the build:

- **Units live in names.** `range_km`, `freq_hz`, `power_dbw`. A test parses
  every data structure and rejects a numeric field without a unit suffix. It
  has caught the author's own naming more than once.
- **Every formula reference must resolve.** A test checks that every citation
  points at a document that exists. An audit trail citing a missing note is
  worse than none.
- **Every simplification is numbered and declared.**
  [`docs/math/assumptions.md`](docs/math/assumptions.md) lists them all —
  A-GEO-3 for refraction, A-RF-2 for noise temperature, A-SCHED-1 for greedy
  scheduling. Entries are never deleted, only amended with the phase that
  removed them, so the history of what was once wrong stays readable.

And one rule above the rest, from [`CONTRIBUTING.md`](CONTRIBUTING.md):

> **A number without an external reference is not verified**, and **never
> invent a number to make something work**. A plausible default for an
> atmospheric loss, a station coordinate from memory, a tolerance widened until
> green — each is worse than an obvious gap, because it is invisible.

---

## 9. What Culmen deliberately is not

- **Not a satellite tracker.** It does not do real-time "where is it now"; it
  answers planning questions about the future.
- **Not antenna or radio control.** It computes; it does not point anything and
  it does not key a transmitter. It is an **analysis** tool.
- **Not a transmitter, and not a licence.** The fact that a frequency is
  publicly documented is *never* authorisation to transmit on it. Licensing is
  a legal matter between you and your national regulator, and nothing this
  software outputs changes that.
- **Not AI, anywhere in the product.** No model, no inference, no learned
  heuristic. Every output is a deterministic function of its inputs: the same
  inputs and the same engine version produce the same numbers, forever. That is
  [ADR 0007](docs/adr/0007-no-ai-in-the-product.md), and for a tool whose job
  is a traceable verdict it is not a limitation — it is the requirement.
- **Not a fetcher on your behalf.** The API never downloads catalogue data
  silently. Respecting a data provider's rate limits, licence and attribution
  is the operator's responsibility, and hiding that from them would be the
  wrong favour.

---

## Where to go next

| You want | Read |
|---|---|
| To run it | [`README.md`](README.md) — one command |
| The actual maths, with sources | [`docs/math/`](docs/math/) |
| Why the project is shaped this way | [`docs/adr/`](docs/adr/) — ten decisions, with the rejected alternatives |
| Every declared simplification | [`docs/math/assumptions.md`](docs/math/assumptions.md) |
| To add your own station or satellites | [`data/README.md`](data/README.md) |
| To contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
