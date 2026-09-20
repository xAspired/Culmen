"""Architectural guards.

``core/`` is the scientific library: it must stay installable and testable
with no web framework, no database and no network. These tests fail the build
the moment that boundary is crossed, which is the only way such a rule
survives contact with a deadline.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1] / "core"

#: Packages core/ must never reach for. FastAPI, SQLAlchemy and HTTP clients
#: belong to the layers above it.
FORBIDDEN_PREFIXES = (
    "backend",
    "fastapi",
    "sqlalchemy",
    "alembic",
    "starlette",
    "pydantic",
    "requests",
    "httpx",
    "urllib",
    "socket",
    "psycopg",
    "psycopg2",
)

CORE_FILES = sorted(CORE.rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_core_has_python_files():
    assert CORE_FILES, "core/ package not found"


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: str(p.relative_to(CORE)))
def test_core_does_not_import_upper_layers(path: Path):
    for module in _imported_modules(path):
        root = module.split(".")[0]
        assert root not in FORBIDDEN_PREFIXES, (
            f"{path.relative_to(CORE)} imports {module!r}: core/ must stay free of "
            f"web, database and network dependencies"
        )


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: str(p.relative_to(CORE)))
def test_core_modules_import_cleanly_in_isolation(path: Path):
    """No import-time side effects that need a database or a network call."""
    module = ".".join(path.relative_to(CORE.parent).with_suffix("").parts)
    __import__(module)


_UNIT_SUFFIXES = (
    "_deg", "_rad", "_km", "_m", "_s", "_hz", "_db", "_dbw", "_dbm", "_dbi", "_dbk",
    "_w", "_k", "_bps", "_bytes", "_days", "_km_s", "_kms", "_utc", "_version",
    "_ref", "_name", "_id", "_profile", "_step_s", "_j_k", "_m_s", "_dbw_hz_k",
    "_dbhz", "_dbk", "_hz", "_bps", "_efficiency", "_temp_k", "_ratio", "_count",
    # Meteorology (ITU-R models): hectopascals, grams per cubic metre, and a
    # percentage of an average year. All three are units, not bare numbers.
    "_hpa", "_g_m3", "_percent",
)
#: Fields that are genuinely dimensionless or non-numeric.
_UNITLESS_ALLOWED = {
    "value", "unit", "inputs", "assumptions", "warnings", "samples", "eccentricity",
    "name", "source", "line1", "line2", "status", "checks", "result", "message",
    "schema_version", "horizon_profile", "classification", "cospar_id",
    # Genuinely dimensionless ordinals, not measurements.
    "priority", "rank",
}


def test_dataclass_fields_declare_their_units():
    """Unit suffixes are mandatory in scientific code; this enforces it.

    ``range_km`` cannot be mistaken for metres at a glance, ``range`` can.
    This test is cheaper and faster than a units library and catches the same
    class of error at review time.
    """
    offenders: list[str] = []
    for path in CORE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                isinstance(d, (ast.Call, ast.Name, ast.Attribute)) and "dataclass" in ast.unparse(d)
                for d in node.decorator_list
            ):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                field = stmt.target.id
                annotation = ast.unparse(stmt.annotation)
                if field in _UNITLESS_ALLOWED:
                    continue
                if not re.search(r"float|int", annotation):
                    continue
                if not field.endswith(_UNIT_SUFFIXES):
                    offenders.append(f"{path.relative_to(CORE)}::{node.name}.{field}")
    assert not offenders, "numeric fields without a unit suffix: " + ", ".join(offenders)


def test_every_formula_reference_points_at_a_real_note():
    """An audit trail that cites a missing file is worse than none at all.

    Every ``formula_ref`` string literal in core/ must resolve to a file that
    exists in docs/math/. This is what stops the provenance from rotting as
    notes get renamed.
    """
    repo = CORE.parent
    missing: list[str] = []
    for path in CORE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                ref = node.value
                if ref.startswith("docs/math/") and not (repo / ref).is_file():
                    missing.append(f"{path.relative_to(CORE)}:{node.lineno} -> {ref}")
    assert not missing, "formula_ref pointing at a non-existent note: " + ", ".join(missing)


# --------------------------------------------------------------------------
# Release readiness
# --------------------------------------------------------------------------


def test_the_community_health_files_exist():
    """A public repository without these is an incomplete one."""
    repo = CORE.parent
    for name in (
        "README.md",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
    ):
        path = repo / name
        assert path.is_file(), f"{name} is missing"
        assert path.stat().st_size > 200, f"{name} looks like a stub"


def test_the_licence_is_the_real_apache_text_not_a_placeholder():
    """A placeholder LICENSE is worse than none: it asserts terms that are absent.

    The operative sections are checked by name. The text shipped here was
    taken verbatim from an Apache-2.0 copy distributed with an installed
    dependency and cross-checked byte-for-byte, through END OF TERMS AND
    CONDITIONS, against a second independent copy.
    """
    text = (CORE.parent / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
    for clause in (
        "1. Definitions.",
        "2. Grant of Copyright License.",
        "3. Grant of Patent License.",  # the reason Apache-2.0 was chosen
        "4. Redistribution.",
        "7. Disclaimer of Warranty.",
        "8. Limitation of Liability.",
        "END OF TERMS AND CONDITIONS",
    ):
        assert clause in text, f"LICENSE is missing {clause!r}"
    assert "TODO" not in text
    assert len(text) > 10_000


def test_the_project_states_what_it_does_not_do():
    """The limitations must be visible on the landing page, not only in docs."""
    readme = (CORE.parent / "README.md").read_text(encoding="utf-8")
    assert "Known limitations" in readme
    assert "A-RF-1" in readme  # the atmospheric gap, named
    assert "never transmits" in readme
