import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from flow_cytometry.ui.widgets.group_preview import GroupPreviewPanel, PreviewThumbnail
from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Sample

@pytest.fixture
def flow_state_groups():
    state = FlowState()
    
    # Sample 1
    sample1 = Sample(sample_id="s1", display_name="Sample 1")
    sample1.fcs_data = MagicMock()
    sample1.fcs_data.events = pd.DataFrame({
        "FSC-A": np.random.normal(50000, 10000, 100),
        "SSC-A": np.random.normal(50000, 10000, 100)
    })
    state.experiment.samples["s1"] = sample1
    
    # Sample 2
    sample2 = Sample(sample_id="s2", display_name="Sample 2")
    sample2.fcs_data = MagicMock()
    sample2.fcs_data.events = pd.DataFrame({
        "FSC-A": np.random.normal(50000, 10000, 100),
        "SSC-A": np.random.normal(50000, 10000, 100)
    })
    state.experiment.samples["s2"] = sample2
    
    # Assign groups
    sample1.group_ids = {"g1"}
    sample2.group_ids = {"g1"}
    
    return state

@pytest.mark.ui
def test_group_preview_panel_init(qtbot, flow_state_groups):
    panel = GroupPreviewPanel(flow_state_groups)
    qtbot.addWidget(panel)
    assert panel._state == flow_state_groups
    assert panel._current_sample_id is None

@pytest.mark.ui
def test_preview_thumbnail_init(qtbot, flow_state_groups):
    thumb = PreviewThumbnail("s1", flow_state_groups)
    qtbot.addWidget(thumb)
    assert thumb._sample_id == "s1"
    assert thumb._state == flow_state_groups

def test_render_task_for_preview():
    from flow_cytometry.ui.graph.render_task import RenderTask
    from flow_cytometry.analysis.scaling import AxisScale
    from flow_cytometry.analysis.transforms import TransformType
    
    data = pd.DataFrame({
        "FSC-A": np.random.normal(50000, 10000, 100),
        "SSC-A": np.random.normal(50000, 10000, 100)
    })
    
    scale = AxisScale(TransformType.LINEAR)
    scale.min_val, scale.max_val = 0, 100000
    
    task = RenderTask()
    task.configure(
        data=data,
        x_param="FSC-A",
        y_param="SSC-A",
        x_scale=scale,
        y_scale=scale,
        x_range=(0, 100000),
        y_range=(0, 100000),
        width_px=100,
        height_px=100,
        plot_type="pseudocolor"
    )
    
    # Mock state for AnalysisBase.run
    mock_state = MagicMock()
    
    result = task.run(mock_state)
    
    assert "image_data" in result
    assert isinstance(result["image_data"], bytes)
    assert len(result["image_data"]) > 0
    assert result["width"] == 100
    assert result["height"] == 100
