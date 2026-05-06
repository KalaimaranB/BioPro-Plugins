"""PolygonGate class.
"""

from __future__ import annotations

from typing import Optional, Any

import numpy as np
import pandas as pd
from matplotlib.path import Path

from .base import Gate
from ..transforms import apply_transform, TransformType
from ..scaling import AxisScale
from .._utils import (
    ScaleFactory,
    TransformTypeResolver,
    BiexponentialParameters,
    ScaleSerializer,
)

class PolygonGate(Gate):
    """Polygonal gate defined by an ordered list of vertices.

    Vertices are stored in **raw data space**.  ``contains()`` projects vertices
    into display space before the point-in-polygon test.

    Attributes:
        vertices: Ordered ``[(x, y), ...]`` pairs in raw data space.
        x_scale:  Axis scale for the X parameter.
        y_scale:  Axis scale for the Y parameter.
    """

    def __init__(
        self,
        x_param: str,
        y_param: str,
        vertices: list[tuple[float, float]],
        x_scale: Optional[AxisScale] = None,
        y_scale: Optional[AxisScale] = None,
        name: str = "Polygon Gate",
        adaptive: bool = False,
        gate_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(x_param, y_param, adaptive=adaptive, gate_id=gate_id)
        self.name = name
        self.vertices = vertices
        self.x_scale = ScaleFactory.parse(x_scale)
        self.y_scale = ScaleFactory.parse(y_scale)

    def copy(self) -> PolygonGate:
        return PolygonGate(
            self.x_param, self.y_param,
            vertices=[v for v in self.vertices],
            x_scale=self.x_scale.copy() if self.x_scale else None,
            y_scale=self.y_scale.copy() if self.y_scale else None,
            name=self.name, adaptive=self.adaptive,
            gate_id=self.gate_id,
        )

    def contains(self, events: pd.DataFrame) -> np.ndarray:
        """Test which events fall inside this polygon gate."""
        if self.x_param not in events.columns:
            raise KeyError(self.x_param)
        if self.y_param not in events.columns:
            raise KeyError(self.y_param)

        x_raw = events[self.x_param].values
        y_raw = events[self.y_param].values
        vx_raw = np.array([v[0] for v in self.vertices])
        vy_raw = np.array([v[1] for v in self.vertices])

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

        # Project events into display space
        x_disp = apply_transform(x_raw, x_type, **x_kwargs)
        y_disp = apply_transform(y_raw, y_type, **y_kwargs)

        # Project raw-space vertices into the same display space
        vx_disp = apply_transform(vx_raw, x_type, **x_kwargs)
        vy_disp = apply_transform(vy_raw, y_type, **y_kwargs)

        points = np.column_stack((x_disp, y_disp))
        poly_path = Path(np.column_stack((vx_disp, vy_disp)))
        return poly_path.contains_points(points)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["vertices"] = [list(v) for v in self.vertices]
        d["x_scale"] = ScaleSerializer.to_dict(self.x_scale)
        d["y_scale"] = ScaleSerializer.to_dict(self.y_scale)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PolygonGate:
        return cls(
            x_param=data["x_param"],
            y_param=data["y_param"],
            vertices=[tuple(v) for v in data.get("vertices", [])],
            x_scale=data.get("x_scale"),
            y_scale=data.get("y_scale"),
            adaptive=data.get("adaptive", False),
            gate_id=data.get("gate_id"),
        )
