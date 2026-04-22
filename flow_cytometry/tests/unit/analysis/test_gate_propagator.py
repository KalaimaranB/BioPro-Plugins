import pytest
import pandas as pd
import numpy as np

from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.gate_controller import GateController
from flow_cytometry.analysis.gate_propagator import GatePropagator
from flow_cytometry.analysis.experiment import Sample, Group

@pytest.fixture
def flow_state_multi(synthetic_events_small, synthetic_events_medium):
    state = FlowState()
    
    # Mock FCS Data
    class MockFcsData:
        def __init__(self, events):
            self.events = events
            self.parameters = {col: {} for col in events.columns}
            self.metadata = {}
            self.num_events = len(events)
            self.file_path = "test.fcs"
            
    # Add two samples
    sample1 = Sample(sample_id="sample_1", name="Sample 1")
    sample1.fcs_data = MockFcsData(synthetic_events_small)
    state.experiment.samples["sample_1"] = sample1
    
    sample2 = Sample(sample_id="sample_2", name="Sample 2")
    sample2.fcs_data = MockFcsData(synthetic_events_medium)
    state.experiment.samples["sample_2"] = sample2
    
    # Add them to a group
    group = Group(group_id="group_1", name="All Samples", sample_ids=["sample_1", "sample_2"])
    state.experiment.groups["group_1"] = group
    
    return state

@pytest.fixture
def gate_controller(flow_state_multi):
    return GateController(flow_state_multi)

@pytest.fixture
def gate_propagator(flow_state_multi, gate_controller):
    propagator = GatePropagator(flow_state_multi, gate_controller)
    propagator.strategy = "global"  # Auto-propagate
    return propagator

def test_propagate_new_gate(gate_controller, gate_propagator, flow_state_multi, gate_rectangle_singlet):
    # Action: add gate to sample 1
    # Note: GatePropagator listens to EventBus in reality, but here we manually call propagate
    gate_controller.add_gate(gate_rectangle_singlet, "sample_1", name="Singlets")
    gate_propagator.propagate(gate_rectangle_singlet.gate_id, "sample_1")
    
    # Assert: sample 2 got the gate
    sample2 = flow_state_multi.experiment.samples["sample_2"]
    nodes = sample2.gate_tree.find_nodes_by_gate(gate_rectangle_singlet.gate_id)
    assert len(nodes) == 0  # Should be cloned, not same ID usually?
    
    # Actually, gate_controller.copy_gates_to_group uses deepcopy but forces a NEW gate_id
    # so we find by name instead.
    found = False
    for child in sample2.gate_tree.children:
        if child.name == "Singlets":
            found = True
            break
    assert found is True

def test_adaptive_gating(gate_controller, flow_state_multi, gate_rectangle_singlet):
    # Set gate to adaptive
    gate_rectangle_singlet.adaptive = True
    gate_controller.add_gate(gate_rectangle_singlet, "sample_1", name="Singlets")
    
    # Just verify adapt_all doesn't crash on standard pandas DataFrame
    sample1 = flow_state_multi.experiment.samples["sample_1"]
    sample1.gate_tree.adapt_all(sample1.fcs_data.events)
