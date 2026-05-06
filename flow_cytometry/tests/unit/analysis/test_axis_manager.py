import pytest
import numpy as np
from flow_cytometry.analysis.axis_manager import AxisManager
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType

@pytest.fixture
def manager(empty_state):
    return AxisManager(empty_state)

def test_axis_manager_get_scale(manager):
    scale = manager.get_scale("FSC-A")
    assert isinstance(scale, AxisScale)
    assert scale.transform_type == TransformType.LINEAR

def test_axis_manager_calculate_range(manager):
    data = np.array([0, 50, 100, 1000])
    # Default range computation
    low, high = manager.calculate_range(data, "FSC-A")
    assert low == 0
    assert high >= 1000

def test_axis_manager_sync_scales(manager):
    scale = manager.get_scale("FSC-A")
    scale.min_val = 100
    scale.max_val = 500
    
    # Another call should return the same object/state
    scale2 = manager.get_scale("FSC-A")
    assert scale2.min_val == 100
    assert scale2.max_val == 500

def test_axis_manager_smart_default(manager):
    # Retrieve a non-existent channel scale with a specified default_transform
    scale = manager.get_scale("SSC-A", default_transform=TransformType.BIEXPONENTIAL)
    assert scale.transform_type == TransformType.BIEXPONENTIAL
    
    # Retrieve an already-existing channel scale with a different default_transform,
    # it should NOT overwrite the existing transform_type
    scale_existing = manager.get_scale("SSC-A", default_transform=TransformType.LOG)
    assert scale_existing.transform_type == TransformType.BIEXPONENTIAL
