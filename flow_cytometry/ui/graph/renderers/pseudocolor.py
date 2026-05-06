from __future__ import annotations
from biopro.sdk.utils.logging import get_logger
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.stats import rankdata
from matplotlib import colormaps
from fast_histogram import histogram2d as fast_hist2d

from .base import DisplayStrategy
from biopro.ui.theme import Colors

logger = get_logger(__name__, "flow_cytometry")


class PseudocolorStrategy(DisplayStrategy):
    """Canonical pseudocolor density renderer."""

    def render(self, ax, x, y, **kwargs) -> None:
        """Render density-colored scatter plot using unified robust math."""
        # Fix import path (rendering is in a sibling of ui, not a child)
        from ....analysis.rendering import compute_pseudocolor_points
        from ....analysis.constants import PSEUDOCOLOR_MAX_EVENTS
        
        # Subsample for UI performance if extremely large
        max_events = kwargs.get("max_events", PSEUDOCOLOR_MAX_EVENTS)
        
        # Ensure we use numpy arrays for positional indexing and performance
        x_np = np.asarray(x)
        y_np = np.asarray(y)
        
        if max_events is not None and len(x_np) > max_events:
            idx = np.random.choice(len(x_np), max_events, replace=False)
            x_sub, y_sub = x_np[idx], y_np[idx]
        else:
            x_sub, y_sub = x_np, y_np

        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()
        
        # Use grid_size if provided, otherwise fall back to quality_multiplier
        grid_size = kwargs.get("grid_size")
        if grid_size:
            # Convert grid_size to quality_multiplier (base is 512)
            quality_multiplier = grid_size / 512.0
        else:
            quality_multiplier = kwargs.get("quality_multiplier", 1.0)
        
        x_plot, y_plot, c_plot = compute_pseudocolor_points(
            x_sub, y_sub, (x_lo, x_hi), (y_lo, y_hi),
            quality_multiplier=quality_multiplier,
            nbins_scaling=kwargs.get("nbins_scaling"),
            sigma_scaling=kwargs.get("sigma_scaling"),
            density_threshold=kwargs.get("density_threshold"),
            vibrancy_min=kwargs.get("vibrancy_min"),
            vibrancy_range=kwargs.get("vibrancy_range"),
        )
        
        # Revert to 'o' to maintain the classic thick blue cloud appearance
        # Point size 1.0 for Full, 1.5 for Optimized
        cmap_name = kwargs.get("cmap", kwargs.get("colormap", "jet"))
        alpha = kwargs.get("alpha", 0.6)
        is_full = kwargs.get("quality_multiplier", 1.0) >= 2.0
        point_size = 1.0 if is_full else 1.5
        
        ax.scatter(
            x_plot, y_plot,
            s=kwargs.get("s", point_size),
            c=c_plot,
            cmap=cmap_name,
            vmin=0.0, vmax=1.0,
            alpha=alpha,
            marker='o',
            rasterized=True,
            edgecolors="none",
            zorder=0
        )
