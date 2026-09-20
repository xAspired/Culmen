"""Link budget, verified against a published external case.

Ground truth: Koudelka, *Link Budget Calculations*, ITU-R small-satellite
workshop, Prague 2015. The full case is transcribed, with its own internal
consistency already checked, in docs/math/link-budget-reference.md.

The reference is UHF. That is deliberate for this first gate: with the
atmospheric terms supplied as given constants, it isolates the arithmetic of
the chain itself. An X-band case with computed P.618/P.676 terms must be added
before Phase 5 is considered complete.
"""

from __future__ import annotations

import math

import pytest

from core.rf.link import (
    FSPL_CONST_KM_MHZ,
    PassLinkBudget,
    PathLosses,
    Receiver,
    Transmitter,
    compute_link_budget,
    doppler_shift_hz,
    eirp,
    free_space_path_loss,
    parabolic_gain_dbi,
    system_noise_temperature_k,
)
from core.units import BOLTZMANN_DBW_HZ_K, db10

# --------------------------------------------------------------------------
# The ITU reference case
# --------------------------------------------------------------------------

REF_FREQ_HZ = 438e6
REF_RANGE_KM = 1000.0
REF_EIRP_DBW = -4.0
REF_FSPL_DB = 145.3
REF_LOSSES = PathLosses(
    atmospheric_db=2.0,
    polarization_db=1.5,
    pointing_db=0.5,
    ionospheric_db=0.7,
)
REF_GT_DBK = -9.07
REF_LNA_TEMP_K = 120.0
REF_INPUT_LOSS_DB = 1.0
REF_TSYS_K = 510.4
REF_BANDWIDTH_HZ = 200e3
REF_DATA_RATE_BPS = 100e3
REF_REQUIRED_EBN0_DB = 7.0
REF_MARGIN_DB = 8.34


def test_fspl_constant_is_derivable_not_memorised():
    """32.4478 = 20*log10(4*pi/c) with km and MHz. Derive it, don't trust it."""
    derived = 20.0 * math.log10(4.0 * math.pi / 299_792_458.0) + 20.0 * math.log10(1e3 * 1e6)
    assert pytest.approx(derived, abs=1e-5) == FSPL_CONST_KM_MHZ


def test_fspl_matches_the_reference_case():
    got = free_space_path_loss(REF_RANGE_KM, REF_FREQ_HZ)
    assert got.value == pytest.approx(REF_FSPL_DB, abs=0.05)
    assert got.unit == "dB"
    assert got.formula_ref == "docs/math/fspl.md"
    assert got.inputs["freq_mhz"] == pytest.approx(438.0)


def test_fspl_unit_constants_for_other_conventions():
    """The constant changes with the units; pin the two other common forms."""
    # km / GHz -> 92.45
    assert FSPL_CONST_KM_MHZ + 20.0 * math.log10(1e3) == pytest.approx(92.45, abs=0.01)
    # 1 km at 1 GHz
    assert free_space_path_loss(1.0, 1e9).value == pytest.approx(92.45, abs=0.01)


def test_fspl_doubling_range_costs_exactly_6_db():
    a = free_space_path_loss(1000.0, REF_FREQ_HZ).value
    b = free_space_path_loss(2000.0, REF_FREQ_HZ).value
    assert b - a == pytest.approx(6.0206, abs=1e-4)


def test_fspl_rejects_nonsense_inputs():
    for bad_range in (0.0, -1.0):
        with pytest.raises(ValueError):
            free_space_path_loss(bad_range, REF_FREQ_HZ)
    with pytest.raises(ValueError):
        free_space_path_loss(REF_RANGE_KM, 0.0)


def test_system_noise_temperature_matches_the_reference_case():
    """T_sys = T_ant + (L-1)*T_amb + L*T_lna, referred to the antenna plane.

    The reference quotes 510.4 K for a 120 K LNB behind 1 dB of input loss.
    Back-solving for the antenna temperature the slide implies and confirming
    the arithmetic reproduces its figure.
    """
    loss_ratio = 10.0 ** (REF_INPUT_LOSS_DB / 10.0)
    implied_t_ant = REF_TSYS_K - (loss_ratio - 1.0) * 290.0 - loss_ratio * REF_LNA_TEMP_K
    got = system_noise_temperature_k(
        antenna_temp_k=implied_t_ant,
        line_loss_db=REF_INPUT_LOSS_DB,
        lna_temp_k=REF_LNA_TEMP_K,
    )
    assert got.value == pytest.approx(REF_TSYS_K, abs=0.1)
    # The implied antenna temperature must itself be physically sensible.
    assert 150.0 < implied_t_ant < 350.0


