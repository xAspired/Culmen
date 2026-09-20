"""Mapping between ``core`` dataclasses and the HTTP DTOs.

All of it lives here so that no route handler ever touches a ``core`` type
directly and no ``core`` type ever learns about Pydantic (ADR 0001).
"""

from __future__ import annotations

from datetime import datetime

from backend.app.schemas import models as dto
from core.datavol.volume import BYTES_PER_GIGABYTE, DataVolume, TransferProfile
from core.geometry.station import GroundStation, TopocentricSample
from core.orbit.propagator import SatelliteState
from core.orbit.tle import Tle
from core.passes.finder import Pass
from core.provenance import Computed
from core.rf.link import LinkBudget, PathLosses, Receiver, Transmitter
from core.scheduling.scheduler import Candidate, Schedule
from core.validation.contact import (
    AntennaConstraints,
    ContactValidation,
    MissionRequirement,
)


def computed_out(c: Computed[float]) -> dto.ComputedOut:
    return dto.ComputedOut(
        value=c.value,
        unit=c.unit,
        formula_ref=c.formula_ref,
        inputs=dict(c.inputs),
        assumptions=list(c.assumptions),
    )


def station_out(s: GroundStation) -> dto.StationOut:
    return dto.StationOut(
        name=s.name,
        lat_deg=s.lat_deg,
        lon_deg=s.lon_deg,
        alt_m=s.alt_m,
        min_elevation_deg=s.min_elevation_deg,
        has_horizon_profile=bool(s.horizon_profile.samples),
    )


def satellite_out(tle: Tle, now: datetime) -> dto.SatelliteOut:
    return dto.SatelliteOut(
        norad_id=tle.norad_id,
        name=tle.name,
        cospar_id=tle.cospar_id,
        epoch_utc=tle.epoch_utc,
        inclination_deg=tle.inclination_deg,
        eccentricity=tle.eccentricity,
        mean_motion_rev_day=tle.mean_motion_rev_day,
        age_days=tle.age_days(now),
        age_warning=tle.age_warning(now),
    )


def pass_out(p: Pass) -> dto.PassOut:
    return dto.PassOut(
        satellite_norad_id=p.satellite_norad_id,
        station_name=p.station_name,
        aos_utc=p.aos_utc,
        los_utc=p.los_utc,
        duration_s=p.duration_s,
        max_elevation_deg=p.max_elevation_deg,
        max_elevation_utc=p.max_elevation_utc,
        aos_az_deg=p.aos_az_deg,
        los_az_deg=p.los_az_deg,
        max_el_az_deg=p.max_el_az_deg,
        tle_epoch_utc=p.tle_epoch_utc,
        tle_age_days=p.tle_age_days,
        propagator_version=p.propagator_version,
        warnings=list(p.warnings),
    )


def sample_out(s: TopocentricSample) -> dto.TimelineSampleOut:
    return dto.TimelineSampleOut(
        t_utc=s.t_utc,
        az_deg=s.az_deg,
        el_deg=s.el_deg,
        range_km=s.range_km,
        range_rate_km_s=s.range_rate_km_s,
    )


def ground_track_out(state: SatelliteState) -> dto.GroundTrackSampleOut:
    return dto.GroundTrackSampleOut(
        t_utc=state.t_utc,
        lat_deg=state.lat_deg,
        lon_deg=state.lon_deg,
        alt_km=state.alt_km,
    )


def budget_out(b: LinkBudget) -> dto.LinkBudgetOut:
    return dto.LinkBudgetOut(
        range_km=b.range_km,
        freq_hz=b.freq_hz,
        eirp_dbw=computed_out(b.eirp_dbw),
        fspl_db=computed_out(b.fspl_db),
        other_losses_db=computed_out(b.other_losses_db),
        g_over_t_dbk=computed_out(b.g_over_t_dbk),
        cn0_dbhz=computed_out(b.cn0_dbhz),
        ebn0_db=computed_out(b.ebn0_db) if b.ebn0_db else None,
        margin_db=computed_out(b.margin_db) if b.margin_db else None,
        doppler_hz=computed_out(b.doppler_hz) if b.doppler_hz else None,
        closes=b.closes(),
        lines=[
            dto.BudgetLineOut(label=label, value=value, unit=unit)
            for label, value, unit in b.lines()
        ],
        assumptions=list(b.assumptions),
    )


