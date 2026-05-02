"""Renderer strategy for 2D Histogram/Density heatmaps."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from biopro.ui.theme import Colors


class DensityStrategy(DisplayStrategy):
    """2D Histogram/Density heatmap renderer."""

    def render(self, ax, x, y, **kwargs) -> None:
        """Render density as a 2D histogram heatmap."""
        valid = np.isfinite(x) & np.isfinite(y)
        x_vis, y_vis = x[valid], y[valid]

        if len(x_vis) < 100:
            ax.scatter(x_vis, y_vis, s=2, alpha=0.3)
            return

        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()

        # Grid resolution: use grid_resolution if provided, else fall back to grid_size
        grid_res = kwargs.get("grid_resolution", None)
        if grid_res is not None:
            bins = int(grid_res)
        else:
            bins = kwargs.get("grid_size", 500) // 5
        bins = max(10, bins)

        hist, xedges, yedges = np.histogram2d(
            x_vis, y_vis,
            bins=bins,
            range=[[x_lo, x_hi], [y_lo, y_hi]]
        )

        cmap = kwargs.get("cmap", kwargs.get("colormap", "jet"))
        alpha = kwargs.get("alpha", kwargs.get("opacity", 0.8))

        X, Y = np.meshgrid(
            (xedges[:-1] + xedges[1:]) / 2,
            (yedges[:-1] + yedges[1:]) / 2
        )

        ax.pcolormesh(X, Y, hist.T, cmap=cmap, alpha=alpha, shading="auto")