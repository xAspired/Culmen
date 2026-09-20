"""Data volume.

There is no published reference case for this layer the way there is for SGP4
or the link budget: achievable volume depends on a specific ground system's
overheads. So the tests here pin *properties* and *inverse consistency*
instead, which is the honest substitute:

* the result is strictly below the naive rate x duration figure whenever any
  overhead is declared;
* computing volume and inverting it round-trip exactly;
* the answer does not depend on how finely the pass was sampled;
* every reduction is attributable to a named cause.

The worked arithmetic in the round-trip tests is checked by hand in the
assertions themselves, not taken on trust from the implementation.
"""

from __future__ import annotations

import pytest

from core.datavol.volume import (
    BYTES_PER_GIGABYTE,
    TransferProfile,
    accumulate,
    compute_data_volume,
    required_contact_seconds,
)
from core.rf.link import (
    PassLinkBudget,
    PathLosses,
    Receiver,
    Transmitter,
    compute_link_budget,
)

RATE_BPS = 25e6
LOSSES = PathLosses(pointing_db=0.5, atmospheric_db=0.5)


def _pass_budget(
    n_samples: int = 21,
    duration_s: float = 600.0,
    rate_bps: float = RATE_BPS,
    required_ebn0_db: float = 4.0,
    min_range_km: float = 500.0,
    max_range_km: float = 2300.0,
) -> PassLinkBudget:
    """A symmetric V-shaped range profile: horizon -> zenith -> horizon."""
    tx = Transmitter("sat", 8.2e9, 20.0, 12.0, data_rate_bps=rate_bps,
                     required_ebn0_db=required_ebn0_db)
    rx = Receiver("gs", gain_dbi=46.0, system_noise_temp_k=150.0)
    samples = []
    for i in range(n_samples):
        t = duration_s * i / (n_samples - 1)
        frac = abs(t - duration_s / 2.0) / (duration_s / 2.0)
        rng = min_range_km + frac * (max_range_km - min_range_km)
        samples.append((t, compute_link_budget(tx, rx, rng, LOSSES)))
    return PassLinkBudget(samples=tuple(samples))


# --------------------------------------------------------------------------
# The core claim: the naive figure is an overestimate
# --------------------------------------------------------------------------


def test_volume_is_below_the_naive_rate_times_duration():
    """rate x duration is the number this module exists to correct."""
    pass_budget = _pass_budget(duration_s=600.0)
    profile = TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0)
    got = compute_data_volume(pass_budget, RATE_BPS, profile)

    naive_bytes = RATE_BPS * 600.0 / 8.0
    assert got.delivered_bytes.value < naive_bytes
    assert got.delivered_bytes.value > 0.0


def test_each_overhead_removes_capacity_independently():
    """Turning on one overhead at a time must strictly reduce the result."""
    pass_budget = _pass_budget()
    base = compute_data_volume(pass_budget, RATE_BPS).delivered_bytes.value

    framing = compute_data_volume(
        pass_budget, RATE_BPS, TransferProfile(framing_efficiency=0.85)
    ).delivered_bytes.value
    acq = compute_data_volume(
        pass_budget, RATE_BPS, TransferProfile(acquisition_s=45.0)
    ).delivered_bytes.value
    setup = compute_data_volume(
        pass_budget, RATE_BPS, TransferProfile(setup_s=30.0)
    ).delivered_bytes.value

    assert framing < base
    assert acq < base
    assert setup < base
    # Framing is a pure multiplier and must be exactly 85% of the base.
    assert framing == pytest.approx(0.85 * base, rel=1e-12)


def test_negative_margin_intervals_are_excluded():
    """A pass that only closes near the peak must not be credited end to end."""
    # A demanding requirement so the horizon samples fail.
    marginal = _pass_budget(rate_bps=2.5e9, required_ebn0_db=10.0)
    assert not all(b.closes() for _, b in marginal.samples), "test case does not fail anywhere"

    got = compute_data_volume(marginal, RATE_BPS)
    total_s = marginal.samples[-1][0] - marginal.samples[0][0]
    assert 0.0 < got.closing_s.value < total_s
    assert got.delivered_bytes.value == pytest.approx(
        RATE_BPS * got.closing_s.value / 8.0, rel=1e-12
    )


def test_a_pass_that_never_closes_delivers_nothing():
    impossible = _pass_budget(rate_bps=1e12, required_ebn0_db=30.0)
    assert not any(b.closes() for _, b in impossible.samples)
    got = compute_data_volume(impossible, RATE_BPS)
    assert got.closing_s.value == 0.0
    assert got.delivered_bytes.value == 0.0
    assert got.satisfies(1.0) is False


def test_overhead_longer_than_the_contact_yields_zero_not_negative():
    pass_budget = _pass_budget(duration_s=120.0)
    profile = TransferProfile(acquisition_s=300.0, setup_s=300.0)
    got = compute_data_volume(pass_budget, RATE_BPS, profile)
    assert got.usable_s.value == 0.0
    assert got.delivered_bytes.value == 0.0


# --------------------------------------------------------------------------
# Sampling independence
# --------------------------------------------------------------------------


def test_result_does_not_depend_on_sampling_density():
    """Sampling finer must refine the answer, not change it."""
    coarse = compute_data_volume(_pass_budget(n_samples=11), RATE_BPS)
    fine = compute_data_volume(_pass_budget(n_samples=201), RATE_BPS)
    assert coarse.delivered_bytes.value == pytest.approx(
        fine.delivered_bytes.value, rel=0.05
    )


