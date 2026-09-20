"""The data-population scripts.

Neither script is exercised against a live service here — the test suite is
offline by design, and a test that needs CelesTrak to be up is a test that
fails for reasons unrelated to the code. What *is* pinned is everything that
can go wrong without a network:

* the usage-policy guards actually refuse (no contact address, too soon since
  the last fetch, conditional-request headers present);
* the station converter never invents a coordinate, and reports what it
  mapped rather than assuming;
* generated station definitions load back through the real parser.

That last one matters: a converter whose output the loader rejects is a
converter that looked like it worked.
"""

from __future__ import annotations

import json
import time

import pytest

from core.geometry.definition import load_station, load_stations
from scripts.fetch_tle import (
    CacheEntry,
    PolicyError,
    build_request,
    count_element_sets,
    load_cache,
    save_cache,
    too_soon,
    user_agent,
)
from scripts.import_stations import (
    MappingError,
    build_mapping,
    convert,
    detect,
    load_rows,
    slugify,
    station_yaml,
)

# --------------------------------------------------------------------------
# fetch_tle: the policy guards
# --------------------------------------------------------------------------


def test_fetching_without_a_contact_address_is_refused():
    """An anonymous scraper is what rate limits exist to stop."""
    for bad in (None, "", "not-an-address"):
        with pytest.raises(PolicyError, match="CULMEN_CONTACT"):
            user_agent(bad)


def test_the_user_agent_identifies_the_tool_and_a_contact():
    ua = user_agent("someone@example.org")
    assert ua.startswith("Culmen/")
    assert "someone@example.org" in ua


def test_a_recent_fetch_of_the_same_group_must_wait():
    now = time.time()
    fresh = CacheEntry(fetched_at=now - 60, etag=None, last_modified=None, satellites=10)
    assert too_soon(fresh, now, 3600) == pytest.approx(3540, abs=1)

    old = CacheEntry(fetched_at=now - 7200, etag=None, last_modified=None, satellites=10)
    assert too_soon(old, now, 3600) == 0.0
    assert too_soon(None, now, 3600) == 0.0


def test_a_cached_response_produces_a_conditional_request():
    """An unchanged group must cost a 304, not a payload."""
    entry = CacheEntry(
        fetched_at=time.time(),
        etag='W/"abc123"',
        last_modified="Wed, 21 Oct 2026 07:28:00 GMT",
        satellites=42,
    )
    request = build_request("stations", entry, "someone@example.org")
    assert request.get_header("If-none-match") == 'W/"abc123"'
    assert request.get_header("If-modified-since") == "Wed, 21 Oct 2026 07:28:00 GMT"
    assert "Culmen/" in (request.get_header("User-agent") or "")


def test_a_first_fetch_sends_no_conditional_headers():
    request = build_request("stations", None, "someone@example.org")
    assert request.get_header("If-none-match") is None
    assert request.get_header("If-modified-since") is None


def test_the_request_asks_for_the_modern_gp_endpoint():
    request = build_request("cubesat", None, "someone@example.org")
    assert "gp.php" in request.full_url
    assert "GROUP=cubesat" in request.full_url
    assert "FORMAT=tle" in request.full_url


def test_element_sets_are_counted_from_line_ones(verification_tles):
    text = "\n".join(f"NAME\n{t.line1}\n{t.line2}" for t in verification_tles[:5])
    assert count_element_sets(text) == 5
    assert count_element_sets("") == 0


def test_the_cache_round_trips(tmp_path):
    cache = {
        "stations": CacheEntry(1234.5, 'W/"x"', "Wed, 21 Oct 2026 07:28:00 GMT", 7),
    }
    save_cache(tmp_path, cache)
    back = load_cache(tmp_path)
    assert back["stations"].etag == 'W/"x"'
    assert back["stations"].satellites == 7


def test_a_corrupt_cache_is_ignored_rather_than_fatal(tmp_path):
    (tmp_path / ".fetch-cache.json").write_text("{not json")
    assert load_cache(tmp_path) == {}


