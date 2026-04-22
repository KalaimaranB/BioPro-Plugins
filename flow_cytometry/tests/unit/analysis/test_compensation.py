import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.compensation import CompensationMatrix

def test_compensation_matrix_init():
    detectors = ["FITC-A", "PE-A", "APC-A"]
    matrix = np.eye(3)
    comp = CompensationMatrix(matrix=matrix, channel_names=detectors)
    
    assert comp.channel_names == detectors
    assert comp.matrix.shape == (3, 3)
    assert comp.inverse.shape == (3, 3)

def test_compensation_apply():
    detectors = ["FITC-A", "PE-A"]
    # 10% spillover from PE to FITC because row @ M^-1 combines columns
    matrix = np.array([
        [1.0, 0.0],
        [0.1, 1.0]
    ])
    comp = CompensationMatrix(matrix=matrix, channel_names=detectors)
    
    class MockFCS:
        def __init__(self, events):
            self.events = events
            
    events = pd.DataFrame({
        "FITC-A": [100.0, 1000.0],
        "PE-A":   [1000.0, 0.0],
        "FSC-A":  [50000.0, 50000.0]  # Uncompensated channel
    })
    
    from flow_cytometry.analysis.compensation import apply_compensation
    comp_events = apply_compensation(MockFCS(events), comp)
    
    # FITC = Raw_FITC - 0.1 * PE -> 100 - 100 = 0
    assert np.isclose(comp_events["FITC-A"].iloc[0], 0.0)
    assert np.isclose(comp_events["PE-A"].iloc[0], 1000.0)
    
    # Uncompensated channels pass through unchanged
    assert np.isclose(comp_events["FSC-A"].iloc[0], 50000.0)

def test_parse_spillover():
    from flow_cytometry.analysis.compensation import extract_spill_from_fcs
    
    class MockFCSData:
        def __init__(self):
            self.metadata = {"$SPILLOVER": "2,FITC-A,PE-A,1.0,0.0,0.1,1.0"}
            
    comp = extract_spill_from_fcs(MockFCSData())
    
    assert comp.channel_names == ["FITC-A", "PE-A"]
    assert np.allclose(comp.matrix, [[1.0, 0.0], [0.1, 1.0]])

def test_compensation_to_dict():
    detectors = ["FITC-A", "PE-A"]
    matrix = np.array([[1.0, 0.0], [0.1, 1.0]])
    comp = CompensationMatrix(matrix=matrix, channel_names=detectors)
    
    d = comp.to_dict()
    assert d["channel_names"] == detectors
    assert d["matrix"] == matrix.tolist()
    
    comp2 = CompensationMatrix.from_dict(d)
    assert comp2.channel_names == comp.channel_names
    assert np.allclose(comp2.matrix, comp.matrix)