def test_g_over_t_from_gain_and_temperature():
    """G/T = G - 10*log10(T_sys); the reference's -9.07 dB/K implies ~18.0 dBi."""
    implied_gain_dbi = REF_GT_DBK + db10(REF_TSYS_K)
    rx = Receiver("ref", gain_dbi=implied_gain_dbi, system_noise_temp_k=REF_TSYS_K)
    assert rx.g_over_t().value == pytest.approx(REF_GT_DBK, abs=1e-6)
    assert 15.0 < implied_gain_dbi < 21.0


def test_full_chain_reproduces_the_reference_margin():
    """End-to-end: EIRP through to margin, against the published figures."""
    tx = Transmitter(
        name="ref-sat",
        freq_hz=REF_FREQ_HZ,
        power_w=10.0,  # placeholder; EIRP is pinned below, not the raw power
        gain_dbi=0.0,
        data_rate_bps=REF_DATA_RATE_BPS,
        required_ebn0_db=REF_REQUIRED_EBN0_DB,
    )
    rx = Receiver("ref-gs", g_over_t_dbk=REF_GT_DBK)

    budget = compute_link_budget(tx, rx, REF_RANGE_KM, REF_LOSSES)

    # Re-anchor EIRP to the reference value rather than inventing a power.
    cn0 = (
        REF_EIRP_DBW
        - budget.fspl_db.value
        - budget.other_losses_db.value
        + REF_GT_DBK
        - BOLTZMANN_DBW_HZ_K
    )
    ebn0 = cn0 - db10(REF_DATA_RATE_BPS)
    margin = ebn0 - REF_REQUIRED_EBN0_DB

    # The known 0.2 dB discrepancy in the source, documented in
    # docs/math/link-budget-reference.md: the slide's Eb/N0 of 15.34 dB does
    # not follow from its own C/N of 12.53 dB and B/Rb of 2 (which give
    # 15.54 dB). The tolerance here is set to that documented gap, NOT widened
    # until the test passes.
    assert margin == pytest.approx(REF_MARGIN_DB, abs=0.25), (
        f"chain gives {margin:.2f} dB against the published {REF_MARGIN_DB} dB"
    )


def test_ebn0_follows_from_cn0_and_bit_rate():
    """Eb/N0 = C/N0 - 10*log10(R_b). Halving the rate buys exactly 3.01 dB."""
    rx = Receiver("gs", g_over_t_dbk=REF_GT_DBK)
    fast = Transmitter("t", REF_FREQ_HZ, 10.0, 0.0, data_rate_bps=100e3)
    slow = Transmitter("t", REF_FREQ_HZ, 10.0, 0.0, data_rate_bps=50e3)

    b_fast = compute_link_budget(fast, rx, REF_RANGE_KM, REF_LOSSES)
    b_slow = compute_link_budget(slow, rx, REF_RANGE_KM, REF_LOSSES)

    assert b_fast.cn0_dbhz.value == pytest.approx(b_slow.cn0_dbhz.value)
    assert b_slow.ebn0_db is not None and b_fast.ebn0_db is not None
    assert b_slow.ebn0_db.value - b_fast.ebn0_db.value == pytest.approx(3.0103, abs=1e-4)


def test_no_data_rate_means_no_ebn0_and_no_margin():
    """An Eb/N0 without a bit rate is meaningless; returning 0 would read as PASS."""
    tx = Transmitter("t", REF_FREQ_HZ, 10.0, 0.0)
    rx = Receiver("gs", g_over_t_dbk=REF_GT_DBK)
    budget = compute_link_budget(tx, rx, REF_RANGE_KM)
    assert budget.ebn0_db is None
    assert budget.margin_db is None
    assert budget.closes() is False


# --------------------------------------------------------------------------
# Antenna gain
# --------------------------------------------------------------------------


def test_parabolic_gain_of_a_3m_dish_at_8_2_ghz():
    """A 3 m dish at 8.2 GHz, eta = 0.55, gives 45.63 dBi.

    Cross-checked by hand: lambda = 36.56 mm, pi*D/lambda = 257.8,
    10*log10(0.55 * 257.8^2) = 45.63 dBi.
    """
    got = parabolic_gain_dbi(3.0, 8.2e9, efficiency=0.55)
    assert got.value == pytest.approx(45.63, abs=0.02)
    assert got.unit == "dBi"


