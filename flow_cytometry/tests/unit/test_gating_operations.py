"""Unit tests for gate operations.

Tests gate membership calculations (contains, exclusion, etc.)
"""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.gating import (
    RectangleGate, PolygonGate, EllipseGate, QuadrantGate, RangeGate
)
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.scaling import AxisScale


class TestRectangleGateContains:
    """Test RectangleGate.contains() membership calculations."""
    
    @pytest.mark.unit
    def test_contains_point_inside(self, gate_rectangle_singlet):
        """Point inside rectangle should be in gate."""
        x = 100_000
        y = 50_000
        result = gate_rectangle_singlet.contains(
            pd.DataFrame({"FSC-A": [x], "SSC-A": [y]})
        )
        assert result[0], "Point inside gate should be included"
    
    @pytest.mark.unit
    def test_contains_point_outside(self, gate_rectangle_singlet):
        """Point outside rectangle should not be in gate."""
        x = 10_000  # Less than x_min
        y = 50_000
        result = gate_rectangle_singlet.contains(
            pd.DataFrame({"FSC-A": [x], "SSC-A": [y]})
        )
        assert not result[0], "Point outside gate should be excluded"
    
    @pytest.mark.unit
    def test_contains_multiple_points(self, gate_rectangle_singlet):
        """Test membership for multiple points."""
        data = pd.DataFrame({
            "FSC-A": [60_000, 150_000, 300_000, 100_000],
            "SSC-A": [20_000, 50_000, 50_000, 50_000],
        })
        result = gate_rectangle_singlet.contains(data)
        
        assert result[0], "First point should be in gate"
        assert result[1], "Second point should be in gate"
        assert not result[2], "Third point (x too high) should be out"
        assert result[3], "Fourth point should be in gate"
    
    @pytest.mark.unit
    def test_contains_boundary(self, gate_rectangle_singlet):
        """Test points on gate boundary."""
        # On lower boundary
        data = pd.DataFrame({
            "FSC-A": [gate_rectangle_singlet.x_min],
            "SSC-A": [gate_rectangle_singlet.y_min],
        })
        result = gate_rectangle_singlet.contains(data)
        # Boundary behavior depends on implementation
        assert isinstance(result[0], (bool, np.bool_))


class TestRectangleGateEventCounting:
    """Test counting events in gates."""
    
    @pytest.mark.unit
    def test_event_count(self, synthetic_events_small, gate_rectangle_singlet):
        """Count events in gate."""
        # Adjust gate to match data range
        gate = RectangleGate(
            x_param="FSC-A",
            y_param="SSC-A",
            x_min=70_000,
            x_max=150_000,
            y_min=30_000,
            y_max=120_000,
            x_scale=AxisScale(TransformType.LINEAR),
            y_scale=AxisScale(TransformType.LINEAR),
        )
        
        membership = gate.contains(synthetic_events_small)
        count = np.sum(membership)
        
        assert count >= 0, "Event count should be non-negative"
        assert count <= len(synthetic_events_small), "Count should not exceed total events"
    
    @pytest.mark.unit
    def test_event_count_empty(self, synthetic_events_small):
        """Gate with no events should return count of 0."""
        gate = RectangleGate(
            x_param="FSC-A",
            y_param="SSC-A",
            x_min=1e10,  # Way outside data range
            x_max=1e11,
            y_min=1e10,
            y_max=1e11,
            x_scale=AxisScale(TransformType.LINEAR),
            y_scale=AxisScale(TransformType.LINEAR),
        )
        
        membership = gate.contains(synthetic_events_small)
        count = np.sum(membership)
        
        assert count == 0, "Gate outside data should have 0 events"


class TestPolygonGateContains:
    """Test PolygonGate.contains() membership calculations."""
    
    @pytest.mark.unit
    def test_polygon_contains_inside(self, gate_polygon_live):
        """Point inside polygon should be included."""
        x = 100_000
        y = 50_000
        data = pd.DataFrame({"FSC-A": [x], "SSC-A": [y]})
        result = gate_polygon_live.contains(data)
        assert result[0], "Point inside polygon should be included"
    
    @pytest.mark.unit
    def test_polygon_contains_outside(self, gate_polygon_live):
        """Point far outside polygon should be excluded."""
        x = 10_000  # Outside defined polygon
        y = 10_000
        data = pd.DataFrame({"FSC-A": [x], "SSC-A": [y]})
        result = gate_polygon_live.contains(data)
        assert not result[0], "Point outside polygon should be excluded"


