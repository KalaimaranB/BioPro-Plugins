"""Gate factory for reconstructing gates from dictionaries.
"""

from __future__ import annotations

import numpy as np

from .base import Gate
from .rectangle import RectangleGate
from .polygon import PolygonGate
from .ellipse import EllipseGate
from .quadrant import QuadrantGate
from .range import RangeGate

_GATE_REGISTRY: dict[str, type[Gate]] = {
    "RectangleGate": RectangleGate,
    "PolygonGate": PolygonGate,
    "EllipseGate": EllipseGate,
    "QuadrantGate": QuadrantGate,
    "RangeGate": RangeGate,
}

def gate_from_dict(data: dict) -> Gate:
    """Reconstruct a Gate instance from a serialized dictionary.
    
    Args:
        data: A dictionary containing the serialized gate attributes. Must
              include at least a 'type' key matching a registered gate class
              (e.g., 'RectangleGate') and the 'x_param' key.
              
    Returns:
        Gate: An instantiated subclass of Gate containing the deserialized state.
        
    Raises:
        ValueError: If the 'type' key does not correspond to any known Gate class.
        KeyError: If required keys like 'x_param' are missing from the data.
    """
    gate_type = data.get("type", "")
    cls = _GATE_REGISTRY.get(gate_type)
    if cls is None:
        raise ValueError(f"Unknown gate type: {gate_type!r}")

    # Common kwargs
    kwargs = {
        "x_param": data["x_param"],
        "adaptive": data.get("adaptive", False),
        "gate_id": data.get("gate_id"),
    }
    if data.get("y_param"):
        kwargs["y_param"] = data["y_param"]

    # Type-specific kwargs
    if gate_type == "RectangleGate":
        kwargs.update(x_min=data.get("x_min", -np.inf),
                      x_max=data.get("x_max", np.inf),
                      y_min=data.get("y_min", -np.inf),
                      y_max=data.get("y_max", np.inf),
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "PolygonGate":
        kwargs.update(vertices=[tuple(v) for v in data.get("vertices", [])],
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "EllipseGate":
        kwargs.update(center=tuple(data.get("center", (0, 0))),
                      width=data.get("width", 1),
                      height=data.get("height", 1),
                      angle=data.get("angle", 0),
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "QuadrantGate":
        kwargs.update(x_mid=data.get("x_mid", 0),
                      y_mid=data.get("y_mid", 0),
                      x_scale=data.get("x_scale"),
                      y_scale=data.get("y_scale"))
    elif gate_type == "RangeGate":
        kwargs.update(low=data.get("low", -np.inf),
                      high=data.get("high", np.inf),
                      x_scale=data.get("x_scale"))

    return cls(**kwargs)
