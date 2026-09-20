"""Achievable data volume over a contact.

The naive formula is wrong, and wrong in the optimistic direction:

    bytes = data_rate * pass_duration        # NO

Four things it ignores, each of which subtracts real capacity:

1. **The margin is not positive for the whole pass.** Near AOS and LOS the
   free-space loss is 8-13 dB worse than at the peak, so a link sized for
   mid-pass simply does not close at the edges. Only the interval where the
   margin is non-negative can carry data.
2. **Acquisition takes time.** Carrier lock, symbol lock and frame sync cost
   tens of seconds after the link first closes, during which nothing useful
   is transferred.
3. **Antenna setup and slew** consume the beginning of the window.
4. **Framing and protocol overhead.** The channel rate is not the delivered
   information rate: CCSDS framing, Reed-Solomon parity, sync markers and
   retransmission all take their share.

So:

    usable_s   = closing_s - setup_s - acquisition_s
    bytes      = data_rate_bps * usable_s * efficiency / 8

Every default here is 0 or 1 (i.e. no reduction) rather than a plausible-
looking guess. An unstated overhead must surface as an optimistic number the
user can see and challenge, never as an invented one.

Reference: docs/math/data-volume.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.provenance import Computed
from core.rf.link import PassLinkBudget

BYTES_PER_GIGABYTE = 1_000_000_000
"""Decimal GB, the convention used for data-transfer budgets.

