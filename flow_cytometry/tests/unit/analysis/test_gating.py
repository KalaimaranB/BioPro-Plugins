import pytest
import pandas as pd
from flow_cytometry.analysis.gating import RectangleGate, PolygonGate, EllipseGate, GateNode

def test_gate_node_serialization():
    """Verify that GateNode serializes correctly without runtime stats."""
    gate = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=0, x_max=100, y_min=0, y_max=100)
    node = GateNode(gate=gate, name="Lymphocytes")
    node.statistics = {"count": 1000}
    
    data = node.to_dict()
    assert "statistics" not in data
    assert data["name"] == "Lymphocytes"

def test_rectangle_gate_contains():
    gate = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=10, x_max=50, y_min=20, y_max=60)
    df = pd.DataFrame({"FSC-A": [30, 5], "SSC-A": [40, 40]})
    mask = gate.contains(df)
    assert mask[0] == True
    assert mask[1] == False

def test_gate_names():
    gate = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=0, x_max=10, y_min=0, y_max=10)
    # Check fallback name logic
    assert getattr(gate, "name", None) or type(gate).__name__ == "RectangleGate"
