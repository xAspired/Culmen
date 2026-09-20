"""TLE ingestion, validation and metadata.

A TLE is not just two strings: its *epoch* and its *age* determine whether any
downstream result is trustworthy. SGP4 error grows roughly with the square of
the time from epoch; a week-old LEO element set can be kilometres off along
track, which moves AOS by seconds to tens of seconds.

Culmen therefore treats TLE age as a first-class, reported quantity, and
the pass/contact layers surface it as a WARN rather than hiding it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from core.time.scales import UTC, ensure_utc, seconds_between

#: Above this age the element set is flagged; results remain computable.
TLE_AGE_WARN_DAYS: float = 7.0
#: Above this age we refuse by default; caller may override explicitly.
TLE_AGE_REJECT_DAYS: float = 30.0

_LINE_RE = re.compile(r"^[12] ")


class TleError(ValueError):
    """Malformed or inconsistent two-line element set."""


def tle_checksum(line: str) -> int:
    """Modulo-10 checksum over the first 68 characters.

    Digits count as themselves, '-' counts as 1, everything else as 0.
    Reference: Vallado & Cefola, and the CelesTrak TLE format description.
    """
    total = 0
    for ch in line[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return total % 10


@dataclass(frozen=True, slots=True)
class Tle:
    """A validated two-line element set."""

    line1: str
    line2: str
    name: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        for idx, line in ((1, self.line1), (2, self.line2)):
            if len(line) < 69:
                raise TleError(f"line{idx} is {len(line)} chars, expected at least 69")
            if not line.startswith(f"{idx} "):
                raise TleError(f"line{idx} must start with '{idx} ', got {line[:2]!r}")
            expected = tle_checksum(line)
            try:
                actual = int(line[68])
            except ValueError as exc:
                raise TleError(f"line{idx} checksum column is not a digit") from exc
            if actual != expected:
                raise TleError(
                    f"line{idx} checksum mismatch: column 69 is {actual}, computed {expected}"
                )
        if self.line1[2:7] != self.line2[2:7]:
            raise TleError(
                f"satellite number differs between lines: "
                f"{self.line1[2:7]!r} vs {self.line2[2:7]!r}"
            )

    # --- parsed fields -------------------------------------------------
    @property
    def norad_id(self) -> int:
        return int(self.line1[2:7])

    @property
    def classification(self) -> str:
        return self.line1[7]

    @property
    def cospar_id(self) -> str:
        """International designator, e.g. '1998-067A'. Empty when absent."""
        raw = self.line1[9:17].strip()
        if not raw:
            return ""
        yy = int(raw[:2])
        century = 1900 if yy >= 57 else 2000
        return f"{century + yy}-{raw[2:]}"

    @property
    def epoch_utc(self) -> datetime:
        """Element-set epoch as an aware UTC datetime.

        Columns 19-32: two-digit year (57-99 -> 19xx, 00-56 -> 20xx) followed
        by fractional day-of-year. Decoded on the continuous scale to avoid
        month-length and leap-year mistakes.
        """
        yy = int(self.line1[18:20])
        year = 1900 + yy if yy >= 57 else 2000 + yy
        doy_frac = float(self.line1[20:32])
        day = int(doy_frac)
        seconds = (doy_frac - day) * 86400.0
        base = datetime(year, 1, 1, tzinfo=UTC)
        from core.time.scales import add_seconds  # local import: avoids cycle at module load

        return add_seconds(base, (day - 1) * 86400.0 + seconds)

    @property
    def mean_motion_rev_day(self) -> float:
        return float(self.line2[52:63])

    @property
    def inclination_deg(self) -> float:
        return float(self.line2[8:16])

    @property
    def eccentricity(self) -> float:
        return float("0." + self.line2[26:33].strip())

    @property
    def revolution_number(self) -> int:
        return int(self.line2[63:68])

    # --- age -----------------------------------------------------------
    def age_days(self, at: datetime) -> float:
        """Signed age in days at ``at``; negative means ``at`` precedes epoch."""
        return seconds_between(self.epoch_utc, ensure_utc(at)) / 86400.0

    def age_warning(self, at: datetime) -> str | None:
        age = abs(self.age_days(at))
        if age > TLE_AGE_REJECT_DAYS:
            return (
                f"TLE is {age:.1f} days from epoch (limit {TLE_AGE_REJECT_DAYS:.0f}); "
                f"propagated state is not usable for planning"
            )
        if age > TLE_AGE_WARN_DAYS:
            return (
                f"TLE is {age:.1f} days from epoch (warn above {TLE_AGE_WARN_DAYS:.0f}); "
                f"along-track error may reach kilometres"
            )
        return None


def parse_tle_text(text: str, source: str | None = None) -> list[Tle]:
    """Parse a 2- or 3-line-per-satellite TLE file into validated :class:`Tle`.

    Blank lines are skipped. A non-'1 '/'2 ' line immediately preceding a
    line 1 is taken as the satellite name (the 3LE / NASA convention).
    """
    lines = [ln.rstrip("\r\n") for ln in text.splitlines() if ln.strip()]
    out: list[Tle] = []
    i = 0
    pending_name: str | None = None
    while i < len(lines):
        line = lines[i]
        if _LINE_RE.match(line) and line.startswith("1 "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("2 "):
                raise TleError(f"line 1 at index {i} is not followed by a line 2")
            out.append(
                Tle(
                    line1=line,
                    line2=lines[i + 1],
                    name=pending_name.strip() if pending_name else None,
                    source=source,
                )
            )
            pending_name = None
            i += 2
        elif _LINE_RE.match(line):
            raise TleError(f"orphan line 2 at index {i}")
        else:
            pending_name = line
            i += 1
    if not out:
        raise TleError("no element sets found in input")
    return out
