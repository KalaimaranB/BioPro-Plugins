import pytest
from unittest.mock import MagicMock, patch
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.event_bus import Event, EventType
from flow_cytometry.ui.graph.graph_window import GraphWindow
from flow_cytometry.analysis.experiment import Sample
import pandas as pd
import numpy as np

@pytest.mark.integration
def test_graph_window_emits_standardized_event_keys(qtbot):
    """Verify that GraphWindow._render_initial emits the correct event payload keys."""
    # Setup state
    state = FlowState()
    
    # Mock a subscriber
    subscriber = MagicMock()
    state.event_bus.subscribe(EventType.AXIS_RANGE_CHANGED, subscriber)
    
    # Setup Sample
    sample = Sample(sample_id="s1", display_name="S1")
    state.experiment.samples["s1"] = sample
    
    # Dummy data
    sample.cache = {"events": pd.DataFrame({"FSC-A": [100, 200, 300], "SSC-A": [100, 200, 300]})}
    
    # Minimal patches to allow GraphWindow to init without crashing
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
    with patch('flow_cytometry.ui.graph.graph_window.FlowCanvas', spec=QWidget), \
         patch('PyQt6.QtWidgets.QVBoxLayout.addWidget'), \
         patch('PyQt6.QtWidgets.QHBoxLayout.addWidget'), \
         patch('PyQt6.QtWidgets.QVBoxLayout.addLayout'), \
         patch('PyQt6.QtWidgets.QHBoxLayout.addLayout'), \
         patch('PyQt6.QtWidgets.QVBoxLayout.addStretch'), \
         patch('PyQt6.QtWidgets.QHBoxLayout.addStretch'), \
         patch('PyQt6.QtWidgets.QVBoxLayout.addSpacing'), \
         patch('PyQt6.QtWidgets.QHBoxLayout.addSpacing'):
        
        win = GraphWindow(state, "s1")
        
        # Manually set the channels to match our dummy data
        win._x_combo = MagicMock()
        win._x_combo.currentText.return_value = "FSC-A"
        win._x_combo.currentData.return_value = "FSC-A"
        win._y_combo = MagicMock()
        win._y_combo.currentText.return_value = "SSC-A"
        win._y_combo.currentData.return_value = "SSC-A"
        
        # Trigger the code path
        win._render_initial()
        
        # Verify event was published
        assert subscriber.called, "AXIS_RANGE_CHANGED event was not published"
        
        # Check the published event
        event = subscriber.call_args[0][0]
        assert event.type == EventType.AXIS_RANGE_CHANGED
        
        # VERIFY STANDARDIZED KEYS (The Fix)
        assert "x_param" in event.data, "Missing 'x_param' in event data"
        assert "y_param" in event.data, "Missing 'y_param' in event data"
        assert "x_scale" in event.data, "Missing 'x_scale' in event data"
        assert "y_scale" in event.data, "Missing 'y_scale' in event data"
        assert "sample_id" in event.data, "Missing 'sample_id' in event data"
        
        assert event.data["x_param"] == "FSC-A"
        assert event.data["y_param"] == "SSC-A"
        assert event.data["sample_id"] == "s1"
