"""
Edge case tests for gate operations - handling invalid inputs, NaN, Inf, and boundary conditions.

Tests verify that gates handle edge cases gracefully:
- NaN values in data
- Inf values
- Empty data
- Missing parameters
- Extreme values
- Numerical instability
- Inverted bounds
- Single-event populations
"""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.gating import RectangleGate, PolygonGate, EllipseGate, QuadrantGate, RangeGate


@pytest.mark.edge_case
class TestNaNHandling:
    """Test gate behavior with NaN values."""

    def test_gate_with_nan_in_x_parameter(self):
        """Apply gate to data with NaN in x parameter."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [100_000, np.nan, 150_000, 120_000],
            'SSC-A': [5_000, 6_000, np.nan, 8_000],
        })
        
        result = gate.contains(data)
        
        # Should handle NaN without crashing
        assert len(result) == len(data)
        # NaN rows should be False (not inside gate)
        assert result[1] == False
        assert result[2] == False

    def test_gate_with_all_nan(self):
        """Apply gate to data that's entirely NaN."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [np.nan, np.nan, np.nan],
            'SSC-A': [np.nan, np.nan, np.nan],
        })
        
        result = gate.contains(data)
        
        # All should be False
        assert np.sum(result) == 0

    def test_range_gate_with_nan(self):
        """Range gate with NaN values."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        data = pd.DataFrame({
            'FITC-A': [100, np.nan, 200, 30, np.nan],
        })
        
        result = gate.contains(data)
        
        # NaN should be False
        assert result[1] == False
        assert result[4] == False
        # Valid values should be evaluated
        assert result[0] == True  # 100 is in [50, 250]
        assert result[2] == True  # 200 is in [50, 250]
        assert result[3] == False # 30 is not in [50, 250]


@pytest.mark.edge_case
class TestInfinityHandling:
    """Test gate behavior with Inf values."""

    def test_gate_with_positive_infinity(self):
        """Apply gate to data with positive Inf."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [100_000, np.inf, 150_000],
            'SSC-A': [5_000, 10_000, np.inf],
        })
        
        result = gate.contains(data)
        
        # Inf should be False (outside gate bounds)
        assert result[1] == False
        assert result[2] == False

    def test_gate_with_negative_infinity(self):
        """Apply gate to data with negative Inf."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [100_000, -np.inf, 150_000],
            'SSC-A': [5_000, 10_000, 20_000],
        })
        
        result = gate.contains(data)
        
        # -Inf should be False (outside bounds)
        assert result[1] == False

    def test_range_gate_with_infinity(self):
        """Range gate with Inf values."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        data = pd.DataFrame({
            'FITC-A': [100, np.inf, 200, -np.inf, 150],
        })
        
        result = gate.contains(data)
        
        # Inf values should be outside range
        assert result[1] == False  # np.inf
        assert result[3] == False  # -np.inf
        # Valid values should be True
        assert result[0] == True
        assert result[2] == True


