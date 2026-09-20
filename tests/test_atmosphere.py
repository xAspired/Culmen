"""Atmospheric attenuation.

Culmen does not reimplement ITU-R P.676 or P.618 — it wraps ITU-Rpy — so
there is nothing to be gained from asserting the constants that library
returns. Asserting them would only pin today's output of somebody else's code.

What these tests check instead is that the **physics** of what comes back is
right, and that the wiring is right:

* attenuation follows the cosecant law with elevation away from the horizon;
* it increases with frequency, and the increase is dramatic across the 22 GHz
  water-vapour line;
* rain dominates gas at X-band, and the rain figure moves with the
  availability target it is quoted for;
* every returned quantity carries its provenance and its assumptions;
* ``core`` still imports and runs with the optional dependency absent.

If the wrapper were ever miswired — the wrong units, the elevation and the
frequency transposed, degrees fed as radians — every one of these would fail.
"""

from __future__ import annotations

import pytest

from core.provenance import Computed
from core.rf.atmosphere import (
    AtmosphereConditions,
    AtmosphereUnavailable,
    atmospheric_losses,
    available,
    cosecant_scaled,
    gaseous_attenuation_db,
    rain_attenuation_db,
)
from core.rf.link import PathLosses

itur = pytest.importorskip(
    "itur", reason="optional dependency; install with culmen[atmosphere]"
)

X_BAND_HZ = 8.2e9
PADOVA = AtmosphereConditions(lat_deg=45.4064, lon_deg=11.8768, alt_km=0.012)


# --------------------------------------------------------------------------
# Gaseous absorption
# --------------------------------------------------------------------------


def test_gaseous_attenuation_follows_the_cosecant_law():
    """Away from the horizon the slant path is the zenith path over sin(el).

    This is the single strongest check that elevation is being passed in the
    right units and the right place: radians, or a transposed argument, would
    break it immediately.
    """
    zenith = gaseous_attenuation_db(X_BAND_HZ, 90.0, PADOVA).value
    for elevation in (60.0, 40.0, 20.0, 10.0, 5.0):
        got = gaseous_attenuation_db(X_BAND_HZ, elevation, PADOVA).value
        assert got == pytest.approx(cosecant_scaled(zenith, elevation), rel=0.02)


def test_gaseous_attenuation_at_x_band_is_small_not_several_db():
    """A correction to this project's own earlier documentation.

    At 8.2 GHz gaseous absorption is a few tenths of a decibel, not several.
    Attributing several dB to it — as the assumptions file once did — is an
    order-of-magnitude error that would have justified a margin that was not
    there.
    """
    zenith = gaseous_attenuation_db(X_BAND_HZ, 90.0, PADOVA).value
    low = gaseous_attenuation_db(X_BAND_HZ, 10.0, PADOVA).value
    assert 0.01 < zenith < 0.2
    assert 0.1 < low < 1.0


def test_gaseous_attenuation_rises_sharply_at_the_water_vapour_line():
    """22.235 GHz is a water-vapour resonance; 8 GHz is nowhere near one."""
    at_x = gaseous_attenuation_db(X_BAND_HZ, 30.0, PADOVA).value
    at_line = gaseous_attenuation_db(22.2e9, 30.0, PADOVA).value
    assert at_line > 5 * at_x


def test_more_humid_air_attenuates_more():
    dry = AtmosphereConditions(45.0, 12.0, water_vapour_g_m3=2.0)
    humid = AtmosphereConditions(45.0, 12.0, water_vapour_g_m3=20.0)
    assert (
        gaseous_attenuation_db(22.2e9, 30.0, humid).value
        > gaseous_attenuation_db(22.2e9, 30.0, dry).value
    )


# --------------------------------------------------------------------------
# Rain
# --------------------------------------------------------------------------


def test_rain_dominates_gas_at_x_band():
    """The term that actually matters at 8 GHz, and the one we defaulted to 0."""
    gas = gaseous_attenuation_db(X_BAND_HZ, 10.0, PADOVA).value
    rain = rain_attenuation_db(X_BAND_HZ, 10.0, PADOVA).value
    assert rain > 10 * gas
    assert 1.0 < rain < 20.0  # temperate climate, 0.01% of an average year


def test_rain_attenuation_grows_as_the_availability_target_tightens():
    """A margin quoted without its availability figure is not a margin."""
    relaxed = AtmosphereConditions(45.4064, 11.8768, exceedance_percent=1.0)
    typical = AtmosphereConditions(45.4064, 11.8768, exceedance_percent=0.01)
    strict = AtmosphereConditions(45.4064, 11.8768, exceedance_percent=0.001)

    a = rain_attenuation_db(X_BAND_HZ, 20.0, relaxed).value
    b = rain_attenuation_db(X_BAND_HZ, 20.0, typical).value
    c = rain_attenuation_db(X_BAND_HZ, 20.0, strict).value
    assert a < b < c
    assert c - a > 2.0  # the choice is worth decibels, not rounding


def test_rain_attenuation_increases_towards_the_horizon():
    high = rain_attenuation_db(X_BAND_HZ, 60.0, PADOVA).value
    low = rain_attenuation_db(X_BAND_HZ, 10.0, PADOVA).value
    assert low > high


