"""Culmen command-line interface.

Deliberately thin: it parses arguments, calls ``core`` and formats the result.
No science happens here. Its second job is to keep ``core`` honest -- anything
the CLI cannot do without a database or a web framework does not belong in
``core``.

Usage::

    python -m cli passes --station data/stations/padova.yaml \\
        --tle data/tle/example.tle --start 2026-09-09T00:00:00Z --hours 24
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from core.geometry.definition import load_station
from core.orbit.propagator import Propagator
from core.orbit.tle import parse_tle_text
from core.passes.finder import find_passes
from core.time.scales import UTC, add_seconds, ensure_utc


def _parse_instant(text: str) -> datetime:
    """Parse an ISO-8601 instant. A timezone is required -- no guessing."""
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return ensure_utc(value)


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s"


def cmd_passes(args: argparse.Namespace) -> int:
    station = load_station(args.station)
    tles = parse_tle_text(Path(args.tle).read_text(encoding="utf-8"), source=str(args.tle))
    if args.norad_id is not None:
        tles = [t for t in tles if t.norad_id == args.norad_id]
        if not tles:
            print(f"no element set for NORAD {args.norad_id} in {args.tle}", file=sys.stderr)
            return 2

    start = _parse_instant(args.start) if args.start else datetime.now(UTC)
    end = add_seconds(start, args.hours * 3600.0)

    print(
        f"Station : {station.name} "
        f"({station.lat_deg:+.4f}, {station.lon_deg:+.4f}, {station.alt_m:.0f} m), "
        f"mask {station.min_elevation_deg:.1f} deg"
    )
    print(f"Window  : {start:%Y-%m-%d %H:%M:%SZ} -> {end:%Y-%m-%d %H:%M:%SZ}")
    print()

    total = 0
    for tle in tles:
        prop = Propagator(tle)
        passes = find_passes(station, prop, start, end, coarse_step_s=args.step_s)
        label = tle.name or f"NORAD {tle.norad_id}"
        print(f"{label}  (TLE epoch {tle.epoch_utc:%Y-%m-%d %H:%M:%SZ})")
        if not passes:
            print("  no passes above the mask in this window")
            print()
            continue
        for i, p in enumerate(passes, start=1):
            print(
                f"  #{i:<3} {p.aos_utc:%d %b %H:%M:%S} -> {p.los_utc:%H:%M:%S}  "
                f"{_format_duration(p.duration_s):>9}  "
                f"max el {p.max_elevation_deg:5.1f} deg  "
                f"az {p.aos_az_deg:5.1f} -> {p.los_az_deg:5.1f}  "
                f"TLE age {p.tle_age_days:+.1f} d"
            )
            for warning in p.warnings:
                print(f"       ! {warning}")
        total += len(passes)
        print()

    print(f"{total} pass(es) found.")
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    station = load_station(args.station)
    tles = parse_tle_text(Path(args.tle).read_text(encoding="utf-8"), source=str(args.tle))
    tle = next((t for t in tles if args.norad_id in (None, t.norad_id)), None)
    if tle is None:
        print(f"no element set for NORAD {args.norad_id}", file=sys.stderr)
        return 2

    prop = Propagator(tle)
    start = _parse_instant(args.start)
    end = add_seconds(start, args.minutes * 60.0)
    from core.passes.finder import sample_window

    print("time_utc,az_deg,el_deg,range_km,range_rate_km_s")
    for s in sample_window(station, prop, start, end, args.step_s):
        print(
            f"{s.t_utc:%Y-%m-%dT%H:%M:%S}Z,{s.az_deg:.4f},{s.el_deg:.4f},"
            f"{s.range_km:.4f},{s.range_rate_km_s:.6f}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="culmen",
        description="Satellite / ground-station contact planning and validation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("passes", help="list visibility windows in a time range")
    p.add_argument("--station", required=True, help="ground station definition (YAML)")
    p.add_argument("--tle", required=True, help="TLE file (2LE or 3LE)")
    p.add_argument("--norad-id", type=int, default=None, help="restrict to one satellite")
    p.add_argument("--start", default=None, help="ISO-8601 start instant (default: now)")
    p.add_argument("--hours", type=float, default=24.0, help="window length in hours")
    p.add_argument("--step-s", type=float, default=30.0, help="coarse search step in seconds")
    p.set_defaults(func=cmd_passes)

    t = sub.add_parser("timeline", help="print az/el/range samples as CSV")
    t.add_argument("--station", required=True)
    t.add_argument("--tle", required=True)
    t.add_argument("--norad-id", type=int, default=None)
    t.add_argument("--start", required=True, help="ISO-8601 start instant")
    t.add_argument("--minutes", type=float, default=15.0)
    t.add_argument("--step-s", type=float, default=10.0)
    t.set_defaults(func=cmd_timeline)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
