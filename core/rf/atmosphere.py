"""Atmospheric attenuation: ITU-R P.676 (gases) and P.618 (rain).

Until now these were inputs with a 0 dB default (A-RF-1), which made every
budget optimistic by whatever the caller failed to supply. This module
computes them.

**It does not reimplement the Recommendations.** P.676 rests on tables of
spectroscopic line data for oxygen and water vapour, and P.618 on rainfall
maps; transcribing either from memory would produce numbers that look
authoritative and are wrong. Instead this wraps `ITU-Rpy
<https://github.com/inigodelportillo/ITU-Rpy>`_, an independent implementation
of the Recommendations, and Culmen's own tests check the *physics* of what
comes back — the cosecant law with elevation, monotonicity with frequency,
the rain/gas ratio at each band — rather than asserting magic constants.

ITU-Rpy is an **optional** dependency::

    pip install "culmen[atmosphere]"

Without it, these functions raise :class:`AtmosphereUnavailable` with that
instruction, and the losses stay inputs exactly as before. ``core`` still
imports and runs with nothing installed beyond its own requirements
(ADR 0001), which is why the import happens inside the functions.

A correction worth stating plainly, because this project's own documentation
had it wrong: at **8.2 GHz** gaseous absorption is *small* — about 0.05 dB at
the zenith and 0.26 dB at 10 degrees elevation. What is large at X-band is
**rain**: about 5.5 dB at 10 degrees for the 0.01% worst-case year in a
temperate climate. Lumping the two together as "several dB of atmosphere"
misattributes an order of magnitude.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any

from core.provenance import Computed
from core.rf.link import PathLosses

#: Sea-level reference conditions, ITU-R P.835 mean annual global reference
#: atmosphere. Overridable: a site with a known local profile should use it.
DEFAULT_PRESSURE_HPA = 1013.25
DEFAULT_TEMPERATURE_K = 288.15
DEFAULT_WATER_VAPOUR_DENSITY_G_M3 = 7.5

#: Percentage of an average year for which the rain attenuation is *exceeded*.
#: 0.01% corresponds to 99.99% availability, the usual design point for a
#: commercial link. A planning tool must state which one it used: the number
#: changes by several dB between 0.1% and 0.001%.
DEFAULT_EXCEEDANCE_PERCENT = 0.01

#: ITU-R P.676's approximate slant-path method is recommended for elevations
#: between 5 and 90 degrees. Below that it still returns a number, and Culmen
#: still returns it — with an extra assumption saying it is an extrapolation.
#: Hiding the limit would be worse than a low-elevation estimate.
GASEOUS_MIN_ELEVATION_DEG = 5.0


class AtmosphereUnavailable(RuntimeError):
    """The optional ITU-R model dependency is not installed."""


def _require_itur() -> Any:
    try:
        import itur  # noqa: PLC0415  (deliberately lazy: keeps core dependency-light)
    except ImportError as exc:  # pragma: no cover - exercised by a skip
        raise AtmosphereUnavailable(
            "atmospheric attenuation needs the optional ITU-R models.\n"
            'Install them with: pip install "culmen[atmosphere]"\n'
            "Until then, supply atmospheric_db and rain_db yourself; leaving "
            "them at 0 dB is optimistic and is flagged in the budget's "
            "assumptions."
        ) from exc
    return itur


def available() -> bool:
    """True when the optional models are installed."""
    try:
        _require_itur()
    except AtmosphereUnavailable:
        return False
    return True


@dataclass(frozen=True, slots=True)
class AtmosphereConditions:
    """Site and climate inputs the ITU-R models need."""

    lat_deg: float
    lon_deg: float
    alt_km: float = 0.0
    pressure_hpa: float = DEFAULT_PRESSURE_HPA
    temperature_k: float = DEFAULT_TEMPERATURE_K
    water_vapour_g_m3: float = DEFAULT_WATER_VAPOUR_DENSITY_G_M3
    exceedance_percent: float = DEFAULT_EXCEEDANCE_PERCENT

    def __post_init__(self) -> None:
        if not 0.001 <= self.exceedance_percent <= 5.0:
            raise ValueError(
                "exceedance_percent must be between 0.001 and 5 "
                f"(ITU-R P.618's validity range), got {self.exceedance_percent}"
            )

    @property
    def availability_percent(self) -> float:
        return 100.0 - self.exceedance_percent


def gaseous_attenuation_db(
    freq_hz: float,
    elevation_deg: float,
    conditions: AtmosphereConditions,
) -> Computed[float]:
    """Slant-path attenuation by oxygen and water vapour, ITU-R P.676.

    Small at X-band and below, dominant near the 22 GHz water-vapour and
    60 GHz oxygen lines. Scales essentially as 1/sin(elevation) away from the
    horizon, which the tests check rather than assume.
    """
    _validate(freq_hz, elevation_deg)
    itur = _require_itur()

    assumptions = [
        "ITU-R P.676 gaseous absorption, computed by ITU-Rpy",
        "the approximate slant-path method is recommended for elevations "
        "between 5 and 90 degrees",
        "surface meteorology assumed constant over the path; a site with a "
        "measured profile should supply its own",
        "no time statistics: this is the mean condition, not a worst case",
    ]
    if elevation_deg < GASEOUS_MIN_ELEVATION_DEG:
        assumptions.append(
            f"elevation {elevation_deg} deg is below the approximate method's "
            f"{GASEOUS_MIN_ELEVATION_DEG} deg validity floor; the figure is an "
            "extrapolation and understates the true path length"
        )

    with warnings.catch_warnings():
        # ITU-Rpy warns about its own validity range, including at exactly
        # 90 degrees (its test is `el % 90 < 5`, and 90 % 90 == 0). We state
        # the range in `assumptions` instead, where it travels with the number.
        warnings.simplefilter("ignore", RuntimeWarning)
        value = float(
            itur.models.itu676.gaseous_attenuation_slant_path(
                f=freq_hz / 1e9,
                el=elevation_deg,
                rho=conditions.water_vapour_g_m3,
                P=conditions.pressure_hpa,
                T=conditions.temperature_k,
            ).value
        )
    return Computed(
        value=value,
        unit="dB",
        formula_ref="docs/math/atmosphere.md",
        inputs={
            "freq_hz": freq_hz,
            "elevation_deg": elevation_deg,
            "water_vapour_g_m3": conditions.water_vapour_g_m3,
            "pressure_hpa": conditions.pressure_hpa,
            "temperature_k": conditions.temperature_k,
        },
        assumptions=tuple(assumptions),
    )


def rain_attenuation_db(
    freq_hz: float,
    elevation_deg: float,
    conditions: AtmosphereConditions,
) -> Computed[float]:
    """Rain attenuation exceeded for ``exceedance_percent`` of an average year.

    This is a **statistical** quantity, and the percentage is part of the
    answer: at X-band in a temperate climate the 0.1% and 0.01% figures differ
    by several dB. A margin quoted without its availability figure is not a
    margin.
    """
    _validate(freq_hz, elevation_deg)
    itur = _require_itur()

    value = float(
        itur.models.itu618.rain_attenuation(
            lat=conditions.lat_deg,
            lon=conditions.lon_deg,
            f=freq_hz / 1e9,
            el=elevation_deg,
            hs=conditions.alt_km,
            p=conditions.exceedance_percent,
        ).value
    )
    return Computed(
        value=value,
        unit="dB",
        formula_ref="docs/math/atmosphere.md",
        inputs={
            "freq_hz": freq_hz,
            "elevation_deg": elevation_deg,
            "lat_deg": conditions.lat_deg,
            "lon_deg": conditions.lon_deg,
            "alt_km": conditions.alt_km,
            "exceedance_percent": conditions.exceedance_percent,
        },
        assumptions=(
            "ITU-R P.618 rain attenuation, computed by ITU-Rpy",
            f"exceeded for {conditions.exceedance_percent}% of an average year "
            f"({conditions.availability_percent}% availability); a different "
            f"availability target gives a materially different number",
            "rainfall statistics from the ITU-R maps for this location, not "
            "from local measurements",
            "long-term statistics: this says nothing about any particular pass",
        ),
    )


def atmospheric_losses(
    freq_hz: float,
    elevation_deg: float,
    conditions: AtmosphereConditions,
    base: PathLosses | None = None,
) -> tuple[PathLosses, tuple[Computed[float], ...]]:
    """Fill in the atmospheric terms of a :class:`PathLosses`.

    Returns the losses and the two computed quantities, so the budget can keep
    their provenance rather than swallowing two bare floats.

    Anything already set in ``base`` for the non-atmospheric terms is kept;
    ``atmospheric_db`` and ``rain_db`` are replaced.
    """
    gas = gaseous_attenuation_db(freq_hz, elevation_deg, conditions)
    rain = rain_attenuation_db(freq_hz, elevation_deg, conditions)
    base = base or PathLosses()

    return (
        PathLosses(
            atmospheric_db=gas.value,
            rain_db=rain.value,
            polarization_db=base.polarization_db,
            pointing_db=base.pointing_db,
            ionospheric_db=base.ionospheric_db,
            implementation_db=base.implementation_db,
        ),
        (gas, rain),
    )


def _validate(freq_hz: float, elevation_deg: float) -> None:
    if freq_hz <= 0.0:
        raise ValueError(f"freq_hz must be positive, got {freq_hz}")
    if not 0.0 < elevation_deg <= 90.0:
        raise ValueError(
            "elevation_deg must be in (0, 90]: the models are undefined at and "
            f"below the horizon, got {elevation_deg}"
        )
    if freq_hz > 1_000e9:
        raise ValueError("the ITU-R models used here are defined up to 1000 GHz")


def cosecant_scaled(zenith_db: float, elevation_deg: float) -> float:
    """Zenith attenuation projected onto a slant path: ``A / sin(el)``.

    The flat-Earth approximation the ITU-R models themselves use away from the
    horizon. Exposed because the tests compare the model against it — if the
    two ever diverge at high elevation, something is wrong with the wiring.
    """
    if not 0.0 < elevation_deg <= 90.0:
        raise ValueError("elevation_deg must be in (0, 90]")
    return zenith_db / math.sin(math.radians(elevation_deg))
