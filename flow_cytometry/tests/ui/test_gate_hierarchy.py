import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.ui

from flow_cytometry.ui.widgets.gate_hierarchy import GateHierarchy
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Sample
from flow_cytometry.analysis.gating import RectangleGate

@pytest.fixture
def flow_state_hierarchy():
    state = FlowState()
    
    # Mock Sample 1
    sample1 = Sample(sample_id="s1", name="Sample 1")
    
    # Add a gate
    gate = RectangleGate("FSC-A", "SSC-A", x_min=10, x_max=100, y_min=10, y_max=100)
    gate.gate_id = "g1"
    
    node = sample1.gate_tree.add_child(gate, name="Singlets")
    node.statistics = {"count": 1000, "pct_parent": 50.0, "pct_total": 50.0}
    
    state.experiment.samples["s1"] = sample1
    return state

@patch('PyQt6.QtWidgets.QTreeWidget')
def test_gate_hierarchy_init(mock_tree, flow_state_hierarchy):
    tree = GateHierarchy(flow_state_hierarchy)
    assert tree._state == flow_state_hierarchy
    assert tree._active_sample_id is None

@patch('PyQt6.QtWidgets.QTreeWidget')
def test_gate_hierarchy_set_sample(mock_tree, flow_state_hierarchy):
    tree = GateHierarchy(flow_state_hierarchy)
    
    # We mock QTreeWidget's methods that get called during clear/add
    tree.clear = MagicMock()
    tree.invisibleRootItem = MagicMock()
    
    tree.set_sample("s1")
    
    assert tree._active_sample_id == "s1"
    assert tree.clear.called
