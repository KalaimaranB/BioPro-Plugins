"""Renderer strategy for 1D frequency histograms."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from biopro.ui.theme import Colors


class HistogramStrategy(DisplayStrategy):
    """1D Histogram renderer."""

    def render(self, ax, x, y=None, **kwargs) -> None:
        """Render a frequency histogram for the X-axis parameter."""
        valid_x = x[np.isfinite(x)]
        if len(valid_x) == 0:
            return

        ax.hist(
            valid_x,
            bins=kwargs.get("bins", 256),
            color=kwargs.get("color", Colors.ACCENT_PRIMARY),
            alpha=kwargs.get("alpha", 0.7),
            histtype="stepfilled",
            density=kwargs.get("density", False)
        )
        ax.set_ylabel("Count", fontsize=9)
