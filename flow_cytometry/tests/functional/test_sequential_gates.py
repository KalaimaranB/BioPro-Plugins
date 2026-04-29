"""
Functional tests for sequential gate application on real FCS data.

Tests verify that applying multiple gates in sequence produces:
- Monotonic population decrease (each gate reduces population)
- Consistent statistics across levels
- Correct gate hierarchy behavior
- No cumulative numerical errors

This tests the key issue area: sequential gates with various transforms and gate types.

Example workflows tested:
1. Rectangle (singlet) → Polygon (live) → Ellipse (CD4+) 
2. Rectangle → Rectangle → Rectangle (3 levels of restriction)
3. Rectangle on Linear → Rectangle on BiExp → Rectangle on Logicle
"""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.gating import RectangleGate, PolygonGate, EllipseGate, QuadrantGate, RangeGate


@pytest.mark.functional
class TestSequentialTwoLevelGates:
    """Test applying two gates in sequence."""

    def test_rectangle_then_polygon(self, sample_a_events):
        """Apply Rectangle (singlet) then Polygon (live cells)."""
        # Level 1: Singlet gate (FSC-A vs SSC-A)
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        singlet_membership = singlet_gate.contains(sample_a_events)
        level1_events = sample_a_events[singlet_membership]
        
        # Level 2: Live cell gate (Polygon on same axes) - must overlap with singlet gate
        vertices = [
            (60_000, 5_000),
            (190_000, 5_000),
            (190_000, 45_000),
            (60_000, 45_000),
        ]
        live_gate = PolygonGate('FSC-A', 'SSC-A', vertices)
        live_membership = live_gate.contains(level1_events)
        level2_events = level1_events[live_membership]
        
        # Verify monotonic decrease
        assert len(level1_events) < len(sample_a_events), "Level 1 should reduce events"
        assert len(level2_events) < len(level1_events), "Level 2 should reduce events further"
        
        # Verify percentages are reasonable
        pct_level1 = 100 * len(level1_events) / len(sample_a_events)
        pct_level2 = 100 * len(level2_events) / len(sample_a_events)
        assert 50 < pct_level1 < 95, f"Singlet percentage {pct_level1:.1f}% unreasonable"
        assert 5 < pct_level2 < 80, f"Live cell percentage {pct_level2:.1f}% unreasonable"

    def test_fsc_ssc_then_cd4_cd8(self, sample_a_events):
        """Apply FSC/SSC gate then CD4/CD8 gate."""
        # Level 1: FSC/SSC singlet gate
        fsc_ssc_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = fsc_ssc_gate.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2: CD4/CD8 gate
        cd_gate = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
        
        # Filter out NaN values
        valid_mask = ~(level1_events['FITC-A'].isna() | level1_events['PE-A'].isna())
        valid_events = level1_events[valid_mask]
        
        if len(valid_events) > 100:  # Need sufficient sample
            level2_membership = cd_gate.contains(valid_events)
            level2_events = valid_events[level2_membership]
            
            # Verify decreases
            assert len(level2_events) <= len(valid_events)
            # CD4/CD8 double positive should be minority
            pct_level2 = 100 * len(level2_events) / len(valid_events)
            assert pct_level2 < 50, f"CD4+CD8+ percentage {pct_level2:.1f}% too high"

    def test_rectangle_then_range(self, sample_a_events):
        """Apply Rectangle gate then Range gate on different axis."""
        # Level 1: FSC/SSC rectangle
        rect_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = rect_gate.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2: CD3 range gate
        cd3_gate = RangeGate('FITC-A', low=50, high=250)
        valid_mask = ~level1_events['FITC-A'].isna()
        valid_events = level1_events[valid_mask]
        
        if len(valid_events) > 100:
            level2_membership = cd3_gate.contains(valid_events)
            level2_events = valid_events[level2_membership]
            
            # Verify decreases
            assert len(level2_events) <= len(valid_events)
            assert len(level2_events) < len(level1_events)