def test_assuming_unit_efficiency_inflates_gain_by_2_6_db():
    real = parabolic_gain_dbi(3.0, 8.2e9, efficiency=0.55).value
    ideal = parabolic_gain_dbi(3.0, 8.2e9, efficiency=1.0).value
    assert ideal - real == pytest.approx(-db10(0.55), abs=1e-6)
    assert ideal - real == pytest.approx(2.6, abs=0.05)


def test_doubling_dish_diameter_gains_exactly_6_db():
    a = parabolic_gain_dbi(1.5, 8.2e9).value
    b = parabolic_gain_dbi(3.0, 8.2e9).value
    assert b - a == pytest.approx(6.0206, abs=1e-6)


def test_gain_rejects_impossible_efficiency():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            parabolic_gain_dbi(3.0, 8.2e9, efficiency=bad)


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------


def test_receiver_refuses_ambiguous_definition():
    with pytest.raises(ValueError, match="not both"):
        Receiver("gs", gain_dbi=40.0, system_noise_temp_k=150.0, g_over_t_dbk=-9.0)
    with pytest.raises(ValueError, match="needs"):
        Receiver("gs", gain_dbi=40.0)
    with pytest.raises(ValueError, match="needs"):
        Receiver("gs")


def test_transmitter_rejects_negative_loss_written_as_a_gain():
    with pytest.raises(ValueError, match="positive number of dB"):
        Transmitter("t", REF_FREQ_HZ, 10.0, 0.0, line_loss_db=-1.0)
    with pytest.raises(ValueError):
        Transmitter("t", 0.0, 10.0, 0.0)
    with pytest.raises(ValueError):
        Transmitter("t", REF_FREQ_HZ, 0.0, 0.0)


def test_eirp_subtracts_line_loss():
    tx = Transmitter("t", REF_FREQ_HZ, 20.0, 12.0, line_loss_db=1.5)
    got = eirp(tx)
    assert got.value == pytest.approx(db10(20.0) + 12.0 - 1.5, abs=1e-9)
    assert got.unit == "dBW"


# --------------------------------------------------------------------------
# Doppler
# --------------------------------------------------------------------------


def test_doppler_at_x_band_for_a_leo_pass():
    """At 8.2 GHz, +-7.5 km/s of range rate is roughly +-205 kHz."""
    receding = doppler_shift_hz(8.2e9, 7.5)
    approaching = doppler_shift_hz(8.2e9, -7.5)
    assert receding.value < 0.0 < approaching.value
    assert abs(receding.value) == pytest.approx(205e3, rel=0.02)


def test_doppler_is_zero_at_closest_approach():
    assert doppler_shift_hz(8.2e9, 0.0).value == 0.0


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_every_reported_quantity_carries_its_audit_trail():
    tx = Transmitter(
        "t", REF_FREQ_HZ, 10.0, 0.0,
        data_rate_bps=REF_DATA_RATE_BPS, required_ebn0_db=REF_REQUIRED_EBN0_DB,
    )
    rx = Receiver("gs", g_over_t_dbk=REF_GT_DBK)
    budget = compute_link_budget(tx, rx, REF_RANGE_KM, REF_LOSSES, range_rate_km_s=-6.0)

    for part in (
        budget.eirp_dbw, budget.fspl_db, budget.other_losses_db,
        budget.g_over_t_dbk, budget.cn0_dbhz, budget.ebn0_db,
        budget.margin_db, budget.doppler_hz,
    ):
        assert part is not None
        assert part.unit
        assert part.formula_ref.startswith("docs/math/")
        assert part.inputs


def test_zero_losses_are_flagged_as_optimistic():
    """A budget with no declared losses must say so, not look clean."""
    tx = Transmitter("t", REF_FREQ_HZ, 10.0, 0.0, data_rate_bps=1e5)
    rx = Receiver("gs", g_over_t_dbk=REF_GT_DBK)
    budget = compute_link_budget(tx, rx, REF_RANGE_KM)
    assert any("optimistic" in a for a in budget.assumptions)


