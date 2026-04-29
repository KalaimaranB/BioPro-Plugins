import pytest
import sys
from PyQt6.QtWidgets import QApplication

from flow_cytometry.ui.main_panel import FlowCytometryPanel
from flow_cytometry.analysis.state import FlowState

@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app

def test_main_panel_initialization(qapp, qtbot):
    """Smoke test: Verify FlowCytometryPanel can be instantiated without crashing.
    
    This catches AttributeErrors in signal wiring and initialization logic.
    """
    # We don't need a real BioPro environment for this smoke test,
    # just the widget itself.
    try:
        panel = FlowCytometryPanel(plugin_id="flow_smoke_test")
        qtbot.addWidget(panel)
        assert panel is not None
        assert panel.state is not None
        assert hasattr(panel, "_gate_controller")
    except Exception as e:
        pytest.fail(f"FlowCytometryPanel failed to initialize: {e}")

def test_graph_manager_initialization(qapp, qtbot, flow_state):
    """Smoke test: Verify GraphManager and GraphWindow initialization."""
    from flow_cytometry.ui.graph.graph_manager import GraphManager
    try:
        manager = GraphManager(flow_state)
        qtbot.addWidget(manager)
        
        # Test opening a graph
        sample_id = "test_sample_1"
        manager.open_graph_for_sample(sample_id)
        
        assert manager._tabs.count() == 1
        graph = manager._tabs.widget(0)
        assert graph is not None
        assert graph.sample_id == sample_id
    except Exception as e:
        pytest.fail(f"GraphManager failed to open graph: {e}")

def test_group_preview_panel_initialization(qapp, qtbot, flow_state):
    """Smoke test: Verify GroupPreviewPanel can rebuild its grid."""
    from flow_cytometry.ui.widgets.group_preview import GroupPreviewPanel
    try:
        # We need a coordinator for GroupPreview if it's used inside PropertiesPanel,
        # but here we test it standalone.
        panel = GroupPreviewPanel(flow_state)
        qtbot.addWidget(panel)
        
        # Add another sample to ensure there are peers to preview
        from flow_cytometry.analysis.experiment import Sample
        flow_state.experiment.samples["test_sample_2"] = Sample(
            sample_id="test_sample_2",
            display_name="Sample 2",
        )

        # Set context to trigger rebuild
        sample_id = "test_sample_1"
        panel.update_context(sample_id, None)
        
        assert len(panel._thumbnails) > 0
    except Exception as e:
        pytest.fail(f"GroupPreviewPanel failed: {e}")