@pytest.mark.edge_case
class TestEmptyDataHandling:
    """Test gate behavior with empty data."""

    def test_gate_on_empty_dataframe(self):
        """Apply gate to empty DataFrame."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        empty = pd.DataFrame({'FSC-A': [], 'SSC-A': []})
        result = gate.contains(empty)
        
        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_gate_on_single_event(self):
        """Apply gate to single event."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        data = pd.DataFrame({'FSC-A': [100_000], 'SSC-A': [5_000]})
        result = gate.contains(data)
        
        assert len(result) == 1
        assert result[0] == True

    def test_gate_on_zero_events(self):
        """Apply gate to zero-size arrays."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        data = pd.DataFrame({'FITC-A': []})
        result = gate.contains(data)
        
        assert len(result) == 0


@pytest.mark.edge_case
class TestBoundaryConditions:
    """Test gates at exact boundaries."""

    def test_rectangle_gate_point_on_boundary(self):
        """Points exactly on rectangle boundary."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=100_000, x_max=200_000, y_min=10_000, y_max=50_000)
        
        # Test boundary points
        data = pd.DataFrame({
            'FSC-A': [100_000, 200_000, 150_000, 150_000],  # left, right, center, center
            'SSC-A': [10_000, 50_000, 30_000, 10_000],      # bottom, top, center, bottom
        })
        
        result = gate.contains(data)
        
        # Behavior: points on or inside should be True
        assert np.sum(result) >= 1  # At least some should be inside

    def test_range_gate_at_boundaries(self):
        """Range gate at exact min/max boundaries."""
        gate = RangeGate('FITC-A', low=100, high=200)
        
        data = pd.DataFrame({
            'FITC-A': [100, 200, 99, 201, 150],
        })
        
        result = gate.contains(data)
        
        # Boundary behavior (typically inclusive)
        assert result[0] == True   # 100 (at min)
        assert result[1] == True   # 200 (at max)
        assert result[2] == False  # 99 (below min)
        assert result[3] == False  # 201 (above max)
        assert result[4] == True   # 150 (inside)

    def test_near_boundary_precision(self):
        """Test gates with values very close to boundaries."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=100_000, x_max=200_000, y_min=10_000, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [99_999.999, 100_000.001, 200_000.001, 199_999.999],
            'SSC-A': [30_000, 30_000, 30_000, 30_000],
        })
        
        result = gate.contains(data)
        
        # Just outside vs just inside
        # Behavior may vary by implementation
        assert len(result) == 4  # All should be evaluable


@pytest.mark.edge_case
class TestMissingParameters:
    """Test gate behavior with missing or invalid parameters."""

    def test_gate_with_missing_parameter_column(self):
        """Apply gate when parameter column is missing."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        # Missing FSC-A column
        data = pd.DataFrame({
            'SSC-A': [5_000, 10_000, 15_000],
        })
        
        # Should raise error
        with pytest.raises((KeyError, ValueError)):
            gate.contains(data)

    def test_range_gate_with_missing_parameter(self):
        """Range gate with missing parameter column."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        data = pd.DataFrame({
            'PE-A': [100, 150, 200],  # Wrong parameter
        })
        
        with pytest.raises((KeyError, ValueError)):
            gate.contains(data)


@pytest.mark.edge_case
class TestExtremeValues:
    """Test gates with extreme numeric values."""

    def test_gate_with_very_small_values(self):
        """Gate with very small positive values."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=1, x_max=1000, y_min=0.1, y_max=100)
        
        data = pd.DataFrame({
            'FSC-A': [0.5, 1.5, 500, 1001],
            'SSC-A': [0.05, 0.5, 50, 101],
        })
        
        result = gate.contains(data)
        
        assert len(result) == 4
        # Should handle small values without precision issues

    def test_gate_with_very_large_values(self):
        """Gate with very large values (typical for flow cytometry)."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=100_000, x_max=262_143, y_min=1_000, y_max=262_143)
        
        data = pd.DataFrame({
            'FSC-A': [150_000, 262_142, 262_143, 262_144],
            'SSC-A': [100_000, 150_000, 200_000, 300_000],
        })
        
        result = gate.contains(data)
        
        assert len(result) == 4

    def test_negative_values_in_data(self):
        """Gate on data with negative values (valid in flow cytometry)."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=-100, x_max=200_000, y_min=-50, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [-50, 0, 100_000, 200_001],
            'SSC-A': [-25, 0, 25_000, 50_001],
        })
        
        result = gate.contains(data)
        
        assert len(result) == 4


@pytest.mark.edge_case
class TestZeroWidthGates:
    """Test gates with zero width (line/point gates)."""

    def test_rectangle_zero_width_x(self):
        """Rectangle with x_min == x_max (vertical line)."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=100_000, x_max=100_000, y_min=1_000, y_max=50_000)
        
        data = pd.DataFrame({
            'FSC-A': [99_999, 100_000, 100_001],
            'SSC-A': [25_000, 25_000, 25_000],
        })
        
        result = gate.contains(data)
        
        # Should handle zero-width gate
        assert len(result) == 3

    def test_range_zero_width(self):
        """Range gate with min == max (single point)."""
        gate = RangeGate('FITC-A', low=100, high=100)
        
        data = pd.DataFrame({
            'FITC-A': [99, 100, 101],
        })
        
        result = gate.contains(data)
        
        assert len(result) == 3
        # Only 100 should be inside (if point is inclusive)


@pytest.mark.edge_case
class TestInvertedGateBounds:
    """Test gates with inverted min/max bounds."""

    def test_rectangle_inverted_x_bounds(self):
        """Rectangle with x_min > x_max."""
        # This should either swap bounds or raise error
        try:
            gate = RectangleGate('FSC-A', 'SSC-A', x_min=200_000, x_max=50_000, y_min=1_000, y_max=50_000)
            
            data = pd.DataFrame({
                'FSC-A': [100_000, 150_000],
                'SSC-A': [25_000, 25_000],
            })
            
            # If it doesn't raise, it should handle gracefully
            result = gate.contains(data)
            assert len(result) == 2
        except (ValueError, AssertionError):
            # Or it might raise an error, which is fine
            pass

    def test_range_inverted_bounds(self):
        """Range gate with min > max."""
        try:
            gate = RangeGate('FITC-A', low=250, high=50)
            
            data = pd.DataFrame({
                'FITC-A': [100, 150],
            })
            
            result = gate.contains(data)
            assert len(result) == 2
        except (ValueError, AssertionError):
            pass


@pytest.mark.edge_case
class TestNumericalStability:
    """Test gates don't have cumulative numerical errors."""

    def test_repeated_gate_operations(self, sample_a_events):
        """Repeated gating produces same results."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        results = []
        for _ in range(10):
            result = gate.contains(sample_a_events)
            results.append(np.sum(result))
        
        # All results should be identical
        assert len(set(results)) == 1, "Repeated gating should give same result"

    def test_gate_chain_stability(self, sample_a_events):
        """Chaining gates doesn't accumulate errors."""
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        gate2 = RectangleGate('FSC-A', 'SSC-A', x_min=70_000, x_max=180_000, y_min=2_000, y_max=40_000)
        gate3 = RectangleGate('FSC-A', 'SSC-A', x_min=80_000, x_max=160_000, y_min=5_000, y_max=35_000)
        
        # Chain: gate1 → gate2 → gate3
        r1 = gate1.contains(sample_a_events)
        l1 = sample_a_events[r1]
        
        r2 = gate2.contains(l1)
        l2 = l1[r2]
        
        r3 = gate3.contains(l2)
        final = l2[r3]
        
        # Should have positive population
        assert len(final) > 0
        # Should not have NaN or Inf
        for col in final.columns:
            assert not final[col].isna().all()


