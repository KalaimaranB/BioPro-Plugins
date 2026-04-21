"""Integration test for GroupPreviewPanel.

Verifies that the rendering request logic (asynchronous tasks) is free of
NameErrors and correctly handles various state configurations.
"""

import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock
import types

# 1. Setup Mock Environment (Same as verify_imports.py)
plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if plugin_root not in sys.path:
    sys.path.insert(0, plugin_root)

def mock_pkg(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

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

biopro.core = mock_pkg("biopro.core")
biopro.core.task_scheduler = mock_pkg("biopro.core.task_scheduler")
biopro.core.task_scheduler.task_scheduler = MagicMock()

sys.modules["PyQt6"] = MagicMock()
sys.modules["PyQt6.QtCore"] = MagicMock()
sys.modules["PyQt6.QtWidgets"] = MagicMock()
sys.modules["PyQt6.QtGui"] = MagicMock()

mock_pkg("pandas")
mock_pkg("numpy").inf = float('inf')
sys.modules["numpy"].nan = float('nan')
sys.modules["numpy"].float64 = float

mock_pkg("matplotlib")
mock_pkg("matplotlib.figure").Figure = MagicMock
mock_pkg("matplotlib.backends.backend_agg").FigureCanvasAgg = MagicMock
mock_pkg("matplotlib.backends.backend_qtagg").FigureCanvasQTAgg = MagicMock
mock_pkg("matplotlib.patches").Rectangle = MagicMock
mock_pkg("matplotlib.patches").Polygon = MagicMock
mock_pkg("matplotlib.lines").Line2D = MagicMock
mock_pkg("fast_histogram").histogram2d = MagicMock
mock_pkg("scipy.ndimage").gaussian_filter = MagicMock

# 2. Setup Test Case
def test_preview_task_closure():
    """Verify that _request_render doesn't crash and initializes variables."""
    from flow_cytometry.ui.widgets.group_preview import PreviewThumbnail
    
    state = MagicMock()
    sample = MagicMock()
    # Mocking properties for compatibility
    type(sample).has_data = PropertyMock(return_value=True)
    sample.fcs_data.events = [1, 2, 3]
    state.experiment.samples = {"s1": sample}
    state.channel_scales = {}
    
    thumb = PreviewThumbnail(state, "s1")
    
    print("Testing _request_render and callback for NameErrors & TypeErrors...")
    try:
        # Patch QImage to verify its arguments
        with patch("flow_cytometry.ui.widgets.group_preview.QImage") as mock_qimage:
            # Patch FunctionalTask to avoid logic issues
            with patch("flow_cytometry.ui.widgets.group_preview.FunctionalTask") as mock_task_cls:
                # Patch the task_scheduler itself
                with patch("flow_cytometry.ui.widgets.group_preview.task_scheduler") as mock_scheduler:
                    
                    # Scenario 1: Basic render
                    thumb._request_render("FSC-A", "SSC-A", None, 5000)
                    
                    # Capture the on_finished callback
                    on_finished = mock_scheduler.task_finished.connect.call_args[0][0]
                    
                    # Call it with the dict wrapping that the SDK uses
                    print("Executing on_finished callback (Scenario 1)...")
                    dummy_pixels = b"dummy_pixels_rgba"
                    on_finished("dummy_id", {"result": dummy_pixels})
                    
                    # VERIFY QImage was called with bytes, not a dict
                    if not mock_qimage.called:
                        print("❌ QImage was NOT called!")
                        raise AssertionError("QImage not called")
                        
                    args = mock_qimage.call_args[0]
                    if not isinstance(args[0], bytes):
                        print(f"❌ QImage called with {type(args[0])}, expected bytes!")
                        raise TypeError(f"QImage called with {type(args[0])}")
                        
                    print("✓ Scenario 1 passed (QImage received bytes)")
                    
                    # Scenario 2: Preview render
                    thumb._request_render("FSC-A", "SSC-A", None, 5000, temp_gate=MagicMock())
                    on_finished_preview = mock_scheduler.task_finished.connect.call_args[0][0]
                    
                    print("Executing on_finished callback (Scenario 2 - Preview)...")
                    on_finished_preview("dummy_id", {"result": b"preview_pixels"})
                    print("✓ Scenario 2 passed")
                
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    print("Running Preview Task Closure Tests...")
    try:
        test_preview_task_closure()
        print("\n🚀 All closure tests passed! No NameErrors detected.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