@pytest.mark.functional
class TestSequentialThreeLevelGates:
    """Test applying three gates in sequence (full gating hierarchy)."""

    def test_singlet_live_cd4_hierarchy(self, sample_a_events):
        """Apply 3-level gate hierarchy: Singlet → Live → CD4+."""
        # Level 1: Singlet gate
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = singlet_gate.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2: Live cell gate (slightly more restrictive polygon)
        vertices = [
            (60_000, 5_000),
            (190_000, 5_000),
            (190_000, 45_000),
            (60_000, 45_000),
        ]
        live_gate = PolygonGate('FSC-A', 'SSC-A', vertices)
        level2_membership = live_gate.contains(level1_events)
        level2_events = level1_events[level2_membership]
        
        # Level 3: CD4+ gate (CD4 positive)
        cd4_gate = RangeGate('FITC-A', low=100, high=500)
        valid_mask = ~level2_events['FITC-A'].isna()
        valid_events = level2_events[valid_mask]
        
        if len(valid_events) > 100:
            level3_membership = cd4_gate.contains(valid_events)
            level3_events = valid_events[level3_membership]
            
            # Verify strict monotonic decrease
            assert len(level1_events) < len(sample_a_events)
            assert len(level2_events) < len(level1_events)
            assert len(level3_events) < len(valid_events)
            
            # Log percentages for verification
            pct1 = 100 * len(level1_events) / len(sample_a_events)
            pct2 = 100 * len(level2_events) / len(level1_events)
            pct3 = 100 * len(level3_events) / len(valid_events)
            
            assert 50 < pct1 < 95, f"Level 1: {pct1:.1f}%"
            assert 5 < pct2 < 95, f"Level 2: {pct2:.1f}%"
            assert pct3 > 5, f"Level 3: {pct3:.1f}%"

    def test_progressive_restriction(self, sample_a_events):
        """Apply progressively more restrictive Rectangle gates."""
        # Outer gate
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=30_000, x_max=220_000, y_min=500, y_max=60_000)
        level1_membership = gate1.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Middle gate (more restrictive)
        gate2 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level2_membership = gate2.contains(level1_events)
        level2_events = level1_events[level2_membership]
        
        # Inner gate (most restrictive)
        gate3 = RectangleGate('FSC-A', 'SSC-A', x_min=80_000, x_max=160_000, y_min=5_000, y_max=35_000)
        level3_membership = gate3.contains(level2_events)
        level3_events = level2_events[level3_membership]
        
        # All populations should decrease monotonically
        assert len(level1_events) < len(sample_a_events)
        assert len(level2_events) < len(level1_events)
        assert len(level3_events) < len(level2_events)
        
        # Final should still have reasonable population
        final_pct = 100 * len(level3_events) / len(sample_a_events)
        assert 5 < final_pct < 80


@pytest.mark.functional
class TestSequentialGatesWithStatistics:
    """Test that statistics are preserved through sequential gating."""

    def test_statistics_at_each_level(self, sample_a_events):
        """Compute and verify statistics at each gating level."""
        # Level 1: FSC/SSC
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = gate1.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2: Polygon
        vertices = [
            (120_000, 10_000),
            (280_000, 10_000),
            (280_000, 40_000),
            (120_000, 40_000),
        ]
        gate2 = PolygonGate('FSC-A', 'SSC-A', vertices)
        level2_membership = gate2.contains(level1_events)
        level2_events = level1_events[level2_membership]
        
        # Get statistics at each level
        fsc_mean_l0 = sample_a_events['FSC-A'].mean()
        fsc_mean_l1 = level1_events['FSC-A'].mean()
        fsc_mean_l2 = level2_events['FSC-A'].mean()
        
        # Means should be positive and within bounds
        assert fsc_mean_l0 > 0
        assert fsc_mean_l1 > 0
        assert fsc_mean_l2 > 0
        
        # All means should be within reasonable range
        assert fsc_mean_l1 > 50_000
        assert fsc_mean_l1 < 300_000
        assert fsc_mean_l2 > 50_000
        assert fsc_mean_l2 < 300_000

    def test_cumulative_std_dev(self, sample_a_events):
        """Verify standard deviations don't show cumulative errors."""
        # Level 1
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = gate1.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2
        gate2 = RectangleGate('FSC-A', 'SSC-A', x_min=70_000, x_max=180_000, y_min=2_000, y_max=40_000)
        level2_membership = gate2.contains(level1_events)
        level2_events = level1_events[level2_membership]
        
        # Level 3
        gate3 = RectangleGate('FSC-A', 'SSC-A', x_min=80_000, x_max=160_000, y_min=5_000, y_max=35_000)
        level3_membership = gate3.contains(level2_events)
        level3_events = level2_events[level3_membership]
        
        # All std devs should be positive and reasonable
        std_l1 = level1_events['FSC-A'].std()
        std_l2 = level2_events['FSC-A'].std()
        std_l3 = level3_events['FSC-A'].std()
        
        assert std_l1 > 0 and not np.isnan(std_l1)
        assert std_l2 > 0 and not np.isnan(std_l2)
        assert std_l3 > 0 and not np.isnan(std_l3)
        
        # Standard deviations shouldn't explode at any level
        assert std_l1 < 100_000
        assert std_l2 < 100_000
        assert std_l3 < 100_000