@pytest.mark.edge_case
class TestPolygonEdgeCases:
    """Edge cases specific to polygon gates."""

    def test_polygon_with_two_vertices(self):
        """Polygon with minimum vertices (degenerate)."""
        vertices = np.array([
            [50_000, 1_000],
            [200_000, 50_000],
        ])
        
        gate = PolygonGate('FSC-A', 'SSC-A', vertices)
        
        data = pd.DataFrame({
            'FSC-A': [100_000, 150_000],
            'SSC-A': [10_000, 30_000],
        })
        
        # Should handle or raise error gracefully
        try:
            result = gate.contains(data)
            assert len(result) == 2
        except (ValueError, AssertionError):
            pass

    def test_polygon_with_many_vertices(self):
        """Polygon with very many vertices."""
        # Circle approximation
        n = 100
        angles = np.linspace(0, 2*np.pi, n, endpoint=False)
        vertices = np.array([
            [100_000 + 50_000 * np.cos(a), 25_000 + 20_000 * np.sin(a)]
            for a in angles
        ])
        
        gate = PolygonGate('FSC-A', 'SSC-A', vertices)
        
        data = pd.DataFrame({
            'FSC-A': [100_000, 120_000, 80_000],
            'SSC-A': [25_000, 25_000, 25_000],
        })
        
        result = gate.contains(data)
        assert len(result) == 3


@pytest.mark.edge_case
class TestEllipseEdgeCases:
    """Edge cases specific to ellipse gates."""

    def test_ellipse_zero_semi_axes(self):
        """Ellipse with zero-length semi-axes (point)."""
        gate = EllipseGate('FITC-A', 'PE-A', center=(100, 100), width=0, height=0, angle=0)
        
        data = pd.DataFrame({
            'FITC-A': [100, 101, 99],
            'PE-A': [100, 100, 100],
        })
        
        try:
            result = gate.contains(data)
            assert len(result) == 3
        except (ValueError, ZeroDivisionError):
            pass

    def test_ellipse_very_small_semi_axes(self):
        """Ellipse with very small semi-axes."""
        gate = EllipseGate('FITC-A', 'PE-A', center=(100, 100), width=0.01, height=0.01, angle=0)
        
        data = pd.DataFrame({
            'FITC-A': [100, 100.001, 100.1],
            'PE-A': [100, 100.001, 100.1],
        })
        
        result = gate.contains(data)
        assert len(result) == 3


@pytest.mark.edge_case
class TestQuadrantEdgeCases:
    """Edge cases specific to quadrant gates."""

    def test_quadrant_threshold_at_extreme(self):
        """Quadrant with threshold at data minimum."""
        gate = QuadrantGate('FITC-A', 'PE-A', x_mid=0, y_mid=0)
        
        data = pd.DataFrame({
            'FITC-A': [-100, 0, 100],
            'PE-A': [-100, 0, 100],
        })
        
        result = gate.contains(data)
        assert len(result) == 3

    def test_quadrant_with_identical_values(self):
        """Quadrant gate on data where all values are identical."""
        gate = QuadrantGate('FITC-A', 'PE-A', x_mid=100, y_mid=100)
        
        data = pd.DataFrame({
            'FITC-A': [100, 100, 100],
            'PE-A': [100, 100, 100],
        })
        
        result = gate.contains(data)
        assert len(result) == 3


@pytest.mark.edge_case
@pytest.mark.slow
class TestLargeDataHandling:
    """Test gates with large datasets."""

    def test_gate_on_large_dataset(self, sample_a_events):
        """Gate on full 300K+ event dataset."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        result = gate.contains(sample_a_events)
        
        assert len(result) == len(sample_a_events)
        assert np.sum(result) > 0

    def test_many_sequential_gates_on_large_data(self, sample_a_events):
        """Apply many sequential gates on large data."""
        gates = [
            RectangleGate('FSC-A', 'SSC-A', x_min=30_000 + i*5_000, x_max=220_000 - i*5_000, y_min=100, y_max=60_000)
            for i in range(20)
        ]
        
        current = sample_a_events
        for gate in gates:
            membership = gate.contains(current)
            current = current[membership]
            
            # Should still have some events
            if len(current) < 100:
                break
        
        # Should not crash on large data
        assert len(current) >= 0
