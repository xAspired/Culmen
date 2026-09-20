"""Deterministic contact scheduling.

The problem — choosing a set of non-overlapping contacts across several
satellites, stations and antennas that satisfies a set of prioritised,
deadline-bound data requirements — is a form of interval scheduling with
resource constraints, and the general case is NP-hard. Culmen does **not**
pretend otherwise and does not ship a solver that looks optimal and is not.

What it ships is a **greedy, deterministic, explainable** scheduler:

1. Rank every candidate contact by a documented, total ordering.
2. Walk the ranking once. Take a contact if its antenna is free (including
   turnaround time) and it still contributes to an unmet requirement.
3. Record, for every contact **not** taken, the specific reason.

That last point is what makes it useful rather than merely fast. A schedule
you cannot interrogate is a schedule you cannot trust, and "why was my pass
dropped?" is the question an operator actually asks.

Greedy is not optimal. A better plan may exist; the ranking is a policy, and
it is stated rather than hidden inside a solver. See docs/scheduling.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from core.datavol.volume import BYTES_PER_GIGABYTE, DataVolume
from core.passes.finder import Pass
from core.time.scales import ensure_utc, seconds_between
from core.validation.contact import ContactValidation, MissionRequirement, Verdict

SCHEDULER_VERSION = "culmen-greedy/1"

#: Checks whose failure does NOT disqualify a contact from being scheduled.
#:
#: The validator asks "can **this one contact** satisfy the requirement?" and
#: correctly answers INVALID when a 3 GB requirement meets a 1.4 GB pass. But
#: accumulating across several contacts is precisely the scheduler's job, so
#: treating that verdict as disqualifying would make any multi-pass requirement
#: permanently unsatisfiable -- the scheduler would reject every contact for
#: being individually insufficient and then report the requirement as unmet.
#:
#: Every other failure is genuinely disqualifying: a link that does not close,
#: a frequency the antenna cannot receive or a pass after the deadline is not
#: made acceptable by adding more of them.
ACCUMULABLE_FAILURES: frozenset[str] = frozenset({"data_capacity"})


class Rejection(StrEnum):
    """Why a candidate did not make it into the schedule."""

    INVALID = "INVALID"
    ANTENNA_BUSY = "ANTENNA_BUSY"
    SATELLITE_BUSY = "SATELLITE_BUSY"
    REQUIREMENT_ALREADY_MET = "REQUIREMENT_ALREADY_MET"
    AFTER_DEADLINE = "AFTER_DEADLINE"
    DELIVERS_NOTHING = "DELIVERS_NOTHING"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One possible contact: a pass, on an antenna, evaluated end to end."""

    pass_: Pass
    antenna_id: str
    validation: ContactValidation
    volume: DataVolume
    requirement: MissionRequirement
    priority: int = 0
    """Lower number means more important. Ties are broken deterministically."""

    @property
    def delivered_bytes(self) -> float:
        return self.volume.delivered_bytes.value

    @property
    def key(self) -> str:
        """Stable identity, used as the final tie-break."""
        return (
            f"{self.requirement.name}|{self.pass_.satellite_norad_id}|"
            f"{self.pass_.station_name}|{self.antenna_id}|"
            f"{self.pass_.aos_utc.isoformat()}"
        )


@dataclass(frozen=True, slots=True)
class ScheduledContact:
    """A candidate that was accepted, with its position in the plan."""

    candidate: Candidate
    rank: int
    cumulative_bytes: float
    """Bytes delivered for this requirement, including this contact."""


@dataclass(frozen=True, slots=True)
class RejectedContact:
    candidate: Candidate
    reason: Rejection
    detail: str


@dataclass(frozen=True, slots=True)
class RequirementStatus:
    requirement: MissionRequirement
    delivered_bytes: float
    satisfied: bool
    contact_count: int

    @property
    def shortfall_bytes(self) -> float:
        return max(0.0, self.requirement.required_bytes - self.delivered_bytes)

    @property
    def delivered_gigabytes(self) -> float:
        return self.delivered_bytes / BYTES_PER_GIGABYTE


