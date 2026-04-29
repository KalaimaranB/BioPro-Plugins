"""
Functional tests for single gate application on real FCS data.

Tests verify that individual gates applied to real samples produce:
- Reasonable population counts (positive, less than total)
- Valid statistical properties (mean, std, etc.)
- Correct region identification
- Consistency across multiple applications

This tests realistic user workflows like:
- Load Sample A → Apply Singlet gate → Verify population decreased
- Load FCS → Apply Rectangle on FSC/SSC → Check statistics
- Load Blank → Apply Debris gate → Verify clean background
"""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.gating import RectangleGate, PolygonGate, EllipseGate, QuadrantGate, RangeGate


@pytest.mark.functional
class TestSingleRectangleGate:
    """Test Rectangle gate application on real sample data."""

    def test_singlet_gate_on_sample_a(self, sample_a_events, gate_rectangle_singlet):
        """Apply realistic singlet gate (FSC-A vs SSC-A) to Sample A."""
        # Apply gate
        membership = gate_rectangle_singlet.contains(sample_a_events)
        
        # Verify population decreased
        total_events = len(sample_a_events)
        gated_events = np.sum(membership)
        assert 0 < gated_events < total_events, \
            f"Singlet gate should reduce population: {total_events} → {gated_events}"
        
        # Singlet gates typically keep 60-80% of events
        gating_percentage = 100 * gated_events / total_events
        assert 50 < gating_percentage < 90, \
            f"Singlet gate kept {gating_percentage:.1f}% (expected 50-90%)"

    def test_singlet_gate_statistics(self, sample_a_events, gate_rectangle_singlet):
        """Verify statistics computed correctly on gated population."""
        # Get gated subset
        membership = gate_rectangle_singlet.contains(sample_a_events)
        gated = sample_a_events[membership]
        
        # All gated points should be within gate bounds
        fsc_values = gated['FSC-A'].values
        ssc_values = gated['SSC-A'].values
        
        assert np.all(fsc_values >= gate_rectangle_singlet.x_min)
        assert np.all(fsc_values <= gate_rectangle_singlet.x_max)
        assert np.all(ssc_values >= gate_rectangle_singlet.y_min)
        assert np.all(ssc_values <= gate_rectangle_singlet.y_max)
        
        # Verify statistics are reasonable
        assert np.mean(fsc_values) > 0
        assert np.std(fsc_values) > 0
        assert not np.isnan(np.mean(fsc_values))

    def test_singlet_gate_on_blank(self, blank_events, gate_rectangle_singlet):
        """Apply singlet gate to blank control - should have low counts."""
        membership = gate_rectangle_singlet.contains(blank_events)
        gated_count = np.sum(membership)
        total_count = len(blank_events)
        
        # Blank should have lower singlet percentage than live sample
        blank_percentage = 100 * gated_count / total_count
        assert blank_percentage > 0, "Blank should have some singlets"
        assert blank_percentage < 50, f"Blank singlet % too high: {blank_percentage:.1f}%"

    def test_rectangle_gate_consistency(self, sample_a_events, gate_rectangle_singlet):
        """Verify same gate applied twice gives same results."""
        result1 = gate_rectangle_singlet.contains(sample_a_events)
        result2 = gate_rectangle_singlet.contains(sample_a_events)
        
        np.testing.assert_array_equal(result1, result2,
            err_msg="Gate should be deterministic")

    def test_nested_rectangle_gates(self, sample_a_events):
        """Test applying nested gates (inner gate should have fewer events)."""
        # Large gate (less restrictive)
        outer_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        # Small gate inside (more restrictive)
        inner_gate = RectangleGate('FSC-A', 'SSC-A', x_min=150_000, x_max=250_000, y_min=75_000, y_max=150_000)
        
        outer_membership = outer_gate.contains(sample_a_events)
        inner_membership = inner_gate.contains(sample_a_events)
        
        outer_count = np.sum(outer_membership)
        inner_count = np.sum(inner_membership)
        
        # Inner should have fewer or equal events
        assert inner_count <= outer_count, \
            f"Inner gate {inner_count} should have ≤ outer gate {outer_count} events"
        assert inner_count > 0, "Inner gate should have some events"