# --------------------------------------------------------------------------
# import_stations: never invent a coordinate
# --------------------------------------------------------------------------

ROWS = [
    {"name": "Alpha", "lat": 45.4064, "lng": 11.8768, "altitude": 12, "status": "Online"},
    {"name": "Bravo", "lat": -42.88, "lng": 147.33, "altitude": 10, "status": "Offline"},
    {"name": "No coords", "lat": None, "lng": None, "altitude": 0, "status": "Online"},
    {"name": "Impossible", "lat": 120.0, "lng": 11.0, "altitude": 0, "status": "Online"},
]


def test_field_detection_reports_the_key_it_found():
    mapping = build_mapping(ROWS, _args())
    assert (mapping.name, mapping.lat, mapping.lon, mapping.alt) == (
        "name",
        "lat",
        "lng",
        "altitude",
    )


def test_unmappable_data_fails_loudly_listing_the_keys_present():
    with pytest.raises(MappingError) as exc:
        build_mapping([{"foo": 1, "bar": 2}], _args())
    assert "latitude" in str(exc.value)
    assert "foo" in str(exc.value)  # tells you what you do have


def test_explicit_flags_override_detection():
    rows = [{"title": "X", "y_deg": 1.0, "x_deg": 2.0}]
    mapping = build_mapping(
        rows, _args(name_field="title", lat_field="y_deg", lon_field="x_deg")
    )
    assert mapping.lat == "y_deg"


def test_rows_without_usable_coordinates_are_skipped_not_guessed(tmp_path):
    written, skipped = convert(
        ROWS,
        build_mapping(ROWS, _args()),
        tmp_path,
        min_elevation_deg=10.0,
        source="test.json",
        attribution=None,
        limit=None,
        only_online=False,
        dry_run=False,
    )
    assert written == 2
    assert any("missing or not numeric" in s for s in skipped)
    assert any("out of range" in s for s in skipped)


def test_only_online_filters_on_the_status_field(tmp_path):
    written, skipped = convert(
        ROWS,
        build_mapping(ROWS, _args()),
        tmp_path,
        min_elevation_deg=10.0,
        source="test.json",
        attribution=None,
        limit=None,
        only_online=True,
        dry_run=False,
    )
    assert written == 1
    assert any("status" in s for s in skipped)


def test_generated_definitions_load_through_the_real_parser(tmp_path):
    convert(
        ROWS,
        build_mapping(ROWS, _args()),
        tmp_path,
        min_elevation_deg=7.5,
        source="test.json",
        attribution="SatNOGS Network, CC BY-SA 4.0",
        limit=None,
        only_online=False,
        dry_run=False,
    )
    stations = load_stations(tmp_path)
    assert {s.name for s in stations} == {"Alpha", "Bravo"}
    alpha = next(s for s in stations if s.name == "Alpha")
    assert alpha.lat_deg == pytest.approx(45.4064)
    assert alpha.lon_deg == pytest.approx(11.8768)
    assert alpha.min_elevation_deg == pytest.approx(7.5)


def test_attribution_is_written_into_every_file(tmp_path):
    convert(
        ROWS[:1],
        build_mapping(ROWS, _args()),
        tmp_path,
        min_elevation_deg=10.0,
        source="satnogs.json",
        attribution="SatNOGS Network, CC BY-SA 4.0",
        limit=None,
        only_online=False,
        dry_run=False,
    )
    text = (tmp_path / "alpha.yaml").read_text()
    assert "CC BY-SA 4.0" in text
    assert "satnogs.json" in text
    # The honest caveat must survive too.
    assert "NOT been" in text and "verified" in text


def test_a_dry_run_writes_nothing(tmp_path):
    written, _ = convert(
        ROWS,
        build_mapping(ROWS, _args()),
        tmp_path,
        min_elevation_deg=10.0,
        source="t",
        attribution=None,
        limit=None,
        only_online=False,
        dry_run=True,
    )
    assert written == 2
    assert list(tmp_path.iterdir()) == []


