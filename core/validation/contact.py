"""Contact Validator: the verdict, and why.

This is the component Culmen exists for. Everything below it computes
numbers; this turns them into a decision a person can act on and argue with:

    VALID                  every check passed
    CONDITIONALLY_VALID    nothing failed, but something needs attention
    INVALID                at least one check failed

A verdict is worthless without its reasoning, so every check records what was
expected, what was actual, in what unit, and a message saying what it means.
Suggestions are **rule-derived from the specific check that failed** — not
generated text, and not a fixed list printed regardless of the failure
(ADR 0007).

Order matters. Checks run cheapest-and-most-fundamental first, and a failure
that makes later checks meaningless marks them SKIPPED rather than inventing a
result: if the satellite is never visible, "link margin: FAIL" would be noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from core.datavol.volume import BYTES_PER_GIGABYTE, DataVolume
from core.passes.finder import Pass
from core.rf.link import PassLinkBudget
from core.time.scales import ensure_utc, seconds_between


class CheckResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIPPED = "SKIPPED"


class Verdict(StrEnum):
    VALID = "VALID"
    CONDITIONALLY_VALID = "CONDITIONALLY_VALID"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class Check:
    """One decidable question about a contact."""

    name: str
    result: CheckResult
    message: str
    expected: str = ""
    actual: str = ""
    unit: str = ""
    formula_ref: str = ""

    @property
    def failed(self) -> bool:
        return self.result is CheckResult.FAIL


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A concrete change that would address a specific failed check."""

    check_name: str
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class AntennaConstraints:
    """Mechanical and RF limits of the ground antenna.

    ``max_elevation_deg`` below 90 models an az/el mount's *keyhole*: near the
    zenith the required azimuth rate goes to infinity and the mount cannot
    track. A pass that looks best on paper — highest elevation — can be the
    one the antenna physically cannot follow.
    """

    rx_freq_min_hz: float | None = None
    rx_freq_max_hz: float | None = None
    min_elevation_deg: float = 0.0
    max_elevation_deg: float = 90.0
    max_slew_rate_deg_s: float | None = None

    def covers_frequency(self, freq_hz: float) -> bool | None:
        """True/False, or None when no band was declared (unknown, not OK)."""
        if self.rx_freq_min_hz is None or self.rx_freq_max_hz is None:
            return None
        return self.rx_freq_min_hz <= freq_hz <= self.rx_freq_max_hz


@dataclass(frozen=True, slots=True)
class MissionRequirement:
    """What the contact has to achieve."""

    name: str
    required_bytes: float
    deadline_utc: datetime | None = None
    min_margin_db: float = 3.0

    def __post_init__(self) -> None:
        if self.required_bytes < 0.0:
            raise ValueError("required_bytes must be non-negative")


