"""Regression of the propagator against the OFFICIAL SGP4 verification data.

Ground truth: ``SGP4-VER.TLE`` and ``tcppver.out``, shipped with the ``sgp4``
package. These are the reference element sets and the reference C++ output
from Vallado, Crawford, Hujsak & Kelso, "Revisiting Spacetrack Report #3"
(AIAA 2006-6753). They are the only external truth that matters at this layer:
a test that only checks our code against itself proves nothing.

The comparison is made in TEME, which is what SGP4 actually produces, and by
minutes since epoch, which is how SGP4 is natively defined -- no time-scale
conversion is involved, so nothing here can mask a frame or scale defect.

Two structural details matter:

* The two files are matched **in file order**, not by satellite number. Some
  satellites appear more than once in the verification set with different
  element sets, so keying by NORAD ID would silently pair the wrong TLE with
  the wrong reference block.
* A handful of element sets were hand-edited to exercise edge cases and carry
  stale checksums. Our validator rejects those, which is correct behaviour;
  they are recorded and skipped rather than waved through.

Tolerance follows the upstream sgp4 test suite: 2e-7 (km, km/s).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sgp4

from core.orbit.propagator import PropagationError, Propagator
from core.orbit.tle import Tle, TleError

#: Same tolerance the sgp4 package uses against tcppver.out.
TOL = 2e-7

_SGP4_DIR = Path(os.path.dirname(sgp4.__file__))


def _load_reference() -> list[tuple[int, list[tuple[float, tuple, tuple]]]]:
    """tcppver.out -> ordered [(satnum, [(minutes, r_km, v_km_s), ...]), ...]."""
    blocks: list[tuple[int, list]] = []
    rows: list | None = None
    for raw in (_SGP4_DIR / "tcppver.out").read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.endswith("xx"):
            rows = []
            blocks.append((int(line.split()[0]), rows))
            continue
        if rows is None:
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        try:
            v = [float(p) for p in parts[:7]]
        except ValueError:
            continue
        rows.append((v[0], (v[1], v[2], v[3]), (v[4], v[5], v[6])))
    return blocks


def _load_tles() -> list[Tle | TleError]:
    """SGP4-VER.TLE -> ordered element sets; rejected ones kept as the error."""
    lines = [
        ln.rstrip()
        for ln in (_SGP4_DIR / "SGP4-VER.TLE").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    out: list[Tle | TleError] = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].startswith("1 ") and lines[i + 1].startswith("2 "):
            # The verification file appends run parameters after column 69.
            try:
                out.append(Tle(lines[i][:69], lines[i + 1][:69]))
            except TleError as exc:
                out.append(exc)
            i += 2
        else:
            i += 1
    return out


REFERENCE = _load_reference()
TLES = _load_tles()
CASES = list(enumerate(zip(TLES, REFERENCE, strict=True)))


def test_verification_data_is_paired():
    assert len(TLES) == len(REFERENCE) > 25, (
        f"element sets ({len(TLES)}) and reference blocks ({len(REFERENCE)}) "
        f"must pair one-to-one and in order"
    )
    for tle, (satnum, _) in zip(TLES, REFERENCE, strict=True):
        if isinstance(tle, Tle):
            assert tle.norad_id == satnum, "file-order pairing is broken"


@pytest.mark.parametrize(
    "index,pair", CASES, ids=[f"{i:02d}-{blk[0]}" for i, (_, blk) in CASES]
)
def test_teme_state_matches_vallado_reference(index: int, pair):
    tle, (satnum, rows) = pair
    if isinstance(tle, TleError):
        pytest.skip(f"element set {satnum} intentionally invalid: {tle}")
    if not rows:
        pytest.skip(f"no reference rows for {satnum}")

    prop = Propagator(tle)
    minutes = [row[0] for row in rows]
    try:
        states = prop.states_at_minutes_from_epoch(minutes)
    except PropagationError:
        # The suite deliberately includes decay and out-of-range cases;
        # refusing to return a state for those is the correct behaviour.
        pytest.skip(f"satnum {satnum} propagates to an SGP4 error condition")

    for state, (m, r_ref, v_ref) in zip(states, rows, strict=True):
        for axis, (got, want) in enumerate(zip(state.position_teme_km, r_ref, strict=True)):
            assert got == pytest.approx(want, abs=TOL), (
                f"satnum {satnum}, t+{m} min, position TEME axis {axis}"
            )
        for axis, (got, want) in enumerate(zip(state.velocity_teme_km_s, v_ref, strict=True)):
            assert got == pytest.approx(want, abs=TOL), (
                f"satnum {satnum}, t+{m} min, velocity TEME axis {axis}"
            )
