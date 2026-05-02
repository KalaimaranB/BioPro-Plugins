"""render_panels package."""
from .pseudocolor_panel import PseudocolorSettingsPanel
from .dotplot_panel import DotPlotSettingsPanel
from .histogram_panel import HistogramSettingsPanel
from .contour_panel import ContourSettingsPanel
from .density_panel import DensitySettingsPanel

__all__ = [
    "PseudocolorSettingsPanel",
    "DotPlotSettingsPanel",
    "HistogramSettingsPanel",
    "ContourSettingsPanel",
    "DensitySettingsPanel",
]
