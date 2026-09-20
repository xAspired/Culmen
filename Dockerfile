# Culmen API.
#
# Multi-stage so the runtime image carries no build toolchain. The image is
# fully offline at run time: the SGP4 verification data ships with the sgp4
# package and the timescale comes from Skyfield's bundled leap-second table,
# so the container never needs the network to compute anything.

FROM node:22-slim AS frontend

WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY core ./core
COPY backend ./backend

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install ".[api]"


FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CULMEN_STATIONS_DIR=/app/data/stations

# Run unprivileged: the service needs no write access to anything.
RUN useradd --create-home --uid 10001 culmen

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY core ./core
COPY backend ./backend
COPY data ./data
COPY docs ./docs
COPY LICENSE* NOTICE THIRD_PARTY.md ./
COPY --from=frontend /ui/dist ./frontend/dist

USER culmen
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
