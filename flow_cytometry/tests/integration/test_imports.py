"""Sanity check for BioPro Flow Cytometry plugin.

Attempts to import all key modules to ensure no broken relative imports exist.
"""

import sys
import os
from unittest.mock import MagicMock

# 1. Add plugins root to path
plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if plugin_root not in sys.path:
    sys.path.insert(0, plugin_root)

import types
def mock_pkg(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

# 2. Mock external dependencies (BioPro SDK, PyQt6, etc.)
biopro = mock_pkg("biopro")
biopro.sdk = mock_pkg("biopro.sdk")
biopro.sdk.core = mock_pkg("biopro.sdk.core")
biopro.sdk.core.PluginState = MagicMock
biopro.sdk.core.PluginBase = MagicMock
biopro.sdk.core.AnalysisBase = MagicMock
biopro.sdk.core.managed_task = mock_pkg("biopro.sdk.core.managed_task")
biopro.sdk.core.managed_task.FunctionalTask = MagicMock

biopro.ui = mock_pkg("biopro.ui")
biopro.ui.theme = mock_pkg("biopro.ui.theme")
biopro.ui.theme.Colors = MagicMock()
biopro.ui.theme.Fonts = MagicMock()

biopro.shared = mock_pkg("biopro.shared")
biopro.shared.ui = mock_pkg("biopro.shared.ui")
biopro.shared.ui.ui_components = mock_pkg("biopro.shared.ui.ui_components")
biopro.shared.ui.ui_components.PrimaryButton = MagicMock
biopro.shared.ui.ui_components.SecondaryButton = MagicMock
biopro.shared.ui.ui_components.GhostButton = MagicMock

biopro.core = mock_pkg("biopro.core")
biopro.core.task_scheduler = mock_pkg("biopro.core.task_scheduler")
biopro.core.task_scheduler.task_scheduler = MagicMock()

# UI frameworks
sys.modules["PyQt6"] = MagicMock()
sys.modules["PyQt6.QtCore"] = MagicMock()
sys.modules["PyQt6.QtWidgets"] = MagicMock()
sys.modules["PyQt6.QtGui"] = MagicMock()

# Analysis heavyweights
# Analysis heavyweights
mock_pkg("pandas")
pd = sys.modules["pandas"]
pd.DataFrame = MagicMock
pd.Series = MagicMock
pd.read_csv = MagicMock

np = mock_pkg("numpy")
np.inf = float('inf')
np.nan = float('nan')
np.float64 = float
np.array = MagicMock
np.random = MagicMock()
np.isfinite = MagicMock
np.clip = MagicMock
np.argsort = MagicMock

mpl = mock_pkg("matplotlib")
mpl.colormaps = MagicMock()
mpl.cm = MagicMock()
mock_pkg("matplotlib.figure").Figure = MagicMock
mock_pkg("matplotlib.axes").Axes = MagicMock
mock_pkg("matplotlib.backends")
mock_pkg("matplotlib.backends.backend_agg").FigureCanvasAgg = MagicMock
mock_pkg("matplotlib.backends.backend_qtagg").FigureCanvasQTAgg = MagicMock
patches = mock_pkg("matplotlib.patches")
patches.Rectangle = MagicMock
patches.Polygon = MagicMock
patches.Ellipse = MagicMock
patches.FancyBboxPatch = MagicMock
mock_pkg("matplotlib.lines").Line2D = MagicMock
mock_pkg("matplotlib.ticker")
mock_pkg("fast_histogram").histogram2d = MagicMock
mock_pkg("scipy")
mock_pkg("scipy.ndimage").gaussian_filter = MagicMock
mock_pkg("scipy.stats").rankdata = MagicMock

print("Checking imports for flow_cytometry...")

try:
    # Test entry point
    import flow_cytometry
    print("✓ flow_cytometry imported")
    
    from flow_cytometry import get_panel_class
    print("✓ get_panel_class found")
    
    panel_cls = get_panel_class()
    print(f"✓ Panel class retrieved: {panel_cls.__name__}")
    
    # Deep dive into widgets (where the error was)
    from flow_cytometry.ui.widgets.group_preview import GroupPreviewPanel
    print("✓ GroupPreviewPanel imported")
    
    from flow_cytometry.ui.widgets.properties_panel import PropertiesPanel
    print("✓ PropertiesPanel imported")
    
    print("\n🚀 All imports verified successfully!")
    
except Exception as e:
    print(f"\n❌ IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
    raise e
