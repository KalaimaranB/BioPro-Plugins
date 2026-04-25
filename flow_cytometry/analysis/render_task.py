"""Analysis task for off-thread plot rendering.

Uses the BioPro TaskScheduler to render high-fidelity plots without blocking the UI.
Returns an RGBA byte buffer that can be loaded into a QImage/QPixmap.
"""

from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, Tuple

from biopro.sdk.core import AnalysisBase, PluginState
from .rendering import compute_pseudocolor_density
from .transforms import apply_transform, TransformType
from .scaling import AxisScale

logger = logging.getLogger(__name__)

class RenderTask(AnalysisBase):
    """Asynchronous plot renderer."""

    def __init__(self, plugin_id: str = "flow_cytometry") -> None:
        super().__init__(plugin_id)
        self.config = {}

    def configure(
        self,
        data: pd.DataFrame,
        x_param: str,
        y_param: str,
        x_scale: AxisScale,
        y_scale: AxisScale,
        x_range: Tuple[float, float],
        y_range: Tuple[float, float],
        width_px: int = 400,
        height_px: int = 400,
        plot_type: str = "pseudocolor"
    ) -> None:
        """Set the rendering parameters."""
        self.config = {
            "data": data,
            "x_param": x_param,
            "y_param": y_param,
            "x_scale": x_scale,
            "y_scale": y_scale,
            "x_range": x_range,
            "y_range": y_range,
            "width": width_px,
            "height": height_px,
            "plot_type": plot_type
        }

    def run(self, state: PluginState) -> dict:
        """Execute the render — called by TaskScheduler."""
        import matplotlib
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        
        c = self.config
        if not c:
            return {"error": "Not configured"}
            
        data = c["data"]
        x_ch, y_ch = c["x_param"], c["y_param"]
        
        if x_ch not in data.columns or y_ch not in data.columns:
            return {"error": f"Missing columns: {x_ch}, {y_ch}"}

        # Apply transforms
        x_raw = data[x_ch].values
        y_raw = data[y_ch].values
        
        # (Transform logic here... simplified for now)
        # In a real implementation, we'd use apply_transform
        
        # Create figure
        dpi = 100
        fig = Figure(figsize=(c["width"]/dpi, c["height"]/dpi), dpi=dpi)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1]) # Full bleed
        ax.set_axis_off()
        
        # Render
        if c["plot_type"] == "pseudocolor":
            # Grid size proportional to resolution for consistent "look"
            gridsize = max(20, min(c["width"], c["height"]) // 4)
            ax.hexbin(x_raw, y_raw, gridsize=gridsize, cmap="turbo", mincnt=1)
        else:
            ax.scatter(x_raw, y_raw, s=1, alpha=0.5)
            
        ax.set_xlim(c["x_range"])
        ax.set_ylim(c["y_range"])
        
        # Draw and export
        canvas.draw()
        rgba_buffer = canvas.buffer_rgba()
        
        return {
            "image_data": bytes(rgba_buffer),
            "width": c["width"],
            "height": c["height"]
        }
