"""Topocentric geometry, checked against an INDEPENDENT implementation.

The production path (``core.geometry.station.look_angles``) goes through
Skyfield's topocentric machinery. To prove that path is right rather than
merely self-consistent, this module re-derives azimuth, elevation and range
from the ITRF state vectors by a completely different route:

    ITRF station position (Bowring/closed-form geodetic -> ECEF)
    -> line-of-sight vector in ECEF
    -> rotation into the local East-North-Up frame
    -> az = atan2(E, N), el = asin(U / |r|)

The two routes share no code beyond the ITRF state itself, so agreement to
sub-milli-degree means both the frame conversion and the topocentric
reduction are correct.

The module also pins the geodetic-vs-geocentric latitude distinction, which is
the second classic error in this domain.
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pytest

from core.geometry.station import GroundStation, look_angles
from core.orbit.propagator import PropagationError, Propagator
from core.time.scales import UTC, add_seconds
from core.units import WGS84_A_M, WGS84_B_M, WGS84_E2

ANGLE_TOL_DEG = 1e-4
RANGE_TOL_KM = 1e-6


def geodetic_to_ecef_km(lat_deg: float, lon_deg: float, alt_m: float) -> np.ndarray:
    """WGS84 geodetic -> ECEF, closed form. Reference: Vallado, Alg. 51."""
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    sin_lat = math.sin(lat)
    n = WGS84_A_M / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * math.cos(lat) * math.cos(lon)
    y = (n + alt_m) * math.cos(lat) * math.sin(lon)
    z = (n * (1.0 - WGS84_E2) + alt_m) * sin_lat
    return np.array([x, y, z]) / 1000.0


def ecef_to_geodetic(x_km: float, y_km: float, z_km: float) -> tuple[float, float, float]:
    """ECEF -> WGS84 geodetic, Bowring's method. Reference: Bowring (1976)."""
    a, b = WGS84_A_M, WGS84_B_M
    x, y, z = x_km * 1000.0, y_km * 1000.0, z_km * 1000.0
    ep2 = (a * a - b * b) / (b * b)
    p = math.hypot(x, y)
    theta = math.atan2(z * a, p * b)
    lat = math.atan2(
        z + ep2 * b * math.sin(theta) ** 3,
        p - WGS84_E2 * a * math.cos(theta) ** 3,
    )
    lon = math.atan2(y, x)
    n = a / math.sqrt(1.0 - WGS84_E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), alt / 1000.0


