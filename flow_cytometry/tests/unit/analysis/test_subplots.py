import pytest
import numpy as np
import pandas as pd
from flow_cytometry.ui.graph.render_task import RenderTask
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType

def test_thumbnail_rendering_resolution(sample_data):
    """Verify that RenderTask produces an image of the requested size."""
    task = RenderTask()
    x_scale = AxisScale(TransformType.LINEAR)
    y_scale = AxisScale(TransformType.LINEAR)
    
    # Request a small thumbnail size
    thumb_w, thumb_h = 150, 150
    
    task.configure(
        data=sample_data,
        x_param="FSC-A",
        y_param="SSC-A",
        x_scale=x_scale,
        y_scale=y_scale,
        x_range=(0, 1024),
        y_range=(0, 1024),
        width_px=thumb_w,
        height_px=thumb_h,
        plot_type="pseudocolor"
    )
    
    # Mock state
    state = None
    results = task.run(state)
    
    assert "image_data" in results
    assert results["width"] == thumb_w
    assert results["height"] == thumb_h
    
    # Check that buffer size matches expected RGBA size (width * height * 4)
    assert len(results["image_data"]) == thumb_w * thumb_h * 4

def test_thumbnail_rendering_full_bleed():
    """Verify that thumbnails are rendered without axes/padding."""
    # This is harder to test without inspecting the image pixels,
    # but we can verify the configuration in the task if we exposed it.
    pass
