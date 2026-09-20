"""Physical constants and decibel conversions.

Naming convention (non-negotiable across the whole codebase):
every numeric name carries its unit suffix, e.g. range_km, freq_hz,
power_dbw, gain_dbi, el_deg.

Sources:
  - CODATA 2018 for c and k_B (exact by SI definition since 2019).
  - WGS84 ellipsoid parameters: NIMA TR8350.2, 3rd ed.
"""

from __future__ import annotations

import math

# --- Physical constants (SI, exact) ---
SPEED_OF_LIGHT_M_S: float = 299_792_458.0
BOLTZMANN_J_K: float = 1.380_649e-23
BOLTZMANN_DBW_HZ_K: float = 10.0 * math.log10(BOLTZMANN_J_K)  # -228.5991... dBW/(Hz.K)

# --- WGS84 ellipsoid ---
WGS84_A_M: float = 6_378_137.0
WGS84_F: float = 1.0 / 298.257_223_563
WGS84_B_M: float = WGS84_A_M * (1.0 - WGS84_F)
WGS84_E2: float = WGS84_F * (2.0 - WGS84_F)

# --- Earth rotation ---
EARTH_ROTATION_RATE_RAD_S: float = 7.292_115_146_706_979e-5  # IERS, rad/s (UT1)


# --- Decibel helpers ---
def db10(ratio: float) -> float:
    """Power ratio -> dB. 10*log10. Use for powers, gains, noise, bandwidths."""
    if ratio <= 0.0:
        raise ValueError(f"db10 requires a strictly positive ratio, got {ratio}")
    return 10.0 * math.log10(ratio)


def undb10(db: float) -> float:
    """dB -> power ratio."""
    return float(10.0 ** (db / 10.0))


def db20(ratio: float) -> float:
    """Amplitude/field ratio -> dB. 20*log10. NEVER use for powers."""
    if ratio <= 0.0:
        raise ValueError(f"db20 requires a strictly positive ratio, got {ratio}")
    return 20.0 * math.log10(ratio)


def dbw_to_dbm(dbw: float) -> float:
    return dbw + 30.0


def dbm_to_dbw(dbm: float) -> float:
    return dbm - 30.0


def w_to_dbw(watt: float) -> float:
    return db10(watt)


def dbw_to_w(dbw: float) -> float:
    return undb10(dbw)


def dbi_to_dbd(dbi: float) -> float:
    """Isotropic-referenced -> half-wave-dipole-referenced. dBd = dBi - 2.15."""
    return dbi - 2.15


def dbd_to_dbi(dbd: float) -> float:
    return dbd + 2.15


def wavelength_m(freq_hz: float) -> float:
    if freq_hz <= 0.0:
        raise ValueError(f"freq_hz must be positive, got {freq_hz}")
    return SPEED_OF_LIGHT_M_S / freq_hz