def look_angles_reference(
    station: GroundStation, sat_itrf_km: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Independent az/el/range via an explicit ECEF -> ENU rotation."""
    r_station = geodetic_to_ecef_km(station.lat_deg, station.lon_deg, station.alt_m)
    d = np.asarray(sat_itrf_km) - r_station

    lat, lon = math.radians(station.lat_deg), math.radians(station.lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    east = np.array([-sin_lon, cos_lon, 0.0])
    north = np.array([-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat])
    up = np.array([cos_lat * cos_lon, cos_lat * sin_lon, sin_lat])

    e, n, u = float(d @ east), float(d @ north), float(d @ up)
    rng = float(np.linalg.norm(d))
    az = math.degrees(math.atan2(e, n)) % 360.0
    el = math.degrees(math.asin(u / rng))
    return az, el, rng


# --- geodetic vs geocentric ------------------------------------------------


def test_geodetic_and_geocentric_latitude_differ_by_up_to_about_0p19_deg():
    """The classic 21 km trap: the two latitudes are NOT interchangeable."""
    worst = 0.0
    for lat_deg in np.arange(-90.0, 90.001, 0.5):
        r = geodetic_to_ecef_km(float(lat_deg), 0.0, 0.0)
        geocentric = math.degrees(math.atan2(r[2], math.hypot(r[0], r[1])))
        worst = max(worst, abs(float(lat_deg) - geocentric))
    assert 0.185 < worst < 0.195, f"max geodetic-geocentric difference was {worst} deg"


def test_geodetic_round_trip_is_stable():
    for lat, lon, alt in [(45.4064, 11.8768, 12.0), (-42.88, 147.33, 10.0), (78.23, 15.41, 458.0)]:
        x, y, z = geodetic_to_ecef_km(lat, lon, alt)
        got_lat, got_lon, got_alt_km = ecef_to_geodetic(x, y, z)
        assert got_lat == pytest.approx(lat, abs=1e-9)
        assert got_lon == pytest.approx(lon, abs=1e-9)
        assert got_alt_km * 1000.0 == pytest.approx(alt, abs=1e-6)


def test_station_itrf_position_matches_independent_conversion(stations):
    for st in stations:
        expected = geodetic_to_ecef_km(st.lat_deg, st.lon_deg, st.alt_m)
        got = np.asarray(st.position_itrf_km)
        assert np.allclose(got, expected, atol=1e-6), f"{st.name}: ITRF position mismatch"


# --- look angles -----------------------------------------------------------


def test_look_angles_match_independent_enu_derivation(leo_tle, stations):
    prop = Propagator(leo_tle)
    times = [add_seconds(leo_tle.epoch_utc, 60.0 * k) for k in range(0, 180, 7)]
    try:
        states = prop.states_at(times)
    except PropagationError as exc:  # pragma: no cover
        pytest.skip(f"element set not propagable: {exc}")

    for station in stations:
        samples = look_angles(station, prop, times)
        assert len(samples) == len(states)
        for sample, state in zip(samples, states, strict=True):
            az, el, rng = look_angles_reference(station, state.position_itrf_km)
            assert sample.range_km == pytest.approx(rng, rel=RANGE_TOL_KM)
            assert sample.el_deg == pytest.approx(el, abs=ANGLE_TOL_DEG)
            # Azimuth is ill-conditioned near the zenith; skip it there.
            if abs(sample.el_deg) < 89.0:
                delta = abs((sample.az_deg - az + 180.0) % 360.0 - 180.0)
                assert delta < ANGLE_TOL_DEG, f"{station.name}: azimuth off by {delta} deg"


def test_range_rate_matches_numerical_derivative_of_range(leo_tle, padova):
    """Range rate must be the time derivative of range, not a re-derived guess."""
    prop = Propagator(leo_tle)
    t0 = add_seconds(leo_tle.epoch_utc, 600.0)
    dt = 0.5
    before, at, after = look_angles(
        padova, prop, [t0 - timedelta(seconds=dt), t0, t0 + timedelta(seconds=dt)]
    )
    numerical = (after.range_km - before.range_km) / (2.0 * dt)
    assert at.range_rate_km_s == pytest.approx(numerical, abs=1e-4)


def test_elevation_is_geometric_not_refracted(leo_tle, padova):
    """We promise geometric elevation; a refraction model would bias it upward.

    Near the horizon, refraction would add roughly +0.5 deg. Comparing against
    the purely geometric ENU derivation confirms no such model is applied.
    """
    prop = Propagator(leo_tle)
    times = [add_seconds(leo_tle.epoch_utc, 30.0 * k) for k in range(240)]
    samples = look_angles(padova, prop, times)
    states = prop.states_at(times)
    low = [
        (s, st)
        for s, st in zip(samples, states, strict=True)
        if -1.0 < s.el_deg < 5.0
    ]
    if not low:
        pytest.skip("no near-horizon samples in this window")
    for sample, state in low:
        _, el_ref, _ = look_angles_reference(padova, state.position_itrf_km)
        assert sample.el_deg == pytest.approx(el_ref, abs=ANGLE_TOL_DEG)


def test_station_rejects_impossible_coordinates():
    with pytest.raises(ValueError):
        GroundStation("bad", 91.0, 0.0)
    with pytest.raises(ValueError):
        GroundStation("bad", 0.0, 0.0, min_elevation_deg=90.0)


def test_times_must_be_timezone_aware(leo_tle, padova):
    prop = Propagator(leo_tle)
    naive = leo_tle.epoch_utc.replace(tzinfo=None)
    with pytest.raises(ValueError):
        look_angles(padova, prop, [naive])
    assert leo_tle.epoch_utc.tzinfo is UTC
