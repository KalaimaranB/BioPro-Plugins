"""Tests for EventBus integration specifically for the flow cytometry module."""

import unittest
from unittest.mock import MagicMock
import sys
import os

# Add plugin root to sys.path so 'flow_cytometry' package is discoverable
# Path: plugins/flow_cytometry/tests/integration/test_event_bus.py -> plugins/
plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if plugin_root not in sys.path:
    sys.path.insert(0, plugin_root)

# Mock biopro SDK before imports
from unittest.mock import MagicMock
import sys
import types

def mock_pkg(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

# Create biopro mocks
biopro = mock_pkg("biopro")
biopro.sdk = mock_pkg("biopro.sdk")
biopro.sdk.core = mock_pkg("biopro.sdk.core")
class MockPluginState: pass
biopro.sdk.core.PluginState = MockPluginState
biopro.sdk.core.PluginBase = MagicMock
biopro.ui = mock_pkg("biopro.ui")
biopro.ui.theme = MagicMock()
biopro.shared = mock_pkg("biopro.shared")
biopro.shared.ui = mock_pkg("biopro.shared.ui")
biopro.shared.ui.ui_components = MagicMock()
biopro.core = mock_pkg("biopro.core")
biopro.core.task_scheduler = MagicMock()

# Mock heavy dependencies
mock_pkg("pandas")
np = mock_pkg("numpy")
np.inf = float('inf')
np.nan = float('nan')
np.array = MagicMock
np.float64 = float

mock_pkg("matplotlib")
mock_pkg("matplotlib.figure")
mock_pkg("matplotlib.backends")
mock_pkg("matplotlib.backends.backend_qtagg")
mock_pkg("matplotlib.patches")
mock_pkg("matplotlib.lines")
mock_pkg("fast_histogram")
mock_pkg("scipy")
mock_pkg("scipy.ndimage")
mock_pkg("scipy.stats")

# Mock PyQt6
qt = mock_pkg("PyQt6")
qt_core = mock_pkg("PyQt6.QtCore")
qt_core.QObject = MagicMock
qt_core.pyqtSignal = MagicMock
qt_core.pyqtSlot = MagicMock
qt_core.Qt = MagicMock()
qt_core.QTimer = MagicMock
qt_widgets = mock_pkg("PyQt6.QtWidgets")
qt_widgets.QWidget = MagicMock
qt_widgets.QVBoxLayout = MagicMock
qt_widgets.QHBoxLayout = MagicMock
qt_widgets.QLabel = MagicMock
qt_gui = mock_pkg("PyQt6.QtGui")

from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.event_bus import EventType, Event
from flow_cytometry.analysis.gate_controller import GateController
from flow_cytometry.analysis.gating import RectangleGate

class TestEventBusIntegration(unittest.TestCase):
    def setUp(self):
        self.state = FlowState()
        self.bus = self.state.event_bus
        self.mock_handler = MagicMock()

    def test_render_quality_event(self):
        """Test that changing render_quality publishes an event."""
        self.bus.subscribe(EventType.RENDER_MODE_CHANGED, self.mock_handler)
        
        # Change state
        self.state.render_quality = "transparent"
        
        # Verify event
        self.mock_handler.assert_called_once()
        event = self.mock_handler.call_args[0][0]
        self.assertEqual(event.type, EventType.RENDER_MODE_CHANGED)
        self.assertEqual(event.data["mode"], "transparent")

    def test_gate_created_event(self):
        """Test that adding a gate via GateController publishes an event."""
        self.bus.subscribe(EventType.GATE_CREATED, self.mock_handler)
        
        from flow_cytometry.analysis.experiment import Sample
        from flow_cytometry.analysis.gating import GateNode

        controller = GateController(self.state)
        
        # Use real objects
        sample_id = "sample_1"
        sample = Sample(sample_id=sample_id, display_name="Sample 1")
        self.state.experiment.samples[sample_id] = sample
        
        # Add a gate
        gate = RectangleGate(
            "FSC-A", "SSC-A", 
            x_min=1000, x_max=5000, y_min=1000, y_max=5000
        )
        controller.add_gate(gate, sample_id, name="Test Gate", parent_node_id=sample.gate_tree.node_id)
        
        # Verify event
        self.assertTrue(self.mock_handler.called)
        event = self.mock_handler.call_args[0][0]
        self.assertEqual(event.type, EventType.GATE_CREATED)
        self.assertEqual(event.data["sample_id"], sample_id)
        self.assertEqual(event.data["name"], "Test Gate")

    def test_gate_renamed_event(self):
        """Test that renaming a gate publishes an event."""
        self.bus.subscribe(EventType.GATE_RENAMED, self.mock_handler)
        
        from flow_cytometry.analysis.experiment import Sample
        from flow_cytometry.analysis.gating import GateNode

        controller = GateController(self.state)
        
        # Use real objects
        sample_id = "sample_1"
        sample = Sample(sample_id=sample_id, display_name="Sample 1")
        
        gate = RectangleGate("FSC-A", "SSC-A")
        node = sample.gate_tree.add_child(gate, name="Old Name")
        
        self.state.experiment.samples[sample_id] = sample
        
        # Rename gate
        controller.rename_population(sample_id, node.node_id, "New Name")
        
        # Verify event
        self.mock_handler.assert_called_once()
        event = self.mock_handler.call_args[0][0]
        self.assertEqual(event.type, EventType.GATE_RENAMED)
        self.assertEqual(event.data["new_name"], "New Name")

    def test_ui_subscription(self):
        """Test that UI components subscribe to events."""
        from flow_cytometry.ui.graph.graph_window import GraphWindow
        from flow_cytometry.ui.graph.graph_manager import GraphManager
        
        # Mock UI setup
        GraphWindow._setup_ui = MagicMock()
        GraphManager._setup_ui = MagicMock()
        
        window = GraphWindow(self.state, "sample_1")
        manager = GraphManager(self.state)
        
        window._on_bus_event = MagicMock()
        manager._on_bus_event = MagicMock()
        
        self.bus.publish(Event(EventType.GATE_RENAMED, data={"sample_id": "sample_1"}))
        
        self.assertTrue(window._on_bus_event.called)
        self.assertTrue(manager._on_bus_event.called)

if __name__ == "__main__":
    unittest.main()