def test_duplicate_names_do_not_overwrite_each_other(tmp_path):
    rows = [
        {"name": "Same", "lat": 1.0, "lng": 2.0},
        {"name": "Same", "lat": 3.0, "lng": 4.0},
    ]
    convert(
        rows,
        build_mapping(rows, _args()),
        tmp_path,
        min_elevation_deg=10.0,
        source="t",
        attribution=None,
        limit=None,
        only_online=False,
        dry_run=False,
    )
    assert {p.name for p in tmp_path.iterdir()} == {"same.yaml", "same-2.yaml"}


def test_a_paginated_api_shape_is_unwrapped(tmp_path):
    path = tmp_path / "page.json"
    path.write_text(json.dumps({"count": 2, "results": ROWS[:2]}))
    assert len(load_rows(path)) == 2


def test_a_json_object_with_no_array_fails_clearly(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"detail": "not found"}))
    with pytest.raises(MappingError, match="results/data"):
        load_rows(path)


def test_awkward_names_become_usable_filenames():
    assert slugify("KSAT Svalbard #2") == "ksat-svalbard-2"
    assert slugify("  ") == "station"
    assert slugify("Ünïcødé") == "n-c-d"


def test_detect_returns_none_when_nothing_matches():
    assert detect([{"zzz": 1}], ("a", "b")) is None


def test_the_yaml_is_valid_for_a_single_station(tmp_path):
    path = tmp_path / "one.yaml"
    path.write_text(
        station_yaml("Test", 1.5, -2.5, 30.0, 10.0, "src.json", "Some Source, CC BY-SA")
    )
    station = load_station(path)
    assert station.name == "Test"
    assert station.lon_deg == pytest.approx(-2.5)
    assert station.alt_m == pytest.approx(30.0)


def _args(**overrides):
    import argparse

    defaults = {
        "name_field": None,
        "lat_field": None,
        "lon_field": None,
        "alt_field": None,
        "min_elevation_field": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_stations_in_a_subdirectory_are_found(tmp_path):
    """Imported catalogues live in their own subdirectory; loading must reach it.

    The separation is a licensing one: a hand-written station is the user's
    own and belongs in git, while one derived from a CC BY-SA source is not.
    Keeping them apart is only useful if the loader still sees both.
    """
    (tmp_path / "mine.yaml").write_text(
        station_yaml("Mine", 1.0, 2.0, 0.0, 10.0, "hand-written", None)
    )
    imported = tmp_path / "imported"
    imported.mkdir()
    (imported / "theirs.yaml").write_text(
        station_yaml("Theirs", 3.0, 4.0, 0.0, 10.0, "cat.json", "Some Source, CC BY-SA")
    )

    names = {s.name for s in load_stations(tmp_path)}
    assert names == {"Mine", "Theirs"}


def test_the_importer_defaults_to_the_gitignored_subdirectory():
    from scripts.import_stations import DEFAULT_OUT

    assert DEFAULT_OUT.name == "imported"
    assert DEFAULT_OUT.parent.name == "stations"


def test_the_data_scripts_depend_on_nothing_but_the_standard_library():
    """They must run with the system interpreter, outside any virtualenv.

    Populating the catalogue is the first thing a new user does, often before
    the environment exists. A script that needed the venv would fail with
    'command not found: python' on macOS and look like a broken project.
    """
    import ast
    import sys
    from pathlib import Path

    stdlib = set(sys.stdlib_module_names)
    root = Path(__file__).resolve().parents[1]
    for name in ("fetch_tle.py", "import_stations.py"):
        path = root / "scripts" / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        outside = sorted(m for m in imported if m not in stdlib)
        assert not outside, f"{name} imports non-stdlib modules: {outside}"


def test_the_data_scripts_are_executable():
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("fetch_tle.py", "import_stations.py"):
        path = root / "scripts" / name
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
        assert os.access(path, os.X_OK), f"{name} is not executable"
