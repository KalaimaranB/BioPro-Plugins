"""Pytest configuration and top-level fixtures for flow_cytometry tests."""

import os
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure headless Qt can start in CI or offline environments
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# ── Use real Qt if available, otherwise mock it ───────────────────────────
USE_REAL_QT = True
try:
    import PyQt6  # noqa: F401
    import matplotlib.backends.backend_qtagg  # noqa: F401
except Exception:
    USE_REAL_QT = False

if USE_REAL_QT:
    from PyQt6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication([])
else:
    # Create mock Qt modules with proper version checking
    class MockQtVersion:
        def __init__(self):
            self.major = 6
            self.minor = 5
        
        def toString(self):
            return "6.5.0"

    class MockQtCore:
        QLibraryInfo = MagicMock()
        QLibraryInfo.version = MagicMock(return_value=MockQtVersion())
        QTimer = MagicMock()
        Qt = MagicMock()
        Qt.FocusPolicy = type('FocusPolicy', (), {'StrongFocus': MagicMock()})()
        pyqtSignal = MagicMock()
        Slot = lambda x: x

    class MockQtGui:
        pass

    class MockQtWidgets:
        QSizePolicy = MagicMock()
        QSizePolicy.Policy = type('Policy', (), {
            'Expanding': MagicMock(),
        })()
        QLabel = MagicMock()

    # Mock matplotlib backends to avoid Qt version checking
    mock_figure_canvas = MagicMock()
    mock_canvas = MagicMock()
    mock_canvas.side_effect = None  # Ensure no side_effect
    mock_figure_canvas.FigureCanvasQTAgg = mock_canvas
    sys.modules['matplotlib.backends.backend_qtagg'] = mock_figure_canvas
    sys.modules['matplotlib.backends.qt_compat'] = MagicMock()

# Mock biopro theme module
class MockColors:
    BG_DARKEST = '#121212'
    BG_DARK = '#1F1F26'
    BG_MEDIUM = '#2A2A34'
    BORDER = '#404040'
    FG_PRIMARY = '#FFFFFF'
    FG_SECONDARY = '#999999'
    FG_DISABLED = '#6C6C7A'
    ACCENT_PRIMARY = '#58A6FF'
    ACCENT_PRIMARY_HOVER = '#4494E8'
    ACCENT_PRIMARY_PRESSED = '#2C73C7'
    ACCENT_NEGATIVE = '#FF6B6B'
    ACCENT_WARNING = '#FFC542'
    ACCENT_DANGER = '#FF4D4D'
    SUCCESS = '#4CAF50'
    BORDER_FOCUS = '#90CDF4'
    CHART_COLORS = [
        '#58A6FF', '#4DD0E1', '#50E3C2', '#82C91E',
        '#F59F00', '#F76707', '#BE4BDB', '#FF6B6B'
    ]

class MockFonts:
    SIZE_SMALL = 10
    SIZE_NORMAL = 12
    SIZE_LARGE = 14
    SIZE_XLARGE = 18

sys.modules['biopro'] = MagicMock()
sys.modules['biopro.ui'] = MagicMock()
sys.modules['biopro.ui.theme'] = MagicMock()
sys.modules['biopro.ui.theme'].Colors = MockColors
sys.modules['biopro.ui.theme'].Fonts = MockFonts

import types
def mock_pkg(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

biopro_sdk = mock_pkg("biopro.sdk")
biopro_sdk_core = mock_pkg("biopro.sdk.core")
class MockBase: pass
biopro_sdk_core.PluginState = MockBase
biopro_sdk_core.PluginBase = MockBase
biopro_sdk_core.AnalysisBase = MockBase
biopro_sdk_core_managed_task = mock_pkg("biopro.sdk.core.managed_task")
biopro_sdk_core_managed_task.FunctionalTask = MagicMock
biopro_sdk_core.managed_task = biopro_sdk_core_managed_task

biopro_core = mock_pkg("biopro.core")
biopro_core_task = mock_pkg("biopro.core.task_scheduler")
biopro_core_task.task_scheduler = MagicMock()

sys.modules['biopro.shared'] = MagicMock()
sys.modules['biopro.shared.ui'] = MagicMock()
sys.modules['biopro.shared.ui.ui_components'] = MagicMock()
sys.modules['biopro.shared.ui.ui_components'].PrimaryButton = MagicMock
sys.modules['biopro.shared.ui.ui_components'].SecondaryButton = MagicMock

# ─────────────────────────────────────────────────────────────────────────

# Add parent directory to path to import flow_cytometry
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import all fixtures
from flow_cytometry.tests.fixtures import *  # noqa: F401, F403

# ── Pytest Configuration ──────────────────────────────────────────────────

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (fast, no I/O)"
    )
    config.addinivalue_line(
        "markers", "functional: mark test as a functional test (medium speed)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (full workflow)"
    )
    config.addinivalue_line(
        "markers", "edge_case: mark test as an edge case test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "ui: mark test as a UI test (requires PyQt6)"
    )


@pytest.fixture(scope="session")
def tests_dir():
    """Root directory of tests."""
    return Path(__file__).parent


@pytest.fixture(autouse=True)
def reset_random_seed():
    """Reset random seed before each test for reproducibility."""
    import numpy as np
    np.random.seed(42)
    yield


@pytest.fixture(scope="session")
def fcs_dir():
    """Path to real FCS test data."""
    return Path(__file__).parent / "data" / "fcs"


@pytest.fixture(scope="session")
def sample_c_events(fcs_dir):
    """Real 20k-event FCS data from Specimen_001_Sample_C.fcs."""
    from flow_cytometry.analysis.fcs_io import load_fcs
    # Using the exact path to one of the real data files
    path = fcs_dir / "Specimen_001_Sample C.fcs"
    if not path.exists():
        pytest.skip(f"Real FCS test data not found: {path}")
    sample = load_fcs(str(path))
    return sample.events


@pytest.fixture(scope="session")
def sample_a_events(fcs_dir):
    """Real FCS data from Specimen_001_Sample_A.fcs."""
    from flow_cytometry.analysis.fcs_io import load_fcs
    path = fcs_dir / "Specimen_001_Sample A.fcs"
    if not path.exists():
        pytest.skip(f"Real FCS test data not found: {path}")
    sample = load_fcs(str(path))
    return sample.events


@pytest.fixture
def graph_window_with_sample_c(qtbot, fcs_dir):
    """Fully initialised GraphWindow using real FCS data."""
    from flow_cytometry.ui.graph.graph_window import GraphWindow
    from flow_cytometry.analysis.state import FlowState
    from flow_cytometry.analysis.experiment import Experiment
    from flow_cytometry.analysis.fcs_io import load_fcs
    from biopro.sdk.core import PluginState
    
    path = fcs_dir / "Specimen_001_Sample C.fcs"
    if not path.exists():
        pytest.skip(f"Real FCS test data not found: {path}")
        
    fcs_data = load_fcs(str(path))
    from flow_cytometry.analysis.experiment import Sample
    sample = Sample(sample_id="sample_c", display_name="Sample C", fcs_data=fcs_data)
    
    state = FlowState(PluginState())
    state.experiment = Experiment()
    state.experiment.samples[sample.sample_id] = sample
    
    # We need a headless GraphWindow
    win = GraphWindow(state, sample.sample_id)
    win.show()
    qtbot.addWidget(win)
    
    # Wait for the async initial render to complete (debounced)
    qtbot.waitSignal(win._axis_debounce.timeout, timeout=1000)
    qtbot.wait(100) # extra buffer for render completion
    
    return win