@dataclass(frozen=True, slots=True)
class Schedule:
    """The plan, and the full account of what was left out and why."""

    scheduled: tuple[ScheduledContact, ...]
    rejected: tuple[RejectedContact, ...]
    requirements: tuple[RequirementStatus, ...]
    scheduler_version: str = SCHEDULER_VERSION
    notes: tuple[str, ...] = field(default=())

    @property
    def all_satisfied(self) -> bool:
        return all(r.satisfied for r in self.requirements)

    def for_antenna(self, antenna_id: str) -> tuple[ScheduledContact, ...]:
        return tuple(s for s in self.scheduled if s.candidate.antenna_id == antenna_id)

    def rejections_for(self, reason: Rejection) -> tuple[RejectedContact, ...]:
        return tuple(r for r in self.rejected if r.reason is reason)

    def report(self) -> str:
        lines: list[str] = ["SCHEDULE"]
        if not self.scheduled:
            lines.append("  (nothing scheduled)")
        for s in self.scheduled:
            c = s.candidate
            lines.append(
                f"  #{s.rank:<2} {c.pass_.aos_utc:%d %b %H:%M:%S}Z -> "
                f"{c.pass_.los_utc:%H:%M:%S}Z  "
                f"NORAD {c.pass_.satellite_norad_id}  "
                f"{c.pass_.station_name}/{c.antenna_id}  "
                f"el {c.pass_.max_elevation_deg:5.1f} deg  "
                f"{c.delivered_bytes / BYTES_PER_GIGABYTE:6.3f} GB  "
                f"[{c.requirement.name}]"
            )

        lines.append("")
        lines.append("REQUIREMENTS")
        for r in self.requirements:
            state = "SATISFIED" if r.satisfied else "UNMET"
            lines.append(
                f"  {r.requirement.name:<20} {state:<10} "
                f"{r.delivered_gigabytes:6.3f} / "
                f"{r.requirement.required_bytes / BYTES_PER_GIGABYTE:.3f} GB "
                f"over {r.contact_count} contact(s)"
            )
            if not r.satisfied:
                lines.append(
                    f"    short by {r.shortfall_bytes / BYTES_PER_GIGABYTE:.3f} GB"
                )

        if self.rejected:
            lines.append("")
            lines.append("NOT SCHEDULED")
            for rej in self.rejected:
                c = rej.candidate
                lines.append(
                    f"  {c.pass_.aos_utc:%d %b %H:%M:%S}Z  "
                    f"NORAD {c.pass_.satellite_norad_id}  "
                    f"{c.pass_.station_name}/{c.antenna_id}  "
                    f"{rej.reason.value}: {rej.detail}"
                )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Ranking
# --------------------------------------------------------------------------


def rank_key(candidate: Candidate) -> tuple[int, float, float, float, str]:
    """The total ordering used to walk candidates. Lower sorts first.

    The policy, in order:

    1. **Priority** — the operator's own ordering, respected first. Nothing
       computed is allowed to override an explicitly stated priority.
    2. **Deadline** — the earlier the deadline, the more urgent. A requirement
       with no deadline sorts last among equal priorities.
    3. **Delivered volume, descending** — among contacts of equal urgency,
       prefer the one that moves the most data. This is what makes the walk
       greedy.
    4. **AOS, ascending** — earlier contacts first, which frees later antenna
       time and keeps the plan readable.
    5. **Identity key** — so the result is byte-for-byte reproducible when
       everything above ties. Without this, dictionary or set iteration order
       could leak into the plan.

    Deliberately NOT in the ranking: link margin. A contact that closes with
    +3 dB and one that closes with +20 dB deliver the same bytes; margin is a
    validity question, already decided, not a ranking one. Ranking on it would
    quietly prefer high-elevation passes even when a lower one does the job.
    """
    deadline = candidate.requirement.deadline_utc
    deadline_sort = ensure_utc(deadline).timestamp() if deadline else float("inf")
    return (
        candidate.priority,
        deadline_sort,
        -candidate.delivered_bytes,
        candidate.pass_.aos_utc.timestamp(),
        candidate.key,
    )


# --------------------------------------------------------------------------
# Conflicts
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Booking:
    """A reserved interval on one resource: an antenna, or a satellite.

    Satellites are a resource too. A spacecraft has one transmitter: pointing
    two dishes at it receives the same downlink twice, it does not double the
    data. Without this, the scheduler happily books the same pass on every
    available antenna and reports a requirement satisfied that is not.
    """

    resource_id: str
    start_utc: datetime
    end_utc: datetime
    candidate_key: str


def _conflicts(
    booking: Booking, start: datetime, end: datetime, turnaround_s: float
) -> bool:
    """True when a new interval cannot follow an existing booking.

    Turnaround is charged on **both** sides: an antenna needs time to slew away
    from one satellite and onto the next, whichever order they come in.
    """
    gap_after = seconds_between(booking.end_utc, start)
    gap_before = seconds_between(end, booking.start_utc)
    return gap_after < turnaround_s and gap_before < turnaround_s


# --------------------------------------------------------------------------
# The scheduler
# --------------------------------------------------------------------------


