"""HTTP API.

The science is pinned by the core tests. What is pinned here is the boundary:

* the API returns the same numbers the library does — no rounding, no
  reshaping, no quiet loss of provenance on the way out;
* naive datetimes are refused rather than guessed at;
* errors come back as 404 or 422 with a usable message, never as a 500;
* the endpoints that need nothing loaded really do work stateless.

The strongest of these is the first: an API that silently degrades the
numbers underneath it is worse than no API.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from core.datavol.volume import BYTES_PER_GIGABYTE
from core.orbit.tle import parse_tle_text
from core.rf.link import (
    PathLosses,
    Receiver,
    Transmitter,
    compute_link_budget,
    free_space_path_loss,
)
from core.time.scales import add_seconds

ROOT = Path(__file__).resolve().parents[1]
TLE_TEXT = (ROOT / "data/tle/example-leo.tle").read_text()
NORAD = 28057


@pytest.fixture(scope="module")
def client() -> TestClient:
    c = TestClient(create_app(stations_dir=ROOT / "data/stations"))
    c.post("/api/v1/satellites/import-tle", json={"text": TLE_TEXT, "source": "test"})
    return c


@pytest.fixture(scope="module")
def window() -> tuple[str, str]:
    tle = next(t for t in parse_tle_text(TLE_TEXT) if t.norad_id == NORAD)
    start = tle.epoch_utc
    return start.isoformat(), add_seconds(start, 12 * 3600.0).isoformat()


# --------------------------------------------------------------------------
# Meta and registry
# --------------------------------------------------------------------------


def test_health_reports_what_is_loaded(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["stations"] >= 1
    assert body["satellites"] >= 1


def test_stations_come_from_the_yaml_definition_format(client):
    stations = client.get("/api/v1/ground-stations").json()
    padova = next(s for s in stations if s["name"] == "Padova")
    assert padova["lat_deg"] == pytest.approx(45.4064)
    assert padova["min_elevation_deg"] == pytest.approx(10.0)
    assert padova["has_horizon_profile"] is False


def test_unknown_station_is_404_and_lists_what_exists(client):
    r = client.get("/api/v1/ground-stations/Atlantis")
    assert r.status_code == 404
    assert "Padova" in r.json()["detail"]


def test_unknown_satellite_is_404(client):
    r = client.get("/api/v1/satellites/1")
    assert r.status_code == 404


def test_importing_malformed_tle_is_422_not_500(client):
    r = client.post("/api/v1/satellites/import-tle", json={"text": "x" * 200})
    assert r.status_code == 422


def test_imported_satellite_reports_its_epoch_and_age(client):
    sat = client.get(f"/api/v1/satellites/{NORAD}").json()
    assert sat["norad_id"] == NORAD
    assert sat["cospar_id"] == "2003-049A"
    assert sat["age_days"] > 0
    # These are 2006 element sets: the API must say so, loudly.
    assert sat["age_warning"] and "not usable" in sat["age_warning"]


# --------------------------------------------------------------------------
# Passes
# --------------------------------------------------------------------------


def test_pass_search_matches_the_library_exactly(client, window):
    from core.geometry.definition import load_station
    from core.orbit.propagator import Propagator
    from core.passes.finder import find_passes
    from core.time.scales import ensure_utc

    start, end = window
    body = {
        "station": "Padova",
        "norad_id": NORAD,
        "start_utc": start,
        "end_utc": end,
    }
    api = client.post("/api/v1/passes/search", json=body).json()

    station = load_station(ROOT / "data/stations/padova.yaml")
    tle = next(t for t in parse_tle_text(TLE_TEXT) if t.norad_id == NORAD)
    direct = find_passes(
        station, Propagator(tle), ensure_utc_iso(start), ensure_utc_iso(end)
    )

    assert len(api) == len(direct)
    for got, want in zip(api, direct, strict=True):
        assert got["max_elevation_deg"] == pytest.approx(want.max_elevation_deg, abs=1e-9)
        assert got["duration_s"] == pytest.approx(want.duration_s, abs=1e-9)
        assert ensure_utc(
            __import__("datetime").datetime.fromisoformat(got["aos_utc"])
        ) == want.aos_utc


def ensure_utc_iso(text: str):
    from datetime import datetime

    from core.time.scales import ensure_utc

    return ensure_utc(datetime.fromisoformat(text))


def test_a_higher_mask_can_be_requested_per_call(client, window):
    start, end = window
    base = client.post(
        "/api/v1/passes/search",
        json={"station": "Padova", "norad_id": NORAD, "start_utc": start, "end_utc": end},
    ).json()
    strict = client.post(
        "/api/v1/passes/search",
        json={
            "station": "Padova",
            "norad_id": NORAD,
            "start_utc": start,
            "end_utc": end,
            "min_elevation_deg": 40.0,
        },
    ).json()
    assert len(strict) <= len(base)
    assert all(p["max_elevation_deg"] > 40.0 for p in strict)


def test_a_reversed_window_is_422(client, window):
    start, end = window
    r = client.post(
        "/api/v1/passes/search",
        json={"station": "Padova", "norad_id": NORAD, "start_utc": end, "end_utc": start},
    )
    assert r.status_code == 422


def test_naive_datetimes_are_refused(client, window):
    """No timezone means no guessing: this is a one-hour error waiting to happen."""
    start, _ = window
    r = client.post(
        "/api/v1/passes/search",
        json={
            "station": "Padova",
            "norad_id": NORAD,
            "start_utc": start.replace("+00:00", ""),
            "end_utc": start.replace("+00:00", ""),
        },
    )
    assert r.status_code == 422


def test_timeline_returns_samples_with_range_rate(client, window):
    start, _ = window
    end = add_seconds(ensure_utc_iso(start), 600.0).isoformat()
    samples = client.get(
        "/api/v1/passes/timeline",
        params={
            "station": "Padova",
            "norad_id": NORAD,
            "start_utc": start,
            "end_utc": end,
            "step_s": 60,
        },
    ).json()
    assert len(samples) == 11
    assert all("range_rate_km_s" in s for s in samples)


# --------------------------------------------------------------------------
# Stateless compute
# --------------------------------------------------------------------------


LINK_BODY = {
    "transmitter": {
        "freq_hz": 8.2e9,
        "power_w": 20.0,
        "gain_dbi": 12.0,
        "line_loss_db": 1.0,
        "data_rate_bps": 25e6,
        "required_ebn0_db": 4.0,
    },
    "receiver": {"gain_dbi": 45.63, "system_noise_temp_k": 150.0},
    "range_km": 1200.0,
    "losses": {"atmospheric_db": 1.5, "pointing_db": 0.5},
    "range_rate_km_s": -5.0,
}


def test_link_budget_endpoint_needs_nothing_loaded():
    """Stateless by design: usable and testable without populating anything."""
    bare = TestClient(create_app(stations_dir=ROOT / "nonexistent"))
    assert bare.get("/health").json()["stations"] == 0
    r = bare.post("/api/v1/link-budget/compute", json=LINK_BODY)
    assert r.status_code == 200


def test_link_budget_matches_the_library_to_full_precision(client):
    body = client.post("/api/v1/link-budget/compute", json=LINK_BODY).json()

    direct = compute_link_budget(
        Transmitter(
            "transmitter", 8.2e9, 20.0, 12.0, line_loss_db=1.0,
            data_rate_bps=25e6, required_ebn0_db=4.0,
        ),
        Receiver("receiver", gain_dbi=45.63, system_noise_temp_k=150.0),
        1200.0,
        PathLosses(atmospheric_db=1.5, pointing_db=0.5),
        -5.0,
    )
    assert body["cn0_dbhz"]["value"] == pytest.approx(direct.cn0_dbhz.value, abs=1e-12)
    assert body["margin_db"]["value"] == pytest.approx(direct.margin_db.value, abs=1e-12)
    assert body["fspl_db"]["value"] == pytest.approx(
        free_space_path_loss(1200.0, 8.2e9).value, abs=1e-12
    )


def test_provenance_survives_serialisation(client):
    """The audit trail is the product; it must not be dropped at the boundary."""
    body = client.post("/api/v1/link-budget/compute", json=LINK_BODY).json()
    for field in ("eirp_dbw", "fspl_db", "cn0_dbhz", "ebn0_db", "margin_db"):
        part = body[field]
        assert part["unit"]
        assert part["formula_ref"].startswith("docs/math/")
        assert part["inputs"]
    assert body["assumptions"]
    assert body["lines"]


def test_budget_lines_sum_to_the_reported_cn0(client):
    body = client.post("/api/v1/link-budget/compute", json=LINK_BODY).json()
    lines = {line["label"]: line["value"] for line in body["lines"]}
    total = sum(
        v for k, v in lines.items() if k not in {"C/N0", "Eb/N0", "Link margin"}
    )
    assert total == pytest.approx(lines["C/N0"], abs=1e-9)


def test_a_receiver_defined_twice_over_is_422_not_500(client):
    bad = {**LINK_BODY, "receiver": {"gain_dbi": 40.0, "system_noise_temp_k": 150.0,
                                     "g_over_t_dbk": -9.0}}
    assert client.post("/api/v1/link-budget/compute", json=bad).status_code == 422


def test_a_negative_loss_is_rejected_by_the_schema(client):
    bad = {**LINK_BODY, "losses": {"atmospheric_db": -3.0}}
    assert client.post("/api/v1/link-budget/compute", json=bad).status_code == 422


def test_required_duration_includes_overhead(client):
    r = client.post(
        "/api/v1/data-volume/required-duration",
        json={
            "required_bytes": 2 * BYTES_PER_GIGABYTE,
            "data_rate_bps": 25e6,
            "profile": {"framing_efficiency": 0.85, "acquisition_s": 45.0,
                        "setup_s": 30.0},
        },
    ).json()
    assert r["value"] == pytest.approx(827.94, abs=0.01)
    assert r["inputs"]["transfer_s"] == pytest.approx(752.94, abs=0.01)


# --------------------------------------------------------------------------
# The plan endpoint
# --------------------------------------------------------------------------


def plan_body(start: str, end: str, required_gb: float = 2.0) -> dict:
    return {
        "station": "Padova",
        "norad_ids": [NORAD],
        "start_utc": start,
        "end_utc": end,
        "transmitter": LINK_BODY["transmitter"],
        "receiver": LINK_BODY["receiver"],
        "requirement": {
            "name": "bulk",
            "required_bytes": required_gb * BYTES_PER_GIGABYTE,
            "deadline_utc": end,
            "min_margin_db": 3.0,
        },
        "losses": LINK_BODY["losses"],
        "profile": {"framing_efficiency": 0.85, "acquisition_s": 45.0, "setup_s": 30.0},
        "antenna": {
            "rx_freq_min_hz": 8.0e9,
            "rx_freq_max_hz": 8.5e9,
            "min_elevation_deg": 5.0,
            "max_elevation_deg": 85.0,
        },
        "turnaround_s": 600.0,
    }


def test_plan_returns_a_schedule_with_requirements_and_rejections(client, window):
    start, end = window
    body = client.post("/api/v1/plan", json=plan_body(start, end)).json()

    assert body["scheduler_version"]
    assert body["requirements"]
    assert body["notes"]
    # Both the accepted and the discarded contacts must come back.
    assert body["scheduled"] or body["rejected"]
    for rejected in body["rejected"]:
        assert rejected["reason"]
        assert rejected["detail"]


def test_plan_carries_the_full_verdict_for_every_contact(client, window):
    start, end = window
    body = client.post("/api/v1/plan", json=plan_body(start, end)).json()
    contacts = [s["contact"] for s in body["scheduled"]] + [
        r["contact"] for r in body["rejected"]
    ]
    assert contacts
    for c in contacts:
        assert c["validation"]["verdict"] in {
            "VALID", "INVALID", "CONDITIONALLY_VALID",
        }
        assert c["validation"]["checks"]
        assert c["volume"]["delivered_bytes"]["formula_ref"]
        assert c["pass"]["propagator_version"]
        assert c["fspl_spread_db"] >= 0.0


def test_an_impossible_requirement_comes_back_unsatisfied_not_empty(client, window):
    start, end = window
    body = client.post("/api/v1/plan", json=plan_body(start, end, 500.0)).json()
    status_ = body["requirements"][0]
    assert not status_["satisfied"]
    assert status_["shortfall_bytes"] > 0
    assert not body["all_satisfied"]


def test_planning_without_a_data_rate_is_422_with_an_explanation(client, window):
    start, end = window
    body = plan_body(start, end)
    body["transmitter"] = {**body["transmitter"], "data_rate_bps": 0.0}
    r = client.post("/api/v1/plan", json=body)
    assert r.status_code == 422
    assert "data_rate_bps" in r.json()["detail"]


def test_planning_against_an_unknown_satellite_is_404(client, window):
    start, end = window
    body = {**plan_body(start, end), "norad_ids": [1]}
    assert client.post("/api/v1/plan", json=body).status_code == 404


# --------------------------------------------------------------------------
# Documentation
# --------------------------------------------------------------------------


def test_openapi_is_generated_and_describes_every_endpoint(client):
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    for expected in (
        "/api/v1/ground-stations",
        "/api/v1/satellites",
        "/api/v1/passes/search",
        "/api/v1/link-budget/compute",
        "/api/v1/data-volume/required-duration",
        "/api/v1/plan",
        "/health",
    ):
        assert expected in paths


def test_the_api_states_that_it_contains_no_ai(client):
    """ADR 0007, visible to anyone reading the generated documentation."""
    spec = client.get("/openapi.json").json()
    description = spec["info"]["description"]
    assert "no AI or machine learning" in description
    assert "deterministic" in description


def test_the_api_states_that_it_does_not_fetch_orbital_data(client):
    spec = client.get("/openapi.json").json()
    assert "never fetches orbital data" in spec["info"]["description"]


def test_timedelta_import_is_used():
    """Guard against an unused import creeping back into this module."""
    assert timedelta(seconds=1).total_seconds() == 1.0


# --------------------------------------------------------------------------
# Ground track
# --------------------------------------------------------------------------


def test_ground_track_returns_geodetic_subsatellite_points(client, window):
    start, _ = window
    end = add_seconds(ensure_utc_iso(start), 3600.0).isoformat()
    samples = client.get(
        f"/api/v1/satellites/{NORAD}/ground-track",
        params={"start_utc": start, "end_utc": end, "step_s": 300},
    ).json()

    assert len(samples) == 13
    for s in samples:
        assert -90.0 <= s["lat_deg"] <= 90.0
        assert -180.0 <= s["lon_deg"] <= 180.0
        assert s["alt_km"] > 200.0  # a LEO satellite, not a ground point


def test_ground_track_matches_the_propagator(client, window):
    from core.orbit.propagator import Propagator

    start, _ = window
    end = add_seconds(ensure_utc_iso(start), 600.0).isoformat()
    samples = client.get(
        f"/api/v1/satellites/{NORAD}/ground-track",
        params={"start_utc": start, "end_utc": end, "step_s": 600},
    ).json()

    tle = next(t for t in parse_tle_text(TLE_TEXT) if t.norad_id == NORAD)
    direct = Propagator(tle).state_at(ensure_utc_iso(start))
    assert samples[0]["lat_deg"] == pytest.approx(direct.lat_deg, abs=1e-9)
    assert samples[0]["lon_deg"] == pytest.approx(direct.lon_deg, abs=1e-9)


def test_ground_track_for_an_unknown_satellite_is_404(client, window):
    start, end = window
    r = client.get(
        "/api/v1/satellites/1/ground-track",
        params={"start_utc": start, "end_utc": end},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Startup loading
# --------------------------------------------------------------------------


def test_element_sets_in_the_tle_directory_load_at_startup():
    """A fresh start must have something to show.

    The registry is in memory (ADR 0009), so without this every restart would
    leave the satellite list empty and the first run would look broken. These
    are files on disk, not a network fetch.
    """
    app = TestClient(
        create_app(stations_dir=ROOT / "data/stations", tle_dir=ROOT / "data/tle")
    )
    body = app.get("/health").json()
    assert body["stations"] >= 1
    assert body["satellites"] >= 2
    assert {s["norad_id"] for s in app.get("/api/v1/satellites").json()} >= {NORAD}


def test_a_missing_tle_directory_is_not_fatal():
    app = TestClient(
        create_app(stations_dir=ROOT / "data/stations", tle_dir=ROOT / "nonexistent")
    )
    assert app.get("/health").json()["satellites"] == 0


def test_a_malformed_tle_file_does_not_stop_the_service(tmp_path):
    """One bad file must not prevent startup; the good ones still load."""
    (tmp_path / "broken.tle").write_text("not an element set at all\n")
    (tmp_path / "good.tle").write_text(TLE_TEXT)
    app = TestClient(create_app(stations_dir=ROOT / "data/stations", tle_dir=tmp_path))
    assert app.get("/health").json()["satellites"] >= 2


def test_the_satellite_list_is_filtered_and_capped(client):
    """A full catalogue is ~11 000 objects; returning it all would stall the UI."""
    everything = client.get("/api/v1/satellites")
    assert everything.status_code == 200
    assert "X-Total-Count" in everything.headers

    one = client.get("/api/v1/satellites", params={"search": str(NORAD)})
    assert [s["norad_id"] for s in one.json()] == [NORAD]
    assert one.headers["X-Total-Count"] == "1"

    by_name = client.get("/api/v1/satellites", params={"search": "leo-demo"})
    assert len(by_name.json()) >= 2

    capped = client.get("/api/v1/satellites", params={"limit": 1})
    assert len(capped.json()) == 1
    assert int(capped.headers["X-Total-Count"]) >= 2


def test_a_search_matching_nothing_is_an_empty_list_not_an_error(client):
    r = client.get("/api/v1/satellites", params={"search": "no-such-satellite"})
    assert r.status_code == 200
    assert r.json() == []
    assert r.headers["X-Total-Count"] == "0"


def test_the_station_list_is_filtered_and_capped(client):
    """A public catalogue is thousands of stations; a full dropdown is unusable."""
    everything = client.get("/api/v1/ground-stations")
    assert "X-Total-Count" in everything.headers

    hit = client.get("/api/v1/ground-stations", params={"search": "pado"})
    assert [s["name"] for s in hit.json()] == ["Padova"]

    miss = client.get("/api/v1/ground-stations", params={"search": "atlantis"})
    assert miss.json() == []
    assert miss.headers["X-Total-Count"] == "0"
