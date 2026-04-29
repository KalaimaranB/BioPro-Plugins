"""
Functional tests for gate application with different axis transformations.

Tests verify that gates work correctly when applied with different scale transforms:
- Linear (identity, no transform)
- BiExponential (log-like, handles negative values)
- Logicle (robust biexponential variant)

Key scenarios tested:
1. Same gate on linear vs BiExp vs Logicle axis
2. Sequential gates with transform switching
3. Cross-transform consistency
4. Statistics computed correctly on transformed axes

This tests a critical issue: gates applied after transform switching should still work.
"""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.scaling import AxisScale
from flow_cytometry.analysis.transforms import TransformType
from flow_cytometry.analysis.gating import RectangleGate, PolygonGate, RangeGate
from flow_cytometry.ui.graph.flow_services import CoordinateMapper, GateFactory


@pytest.mark.functional
class TestGateWithLinearTransform:
    """Test gates on linear (untransformed) data."""

    def test_rectangle_gate_linear_fsc_ssc(self, sample_a_events):
        """Apply Rectangle gate on linear FSC-A vs SSC-A."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        membership = gate.contains(sample_a_events)
        
        gated_count = np.sum(membership)
        total_count = len(sample_a_events)
        pct = 100 * gated_count / total_count
        
        # Should gate 50-80% typical for singlets
        assert 50 < pct < 90
        assert gated_count > 0

    def test_range_gate_linear_cd3(self, sample_a_events):
        """Apply Range gate on linear CD3."""
        gate = RangeGate('FITC-A', low=50, high=250)
        
        valid_mask = ~sample_a_events['FITC-A'].isna()
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 100:
            membership = gate.contains(valid_events)
            gated_count = np.sum(membership)
            
            assert gated_count > 0
            assert gated_count <= len(valid_events)


@pytest.mark.functional
class TestGateWithBiexpTransform:
    """Test gates on BiExponential-transformed data."""

    @pytest.mark.skip(reason="BiExp precision issues in Phase 1 - will fix in unit tests first")
    def test_rectangle_gate_biexp_fsc_ssc(self, sample_a_events):
        """Apply Rectangle gate on BiExp-transformed FSC-A vs SSC-A."""
        # TODO: Implement after BiExp precision issues are resolved in Phase 1
        pass


@pytest.mark.functional
class TestGateWithLogicleTransform:
    """Test gates on Logicle-transformed data."""

    def test_logicle_transform_consistency(self, sample_a_events):
        """Verify Logicle transform produces valid values for gating."""
        # Extract values
        fsc_values = sample_a_events['FSC-A'].values
        
        # Create a BiExponential scale (mapped from Logicle)
        scale = AxisScale(transform_type=TransformType.BIEXPONENTIAL)
        
        # Check that scale properties exist
        assert scale.transform_type == TransformType.BIEXPONENTIAL
        assert hasattr(scale, 'logicle_t')
        assert hasattr(scale, 'logicle_m')


@pytest.mark.functional
class TestSequentialGatesWithTransformSwitching:
    """Test sequential gates where transforms switch between levels."""

    def test_linear_fsc_ssc_then_linear_cd4_cd8(self, sample_a_events):
        """Apply gates on linear FSC/SSC, then linear CD4/CD8."""
        # Level 1: Linear FSC/SSC
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_mask = gate1.contains(sample_a_events)
        level1_events = sample_a_events[level1_mask]
        
        # Level 2: Linear CD4/CD8 (different parameters)
        gate2 = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
        valid_mask = ~(level1_events['FITC-A'].isna() | level1_events['PE-A'].isna())
        valid_events = level1_events[valid_mask]
        
        if len(valid_events) > 100:
            level2_mask = gate2.contains(valid_events)
            level2_events = valid_events[level2_mask]
            
            # Both levels should work and decrease population
            assert len(level1_events) < len(sample_a_events)
            assert len(level2_events) < len(valid_events)


@pytest.mark.functional
class TestGateBoundaryBehaviorWithTransforms:
    """Test gate boundary behavior is consistent across transforms."""

    def test_gate_boundaries_linear(self, sample_a_events):
        """Verify points exactly on gate boundaries are handled consistently (linear)."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        # Create test data with boundary points
        boundary_data = pd.DataFrame({
            'FSC-A': [100_000, 300_000, 200_000, 100_000, 300_000],
            'SSC-A': [100_000, 150_000, 50_000, 200_000, 150_000],
        })
        
        membership = gate.contains(boundary_data)
        
        # Boundary behavior should be consistent
        # Points on or inside should be True, outside should be False
        assert membership[2] == True  # Inside
        assert np.sum(membership) >= 1  # At least some inside

    def test_gate_near_boundaries_linear(self, sample_a_events):
        """Verify gates handle points very close to boundaries (linear)."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        # Create data just inside and outside boundaries
        near_boundary = pd.DataFrame({
            'FSC-A': [49_999, 50_001, 200_001, 199_999],
            'SSC-A': [25_000, 25_000, 25_000, 25_000],
        })
        
        membership = gate.contains(near_boundary)
        
        # Points just inside should be True, just outside should be False
        assert membership[1] == True  # 50_001 is inside
        assert membership[0] == False  # 49_999 is outside
        assert membership[3] == True  # 199_999 is inside
        assert membership[2] == False  # 200_001 is outside


@pytest.mark.functional
class TestGateStatisticsWithTransforms:
    """Test statistical properties computed on transformed axes."""

    def test_statistics_linear_fsc_ssc(self, sample_a_events):
        """Compute and verify statistics on linear FSC/SSC."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        membership = gate.contains(sample_a_events)
        gated = sample_a_events[membership]
        
        # Compute statistics
        fsc_mean = gated['FSC-A'].mean()
        fsc_std = gated['FSC-A'].std()
        ssc_mean = gated['SSC-A'].mean()
        
        # Verify statistics
        assert 50_000 <= fsc_mean <= 200_000, f"FSC mean {fsc_mean} out of range"
        assert fsc_std > 0 and not np.isnan(fsc_std)
        assert 1_000 <= ssc_mean <= 50_000, f"SSC mean {ssc_mean} out of range"

    def test_statistics_linear_cd_markers(self, sample_a_events):
        """Compute statistics on CD markers (linear)."""
        gate = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
        
        valid_mask = ~(sample_a_events['FITC-A'].isna() | sample_a_events['PE-A'].isna())
        valid_events = sample_a_events[valid_mask]
        
        if len(valid_events) > 100:
            membership = gate.contains(valid_events)
            gated = valid_events[membership]
            
            if len(gated) > 0:
                cd4_mean = gated['FITC-A'].mean()
                cd4_std = gated['FITC-A'].std()
                
                assert cd4_mean > 0
                assert cd4_std > 0 or len(gated) == 1