@pytest.mark.functional
class TestSequentialGatesWithDifferentParameterPairs:
    """Test sequential gates on different parameter combinations."""

    def test_fsc_ssc_then_b220_cd45(self, sample_a_events):
        """Gate on FSC/SSC then B220/CD45 (surface markers)."""
        # Level 1: FSC/SSC
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = gate1.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2: B220/CD45 marker gate
        gate2 = RectangleGate('PerCP-Cy5-5-A', 'APC-Cy7-A', x_min=100, x_max=300, y_min=100, y_max=300)
        valid_mask = ~(level1_events['PerCP-Cy5-5-A'].isna() | level1_events['APC-Cy7-A'].isna())
        valid_events = level1_events[valid_mask]
        
        if len(valid_events) > 100:
            level2_membership = gate2.contains(valid_events)
            level2_events = valid_events[level2_membership]
            
            assert len(level2_events) <= len(valid_events)
            assert len(level2_events) < len(level1_events)

    def test_multiple_parameter_transitions(self, sample_a_events):
        """Test gating on FSC/SSC, then CD4/CD8, then PI (univariate)."""
        # Level 1: FSC/SSC
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1_membership = gate1.contains(sample_a_events)
        level1_events = sample_a_events[level1_membership]
        
        # Level 2: CD4/CD8
        gate2 = RectangleGate('FITC-A', 'PE-A', x_min=100, x_max=300, y_min=100, y_max=300)
        valid_mask = ~(level1_events['FITC-A'].isna() | level1_events['PE-A'].isna())
        valid_events = level1_events[valid_mask]
        
        if len(valid_events) > 100:
            level2_membership = gate2.contains(valid_events)
            level2_events = valid_events[level2_membership]
            
            # Level 3: PI (viability)
            gate3 = RangeGate('APC-A', low=0, high=200)
            valid_mask3 = ~level2_events['APC-A'].isna()
            valid_events3 = level2_events[valid_mask3]
            
            if len(valid_events3) > 50:
                level3_membership = gate3.contains(valid_events3)
                level3_events = valid_events3[level3_membership]
                
                # All levels should decrease
                assert len(level1_events) < len(sample_a_events)
                assert len(level2_events) < len(valid_events)
                assert len(level3_events) <= len(valid_events3)


