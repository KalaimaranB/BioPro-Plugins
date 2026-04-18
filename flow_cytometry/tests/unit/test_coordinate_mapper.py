"""Unit tests for CoordinateMapper service.

Tests coordinate transformation logic independently from UI/matplotlib.
"""

import pytest
import numpy as np
from flow_cytometry.ui.graph.flow_services import CoordinateMapper
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.scaling import AxisScale


class TestCoordinateMapperLinear:
    """Test CoordinateMapper with linear transforms."""
    
    @pytest.mark.unit
    def test_linear_transform_identity(self, coordinate_mapper_linear):
        """Linear transform should be identity (no change)."""
        x = np.array([0, 100, 1000])
        result = coordinate_mapper_linear.transform_x(x)
        np.testing.assert_array_almost_equal(result, x)
    
    @pytest.mark.unit
    def test_linear_inverse_identity(self, coordinate_mapper_linear):
        """Linear inverse should be identity."""
        x = np.array([0, 100, 1000])
        result = coordinate_mapper_linear.inverse_transform_x(x)
        np.testing.assert_array_almost_equal(result, x)
    
    @pytest.mark.unit
    def test_linear_round_trip(self, coordinate_mapper_linear):
        """Transform → inverse should restore original values."""
        x = np.array([0, 50, 100, 500, 1000])
        transformed = coordinate_mapper_linear.transform_x(x)
        restored = coordinate_mapper_linear.inverse_transform_x(transformed)
        np.testing.assert_array_almost_equal(restored, x)
    
    @pytest.mark.unit
    def test_linear_handles_negative(self, coordinate_mapper_linear):
        """Linear transform should handle negative values."""
        x = np.array([-100, -50, 0, 50, 100])
        result = coordinate_mapper_linear.transform_x(x)
        np.testing.assert_array_almost_equal(result, x)
    
    @pytest.mark.unit
    def test_linear_handles_large_values(self, coordinate_mapper_linear):
        """Linear transform should handle large values."""
        x = np.array([1e6, 1e7, 1e8])
        result = coordinate_mapper_linear.transform_x(x)
        np.testing.assert_array_almost_equal(result, x)


class TestCoordinateMapperBiexponential:
    """Test CoordinateMapper with biexponential transforms."""
    
    @pytest.mark.unit
    def test_biexp_positive_values(self, coordinate_mapper_biexp):
        """BiExp transform should handle positive values."""
        x = np.array([0, 100, 1000, 10000])
        result = coordinate_mapper_biexp.transform_x(x)
        # Should be monotonically increasing
        assert np.all(np.diff(result) >= 0), "BiExp transform not monotonic"
    
    @pytest.mark.unit
    def test_biexp_inverse_round_trip(self, coordinate_mapper_biexp):
        """BiExp transform → inverse should restore original within dithering tolerance."""
        # Note: BiExp adds ±0.5 dithering for density calculations, so precision is limited
        x = np.array([100, 500, 1000, 5000, 10000])
        transformed = coordinate_mapper_biexp.transform_x(x)
        restored = coordinate_mapper_biexp.inverse_transform_x(transformed)
        np.testing.assert_array_almost_equal(restored, x, decimal=0)
    
    @pytest.mark.unit
    def test_biexp_zero_input(self, coordinate_mapper_biexp):
        """BiExp should handle zero input."""
        x = np.array([0])
        result = coordinate_mapper_biexp.transform_x(x)
        assert np.isfinite(result[0]), "BiExp of zero should be finite"
    
    @pytest.mark.unit
    def test_biexp_at_scale_top(self, coordinate_mapper_biexp):
        """BiExp at scale.logicle_t should be at top of scale."""
        scale = AxisScale(TransformType.BIEXPONENTIAL)
        scale.logicle_m = 5.0
        scale.logicle_w = 1.0
        scale.logicle_t = 262144.0
        scale.logicle_a = 0.0
        
        mapper = CoordinateMapper(scale, scale)
        x = np.array([scale.logicle_t])
        result = mapper.transform_x(x)
        
        # At top value, transform should give high output (near maximum in normalized scale)
        assert result[0] > 0.95, f"BiExp at T should be near maximum, got {result[0]}"
    
    @pytest.mark.unit
    def test_biexp_parameter_sensitivity(self):
        """Different BiExp parameters should give different results."""
        scale1 = AxisScale(TransformType.BIEXPONENTIAL)
        scale1.logicle_m = 5.0
        scale1.logicle_w = 1.0
        scale1.logicle_t = 262144.0
        scale1.logicle_a = 0.0
        
        scale2 = AxisScale(TransformType.BIEXPONENTIAL)
        scale2.logicle_m = 4.0  # Different M
        scale2.logicle_w = 1.0
        scale2.logicle_t = 262144.0
        scale2.logicle_a = 0.0
        
        mapper1 = CoordinateMapper(scale1, scale1)
        mapper2 = CoordinateMapper(scale2, scale2)
        
        x = np.array([1000])
        result1 = mapper1.transform_x(x)
        result2 = mapper2.transform_x(x)
        
        # Different parameters should give different results
        assert result1[0] != result2[0], "Different parameters should give different results"


