import pytest
from flow_cytometry.analysis.state import FlowState
from biopro.sdk.core import PluginState
from unittest.mock import MagicMock

def test_state_serialization_avoids_recursive_objects(empty_state):
    """Verify that to_dict() handles non-serializable fields like EventBus."""
    data = empty_state.to_dict()
    assert isinstance(data, dict)
    assert "event_bus" not in data
    assert "data" in data
    assert "view" in data
    assert "experiment" in data["data"]

def test_state_active_params(empty_state):
    empty_state.active_x_param = "FSC-A"
    empty_state.active_y_param = "SSC-A"
    assert empty_state.active_x_param == "FSC-A"
    assert empty_state.active_y_param == "SSC-A"

def test_render_config_serialization(empty_state):
    from flow_cytometry.analysis.config import RenderConfig
    
    custom_config = RenderConfig(max_events=42000, nbins_scaling=3.5)
    empty_state.render_config = custom_config
    
    workflow_dict = empty_state.to_workflow_dict()
    assert "view" in workflow_dict
    assert "render_config" in workflow_dict["view"]
    assert workflow_dict["view"]["render_config"]["max_events"] == 42000
    assert workflow_dict["view"]["render_config"]["nbins_scaling"] == 3.5
    
    # Test round trip
    new_state = type(empty_state)(MagicMock())
    new_state.from_workflow_dict(workflow_dict)
    assert new_state.render_config.max_events == 42000
    assert new_state.render_config.nbins_scaling == 3.5
