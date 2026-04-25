"""Initializes the gate registry with default flow cytometry gates."""

from .gate_registry import GateRegistry
from ...analysis.gating import (
    RectangleGate, PolygonGate, EllipseGate, QuadrantGate, RangeGate
)

def initialize_registry():
    """Register core gate types."""
    GateRegistry.register_gate_type("rectangle", RectangleGate)
    GateRegistry.register_gate_type("polygon", PolygonGate)
    GateRegistry.register_gate_type("ellipse", EllipseGate)
    GateRegistry.register_gate_type("quadrant", QuadrantGate)
    GateRegistry.register_gate_type("range", RangeGate)
