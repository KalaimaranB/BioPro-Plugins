import pytest
import pandas as pd
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.gate_controller import GateController
from flow_cytometry.analysis.experiment import Sample
from flow_cytometry.analysis.gating import RectangleGate, QuadrantGate, GateNode

@pytest.fixture
def flow_state(synthetic_events_small):
    state = FlowState()
    sample = Sample(sample_id="test_sample_1", name="Test Sample")
    
    # Mock FCS Data
    class MockFcsData:
        def __init__(self, events):
            self.events = events
            self.parameters = {col: {} for col in events.columns}
            self.metadata = {}
            self.num_events = len(events)
            self.file_path = "test.fcs"
    
    sample.fcs_data = MockFcsData(synthetic_events_small)
    state.experiment.samples[sample.sample_id] = sample
    return state

@pytest.fixture
def gate_controller(flow_state):
    return GateController(flow_state)

def test_add_rectangle_gate(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    
    # Add a gate
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    assert node_id is not None
    sample = flow_state.experiment.samples[sample_id]
    
    # Check tree
    node = sample.gate_tree.find_node_by_id(node_id)
    assert node is not None
    assert node.name == "Singlets"
    assert node.gate == gate_rectangle_singlet
    
    # Check stats were computed
    assert "count" in node.statistics
    assert node.statistics["count"] > 0
    assert node.statistics["pct_parent"] <= 100.0

def test_add_quadrant_gate(gate_controller, flow_state, gate_quadrant_cd4_cd8):
    sample_id = "test_sample_1"
    
    node_id = gate_controller.add_gate(gate_quadrant_cd4_cd8, sample_id)
    
    sample = flow_state.experiment.samples[sample_id]
    quad_node = sample.gate_tree.find_node_by_id(node_id)
    
    assert quad_node is not None
    assert len(quad_node.children) == 4
    
    labels = [n.name for n in quad_node.children]
    assert labels == ["Q1 ++", "Q2 −+", "Q3 −−", "Q4 +−"]

def test_modify_gate(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    sample = flow_state.experiment.samples[sample_id]
    node = sample.gate_tree.find_node_by_id(node_id)
    orig_count = node.statistics["count"]
    
    # Modify gate to be much smaller
    success = gate_controller.modify_gate(
        gate_rectangle_singlet.gate_id, 
        sample_id, 
        x_min=100_000, 
        x_max=110_000,
        y_min=80_000,
        y_max=90_000
    )
    
    assert success is True
    assert gate_rectangle_singlet.x_min == 100_000
    
    # Check stats updated
    new_count = node.statistics["count"]
    assert new_count < orig_count

def test_remove_population(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    success = gate_controller.remove_population(sample_id, node_id)
    assert success is True
    
    sample = flow_state.experiment.samples[sample_id]
    assert sample.gate_tree.find_node_by_id(node_id) is None

def test_rename_population(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    success = gate_controller.rename_population(sample_id, node_id, "New Name")
    assert success is True
    
    sample = flow_state.experiment.samples[sample_id]
    node = sample.gate_tree.find_node_by_id(node_id)
    assert node.name == "New Name"

def test_split_population(gate_controller, flow_state, gate_rectangle_singlet):
    sample_id = "test_sample_1"
    node_id = gate_controller.add_gate(gate_rectangle_singlet, sample_id, name="Singlets")
    
    sibling_id = gate_controller.split_population(sample_id, node_id)
    assert sibling_id is not None
    
    sample = flow_state.experiment.samples[sample_id]
    sibling = sample.gate_tree.find_node_by_id(sibling_id)
    
    assert sibling is not None
    assert sibling.negated is True
    assert sibling.name == "Singlets (Outside)"
