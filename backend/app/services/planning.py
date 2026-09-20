"""Orchestration: the sequence that turns a request into a plan.

This is the only place that knows the *order* of the pipeline — propagate,
find passes, sample the budget along each pass, estimate volume, validate,
schedule. Route handlers call into here and do no science of their own
(ADR 0001).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.datavol.volume import DataVolume, TransferProfile, compute_data_volume
from core.geometry.station import GroundStation
from core.orbit.propagator import Propagator
from core.passes.finder import Pass, find_passes
from core.rf.link import (
    PassLinkBudget,
    PathLosses,
    Receiver,
    Transmitter,
    compute_link_budget,
)
from core.scheduling.scheduler import Candidate, Schedule, schedule_contacts
from core.time.scales import seconds_between
from core.validation.contact import (
    AntennaConstraints,
    ContactValidation,
    MissionRequirement,
    validate_contact,
)


@dataclass(frozen=True, slots=True)
class EvaluatedContact:
    pass_: Pass
    budget: PassLinkBudget
    volume: DataVolume
    validation: ContactValidation


def budget_along_pass(
    station: GroundStation,
    prop: Propagator,
    pass_: Pass,
    transmitter: Transmitter,
    receiver: Receiver,
    losses: PathLosses,
    step_s: float,
) -> PassLinkBudget:
    """Sample the link budget across the pass.

    Never at peak elevation only: free-space loss at the horizon is 8-13 dB
    worse, so a peak-only budget systematically overestimates capacity
    (docs/math/cn0-ebn0.md).
    """
    timeline = pass_.timeline(station, prop, step_s=step_s)
    return PassLinkBudget(
        samples=tuple(
            (
                seconds_between(pass_.aos_utc, s.t_utc),
                compute_link_budget(
                    transmitter, receiver, s.range_km, losses, s.range_rate_km_s
                ),
            )
            for s in timeline
        )
    )


def evaluate_pass(
    station: GroundStation,
    prop: Propagator,
    pass_: Pass,
    transmitter: Transmitter,
    receiver: Receiver,
    losses: PathLosses,
    profile: TransferProfile,
    requirement: MissionRequirement,
    antenna: AntennaConstraints,
    step_s: float,
) -> EvaluatedContact:
    budget = budget_along_pass(
        station, prop, pass_, transmitter, receiver, losses, step_s
    )
    volume = compute_data_volume(budget, transmitter.data_rate_bps, profile)
    validation = validate_contact(
        pass_, budget, volume, requirement, antenna=antenna, freq_hz=transmitter.freq_hz
    )
    return EvaluatedContact(pass_, budget, volume, validation)


def plan(
    station: GroundStation,
    propagators: dict[int, Propagator],
    start_utc: datetime,
    end_utc: datetime,
    transmitter: Transmitter,
    receiver: Receiver,
    losses: PathLosses,
    profile: TransferProfile,
    requirement: MissionRequirement,
    antenna: AntennaConstraints,
    antenna_id: str,
    step_s: float = 15.0,
    turnaround_s: float = 0.0,
    coarse_step_s: float = 30.0,
) -> tuple[Schedule, dict[str, float]]:
    """Full pipeline for one station, one antenna and any number of satellites.

    Returns the schedule and, keyed by candidate, the free-space-loss spread
    across each pass — the number that shows at a glance how much a peak-only
    budget would have overstated.
    """
    if transmitter.data_rate_bps <= 0.0:
        raise ValueError(
            "transmitter.data_rate_bps must be positive to plan against a data "
            "requirement: without a bit rate there is no Eb/N0 and no volume"
        )

    candidates: list[Candidate] = []
    spreads: dict[str, float] = {}

    for _norad_id, prop in sorted(propagators.items()):
        for p in find_passes(station, prop, start_utc, end_utc, coarse_step_s):
            evaluated = evaluate_pass(
                station, prop, p, transmitter, receiver, losses,
                profile, requirement, antenna, step_s,
            )
            candidate = Candidate(
                pass_=p,
                antenna_id=antenna_id,
                validation=evaluated.validation,
                volume=evaluated.volume,
                requirement=requirement,
            )
            candidates.append(candidate)
            spreads[candidate.key] = (
                evaluated.budget.fspl_spread_db() if evaluated.budget.samples else 0.0
            )

    return schedule_contacts(candidates, turnaround_s=turnaround_s), spreads
