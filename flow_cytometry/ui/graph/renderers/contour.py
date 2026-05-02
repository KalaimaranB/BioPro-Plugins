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

        sigma = kwargs.get("sigma", kwargs.get("smoothing", 1.5))
        smoothed = gaussian_filter(hist, sigma=sigma)

        X, Y = np.meshgrid(
            (xedges[:-1] + xedges[1:]) / 2,
            (yedges[:-1] + yedges[1:]) / 2
        )

        levels = kwargs.get("levels", kwargs.get("num_levels", 10))
        show_filled = kwargs.get("show_filled", False)
        color_mode = kwargs.get("color_mode", "black")
        colormap = kwargs.get("colormap", "viridis")
        show_dot_underlay = kwargs.get("show_dot_underlay", False)

        # Manually calculate levels to avoid starting at 0 (which fills the whole canvas)
        max_val = np.max(smoothed)
        if max_val > 0:
            # We start at 2% of the max density to clear the background noise
            # and prevent the colormap from filling the entire plot area.
            levels_arr = np.linspace(max_val * 0.02, max_val, levels)
        else:
            levels_arr = [0, 1]

        # Optional dot underlay first (zorder=0 so contours sit on top)
        if show_dot_underlay:
            max_dots = min(len(x_vis), 30_000)
            if len(x_vis) > max_dots:
                idx = np.random.choice(len(x_vis), max_dots, replace=False)
                xd, yd = x_vis[idx], y_vis[idx]
            else:
                xd, yd = x_vis, y_vis
            ax.scatter(xd, yd, s=1, c="#888888", alpha=0.15, zorder=0, rasterized=True, edgecolors="none")

        # Filled contours
        if show_filled:
            ax.contourf(X, Y, smoothed.T, levels=levels_arr, cmap=colormap, alpha=0.5, zorder=1)

        # Contour lines — color mode determines style
        if color_mode == "colormap":
            ax.contour(X, Y, smoothed.T, levels=levels_arr, cmap=colormap, alpha=0.8, linewidths=0.8, zorder=2)
        elif color_mode == "blue":
            ax.contour(X, Y, smoothed.T, levels=levels_arr, colors="#1565C0", alpha=0.7, linewidths=0.8, zorder=2)
        else:  # black (default)
            ax.contour(X, Y, smoothed.T, levels=levels_arr, colors="k", alpha=0.5, linewidths=0.8, zorder=2)
