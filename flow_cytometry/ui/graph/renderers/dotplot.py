"""Renderer strategy for simple subsampled scatter plots."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from biopro.ui.theme import Colors


class DotPlotStrategy(DisplayStrategy):
    """Simple subsampled scatter plot renderer."""

    def render(self, ax, x, y, **kwargs) -> None:
        """Render individual events as dots."""
        max_events = kwargs.get("max_events", 100_000)
        n = len(x)
        
        if max_events is not None and n > max_events:
            idx = np.random.choice(n, max_events, replace=False)
            x, y = x[idx], y[idx]

        ax.scatter(
            x, y,
            s=kwargs.get("s", 2),
            c=kwargs.get("c", Colors.ACCENT_PRIMARY),
            alpha=kwargs.get("alpha", 0.25),
            rasterized=True,
            edgecolors="none",
        )
