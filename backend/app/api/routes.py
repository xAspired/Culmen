"""HTTP routes.

Handlers do three things and nothing else: validate input, call a service,
map the result. No arithmetic lives here (ADR 0001).

The stateless compute endpoints (``/link-budget/compute``,
``/data-volume/required-duration``) exist so the engine can be used and tested
without loading anything into the registry first.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.app.infrastructure.registry import NotFound, Registry
from backend.app.schemas import models as dto
from backend.app.services import mapping, planning
from core.datavol.volume import required_contact_seconds
from core.orbit.propagator import PropagationError
from core.orbit.tle import TleError
from core.passes.finder import find_passes, sample_window
from core.rf.link import compute_link_budget
from core.time.scales import UTC, ensure_utc, time_range

router = APIRouter(prefix="/api/v1")


def get_registry() -> Registry:  # pragma: no cover - replaced by app wiring
    raise RuntimeError("registry dependency not wired")


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(422, detail=str(exc))


# --------------------------------------------------------------------------
# Stations
# --------------------------------------------------------------------------


@router.get("/ground-stations", response_model=list[dto.StationOut], tags=["stations"])
def list_stations(
    response: Response,
    search: str | None = Query(default=None, description="substring of the name"),
    limit: int = Query(default=200, ge=1, le=5000),
    registry: Registry = Depends(get_registry),
) -> list[dto.StationOut]:
    """List loaded stations, filtered and capped.

    A public catalogue is thousands of stations; a dropdown containing all of
    them is a dropdown nobody can use. ``X-Total-Count`` carries how many
    matched before the cap.
    """
    matching = registry.stations()
    if search:
        needle = search.strip().lower()
        matching = [s for s in matching if needle in s.name.lower()]
    response.headers["X-Total-Count"] = str(len(matching))
    return [mapping.station_out(s) for s in matching[:limit]]


@router.get("/ground-stations/{name}", response_model=dto.StationOut, tags=["stations"])
def get_station(name: str, registry: Registry = Depends(get_registry)) -> dto.StationOut:
    try:
        return mapping.station_out(registry.station(name))
    except NotFound as exc:
        raise _not_found(exc) from exc


# --------------------------------------------------------------------------
# Satellites
# --------------------------------------------------------------------------


@router.post(
    "/satellites/import-tle",
    response_model=list[dto.SatelliteOut],
    status_code=status.HTTP_201_CREATED,
    tags=["satellites"],
)
def import_tle(
    payload: dto.TleImportIn, registry: Registry = Depends(get_registry)
) -> list[dto.SatelliteOut]:
    """Import element sets from raw TLE text.

    Culmen never fetches from CelesTrak on a caller's behalf: rate limiting
    and attribution are the operator's responsibility, and an API that fetched
    silently would make them invisible (see data/README.md).
    """
    try:
        imported = registry.import_tles(payload.text, source=payload.source)
    except TleError as exc:
        raise _bad_request(exc) from exc
    now = datetime.now(UTC)
    return [mapping.satellite_out(t, now) for t in imported]


@router.get("/satellites", response_model=list[dto.SatelliteOut], tags=["satellites"])
def list_satellites(
    response: Response,
    search: str | None = Query(
        default=None, description="substring of the name or catalogue number"
    ),
    limit: int = Query(default=200, ge=1, le=5000),
    registry: Registry = Depends(get_registry),
) -> list[dto.SatelliteOut]:
    """List loaded element sets, filtered and capped.

    A full CelesTrak catalogue is around 11 000 objects, which serialises to
    several megabytes and takes about a second. Returning that on every page
    load would make the UI feel broken, so the list is filtered server-side and
    capped; ``X-Total-Count`` carries how many matched before the cap.
    """
    now = datetime.now(UTC)
    matching = registry.satellites()
    if search:
        needle = search.strip().lower()
        matching = [
            t
            for t in matching
            if needle in (t.name or "").lower() or needle in str(t.norad_id)
        ]
    response.headers["X-Total-Count"] = str(len(matching))
    return [mapping.satellite_out(t, now) for t in matching[:limit]]


@router.get(
    "/satellites/{norad_id}", response_model=dto.SatelliteOut, tags=["satellites"]
)
def get_satellite(
    norad_id: int, registry: Registry = Depends(get_registry)
) -> dto.SatelliteOut:
    try:
        return mapping.satellite_out(registry.tle(norad_id), datetime.now(UTC))
    except NotFound as exc:
        raise _not_found(exc) from exc


# --------------------------------------------------------------------------
# Passes
# --------------------------------------------------------------------------


@router.post("/passes/search", response_model=list[dto.PassOut], tags=["passes"])
def search_passes(
    payload: dto.PassSearchIn, registry: Registry = Depends(get_registry)
) -> list[dto.PassOut]:
    try:
        station = registry.station(payload.station)
        prop = registry.propagator(payload.norad_id)
    except NotFound as exc:
        raise _not_found(exc) from exc

    if payload.min_elevation_deg is not None:
        station = replace(station, min_elevation_deg=payload.min_elevation_deg)

    try:
        passes = find_passes(
            station,
            prop,
            payload.start_utc,
            payload.end_utc,
            coarse_step_s=payload.coarse_step_s,
        )
    except (ValueError, PropagationError) as exc:
        raise _bad_request(exc) from exc
    return [mapping.pass_out(p) for p in passes]


@router.get(
    "/passes/timeline", response_model=list[dto.TimelineSampleOut], tags=["passes"]
)
def pass_timeline(
    station: str,
    norad_id: int,
    start_utc: datetime,
    end_utc: datetime,
    step_s: float = Query(default=10.0, gt=0.0, le=600.0),
    registry: Registry = Depends(get_registry),
) -> list[dto.TimelineSampleOut]:
    """Az/el/range/range-rate across an arbitrary window."""
    try:
        gs = registry.station(station)
        prop = registry.propagator(norad_id)
    except NotFound as exc:
        raise _not_found(exc) from exc
    try:
        samples = sample_window(
            gs, prop, ensure_utc(start_utc), ensure_utc(end_utc), step_s
        )
    except (ValueError, PropagationError) as exc:
        raise _bad_request(exc) from exc
    return [mapping.sample_out(s) for s in samples]


@router.get(
    "/satellites/{norad_id}/ground-track",
    response_model=list[dto.GroundTrackSampleOut],
    tags=["satellites"],
)
def ground_track(
    norad_id: int,
    start_utc: datetime,
    end_utc: datetime,
    step_s: float = Query(default=60.0, gt=0.0, le=3600.0),
    registry: Registry = Depends(get_registry),
) -> list[dto.GroundTrackSampleOut]:
    """Sub-satellite points over a window, for drawing a ground track.

    Latitude is WGS84 *geodetic*. Longitude is continuous in [-180, 180] and
    will wrap: a client drawing a polyline must split the path at the
    antimeridian rather than drawing a line straight across the map.
    """
    try:
        prop = registry.propagator(norad_id)
    except NotFound as exc:
        raise _not_found(exc) from exc
    try:
        grid = time_range(ensure_utc(start_utc), ensure_utc(end_utc), step_s)
        states = prop.states_over(grid)
    except (ValueError, PropagationError) as exc:
        raise _bad_request(exc) from exc
    return [mapping.ground_track_out(s) for s in states]


# --------------------------------------------------------------------------
# Stateless compute
# --------------------------------------------------------------------------


@router.post("/link-budget/compute", response_model=dto.LinkBudgetOut, tags=["rf"])
def link_budget(payload: dto.LinkBudgetIn) -> dto.LinkBudgetOut:
    """Evaluate the chain at one range. Stateless: nothing need be loaded."""
    try:
        budget = compute_link_budget(
            mapping.transmitter_in(payload.transmitter),
            mapping.receiver_in(payload.receiver),
            payload.range_km,
            mapping.losses_in(payload.losses),
            payload.range_rate_km_s,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return mapping.budget_out(budget)


@router.post(
    "/data-volume/required-duration",
    response_model=dto.ComputedOut,
    tags=["data-volume"],
)
def required_duration(payload: dto.RequiredDurationIn) -> dto.ComputedOut:
    """How long a contact must close for, overhead included. Stateless."""
    try:
        result = required_contact_seconds(
            payload.required_bytes,
            payload.data_rate_bps,
            mapping.profile_in(payload.profile),
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    return mapping.computed_out(result)


# --------------------------------------------------------------------------
# The whole pipeline
# --------------------------------------------------------------------------


@router.post("/plan", response_model=dto.PlanOut, tags=["planning"])
def build_plan(
    payload: dto.ContactPlanIn, registry: Registry = Depends(get_registry)
) -> dto.PlanOut:
    """Geometry, RF, volume, verdict and schedule in one call.

    Returns the plan **and** every rejected contact with its reason. An
    endpoint that returned only the accepted contacts would answer "what shall
    I do?" while hiding "and what did you discard on my behalf?".
    """
    try:
        station = registry.station(payload.station)
        propagators = {n: registry.propagator(n) for n in payload.norad_ids}
    except NotFound as exc:
        raise _not_found(exc) from exc

    try:
        schedule, spreads = planning.plan(
            station=station,
            propagators=propagators,
            start_utc=payload.start_utc,
            end_utc=payload.end_utc,
            transmitter=mapping.transmitter_in(payload.transmitter),
            receiver=mapping.receiver_in(payload.receiver),
            losses=mapping.losses_in(payload.losses),
            profile=mapping.profile_in(payload.profile),
            requirement=mapping.requirement_in(payload.requirement),
            antenna=mapping.antenna_in(payload.antenna),
            antenna_id=payload.antenna_id,
            step_s=payload.sample_step_s,
            turnaround_s=payload.turnaround_s,
        )
    except (ValueError, PropagationError) as exc:
        raise _bad_request(exc) from exc

    return mapping.plan_out(schedule, spreads)
