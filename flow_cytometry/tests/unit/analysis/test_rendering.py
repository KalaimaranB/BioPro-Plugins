import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from flow_cytometry.analysis.render_task import RenderTask
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType

def test_render_task_execution(sample_data):
    task = RenderTask()
    x_scale = AxisScale(TransformType.LINEAR)
    y_scale = AxisScale(TransformType.LINEAR)
    
    task.configure(
        data=sample_data,
        x_param="FSC-A",
        y_param="SSC-A",
        x_scale=x_scale,
        y_scale=y_scale,
        x_range=(0, 1024),
        y_range=(0, 1024),
        width_px=100,
        height_px=100,
        plot_type="pseudocolor"
    )
    
    state = MagicMock()
    results = task.run(state)
    
    assert "image_data" in results
    assert results["width"] == 100
    assert results["height"] == 100

def test_rendering_math():
    from flow_cytometry.analysis.rendering import compute_1d_histogram, compute_pseudocolor_density
    
    x = np.linspace(0, 100, 50)
    counts, edges = compute_1d_histogram(x, (0, 100), bins=10)
    assert len(counts) == 10
    assert counts.sum() == 50
    
    y = np.linspace(0, 100, 50)
    H, ox, oy = compute_pseudocolor_density(x, y, (0, 100), (0, 100), bins=10)
    assert H.shape == (10, 10)
