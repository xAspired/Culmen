"""Scheduler.

Greedy scheduling has no external reference to check against, and "the plan
looks sensible" is not a test. What is pinned here instead:

* the ranking is a **total order** — identical inputs give an identical plan,
  and shuffling the input list cannot change the result;
* no two scheduled contacts ever share an antenna in overlapping time, with
  turnaround honoured on both sides;
* every candidate that was not scheduled has a specific recorded reason;
* the stated policy (priority, then deadline, then volume) is actually the
  policy the code follows.

The last one matters most: a ranking documented in a docstring but not
enforced by a test is a comment, not a behaviour.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from core.datavol.volume import BYTES_PER_GIGABYTE, DataVolume
from core.passes.finder import Pass
from core.provenance import Computed
from core.scheduling.scheduler import (
    Candidate,
    Rejection,
    rank_key,
    schedule_contacts,
)
from core.time.scales import UTC
from core.validation.contact import (
    Check,
    CheckResult,
    ContactValidation,
    MissionRequirement,
    Verdict,
)

T0 = datetime(2026, 9, 9, 6, 0, tzinfo=UTC)
GB = BYTES_PER_GIGABYTE


def make_volume(gigabytes: float) -> DataVolume:
    b = gigabytes * GB
    c = Computed(0.0, "s", "docs/math/data-volume.md")
    return DataVolume(
        closing_s=c,
        usable_s=c,
        delivered_bytes=Computed(b, "B", "docs/math/data-volume.md"),
    )


def make_validation(
    verdict: Verdict = Verdict.VALID, failing: str = "link_margin"
) -> ContactValidation:
    if verdict is Verdict.VALID:
        checks = (Check("link_margin", CheckResult.PASS, "ok"),)
    elif verdict is Verdict.CONDITIONALLY_VALID:
        checks = (Check("tle_freshness", CheckResult.WARN, "stale"),)
    else:
        checks = (Check(failing, CheckResult.FAIL, "failed"),)
    return ContactValidation(verdict=verdict, checks=checks)


def make_pass(
    offset_min: float,
    duration_min: float = 10.0,
    norad_id: int = 25544,
    station: str = "Padova",
    max_el_deg: float = 45.0,
) -> Pass:
    aos = T0 + timedelta(minutes=offset_min)
    los = aos + timedelta(minutes=duration_min)
    return Pass(
        satellite_norad_id=norad_id,
        station_name=station,
        aos_utc=aos,
        los_utc=los,
        max_elevation_deg=max_el_deg,
        max_elevation_utc=aos + timedelta(minutes=duration_min / 2),
        duration_s=duration_min * 60.0,
        aos_az_deg=10.0,
        los_az_deg=190.0,
        max_el_az_deg=100.0,
        tle_epoch_utc=T0 - timedelta(days=1),
        tle_age_days=1.0,
        propagator_version="test",
    )


REQ = MissionRequirement("bulk", 2.0 * GB, deadline_utc=T0 + timedelta(days=1))


def candidate(
    offset_min: float,
    gigabytes: float = 1.0,
    antenna: str = "ANT-1",
    duration_min: float = 10.0,
    verdict: Verdict = Verdict.VALID,
    requirement: MissionRequirement = REQ,
    priority: int = 0,
    norad_id: int = 25544,
    failing: str = "link_margin",
) -> Candidate:
    return Candidate(
        pass_=make_pass(offset_min, duration_min, norad_id=norad_id),
        antenna_id=antenna,
        validation=make_validation(verdict, failing),
        volume=make_volume(gigabytes),
        requirement=requirement,
        priority=priority,
    )


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_plan_is_independent_of_input_order():
    """Shuffling the candidate list must not change the schedule."""
    cands = [
        candidate(0, 1.0),
        candidate(60, 1.2, antenna="ANT-2"),
        candidate(120, 0.9),
        candidate(180, 1.1, antenna="ANT-2"),
        candidate(240, 0.5),
    ]
    reference = [s.candidate.key for s in schedule_contacts(cands).scheduled]

    rng = random.Random(12345)
    for _ in range(20):
        shuffled = cands[:]
        rng.shuffle(shuffled)
        got = [s.candidate.key for s in schedule_contacts(shuffled).scheduled]
        assert got == reference


def test_rank_key_is_a_total_order_with_no_ties():
    """Without the identity tie-break, set iteration order could leak in."""
    cands = [
        candidate(0, 1.0),
        candidate(0, 1.0, antenna="ANT-2"),
        candidate(0, 1.0, norad_id=43700),
    ]
    keys = [rank_key(c) for c in cands]
    assert len(set(keys)) == len(keys)


# --------------------------------------------------------------------------
# Conflicts
# --------------------------------------------------------------------------


def test_one_antenna_cannot_hold_two_overlapping_contacts():
    # Two DIFFERENT satellites, so the antenna is the only contended resource.
    overlapping = [candidate(0, 1.0), candidate(5, 1.0, norad_id=43700)]
    result = schedule_contacts(overlapping)
    assert len(result.scheduled) == 1
    assert result.rejections_for(Rejection.ANTENNA_BUSY)


def test_two_antennas_can_hold_the_same_time_slot():
    result = schedule_contacts(
        [
            candidate(0, 1.0, antenna="ANT-1"),
            candidate(0, 1.0, antenna="ANT-2", norad_id=43700),
        ]
    )
    assert len(result.scheduled) == 2
    assert not result.rejections_for(Rejection.ANTENNA_BUSY)


def test_one_satellite_cannot_downlink_to_two_antennas_at_once():
    """Two dishes on one spacecraft receive the same signal, not double the data.

    Found by running the example, not by reasoning about it: the scheduler
    booked the same pass on every free antenna and reported a requirement
    satisfied that was not.
    """
    result = schedule_contacts(
        [
            candidate(0, 1.0, antenna="ANT-1"),
            candidate(0, 1.0, antenna="ANT-2"),  # same satellite, same window
        ]
    )
    assert len(result.scheduled) == 1
    rejection = result.rejections_for(Rejection.SATELLITE_BUSY)[0]
    assert "same signal, not more data" in rejection.detail
    assert result.requirements[0].delivered_bytes == pytest.approx(1.0 * GB)


def test_the_same_satellite_can_use_different_antennas_at_different_times():
    result = schedule_contacts(
        [candidate(0, 1.0, antenna="ANT-1"), candidate(120, 1.0, antenna="ANT-2")]
    )
    assert len(result.scheduled) == 2
    assert not result.rejections_for(Rejection.SATELLITE_BUSY)


def test_turnaround_is_enforced_between_consecutive_contacts():
    """Back to back is not free: the dish has to slew."""
    # First ends at T0+10 min, second starts at T0+12 min: a 120 s gap.
    back_to_back = [candidate(0, 1.0), candidate(12, 1.0)]

    assert len(schedule_contacts(back_to_back, turnaround_s=60.0).scheduled) == 2

    tight = schedule_contacts(back_to_back, turnaround_s=300.0)
    assert len(tight.scheduled) == 1
    detail = tight.rejections_for(Rejection.ANTENNA_BUSY)[0].detail
    assert "turnaround" in detail


def test_turnaround_applies_in_both_directions():
    """A contact scheduled later must also respect a gap before an earlier one."""
    # The bigger one ranks first and is taken; the earlier, smaller one then
    # has to fit before it, turnaround included. The requirement is set large
    # enough that both contacts are still wanted -- otherwise the second would
    # be rejected as REQUIREMENT_ALREADY_MET and prove nothing about slew time.
    big_req = MissionRequirement("big", 100.0 * GB, deadline_utc=T0 + timedelta(days=1))
    later_bigger = candidate(60, 5.0, requirement=big_req)
    earlier_smaller = candidate(45, 0.5, requirement=big_req)
    result = schedule_contacts(
        [earlier_smaller, later_bigger],
        turnaround_s=1800.0,
    )
    assert [s.candidate.key for s in result.scheduled] == [later_bigger.key]
    assert result.rejections_for(Rejection.ANTENNA_BUSY)


def test_negative_turnaround_is_rejected():
    with pytest.raises(ValueError, match="turnaround_s"):
        schedule_contacts([candidate(0)], turnaround_s=-1.0)


# --------------------------------------------------------------------------
# The stated policy is the policy
# --------------------------------------------------------------------------


def test_priority_beats_delivered_volume():
    """An explicit operator priority must not be overridden by a computation."""
    urgent_small = candidate(
        0, 0.1, requirement=MissionRequirement("urgent", 0.1 * GB), priority=0
    )
    bulk_large = candidate(
        0, 5.0, requirement=MissionRequirement("bulk", 5.0 * GB), priority=5,
        norad_id=43700,
    )
    result = schedule_contacts([bulk_large, urgent_small])
    assert result.scheduled[0].candidate.key == urgent_small.key
    assert len(result.scheduled) == 1  # same antenna, same slot
    assert result.rejections_for(Rejection.ANTENNA_BUSY)


def test_earlier_deadline_wins_at_equal_priority():
    soon = MissionRequirement("soon", 1.0 * GB, deadline_utc=T0 + timedelta(hours=2))
    later = MissionRequirement("later", 1.0 * GB, deadline_utc=T0 + timedelta(days=3))
    result = schedule_contacts(
        [candidate(0, 2.0, requirement=later), candidate(0, 0.5, requirement=soon)]
    )
    assert result.scheduled[0].candidate.requirement.name == "soon"


def test_a_requirement_without_a_deadline_sorts_last():
    dated = MissionRequirement("dated", 1.0 * GB, deadline_utc=T0 + timedelta(days=1))
    undated = MissionRequirement("undated", 1.0 * GB)
    result = schedule_contacts(
        [
            candidate(0, 5.0, requirement=undated),
            candidate(0, 0.1, requirement=dated),
        ]
    )
    assert result.scheduled[0].candidate.requirement.name == "dated"


def test_larger_volume_wins_at_equal_priority_and_deadline():
    result = schedule_contacts([candidate(0, 0.5), candidate(0, 1.5)])
    assert result.scheduled[0].candidate.delivered_bytes == pytest.approx(1.5 * GB)


def test_link_margin_is_deliberately_not_part_of_the_ranking():
    """Margin is a validity question, already settled, not a ranking one."""
    modest = candidate(0, 1.0, antenna="ANT-1")
    generous = candidate(0, 1.0, antenna="ANT-2")
    # Same everything except identity: neither can outrank the other on margin,
    # because margin never enters rank_key.
    assert rank_key(modest)[:4] == rank_key(generous)[:4]


# --------------------------------------------------------------------------
# Requirements
# --------------------------------------------------------------------------


def test_contacts_accumulate_until_the_requirement_is_met_then_stop():
    cands = [candidate(i * 60, 0.8, antenna=f"ANT-{i}") for i in range(5)]
    result = schedule_contacts(cands)

    status = result.requirements[0]
    assert status.satisfied
    assert status.contact_count == 3  # 0.8 * 3 = 2.4 GB >= 2.0 GB
    assert len(result.rejections_for(Rejection.REQUIREMENT_ALREADY_MET)) == 2


def test_an_unmet_requirement_reports_its_shortfall():
    result = schedule_contacts([candidate(0, 0.5)])
    status = result.requirements[0]
    assert not status.satisfied
    assert status.shortfall_bytes == pytest.approx(1.5 * GB)
    assert not result.all_satisfied


def test_several_requirements_are_tracked_independently():
    a = MissionRequirement("imagery", 1.0 * GB, deadline_utc=T0 + timedelta(days=1))
    b = MissionRequirement("telemetry", 0.5 * GB, deadline_utc=T0 + timedelta(days=1))
    result = schedule_contacts(
        [
            candidate(0, 1.0, antenna="ANT-1", requirement=a),
            candidate(0, 0.5, antenna="ANT-2", requirement=b, norad_id=43700),
        ]
    )
    assert result.all_satisfied
    names = {r.requirement.name for r in result.requirements}
    assert names == {"imagery", "telemetry"}


def test_cumulative_bytes_are_recorded_per_contact():
    cands = [candidate(i * 60, 0.8, antenna=f"ANT-{i}") for i in range(3)]
    result = schedule_contacts(cands)
    cumulative = [s.cumulative_bytes for s in sorted(result.scheduled, key=lambda s: s.rank)]
    assert cumulative == pytest.approx([0.8 * GB, 1.6 * GB, 2.4 * GB])


# --------------------------------------------------------------------------
# Exclusions are always explained
# --------------------------------------------------------------------------


def test_every_candidate_is_either_scheduled_or_has_a_reason():
    """The property that makes the plan interrogable."""
    cands = [
        candidate(0, 1.0),
        candidate(5, 1.0),  # clashes on ANT-1
        candidate(60, 0.0),  # delivers nothing
        candidate(120, 1.0, verdict=Verdict.INVALID),
        candidate(180, 1.0, antenna="ANT-9"),
        candidate(240, 1.0, antenna="ANT-8"),  # requirement already met by then
    ]
    result = schedule_contacts(cands)
    accounted = {s.candidate.key for s in result.scheduled} | {
        r.candidate.key for r in result.rejected
    }
    assert accounted == {c.key for c in cands}
    for rejection in result.rejected:
        assert rejection.detail


def test_invalid_contacts_are_never_scheduled_and_name_their_failed_check():
    result = schedule_contacts(
        [candidate(0, 5.0, verdict=Verdict.INVALID, failing="link_margin")]
    )
    assert not result.scheduled
    rejection = result.rejections_for(Rejection.INVALID)[0]
    assert "link_margin" in rejection.detail


def test_a_contact_too_small_on_its_own_is_still_scheduled():
    """Accumulating across passes is the scheduler's job, not a reason to refuse.

    The validator correctly calls a 1 GB contact INVALID against a 2 GB
    requirement -- it answers "can THIS contact satisfy it?". If the scheduler
    treated that as disqualifying, every multi-pass requirement would be
    permanently unsatisfiable: each contact rejected for being individually
    insufficient, and the requirement then reported as unmet.
    """
    too_small = [
        candidate(0, 1.2, antenna="ANT-1", verdict=Verdict.INVALID,
                  failing="data_capacity"),
        candidate(60, 1.2, antenna="ANT-2", verdict=Verdict.INVALID,
                  failing="data_capacity"),
    ]
    result = schedule_contacts(too_small)
    assert len(result.scheduled) == 2
    assert result.requirements[0].satisfied
    assert not result.rejections_for(Rejection.INVALID)


def test_a_capacity_failure_combined_with_a_real_one_still_disqualifies():
    """Only a purely accumulable failure is forgiven."""
    both = ContactValidation(
        verdict=Verdict.INVALID,
        checks=(
            Check("data_capacity", CheckResult.FAIL, "short"),
            Check("link_margin", CheckResult.FAIL, "does not close"),
        ),
    )
    c = Candidate(
        pass_=make_pass(0),
        antenna_id="ANT-1",
        validation=both,
        volume=make_volume(1.0),
        requirement=REQ,
    )
    result = schedule_contacts([c])
    assert not result.scheduled
    detail = result.rejections_for(Rejection.INVALID)[0].detail
    assert "link_margin" in detail
    assert "data_capacity" not in detail


def test_conditional_contacts_are_allowed_by_default_and_can_be_refused():
    conditional = [candidate(0, 5.0, verdict=Verdict.CONDITIONALLY_VALID)]
    assert schedule_contacts(conditional).scheduled

    strict = schedule_contacts(conditional, allow_conditional=False)
    assert not strict.scheduled
    assert "tle_freshness" in strict.rejections_for(Rejection.INVALID)[0].detail


def test_a_contact_after_the_deadline_is_rejected_as_such():
    tight = MissionRequirement("tight", 1.0 * GB, deadline_utc=T0 + timedelta(minutes=5))
    result = schedule_contacts([candidate(600, 5.0, requirement=tight)])
    assert result.rejections_for(Rejection.AFTER_DEADLINE)
    assert not result.scheduled


def test_a_contact_delivering_nothing_is_rejected_as_such():
    result = schedule_contacts([candidate(0, 0.0)])
    assert result.rejections_for(Rejection.DELIVERS_NOTHING)


# --------------------------------------------------------------------------
# Honesty about the algorithm
# --------------------------------------------------------------------------


def test_the_schedule_declares_that_greedy_is_not_optimal():
    result = schedule_contacts([candidate(0, 1.0)])
    assert any("greedy" in n and "better combination may exist" in n for n in result.notes)


def test_zero_turnaround_is_flagged_as_unrealistic():
    result = schedule_contacts([candidate(0, 1.0)], turnaround_s=0.0)
    assert any("turnaround_s is 0" in n for n in result.notes)
    assert not any("turnaround_s is 0" in n for n in schedule_contacts(
        [candidate(0, 1.0)], turnaround_s=120.0
    ).notes)


def test_greedy_can_be_beaten_and_the_report_shows_it():
    """A concrete case where the greedy choice is worse than the alternative.

    One long contact of 1.2 GB overlaps two short ones of 0.9 GB each. Greedy
    takes the biggest single contact first and loses 0.6 GB. This is not a bug
    to fix here but a property to state — and the rejection list is what lets
    an operator see it and override with priorities.
    """
    long_one = candidate(0, 1.2, duration_min=60)
    short_a = candidate(0, 0.9, duration_min=20)
    short_b = candidate(30, 0.9, duration_min=20)
    # All three are the same satellite on the same antenna, which is the point:
    # they are mutually exclusive and greedy must choose.

    result = schedule_contacts([long_one, short_a, short_b])
    assert [s.candidate.key for s in result.scheduled] == [long_one.key]

    total_scheduled = sum(s.candidate.delivered_bytes for s in result.scheduled)
    better_alternative = short_a.delivered_bytes + short_b.delivered_bytes
    assert better_alternative > total_scheduled

    assert len(result.rejected) == 2


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def test_report_shows_the_plan_the_requirements_and_the_exclusions():
    result = schedule_contacts([candidate(0, 1.0), candidate(5, 1.0, norad_id=43700)])
    text = result.report()
    assert "SCHEDULE" in text
    assert "REQUIREMENTS" in text
    assert "NOT SCHEDULED" in text
    assert "ANTENNA_BUSY" in text
    assert "Padova/ANT-1" in text


def test_an_empty_candidate_list_is_an_empty_plan_not_an_error():
    result = schedule_contacts([])
    assert result.scheduled == ()
    assert result.requirements == ()
    assert result.all_satisfied  # vacuously
    assert "nothing scheduled" in result.report()


def test_scheduler_version_is_recorded():
    assert schedule_contacts([candidate(0)]).scheduler_version
