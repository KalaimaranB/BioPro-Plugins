import pytest
from unittest.mock import MagicMock, patch
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.ui.graph.graph_window import GraphWindow
from flow_cytometry.analysis.experiment import Sample
from biopro.sdk.core.events import CentralEventBus
from flow_cytometry.analysis import events
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import QApplication
import sys

@pytest.mark.integration
def test_graph_window_emits_standardized_event_keys(qtbot):
    """Verify that GraphWindow._render_initial emits the correct event payload keys."""
    # Ensure QApplication exists
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Setup state
    state = FlowState()
    from flow_cytometry.analysis.population_service import PopulationService
    from flow_cytometry.analysis.axis_manager import AxisManager
    state.population_service = PopulationService(state)
    state.axis_manager = AxisManager(state)
    
    # Mock a subscriber
    subscriber: MagicMock = MagicMock()
    CentralEventBus.subscribe(events.AXIS_RANGE_CHANGED, subscriber)
    
    # Setup Sample
    sample = Sample(sample_id="s1", display_name="S1")
    state.experiment.samples["s1"] = sample
    
    # Dummy data
    sample.fcs_data = MagicMock()
    sample.fcs_data.events = pd.DataFrame({"FSC-A": [100, 200, 300], "SSC-A": [100, 200, 300]})
    sample.fcs_data.channels = ["FSC-A", "SSC-A"]
    sample.fcs_data.markers = ["", ""]
    sample.fcs_data.file_path = None
    
    # Minimal patches to allow GraphWindow to init without crashing
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
    mock_canvas_cls: MagicMock = MagicMock(spec=QWidget)
    mock_canvas_cls.return_value.gate_created = MagicMock()
    
    with patch('flow_cytometry.ui.graph.graph_window.FlowCanvas', return_value=mock_canvas_cls.return_value), \
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
        win._x_combo: MagicMock = MagicMock()
        win._x_combo.currentText.return_value = "FSC-A"
        win._x_combo.currentData.return_value = "FSC-A"
        win._y_combo: MagicMock = MagicMock()
        win._y_combo.currentText.return_value = "SSC-A"
        win._y_combo.currentData.return_value = "SSC-A"
        
        # Trigger the code path
        win._render_initial()
        
        # Process events to allow CentralEventBus to dispatch
        QApplication.processEvents()
        
        # Verify event was published
        assert subscriber.called, "AXIS_RANGE_CHANGED event was not published"
        
        # Check the published event data
        data = subscriber.call_args[0][0]
        
        # VERIFY STANDARDIZED KEYS
        assert "x_param" in data
        assert "y_param" in data
        assert "x_scale" in data
        assert "y_scale" in data
        assert "sample_id" in data
        
        assert data["x_param"] == "FSC-A"
        assert data["y_param"] == "SSC-A"
        assert data["sample_id"] == "s1"
        
    # Cleanup
    CentralEventBus.unsubscribe(events.AXIS_RANGE_CHANGED, subscriber)
