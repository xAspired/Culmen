"""Ground Station Definition format (YAML/JSON).

The definition file is the project's own small de-facto standard: a user must
be able to add a station without touching code. It is versioned from the very
first file so it can evolve without breaking existing definitions.

Example::

    schema_version: 1
    name: Padova
    location:
      lat_deg: 45.4064
      lon_deg: 11.8768
      alt_m: 12.0
    min_elevation_deg: 10.0
    # optional, not used by the V1 geometry beyond the mask lookup:
    horizon_profile:
      - {az_deg: 0,   el_deg: 12.0}
      - {az_deg: 180, el_deg: 8.0}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.geometry.station import STATION_SCHEMA_VERSION, GroundStation, HorizonProfile


class StationDefinitionError(ValueError):
    """The definition file is missing required fields or uses a future schema."""


def station_from_dict(data: dict[str, Any]) -> GroundStation:
    version = int(data.get("schema_version", STATION_SCHEMA_VERSION))
    if version > STATION_SCHEMA_VERSION:
        raise StationDefinitionError(
            f"definition uses schema_version {version}, this build understands "
            f"up to {STATION_SCHEMA_VERSION}"
        )
    try:
        name = data["name"]
        loc = data["location"]
        lat_deg = float(loc["lat_deg"])
        lon_deg = float(loc["lon_deg"])
    except KeyError as exc:
        raise StationDefinitionError(f"missing required field: {exc.args[0]}") from exc

    profile_raw = data.get("horizon_profile") or []
    profile = HorizonProfile(
        tuple((float(p["az_deg"]), float(p["el_deg"])) for p in profile_raw)
    )

    return GroundStation(
        name=str(name),
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        alt_m=float(loc.get("alt_m", 0.0)),
        min_elevation_deg=float(data.get("min_elevation_deg", 10.0)),
        horizon_profile=profile,
        schema_version=version,
    )


#: The C loader when PyYAML was built with libyaml, the Python one otherwise.
#: A public catalogue is thousands of files and the difference is several
#: seconds of startup; behaviour is identical.
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def load_station(path: str | Path) -> GroundStation:
    data = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_LOADER)
    if not isinstance(data, dict):
        raise StationDefinitionError(f"{path}: expected a YAML mapping at the top level")
    return station_from_dict(data)


def load_stations(directory: str | Path) -> list[GroundStation]:
    """Load every definition under ``directory``, subdirectories included.

    Recursive on purpose: it lets imported catalogues live in their own
    subdirectory, separate from the definitions a user writes by hand. Those
    two have different licensing: a hand-written station is the user's own,
    while one derived from a CC BY-SA source carries that obligation with it
    and must not be committed alongside Apache-2.0 code (data/README.md).
    """
    paths = sorted(
        p for p in Path(directory).rglob("*") if p.suffix in {".yaml", ".yml"}
    )
    return [load_station(p) for p in paths]
