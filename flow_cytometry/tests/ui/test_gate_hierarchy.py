import pytest
import pandas as pd
from unittest.mock import MagicMock
from flow_cytometry.ui.widgets.gate_hierarchy import GateHierarchy
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Sample
from flow_cytometry.analysis.gating import RectangleGate

@pytest.fixture
def flow_state_hierarchy():
    state = FlowState()
    
    # Mock Sample 1
    sample1 = Sample(sample_id="s1", display_name="Sample 1")
    
    # Add a gate
    gate = RectangleGate("FSC-A", "SSC-A", x_min=10, x_max=100, y_min=10, y_max=100)
    gate.gate_id = "g1"
    
    node = sample1.gate_tree.add_child(gate, name="Singlets")
    node.statistics = {"count": 1000, "pct_parent": 50.0, "pct_total": 50.0}
    
    state.experiment.samples["s1"] = sample1
    return state

@pytest.mark.ui
def test_gate_hierarchy_init(qtbot, flow_state_hierarchy):
    widget = GateHierarchy(flow_state_hierarchy)
    qtbot.addWidget(widget)
    assert widget._state == flow_state_hierarchy
    assert widget._active_sample_id is None

@pytest.mark.ui
def test_gate_hierarchy_set_sample(qtbot, flow_state_hierarchy):
    widget = GateHierarchy(flow_state_hierarchy)
    qtbot.addWidget(widget)
    
    widget.set_active_sample("s1")
    assert widget._active_sample_id == "s1"
    
    # Verify tree has items
    # The hierarchy widget in global mode (default) shows the strategy
    # regardless of sample if it's the same tree.
    assert widget._tree.topLevelItemCount() > 0
    item = widget._tree.topLevelItem(0)
    assert "Singlets" in item.text(0)
    assert "1,000" in item.text(1)

@pytest.mark.ui
def test_gate_hierarchy_selection(qtbot, flow_state_hierarchy):
    widget = GateHierarchy(flow_state_hierarchy)
    qtbot.addWidget(widget)
    widget.set_active_sample("s1")
    
    # Get the actual gate ID assigned by the tree
    sample = flow_state_hierarchy.experiment.samples["s1"]
    actual_gate_id = sample.gate_tree.children[0].node_id

    with qtbot.waitSignal(widget.selection_changed, timeout=1000) as blocker:
        item = widget._tree.topLevelItem(0)
        widget._tree.setCurrentItem(item)
    
    assert blocker.args[0] == actual_gate_id
