import pytest
from flow_cytometry.analysis.state import FlowState
from biopro.sdk.core import PluginState

def test_state_serialization_avoids_recursive_objects(empty_state):
    """Verify that to_dict() handles non-serializable fields like EventBus."""
    data = empty_state.to_dict()
    assert isinstance(data, dict)
    assert "event_bus" not in data
    assert "experiment" in data

def test_state_active_params(empty_state):
    empty_state.active_x_param = "FSC-A"
    empty_state.active_y_param = "SSC-A"
    assert empty_state.active_x_param == "FSC-A"
    assert empty_state.active_y_param == "SSC-A"
