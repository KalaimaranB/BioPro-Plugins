"""Test fixtures for flow_cytometry module testing.

This module provides reusable fixtures for testing flow cytometry components.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from flow_cytometry.analysis.fcs_io import load_fcs
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.gating import (
    RectangleGate,
    PolygonGate,
    EllipseGate,
    QuadrantGate,
    RangeGate,
)


from flow_cytometry.analysis.state import FlowState
from flow_cytometry.analysis.experiment import Sample, Experiment
from flow_cytometry.analysis.population_service import PopulationService

# ── Mock Objects ──────────────────────────────────────────────────────────

class MockFcsData:
    """Mock for FCS data that implements the minimal interface needed for testing."""
    def __init__(self, events: pd.DataFrame):
        self.events = events
        self.parameters = {col: {} for col in events.columns}
        self.metadata = {}
        self.num_events = len(events)
        self.file_path = "test.fcs"

    @property
    def channels(self) -> list[str]:
        return list(self.events.columns)

    @property
    def markers(self) -> list[str]:
        return [""] * len(self.channels)

# ── FCS Data Fixtures ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fcs_test_data_dir():
    """Path to FCS test data directory."""
    # Go up one level to tests directory, then into data/fcs
    return Path(__file__).parent.parent / "data" / "fcs"


@pytest.fixture
def sample_a_events(fcs_test_data_dir):
    """Load Specimen_001_Sample A.fcs events."""
    fcs_file = fcs_test_data_dir / "Specimen_001_Sample A.fcs"
    fcs_data = load_fcs(str(fcs_file))
    return fcs_data.events


@pytest.fixture
def sample_b_events(fcs_test_data_dir):
    """Load Specimen_001_Sample B.fcs events."""
    fcs_file = fcs_test_data_dir / "Specimen_001_Sample B.fcs"
    fcs_data = load_fcs(str(fcs_file))
    return fcs_data.events


@pytest.fixture
def sample_c_events(fcs_test_data_dir):
    """Load Specimen_001_Sample C.fcs events."""
    fcs_file = fcs_test_data_dir / "Specimen_001_Sample C.fcs"
    fcs_data = load_fcs(str(fcs_file))
    return fcs_data.events


@pytest.fixture
def fmo_pe_events(fcs_test_data_dir):
    """Load FMO PE control events."""
    fcs_file = fcs_test_data_dir / "Specimen_001_FMO PE.fcs"
    fcs_data = load_fcs(str(fcs_file))
    return fcs_data.events


@pytest.fixture
def fmo_fitc_events(fcs_test_data_dir):
    """Load FMO FITC control events."""
    fcs_file = fcs_test_data_dir / "Specimen_001_FMO FITC.fcs"
    fcs_data = load_fcs(str(fcs_file))
    return fcs_data.events


@pytest.fixture
def blank_events(fcs_test_data_dir):
    """Load blank control events."""
    fcs_file = fcs_test_data_dir / "Specimen_001_Blank.fcs"
    fcs_data = load_fcs(str(fcs_file))
    return fcs_data.events


# ── Axis Scale Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def scale_linear():
    """Linear axis scale (identity transform)."""
    return AxisScale(TransformType.LINEAR)


@pytest.fixture
def scale_biexp_standard():
    """Standard BiExponential scale (M=5, W=1, T=262144, A=0)."""
    scale = AxisScale(TransformType.BIEXPONENTIAL)
    scale.logicle_m = 5.0
    scale.logicle_w = 1.0
    scale.logicle_t = 262144.0
    scale.logicle_a = 0.0
    return scale


@pytest.fixture
def scale_biexp_relaxed():
    """Relaxed BiExponential scale (M=4, W=0.5, T=10000, A=-100)."""
    scale = AxisScale(TransformType.BIEXPONENTIAL)
    scale.logicle_m = 4.0
    scale.logicle_w = 0.5
    scale.logicle_t = 10000.0
    scale.logicle_a = -100.0
    return scale


@pytest.fixture
def scale_logicle():
    """Logicle axis scale."""
    scale = AxisScale(TransformType.LOGICLE)
    return scale


# ── Gate Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def gate_rectangle_singlet():
    """Typical singlet gate (Rectangle on FSC-A vs SSC-A)."""
    return RectangleGate(
        x_param="FSC-A",
        y_param="SSC-A",
        x_min=50_000,
        x_max=200_000,
        y_min=1_000,
        y_max=50_000,
        x_scale=AxisScale(TransformType.LINEAR),
        y_scale=AxisScale(TransformType.LINEAR),
    )


@pytest.fixture
def gate_rectangle_lymph():
    """Typical lymphocyte gate (Rectangle on FSC-A vs SSC-A)."""
    return RectangleGate(
        x_param="FSC-A",
        y_param="SSC-A",
        x_min=40_000,
        x_max=150_000,
        y_min=500,
        y_max=30_000,
        x_scale=AxisScale(TransformType.LINEAR),
        y_scale=AxisScale(TransformType.LINEAR),
    )


@pytest.fixture
def gate_polygon_live():
    """Typical live cell gate (Polygon excluding debris and doublets)."""
    vertices = [
        (50_000, 1_000),
        (200_000, 1_000),
        (200_000, 50_000),
        (50_000, 50_000),
    ]
    return PolygonGate(
        x_param="FSC-A",
        y_param="SSC-A",
        vertices=vertices,
        x_scale=AxisScale(TransformType.LINEAR),
        y_scale=AxisScale(TransformType.LINEAR),
    )


@pytest.fixture
def gate_ellipse_cd4_plus():
    """Typical fluorescence gate (Ellipse on FITC vs PE)."""
    return EllipseGate(
        x_param="FITC-A",
        y_param="PE-A",
        center=(100, 100),
        width=80,
        height=60,
        angle=0.0,
        x_scale=AxisScale(TransformType.LINEAR),
        y_scale=AxisScale(TransformType.LINEAR),
    )


@pytest.fixture
def gate_quadrant_cd4_cd8():
    """Quadrant gate for fluorescence classification."""
    return QuadrantGate(
        x_param="FITC-A",
        y_param="PE-A",
        x_mid=100,
        y_mid=100,
        x_scale=AxisScale(TransformType.LINEAR),
        y_scale=AxisScale(TransformType.LINEAR),
    )


@pytest.fixture
def gate_range_cd3(scale_biexp_standard):
    """Range gate for fluorescence selection."""
    return RangeGate(
        x_param="CD3",
        low=100,
        high=262144,
        x_scale=scale_biexp_standard,
    )


# ── Synthetic Event Data Fixtures ─────────────────────────────────────────

@pytest.fixture
def synthetic_events_small():
    """Synthetic events DataFrame (1000 events, simple distribution)."""
    np.random.seed(42)
    n_events = 1000
    
    # Simulate typical flow cytometry data
    data = {
        "FSC-A": np.random.normal(100_000, 30_000, n_events).clip(0, 262144),
        "SSC-A": np.random.normal(80_000, 25_000, n_events).clip(0, 262144),
        "CD4": np.random.exponential(5000, n_events).clip(0, 262144),
        "CD8": np.random.exponential(3000, n_events).clip(0, 262144),
        "CD3": np.random.normal(50_000, 30_000, n_events).clip(0, 262144),
    }
    
    return pd.DataFrame(data)


@pytest.fixture
def synthetic_events_medium():
    """Synthetic events DataFrame (10,000 events, realistic distribution)."""
    np.random.seed(42)
    n_events = 10_000
    
    # More realistic simulation with population structure
    fsc = np.concatenate([
        np.random.normal(50_000, 20_000, int(n_events * 0.3)),  # Debris
        np.random.normal(150_000, 40_000, int(n_events * 0.5)),  # Singlets
        np.random.normal(220_000, 30_000, int(n_events * 0.2)),  # Doublets
    ]).clip(0, 262144)
    
    ssc = fsc * 0.8 + np.random.normal(0, 20_000, len(fsc))
    ssc = ssc.clip(0, 262144)
    
    data = {
        "FSC-A": fsc,
        "SSC-A": ssc,
        "CD4": np.random.exponential(5000, n_events).clip(0, 262144),
        "CD8": np.random.exponential(3000, n_events).clip(0, 262144),
        "CD3": np.random.exponential(20_000, n_events).clip(0, 262144),
    }
    
    return pd.DataFrame(data).iloc[:n_events]


@pytest.fixture
def flow_state(synthetic_events_small):
    """Returns a pre-populated FlowState with a test sample and services."""
    state = FlowState()
    sample = Sample(sample_id="test_sample_1", display_name="Test Sample")
    sample.fcs_data = MockFcsData(synthetic_events_small)
    state.experiment.samples[sample.sample_id] = sample
    
    # Initialize services
    from flow_cytometry.analysis.axis_manager import AxisManager
    state.population_service = PopulationService(state)
    state.axis_manager = AxisManager(state)
    return state


# ── Utility Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def coordinate_mapper_linear(scale_linear):
    """CoordinateMapper with linear scales."""
    from flow_cytometry.ui.graph.flow_services import CoordinateMapper
    return CoordinateMapper(scale_linear, scale_linear)


@pytest.fixture
def coordinate_mapper_biexp(scale_biexp_standard):
    """CoordinateMapper with biexponential scales."""
    from flow_cytometry.ui.graph.flow_services import CoordinateMapper
    return CoordinateMapper(scale_biexp_standard, scale_biexp_standard)


@pytest.fixture
def gate_factory_linear(scale_linear):
    """GateFactory with linear scales."""
    from flow_cytometry.ui.graph.flow_services import CoordinateMapper, GateFactory
    mapper = CoordinateMapper(scale_linear, scale_linear)
    return GateFactory("FSC-A", "SSC-A", scale_linear, scale_linear, mapper)


@pytest.fixture
def gate_factory_biexp(scale_biexp_standard):
    """GateFactory with biexponential scales."""
    from flow_cytometry.ui.graph.flow_services import CoordinateMapper, GateFactory
    mapper = CoordinateMapper(scale_biexp_standard, scale_biexp_standard)
    return GateFactory("CD4", "CD8", scale_biexp_standard, scale_biexp_standard, mapper)


# ── Assertion Helpers ───────────────────────────────────────────────────────

def assert_events_subset(subset: pd.DataFrame, superset: pd.DataFrame) -> None:
    """Assert that subset contains only events from superset."""
    # Check that all rows in subset are in superset
    # (comparing as strings for floating point tolerance)
    subset_str = subset.round(6).astype(str).values
    superset_str = superset.round(6).astype(str).values
    
    for row in subset_str:
        assert any((superset_str == row).all(axis=1)), f"Row {row} not found in superset"


def assert_gate_contains_point(gate: object, x: float, y: float) -> None:
    """Assert that gate contains a specific point."""
    from flow_cytometry.analysis.gating import RectangleGate, PolygonGate
    
    if isinstance(gate, RectangleGate):
        assert gate.x_min <= x <= gate.x_max, f"x={x} outside gate x range"
        assert gate.y_min <= y <= gate.y_max, f"y={y} outside gate y range"
    else:
        pytest.skip(f"Point containment test not implemented for {type(gate)}")


def assert_monotonic_decrease(counts: list[int]) -> None:
    """Assert that gate population counts decrease monotonically."""
    for i in range(len(counts) - 1):
        assert counts[i] >= counts[i + 1], \
            f"Population count did not decrease: {counts[i]} -> {counts[i+1]}"
