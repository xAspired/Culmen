"""Culmen HTTP API.

    uvicorn backend.app.main:app --reload

The application wires a :class:`Registry` into the routes and does nothing
else. All behaviour lives in ``core`` (the science) and in
``backend/app/services`` (the orchestration).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api import routes
from backend.app.infrastructure.registry import Registry

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATIONS_DIR = REPO_ROOT / "data" / "stations"
DEFAULT_TLE_DIR = REPO_ROOT / "data" / "tle"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

DESCRIPTION = """
Satellite / ground-station **contact planning and validation**.

Culmen answers: when can we make contact, will the link close, how much data
can we move — and **which check fails if it doesn't**.

Every computed quantity carries its own audit trail: the inputs it was derived
from, its unit, the maths note that defines it, and the assumptions behind it.
Every verdict lists the checks that produced it and, when it fails, concrete
alternatives derived from the specific check that failed.

This service contains no AI or machine learning. Every response is a
deterministic function of its inputs.

It never transmits, and it never fetches orbital data on your behalf:
respecting a data provider's rate limits and attribution is the operator's
responsibility, and an API that fetched silently would make them invisible.
"""


def create_app(
    stations_dir: Path | None = None, tle_dir: Path | None = None
) -> FastAPI:
    registry = Registry(
        stations_dir or _stations_dir_from_env(),
        tle_dir if tle_dir is not None else _tle_dir_from_env(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.registry = registry
        yield

    app = FastAPI(
        title="Culmen",
        version="0.9.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        contact={"name": "Culmen", "url": "https://github.com/"},
        license_info={"name": "Apache-2.0"},
    )
    app.dependency_overrides[routes.get_registry] = lambda: registry
    app.include_router(routes.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "stations": len(registry.stations()),
            "satellites": len(registry.satellites()),
        }

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built single-page app, when there is one.

    Mounted last and at the root, so every API route registered above keeps
    precedence and only unmatched paths fall through to the SPA. This is what
    lets `docker compose up` expose one service on one URL instead of a second
    web server whose only job is to hand over static files.

    Absent in development: `npm run dev` proxies /api to this process.
    """
    if not FRONTEND_DIST.is_dir():
        return
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


def _stations_dir_from_env() -> Path:
    return Path(os.environ.get("CULMEN_STATIONS_DIR", DEFAULT_STATIONS_DIR))


def _tle_dir_from_env() -> Path:
    return Path(os.environ.get("CULMEN_TLE_DIR", DEFAULT_TLE_DIR))


app = create_app()