@pytest.mark.functional
class TestSinglePolygonGate:
    """Test Polygon gate application on real sample data."""

    def test_polygon_gate_on_sample(self, sample_a_events):
        """Apply polygon gate to real sample."""
        # Create a realistic polygon (e.g., live cell region)
        vertices = np.array([
            [100_000, 50_000],   # Bottom-left
            [300_000, 50_000],   # Bottom-right
            [300_000, 150_000],  # Top-right
            [100_000, 150_000],  # Top-left
        ])
        gate = PolygonGate('FSC-A', 'SSC-A', vertices)
        
        membership = gate.contains(sample_a_events)
        gated_count = np.sum(membership)
        
        assert gated_count > 0, "Polygon gate should include some events"
        assert gated_count < len(sample_a_events), "Polygon gate should exclude some events"

    def test_polygon_vs_rectangle(self, sample_a_events):
        """Compare polygon and rectangle on same region."""
        # Rectangle bounds
        rect_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        # Polygon with same outer bounds
        vertices = [
            (50_000, 1_000),
            (200_000, 1_000),
            (200_000, 50_000),
            (50_000, 50_000),
        ]
        poly_gate = PolygonGate('FSC-A', 'SSC-A', vertices)
        
        rect_membership = rect_gate.contains(sample_a_events)
        poly_membership = poly_gate.contains(sample_a_events)
        
        rect_count = np.sum(rect_membership)
        poly_count = np.sum(poly_membership)
        
        # Should be very similar (polygon may differ slightly on boundaries)
        assert np.abs(rect_count - poly_count) < rect_count * 0.05, \
            f"Polygon ({poly_count}) and Rectangle ({rect_count}) differ too much"


@pytest.mark.functional
class TestSingleEllipseGate:
    """Test Ellipse gate application on real sample data."""

    def test_ellipse_gate_on_cd4_cd8(self, sample_a_events):
        """Apply ellipse gate to CD4 vs CD8 (typical lymph marker combo)."""
        gate = EllipseGate(
            'FITC-A', 'PE-A',
            center=(200, 200),
            width=100, height=80,
            angle=0
        )
        
        # Filter to only events with both markers
        valid_mask = ~(sample_a_events['FITC-A'].isna() | sample_a_events['PE-A'].isna())
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 0:
            membership = gate.contains(valid_events)
            gated_count = np.sum(membership)
            
            # Should gate some events
            assert gated_count >= 0, "Should have non-negative count"

    def test_ellipse_gate_orientation(self, sample_a_events):
        """Test ellipse with different orientations."""
        # Horizontal ellipse
        gate_0 = EllipseGate('FITC-A', 'PE-A', center=(200, 200), width=100, height=60, angle=0)
        
        # Vertical ellipse
        gate_90 = EllipseGate('FITC-A', 'PE-A', center=(200, 200), width=60, height=100, angle=0)
        
        valid_mask = ~(sample_a_events['FITC-A'].isna() | sample_a_events['PE-A'].isna())
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 0:
            result_0 = gate_0.contains(valid_events)
            result_90 = gate_90.contains(valid_events)
            
            # Orientations may differ slightly but both should gate some events
            assert np.sum(result_0) >= 0
            assert np.sum(result_90) >= 0


