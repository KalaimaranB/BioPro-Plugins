"""Renderer strategy for 2D Contour plots."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from scipy.ndimage import gaussian_filter


class ContourStrategy(DisplayStrategy):
    """2D Contour plot renderer."""

    def render(self, ax, x, y, **kwargs) -> None:
        """Render density contours."""
        valid = np.isfinite(x) & np.isfinite(y)
        x_vis, y_vis = x[valid], y[valid]

        if len(x_vis) < 100:
            ax.scatter(x_vis, y_vis, s=2, alpha=0.3)
            return

        x_lo, x_hi = ax.get_xlim()
        y_lo, y_hi = ax.get_ylim()

        bins = kwargs.get("bins", 100)
        hist, xedges, yedges = np.histogram2d(
            x_vis, y_vis, 
            bins=bins, 
            range=[[x_lo, x_hi], [y_lo, y_hi]]
        )

        # Smooth to get cleaner contours
        sigma = kwargs.get("sigma", 1.5)
        smoothed = gaussian_filter(hist, sigma=sigma)

        X, Y = np.meshgrid(
            (xedges[:-1] + xedges[1:]) / 2,
            (yedges[:-1] + yedges[1:]) / 2
        )
        
        ax.contour(
            X, Y, smoothed.T, 
            levels=kwargs.get("levels", 10),
            colors=kwargs.get("colors", 'k'), 
            alpha=kwargs.get("alpha", 0.5),
            linewidths=0.8
        )
