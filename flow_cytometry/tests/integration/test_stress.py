import pytest
import pandas as pd
import numpy as np
import time
from flow_cytometry.analysis.gating import RectangleGate, GateNode

@pytest.fixture
def stress_data():
    """Generate 1M synthetic events."""
    np.random.seed(42)
    n = 1_000_000
    return pd.DataFrame({
        "FSC-A": np.random.rand(n) * 262144,
        "SSC-A": np.random.rand(n) * 262144,
        "CD4": np.random.rand(n) * 262144
    })

def test_apply_hierarchy_stress(stress_data):
    """Verify performance of apply_hierarchy on 1M events."""
    # Build a 5-level hierarchy
    root = GateNode(name="Root")
    
    g1 = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=0, x_max=200000, y_min=0, y_max=200000)
    n1 = root.add_child(g1, name="Level 1")
    
    g2 = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=0, x_max=150000, y_min=0, y_max=150000)
    n2 = n1.add_child(g2, name="Level 2")
    
    g3 = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=0, x_max=100000, y_min=0, y_max=100000)
    n3 = n2.add_child(g3, name="Level 3")
    
    g4 = RectangleGate(x_param="FSC-A", y_param="SSC-A", x_min=0, x_max=50000, y_min=0, y_max=50000)
    n4 = n3.add_child(g4, name="Level 4")
    
    g5 = RectangleGate(x_param="CD4", y_param="FSC-A", x_min=0, x_max=20000, y_min=0, y_max=20000)
    n5 = n4.add_child(g5, name="Level 5")
    
    start_time = time.time()
    subset = n5.apply_hierarchy(stress_data)
    duration = time.time() - start_time
    
    print(f"\nStress Test: Applied 5-level hierarchy to 1M events in {duration:.4f}s")
    
    # Threshold: Should be well under 1 second on modern hardware with vectorized operations.
    # On most machines, 1M bitwise ANDs and one loc take ~50-100ms.
    assert duration < 0.5, f"Performance too slow: {duration:.4f}s"
    assert len(subset) < 1_000_000
