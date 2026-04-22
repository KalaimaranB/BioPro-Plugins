import pytest
import numpy as np

from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType

@pytest.mark.ui
class TestThumbnailRendering:

    def test_render_preview_to_buffer_returns_bytes(self, sample_c_events):
        """Ensure the off-thread rendering function returns a valid image buffer."""
        from flow_cytometry.ui.widgets.group_preview import render_preview_to_buffer
        
        buf = render_preview_to_buffer(
            sample_id="test_id", 
            events=sample_c_events, 
            x_param="FSC-A", 
            y_param="SSC-A",
            x_scale=AxisScale(TransformType.LINEAR), 
            y_scale=AxisScale(TransformType.LINEAR),
            gate=None, 
            limit=20000, 
            width_px=160, 
            height_px=160
        )
        assert isinstance(buf, bytes)
        assert len(buf) == 160 * 160 * 4  # RGBA

    def test_thumbnail_not_blank_for_real_fcs_data(self, sample_c_events):
        """The returned buffer must not be all-white (data must be visible)."""
        from flow_cytometry.ui.widgets.group_preview import render_preview_to_buffer
        
        buf = render_preview_to_buffer(
            sample_id="test_id", 
            events=sample_c_events, 
            x_param="FSC-A", 
            y_param="SSC-A",
            x_scale=AxisScale(TransformType.LINEAR), 
            y_scale=AxisScale(TransformType.LINEAR),
            gate=None, 
            limit=20000, 
            width_px=160, 
            height_px=160
        )
        
        arr = np.frombuffer(buf, dtype=np.uint8).reshape((160, 160, 4))
        # Check that not all RGB values are 255 (white)
        # Assuming background is white or transparent, and data points have some color
        # In our theme, background might be dark, but let's just check it's not a single solid color
        unique_colors = len(np.unique(arr.reshape(-1, 4), axis=0))
        assert unique_colors > 1, "Thumbnail must not be a solid blank square"

    def test_thumbnail_biex_different_from_linear(self, sample_c_events):
        """Biex and linear renders of same data must produce different images."""
        from flow_cytometry.ui.widgets.group_preview import render_preview_to_buffer
        
        buf_lin = render_preview_to_buffer(
            sample_id="test_id", 
            events=sample_c_events, 
            x_param="FSC-A", 
            y_param="SSC-A",
            x_scale=AxisScale(TransformType.LINEAR), 
            y_scale=AxisScale(TransformType.LINEAR),
            gate=None, limit=20000, width_px=160, height_px=160
        )
        
        buf_biex = render_preview_to_buffer(
            sample_id="test_id", 
            events=sample_c_events, 
            x_param="FSC-A", 
            y_param="SSC-A",
            x_scale=AxisScale(TransformType.BIEXPONENTIAL), 
            y_scale=AxisScale(TransformType.BIEXPONENTIAL),
            gate=None, limit=20000, width_px=160, height_px=160
        )
        
        assert buf_lin != buf_biex, "Biexponential render should look different from linear"
