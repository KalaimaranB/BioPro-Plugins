import pytest
from unittest.mock import MagicMock, patch
from flow_cytometry.ui.main_panel import FlowCytometryPanel
from flow_cytometry.analysis.event_bus import Event, EventType

@pytest.fixture
def mock_plugin_host():
    host = MagicMock()
    return host

def test_main_panel_event_bridge_no_nameerror(mock_plugin_host, empty_state):
    """Verify that _bridge_event can handle all EventType members without NameError."""
    # We need to mock the UI setup because it's expensive/complex
    with patch.object(FlowCytometryPanel, '_setup_ui'):
        panel = FlowCytometryPanel(parent=None)
        panel.publish_event = MagicMock()
        panel.push_state = MagicMock()
        
        # Iterate through all event types and try to bridge them
        for etype in EventType:
            event = Event(type=etype, data={"test": "data"}, source="test")
            try:
                panel._bridge_event(event)
            except NameError as e:
                pytest.fail(f"NameError triggered for {etype}: {e}")
            except Exception as e:
                # Other exceptions might occur due to missing state, but NameError is what we're hunting
                pass
