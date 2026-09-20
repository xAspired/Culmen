#!/usr/bin/env python3
"""Fetch element sets from CelesTrak into ``data/tle/``.

Culmen ships no bulk orbital data (data/README.md). This script is how you
populate a local catalogue, and it is written to respect CelesTrak's usage
policy rather than to be as fast as possible:

* **an identifiable User-Agent with a contact address**, which the script
  refuses to run without;
* **conditional requests** — ``If-Modified-Since`` and ``If-None-Match`` from
  a cached response, so an unchanged group costs a 304 and no payload;
* **a minimum interval between fetches of the same group** (three hours by
  default), enforced locally and overridable only with an explicit flag;
* **no redistribution** — everything lands in ``data/tle/``, which is
  gitignored apart from the small historical example.

Usage::

    export CULMEN_CONTACT="you@example.org"
    python scripts/fetch_tle.py                    # a sensible default set
    python scripts/fetch_tle.py --group active     # ~11 000 objects
    python scripts/fetch_tle.py --list-cached

Group names are CelesTrak's own; see their "NORAD GP Element Sets" page for
the current list. The script does not validate them locally — an unknown group
comes back from the server and is reported as such.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import formatdate
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "tle"
CACHE_NAME = ".fetch-cache.json"

GP_URL = "https://celestrak.org/NORAD/elements/gp.php"

#: A modest default: enough to be useful, far short of the whole catalogue.
DEFAULT_GROUPS = ("stations", "cubesat", "weather", "noaa", "science")

#: Minimum seconds between fetches of the same group.
MIN_INTERVAL_S = 3 * 3600

VERSION = "0.9"


class PolicyError(RuntimeError):
    """The request would breach the usage policy we committed to."""


@dataclass(frozen=True, slots=True)
class CacheEntry:
    fetched_at: float
    etag: str | None
    last_modified: str | None
    satellites: int

    def to_dict(self) -> dict[str, object]:
        return {
            "fetched_at": self.fetched_at,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "satellites": self.satellites,
        }

    @staticmethod
    def from_dict(d: dict[str, object]) -> CacheEntry:
        etag = d.get("etag")
        last_modified = d.get("last_modified")
        return CacheEntry(
            fetched_at=float(d.get("fetched_at", 0.0)),  # type: ignore[arg-type]
            etag=etag if isinstance(etag, str) else None,
            last_modified=last_modified if isinstance(last_modified, str) else None,
            satellites=int(d.get("satellites", 0)),  # type: ignore[call-overload]
        )


def user_agent(contact: str | None) -> str:
    """Identify ourselves, with a contact address. No contact, no fetch.

    An anonymous scraper is exactly what a data provider's rate limits exist
    to stop, and Culmen's data policy says it will not be one.
    """
    if not contact or "@" not in contact:
        raise PolicyError(
            "set CULMEN_CONTACT to an email address (or pass --contact).\n"
            "CelesTrak's usage policy expects an identifiable User-Agent, and "
            "Culmen will not fetch anonymously."
        )
    return f"Culmen/{VERSION} (+https://github.com/; {contact})"


def load_cache(out_dir: Path) -> dict[str, CacheEntry]:
    path = out_dir / CACHE_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: CacheEntry.from_dict(v) for k, v in raw.items() if isinstance(v, dict)}


def save_cache(out_dir: Path, cache: dict[str, CacheEntry]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / CACHE_NAME).write_text(
        json.dumps({k: v.to_dict() for k, v in cache.items()}, indent=2),
        encoding="utf-8",
    )


def too_soon(entry: CacheEntry | None, now: float, min_interval_s: int) -> float:
    """Seconds still to wait before this group may be fetched again."""
    if entry is None:
        return 0.0
    return max(0.0, min_interval_s - (now - entry.fetched_at))


def build_request(
    group: str, entry: CacheEntry | None, contact: str | None
) -> urllib.request.Request:
    url = f"{GP_URL}?GROUP={group}&FORMAT=tle"
    request = urllib.request.Request(url)
    request.add_header("User-Agent", user_agent(contact))
    request.add_header("Accept", "text/plain")
    if entry is not None:
        if entry.etag:
            request.add_header("If-None-Match", entry.etag)
        if entry.last_modified:
            request.add_header("If-Modified-Since", entry.last_modified)
        elif entry.fetched_at:
            request.add_header(
                "If-Modified-Since", formatdate(entry.fetched_at, usegmt=True)
            )
    return request


def count_element_sets(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("1 "))


def fetch_group(
    group: str,
    out_dir: Path,
    cache: dict[str, CacheEntry],
    contact: str | None,
    *,
    force: bool = False,
    min_interval_s: int = MIN_INTERVAL_S,
    timeout: float = 30.0,
) -> str:
    """Fetch one group. Returns a one-line human-readable outcome."""
    now = time.time()
    entry = cache.get(group)

    wait = 0.0 if force else too_soon(entry, now, min_interval_s)
    if wait > 0:
        return (
            f"{group}: skipped, fetched {int((now - entry.fetched_at) / 60)} min ago "  # type: ignore[union-attr]
            f"(wait {int(wait / 60)} min, or pass --force)"
        )

    request = build_request(group, entry, contact)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = response.headers
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            if entry is not None:
                cache[group] = CacheEntry(now, entry.etag, entry.last_modified,
                                          entry.satellites)
            return f"{group}: unchanged (304), {entry.satellites if entry else 0} kept"
        return f"{group}: HTTP {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return f"{group}: not reachable ({exc.reason})"

    # CelesTrak answers an unknown group with a short text body, not an error.
    count = count_element_sets(body)
    if count == 0:
        return f"{group}: no element sets returned — check the group name ({body.strip()[:80]})"

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{group}.tle"
    target.write_text(body, encoding="utf-8")
    cache[group] = CacheEntry(
        fetched_at=now,
        etag=headers.get("ETag"),
        last_modified=headers.get("Last-Modified"),
        satellites=count,
    )
    return f"{group}: {count} element sets -> {target.relative_to(REPO_ROOT)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch element sets from CelesTrak into data/tle/.",
        epilog="Culmen redistributes no orbital data; this populates your copy.",
    )
    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        help=f"CelesTrak group; repeatable. Default: {', '.join(DEFAULT_GROUPS)}",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--contact",
        default=os.environ.get("CULMEN_CONTACT"),
        help="contact address for the User-Agent (or set CULMEN_CONTACT)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ignore the local minimum interval between fetches",
    )
    parser.add_argument(
        "--min-interval-s", type=int, default=MIN_INTERVAL_S,
        help=f"minimum seconds between fetches of a group (default {MIN_INTERVAL_S})",
    )
    parser.add_argument("--list-cached", action="store_true")
    args = parser.parse_args(argv)

    cache = load_cache(args.out)

    if args.list_cached:
        if not cache:
            print("nothing fetched yet")
            return 0
        now = time.time()
        for group, entry in sorted(cache.items()):
            age_h = (now - entry.fetched_at) / 3600
            print(f"{group:<14} {entry.satellites:>6} sets   fetched {age_h:.1f} h ago")
        return 0

    try:
        user_agent(args.contact)
    except PolicyError as exc:
        print(exc, file=sys.stderr)
        return 2

    groups = args.groups or list(DEFAULT_GROUPS)
    print(f"fetching {len(groups)} group(s) into {args.out}")
    for group in groups:
        print("  " + fetch_group(
            group, args.out, cache, args.contact,
            force=args.force, min_interval_s=args.min_interval_s,
        ))
    save_cache(args.out, cache)

    print(
        "\nAttribution: orbital data from CelesTrak (celestrak.org). The element "
        "sets derive from US Government sources and are not subject to "
        "copyright; CelesTrak's usage policy still applies. Do not redistribute "
        "these files — see data/README.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
