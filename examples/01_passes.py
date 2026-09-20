"""End-to-end example: find passes and print a timeline.

Runs entirely offline against the bundled historical element sets.

    python examples/01_passes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run straight from a checkout without installing the package first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.geometry.definition import load_station
from core.orbit.propagator import Propagator
from core.orbit.tle import parse_tle_text
from core.passes.finder import find_passes

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    station = load_station(ROOT / "data/stations/padova.yaml")
    tles = parse_tle_text((ROOT / "data/tle/example-leo.tle").read_text())
    tle = next(t for t in tles if t.norad_id == 28057)
    prop = Propagator(tle)

    start = tle.epoch_utc
    end = start.replace(hour=23, minute=59)
    passes = find_passes(station, prop, start, end)

    print(f"{station.name}: {len(passes)} pass(es) for NORAD {tle.norad_id}\n")
    if not passes:
        return

    best = max(passes, key=lambda p: p.max_elevation_deg)
    print(
        f"Highest pass: {best.aos_utc:%Y-%m-%d %H:%M:%S}Z -> {best.los_utc:%H:%M:%S}Z, "
        f"{best.duration_s / 60:.1f} min, peak {best.max_elevation_deg:.1f} deg"
    )
    print(f"TLE age at AOS: {best.tle_age_days:+.2f} days")
    for w in best.warnings:
        print(f"  ! {w}")

    print("\n  time        az      el    range_km   range_rate_km_s")
    for s in best.timeline(station, prop, step_s=60.0):
        print(
            f"  {s.t_utc:%H:%M:%S}  {s.az_deg:6.1f}  {s.el_deg:5.1f}  "
            f"{s.range_km:9.1f}   {s.range_rate_km_s:+8.3f}"
        )


if __name__ == "__main__":
    main()