class TestCoordinateMapperUpdateScales:
    """Test updating scales in mapper."""
    
    @pytest.mark.unit
    def test_update_scales_linear_to_biexp(self):
        """Update from linear to biexp should change transform."""
        scale_linear = AxisScale(TransformType.LINEAR)
        mapper = CoordinateMapper(scale_linear, scale_linear)
        
        x = np.array([1000])
        result_linear = mapper.transform_x(x)
        
        scale_biexp = AxisScale(TransformType.BIEXPONENTIAL)
        scale_biexp.logicle_m = 5.0
        scale_biexp.logicle_w = 1.0
        scale_biexp.logicle_t = 262144.0
        scale_biexp.logicle_a = 0.0
        
        mapper.update_scales(scale_biexp, scale_biexp)
        result_biexp = mapper.transform_x(x)
        
        # Results should be different
        assert result_linear[0] != result_biexp[0]


class TestCoordinateMapperPointTransforms:
    """Test point-based transform methods."""
    
    @pytest.mark.unit
    def test_transform_point_linear(self, coordinate_mapper_linear):
        """Transform single point with linear scale."""
        x, y = 100, 200
        result_x, result_y = coordinate_mapper_linear.transform_point(x, y)
        
        assert result_x == x, "Linear x should be unchanged"
        assert result_y == y, "Linear y should be unchanged"
    
    @pytest.mark.unit
    def test_transform_point_and_array_consistent(self, coordinate_mapper_biexp):
        """Transform point should match array transform."""
        x, y = 5000, 3000
        
        # Point version
        pt_x, pt_y = coordinate_mapper_biexp.transform_point(x, y)
        
        # Array version
        arr_x = coordinate_mapper_biexp.transform_x(np.array([x]))[0]
        arr_y = coordinate_mapper_biexp.transform_y(np.array([y]))[0]
        
        np.testing.assert_almost_equal(pt_x, arr_x, decimal=5)
        np.testing.assert_almost_equal(pt_y, arr_y, decimal=5)


class TestCoordinateMapperEdgeCases:
    """Test edge cases and robustness."""
    
    @pytest.mark.unit
    def test_nan_input(self, coordinate_mapper_linear):
        """Handle NaN in input array."""
        x = np.array([100, np.nan, 300])
        result = coordinate_mapper_linear.transform_x(x)
        
        assert np.isfinite(result[0]), "Finite input should give finite output"
        assert np.isnan(result[1]), "NaN input should give NaN output"
        assert np.isfinite(result[2]), "Finite input should give finite output"
    
    @pytest.mark.unit
    def test_inf_input(self, coordinate_mapper_linear):
        """Handle inf in input array."""
        x = np.array([100, np.inf, 300])
        result = coordinate_mapper_linear.transform_x(x)
        
        assert np.isfinite(result[0]), "Finite input should be finite"
        # Inf handling depends on transform, just check it doesn't crash
        assert len(result) == 3, "Should return same length"
    
    @pytest.mark.unit
    def test_empty_array(self, coordinate_mapper_linear):
        """Handle empty array."""
        x = np.array([])
        result = coordinate_mapper_linear.transform_x(x)
        assert len(result) == 0, "Empty input should give empty output"
    
    @pytest.mark.unit
    def test_single_value(self, coordinate_mapper_biexp):
        """Handle single value array."""
        x = np.array([5000])
        result = coordinate_mapper_biexp.transform_x(x)
        assert len(result) == 1, "Single value should give single value"
        assert np.isfinite(result[0]), "Output should be finite"
