"""Gate factory for reconstructing gates from dictionaries.
"""

from __future__ import annotations

import numpy as np

from .base import Gate
from .rectangle import RectangleGate
from .polygon import PolygonGate
from .ellipse import EllipseGate
from .quadrant import QuadrantGate, QuadrantSubGate
from .range import RangeGate

_GATE_REGISTRY: dict[str, type[Gate]] = {
    "RectangleGate": RectangleGate,
    "PolygonGate": PolygonGate,
    "EllipseGate": EllipseGate,
    "QuadrantGate": QuadrantGate,
    "QuadrantSubGate": QuadrantSubGate,
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

    # Use the polymorphic from_dict method to handle type-specific reconstruction.
    # This satisfies the Open/Closed Principle (OCP).
    return cls.from_dict(data)