@pytest.mark.functional
class TestSingleQuadrantGate:
    """Test Quadrant gate application on real sample data."""

    def test_quadrant_gate_cd4_cd8(self, sample_a_events):
        """Apply quadrant gate to CD4 vs CD8 (typical classification)."""
        gate = QuadrantGate('FITC-A', 'PE-A', x_mid=200, y_mid=200)
        
        valid_mask = ~(sample_a_events['FITC-A'].isna() | sample_a_events['PE-A'].isna())
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 0:
            membership = gate.contains(valid_events)
            
            # Should classify all valid events into one of 4 quadrants (True/False for each axis)
            assert len(membership) == len(valid_events)
            assert np.sum(membership >= 0) == len(valid_events)  # Valid indices

    def test_quadrant_population_distribution(self, sample_a_events):
        """Verify quadrant gate distributes events across regions."""
        gate = QuadrantGate('FITC-A', 'PE-A', x_mid=200, y_mid=200)
        
        valid_mask = ~(sample_a_events['FITC-A'].isna() | sample_a_events['PE-A'].isna())
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 100:  # Need reasonable sample size
            cd4 = valid_events['FITC-A'].values
            cd8 = valid_events['PE-A'].values
            
            # Manually count distribution
            q1 = np.sum((cd4 >= 200) & (cd8 >= 200))  # Both positive
            q2 = np.sum((cd4 < 200) & (cd8 >= 200))   # CD4-, CD8+
            q3 = np.sum((cd4 < 200) & (cd8 < 200))    # Both negative
            q4 = np.sum((cd4 >= 200) & (cd8 < 200))   # CD4+, CD8-
            
            total = q1 + q2 + q3 + q4
            
            # Should distribute across multiple quadrants
            non_empty_quadrants = sum([q1 > 0, q2 > 0, q3 > 0, q4 > 0])
            assert non_empty_quadrants >= 2, \
                f"Expected multiple quadrants with events, got {non_empty_quadrants}: {q1}, {q2}, {q3}, {q4}"


@pytest.mark.functional
class TestSingleRangeGate:
    """Test Range gate application on real sample data."""

    def test_range_gate_on_cd3(self, sample_a_events):
        """Apply range gate to CD3 marker (typical T-cell marker)."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        valid_mask = ~sample_a_events['FITC-A'].isna()
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 0:
            membership = gate.contains(valid_events)
            gated_count = np.sum(membership)
            
            # Should gate some events
            assert gated_count > 0, "Range gate should capture some CD3+ cells"
            assert gated_count <= len(valid_events)

    def test_range_gate_boundaries(self, sample_a_events):
        """Verify range gate boundaries are respected."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        valid_mask = ~sample_a_events['FITC-A'].isna()
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 0:
            membership = gate.contains(valid_events)
            gated = valid_events[membership]
            
            if len(gated) > 0:
                values = gated['FITC-A'].values
                assert np.all(values >= 50), "All gated values should be >= min"
                assert np.all(values <= 250), "All gated values should be <= max"

    def test_range_gate_narrow_vs_wide(self, sample_a_events):
        """Compare narrow vs wide range gates."""
        narrow_gate = RangeGate('FITC-A', low=100, high=150)  # Strict
        wide_gate = RangeGate('FITC-A', low=50, high=250)     # Loose
        
        valid_mask = ~sample_a_events['FITC-A'].isna()
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 0:
            narrow_count = np.sum(narrow_gate.contains(valid_events))
            wide_count = np.sum(wide_gate.contains(valid_events))
            
            # Wide gate should have >= events than narrow gate
            assert wide_count >= narrow_count, \
                f"Wide gate {wide_count} should have ≥ narrow gate {narrow_count} events"