def schedule_contacts(
    candidates: list[Candidate],
    turnaround_s: float = 0.0,
    allow_conditional: bool = True,
) -> Schedule:
    """Greedily build a conflict-free plan from ranked candidates.

    ``turnaround_s`` is the minimum gap the same antenna needs between two
    contacts. ``allow_conditional`` decides whether CONDITIONALLY_VALID
    contacts may be scheduled; INVALID ones never are.

    The walk is single-pass and never backtracks. That is the honest cost of
    determinism and speed: a contact taken early can block a better
    combination later. Every such exclusion is reported, so the operator can
    see the trade and override it by adjusting priorities.
    """
    if turnaround_s < 0.0:
        raise ValueError("turnaround_s must be non-negative")

    ordered = sorted(candidates, key=rank_key)

    antenna_bookings: list[Booking] = []
    satellite_bookings: list[Booking] = []
    scheduled: list[ScheduledContact] = []
    rejected: list[RejectedContact] = []
    delivered: dict[str, float] = {}
    counts: dict[str, int] = {}
    requirements: dict[str, MissionRequirement] = {}

    for c in candidates:
        requirements.setdefault(c.requirement.name, c.requirement)
        delivered.setdefault(c.requirement.name, 0.0)
        counts.setdefault(c.requirement.name, 0)

    rank = 0
    for c in ordered:
        name = c.requirement.name

        if c.validation.verdict is Verdict.INVALID:
            blocking = [
                chk.name
                for chk in c.validation.failed_checks
                if chk.name not in ACCUMULABLE_FAILURES
            ]
            if blocking:
                rejected.append(
                    RejectedContact(
                        c, Rejection.INVALID, f"failed checks: {', '.join(blocking)}"
                    )
                )
                continue
            # Only accumulable failures: the contact is individually
            # insufficient but can still contribute. See ACCUMULABLE_FAILURES.

        if c.validation.verdict is Verdict.CONDITIONALLY_VALID and not allow_conditional:
            warned = ", ".join(chk.name for chk in c.validation.warnings)
            rejected.append(
                RejectedContact(
                    c,
                    Rejection.INVALID,
                    f"conditionally valid and conditional contacts are not allowed: {warned}",
                )
            )
            continue

        if delivered[name] >= c.requirement.required_bytes:
            rejected.append(
                RejectedContact(
                    c,
                    Rejection.REQUIREMENT_ALREADY_MET,
                    f"{name} already satisfied by earlier contacts",
                )
            )
            continue

        if c.delivered_bytes <= 0.0:
            rejected.append(
                RejectedContact(
                    c,
                    Rejection.DELIVERS_NOTHING,
                    "the link does not close long enough to move any data",
                )
            )
            continue

        deadline = c.requirement.deadline_utc
        if deadline is not None and seconds_between(c.pass_.los_utc, deadline) < 0.0:
            rejected.append(
                RejectedContact(
                    c,
                    Rejection.AFTER_DEADLINE,
                    f"contact ends after the {name} deadline",
                )
            )
            continue

        sat_id = str(c.pass_.satellite_norad_id)
        # A satellite downlinks once at a time: no turnaround, but no overlap.
        sat_clash = next(
            (
                b
                for b in satellite_bookings
                if b.resource_id == sat_id
                and _conflicts(b, c.pass_.aos_utc, c.pass_.los_utc, 0.0)
            ),
            None,
        )
        if sat_clash is not None:
            rejected.append(
                RejectedContact(
                    c,
                    Rejection.SATELLITE_BUSY,
                    (
                        f"NORAD {sat_id} is already downlinking "
                        f"{sat_clash.start_utc:%d %b %H:%M:%S}Z-"
                        f"{sat_clash.end_utc:%H:%M:%S}Z; a second antenna receives "
                        f"the same signal, not more data"
                    ),
                )
            )
            continue

        clash = next(
            (
                b
                for b in antenna_bookings
                if b.resource_id == c.antenna_id
                and _conflicts(b, c.pass_.aos_utc, c.pass_.los_utc, turnaround_s)
            ),
            None,
        )
        if clash is not None:
            rejected.append(
                RejectedContact(
                    c,
                    Rejection.ANTENNA_BUSY,
                    (
                        f"{c.antenna_id} is booked "
                        f"{clash.start_utc:%d %b %H:%M:%S}Z-{clash.end_utc:%H:%M:%S}Z"
                        + (f" (turnaround {turnaround_s:.0f} s)" if turnaround_s else "")
                    ),
                )
            )
            continue

        rank += 1
        delivered[name] += c.delivered_bytes
        counts[name] += 1
        antenna_bookings.append(
            Booking(c.antenna_id, c.pass_.aos_utc, c.pass_.los_utc, c.key)
        )
        satellite_bookings.append(
            Booking(sat_id, c.pass_.aos_utc, c.pass_.los_utc, c.key)
        )
        scheduled.append(
            ScheduledContact(candidate=c, rank=rank, cumulative_bytes=delivered[name])
        )

    scheduled.sort(key=lambda s: s.candidate.pass_.aos_utc)

    statuses = tuple(
        RequirementStatus(
            requirement=req,
            delivered_bytes=delivered[name],
            satisfied=delivered[name] >= req.required_bytes,
            contact_count=counts[name],
        )
        for name, req in sorted(requirements.items())
    )

    notes = [
        "greedy single-pass allocation: no backtracking, so a better "
        "combination may exist (docs/scheduling.md)",
    ]
    if turnaround_s == 0.0:
        notes.append(
            "turnaround_s is 0: contacts may be scheduled back to back with no "
            "time to slew between satellites"
        )

    return Schedule(
        scheduled=tuple(scheduled),
        rejected=tuple(rejected),
        requirements=statuses,
        notes=tuple(notes),
    )
