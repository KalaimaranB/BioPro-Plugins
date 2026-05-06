"""Data layer rendering for FlowCanvas.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
import numpy as np
import pandas as pd
from typing import TYPE_CHECKING, Optional

from ....analysis.transforms import apply_transform, TransformType
from ....analysis.scaling import calculate_auto_range
from ..renderers.factory import RenderStrategyFactory

if TYPE_CHECKING:
    from ..flow_canvas import FlowCanvas

logger = get_logger(__name__, "flow_cytometry")

class DataLayerRenderer:
    """Handles rendering of the expensive data layer (scatter, pseudocolor, etc.).
    """

    def __init__(self, canvas: FlowCanvas) -> None:
        self.canvas = canvas

    def render(self) -> None:
        """Render the expensive scatter/histogram data.
        """
        canvas = self.canvas
        ax = canvas._ax
        logger.info(f"DataLayerRenderer.render START: mode={canvas._display_mode}")
        
        ax.clear()
        ax.set_axis_on()
        ax.set_facecolor(canvas._PLOT_BG if hasattr(canvas, "_PLOT_BG") else "#FFFFFF")
        canvas._gate_patches.clear()
        canvas._edit_handles.clear()
        canvas._gate_artists.clear()

        df = canvas._current_data
        if df is None or df.empty:
            canvas._show_empty()
            return

        # Validate columns exist
        if canvas._x_param not in df.columns:
            canvas._show_error(f"Channel '{canvas._x_param}' not found")
            return

        # Get raw data
        x_raw = df[canvas._x_param].values.astype(np.float64)

        # Histogram/CDF mode only needs X
        from ..flow_canvas import DisplayMode
        if canvas._display_mode in (DisplayMode.HISTOGRAM, DisplayMode.CDF):
            strategy = RenderStrategyFactory.get_strategy(canvas._display_mode.value)
            try:
                strategy.render(ax, x_raw)
                ax.set_xlabel(canvas._x_label, fontsize=9, color="#333333")
                canvas._apply_axis_formatting()
                return
            except Exception as e:
                logger.error(f"1D Strategy rendering failed: {e}")

        if canvas._y_param not in df.columns:
            canvas._show_error(f"Channel '{canvas._y_param}' not found")
            return

        y_raw = df[canvas._y_param].values.astype(np.float64)

        # Apply transforms
        x_kwargs = self._get_transform_kwargs(canvas._x_scale)
        y_kwargs = self._get_transform_kwargs(canvas._y_scale)
        
        x_data = apply_transform(x_raw, canvas._x_scale.transform_type, **x_kwargs)
        y_data = apply_transform(y_raw, canvas._y_scale.transform_type, **y_kwargs)

        # Establish axis limits
        self._setup_limits(ax, x_raw, canvas._x_scale, x_kwargs, "x")
        self._setup_limits(ax, y_raw, canvas._y_scale, y_kwargs, "y")

        # Draw based on mode
        strategy = RenderStrategyFactory.get_strategy(canvas._display_mode.value)
        render_config = canvas._state.view.render_config if canvas._state else None

        # Base kwargs
        render_kwargs = {
            "quality_multiplier": canvas._quality_multiplier,
            "grid_size": int(512 * canvas._quality_multiplier),
            "alpha": 1.0 if canvas._quality_multiplier >= 2.0 else 0.8
        }

        if render_config:
            from ..flow_canvas import DisplayMode
            mode = canvas._display_mode

            if mode == DisplayMode.PSEUDOCOLOR:
                pc = render_config.pseudocolor
                render_kwargs.update({
                    "max_events": pc.max_events if canvas._quality_multiplier < 2.0 else None,
                    "nbins_scaling": pc.population_detail,
                    "sigma_scaling": pc.population_smoothing,
                    "density_threshold": pc.background_suppression,
                    "vibrancy_min": pc.vibrancy_min,
                    "vibrancy_range": pc.vibrancy_range,
                    "colormap": pc.colormap,
                    "cmap": pc.colormap,
                    "point_size": pc.point_size,
                    "s": pc.point_size,
                    "opacity": pc.opacity,
                    "alpha": pc.opacity,
                })
            elif mode == DisplayMode.DOT_PLOT:
                dp = render_config.dot_plot
                render_kwargs.update({
                    "max_events": dp.max_events if canvas._quality_multiplier < 2.0 else None,
                    "dot_color": dp.dot_color,
                    "c": dp.dot_color,
                    "dot_size": dp.dot_size,
                    "s": dp.dot_size,
                    "opacity": dp.opacity,
                    "alpha": dp.opacity,
                })
            elif mode == DisplayMode.HISTOGRAM:
                h = render_config.histogram
                render_kwargs.update({
                    "bar_color": h.bar_color,
                    "color": h.bar_color,
                    "bins": h.bins,
                    "auto_bins": h.auto_bins,
                    "y_axis_mode": h.y_axis_mode,
                    "density": (h.y_axis_mode == "frequency"),
                    "filled": h.filled,
                    "smooth_kde": h.smooth_kde,
                })
            elif mode == DisplayMode.CONTOUR:
                c = render_config.contour
                render_kwargs.update({
                    "num_levels": c.num_levels,
                    "levels": c.num_levels,
                    "smoothing": c.smoothing,
                    "sigma": c.smoothing,
                    "color_mode": c.color_mode,
                    "colormap": c.colormap,
                    "show_filled": c.show_filled,
                    "show_dot_underlay": c.show_dot_underlay,
                })
            elif mode == DisplayMode.DENSITY:
                d = render_config.density
                render_kwargs.update({
                    "colormap": d.colormap,
                    "cmap": d.colormap,
                    "grid_resolution": d.grid_resolution,
                    "opacity": d.opacity,
                    "alpha": d.opacity,
                })
        else:
            render_kwargs["max_events"] = canvas._max_events
        
        try:
            strategy.render(ax, x_data, y_data, **render_kwargs)
        except Exception as e:
            logger.error(f"Strategy rendering failed: {e}", exc_info=True)
            RenderStrategyFactory.get_strategy("Dot Plot").render(ax, x_data, y_data)

        # Labels and styling
        ax.set_xlabel(canvas._x_label, fontsize=9, color="#333333")
        ax.set_ylabel(canvas._y_label, fontsize=9, color="#333333")
        canvas._apply_axis_formatting()
        
        for spine in ax.spines.values():
            spine.set_color('#333333')
            spine.set_linewidth(1.0)
        ax.tick_params(colors='#333333', labelsize=8)

        # Event count annotation
        n = len(x_data)
        ax.annotate(
            f"{n:,} events",
            xy=(0.98, 0.98),
            xycoords="axes fraction",
            ha="right", va="top",
            fontsize=8,
            color="#333333",
            alpha=0.8,
        )

        ax.grid(True, color="#B0B0B0", alpha=0.35, linewidth=0.5)
        canvas._fig.subplots_adjust(left=0.12, bottom=0.12, right=0.95, top=0.95)
        
        canvas.draw()
        logger.info("DataLayerRenderer.render COMPLETE")

    def _get_transform_kwargs(self, scale) -> dict:
        if scale.transform_type == TransformType.BIEXPONENTIAL:
            return {
                "top": scale.logicle_t,
                "width": scale.logicle_w,
                "positive": scale.logicle_m,
                "negative": scale.logicle_a,
            }
        return {}

    def _setup_limits(self, ax, raw_data, scale, kwargs, axis_name: str) -> None:
        setter = ax.set_xlim if axis_name == "x" else ax.set_ylim
        if scale.min_val is not None and scale.max_val is not None:
            lim = apply_transform(
                np.array([scale.min_val, scale.max_val]),
                scale.transform_type, **kwargs,
            )
            setter(lim[0], lim[1])
        else:
            valid_raw = raw_data[np.isfinite(raw_data)]
            if len(valid_raw) > 0:
                raw_min, raw_max = calculate_auto_range(valid_raw, scale.transform_type)
                lim = apply_transform(
                    np.array([raw_min, raw_max]), 
                    scale.transform_type, **kwargs
                )
                setter(lim[0], lim[1])
