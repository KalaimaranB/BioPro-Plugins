import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.ui

from flow_cytometry.ui.widgets.group_preview import GroupPreviewPanel, PreviewThumbnail
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.event_bus import Event, EventType
from flow_cytometry.analysis.experiment import Sample, Group

@pytest.fixture
def flow_state_groups():
    state = FlowState()
    
    # Mock Sample 1
    sample1 = Sample(sample_id="s1", name="Sample 1")
    class MockFcsData:
        def __init__(self):
            self.file_path = "s1.fcs"
    sample1.fcs_data = MockFcsData()
    state.experiment.samples["s1"] = sample1
    
    # Mock Sample 2
    sample2 = Sample(sample_id="s2", name="Sample 2")
    sample2.fcs_data = MockFcsData()
    state.experiment.samples["s2"] = sample2
    
    # Create group
    group = Group(group_id="g1", name="Test Group", sample_ids=["s1", "s2"])
    state.experiment.groups["g1"] = group
    
    return state

@patch('PyQt6.QtWidgets.QWidget')
@patch('PyQt6.QtWidgets.QScrollArea')
@patch('flow_cytometry.ui.widgets.group_preview.QThreadPool.globalInstance')
def test_group_preview_panel_init(mock_pool, mock_scroll, mock_widget, flow_state_groups):
    panel = GroupPreviewPanel(flow_state_groups)
    assert panel._state == flow_state_groups
    assert panel._active_group_id is None

@patch('PyQt6.QtWidgets.QWidget')
@patch('flow_cytometry.ui.widgets.group_preview.QThreadPool.globalInstance')
def test_preview_thumbnail_init(mock_pool, mock_widget, flow_state_groups):
    sample = flow_state_groups.experiment.samples["s1"]
    thumb = PreviewThumbnail(sample, flow_state_groups)
    
    assert thumb._sample == sample
    assert thumb._state == flow_state_groups
    assert thumb._current_gate_id is None

def test_render_preview_to_buffer():
    from flow_cytometry.ui.widgets.group_preview import render_preview_to_buffer
    from flow_cytometry.ui.graph.flow_services import CoordinateMapper
    from flow_cytometry.analysis.scaling import AxisScale
    from flow_cytometry.analysis.transforms import TransformType
    from flow_cytometry.analysis.gating import RectangleGate
    import pandas as pd
    import numpy as np
    
    data = pd.DataFrame({
        "FSC-A": np.random.normal(50000, 10000, 100),
        "SSC-A": np.random.normal(50000, 10000, 100)
    })
    
    scale = AxisScale(TransformType.LINEAR)
    mapper = CoordinateMapper(scale, scale)
    
    # Just verify it returns bytes without crashing
    buf = render_preview_to_buffer(
        data=data,
        x_param="FSC-A",
        y_param="SSC-A",
        x_scale=scale,
        y_scale=scale,
        mapper=mapper,
        display_mode="pseudocolor",
        active_gates=[],
        preview_gate=None,
        width=100,
        height=100,
        dpi=50
    )
    
    assert isinstance(buf, bytes)
    assert len(buf) > 0
