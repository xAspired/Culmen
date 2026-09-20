"""Contact Validator.

What is tested here is not arithmetic — the layers below already pin that —
but the *decision*: that a verdict follows from its checks, that the reasoning
is complete and specific, and that suggestions are derived from the actual
failure rather than printed regardless.

The property that matters most: it must be impossible for the validator to say
INVALID without naming which check failed, by how much, and what to change.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from core.datavol.volume import (
    BYTES_PER_GIGABYTE,
    TransferProfile,
    compute_data_volume,
)
from core.passes.finder import Pass
from core.rf.link import (
    PassLinkBudget,
    PathLosses,
    Receiver,
    Transmitter,
    compute_link_budget,
)
from core.time.scales import UTC
from core.validation.contact import (
    AntennaConstraints,
    CheckResult,
    ContactValidation,
    MissionRequirement,
    Verdict,
    validate_contact,
)

FREQ_HZ = 8.2e9
AOS = datetime(2026, 9, 9, 6, 42, tzinfo=UTC)


def make_pass(
    duration_s: float = 600.0,
    max_el_deg: float = 47.3,
    tle_age_days: float = 0.5,
) -> Pass:
    return Pass(
        satellite_norad_id=99999,
        station_name="Padova",
        aos_utc=AOS,
        los_utc=AOS + timedelta(seconds=duration_s),
        max_elevation_deg=max_el_deg,
        max_elevation_utc=AOS + timedelta(seconds=duration_s / 2),
        duration_s=duration_s,
        aos_az_deg=172.0,
        los_az_deg=79.0,
        max_el_az_deg=250.0,
        tle_epoch_utc=AOS - timedelta(days=tle_age_days),
        tle_age_days=tle_age_days,
        propagator_version="test",
    )


def make_budget(
    rate_bps: float = 25e6,
    required_ebn0_db: float = 4.0,
    duration_s: float = 600.0,
    n: int = 21,
    gs_gain_dbi: float = 46.0,
) -> PassLinkBudget:
    tx = Transmitter("sat", FREQ_HZ, 20.0, 12.0,
                     data_rate_bps=rate_bps, required_ebn0_db=required_ebn0_db)
    rx = Receiver("gs", gain_dbi=gs_gain_dbi, system_noise_temp_k=150.0)
    losses = PathLosses(pointing_db=0.5, atmospheric_db=0.5)
    samples = []
    for i in range(n):
        t = duration_s * i / (n - 1)
        frac = abs(t - duration_s / 2) / (duration_s / 2)
        rng = 500.0 + frac * 1800.0
        samples.append((t, compute_link_budget(tx, rx, rng, losses)))
    return PassLinkBudget(samples=tuple(samples))


PROFILE = TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0)
X_BAND_ANTENNA = AntennaConstraints(
    rx_freq_min_hz=8.0e9, rx_freq_max_hz=8.5e9, min_elevation_deg=5.0
)


def validate(
    pass_=None, budget=None, rate_bps=25e6, required_gb=1.0, **kwargs
) -> ContactValidation:
    pass_ = pass_ or make_pass()
    budget = budget if budget is not None else make_budget(rate_bps=rate_bps)
    volume = compute_data_volume(budget, rate_bps, PROFILE)
    requirement = MissionRequirement(
        name="downlink",
        required_bytes=required_gb * BYTES_PER_GIGABYTE,
        **{k: v for k, v in kwargs.items() if k in {"deadline_utc", "min_margin_db"}},
    )
    return validate_contact(
        pass_,
        budget,
        volume,
        requirement,
        antenna=kwargs.get("antenna", X_BAND_ANTENNA),
        freq_hz=FREQ_HZ,
    )


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------


def test_a_healthy_contact_is_valid():
    result = validate(required_gb=1.0)
    assert result.verdict is Verdict.VALID, result.report()
    assert not result.failed_checks
    assert not result.warnings


def test_any_failure_makes_the_contact_invalid():
    result = validate(required_gb=99.0)
    assert result.verdict is Verdict.INVALID
    assert [c.name for c in result.failed_checks] == ["data_capacity"]


def test_a_warning_alone_makes_it_conditionally_valid():
    stale = make_pass(tle_age_days=12.0)
    result = validate(pass_=stale, required_gb=1.0)
    assert result.verdict is Verdict.CONDITIONALLY_VALID
    assert [c.name for c in result.warnings] == ["tle_freshness"]
    assert not result.failed_checks


def test_a_failure_outranks_a_warning():
    stale = make_pass(tle_age_days=12.0)
    result = validate(pass_=stale, required_gb=99.0)
    assert result.verdict is Verdict.INVALID
    assert result.warnings  # the warning is still reported, not swallowed


# --------------------------------------------------------------------------
# The reasoning must be complete
# --------------------------------------------------------------------------


def test_every_invalid_verdict_names_a_failed_check_with_numbers():
    """The property the whole component exists for."""
    for kwargs in (
        {"required_gb": 99.0},
        {"required_gb": 1.0, "min_margin_db": 60.0},
        {"required_gb": 1.0, "deadline_utc": AOS - timedelta(hours=1)},
    ):
        result = validate(**kwargs)
        assert result.verdict is Verdict.INVALID
        assert result.failed_checks, f"no failed check named for {kwargs}"
        for check in result.failed_checks:
            assert check.message
            assert check.expected, f"{check.name} states no expectation"
            assert check.actual, f"{check.name} states no actual value"
        assert result.suggestions, f"no alternatives offered for {kwargs}"


def test_suggestions_are_derived_from_the_failure_not_printed_always():
    healthy = validate(required_gb=1.0)
    assert healthy.suggestions == ()

    capacity = validate(required_gb=99.0)
    assert {s.check_name for s in capacity.suggestions} == {"data_capacity"}

    margin = validate(required_gb=1.0, min_margin_db=60.0)
    assert {s.check_name for s in margin.suggestions} == {"link_margin"}


def test_margin_suggestions_carry_numbers_from_this_contact():
    result = validate(required_gb=1.0, min_margin_db=60.0)
    actions = {s.action: s.detail for s in result.suggestions}
    assert "reduce the data rate" in actions
    assert "increase antenna gain" in actions
    # Each must quote a figure, not offer generic advice.
    assert any(char.isdigit() for char in actions["reduce the data rate"])
    assert any(char.isdigit() for char in actions["increase antenna gain"])


def test_report_renders_verdict_checks_and_alternatives():
    result = validate(required_gb=99.0)
    text = result.report()
    assert text.startswith("INVALID")
    assert "data_capacity" in text
    assert "Suggested alternatives:" in text
    assert "GB" in text


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def test_link_margin_uses_the_worst_case_not_the_peak():
    """Validating at peak elevation would pass a link that fails at the edges."""
    budget = make_budget()
    worst = budget.worst.margin_db.value
    best = budget.best.margin_db.value
    assert worst < best

    # A threshold between the two: peak-based validation would wrongly pass.
    threshold = (worst + best) / 2
    result = validate(budget=budget, required_gb=1.0, min_margin_db=threshold)
    assert result.verdict is Verdict.INVALID
    margin_check = next(c for c in result.checks if c.name == "link_margin")
    assert float(margin_check.actual) == pytest.approx(worst, abs=0.05)


def test_frequency_outside_the_band_fails():
    s_band = AntennaConstraints(rx_freq_min_hz=2.0e9, rx_freq_max_hz=2.3e9)
    result = validate(required_gb=1.0, antenna=s_band)
    assert result.verdict is Verdict.INVALID
    check = next(c for c in result.checks if c.name == "frequency_compatibility")
    assert check.result is CheckResult.FAIL
    assert "8200.000" in check.actual


def test_an_undeclared_band_warns_rather_than_silently_passing():
    """Unknown is not the same as compatible."""
    result = validate(required_gb=1.0, antenna=AntennaConstraints())
    check = next(c for c in result.checks if c.name == "frequency_compatibility")
    assert check.result is CheckResult.WARN
    assert "unknown is not the same as compatible" in check.message
    assert result.verdict is Verdict.CONDITIONALLY_VALID


def test_keyhole_warns_on_a_near_zenith_pass():
    """The highest pass can be the one an az/el mount cannot track."""
    overhead = make_pass(max_el_deg=88.0)
    antenna = replace(X_BAND_ANTENNA, max_elevation_deg=85.0)
    result = validate(pass_=overhead, required_gb=1.0, antenna=antenna)
    check = next(c for c in result.checks if c.name == "antenna_keyhole")
    assert check.result is CheckResult.WARN
    assert result.verdict is Verdict.CONDITIONALLY_VALID


def test_elevation_below_the_mount_limit_fails():
    low = make_pass(max_el_deg=3.0)
    result = validate(pass_=low, required_gb=1.0)
    check = next(c for c in result.checks if c.name == "minimum_elevation")
    assert check.result is CheckResult.FAIL
    assert result.verdict is Verdict.INVALID


def test_tle_age_thresholds():
    assert validate(pass_=make_pass(tle_age_days=1.0)).verdict is Verdict.VALID
    warn = next(
        c for c in validate(pass_=make_pass(tle_age_days=10.0)).checks
        if c.name == "tle_freshness"
    )
    assert warn.result is CheckResult.WARN
    fail = next(
        c for c in validate(pass_=make_pass(tle_age_days=45.0)).checks
        if c.name == "tle_freshness"
    )
    assert fail.result is CheckResult.FAIL


def test_deadline_after_the_pass_passes_and_before_it_fails():
    late = validate(required_gb=1.0, deadline_utc=AOS + timedelta(days=2))
    assert next(c for c in late.checks if c.name == "deadline").result is CheckResult.PASS

    early = validate(required_gb=1.0, deadline_utc=AOS - timedelta(hours=1))
    assert next(c for c in early.checks if c.name == "deadline").result is CheckResult.FAIL
    assert early.verdict is Verdict.INVALID


def test_no_deadline_is_skipped_not_silently_passed():
    result = validate(required_gb=1.0)
    check = next(c for c in result.checks if c.name == "deadline")
    assert check.result is CheckResult.SKIPPED
    assert result.verdict is Verdict.VALID


# --------------------------------------------------------------------------
# Degenerate inputs
# --------------------------------------------------------------------------


def test_an_invisible_satellite_short_circuits_the_rest():
    """'link margin: FAIL' would be noise when there is no pass at all."""
    invisible = make_pass(duration_s=0.0)
    result = validate(pass_=invisible, required_gb=1.0)
    assert result.verdict is Verdict.INVALID
    names = {c.name: c.result for c in result.checks}
    assert names["satellite_visibility"] is CheckResult.FAIL
    assert names["link_margin"] is CheckResult.SKIPPED
    assert names["data_capacity"] is CheckResult.SKIPPED
    assert result.suggestions


def test_a_budget_without_a_data_rate_skips_the_margin_check():
    tx = Transmitter("sat", FREQ_HZ, 20.0, 12.0)
    rx = Receiver("gs", gain_dbi=46.0, system_noise_temp_k=150.0)
    budget = PassLinkBudget(
        samples=tuple(
            (float(i * 60), compute_link_budget(tx, rx, 500.0 + i * 100.0))
            for i in range(5)
        )
    )
    volume = compute_data_volume(budget, 25e6, PROFILE)
    result = validate_contact(
        make_pass(),
        budget,
        volume,
        MissionRequirement("r", 1 * BYTES_PER_GIGABYTE),
        antenna=X_BAND_ANTENNA,
        freq_hz=FREQ_HZ,
    )
    check = next(c for c in result.checks if c.name == "link_margin")
    assert check.result is CheckResult.SKIPPED
    assert "no data rate" in check.message


def test_assumptions_from_every_layer_reach_the_verdict():
    """The verdict must carry the caveats of the numbers it rests on."""
    result = validate(required_gb=1.0)
    assert result.assumptions
    joined = " ".join(result.assumptions)
    assert "INFORMATION rate" in joined  # from the data-volume layer
    assert "reference plane" in joined  # from the RF layer


def test_a_negative_requirement_is_rejected():
    with pytest.raises(ValueError, match="required_bytes"):
        MissionRequirement("bad", -1.0)


def test_engine_version_is_recorded():
    """A cached verdict must be invalidatable when the engine changes."""
    assert validate(required_gb=1.0).engine_version
