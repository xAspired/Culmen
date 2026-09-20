"""Pydantic DTOs for the HTTP boundary.

These are deliberately separate from the ``core`` dataclasses. The duplication
is the price of ADR 0001: ``core`` must stay free of Pydantic and of any
serialisation concern, so the mapping lives here, on the edge.

Two conventions hold throughout, and both are load-bearing:

* every numeric field carries its unit in the name, exactly as in ``core``;
* every response that rests on a simplification carries ``assumptions`` and,
  where a threshold was involved, the full check list. A verdict without its
  reasoning is not something this API is willing to return.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.time.scales import ensure_utc


class UtcModel(BaseModel):
    """Base class that refuses naive datetimes at the HTTP boundary.

    A timestamp without a timezone is the single most common way a planning
    tool silently produces answers an hour or two out.
    """

    @field_validator("*", mode="after")
    @classmethod
    def _reject_naive_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return ensure_utc(value)
        return value


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


class ComputedOut(BaseModel):
    """A single quantity with its audit trail (ADR 0006)."""

    value: float
    unit: str
    formula_ref: str
    inputs: dict[str, float] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Stations and satellites
# --------------------------------------------------------------------------


class StationOut(BaseModel):
    name: str
    lat_deg: float
    lon_deg: float
    alt_m: float
    min_elevation_deg: float
    has_horizon_profile: bool


class SatelliteOut(BaseModel):
    norad_id: int
    name: str | None
    cospar_id: str
    epoch_utc: datetime
    inclination_deg: float
    eccentricity: float
    mean_motion_rev_day: float
    age_days: float
    age_warning: str | None


class TleImportIn(BaseModel):
    """Raw TLE text, 2LE or 3LE. The server never fetches it for you.

    Culmen does not reach out to CelesTrak on a caller's behalf: rate limits
    and attribution are the operator's responsibility, and an API that fetches
    silently makes them invisible (see data/README.md).
    """

    text: str = Field(min_length=100, description="TLE file contents")
    source: str | None = None


# --------------------------------------------------------------------------
# Passes
# --------------------------------------------------------------------------


class PassSearchIn(UtcModel):
    station: str = Field(description="station name, as loaded from data/stations")
    norad_id: int
    start_utc: datetime
    end_utc: datetime
    min_elevation_deg: float | None = Field(
        default=None, description="overrides the station's own mask"
    )
    coarse_step_s: float = Field(default=30.0, gt=0.0, le=600.0)


class PassOut(BaseModel):
    satellite_norad_id: int
    station_name: str
    aos_utc: datetime
    los_utc: datetime
    duration_s: float
    max_elevation_deg: float
    max_elevation_utc: datetime
    aos_az_deg: float
    los_az_deg: float
    max_el_az_deg: float
    tle_epoch_utc: datetime
    tle_age_days: float
    propagator_version: str
    warnings: list[str] = Field(default_factory=list)


class GroundTrackSampleOut(BaseModel):
    """Sub-satellite point. Latitude is WGS84 geodetic, never geocentric."""

    t_utc: datetime
    lat_deg: float
    lon_deg: float
    alt_km: float


class TimelineSampleOut(BaseModel):
    t_utc: datetime
    az_deg: float
    el_deg: float
    range_km: float
    range_rate_km_s: float


# --------------------------------------------------------------------------
# Link budget
# --------------------------------------------------------------------------


class TransmitterIn(BaseModel):
    name: str = "transmitter"
    freq_hz: float = Field(gt=0.0)
    power_w: float = Field(gt=0.0)
    gain_dbi: float
    line_loss_db: float = Field(default=0.0, ge=0.0)
    data_rate_bps: float = Field(default=0.0, ge=0.0)
    required_ebn0_db: float = 0.0
    modulation: str = ""
    coding: str = ""


class ReceiverIn(BaseModel):
    name: str = "receiver"
    gain_dbi: float | None = None
    system_noise_temp_k: float | None = Field(default=None, gt=0.0)
    g_over_t_dbk: float | None = None


class PathLossesIn(BaseModel):
    """All values are POSITIVE decibels of loss. Defaults of 0 are optimistic."""

    atmospheric_db: float = Field(default=0.0, ge=0.0)
    polarization_db: float = Field(default=0.0, ge=0.0)
    pointing_db: float = Field(default=0.0, ge=0.0)
    ionospheric_db: float = Field(default=0.0, ge=0.0)
    implementation_db: float = Field(default=0.0, ge=0.0)
    rain_db: float = Field(default=0.0, ge=0.0)


class LinkBudgetIn(BaseModel):
    transmitter: TransmitterIn
    receiver: ReceiverIn
    range_km: float = Field(gt=0.0)
    losses: PathLossesIn = Field(default_factory=PathLossesIn)
    range_rate_km_s: float | None = None


class BudgetLineOut(BaseModel):
    label: str
    value: float
    unit: str


class LinkBudgetOut(BaseModel):
    range_km: float
    freq_hz: float
    eirp_dbw: ComputedOut
    fspl_db: ComputedOut
    other_losses_db: ComputedOut
    g_over_t_dbk: ComputedOut
    cn0_dbhz: ComputedOut
    ebn0_db: ComputedOut | None
    margin_db: ComputedOut | None
    doppler_hz: ComputedOut | None
    closes: bool
    lines: list[BudgetLineOut]
    assumptions: list[str]


# --------------------------------------------------------------------------
# Data volume
# --------------------------------------------------------------------------


class TransferProfileIn(BaseModel):
    framing_efficiency: float = Field(default=1.0, gt=0.0, le=1.0)
    acquisition_s: float = Field(default=0.0, ge=0.0)
    setup_s: float = Field(default=0.0, ge=0.0)


class RequiredDurationIn(BaseModel):
    required_bytes: float = Field(ge=0.0)
    data_rate_bps: float = Field(gt=0.0)
    profile: TransferProfileIn = Field(default_factory=TransferProfileIn)


class DataVolumeOut(BaseModel):
    closing_s: ComputedOut
    usable_s: ComputedOut
    delivered_bytes: ComputedOut
    gigabytes: float
    assumptions: list[str]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


class AntennaConstraintsIn(BaseModel):
    rx_freq_min_hz: float | None = None
    rx_freq_max_hz: float | None = None
    min_elevation_deg: float = 0.0
    max_elevation_deg: float = 90.0


class RequirementIn(UtcModel):
    name: str
    required_bytes: float = Field(ge=0.0)
    deadline_utc: datetime | None = None
    min_margin_db: float = 3.0


class CheckOut(BaseModel):
    name: str
    result: str
    message: str
    expected: str = ""
    actual: str = ""
    unit: str = ""
    formula_ref: str = ""


class SuggestionOut(BaseModel):
    check_name: str
    action: str
    detail: str


class ValidationOut(BaseModel):
    verdict: str
    checks: list[CheckOut]
    suggestions: list[SuggestionOut]
    assumptions: list[str]
    engine_version: str


class ContactPlanIn(UtcModel):
    """One end-to-end request: geometry, RF, volume and verdict in one call."""

    station: str
    norad_ids: list[int] = Field(min_length=1)
    start_utc: datetime
    end_utc: datetime
    transmitter: TransmitterIn
    receiver: ReceiverIn
    requirement: RequirementIn
    losses: PathLossesIn = Field(default_factory=PathLossesIn)
    profile: TransferProfileIn = Field(default_factory=TransferProfileIn)
    antenna: AntennaConstraintsIn = Field(default_factory=AntennaConstraintsIn)
    antenna_id: str = "ANT-1"
    sample_step_s: float = Field(default=15.0, gt=0.0, le=300.0)
    turnaround_s: float = Field(default=0.0, ge=0.0)


class ContactOut(BaseModel):
    pass_: PassOut = Field(alias="pass")
    antenna_id: str
    volume: DataVolumeOut
    validation: ValidationOut
    fspl_spread_db: float

    model_config = {"populate_by_name": True}


class ScheduledOut(BaseModel):
    rank: int
    contact: ContactOut
    cumulative_bytes: float


class RejectedOut(BaseModel):
    contact: ContactOut
    reason: str
    detail: str


class RequirementStatusOut(BaseModel):
    name: str
    required_bytes: float
    delivered_bytes: float
    satisfied: bool
    contact_count: int
    shortfall_bytes: float


class PlanOut(BaseModel):
    scheduled: list[ScheduledOut]
    rejected: list[RejectedOut]
    requirements: list[RequirementStatusOut]
    all_satisfied: bool
    scheduler_version: str
    notes: list[str]
