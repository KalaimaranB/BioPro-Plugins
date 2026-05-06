"""Analysis task for off-thread plot rendering.

Uses the BioPro TaskScheduler to render high-fidelity plots without blocking the UI.
Returns an RGBA byte buffer that can be loaded into a QImage/QPixmap.
"""

from __future__ import annotations
from biopro.sdk.utils.logging import get_logger
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, Tuple, List

from biopro.sdk.core import AnalysisBase, PluginState
from ...analysis.transforms import apply_transform, TransformType
from ...analysis.scaling import AxisScale
from ...analysis.rendering import compute_pseudocolor_points
from biopro.ui.theme import Colors

logger = get_logger(__name__, "flow_cytometry")

from ...analysis.constants import DEFAULT_DENSITY_FACTOR

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
        plot_type: str = "pseudocolor",
        max_events: Optional[int] = 100000,
        quality_multiplier: float = 1.0,
        gates: List[Any] = None,
        selected_gate_id: Optional[str] = None,
        colormap: str = "jet",
        s: Optional[float] = None,
        render_config: Optional[dict] = None
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
            "plot_type": plot_type,
            "max_events": max_events,
            "quality_multiplier": quality_multiplier,
            "gates": gates or [],
            "selected_gate_id": selected_gate_id,
            "colormap": colormap,
            "s": s,
            "render_config": render_config or {}
        }

    def run(self, state: PluginState) -> dict:
        """Execute the render — called by TaskScheduler."""
        import matplotlib
        matplotlib.use('Agg')
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib import colormaps
        
        c = self.config
        if not c:
            return {"error": "Not configured"}
            
        data = c["data"]
        x_ch, y_ch = c["x_param"], c["y_param"]
        
        if x_ch not in data.columns or y_ch not in data.columns:
            return {"error": f"Missing columns: {x_ch}, {y_ch}"}

        # 1. Use the same max_events logic as the main plot for perfect parity
        thumb_max = c.get("max_events", 100000)
        if thumb_max is None:
            thumb_max = len(data)
            
        if len(data) > thumb_max:
            data = data.sample(n=thumb_max, random_state=42)

        # 2. Transform raw data to display coordinates
        def _get_xform_params(scale):
            from ...analysis._utils import BiexponentialParameters
            return BiexponentialParameters(scale).to_dict() if scale.transform_type == TransformType.BIEXPONENTIAL else {}

        x_vis = apply_transform(data[x_ch].values.astype(np.float64), c["x_scale"].transform_type, **_get_xform_params(c["x_scale"]))
        y_vis = apply_transform(data[y_ch].values.astype(np.float64), c["y_scale"].transform_type, **_get_xform_params(c["y_scale"]))
        
        # 3. Transform limits to display coordinates
        xlim = apply_transform(np.asarray(c["x_range"]), c["x_scale"].transform_type, **_get_xform_params(c["x_scale"]))
        ylim = apply_transform(np.asarray(c["y_range"]), c["y_scale"].transform_type, **_get_xform_params(c["y_scale"]))

        # 4. Create figure
        dpi = 150
        fig = Figure(figsize=(c["width"]/dpi, c["height"]/dpi), dpi=dpi)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        fig.patch.set_facecolor('#FFFFFF')
        ax.set_facecolor('#FFFFFF')
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

        # 5. Render data layer using the EXACT same strategy as the main UI
        from .renderers.factory import RenderStrategyFactory
        
        # Map plot_type string to strategy name (e.g., "pseudocolor" -> "Pseudocolor")
        strategy_name = "Pseudocolor" if c["plot_type"] == "pseudocolor" else "Dot Plot"
        strategy = RenderStrategyFactory.get_strategy(strategy_name)
        
        # Extract render_config values if available
        rc = c.get("render_config", {})
        
        # Call the strategy with the same parameters as the main plot
        # Note: we pass quality_multiplier from config for parity
        strategy.render(
            ax, x_vis, y_vis, 
            max_events=thumb_max,
            quality_multiplier=c.get("quality_multiplier", 1.0),
            grid_size=int(512 * c.get("quality_multiplier", 1.0)),
            cmap=c["colormap"],
            s=c.get("s"),
            nbins_scaling=rc.get("nbins_scaling"),
            sigma_scaling=rc.get("sigma_scaling"),
            density_threshold=rc.get("density_threshold"),
            vibrancy_min=rc.get("vibrancy_min"),
            vibrancy_range=rc.get("vibrancy_range")
        )

        # 6. Render gate overlays (Identical to main FlowCanvas)
        if c.get("gates"):
            from .flow_services import CoordinateMapper, GateOverlayRenderer
            mapper = CoordinateMapper(c["x_scale"], c["y_scale"])
            # Thinner lines for subplots (1.2 instead of 2.5)
            renderer = GateOverlayRenderer(mapper, linewidth=1.2)
            
            for gate in c["gates"]:
                # Only draw if it matches current axes
                if gate.x_param == x_ch and gate.y_param == y_ch:
                    is_selected = (gate.gate_id == c.get("selected_gate_id"))
                    renderer.render_gate(ax, gate, is_selected=is_selected)
            
        canvas.draw()
        rgba_buffer = canvas.buffer_rgba()
        
        return {
            "image_data": bytes(rgba_buffer),
            "width": c["width"],
            "height": c["height"]
        }
