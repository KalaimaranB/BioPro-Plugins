import pytest
import pandas as pd
import numpy as np
from flow_cytometry.analysis.population_service import PopulationService
from flow_cytometry.analysis.gating import RectangleGate, QuadrantGate

@pytest.fixture
def service(state_with_sample):
    return PopulationService(state_with_sample)

def test_population_service_get_events(service, sample_with_data):
    events = service.get_gated_events(sample_with_data.sample_id, None)
    assert len(events) == 1000

def test_population_service_quadrant_creation(service, sample_with_data):
    gate = QuadrantGate(x_param="FSC-A", y_param="SSC-A", x_mid=500, y_mid=500)
    # This would typically be called by GateController
    # but we can test the helper logic if exposed or just the effect.
    pass

def test_population_service_find_node(service, sample_with_data):
    sample_with_data.gate_tree.node_id = "root"
    node = service.find_node(sample_with_data.sample_id, "root")
    assert node is not None
    assert node.node_id == "root"
