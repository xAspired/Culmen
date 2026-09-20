"""Shared fixtures.

Note on test data: Culmen does not vendor element sets into the
repository. The tests read the verification set that ships with the ``sgp4``
package (Vallado's SGP4-VER.TLE), so there is nothing to keep up to date and
no third-party data redistribution question.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
import sgp4

from core.geometry.station import GroundStation
from core.orbit.tle import Tle, TleError, parse_tle_text

_SGP4_DIR = Path(os.path.dirname(sgp4.__file__))


def _verification_tles() -> list[Tle]:
    text = (_SGP4_DIR / "SGP4-VER.TLE").read_text()
    lines = [ln[:69] for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    out: list[Tle] = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].startswith("1 ") and lines[i + 1].startswith("2 "):
            with contextlib.suppress(TleError):
                out.append(Tle(lines[i], lines[i + 1]))
            i += 2
        else:
            i += 1
    return out


@pytest.fixture(scope="session")
def verification_tles() -> list[Tle]:
    return _verification_tles()


@pytest.fixture(scope="session")
def leo_tle(verification_tles) -> Tle:
    """A near-circular LEO element set, suitable for pass-finding tests."""
    candidates = [
        t
        for t in verification_tles
        if 13.0 <= t.mean_motion_rev_day <= 16.0 and t.eccentricity < 0.01
    ]
    assert candidates, "no near-circular LEO element set in the verification data"
    return candidates[0]


@pytest.fixture(scope="session")
def padova() -> GroundStation:
    from core.geometry.definition import load_station

    return load_station(Path(__file__).resolve().parents[1] / "data/stations/padova.yaml")


@pytest.fixture(scope="session")
def stations() -> list[GroundStation]:
    """A geographically spread set: equatorial, mid-latitude, polar, southern."""
    return [
        GroundStation("Equator", 0.0, 0.0, 0.0, min_elevation_deg=5.0),
        GroundStation("Padova", 45.4064, 11.8768, 12.0, min_elevation_deg=10.0),
        GroundStation("Svalbard", 78.2297, 15.4075, 458.0, min_elevation_deg=5.0),
        GroundStation("Hobart", -42.8821, 147.3272, 10.0, min_elevation_deg=10.0),
        GroundStation("Quito", -0.1807, -78.4678, 2850.0, min_elevation_deg=10.0),
    ]


__all__ = ["parse_tle_text"]
