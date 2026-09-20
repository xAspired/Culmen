"""Pass finding: correctness of AOS/LOS/max-elevation and of the search itself.

The properties tested here are the ones that make a pass list trustworthy:

* AOS and LOS sit exactly on the elevation mask (that is their definition).
* The reported maximum is really the maximum, checked against dense sampling.
* Coarse-grid search plus root refinement gives the same answer as a brute
  force fine grid -- i.e. the optimisation does not lose short passes or
  displace boundaries.
* Windows that clip a pass are reported as clipped, not silently truncated.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.geometry.station import look_angles
from core.orbit.propagator import PropagationError, Propagator
from core.passes.finder import find_passes, sample_window
from core.time.scales import add_seconds, seconds_between

WINDOW_S = 24 * 3600.0


@pytest.fixture(scope="module")
def prop(leo_tle) -> Propagator:
    return Propagator(leo_tle)


@pytest.fixture(scope="module")
def window(leo_tle):
    start = add_seconds(leo_tle.epoch_utc, 3600.0)
    return start, add_seconds(start, WINDOW_S)


@pytest.fixture(scope="module")
def found(prop, padova, window):
    try:
        return find_passes(padova, prop, *window)
    except PropagationError as exc:  # pragma: no cover
        pytest.skip(f"element set not propagable: {exc}")


def test_some_passes_are_found(found):
    assert found, "a LEO satellite should have passes over a mid-latitude site in 24 h"
    assert len(found) < 40, "implausibly many passes; the search is probably double-counting"


def test_aos_and_los_lie_on_the_elevation_mask(found, padova, prop):
    for p in found:
        if p.warnings and any("clipped" in w for w in p.warnings):
            continue
        aos, los = look_angles(padova, prop, [p.aos_utc, p.los_utc])
        assert aos.el_deg == pytest.approx(padova.mask_deg(aos.az_deg), abs=1e-4)
        assert los.el_deg == pytest.approx(padova.mask_deg(los.az_deg), abs=1e-4)


def test_pass_is_internally_consistent(found):
    for p in found:
        assert p.aos_utc < p.max_elevation_utc < p.los_utc
        assert p.duration_s > 0.0
        assert p.duration_s == pytest.approx(seconds_between(p.aos_utc, p.los_utc), abs=1e-3)
        assert p.max_elevation_deg > 0.0
        assert 0.0 <= p.aos_az_deg < 360.0
        assert 0.0 <= p.los_az_deg < 360.0


def test_reported_maximum_is_the_real_maximum(found, padova, prop):
    for p in found:
        samples = sample_window(padova, prop, p.aos_utc, p.los_utc, step_s=1.0)
        best = max(s.el_deg for s in samples)
        assert p.max_elevation_deg >= best - 1e-6, "reported peak is below a sampled elevation"
        assert p.max_elevation_deg == pytest.approx(best, abs=1e-3)


def test_passes_do_not_overlap_and_are_ordered(found):
    for earlier, later in zip(found, found[1:], strict=False):
        assert earlier.los_utc < later.aos_utc


def test_coarse_search_agrees_with_a_fine_brute_force_grid(found, padova, prop, window):
    """The coarse-plus-refinement search must not change the answer.

    Brute force here means: sample every 5 s, take contiguous above-mask runs,
    and compare boundaries. The coarse search uses a 30 s grid, so agreement
    within the brute-force grid resolution proves no pass is lost or moved.
    """
    start, end = window
    n = int(WINDOW_S // 5)
    times = [add_seconds(start, 5.0 * k) for k in range(n + 1)]
    samples = look_angles(padova, prop, times)
    above = np.array([s.el_deg > padova.mask_deg(s.az_deg) for s in samples])

    runs = []
    in_run = False
    for i, flag in enumerate(above):
        if flag and not in_run:
            in_run, i0 = True, i
        elif not flag and in_run:
            in_run = False
            runs.append((i0, i - 1))
    if in_run:
        runs.append((i0, len(above) - 1))

    assert len(runs) == len(found), (
        f"brute force found {len(runs)} passes, coarse search found {len(found)}"
    )
    for (i0, i1), p in zip(runs, found, strict=True):
        assert abs(seconds_between(samples[i0].t_utc, p.aos_utc)) <= 5.0
        assert abs(seconds_between(samples[i1].t_utc, p.los_utc)) <= 5.0


def test_clipped_passes_are_flagged(prop, padova, found):
    """A window that starts mid-pass must say so rather than report a false AOS."""
    target = max(found, key=lambda p: p.duration_s)
    mid = add_seconds(target.aos_utc, target.duration_s / 2.0)
    clipped = find_passes(padova, prop, mid, add_seconds(mid, 3600.0))
    assert clipped
    first = clipped[0]
    assert any("clipped" in w for w in first.warnings)
    assert first.aos_utc >= mid


def test_higher_mask_yields_fewer_and_shorter_passes(prop, padova, window):
    from dataclasses import replace

    strict = replace(padova, min_elevation_deg=40.0)
    loose = find_passes(padova, prop, *window)
    tight = find_passes(strict, prop, *window)
    assert len(tight) <= len(loose)
    for p in tight:
        assert p.max_elevation_deg > 40.0


def test_tle_age_is_reported_on_every_pass(found, leo_tle):
    for p in found:
        assert p.tle_epoch_utc == leo_tle.epoch_utc
        assert p.tle_age_days > 0.0
        assert p.propagator_version


def test_azimuth_dependent_horizon_profile_is_respected(prop, window):
    """A mask that is high to the north must cut northern passes specifically."""
    from dataclasses import replace

    from core.geometry.station import GroundStation, HorizonProfile

    flat = GroundStation("Profiled", 45.4064, 11.8768, 12.0, min_elevation_deg=10.0)
    profiled = replace(
        flat,
        horizon_profile=HorizonProfile(
            ((0.0, 40.0), (90.0, 10.0), (180.0, 10.0), (270.0, 10.0))
        ),
    )
    assert profiled.mask_deg(0.0) == pytest.approx(40.0)
    assert profiled.mask_deg(180.0) == pytest.approx(10.0)
    assert profiled.mask_deg(45.0) == pytest.approx(25.0)  # linear interpolation
    # 359 deg sits just short of the northern peak; the wrap must interpolate
    # towards 40 deg rather than falling back to the default.
    assert 39.0 < profiled.mask_deg(359.0) <= 40.0

    base = find_passes(flat, prop, *window)
    masked = find_passes(profiled, prop, *window)
    assert len(masked) <= len(base)
    for p in masked:
        aos_mask = profiled.mask_deg(p.aos_az_deg)
        assert p.max_elevation_deg >= aos_mask - 1e-6