Not 2^30. A 2 GB requirement quoted by a mission is 2e9 bytes; using GiB here
would silently inflate every requirement by 7.4%.
"""
BYTES_PER_GIBIBYTE = 1_073_741_824


@dataclass(frozen=True, slots=True)
class TransferProfile:
    """Everything between the channel rate and delivered bytes.

    All defaults are neutral. Supplying none of them yields the optimistic
    upper bound, flagged as such in the assumptions.
    """

    #: Delivered information bytes per channel byte, after framing, coding
    #: overhead not already reflected in the data rate, and retransmission.
    framing_efficiency: float = 1.0
    #: Seconds from link closure to usable data: carrier, symbol and frame lock.
    acquisition_s: float = 0.0
    #: Seconds consumed before the contact can begin: slew, configuration.
    setup_s: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.framing_efficiency <= 1.0:
            raise ValueError(
                f"framing_efficiency must be in (0, 1], got {self.framing_efficiency}"
            )
        if self.acquisition_s < 0.0 or self.setup_s < 0.0:
            raise ValueError("acquisition_s and setup_s must be non-negative")

    def overhead_s(self) -> float:
        return self.setup_s + self.acquisition_s

    def is_neutral(self) -> bool:
        return (
            self.framing_efficiency == 1.0
            and self.acquisition_s == 0.0
            and self.setup_s == 0.0
        )


@dataclass(frozen=True, slots=True)
class DataVolume:
    """What a contact can actually deliver."""

    closing_s: Computed[float]
    usable_s: Computed[float]
    delivered_bytes: Computed[float]
    assumptions: tuple[str, ...] = ()

    @property
    def gigabytes(self) -> float:
        return self.delivered_bytes.value / BYTES_PER_GIGABYTE

    def satisfies(self, required_bytes: float) -> bool:
        return self.delivered_bytes.value >= required_bytes

    def shortfall_bytes(self, required_bytes: float) -> float:
        """Bytes still missing; 0.0 when the requirement is met."""
        return max(0.0, required_bytes - self.delivered_bytes.value)


def compute_data_volume(
    pass_budget: PassLinkBudget,
    data_rate_bps: float,
    profile: TransferProfile | None = None,
) -> DataVolume:
    """Bytes deliverable over a pass whose link budget has been sampled.

    Takes a :class:`~core.rf.link.PassLinkBudget` rather than a duration, so
    the peak-only mistake cannot be made here either: the closing interval
    comes from the sampled margin, not from AOS-to-LOS.
    """
    if data_rate_bps <= 0.0:
        raise ValueError(f"data_rate_bps must be positive, got {data_rate_bps}")
    profile = profile or TransferProfile()

    closing_value = pass_budget.closing_seconds()
    closing = Computed(
        value=closing_value,
        unit="s",
        formula_ref="docs/math/data-volume.md",
        inputs={
            "sample_count": float(len(pass_budget.samples)),
            "fspl_spread_db": pass_budget.fspl_spread_db() if pass_budget.samples else 0.0,
        },
        assumptions=(
            "only the interval with a non-negative link margin is counted; "
            "AOS-to-LOS duration would overstate it",
            "closing interval integrated trapezoidally between samples, so the "
            "result does not depend on the sampling step",
        ),
    )

    usable_value = max(0.0, closing_value - profile.overhead_s())
    usable = Computed(
        value=usable_value,
        unit="s",
        formula_ref="docs/math/data-volume.md",
        inputs={
            "closing_s": closing_value,
            "setup_s": profile.setup_s,
            "acquisition_s": profile.acquisition_s,
        },
        assumptions=(
            "setup and acquisition are charged once, at the start of the contact",
            "a pass whose closing interval is shorter than the overhead delivers "
            "nothing, rather than a negative volume",
        ),
    )

    bytes_value = data_rate_bps * usable_value * profile.framing_efficiency / 8.0
    collected = list(closing.assumptions) + list(usable.assumptions)
    if profile.is_neutral():
        collected.append(
            "no framing efficiency, acquisition or setup time supplied: this is "
            "an optimistic upper bound, not an expected delivery"
        )

    delivered = Computed(
        value=bytes_value,
        unit="B",
        formula_ref="docs/math/data-volume.md",
        inputs={
            "data_rate_bps": data_rate_bps,
            "usable_s": usable_value,
            "framing_efficiency": profile.framing_efficiency,
        },
        assumptions=(
            "data_rate_bps is the INFORMATION rate, matching the rate used in "
            "the Eb/N0 calculation; a symbol rate here would overstate the volume",
            "rate is constant across the contact; adaptive coding and modulation "
            "are not modelled",
        ),
    )
    collected.extend(delivered.assumptions)

    return DataVolume(
        closing_s=closing,
        usable_s=usable,
        delivered_bytes=delivered,
        assumptions=tuple(dict.fromkeys(collected)),
    )


def required_contact_seconds(
    required_bytes: float,
    data_rate_bps: float,
    profile: TransferProfile | None = None,
) -> Computed[float]:
    """Closing seconds needed to deliver ``required_bytes``.

    The inverse of :func:`compute_data_volume`, and the answer to "how long a
    contact do I need?". Overhead is added back, because the returned figure is
    a *closing* interval, not a pure transfer time.
    """
    if required_bytes < 0.0:
        raise ValueError("required_bytes must be non-negative")
    if data_rate_bps <= 0.0:
        raise ValueError(f"data_rate_bps must be positive, got {data_rate_bps}")
    profile = profile or TransferProfile()

    transfer_s = (required_bytes * 8.0) / (data_rate_bps * profile.framing_efficiency)
    value = transfer_s + profile.overhead_s()
    return Computed(
        value=value,
        unit="s",
        formula_ref="docs/math/data-volume.md",
        inputs={
            "required_bytes": required_bytes,
            "data_rate_bps": data_rate_bps,
            "framing_efficiency": profile.framing_efficiency,
            "transfer_s": transfer_s,
            "overhead_s": profile.overhead_s(),
        },
        assumptions=(
            "result is a required CLOSING interval, with setup and acquisition "
            "already included",
            "a single uninterrupted contact; splitting across passes needs the "
            "requirement planner, not this function",
        ),
    )


@dataclass(frozen=True, slots=True)
class RequirementOutcome:
    """Whether a set of contacts satisfies a data requirement."""

    required_bytes: float
    delivered_bytes: float
    contact_count: int
    satisfied: bool
    shortfall_bytes: float

    @property
    def required_gigabytes(self) -> float:
        return self.required_bytes / BYTES_PER_GIGABYTE

    @property
    def delivered_gigabytes(self) -> float:
        return self.delivered_bytes / BYTES_PER_GIGABYTE


def accumulate(volumes: list[DataVolume], required_bytes: float) -> RequirementOutcome:
    """Accumulate contacts, in the order given, until the requirement is met.

    The order is the caller's: this function does not choose which passes to
    use. Ranking belongs to the scheduler (Phase 9), and mixing the two would
    hide a policy decision inside an arithmetic helper.

    ``contact_count`` counts only the contacts actually needed. A contact that
    delivers nothing is still counted if it was consumed before the
    requirement was met, because it occupied the antenna.
    """
    if required_bytes < 0.0:
        raise ValueError("required_bytes must be non-negative")

    total = 0.0
    used = 0
    for volume in volumes:
        if total >= required_bytes:
            break
        total += volume.delivered_bytes.value
        used += 1

    return RequirementOutcome(
        required_bytes=required_bytes,
        delivered_bytes=total,
        contact_count=used,
        satisfied=total >= required_bytes,
        shortfall_bytes=max(0.0, required_bytes - total),
    )
