"""Pass finding: AOS, LOS, maximum elevation, duration.

Method (deliberately boring and deterministic):

1. Evaluate elevation on a coarse uniform grid. The grid step must be well
   below the shortest possible pass; for LEO a 30 s step is safe (the shortest
   useful passes are minutes long), while a 1 s grid over 30 days x many
   satellites x many stations does not scale.
2. Where ``f(t) = elevation(t) - mask`` changes sign, bracket the root and
   refine it with Brent's method to sub-second precision. This gives AOS and
   LOS without needing a fine grid anywhere else.
3. Refine the maximum with a bounded golden-section search on ``-elevation``.

All refinement is done in **seconds relative to the window start**, never on
absolute Julian dates. Both ``brentq`` and ``minimize_scalar`` mix an absolute
and a *relative* tolerance, and a Julian date is of order 2.45e6: the relative
term alone then swamps the width of a pass, and the bounded minimiser returns
after a single iteration while reporting success. Working on small offsets
removes that failure mode entirely.

The elevation mask may be azimuth-dependent (horizon profile), so ``f`` is
evaluated with the mask looked up at the current azimuth rather than against
a fixed constant.

Elevations are geometric; refraction is not modelled (docs/math/assumptions.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from core.geometry.station import GroundStation, TopocentricSample, look_angles_over
from core.orbit.propagator import PROPAGATOR_VERSION, Propagator
from core.time.scales import ensure_utc, time_range, timescale, to_time

DEFAULT_COARSE_STEP_S: float = 30.0
#: Root-finding tolerance on AOS/LOS, in seconds.
_ROOT_XTOL_S: float = 1e-3
#: Tolerance for the maximum-elevation search, in seconds.
_PEAK_XTOL_S: float = 1e-3


@dataclass(frozen=True, slots=True)
class Pass:
    """A single visibility window above the station's elevation mask."""

    satellite_norad_id: int
    station_name: str
    aos_utc: datetime
    los_utc: datetime
    max_elevation_deg: float
    max_elevation_utc: datetime
    duration_s: float
    aos_az_deg: float
    los_az_deg: float
    max_el_az_deg: float
    tle_epoch_utc: datetime
    tle_age_days: float
    propagator_version: str
    warnings: tuple[str, ...] = ()

    def timeline(
        self, station: GroundStation, prop: Propagator, step_s: float = 10.0
    ) -> list[TopocentricSample]:
        """Az/el/range samples across the pass, endpoints included."""
        return sample_window(station, prop, self.aos_utc, self.los_utc, step_s)


def sample_window(
    station: GroundStation,
    prop: Propagator,
    start: datetime,
    end: datetime,
    step_s: float,
) -> list[TopocentricSample]:
    ts = timescale()
    t0, t1 = to_time(start).tt, to_time(end).tt
    n = max(int(np.ceil((t1 - t0) * 86400.0 / step_s)), 1)
    grid = ts.tt_jd(np.linspace(t0, t1, n + 1))
    return look_angles_over(station, prop, grid)


def find_passes(
    station: GroundStation,
    prop: Propagator,
    start: datetime,
    end: datetime,
    coarse_step_s: float = DEFAULT_COARSE_STEP_S,
) -> list[Pass]:
    """All passes whose elevation exceeds the station mask within the window.

    A pass already in progress at ``start``, or still in progress at ``end``,
    is returned clipped to the window and flagged in ``warnings``.
    """
    start, end = ensure_utc(start), ensure_utc(end)
    ts = timescale()
    grid = time_range(start, end, coarse_step_s)
    samples = look_angles_over(station, prop, grid)

    margin = np.array([s.el_deg - station.mask_deg(s.az_deg) for s in samples])
    jd = np.asarray(grid.tt, dtype=float)
    epoch_jd = float(jd[0])

    def at_offset(offset_s: float) -> TopocentricSample:
        """Look angles at ``offset_s`` seconds after the window start."""
        return look_angles_over(
            station, prop, ts.tt_jd(epoch_jd + float(offset_s) / 86400.0)
        )[0]

    def margin_at(offset_s: float) -> float:
        s = at_offset(offset_s)
        return float(s.el_deg - station.mask_deg(s.az_deg))

    def neg_el_at(offset_s: float) -> float:
        return float(-at_offset(offset_s).el_deg)

    offsets_s = (jd - epoch_jd) * 86400.0

    above = margin > 0.0
    if not above.any():
        return []

    # Contiguous runs of "above the mask" on the coarse grid.
    edges = np.flatnonzero(np.diff(above.astype(int)))
    starts = [0] if above[0] else []
    ends: list[int] = []
    for e in edges:
        if above[e + 1]:
            starts.append(int(e) + 1)
        else:
            ends.append(int(e))
    if above[-1]:
        ends.append(len(above) - 1)

    passes: list[Pass] = []
    for i0, i1 in zip(starts, ends, strict=True):
        warnings: list[str] = []

        if i0 == 0:
            aos_s = offsets_s[0]
            warnings.append("pass already in progress at window start; AOS clipped")
        else:
            aos_s = brentq(
                margin_at, offsets_s[i0 - 1], offsets_s[i0], xtol=_ROOT_XTOL_S
            )

        if i1 == len(offsets_s) - 1:
            los_s = offsets_s[-1]
            warnings.append("pass still in progress at window end; LOS clipped")
        else:
            los_s = brentq(
                margin_at, offsets_s[i1], offsets_s[i1 + 1], xtol=_ROOT_XTOL_S
            )

        peak = minimize_scalar(
            neg_el_at,
            bounds=(aos_s, los_s),
            method="bounded",
            options={"xatol": _PEAK_XTOL_S},
        )
        peak_s = float(peak.x)

        aos_look, peak_look, los_look = look_angles_over(
            station,
            prop,
            ts.tt_jd(epoch_jd + np.array([aos_s, peak_s, los_s]) / 86400.0),
        )

        tle_age = prop.tle.age_days(aos_look.t_utc)
        age_warn = prop.tle.age_warning(aos_look.t_utc)
        if age_warn:
            warnings.append(age_warn)

        passes.append(
            Pass(
                satellite_norad_id=prop.norad_id,
                station_name=station.name,
                aos_utc=aos_look.t_utc,
                los_utc=los_look.t_utc,
                max_elevation_deg=peak_look.el_deg,
                max_elevation_utc=peak_look.t_utc,
                duration_s=los_s - aos_s,
                aos_az_deg=aos_look.az_deg,
                los_az_deg=los_look.az_deg,
                max_el_az_deg=peak_look.az_deg,
                tle_epoch_utc=prop.tle.epoch_utc,
                tle_age_days=tle_age,
                propagator_version=PROPAGATOR_VERSION,
                warnings=tuple(warnings),
            )
        )
    return passes


__all__ = ["Pass", "find_passes", "sample_window", "DEFAULT_COARSE_STEP_S"]
