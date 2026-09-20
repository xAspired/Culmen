"""Audit trail for every number that ends up in a verdict.

The distinguishing feature of Culmen is the explainable, reproducible
verdict. That is only possible if each computed quantity carries its own
inputs, unit, formula reference and declared assumptions.

Rule: any value that a Contact Validator check compares against a threshold
MUST be a Computed[...]. Intermediate scratch values need not be.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Computed(Generic[T]):
    value: T
    unit: str
    formula_ref: str
    """Path of the maths note that defines this quantity, e.g. 'docs/math/fspl.md'."""
    inputs: dict[str, float] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.unit:
            raise ValueError("Computed.unit must be a non-empty string (use '1' for dimensionless)")
        if not self.formula_ref:
            raise ValueError("Computed.formula_ref must reference a docs/math/ note")

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "unit": self.unit,
            "formula_ref": self.formula_ref,
            "inputs": dict(self.inputs),
            "assumptions": list(self.assumptions),
        }
