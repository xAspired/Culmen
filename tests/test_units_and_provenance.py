"""Decibel conversions, constants and the provenance wrapper.

These are the foundations the Phase 5 link budget will be built on, so they
are pinned now against known values rather than after the RF code exists.
The 10·log₁₀ / 20·log₁₀ distinction and the dBi/dBd offset are pinned
explicitly: both are standard sources of multi-dB errors.
"""

from __future__ import annotations

import math

import pytest

from core.provenance import Computed
from core.units import (
    BOLTZMANN_DBW_HZ_K,
    SPEED_OF_LIGHT_M_S,
    WGS84_A_M,
    WGS84_B_M,
    WGS84_E2,
    db10,
    db20,
    dbd_to_dbi,
    dbi_to_dbd,
    dbm_to_dbw,
    dbw_to_dbm,
    dbw_to_w,
    undb10,
    w_to_dbw,
    wavelength_m,
)


def test_boltzmann_in_db_is_the_textbook_value():
    """k = −228.6 dBW/(Hz·K) is the constant every link budget starts from."""
    assert pytest.approx(-228.599, abs=1e-3) == BOLTZMANN_DBW_HZ_K


def test_power_and_amplitude_decibels_are_distinct():
    """Confusing 10·log₁₀ with 20·log₁₀ doubles the error in dB."""
    assert db10(2.0) == pytest.approx(3.0103, abs=1e-4)
    assert db20(2.0) == pytest.approx(6.0206, abs=1e-4)
    assert db20(2.0) == pytest.approx(2.0 * db10(2.0))
    assert db10(1.0) == 0.0
    assert db10(100.0) == pytest.approx(20.0)


def test_decibel_round_trip():
    for ratio in (1e-6, 0.5, 1.0, 3.7, 1e6):
        assert undb10(db10(ratio)) == pytest.approx(ratio, rel=1e-12)


def test_non_positive_ratios_are_rejected_rather_than_returning_nan():
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            db10(bad)
        with pytest.raises(ValueError):
            db20(bad)


def test_watt_and_dbw_conversions():
    assert w_to_dbw(1.0) == pytest.approx(0.0)
    assert w_to_dbw(20.0) == pytest.approx(13.0103, abs=1e-4)
    assert dbw_to_w(13.0103) == pytest.approx(20.0, rel=1e-4)


def test_dbw_and_dbm_differ_by_exactly_30():
    assert dbw_to_dbm(0.0) == 30.0
    assert dbm_to_dbw(30.0) == 0.0


def test_dbi_and_dbd_differ_by_the_dipole_gain():
    assert dbi_to_dbd(12.0) == pytest.approx(9.85)
    assert dbd_to_dbi(9.85) == pytest.approx(12.0)


def test_wavelength_at_a_known_frequency():
    """8.2 GHz (X-band downlink) has a wavelength of about 36.6 mm."""
    assert wavelength_m(8.2e9) == pytest.approx(0.03656, abs=1e-5)
    assert wavelength_m(SPEED_OF_LIGHT_M_S) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        wavelength_m(0.0)


def test_wgs84_constants_are_self_consistent():
    assert pytest.approx(6_356_752.314_245, abs=1e-6) == WGS84_B_M
    assert pytest.approx(
        (WGS84_A_M**2 - WGS84_B_M**2) / WGS84_A_M**2, rel=1e-12
    ) == WGS84_E2
    assert math.isclose(WGS84_E2, 6.694_379_990_14e-3, rel_tol=1e-9)


# --- provenance ------------------------------------------------------------


def test_computed_carries_its_audit_trail():
    c = Computed(
        value=-172.4,
        unit="dB",
        formula_ref="docs/math/fspl.md",
        inputs={"range_km": 2000.0, "freq_hz": 8.2e9},
        assumptions=("free space, no atmosphere",),
    )
    assert c.value == -172.4
    payload = c.to_dict()
    assert payload["unit"] == "dB"
    assert payload["formula_ref"] == "docs/math/fspl.md"
    assert payload["inputs"]["range_km"] == 2000.0
    assert payload["assumptions"] == ["free space, no atmosphere"]


def test_computed_is_immutable():
    c = Computed(value=1.0, unit="dB", formula_ref="docs/math/fspl.md")
    with pytest.raises((AttributeError, TypeError)):
        c.value = 2.0  # type: ignore[misc]


def test_computed_refuses_to_exist_without_unit_or_source():
    with pytest.raises(ValueError, match="unit"):
        Computed(value=1.0, unit="", formula_ref="docs/math/fspl.md")
    with pytest.raises(ValueError, match="formula_ref"):
        Computed(value=1.0, unit="dB", formula_ref="")
