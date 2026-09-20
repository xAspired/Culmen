#!/usr/bin/env python3
"""Convert a JSON list of ground stations into Culmen station definitions.

Why this takes a **file** rather than fetching an API itself: the station
catalogues worth importing (SatNOGS Network, an operator's own inventory) have
schemas this project cannot verify from here, and a converter written against
a guessed schema is a converter that silently produces wrong coordinates. A
station misplaced by 0.1 degrees is 11 km, which moves every azimuth and
elevation it produces.

So the mapping is explicit and inspectable:

    # see what you actually have
    python scripts/import_stations.py stations.json --inspect

    # convert, naming the fields
    python scripts/import_stations.py stations.json \\
        --name-field name --lat-field lat --lon-field lng --alt-field altitude \\
        --attribution "SatNOGS Network, CC BY-SA 4.0"

Output goes to ``data/stations/imported/``, which is gitignored. Stations you
write by hand live in ``data/stations/`` itself and are yours to commit: the
two are kept apart because their licensing differs.

``--inspect`` prints the keys present and a sample row, so the flags can be
filled in from the data rather than from an assumption. Common spellings are
tried automatically and the script **reports which one it used**; anything it
cannot map is skipped and listed, never guessed.

Attribution is mandatory when the source requires it: SatNOGS data is
CC BY-SA, so the obligation travels with the data. The attribution string is
written into every generated file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "stations" / "imported"

#: Field spellings seen in the wild, tried in order. Reported, never silent.
NAME_KEYS = ("name", "station_name", "title", "label", "id", "identifier")
LAT_KEYS = ("lat", "latitude", "lat_deg", "latitude_deg")
LON_KEYS = ("lng", "lon", "long", "longitude", "lon_deg", "longitude_deg")
ALT_KEYS = ("altitude", "alt", "elevation", "alt_m", "altitude_m", "elevation_m")
STATUS_KEYS = ("status", "state")
#: The station's own elevation mask, when the source carries one. SatNOGS
#: calls it ``min_horizon``. Using it beats a flat default: the mask is a
#: property of the site's terrain and hardware, not of our preference.
MIN_EL_KEYS = ("min_horizon", "min_elevation_deg", "min_elevation", "horizon")
#: Antenna coverage, recorded as a comment: the station schema has no field
#: for it yet, and dropping it silently would lose the one datum that decides
#: the frequency-compatibility check.
ANTENNA_KEYS = ("antenna", "antennas", "rf_bands")


@dataclass(frozen=True, slots=True)
class Mapping:
    name: str
    lat: str
    lon: str
    alt: str | None
    min_elevation: str | None = None
    antenna: str | None = None


class MappingError(RuntimeError):
    pass


def detect(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    """First key from ``keys`` that appears in the data. No inference beyond this."""
    present = {k for row in rows[:50] for k in row}
    for key in keys:
        if key in present:
            return key
    return None


def build_mapping(rows: list[dict[str, Any]], args: argparse.Namespace) -> Mapping:
    name = args.name_field or detect(rows, NAME_KEYS)
    lat = args.lat_field or detect(rows, LAT_KEYS)
    lon = args.lon_field or detect(rows, LON_KEYS)
    alt = args.alt_field or detect(rows, ALT_KEYS)

    missing = [
        label
        for label, value in (("name", name), ("latitude", lat), ("longitude", lon))
        if value is None
    ]
    if missing:
        keys = sorted({k for row in rows[:50] for k in row})
        raise MappingError(
            f"could not find a field for: {', '.join(missing)}.\n"
            f"Keys present in the data: {', '.join(keys) or '(none)'}\n"
            f"Name them explicitly with --name-field / --lat-field / --lon-field."
        )
    assert name and lat and lon
    return Mapping(
        name=name,
        lat=lat,
        lon=lon,
        alt=alt,
        min_elevation=args.min_elevation_field or detect(rows, MIN_EL_KEYS),
        antenna=detect(rows, ANTENNA_KEYS),
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "station"


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # reject NaN


def describe_antennas(value: Any) -> str:
    """One line naming the bands an antenna list covers, for the comment.

    Only what the data says: band labels when present, otherwise the
    frequency range in MHz. Nothing is inferred.
    """
    if not isinstance(value, list) or not value:
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        band = item.get("band")
        lo = to_float(item.get("frequency"))
        hi = to_float(item.get("frequency_max"))
        if band:
            parts.append(str(band))
        elif lo is not None and hi is not None:
            parts.append(f"{lo / 1e6:.0f}-{hi / 1e6:.0f} MHz")
        elif lo is not None:
            parts.append(f"{lo / 1e6:.0f} MHz")
    unique = list(dict.fromkeys(parts))
    return ", ".join(unique)


def station_yaml(
    name: str,
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
    min_elevation_deg: float,
    source: str,
    attribution: str | None,
    antennas: str = "",
) -> str:
    lines = [
        "schema_version: 1",
        f"name: {json.dumps(name)}",
        "location:",
        f"  lat_deg: {lat_deg:.6f}",
        f"  lon_deg: {lon_deg:.6f}",
        f"  alt_m: {alt_m:.1f}",
        f"min_elevation_deg: {min_elevation_deg}",
        "",
        f"# Imported from {source} by scripts/import_stations.py.",
    ]
    if antennas:
        lines.append(
            f"# Antenna coverage reported by the source: {antennas}. The station"
        )
        lines.append(
            "# definition format has no field for this yet; supply it to the"
        )
        lines.append("# validator as AntennaConstraints when checking a contact.")
    if attribution:
        lines.append(f"# Attribution: {attribution}")
        lines.append(
            "# The licence of the source data travels with this file; see "
            "data/README.md."
        )
    lines.append(
        "# Coordinates are as supplied by the source and have NOT been "
        "independently verified."
    )
    return "\n".join(lines) + "\n"


def convert(
    rows: list[dict[str, Any]],
    mapping: Mapping,
    out_dir: Path,
    *,
    min_elevation_deg: float,
    source: str,
    attribution: str | None,
    limit: int | None,
    only_online: bool,
    dry_run: bool,
) -> tuple[int, list[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped: list[str] = []
    seen: set[str] = set()

    for row in rows:
        if limit is not None and written >= limit:
            break

        raw_name = row.get(mapping.name)
        name = str(raw_name).strip() if raw_name is not None else ""
        if not name:
            skipped.append("(unnamed row)")
            continue

        if only_online:
            status_key = detect([row], STATUS_KEYS)
            status = str(row.get(status_key, "")).lower() if status_key else ""
            if status and status not in {"online", "active", "1", "true"}:
                skipped.append(f"{name}: status {status!r}")
                continue

        lat = to_float(row.get(mapping.lat))
        lon = to_float(row.get(mapping.lon))
        if lat is None or lon is None:
            skipped.append(f"{name}: latitude or longitude missing or not numeric")
            continue
        if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
            skipped.append(f"{name}: coordinates out of range ({lat}, {lon})")
            continue

        alt = to_float(row.get(mapping.alt)) if mapping.alt else 0.0
        if alt is None:
            alt = 0.0

        # Prefer the station's own mask over our default, when it has one and
        # it is usable. A mask at or above 90 degrees would make the station
        # see nothing, so it is rejected rather than carried over.
        mask = min_elevation_deg
        if mapping.min_elevation:
            supplied = to_float(row.get(mapping.min_elevation))
            if supplied is not None and 0.0 <= supplied < 90.0:
                mask = supplied

        antennas = (
            describe_antennas(row.get(mapping.antenna)) if mapping.antenna else ""
        )

        slug = slugify(name)
        candidate = slug
        suffix = 2
        while candidate in seen:
            candidate = f"{slug}-{suffix}"
            suffix += 1
        seen.add(candidate)

        if not dry_run:
            (out_dir / f"{candidate}.yaml").write_text(
                station_yaml(
                    name, lat, lon, alt, mask, source, attribution, antennas
                ),
                encoding="utf-8",
            )
        written += 1

    return written, skipped


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Tolerate the two shapes a paginated API produces.
    if isinstance(data, dict):
        for key in ("results", "data", "stations", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise MappingError(
                "the JSON is an object, not a list, and has no results/data/"
                "stations/items array"
            )
    if not isinstance(data, list):
        raise MappingError("expected a JSON array of station objects")
    rows = [r for r in data if isinstance(r, dict)]
    if not rows:
        raise MappingError("no station objects found")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a JSON station list into Culmen station definitions.",
    )
    parser.add_argument("input", type=Path, help="JSON file to convert")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--inspect", action="store_true",
                        help="print the keys present and a sample row, then exit")
    parser.add_argument("--name-field")
    parser.add_argument("--lat-field")
    parser.add_argument("--lon-field")
    parser.add_argument("--alt-field")
    parser.add_argument(
        "--min-elevation-deg", type=float, default=10.0,
        help="fallback mask when the source carries none (default 10)",
    )
    parser.add_argument(
        "--min-elevation-field",
        help="field holding each station's own mask; auto-detected "
             f"from {', '.join(MIN_EL_KEYS)}",
    )
    parser.add_argument("--attribution",
                        help="required by CC BY-SA sources such as SatNOGS")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only-online", action="store_true",
                        help="keep only rows whose status field reads online/active")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        rows = load_rows(args.input)
    except (MappingError, json.JSONDecodeError, OSError) as exc:
        print(f"cannot read {args.input}: {exc}", file=sys.stderr)
        return 2

    if args.inspect:
        keys = sorted({k for row in rows[:200] for k in row})
        print(f"{len(rows)} row(s); keys present:")
        for key in keys:
            print(f"  {key}")
        print("\nfirst row:")
        print(json.dumps(rows[0], indent=2, default=str)[:2000])
        return 0

    try:
        mapping = build_mapping(rows, args)
    except MappingError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(
        f"mapping: name={mapping.name}  lat={mapping.lat}  lon={mapping.lon}  "
        f"alt={mapping.alt or '(none, using 0 m)'}  "
        f"mask={mapping.min_elevation or f'(none, using {args.min_elevation_deg})'}"
    )

    written, skipped = convert(
        rows,
        mapping,
        args.out,
        min_elevation_deg=args.min_elevation_deg,
        source=str(args.input),
        attribution=args.attribution,
        limit=args.limit,
        only_online=args.only_online,
        dry_run=args.dry_run,
    )

    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} station definition(s) to {args.out}")
    if skipped:
        print(f"skipped {len(skipped)}:")
        for reason in skipped[:20]:
            print(f"  {reason}")
        if len(skipped) > 20:
            print(f"  ... and {len(skipped) - 20} more")

    if not args.attribution:
        print(
            "\nNo --attribution given. If the source requires attribution "
            "(SatNOGS is CC BY-SA), re-run with it: the obligation travels with "
            "the data, not with Culmen's code.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
