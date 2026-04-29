"""Renderer strategy for 1D Cumulative Distribution Function (CDF) plots."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from biopro.ui.theme import Colors


class CdfStrategy(DisplayStrategy):
    """1D Cumulative Distribution Function (CDF) renderer."""

    def render(self, ax, x, y=None, **kwargs) -> None:
        """Render a CDF plot for the X-axis parameter."""
        valid_x = x[np.isfinite(x)]
        if len(valid_x) == 0:
            return

        sorted_x = np.sort(valid_x)
        y_vals = np.arange(len(sorted_x)) / float(len(sorted_x))

        ax.plot(
            sorted_x, y_vals,
            color=kwargs.get("color", Colors.ACCENT_PRIMARY),
            linewidth=kwargs.get("linewidth", 1.5),
            alpha=kwargs.get("alpha", 0.9)
        )
        ax.set_ylabel("Probability", fontsize=9)
        ax.set_ylim(0, 1.05)
