"""Ground station model and topocentric geometry.

Two traps this module exists to avoid:

1. Geodetic vs geocentric latitude. They differ by up to ~0.19 deg (about
   21 km on the surface). A station's latitude as written on a map is WGS84
   *geodetic*; converting it as if it were geocentric puts the station in the
   wrong place. We use ``skyfield.api.wgs84``, which is geodetic throughout.

2. Refraction. Reported elevations here are *geometric*, with no atmospheric
   refraction applied. Near the horizon refraction raises the apparent
   elevation by roughly 0.5 deg; at a 10 deg mask the effect on AOS is a few
   seconds. Declared, not silently ignored: see docs/math/assumptions.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from skyfield.api import wgs84
from skyfield.timelib import Time
from skyfield.toposlib import GeographicPosition

from core.orbit.propagator import Propagator
from core.time.scales import UTC, to_times

#: Version of the ground-station definition file format.
STATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class HorizonProfile:
    """Azimuth-dependent horizon mask.

    V1 uses a constant mask everywhere; this type exists so the YAML format
    and the geometry API do not have to change when real terrain profiles
    arrive. ``samples`` is a sequence of (azimuth_deg, min_elevation_deg),
    interpolated linearly and wrapped at 360 deg.
    """

    samples: tuple[tuple[float, float], ...] = ()

    def min_elevation_deg(self, az_deg: float, default_deg: float) -> float:
        if not self.samples:
            return default_deg
        az = np.asarray([s[0] for s in self.samples], dtype=float)
        el = np.asarray([s[1] for s in self.samples], dtype=float)
        order = np.argsort(az)
        az, el = az[order], el[order]
        az_ext = np.concatenate([az, az[:1] + 360.0])
        el_ext = np.concatenate([el, el[:1]])
        return float(np.interp(az_deg % 360.0, az_ext, el_ext))


@dataclass(frozen=True, slots=True)
class GroundStation:
    """A ground station, located on the WGS84 ellipsoid."""

    name: str
    lat_deg: float
    lon_deg: float
    alt_m: float = 0.0
    min_elevation_deg: float = 10.0
    horizon_profile: HorizonProfile = field(default_factory=HorizonProfile)
    schema_version: int = STATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat_deg <= 90.0:
            raise ValueError(f"lat_deg out of range: {self.lat_deg}")
        if not -180.0 <= self.lon_deg <= 360.0:
            raise ValueError(f"lon_deg out of range: {self.lon_deg}")
        if not 0.0 <= self.min_elevation_deg < 90.0:
            raise ValueError(f"min_elevation_deg out of range: {self.min_elevation_deg}")

    @property
    def topos(self) -> GeographicPosition:
        """Skyfield geodetic position (WGS84)."""
        return wgs84.latlon(self.lat_deg, self.lon_deg, elevation_m=self.alt_m)

    @property
    def position_itrf_km(self) -> tuple[float, float, float]:
        xyz = self.topos.itrs_xyz.km
        return (float(xyz[0]), float(xyz[1]), float(xyz[2]))

    def mask_deg(self, az_deg: float) -> float:
        """Effective elevation mask in the given azimuth direction."""
        return self.horizon_profile.min_elevation_deg(az_deg, self.min_elevation_deg)


@dataclass(frozen=True, slots=True)
class TopocentricSample:
    """Look angles from a station to a satellite at one instant.

    Angles are geometric (no refraction). ``range_rate_km_s`` is positive when
    the satellite is receding; it is what drives the Doppler shift.
    """

    t_utc: datetime
    az_deg: float
    el_deg: float
    range_km: float
    range_rate_km_s: float


def look_angles(
    station: GroundStation, prop: Propagator, times: list[datetime]
) -> list[TopocentricSample]:
    """Topocentric look angles for a list of instants."""
    return look_angles_over(station, prop, to_times(list(times)))


def look_angles_over(
    station: GroundStation, prop: Propagator, t: Time
) -> list[TopocentricSample]:
    """Vectorised look angles over a Skyfield ``Time`` grid."""
    difference = prop.skyfield_satellite - station.topos
    topocentric = difference.at(t)
    el, az, dist = topocentric.altaz()  # geometric: no refraction model applied

    r = np.atleast_2d(topocentric.position.km.T).T
    v = np.atleast_2d(topocentric.velocity.km_per_s.T).T
    rng = np.atleast_1d(dist.km)
    range_rate = np.sum(r * v, axis=0) / rng

    dts = t.utc_datetime()
    dts = [dts] if isinstance(dts, datetime) else list(dts)

    az_deg = np.atleast_1d(az.degrees)
    el_deg = np.atleast_1d(el.degrees)

    return [
        TopocentricSample(
            t_utc=dt.replace(tzinfo=UTC),
            az_deg=float(az_deg[i] % 360.0),
            el_deg=float(el_deg[i]),
            range_km=float(rng[i]),
            range_rate_km_s=float(range_rate[i]),
        )
        for i, dt in enumerate(dts)
    ]
