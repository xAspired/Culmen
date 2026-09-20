"""End-to-end: TLE and a station definition in, verdict out.

This is the whole pipeline in one file — propagate, find passes, sample the
link budget along each pass, estimate volume, validate against a requirement.

    python examples/02_validate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.datavol.volume import (
    BYTES_PER_GIGABYTE,
    TransferProfile,
    accumulate,
    compute_data_volume,
)
from core.geometry.definition import load_station
from core.orbit.propagator import Propagator
from core.orbit.tle import parse_tle_text
from core.passes.finder import find_passes
from core.rf.link import (
    PassLinkBudget,
    PathLosses,
    Receiver,
    Transmitter,
    compute_link_budget,
    parabolic_gain_dbi,
)
from core.time.scales import add_seconds, seconds_between
from core.validation.contact import (
    AntennaConstraints,
    MissionRequirement,
    validate_contact,
)

ROOT = Path(__file__).resolve().parents[1]

# --- the scenario ----------------------------------------------------------
FREQ_HZ = 8.2e9
DATA_RATE_BPS = 25e6

SAT_TX = Transmitter(
    name="SAT-01 X-band downlink",
    freq_hz=FREQ_HZ,
    power_w=20.0,
    gain_dbi=12.0,
    line_loss_db=1.0,
    data_rate_bps=DATA_RATE_BPS,
    required_ebn0_db=4.0,
    modulation="QPSK",
    coding="rate-1/2",
)

# A 3 m dish; the gain is computed, not asserted.
DISH_GAIN = parabolic_gain_dbi(3.0, FREQ_HZ, efficiency=0.55)
GS_RX = Receiver("Padova 3 m", gain_dbi=DISH_GAIN.value, system_noise_temp_k=150.0)

LOSSES = PathLosses(
    atmospheric_db=1.5,   # placeholder: ITU-R P.676 is not yet computed (A-RF-1)
    polarization_db=0.5,
    pointing_db=0.5,
    implementation_db=1.0,
)

TRANSFER = TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0)

ANTENNA = AntennaConstraints(
    rx_freq_min_hz=8.0e9,
    rx_freq_max_hz=8.5e9,
    min_elevation_deg=5.0,
    max_elevation_deg=85.0,
)

REQUIREMENT_GB = 2.0


def main() -> None:
    station = load_station(ROOT / "data/stations/padova.yaml")
    tle = next(
        t
        for t in parse_tle_text((ROOT / "data/tle/example-leo.tle").read_text())
        if t.norad_id == 28057
    )
    prop = Propagator(tle)

    start = tle.epoch_utc
    end = add_seconds(start, 24 * 3600.0)
    passes = find_passes(station, prop, start, end)

    print(f"Station    : {station.name}, mask {station.min_elevation_deg:.0f} deg")
    print(f"Satellite  : NORAD {tle.norad_id}, {FREQ_HZ / 1e9:.1f} GHz, "
          f"{DATA_RATE_BPS / 1e6:.0f} Mbps")
    print(f"Dish gain  : {DISH_GAIN.value:.2f} dBi  ({DISH_GAIN.formula_ref})")
    print(f"Requirement: {REQUIREMENT_GB:.1f} GB by {end:%Y-%m-%d %H:%M}Z")
    print(f"Passes     : {len(passes)}\n")

    requirement = MissionRequirement(
        name="bulk downlink",
        required_bytes=REQUIREMENT_GB * BYTES_PER_GIGABYTE,
        deadline_utc=end,
        min_margin_db=3.0,
    )

    results = []
    for i, p in enumerate(passes, start=1):
        # Sample the budget ALONG the pass, not at peak elevation.
        timeline = p.timeline(station, prop, step_s=15.0)
        budget = PassLinkBudget(
            samples=tuple(
                (
                    seconds_between(p.aos_utc, s.t_utc),
                    compute_link_budget(
                        SAT_TX, GS_RX, s.range_km, LOSSES, s.range_rate_km_s
                    ),
                )
                for s in timeline
            )
        )
        volume = compute_data_volume(budget, DATA_RATE_BPS, TRANSFER)
        result = validate_contact(
            p, budget, volume, requirement, antenna=ANTENNA, freq_hz=FREQ_HZ
        )
        results.append((p, volume, result))

        print(f"--- PASS #{i}  {p.aos_utc:%d %b %H:%M:%S} -> {p.los_utc:%H:%M:%S}  "
              f"max el {p.max_elevation_deg:.1f} deg  "
              f"FSPL spread {budget.fspl_spread_db():.1f} dB")
        print(f"    capacity {volume.gigabytes:.3f} GB "
              f"({volume.usable_s.value:.0f} s usable of {p.duration_s:.0f} s)")
        print(result.report())
        print()

    # A single contact rarely carries a bulk requirement. Rank by delivered
    # volume and accumulate until the requirement is met. Ranking here is a
    # deliberately simple, deterministic rule -- the real scheduler is Phase 9.
    workable = [
        (p, v)
        for p, v, r in results
        if not any(
            c.name in {"link_margin", "frequency_compatibility", "minimum_elevation"}
            and c.result.value == "FAIL"
            for c in r.checks
        )
    ]
    workable.sort(key=lambda pv: pv[1].delivered_bytes.value, reverse=True)
    outcome = accumulate([v for _, v in workable], requirement.required_bytes)

    print("RECOMMENDED PLAN")
    if outcome.satisfied:
        print(f"  {outcome.contact_count} contact(s), "
              f"{outcome.delivered_gigabytes:.3f} GB of "
              f"{outcome.required_gigabytes:.1f} GB required:")
        for p, v in workable[: outcome.contact_count]:
            print(f"    {p.aos_utc:%d %b %H:%M:%S}Z -> {p.los_utc:%H:%M:%S}Z  "
                  f"max el {p.max_elevation_deg:5.1f} deg  {v.gigabytes:.3f} GB")
    else:
        print(f"  NOT ACHIEVABLE in this window: "
              f"{outcome.delivered_gigabytes:.3f} GB available across "
              f"{outcome.contact_count} contact(s), "
              f"short by {outcome.shortfall_bytes / BYTES_PER_GIGABYTE:.3f} GB")


if __name__ == "__main__":
    main()
