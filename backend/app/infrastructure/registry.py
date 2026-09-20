"""In-process registry of stations and element sets.

**Deliberately not a database** (ADR 0009). Stations come from the versioned
YAML definition format on disk; element sets are supplied by the caller and
held in memory for the life of the process.

Passes and contacts are *computed*, never stored: they are a cache of a
calculation whose inputs (the element set, the engine version) change, and a
cache that outlives its inputs is worse than no cache at all (ADR 0006).
"""

from __future__ import annotations

import threading
from pathlib import Path

from core.geometry.definition import load_stations
from core.geometry.station import GroundStation
from core.orbit.propagator import Propagator
from core.orbit.tle import Tle, TleError, parse_tle_text


class NotFound(KeyError):
    """A named station or satellite is not loaded."""


class Registry:
    """Thread-safe holder for stations and element sets."""

    def __init__(self, stations_dir: Path, tle_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._stations: dict[str, GroundStation] = {}
        self._tles: dict[int, Tle] = {}
        self._propagators: dict[int, Propagator] = {}
        self.stations_dir = stations_dir
        self.tle_dir = tle_dir
        self.reload_stations()
        if tle_dir is not None:
            self.load_tle_dir(tle_dir)

    def load_tle_dir(self, directory: Path) -> int:
        """Import every .tle file in a directory, at startup.

        Element sets are still never fetched from the network -- these are
        files the operator put on disk, exactly like the station definitions.
        It exists so a fresh `docker compose up` has something to show: the
        registry is in memory (ADR 0009), so without this every restart leaves
        the satellite list empty and the first run looks broken.

        A malformed file is skipped rather than fatal: one bad file must not
        stop the service from starting.
        """
        if not directory.is_dir():
            return 0
        count = 0
        for path in sorted(directory.glob("*.tle")):
            try:
                count += len(self.import_tles(path.read_text(encoding="utf-8"),
                                              source=str(path)))
            except (TleError, OSError):
                continue
        return count

    # --- stations -------------------------------------------------------
    def reload_stations(self) -> int:
        if not self.stations_dir.is_dir():
            return 0
        loaded = {s.name: s for s in load_stations(self.stations_dir)}
        with self._lock:
            self._stations = loaded
        return len(loaded)

    def stations(self) -> list[GroundStation]:
        with self._lock:
            return sorted(self._stations.values(), key=lambda s: s.name)

    def station(self, name: str) -> GroundStation:
        with self._lock:
            try:
                return self._stations[name]
            except KeyError:
                known = ", ".join(sorted(self._stations)) or "none loaded"
                raise NotFound(f"unknown station {name!r}; known: {known}") from None

    def add_station(self, station: GroundStation) -> None:
        with self._lock:
            self._stations[station.name] = station

    # --- satellites -----------------------------------------------------
    def import_tles(self, text: str, source: str | None = None) -> list[Tle]:
        parsed = parse_tle_text(text, source=source)
        with self._lock:
            for tle in parsed:
                # A newer element set replaces an older one for the same object.
                existing = self._tles.get(tle.norad_id)
                if existing is None or tle.epoch_utc >= existing.epoch_utc:
                    self._tles[tle.norad_id] = tle
                    self._propagators.pop(tle.norad_id, None)
        return parsed

    def satellites(self) -> list[Tle]:
        with self._lock:
            return sorted(self._tles.values(), key=lambda t: t.norad_id)

    def tle(self, norad_id: int) -> Tle:
        with self._lock:
            try:
                return self._tles[norad_id]
            except KeyError:
                known = ", ".join(str(n) for n in sorted(self._tles)) or "none loaded"
                raise NotFound(
                    f"no element set for NORAD {norad_id}; loaded: {known}"
                ) from None

    def propagator(self, norad_id: int) -> Propagator:
        """Propagators are cached: building one parses the element set."""
        tle = self.tle(norad_id)
        with self._lock:
            prop = self._propagators.get(norad_id)
            if prop is None:
                prop = Propagator(tle)
                self._propagators[norad_id] = prop
            return prop

    def clear_satellites(self) -> None:
        with self._lock:
            self._tles.clear()
            self._propagators.clear()
