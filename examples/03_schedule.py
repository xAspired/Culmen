"""Multi-satellite, multi-antenna scheduling, end to end.

Two satellites, one station with two antennas, two competing requirements.

    python examples/03_schedule.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.datavol.volume import BYTES_PER_GIGABYTE, TransferProfile, compute_data_volume
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
from core.scheduling.scheduler import Candidate, schedule_contacts
from core.time.scales import add_seconds, seconds_between
from core.validation.contact import (
    AntennaConstraints,
    MissionRequirement,
    validate_contact,
)

ROOT = Path(__file__).resolve().parents[1]

FREQ_HZ = 8.2e9
RATE_BPS = 25e6
LOSSES = PathLosses(atmospheric_db=1.5, polarization_db=0.5, pointing_db=0.5,
                    implementation_db=1.0)
TRANSFER = TransferProfile(framing_efficiency=0.85, acquisition_s=45.0, setup_s=30.0)
ANTENNA_LIMITS = AntennaConstraints(
    rx_freq_min_hz=8.0e9, rx_freq_max_hz=8.5e9,
    min_elevation_deg=5.0, max_elevation_deg=85.0,
)

# One station, two dishes of different size -- so the plan has a real choice.
ANTENNAS = {
    "ANT-3M": parabolic_gain_dbi(3.0, FREQ_HZ, efficiency=0.55).value,
    "ANT-5M": parabolic_gain_dbi(5.0, FREQ_HZ, efficiency=0.55).value,
}


def main() -> None:
    station = load_station(ROOT / "data/stations/padova.yaml")
    tles = parse_tle_text((ROOT / "data/tle/example-leo.tle").read_text())

    start = min(t.epoch_utc for t in tles)
    end = add_seconds(start, 36 * 3600.0)

    # Each satellite carries its own requirement, with different urgency.
    requirements = {
        tles[0].norad_id: MissionRequirement(
            name="imagery-bulk",
            required_bytes=3.0 * BYTES_PER_GIGABYTE,
            deadline_utc=end,
            min_margin_db=3.0,
        ),
        tles[1].norad_id: MissionRequirement(
            name="telemetry-urgent",
            required_bytes=0.4 * BYTES_PER_GIGABYTE,
            deadline_utc=add_seconds(start, 12 * 3600.0),
            min_margin_db=3.0,
        ),
    }
    priorities = {tles[0].norad_id: 5, tles[1].norad_id: 0}

    candidates: list[Candidate] = []
    for tle in tles:
        prop = Propagator(tle)
        tx = Transmitter(f"NORAD {tle.norad_id}", FREQ_HZ, 20.0, 12.0,
                         line_loss_db=1.0, data_rate_bps=RATE_BPS,
                         required_ebn0_db=4.0)
        for p in find_passes(station, prop, start, end):
            timeline = p.timeline(station, prop, step_s=15.0)
            for antenna_id, gain_dbi in ANTENNAS.items():
                rx = Receiver(antenna_id, gain_dbi=gain_dbi, system_noise_temp_k=150.0)
                budget = PassLinkBudget(
                    samples=tuple(
                        (
                            seconds_between(p.aos_utc, s.t_utc),
                            compute_link_budget(tx, rx, s.range_km, LOSSES,
                                                s.range_rate_km_s),
                        )
                        for s in timeline
                    )
                )
                volume = compute_data_volume(budget, RATE_BPS, TRANSFER)
                validation = validate_contact(
                    p, budget, volume, requirements[tle.norad_id],
                    antenna=ANTENNA_LIMITS, freq_hz=FREQ_HZ,
                )
                candidates.append(
                    Candidate(
                        pass_=p,
                        antenna_id=antenna_id,
                        validation=validation,
                        volume=volume,
                        requirement=requirements[tle.norad_id],
                        priority=priorities[tle.norad_id],
                    )
                )

    print(f"Window     : {start:%Y-%m-%d %H:%M}Z -> {end:%Y-%m-%d %H:%M}Z")
    print(f"Satellites : {', '.join(str(t.norad_id) for t in tles)}")
    print(f"Antennas   : {', '.join(ANTENNAS)}")
    print(f"Candidates : {len(candidates)}\n")

    # 10 minutes to slew between satellites and reconfigure.
    plan = schedule_contacts(candidates, turnaround_s=600.0)
    print(plan.report())

    print()
    for note in plan.notes:
        print(f"NOTE: {note}")


if __name__ == "__main__":
    main()