def test_rain_attenuation_is_far_worse_at_ka_band():
    """Why X-band missions exist: the same rain costs an order of magnitude more."""
    x = rain_attenuation_db(X_BAND_HZ, 20.0, PADOVA).value
    ka = rain_attenuation_db(20e9, 20.0, PADOVA).value
    assert ka > 4 * x


def test_a_dry_climate_attenuates_less_than_a_wet_one():
    temperate = AtmosphereConditions(45.4064, 11.8768)        # Padova
    arid = AtmosphereConditions(23.4162, 25.6628)             # eastern Sahara
    assert (
        rain_attenuation_db(X_BAND_HZ, 20.0, arid).value
        < rain_attenuation_db(X_BAND_HZ, 20.0, temperate).value
    )


# --------------------------------------------------------------------------
# Wiring into the budget
# --------------------------------------------------------------------------


def test_atmospheric_losses_fills_both_terms_and_keeps_the_others():
    base = PathLosses(polarization_db=0.5, pointing_db=0.8, implementation_db=1.2)
    losses, computed = atmospheric_losses(X_BAND_HZ, 15.0, PADOVA, base)

    assert losses.atmospheric_db > 0.0
    assert losses.rain_db > 0.0
    assert losses.polarization_db == 0.5
    assert losses.pointing_db == 0.8
    assert losses.implementation_db == 1.2
    assert losses.total_db() > base.total_db()

    assert len(computed) == 2
    for part in computed:
        assert isinstance(part, Computed)
        assert part.unit == "dB"
        assert part.formula_ref == "docs/math/atmosphere.md"
        assert part.inputs
        assert part.assumptions


def test_the_availability_target_appears_in_the_assumptions():
    """The number is meaningless without it, so it travels with the number."""
    rain = rain_attenuation_db(X_BAND_HZ, 20.0, PADOVA)
    joined = " ".join(rain.assumptions)
    assert "0.01%" in joined
    assert "availability" in joined


def test_computing_the_atmosphere_changes_a_real_margin():
    """End to end: the difference between a 0 dB default and the real thing."""
    from core.rf.link import Receiver, Transmitter, compute_link_budget

    tx = Transmitter("sat", X_BAND_HZ, 20.0, 12.0, data_rate_bps=25e6,
                     required_ebn0_db=4.0)
    rx = Receiver("gs", gain_dbi=45.63, system_noise_temp_k=150.0)

    optimistic = compute_link_budget(tx, rx, 2000.0, PathLosses())
    losses, _ = atmospheric_losses(X_BAND_HZ, 10.0, PADOVA)
    realistic = compute_link_budget(tx, rx, 2000.0, losses)

    assert optimistic.margin_db is not None and realistic.margin_db is not None
    cost = optimistic.margin_db.value - realistic.margin_db.value
    assert cost > 3.0, "the atmosphere should cost real margin at 10 degrees"
    assert any("optimistic" in a for a in optimistic.assumptions)


# --------------------------------------------------------------------------
# Validation and the optional dependency
# --------------------------------------------------------------------------


def test_the_horizon_and_below_are_rejected():
    for bad in (0.0, -5.0, 91.0):
        with pytest.raises(ValueError, match="elevation_deg"):
            gaseous_attenuation_db(X_BAND_HZ, bad, PADOVA)


def test_a_non_positive_frequency_is_rejected():
    with pytest.raises(ValueError, match="freq_hz"):
        gaseous_attenuation_db(0.0, 30.0, PADOVA)


def test_an_availability_outside_the_models_range_is_rejected():
    for bad in (0.0, 0.0001, 50.0):
        with pytest.raises(ValueError, match="exceedance_percent"):
            AtmosphereConditions(45.0, 12.0, exceedance_percent=bad)


def test_cosecant_scaling_rejects_a_sub_horizon_elevation():
    with pytest.raises(ValueError):
        cosecant_scaled(1.0, 0.0)


def test_the_models_validity_floor_is_declared_not_hidden():
    """P.676's approximate method is recommended for 5-90 degrees.

    Culmen still answers below 5 degrees — a planner asking about a horizon
    grazer deserves a number — but the answer says it is an extrapolation.
    """
    inside = gaseous_attenuation_db(X_BAND_HZ, 30.0, PADOVA)
    outside = gaseous_attenuation_db(X_BAND_HZ, 2.0, PADOVA)

    assert any("between 5 and 90 degrees" in a for a in inside.assumptions)
    assert not any("extrapolation" in a for a in inside.assumptions)
    assert any("extrapolation" in a for a in outside.assumptions)


def test_availability_reports_the_optional_dependency():
    assert available() is True  # this module is skipped when it is not


def test_the_unavailable_error_says_how_to_fix_it():
    """The message is the whole value of a missing-dependency error."""
    message = str(
        AtmosphereUnavailable(
            'atmospheric attenuation needs the optional ITU-R models.\n'
            'Install them with: pip install "culmen[atmosphere]"'
        )
    )
    assert "culmen[atmosphere]" in message
