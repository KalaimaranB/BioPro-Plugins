"""QuadrantGate class.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import Gate
from ..transforms import apply_transform, TransformType
from ..scaling import AxisScale
from .._utils import (
    ScaleFactory,
    TransformTypeResolver,
    BiexponentialParameters,
    ScaleSerializer,
)

class QuadrantGate(Gate):
    """Quadrant gate — divides the plot into 4 regions at (x_mid, y_mid).
    """

    def __init__(
        self,
        x_param: str,
        y_param: str,
        *,
        x_mid: float = 0.0,
        y_mid: float = 0.0,
        adaptive: bool = False,
        gate_id: Optional[str] = None,
        x_scale: Optional[AxisScale] = None,
        y_scale: Optional[AxisScale] = None,
    ) -> None:
        super().__init__(
            x_param, y_param,
            adaptive=adaptive, gate_id=gate_id
        )
        self.x_mid = x_mid
        self.y_mid = y_mid
        self.x_scale: AxisScale = ScaleFactory.parse(x_scale)
        self.y_scale: AxisScale = ScaleFactory.parse(y_scale)

    def copy(self) -> QuadrantGate:
        return QuadrantGate(
            self.x_param, self.y_param,
            x_mid=self.x_mid, y_mid=self.y_mid,
            adaptive=self.adaptive, gate_id=self.gate_id,
            x_scale=self.x_scale.copy() if self.x_scale else None,
            y_scale=self.y_scale.copy() if self.y_scale else None,
        )

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Returns True for all events (the quadrant gate itself holds all)."""
        return np.ones(len(events), dtype=bool)

    def get_quadrant(
        self, events: pd.DataFrame, quadrant: str
    ) -> np.ndarray:
        """Return a boolean mask for a specific quadrant."""
        if self.x_param not in events.columns or self.y_param not in events.columns:
            return np.zeros(len(events), dtype=bool)

        q = quadrant.split()[0].upper() if quadrant else quadrant

        x_raw = events[self.x_param].values
        y_raw = events[self.y_param].values
        mid_x_raw = np.array([self.x_mid])
        mid_y_raw = np.array([self.y_mid])

        x_type = TransformTypeResolver.resolve(
            getattr(self.x_scale, "transform_type", "linear")
        )
        y_type = TransformTypeResolver.resolve(
            getattr(self.y_scale, "transform_type", "linear")
        )

        x_kwargs = (BiexponentialParameters(self.x_scale).to_dict()
                    if x_type == TransformType.BIEXPONENTIAL else {})
        y_kwargs = (BiexponentialParameters(self.y_scale).to_dict()
                    if y_type == TransformType.BIEXPONENTIAL else {})

        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        y_disp = apply_transform(y_raw, y_type, **y_kwargs)
        mid_x_disp = apply_transform(mid_x_raw, x_type, **x_kwargs)[0]
        mid_y_disp = apply_transform(mid_y_raw, y_type, **y_kwargs)[0]

        if q == "Q1": # Upper Left
            return (x_disp < mid_x_disp) & (y_disp >= mid_y_disp)
        elif q == "Q2": # Upper Right
            return (x_disp >= mid_x_disp) & (y_disp >= mid_y_disp)
        elif q == "Q3": # Lower Left
            return (x_disp < mid_x_disp) & (y_disp < mid_y_disp)
        elif q == "Q4": # Lower Right
            return (x_disp >= mid_x_disp) & (y_disp < mid_y_disp)
        else:
            raise ValueError(f"Invalid quadrant: {quadrant!r}")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(x_mid=self.x_mid, y_mid=self.y_mid)
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
        d["y_scale"] = ScaleSerializer.to_dict(self.y_scale)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> QuadrantGate:
        return cls(
            x_param=data["x_param"],
            y_param=data["y_param"],
            x_mid=data.get("x_mid", 0.0),
            y_mid=data.get("y_mid", 0.0),
            adaptive=data.get("adaptive", False),
            gate_id=data.get("gate_id"),
            x_scale=data.get("x_scale"),
            y_scale=data.get("y_scale"),
        )

class QuadrantSubGate(Gate):
    """Internal gate representing a single quadrant region.
    
    This class satisfies the Liskov Substitution Principle (LSP) by 
    implementing .contains() correctly for a specific quadrant region, 
    allowing generic analysis tools to compute statistics for individual 
    quadrants without specialized logic.
    """
    
    def __init__(
        self, 
        parent: QuadrantGate, 
        quadrant: str,
        gate_id: Optional[str] = None
    ):
        # The sub-gate ID is derived from the parent for consistency
        gid = gate_id or f"{parent.gate_id}_{quadrant}"
        super().__init__(parent.x_param, parent.y_param, gate_id=gid)
        self.parent = parent
        self.quadrant = quadrant

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Filter events for this specific quadrant."""
        return self.parent.get_quadrant(events, self.quadrant)

    def copy(self) -> QuadrantSubGate:
        return QuadrantSubGate(self.parent.copy(), self.quadrant, gate_id=self.gate_id)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "parent_gate": self.parent.to_dict(),
            "quadrant": self.quadrant
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> QuadrantSubGate:
        parent = QuadrantGate.from_dict(data["parent_gate"])
        return cls(parent, data["quadrant"], gate_id=data.get("gate_id"))
