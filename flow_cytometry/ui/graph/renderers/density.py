"""Renderer strategy for 2D Histogram/Density heatmaps."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from biopro.ui.theme import Colors


class DensityStrategy(DisplayStrategy):
    """2D Histogram/Density heatmap renderer using hexbin-style rendering."""

    def render(self, ax, x, y, **kwargs) -> None:
        """Render density as a 2D histogram heatmap."""
        valid = np.isfinite(x) & np.isfinite(y)
        x_vis, y_vis = x[valid], y[valid]

        if len(x_vis) < 100:
            ax.scatter(x_vis, y_vis, s=2, alpha=0.3)
            return

        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()

        # Use grid_size if provided, otherwise default to 100 bins
        bins = kwargs.get("grid_size", 100) // 5  # Scale down for hexbin-style
        
        # Create 2D histogram
        hist, xedges, yedges = np.histogram2d(
            x_vis, y_vis, 
            bins=bins, 
            range=[[x_lo, x_hi], [y_lo, y_hi]]
        )

        # Render as imshow with a colormap
        extent = [x_lo, x_hi, y_lo, y_hi]
        cmap = kwargs.get("cmap", "jet")
        alpha = kwargs.get("alpha", 0.8)
        
        # Use pcolormesh for better quality
        X, Y = np.meshgrid(
            (xedges[:-1] + xedges[1:]) / 2,
            (yedges[:-1] + yedges[1:]) / 2
        )
        
        # Transpose hist for correct orientation
        ax.pcolormesh(X, Y, hist.T, cmap=cmap, alpha=alpha, shading='auto')