# --------------------------------------------------------------------------
# Inverse consistency
# --------------------------------------------------------------------------


def test_required_seconds_inverts_delivered_bytes_exactly():
    profile = TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0)
    pass_budget = _pass_budget()
    volume = compute_data_volume(pass_budget, RATE_BPS, profile)

    needed = required_contact_seconds(
        volume.delivered_bytes.value, RATE_BPS, profile
    )
    assert needed.value == pytest.approx(volume.closing_s.value, rel=1e-9)


def test_required_seconds_worked_by_hand():
    """2 GB at 25 Mbps, 85% efficiency, 75 s of overhead.

    transfer = 2e9 * 8 / (25e6 * 0.85) = 752.94 s
    total    = 752.94 + 75 = 827.94 s
    """
    profile = TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0)
    got = required_contact_seconds(2 * BYTES_PER_GIGABYTE, RATE_BPS, profile)
    assert got.inputs["transfer_s"] == pytest.approx(752.94, abs=0.01)
    assert got.value == pytest.approx(827.94, abs=0.01)


def test_ignoring_overhead_understates_the_contact_needed():
    """The whole point, stated as a number a planner would care about."""
    optimistic = required_contact_seconds(2 * BYTES_PER_GIGABYTE, RATE_BPS).value
    realistic = required_contact_seconds(
        2 * BYTES_PER_GIGABYTE,
        RATE_BPS,
        TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0),
    ).value
    assert optimistic == pytest.approx(640.0, abs=0.01)  # 2e9*8/25e6
    assert realistic > optimistic
    assert realistic - optimistic == pytest.approx(187.94, abs=0.05)


def test_gigabytes_are_decimal_not_binary():
    """A 2 GB mission requirement means 2e9 bytes; GiB would inflate it 7.4%."""
    assert BYTES_PER_GIGABYTE == 1_000_000_000
    pass_budget = _pass_budget()
    got = compute_data_volume(pass_budget, RATE_BPS)
    assert got.gigabytes == pytest.approx(got.delivered_bytes.value / 1e9, rel=1e-12)


# --------------------------------------------------------------------------
# Requirements across several contacts
# --------------------------------------------------------------------------


def test_accumulate_stops_as_soon_as_the_requirement_is_met():
    volumes = [compute_data_volume(_pass_budget(), RATE_BPS) for _ in range(5)]
    per_contact = volumes[0].delivered_bytes.value

    outcome = accumulate(volumes, required_bytes=per_contact * 2.5)
    assert outcome.satisfied
    assert outcome.contact_count == 3
    assert outcome.shortfall_bytes == 0.0


def test_accumulate_reports_the_shortfall_when_it_cannot_be_met():
    volumes = [compute_data_volume(_pass_budget(), RATE_BPS) for _ in range(2)]
    total = sum(v.delivered_bytes.value for v in volumes)

    outcome = accumulate(volumes, required_bytes=total * 3.0)
    assert not outcome.satisfied
    assert outcome.contact_count == 2
    assert outcome.shortfall_bytes == pytest.approx(total * 2.0, rel=1e-9)
    assert outcome.delivered_gigabytes == pytest.approx(total / BYTES_PER_GIGABYTE)


def test_accumulate_with_no_contacts_is_unsatisfied_not_an_error():
    outcome = accumulate([], required_bytes=1e9)
    assert not outcome.satisfied
    assert outcome.contact_count == 0
    assert outcome.shortfall_bytes == 1e9


def test_a_zero_requirement_is_already_satisfied():
    outcome = accumulate([], required_bytes=0.0)
    assert outcome.satisfied
    assert outcome.contact_count == 0


# --------------------------------------------------------------------------
# Validation and provenance
# --------------------------------------------------------------------------


def test_impossible_profiles_are_rejected():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="framing_efficiency"):
            TransferProfile(framing_efficiency=bad)
    with pytest.raises(ValueError, match="non-negative"):
        TransferProfile(acquisition_s=-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        TransferProfile(setup_s=-1.0)


def test_non_positive_rate_is_rejected():
    pass_budget = _pass_budget()
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="data_rate_bps"):
            compute_data_volume(pass_budget, bad)
        with pytest.raises(ValueError, match="data_rate_bps"):
            required_contact_seconds(1e9, bad)
    with pytest.raises(ValueError, match="required_bytes"):
        required_contact_seconds(-1.0, RATE_BPS)


def test_a_neutral_profile_is_flagged_as_an_upper_bound():
    got = compute_data_volume(_pass_budget(), RATE_BPS)
    assert any("optimistic upper bound" in a for a in got.assumptions)


def test_a_realistic_profile_is_not_flagged_as_optimistic():
    got = compute_data_volume(
        _pass_budget(), RATE_BPS, TransferProfile(framing_efficiency=0.85)
    )
    assert not any("optimistic upper bound" in a for a in got.assumptions)


def test_every_quantity_carries_its_audit_trail():
    got = compute_data_volume(
        _pass_budget(),
        RATE_BPS,
        TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0),
    )
    for part in (got.closing_s, got.usable_s, got.delivered_bytes):
        assert part.unit
        assert part.formula_ref == "docs/math/data-volume.md"
        assert part.inputs
        assert part.assumptions
    assert any("INFORMATION rate" in a for a in got.assumptions)