@dataclass(frozen=True, slots=True)
class ContactValidation:
    """The full, explainable outcome for one contact."""

    verdict: Verdict
    checks: tuple[Check, ...]
    suggestions: tuple[Suggestion, ...] = ()
    assumptions: tuple[str, ...] = ()
    engine_version: str = "culmen-validator/1"
    notes: tuple[str, ...] = field(default=())

    @property
    def failed_checks(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.result is CheckResult.FAIL)

    @property
    def warnings(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.result is CheckResult.WARN)

    def report(self) -> str:
        """Human-readable report: the verdict, every check, then what to change."""
        lines = [f"{self.verdict.value}"]
        width = max((len(c.name) for c in self.checks), default=0)
        for c in self.checks:
            row = f"  {c.name.ljust(width)}  {c.result.value:<8} {c.message}"
            if c.expected or c.actual:
                row += f"  [expected {c.expected}{c.unit}, actual {c.actual}{c.unit}]"
            lines.append(row)
        if self.suggestions:
            lines.append("")
            lines.append("Suggested alternatives:")
            for s in self.suggestions:
                lines.append(f"  - {s.action}: {s.detail}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def _check_visibility(pass_: Pass) -> Check:
    ok = pass_.duration_s > 0.0
    return Check(
        name="satellite_visibility",
        result=CheckResult.PASS if ok else CheckResult.FAIL,
        message=(
            f"pass of {pass_.duration_s / 60:.1f} min above the mask"
            if ok
            else "satellite never rises above the station mask in this window"
        ),
        expected="> 0",
        actual=f"{pass_.duration_s:.1f}",
        unit=" s",
        formula_ref="docs/math/pass-search.md",
    )


def _check_elevation(pass_: Pass, antenna: AntennaConstraints) -> Check:
    peak = pass_.max_elevation_deg
    if peak < antenna.min_elevation_deg:
        return Check(
            name="minimum_elevation",
            result=CheckResult.FAIL,
            message="peak elevation is below the antenna's mechanical limit",
            expected=f">= {antenna.min_elevation_deg:.1f}",
            actual=f"{peak:.1f}",
            unit=" deg",
            formula_ref="docs/math/topocentric.md",
        )
    return Check(
        name="minimum_elevation",
        result=CheckResult.PASS,
        message=f"peak elevation {peak:.1f} deg clears the limit",
        expected=f">= {antenna.min_elevation_deg:.1f}",
        actual=f"{peak:.1f}",
        unit=" deg",
        formula_ref="docs/math/topocentric.md",
    )


def _check_keyhole(pass_: Pass, antenna: AntennaConstraints) -> Check:
    """An az/el mount cannot track through the zenith."""
    peak = pass_.max_elevation_deg
    if peak > antenna.max_elevation_deg:
        return Check(
            name="antenna_keyhole",
            result=CheckResult.WARN,
            message=(
                "pass crosses the mount's keyhole; the required azimuth rate "
                "near the peak may exceed what the pedestal can follow"
            ),
            expected=f"<= {antenna.max_elevation_deg:.1f}",
            actual=f"{peak:.1f}",
            unit=" deg",
            formula_ref="docs/math/assumptions.md",
        )
    return Check(
        name="antenna_keyhole",
        result=CheckResult.PASS,
        message="pass stays below the mount's keyhole",
        expected=f"<= {antenna.max_elevation_deg:.1f}",
        actual=f"{peak:.1f}",
        unit=" deg",
        formula_ref="docs/math/assumptions.md",
    )


def _check_frequency(freq_hz: float, antenna: AntennaConstraints) -> Check:
    covered = antenna.covers_frequency(freq_hz)
    actual = f"{freq_hz / 1e6:.3f}"
    if covered is None:
        return Check(
            name="frequency_compatibility",
            result=CheckResult.WARN,
            message=(
                "antenna declares no receive band, so compatibility could not be "
                "checked; unknown is not the same as compatible"
            ),
            actual=actual,
            unit=" MHz",
        )
    # covers_frequency only returns a bool once both bounds are set.
    assert antenna.rx_freq_min_hz is not None
    assert antenna.rx_freq_max_hz is not None
    band = (
        f"{antenna.rx_freq_min_hz / 1e6:.3f}-{antenna.rx_freq_max_hz / 1e6:.3f}"
    )
    return Check(
        name="frequency_compatibility",
        result=CheckResult.PASS if covered else CheckResult.FAIL,
        message=(
            "transmit frequency is inside the antenna's receive band"
            if covered
            else "transmit frequency lies outside the antenna's receive band"
        ),
        expected=band,
        actual=actual,
        unit=" MHz",
    )


def _check_tle_age(pass_: Pass) -> Check:
    age = abs(pass_.tle_age_days)
    if age > 30.0:
        return Check(
            name="tle_freshness",
            result=CheckResult.FAIL,
            message="element set is too far from epoch for the pass times to be trusted",
            expected="<= 7",
            actual=f"{age:.1f}",
            unit=" d",
            formula_ref="docs/math/sgp4-and-teme.md",
        )
    if age > 7.0:
        return Check(
            name="tle_freshness",
            result=CheckResult.WARN,
            message="element set is stale; along-track error may reach kilometres",
            expected="<= 7",
            actual=f"{age:.1f}",
            unit=" d",
            formula_ref="docs/math/sgp4-and-teme.md",
        )
    return Check(
        name="tle_freshness",
        result=CheckResult.PASS,
        message=f"element set is {age:.1f} days from epoch",
        expected="<= 7",
        actual=f"{age:.1f}",
        unit=" d",
        formula_ref="docs/math/sgp4-and-teme.md",
    )


def _check_link_margin(
    pass_budget: PassLinkBudget, required_margin_db: float
) -> tuple[Check, float | None]:
    """Worst-case margin along the pass, not the margin at peak elevation."""
    if not pass_budget.samples:
        return (
            Check(
                name="link_margin",
                result=CheckResult.SKIPPED,
                message="no link budget samples supplied",
            ),
            None,
        )
    worst = pass_budget.worst
    if worst.margin_db is None:
        return (
            Check(
                name="link_margin",
                result=CheckResult.SKIPPED,
                message="no data rate declared, so no Eb/N0 and no margin",
                formula_ref="docs/math/cn0-ebn0.md",
            ),
            None,
        )
    value = worst.margin_db.value
    result = CheckResult.PASS if value >= required_margin_db else CheckResult.FAIL
    return (
        Check(
            name="link_margin",
            result=result,
            message=(
                f"worst-case margin across the pass, at {worst.range_km:.0f} km "
                f"slant range"
            ),
            expected=f"{required_margin_db:+.1f}",
            actual=f"{value:+.1f}",
            unit=" dB",
            formula_ref="docs/math/cn0-ebn0.md",
        ),
        value,
    )


def _check_data_capacity(
    volume: DataVolume, requirement: MissionRequirement
) -> tuple[Check, float]:
    delivered = volume.delivered_bytes.value
    shortfall = volume.shortfall_bytes(requirement.required_bytes)
    ok = shortfall == 0.0
    return (
        Check(
            name="data_capacity",
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            message=(
                "contact can carry the required volume"
                if ok
                else f"short by {shortfall / BYTES_PER_GIGABYTE:.3f} GB"
            ),
            expected=f"{requirement.required_bytes / BYTES_PER_GIGABYTE:.3f}",
            actual=f"{delivered / BYTES_PER_GIGABYTE:.3f}",
            unit=" GB",
            formula_ref="docs/math/data-volume.md",
        ),
        shortfall,
    )


def _check_deadline(pass_: Pass, requirement: MissionRequirement) -> Check:
    if requirement.deadline_utc is None:
        return Check(
            name="deadline",
            result=CheckResult.SKIPPED,
            message="requirement declares no deadline",
        )
    deadline = ensure_utc(requirement.deadline_utc)
    slack_s = seconds_between(pass_.los_utc, deadline)
    if slack_s < 0.0:
        return Check(
            name="deadline",
            result=CheckResult.FAIL,
            message="contact ends after the requirement deadline",
            expected=f"{deadline:%Y-%m-%d %H:%M:%S}Z",
            actual=f"{pass_.los_utc:%Y-%m-%d %H:%M:%S}Z",
        )
    return Check(
        name="deadline",
        result=CheckResult.PASS,
        message=f"contact ends {slack_s / 3600:.1f} h before the deadline",
        expected=f"{deadline:%Y-%m-%d %H:%M:%S}Z",
        actual=f"{pass_.los_utc:%Y-%m-%d %H:%M:%S}Z",
    )


# --------------------------------------------------------------------------
# Suggestions -- rule-derived, never generated
# --------------------------------------------------------------------------


def _suggest(
    checks: tuple[Check, ...],
    pass_: Pass,
    pass_budget: PassLinkBudget,
    volume: DataVolume,
    requirement: MissionRequirement,
    margin_db: float | None,
    shortfall_bytes: float,
) -> tuple[Suggestion, ...]:
    """Derive concrete alternatives from the checks that actually failed.

    Every suggestion carries a number taken from this contact. A generic list
    printed regardless of the failure would be noise, and would undermine the
    one thing this component is for.
    """
    out: list[Suggestion] = []
    by_name = {c.name: c for c in checks}

    margin_check = by_name.get("link_margin")
    if margin_check is not None and margin_check.failed and margin_db is not None:
        deficit = requirement.min_margin_db - margin_db
        out.append(
            Suggestion(
                "link_margin",
                "reduce the data rate",
                f"a {deficit:.1f} dB deficit is recovered by dividing the rate by "
                f"{10 ** (deficit / 10):.2f}",
            )
        )
        best_margin = pass_budget.best.margin_db
        if best_margin is not None:
            detail = (
                f"the worst case is at {pass_budget.worst.range_km:.0f} km slant "
                f"range; the best sample on this pass has {best_margin.value:+.1f} dB"
            )
        else:
            detail = "restrict the contact to the high-elevation part of the pass"
        out.append(Suggestion("link_margin", "raise the elevation mask", detail))
        out.append(
            Suggestion(
                "link_margin",
                "increase antenna gain",
                f"{deficit:.1f} dB needs the dish diameter multiplied by "
                f"{10 ** (deficit / 20):.2f}",
            )
        )
        out.append(
            Suggestion(
                "link_margin",
                "use another ground station",
                "one with a higher G/T, or a better view of this orbit",
            )
        )

    capacity_check = by_name.get("data_capacity")
    if capacity_check is not None and capacity_check.failed:
        delivered = volume.delivered_bytes.value
        out.append(
            Suggestion(
                "data_capacity",
                "use additional passes",
                (
                    f"this contact delivers {delivered / BYTES_PER_GIGABYTE:.3f} GB; "
                    f"about {int(-(-requirement.required_bytes // max(delivered, 1.0)))} "
                    f"contacts of this size would be needed"
                )
                if delivered > 0.0
                else "this contact delivers nothing usable; the link must close first",
            )
        )
        out.append(
            Suggestion(
                "data_capacity",
                "choose a higher-elevation pass",
                f"short by {shortfall_bytes / BYTES_PER_GIGABYTE:.3f} GB; a longer "
                f"closing interval is the cheapest way to recover it",
            )
        )
        out.append(
            Suggestion(
                "data_capacity",
                "reduce the acquisition or setup time",
                f"overhead currently costs "
                f"{volume.closing_s.value - volume.usable_s.value:.0f} s of this contact",
            )
        )

    freq_check = by_name.get("frequency_compatibility")
    if freq_check is not None and freq_check.failed:
        out.append(
            Suggestion(
                "frequency_compatibility",
                "use a station covering this band",
                f"the transmitter is at {freq_check.actual} MHz, outside "
                f"{freq_check.expected} MHz",
            )
        )

    elevation_check = by_name.get("minimum_elevation")
    if elevation_check is not None and elevation_check.failed:
        out.append(
            Suggestion(
                "minimum_elevation",
                "choose another pass",
                f"peak elevation here is {pass_.max_elevation_deg:.1f} deg, below "
                f"what the mount can use",
            )
        )

    deadline_check = by_name.get("deadline")
    if deadline_check is not None and deadline_check.failed:
        out.append(
            Suggestion(
                "deadline",
                "choose an earlier pass",
                f"this contact ends at {pass_.los_utc:%Y-%m-%d %H:%M}Z, after the "
                f"deadline",
            )
        )

    tle_check = by_name.get("tle_freshness")
    if tle_check is not None and tle_check.failed:
        out.append(
            Suggestion(
                "tle_freshness",
                "fetch a current element set",
                f"the one used is {abs(pass_.tle_age_days):.1f} days from epoch",
            )
        )

    return tuple(out)


# --------------------------------------------------------------------------
# The validator
# --------------------------------------------------------------------------


def validate_contact(
    pass_: Pass,
    pass_budget: PassLinkBudget,
    volume: DataVolume,
    requirement: MissionRequirement,
    antenna: AntennaConstraints | None = None,
    freq_hz: float | None = None,
) -> ContactValidation:
    """Run every check against one contact and return an explainable verdict.

    The verdict rule is deliberately blunt:

    * any FAIL              -> INVALID
    * any WARN, no FAIL     -> CONDITIONALLY_VALID
    * everything PASS       -> VALID

    SKIPPED never changes the verdict on its own, but it is always reported:
    a check that could not run is information, not silence.
    """
    antenna = antenna or AntennaConstraints()
    if freq_hz is None and pass_budget.samples:
        freq_hz = pass_budget.samples[0][1].freq_hz

    checks: list[Check] = [_check_visibility(pass_)]

    if checks[0].failed:
        # Nothing below this is meaningful once the satellite is never visible.
        for name in (
            "minimum_elevation",
            "antenna_keyhole",
            "frequency_compatibility",
            "link_margin",
            "data_capacity",
            "deadline",
        ):
            checks.append(
                Check(
                    name=name,
                    result=CheckResult.SKIPPED,
                    message="not evaluated: the satellite is not visible",
                )
            )
        checks.append(_check_tle_age(pass_))
        return ContactValidation(
            verdict=Verdict.INVALID,
            checks=tuple(checks),
            suggestions=(
                Suggestion(
                    "satellite_visibility",
                    "widen the search window or lower the mask",
                    "no usable geometry in the window supplied",
                ),
            ),
        )

    checks.append(_check_elevation(pass_, antenna))
    checks.append(_check_keyhole(pass_, antenna))
    if freq_hz is not None:
        checks.append(_check_frequency(freq_hz, antenna))
    checks.append(_check_tle_age(pass_))

    margin_check, margin_db = _check_link_margin(pass_budget, requirement.min_margin_db)
    checks.append(margin_check)

    capacity_check, shortfall = _check_data_capacity(volume, requirement)
    checks.append(capacity_check)
    checks.append(_check_deadline(pass_, requirement))

    frozen = tuple(checks)
    if any(c.result is CheckResult.FAIL for c in frozen):
        verdict = Verdict.INVALID
    elif any(c.result is CheckResult.WARN for c in frozen):
        verdict = Verdict.CONDITIONALLY_VALID
    else:
        verdict = Verdict.VALID

    assumptions = list(pass_budget.worst.assumptions) if pass_budget.samples else []
    assumptions.extend(volume.assumptions)
    assumptions.extend(pass_.warnings)

    return ContactValidation(
        verdict=verdict,
        checks=frozen,
        suggestions=_suggest(
            frozen, pass_, pass_budget, volume, requirement, margin_db, shortfall
        ),
        assumptions=tuple(dict.fromkeys(assumptions)),
    )
