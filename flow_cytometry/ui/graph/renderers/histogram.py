"""Renderer strategy for 1D frequency histograms."""

from __future__ import annotations
import numpy as np
from .base import DisplayStrategy
from biopro.ui.theme import Colors


class HistogramStrategy(DisplayStrategy):
    """1D Histogram renderer with optional KDE overlay."""

    def render(self, ax, x, y=None, **kwargs) -> None:
        """Render a frequency histogram for the X-axis parameter."""
        valid_x = x[np.isfinite(x)]
        if len(valid_x) == 0:
            return

        color = kwargs.get("color", kwargs.get("bar_color", Colors.ACCENT_PRIMARY))
        filled = kwargs.get("filled", True)
        histtype = "stepfilled" if filled else "step"
        density_mode = kwargs.get("y_axis_mode", "count") == "frequency"

        # Bin count — auto uses Sturges' rule, otherwise use provided value
        auto_bins = kwargs.get("auto_bins", False)
        if auto_bins:
            bins = int(np.ceil(np.log2(len(valid_x)) + 1))
            bins = max(32, min(bins, 512))
        else:
            bins = kwargs.get("bins", 256)

        counts, edges, patches = ax.hist(
            valid_x,
            bins=bins,
            color=color,
            alpha=kwargs.get("alpha", 0.7),
            histtype=histtype,
            density=density_mode,
        )

        # Optional KDE smoothing overlay
        smooth_kde = kwargs.get("smooth_kde", False)
        if smooth_kde and len(valid_x) > 10:
            try:
                from scipy.stats import gaussian_kde
                kde = gaussian_kde(valid_x, bw_method="scott")
                x_grid = np.linspace(valid_x.min(), valid_x.max(), 512)
                kde_vals = kde(x_grid)
                if not density_mode:
                    # Scale KDE to match raw count histogram
                    bin_width = (edges[-1] - edges[0]) / bins
                    kde_vals = kde_vals * len(valid_x) * bin_width
                ax.plot(x_grid, kde_vals, color=color, linewidth=1.5, alpha=0.9)
            except Exception:
                pass  # KDE silently skipped on failure

        y_label = "Frequency (%)" if density_mode else "Count"
        ax.set_ylabel(y_label, fontsize=9)
