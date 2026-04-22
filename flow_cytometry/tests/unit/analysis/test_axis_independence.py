import pytest
import numpy as np
import pandas as pd

from flow_cytometry.analysis.scaling import AxisScale, calculate_auto_range
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.state import FlowState
from biopro.sdk.core import PluginState

@pytest.mark.unit
class TestAxisIndependence:

    def test_x_and_y_auto_ranges_are_independent(self):
        """Separate channels must produce different auto-ranges, especially for SSC vs FSC."""
        # Simulate real FCS data: FSC is wide and high, SSC is narrow and lower.
        np.random.seed(42)
        fsc_data = np.random.uniform(50000, 250000, 20000)
        ssc_data = np.random.uniform(5000, 50000, 20000)

        fsc_min, fsc_max = calculate_auto_range(fsc_data, TransformType.BIEXPONENTIAL)
        ssc_min, ssc_max = calculate_auto_range(ssc_data, TransformType.BIEXPONENTIAL)

        assert fsc_min != ssc_min
        assert fsc_min > 40000  # Stays positive and high
        assert ssc_min < 5000   # Lower than FSC

    def test_channel_scales_store_independent_objects(self):
        """Objects stored in channel_scales must be copies so they don't share references."""
        state = FlowState(PluginState())
        
        x_scale = AxisScale(TransformType.LINEAR)
        y_scale = AxisScale(TransformType.BIEXPONENTIAL)
        
        # Simulate _render_initial saving to state
        state.channel_scales["FSC-A"] = x_scale.copy()
        state.channel_scales["SSC-A"] = y_scale.copy()
        
        # Mutate the original
        x_scale.min_val = 123.0
        
        # Stored version should be unchanged
        assert state.channel_scales["FSC-A"].min_val is None

    def test_switching_channels_recomputes_range_from_new_data(self):
        """Simulate the UI flow of switching a channel and ensure the range reflects the new data."""
        # Initial state: Y was SSC-A
        y_scale_active = AxisScale(TransformType.LINEAR)
        y_scale_active.min_val = 0.0
        y_scale_active.max_val = 262144.0
        
        # Now switch Y to BL1-H (fluorescence)
        bl1_data = np.concatenate([
            np.random.uniform(-5000, 200000, 9500),
            np.random.uniform(-10000, -5000, 500)
        ])
        
        # Simulate the fix in _render_initial: always recompute
        vmin, vmax = calculate_auto_range(bl1_data, y_scale_active.transform_type)
        y_scale_active.min_val = float(vmin)
        y_scale_active.max_val = float(vmax)
        
        assert y_scale_active.min_val < 0.0  # Successfully adopted the BL1-H negative floor