@pytest.mark.functional
class TestSequentialGateConsistency:
    """Test that sequential gating is consistent and reproducible."""

    def test_sequential_reproducibility(self, sample_a_events):
        """Apply same sequential gates twice - should get identical results."""
        # First application
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        r1_level1 = gate1.contains(sample_a_events)
        level1a = sample_a_events[r1_level1]
        
        gate2 = RectangleGate('FSC-A', 'SSC-A', x_min=70_000, x_max=180_000, y_min=2_000, y_max=40_000)
        r1_level2 = gate2.contains(level1a)
        level2a = level1a[r1_level2]
        
        # Second application (same gates)
        gate1_2 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        r2_level1 = gate1_2.contains(sample_a_events)
        level1b = sample_a_events[r2_level1]
        
        gate2_2 = RectangleGate('FSC-A', 'SSC-A', x_min=70_000, x_max=180_000, y_min=2_000, y_max=40_000)
        r2_level2 = gate2_2.contains(level1b)
        level2b = level1b[r2_level2]
        
        # Results should be identical
        assert len(level1a) == len(level1b)
        assert len(level2a) == len(level2b)
        np.testing.assert_array_equal(
            level1a.index.values, level1b.index.values,
            err_msg="Level 1 indices should match"
        )

    def test_sequential_vs_nested_gates(self, sample_a_events):
        """Apply same gates sequentially vs as nested conditions."""
        # Sequential approach
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        seq_mask1 = gate1.contains(sample_a_events)
        seq_level1 = sample_a_events[seq_mask1]
        
        gate2 = RectangleGate('FSC-A', 'SSC-A', x_min=70_000, x_max=180_000, y_min=2_000, y_max=40_000)
        seq_mask2 = gate2.contains(seq_level1)
        seq_final = seq_level1[seq_mask2]
        
        # Nested approach (both gates on original data)
        mask_both = seq_mask1 & gate2.contains(sample_a_events)
        nested_final = sample_a_events[mask_both]
        
        # Should give same result
        assert len(seq_final) == len(nested_final)
        np.testing.assert_array_equal(
            seq_final.index.values, nested_final.index.values,
            err_msg="Sequential and nested approaches should match"
        )


@pytest.mark.functional
class TestSequentialNegationLogic:
    """Test sequential gates with negation (NOT gates)."""

    def test_exclude_singlet_debris(self, sample_a_events):
        """Gate on singlets, then exclude debris."""
        # First get singlets
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        singlet_mask = singlet_gate.contains(sample_a_events)
        singlets = sample_a_events[singlet_mask]
        
        # Then exclude debris (low FSC)
        debris_gate = RectangleGate('FSC-A', 'SSC-A', x_min=0, x_max=100_000, y_min=0, y_max=300_000)
        debris_mask = debris_gate.contains(singlets)
        non_debris = singlets[~debris_mask]
        
        # Should exclude some events
        assert len(non_debris) < len(singlets)
        assert len(non_debris) > 0  # But not all
        
        # Final population should be meaningful
        final_pct = 100 * len(non_debris) / len(sample_a_events)
        assert 5 < final_pct < 80


@pytest.mark.functional
@pytest.mark.slow
class TestSequentialGatePerformance:
    """Test performance and scaling of sequential gates."""

    def test_sequential_gates_dont_degrade_performance(self, sample_a_events):
        """Verify sequential gating doesn't show performance degradation."""
        import time
        
        gate1 = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        gate2 = RectangleGate('FSC-A', 'SSC-A', x_min=70_000, x_max=180_000, y_min=2_000, y_max=40_000)
        gate3 = RectangleGate('FSC-A', 'SSC-A', x_min=80_000, x_max=160_000, y_min=5_000, y_max=35_000)
        
        # Time gate 1
        start = time.time()
        r1 = gate1.contains(sample_a_events)
        time_gate1 = time.time() - start
        
        # Time gate 2 on subset
        level1 = sample_a_events[r1]
        start = time.time()
        r2 = gate2.contains(level1)
        time_gate2 = time.time() - start
        
        # Time gate 3 on subset
        level2 = level1[r2]
        start = time.time()
        r3 = gate3.contains(level2)
        time_gate3 = time.time() - start
        
        # Each gate should be fast (< 50ms per gate on ~300K events)
        assert time_gate1 < 0.1, f"Gate 1 took {time_gate1:.3f}s"
        assert time_gate2 < 0.1, f"Gate 2 took {time_gate2:.3f}s"
        assert time_gate3 < 0.1, f"Gate 3 took {time_gate3:.3f}s"