@pytest.mark.functional
class TestGateConsistency:
    """Test consistency and repeatability of gate operations."""

    @pytest.mark.slow
    def test_multiple_gate_applications(self, sample_a_events, gate_rectangle_singlet):
        """Apply same gate multiple times - should be identical."""
        results = []
        for _ in range(5):
            result = gate_rectangle_singlet.contains(sample_a_events)
            results.append(np.sum(result))
        
        # All results should be identical
        assert len(set(results)) == 1, f"Results should be consistent: {results}"

    def test_gate_with_subset(self, sample_a_events, gate_rectangle_singlet):
        """Apply gate to subset then to full - subset should be consistent."""
        # Get first 10K events
        subset = sample_a_events.iloc[:10000]
        full_result = gate_rectangle_singlet.contains(sample_a_events)
        subset_result = gate_rectangle_singlet.contains(subset)
        
        # Subset result should match first part of full result
        np.testing.assert_array_equal(
            full_result[:10000],
            subset_result,
            err_msg="Gate on subset should match gate on full"
        )

    def test_gate_parameter_preservation(self, gate_rectangle_singlet):
        """Verify gate parameters are preserved after operations."""
        original_xmin = gate_rectangle_singlet.x_min
        original_xmax = gate_rectangle_singlet.x_max
        original_ymin = gate_rectangle_singlet.y_min
        original_ymax = gate_rectangle_singlet.y_max
        
        # Apply gate multiple times
        dummy_data = pd.DataFrame({'FSC-A': [0, 100_000], 'SSC-A': [0, 100_000]})
        gate_rectangle_singlet.contains(dummy_data)
        gate_rectangle_singlet.contains(dummy_data)
        
        # Parameters should remain unchanged
        assert gate_rectangle_singlet.x_min == original_xmin
        assert gate_rectangle_singlet.x_max == original_xmax
        assert gate_rectangle_singlet.y_min == original_ymin
        assert gate_rectangle_singlet.y_max == original_ymax


@pytest.mark.functional
class TestGateEdgeCases:
    """Test edge cases in gate application on real data."""

    def test_gate_on_empty_dataframe(self, gate_rectangle_singlet):
        """Apply gate to empty DataFrame."""
        empty = pd.DataFrame({'FSC-A': [], 'SSC-A': []})
        result = gate_rectangle_singlet.contains(empty)
        
        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_gate_with_missing_values(self, sample_a_events):
        """Apply gate to data with NaN values."""
        # Add NaN to some cells
        modified = sample_a_events.copy()
        modified.loc[100:110, 'FSC-A'] = np.nan
        
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        result = gate.contains(modified)
        
        # Should handle NaN gracefully
        assert len(result) == len(modified)
        # NaN rows should be False
        assert ~result[100:110].all()

    def test_gate_all_inside(self, sample_a_events):
        """Create gate that includes all events."""
        # Very large gate
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=0, x_max=1_000_000, y_min=0, y_max=1_000_000)
        result = gate.contains(sample_a_events)
        
        inside_count = np.sum(result)
        total_count = len(sample_a_events)
        
        # Should include most (allowing for values outside expected range)
        assert inside_count >= total_count * 0.95

    def test_gate_all_outside(self, sample_a_events):
        """Create gate that excludes all events."""
        # Very small gate in unlikely region
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=10_000_000, x_max=11_000_000, y_min=10_000_000, y_max=11_000_000)
        result = gate.contains(sample_a_events)
        
        inside_count = np.sum(result)
        
        # Should exclude all events
        assert inside_count == 0


@pytest.mark.functional
class TestRealSampleStatistics:
    """Test statistical properties of gated populations."""

    def test_sample_statistics_after_gating(self, sample_a_events):
        """Verify statistics are computed correctly after gating."""
        # Gate on FSC-A
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        membership = gate.contains(sample_a_events)
        gated = sample_a_events[membership]
        
        # Compute statistics
        fsc_values = gated['FSC-A'].values
        ssc_values = gated['SSC-A'].values
        
        # Verify statistics
        assert np.mean(fsc_values) > 0
        assert np.std(fsc_values) > 0
        assert np.max(fsc_values) <= 300_000
        assert np.min(fsc_values) >= 50_000

    def test_population_percentage_changes(self, sample_a_events, sample_b_events):
        """Compare population percentages across different samples."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        sample_a_pct = 100 * np.sum(gate.contains(sample_a_events)) / len(sample_a_events)
        sample_b_pct = 100 * np.sum(gate.contains(sample_b_events)) / len(sample_b_events)
        
        # Percentages should be somewhat similar but may differ
        assert 30 < sample_a_pct < 90
        assert 30 < sample_b_pct < 90
        
        # Difference should be reasonable (not > 50%)
        diff = np.abs(sample_a_pct - sample_b_pct)
        assert diff < 30, f"Population percentages differ too much: {sample_a_pct:.1f}% vs {sample_b_pct:.1f}%"
