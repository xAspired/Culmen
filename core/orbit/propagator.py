"""SGP4 propagation.

Critical point, and the single most common error in this domain:

    SGP4 does NOT return J2000/GCRS coordinates. It returns TEME
    (True Equator, Mean Equinox) of date, and it is NOT ECEF either.

Treating TEME as an inertial J2000 frame introduces an error of order the
equation of the equinoxes; treating it as Earth-fixed is catastrophically
wrong. The TEME -> ITRF conversion needs GMST plus polar motion. Skyfield's
``EarthSatellite`` performs TEME -> GCRS -> ITRF correctly, so we build on it
rather than re-deriving the rotations by hand.

Reference: Vallado, Crawford, Hujsak & Kelso, "Revisiting Spacetrack Report #3"
(AIAA 2006-6753), section on coordinate systems.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from skyfield.api import EarthSatellite, wgs84
from skyfield.framelib import itrs
from skyfield.timelib import Time

from core.orbit.tle import Tle
from core.time.scales import UTC, timescale, to_times

PROPAGATOR_VERSION = "sgp4/skyfield-1.55"


@dataclass(frozen=True, slots=True)
class SatelliteState:
    """Instantaneous satellite state.

    ``*_teme_*`` is the raw SGP4 output frame, kept so the propagator can be
    checked against published TEME test vectors. ``*_itrf_*`` is Earth-fixed
    (ITRF/ECEF). Latitude is WGS84 *geodetic*, not geocentric.
    """

    t_utc: datetime
    position_teme_km: tuple[float, float, float]
    velocity_teme_km_s: tuple[float, float, float]
    position_itrf_km: tuple[float, float, float]
    velocity_itrf_km_s: tuple[float, float, float]
    lat_deg: float
    lon_deg: float
    alt_km: float
    propagator_version: str = PROPAGATOR_VERSION


class PropagationError(RuntimeError):
    """SGP4 reported a non-recoverable condition (decay, bad elements, ...)."""


def _leap_seconds(t: Time) -> np.ndarray | float:
    """TAI - UTC at ``t``, in seconds.

    Skyfield exposes this only privately. It is needed by the epoch-relative
    propagation path below, which must reproduce Skyfield's own UTC fraction
    bit-for-bit; the fallback keeps that path working (with microsecond-level
    representation noise) should the private helper disappear.
    """
    helper = getattr(t, "_leap_seconds", None)
    if helper is None:  # pragma: no cover - depends on the Skyfield version
        return 0.0
    return np.asarray(helper(), dtype=float)


def _as_2d(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    return a.reshape(3, 1) if a.ndim == 1 else a


class Propagator:
    """Wrapper around one element set. Holds no mutable state between calls."""

    def __init__(self, tle: Tle) -> None:
        self.tle = tle
        self._sat = EarthSatellite(
            tle.line1, tle.line2, tle.name or str(tle.norad_id), timescale()
        )

    @property
    def norad_id(self) -> int:
        return self.tle.norad_id

    @property
    def skyfield_satellite(self) -> EarthSatellite:
        """Handle for the geometry layer, which forms topocentric differences."""
        return self._sat

    # --- propagation ----------------------------------------------------
    def state_at(self, t_utc: datetime) -> SatelliteState:
        return self.states_at([t_utc])[0]

    def states_at(self, times: list[datetime]) -> list[SatelliteState]:
        return self.states_over(to_times(list(times)))

    def states_at_minutes_from_epoch(self, minutes: list[float]) -> list[SatelliteState]:
        """Propagate by minutes since the element-set epoch.

        This is the form SGP4 is natively defined in, and the form the official
        verification vectors use.

        Two precision details, both deliberate. The offset is applied to the
        two-part Julian date (whole day + fraction) rather than round-tripping
        through ``datetime``, whose microsecond truncation would inject a
        ~40 us time error. And it is applied on the *TAI* fraction, because
        that is the representation SGP4 is ultimately fed (per AIAA 2006-6753
        the TLE epoch is a UTC date, which Skyfield derives from TAI minus
        leap seconds); offsetting a different scale's fraction leaves a
        microsecond-level residual that is physically irrelevant but large
        enough to obscure a real defect at verification tolerance.
        """
        ts = timescale()
        model = self._sat.model
        whole = model.jdsatepoch
        # The UTC day-fraction SGP4 must receive, exactly as the element set
        # stores it, offset by the requested minutes.
        target_utc_fraction = model.jdsatepochF + np.asarray(minutes, dtype=float) / 1440.0
        # Skyfield hands SGP4 ``t.tai_fraction - leap_seconds/86400``, so build
        # the Time on TAI with the leap seconds added back in. Resolved in two
        # steps because the leap-second count is itself a function of the time.
        provisional = ts.tai_jd(whole, target_utc_fraction)
        leap_days = _leap_seconds(provisional) / 86400.0
        return self.states_over(ts.tai_jd(whole, target_utc_fraction + leap_days))

    def states_over(self, t: Time) -> list[SatelliteState]:
        """Vectorised: takes a Skyfield ``Time`` (scalar or array)."""
        p_teme, v_teme, errors = self._sat._position_and_velocity_TEME_km(t)
        self._raise_on_error(errors)

        geocentric = self._sat.at(t)
        p_itrf, v_itrf = geocentric.frame_xyz_and_velocity(itrs)
        sub = wgs84.geographic_position_of(geocentric)

        p_teme, v_teme = _as_2d(p_teme), _as_2d(v_teme)
        p_e, v_e = _as_2d(p_itrf.km), _as_2d(v_itrf.km_per_s)
        lats = np.atleast_1d(sub.latitude.degrees)
        lons = np.atleast_1d(sub.longitude.degrees)
        alts = np.atleast_1d(sub.elevation.km)

        dts = t.utc_datetime()
        dts = [dts] if isinstance(dts, datetime) else list(dts)

        return [
            SatelliteState(
                t_utc=dt.replace(tzinfo=UTC),
                position_teme_km=(float(p_teme[0, i]), float(p_teme[1, i]), float(p_teme[2, i])),
                velocity_teme_km_s=(float(v_teme[0, i]), float(v_teme[1, i]), float(v_teme[2, i])),
                position_itrf_km=(float(p_e[0, i]), float(p_e[1, i]), float(p_e[2, i])),
                velocity_itrf_km_s=(float(v_e[0, i]), float(v_e[1, i]), float(v_e[2, i])),
                lat_deg=float(lats[i]),
                lon_deg=float(lons[i]),
                alt_km=float(alts[i]),
            )
            for i, dt in enumerate(dts)
        ]

    def _raise_on_error(self, errors: object) -> None:
        """Skyfield reports SGP4 failures as message strings (None when fine)."""
        for msg in np.atleast_1d(np.asarray(errors, dtype=object)):
            if msg:
                raise PropagationError(f"SGP4 failed for NORAD {self.tle.norad_id}: {msg}")