def volume_out(v: DataVolume) -> dto.DataVolumeOut:
    return dto.DataVolumeOut(
        closing_s=computed_out(v.closing_s),
        usable_s=computed_out(v.usable_s),
        delivered_bytes=computed_out(v.delivered_bytes),
        gigabytes=v.gigabytes,
        assumptions=list(v.assumptions),
    )


def validation_out(v: ContactValidation) -> dto.ValidationOut:
    return dto.ValidationOut(
        verdict=v.verdict.value,
        checks=[
            dto.CheckOut(
                name=c.name,
                result=c.result.value,
                message=c.message,
                expected=c.expected,
                actual=c.actual,
                unit=c.unit,
                formula_ref=c.formula_ref,
            )
            for c in v.checks
        ],
        suggestions=[
            dto.SuggestionOut(check_name=s.check_name, action=s.action, detail=s.detail)
            for s in v.suggestions
        ],
        assumptions=list(v.assumptions),
        engine_version=v.engine_version,
    )


def contact_out(candidate: Candidate, fspl_spread_db: float) -> dto.ContactOut:
    return dto.ContactOut(
        **{"pass": pass_out(candidate.pass_)},
        antenna_id=candidate.antenna_id,
        volume=volume_out(candidate.volume),
        validation=validation_out(candidate.validation),
        fspl_spread_db=fspl_spread_db,
    )


def plan_out(schedule: Schedule, spreads: dict[str, float]) -> dto.PlanOut:
    return dto.PlanOut(
        scheduled=[
            dto.ScheduledOut(
                rank=s.rank,
                contact=contact_out(s.candidate, spreads.get(s.candidate.key, 0.0)),
                cumulative_bytes=s.cumulative_bytes,
            )
            for s in schedule.scheduled
        ],
        rejected=[
            dto.RejectedOut(
                contact=contact_out(r.candidate, spreads.get(r.candidate.key, 0.0)),
                reason=r.reason.value,
                detail=r.detail,
            )
            for r in schedule.rejected
        ],
        requirements=[
            dto.RequirementStatusOut(
                name=r.requirement.name,
                required_bytes=r.requirement.required_bytes,
                delivered_bytes=r.delivered_bytes,
                satisfied=r.satisfied,
                contact_count=r.contact_count,
                shortfall_bytes=r.shortfall_bytes,
            )
            for r in schedule.requirements
        ],
        all_satisfied=schedule.all_satisfied,
        scheduler_version=schedule.scheduler_version,
        notes=list(schedule.notes),
    )


# --- inbound ---------------------------------------------------------------


def transmitter_in(t: dto.TransmitterIn) -> Transmitter:
    return Transmitter(
        name=t.name,
        freq_hz=t.freq_hz,
        power_w=t.power_w,
        gain_dbi=t.gain_dbi,
        line_loss_db=t.line_loss_db,
        data_rate_bps=t.data_rate_bps,
        required_ebn0_db=t.required_ebn0_db,
        modulation=t.modulation,
        coding=t.coding,
    )


def receiver_in(r: dto.ReceiverIn) -> Receiver:
    return Receiver(
        name=r.name,
        gain_dbi=r.gain_dbi,
        system_noise_temp_k=r.system_noise_temp_k,
        g_over_t_dbk=r.g_over_t_dbk,
    )


def losses_in(p: dto.PathLossesIn) -> PathLosses:
    return PathLosses(
        atmospheric_db=p.atmospheric_db,
        polarization_db=p.polarization_db,
        pointing_db=p.pointing_db,
        ionospheric_db=p.ionospheric_db,
        implementation_db=p.implementation_db,
        rain_db=p.rain_db,
    )


def profile_in(p: dto.TransferProfileIn) -> TransferProfile:
    return TransferProfile(
        framing_efficiency=p.framing_efficiency,
        acquisition_s=p.acquisition_s,
        setup_s=p.setup_s,
    )


def antenna_in(a: dto.AntennaConstraintsIn) -> AntennaConstraints:
    return AntennaConstraints(
        rx_freq_min_hz=a.rx_freq_min_hz,
        rx_freq_max_hz=a.rx_freq_max_hz,
        min_elevation_deg=a.min_elevation_deg,
        max_elevation_deg=a.max_elevation_deg,
    )


def requirement_in(r: dto.RequirementIn) -> MissionRequirement:
    return MissionRequirement(
        name=r.name,
        required_bytes=r.required_bytes,
        deadline_utc=r.deadline_utc,
        min_margin_db=r.min_margin_db,
    )


__all__ = ["BYTES_PER_GIGABYTE"]