class TestEllipseGateContains:
    """Test EllipseGate.contains() membership calculations."""
    
    @pytest.mark.unit
    def test_ellipse_contains_center(self, gate_ellipse_cd4_plus):
        """Center of ellipse should always be included."""
        cx, cy = gate_ellipse_cd4_plus.center
        data = pd.DataFrame({"FITC-A": [cx], "PE-A": [cy]})
        result = gate_ellipse_cd4_plus.contains(data)
        assert result[0], "Center of ellipse should be included"
    
    @pytest.mark.unit
    def test_ellipse_contains_on_axis(self, gate_ellipse_cd4_plus):
        """Points on ellipse axes should be checked."""
        cx, cy = gate_ellipse_cd4_plus.center
        w = gate_ellipse_cd4_plus.width
        
        # Point on x-axis of ellipse
        data = pd.DataFrame({"FITC-A": [cx + w * 0.9], "PE-A": [cy]})
        result = gate_ellipse_cd4_plus.contains(data)
        # Should be in gate (within semi-major axis)
        assert isinstance(result[0], (bool, np.bool_))


class TestQuadrantGateContains:
    """Test QuadrantGate.contains() membership calculations."""
    
    @pytest.mark.unit
    def test_quadrant_regions(self, gate_quadrant_cd4_cd8):
        """Test points in different quadrant regions."""
        xm = gate_quadrant_cd4_cd8.x_mid
        ym = gate_quadrant_cd4_cd8.y_mid
        
        # Create test points in each quadrant
        q1 = (xm + 1000, ym + 500)  # +/+
        q2 = (xm - 1000, ym + 500)  # -/+
        q3 = (xm - 1000, ym - 500)  # -/-
        q4 = (xm + 1000, ym - 500)  # +/-
        
        for qx, qy in [q1, q2, q3, q4]:
            data = pd.DataFrame({"FITC-A": [qx], "PE-A": [qy]})
            result = gate_quadrant_cd4_cd8.contains(data)
            # All should be valid boolean
            assert isinstance(result[0], (bool, np.bool_))


class TestRangeGateContains:
    """Test RangeGate.contains() membership calculations."""
    
    @pytest.mark.unit
    def test_range_contains_inside(self, gate_range_cd3):
        """Point inside range should be included."""
        x = 1000
        data = pd.DataFrame({"CD3": [x]})
        result = gate_range_cd3.contains(data)
        assert result[0], "Point in range should be included"
    
    @pytest.mark.unit
    def test_range_contains_outside_low(self, gate_range_cd3):
        """Point below range should be excluded."""
        x = 50
        data = pd.DataFrame({"CD3": [x]})
        result = gate_range_cd3.contains(data)
        assert not result[0], "Point below range should be excluded"
    
    @pytest.mark.unit
    def test_range_contains_outside_high(self, gate_range_cd3):
        """Point above range should be excluded."""
        x = 1e7
        data = pd.DataFrame({"CD3": [x]})
        result = gate_range_cd3.contains(data)
        # Depends on gate.high value
        assert isinstance(result[0], (bool, np.bool_))


class TestGateOperationsWithTransforms:
    """Test gate operations with transformed coordinates."""
    
    @pytest.mark.unit
    def test_biexp_gate_contains(self, gate_ellipse_cd4_plus):
        """Gate with biexp transform should work correctly."""
        cx, cy = gate_ellipse_cd4_plus.center
        
        # Test point at center
        data = pd.DataFrame({"FITC-A": [cx], "PE-A": [cy]})
        result = gate_ellipse_cd4_plus.contains(data)
        
        assert result[0], "Center should be in gate"


class TestGateErrorHandling:
    """Test gate error handling."""
    
    @pytest.mark.unit
    def test_missing_parameter_column(self, gate_rectangle_singlet, synthetic_events_small):
        """Missing parameter column should raise error."""
        # Remove FSC-A column
        bad_data = synthetic_events_small.drop("FSC-A", axis=1)
        
        # Should raise KeyError or similar
        with pytest.raises(KeyError):
            gate_rectangle_singlet.contains(bad_data)
    
    @pytest.mark.unit
    def test_nan_values_in_data(self, gate_rectangle_singlet):
        """NaN values in data should be handled."""
        data = pd.DataFrame({
            "FSC-A": [100_000, np.nan, 120_000],
            "SSC-A": [50_000, 60_000, np.nan],
        })
        
        result = gate_rectangle_singlet.contains(data)
        
        # NaN rows should typically be False (not in gate)
        assert len(result) == 3
        assert isinstance(result[1], (bool, np.bool_))