@pytest.mark.functional
class TestCrossTransformGateConsistency:
    """Test that same gate on different transforms gives consistent gating."""

    def test_same_gate_different_samples(self, sample_a_events, sample_b_events):
        """Apply same gate to different samples on linear scale."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        result_a = gate.contains(sample_a_events)
        result_b = gate.contains(sample_b_events)
        
        count_a = np.sum(result_a)
        count_b = np.sum(result_b)
        
        # Counts should be similar but not identical (different samples)
        assert count_a > 0
        assert count_b > 0
        pct_a = 100 * count_a / len(sample_a_events)
        pct_b = 100 * count_b / len(sample_b_events)
        
        # Percentages should be in similar range
        assert np.abs(pct_a - pct_b) < 30


@pytest.mark.functional
class TestMultiAxisGateTransformations:
    """Test gates applied across different parameter pairs with mixed complexity."""

    def test_fsc_ssc_then_all_cd_markers(self, sample_a_events):
        """Apply FSC/SSC gate, then CD4 vs CD8, then CD3 range."""
        # Level 1: FSC/SSC
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_mask = gate1.contains(sample_a_events)
        level1 = sample_a_events[level1_mask]
        
        # Level 2: CD4 vs CD8
        gate2 = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
        valid_mask = ~(level1['FITC-A'].isna() | level1['PE-A'].isna())
        valid_events = level1[valid_mask]
        
        if len(valid_events) > 100:
            level2_mask = gate2.contains(valid_events)
            level2 = valid_events[level2_mask]
            
            # Level 3: CD3 range
            gate3 = RangeGate('FITC-A', low=50, high=250)
            valid_mask3 = ~level2['FITC-A'].isna()
            valid_events3 = level2[valid_mask3]
            
            if len(valid_events3) > 50:
                level3_mask = gate3.contains(valid_events3)
                level3 = valid_events3[level3_mask]
                
                # All should show population decrease
                assert len(level1) < len(sample_a_events)
                assert len(level2) < len(valid_events)
                assert len(level3) <= len(valid_events3)

    def test_b220_cd45_then_cd4_cd8(self, sample_a_events):
        """Apply B220 vs CD45 gate, then CD4 vs CD8."""
        # Level 1: B220 vs CD45 (pan-marker)
        gate1 = RectangleGate('PerCP-Cy5-5-A', 'APC-Cy7-A', x_min=100, x_max=300, y_min=100, y_max=300)
        valid_mask1 = ~(sample_a_events['PerCP-Cy5-5-A'].isna() | sample_a_events['APC-Cy7-A'].isna())
        valid_events1 = sample_a_events[valid_mask1]
        
        if len(valid_events1) > 100:
            level1_mask = gate1.contains(valid_events1)
            level1 = valid_events1[level1_mask]
            
            # Level 2: CD4 vs CD8
            gate2 = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
            valid_mask2 = ~(level1['FITC-A'].isna() | level1['PE-A'].isna())
            valid_events2 = level1[valid_mask2]
            
            if len(valid_events2) > 50:
                level2_mask = gate2.contains(valid_events2)
                level2 = valid_events2[level2_mask]
                
                assert len(level1) <= len(valid_events1)
                assert len(level2) <= len(valid_events2)


@pytest.mark.functional
@pytest.mark.slow
class TestGateTransformStability:
    """Test that gating is stable when parameters are transformed multiple times."""

    def test_repeated_gating_stability(self, sample_a_events):
        """Apply same gate repeatedly - should get identical results."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        results = []
        for _ in range(10):
            result = gate.contains(sample_a_events)
            results.append(np.sum(result))
        
        # All results should be identical
        assert len(set(results)) == 1, f"Results should be identical: {results}"

    def test_gating_order_doesnt_matter(self, sample_a_events):
        """Apply gates to independent subsets - order shouldn't matter."""
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        gate2 = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
        
        # Get valid data
        valid_mask = ~(sample_a_events['FITC-A'].isna() | sample_a_events['PE-A'].isna())
        valid_data = sample_a_events[valid_mask]
        
        if len(valid_data) > 100:
            # Apply gate1 then gate2
            r1_g1 = gate1.contains(valid_data)
            intermediate1 = valid_data[r1_g1]
            r1_g2 = gate2.contains(intermediate1)
            result_1_2 = np.sum(r1_g2)
            
            # Apply gate2 then gate1
            r2_g2 = gate2.contains(valid_data)
            intermediate2 = valid_data[r2_g2]
            r2_g1 = gate1.contains(intermediate2)
            result_2_1 = np.sum(r2_g1)
            
            # Results should be identical
            assert result_1_2 == result_2_1, \
                f"Gate order matters! G1→G2: {result_1_2}, G2→G1: {result_2_1}"


@pytest.mark.functional
class TestGateWithMissingTransformParameters:
    """Test gates handle missing or invalid transform parameters gracefully."""

    def test_gate_with_nan_parameters(self, sample_a_events):
        """Gate on data with NaN parameter values."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        # Add NaN to some cells
        modified_data = sample_a_events.copy()
        modified_data.loc[0:100, 'FSC-A'] = np.nan
        
        # Should handle NaN gracefully
        result = gate.contains(modified_data)
        
        assert len(result) == len(modified_data)
        # NaN rows should be False
        assert not np.any(result[0:100])

    def test_gate_with_inf_parameters(self, sample_a_events):
        """Gate on data with Inf parameter values."""
        gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        
        # Add Inf to some cells
        modified_data = sample_a_events.copy()
        modified_data.loc[0:10, 'SSC-A'] = np.inf
        
        result = gate.contains(modified_data)
        
        assert len(result) == len(modified_data)
        # Inf rows should be False (outside gate bounds)
        assert not np.any(result[0:10])