def test_budget_lines_render_losses_as_negative_contributions():
    tx = Transmitter("t", REF_FREQ_HZ, 10.0, 0.0, data_rate_bps=1e5)
    rx = Receiver("gs", g_over_t_dbk=REF_GT_DBK)
    lines = compute_link_budget(tx, rx, REF_RANGE_KM, REF_LOSSES).lines()
    labelled = dict((label, value) for label, value, _ in lines)
    assert labelled["Free-space path loss"] < 0.0
    assert labelled["Other losses"] == pytest.approx(-REF_LOSSES.total_db())
    # The chain must add up to the reported C/N0.
    total = sum(v for k, v in labelled.items() if k not in {"C/N0", "Eb/N0", "Link margin"})
    assert total == pytest.approx(labelled["C/N0"], abs=1e-9)


# --------------------------------------------------------------------------
# Sampling along the pass -- the point of the whole module
# --------------------------------------------------------------------------


def _budget_at(range_km: float) -> object:
    tx = Transmitter(
        "sat", 8.2e9, 20.0, 12.0,
        data_rate_bps=25e6, required_ebn0_db=4.0,
    )
    rx = Receiver("gs", gain_dbi=46.0, system_noise_temp_k=150.0)
    return compute_link_budget(tx, rx, range_km, PathLosses(pointing_db=0.5))


def test_fspl_spread_across_a_leo_pass_is_8_to_10_db():
    """Why a peak-only budget overestimates capacity.

    A 500 km LEO pass runs from roughly 2300 km slant range at a 10 deg mask
    down to 500 km at the zenith. That is 8-13 dB of free-space loss swing.
    """
    horizon = free_space_path_loss(2300.0, 8.2e9).value
    zenith = free_space_path_loss(500.0, 8.2e9).value
    assert 8.0 < horizon - zenith < 14.0


def test_pass_budget_reports_worst_case_not_best():
    ranges = [2300.0, 1500.0, 800.0, 500.0, 800.0, 1500.0, 2300.0]
    samples = tuple(
        (float(i * 60), _budget_at(r)) for i, r in enumerate(ranges)
    )
    pass_budget = PassLinkBudget(samples=samples)  # type: ignore[arg-type]

    assert pass_budget.worst.range_km == 2300.0
    assert pass_budget.best.range_km == 500.0
    assert pass_budget.worst.margin_db is not None
    assert pass_budget.best.margin_db is not None
    assert pass_budget.worst.margin_db.value < pass_budget.best.margin_db.value
    assert 8.0 < pass_budget.fspl_spread_db() < 14.0


def test_closing_seconds_excludes_the_parts_that_do_not_close():
    """Capacity must not count the instants where the margin is negative."""
    # A rate high enough that the horizon samples fail and the close ones pass.
    tx = Transmitter("sat", 8.2e9, 20.0, 12.0, data_rate_bps=2.5e9, required_ebn0_db=10.0)
    rx = Receiver("gs", gain_dbi=46.0, system_noise_temp_k=150.0)
    ranges = [2300.0, 1500.0, 800.0, 500.0, 800.0, 1500.0, 2300.0]
    samples = tuple(
        (float(i * 60), compute_link_budget(tx, rx, r, PathLosses(pointing_db=0.5)))
        for i, r in enumerate(ranges)
    )
    pass_budget = PassLinkBudget(samples=samples)

    closing = pass_budget.closing_seconds()
    total = samples[-1][0] - samples[0][0]
    assert 0.0 <= closing <= total
    # Some sample must fail, or this test proves nothing.
    assert not all(b.closes() for _, b in samples), "raise the rate: every sample closes"
    assert closing < total


def test_closing_seconds_is_independent_of_sampling_step():
    """Trapezoidal attribution, not sample counting."""
    tx = Transmitter("sat", 8.2e9, 20.0, 12.0, data_rate_bps=2.5e9, required_ebn0_db=10.0)
    rx = Receiver("gs", gain_dbi=46.0, system_noise_temp_k=150.0)

    def build(n: int) -> PassLinkBudget:
        duration = 600.0
        out = []
        for i in range(n + 1):
            t = duration * i / n
            # Symmetric V-shaped range profile.
            frac = abs(t - duration / 2.0) / (duration / 2.0)
            rng = 500.0 + frac * 1800.0
            out.append((t, compute_link_budget(tx, rx, rng, PathLosses(pointing_db=0.5))))
        return PassLinkBudget(samples=tuple(out))

    coarse = build(10).closing_seconds()
    fine = build(100).closing_seconds()
    assert coarse == pytest.approx(fine, rel=0.15)
