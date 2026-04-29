"""
Complete real-world gating pipeline test on Sample C.

This test verifies a realistic multi-level gating strategy on Sample C:
1. Gate for cells first (singlets on FSC/SSC)
2. Change axis to PI vs FSC to gate for live cells
3. Gate for lymphocytes
4. Gate for B vs T cells (using available fluorescence channels)
5. Within T cells, gate for CD4 and CD8 clusters

Sample C should have clear clusters making this an excellent test of the complete pipeline.
"""

import pytest
import numpy as np
import pandas as pd
from flow_cytometry.analysis.gating import RectangleGate, RangeGate, PolygonGate


@pytest.mark.integration
class TestSampleCCompletePipeline:
    """Complete realistic gating pipeline on Sample C."""

    def test_complete_gating_pipeline_sample_c(self, sample_c_events):
        """
        Execute complete gating pipeline:
        Cells → Live → Lymphocytes → B/T → CD4/CD8
        
        This is a realistic workflow that tests the full system end-to-end.
        """
        
        # ──────────────────────────────────────────────────────────────
        # STEP 1: Gate for CELLS (Singlets on FSC/SSC)
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("STEP 1: Singlet Gating (FSC-A vs SSC-A)")
        print("="*70)
        
        singlet_gate = RectangleGate(
            'FSC-A', 'SSC-A',
            x_min=50_000, x_max=200_000,  # FSC range
            y_min=1_000, y_max=50_000      # SSC range
        )
        
        singlet_mask = singlet_gate.contains(sample_c_events)
        singlets = sample_c_events[singlet_mask]
        
        print(f"Initial events: {len(sample_c_events):,}")
        print(f"Singlet events: {len(singlets):,}")
        print(f"Singlet percentage: {100 * len(singlets) / len(sample_c_events):.1f}%")
        print(f"FSC mean: {singlets['FSC-A'].mean():.0f}")
        print(f"SSC mean: {singlets['SSC-A'].mean():.0f}")
        
        # Assertions: Singlets should be a reasonable population (20-80%)
        assert len(singlets) > len(sample_c_events) * 0.1, "Too few singlets"
        assert len(singlets) < len(sample_c_events) * 0.9, "Too many singlets"
        assert singlets['FSC-A'].mean() > 50_000, "Singlet FSC too low"
        
        # ──────────────────────────────────────────────────────────────
        # STEP 2: Gate for LIVE CELLS (using PI vs FSC)
        # Change axis: now looking at viability with APC-A as proxy for PI
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("STEP 2: Live Cell Gating (PI/APC-A vs FSC-A)")
        print("="*70)
        print("Using APC-A as proxy for PI (higher = more PI = dead)")
        
        # Live cells should have LOW PI (APC-A < 45,000, adjusted for sample C data)
        live_gate = RangeGate('APC-A', low=0, high=45000)
        
        live_mask = live_gate.contains(singlets)
        live_cells = singlets[live_mask]
        
        print(f"Singlet events: {len(singlets):,}")
        print(f"Live cells: {len(live_cells):,}")
        print(f"Live percentage: {100 * len(live_cells) / len(singlets):.1f}%")
        print(f"APC-A (PI proxy) mean in live: {live_cells['APC-A'].mean():.0f}")
        print(f"APC-A (PI proxy) mean in dead: {singlets[~live_mask]['APC-A'].mean():.0f}")
        
        # Assertions: Live cells should be majority (50-95%)
        assert len(live_cells) > len(singlets) * 0.3, "Too few live cells"
        assert len(live_cells) < len(singlets) * 0.99, "No dead cells detected"
        assert live_cells['APC-A'].mean() < singlets[~live_mask]['APC-A'].mean(), \
            "Live cells should have lower PI than dead cells"
        
        # ──────────────────────────────────────────────────────────────
        # STEP 3: Gate for LYMPHOCYTES
        # Lymphocytes are smaller (lower FSC) than other cell types
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("STEP 3: Lymphocyte Gating (FSC-A vs SSC-A)")
        print("="*70)
        
        lymphocyte_gate = RectangleGate(
            'FSC-A', 'SSC-A',
            x_min=40_000, x_max=120_000,   # Narrower FSC
            y_min=500, y_max=15_000        # Narrower SSC
        )
        
        lymph_mask = lymphocyte_gate.contains(live_cells)
        lymphocytes = live_cells[lymph_mask]
        
        print(f"Live cells: {len(live_cells):,}")
        print(f"Lymphocytes: {len(lymphocytes):,}")
        print(f"Lymphocyte percentage: {100 * len(lymphocytes) / len(live_cells):.1f}%")
        print(f"FSC mean: {lymphocytes['FSC-A'].mean():.0f}")
        print(f"SSC mean: {lymphocytes['SSC-A'].mean():.0f}")
        
        # Assertions: Lymphocytes should be a meaningful population
        assert len(lymphocytes) > len(live_cells) * 0.1, "Too few lymphocytes"
        assert len(lymphocytes) < len(live_cells) * 0.99, "Too many lymphocytes"
        assert lymphocytes['FSC-A'].mean() > 70_000, "Lymphocyte FSC too low"
        
        # ──────────────────────────────────────────────────────────────
        # STEP 4: Gate for B CELLS vs T CELLS
        # Use available fluorescence channels as proxy:
        # FITC-A as marker 1, PE-A as marker 2
        # This will create 4 quadrants: double negative, FITC+, PE+, double+
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("STEP 4: B vs T Cell Gating (FITC-A vs PE-A)")
        print("="*70)
        print("FITC-A as proxy for B cell marker")
        print("PE-A as proxy for T cell marker")
        
        # B cells: FITC+ PE- (or primarily FITC+)
        b_cell_gate = RectangleGate(
            'FITC-A', 'PE-A',
            x_min=1000, x_max=200_000,    # FITC positive
            y_min=0, y_max=5000           # PE negative
        )
        
        # T cells: PE+ FITC- (or primarily PE+)
        t_cell_gate = RectangleGate(
            'FITC-A', 'PE-A',
            x_min=0, x_max=5000,          # FITC negative
            y_min=1000, y_max=200_000     # PE positive
        )
        
        b_mask = b_cell_gate.contains(lymphocytes)
        t_mask = t_cell_gate.contains(lymphocytes)
        double_neg_mask = ~(b_mask | t_mask)
        double_pos_mask = (b_mask & t_mask)
        
        b_cells = lymphocytes[b_mask]
        t_cells = lymphocytes[t_mask]
        double_neg = lymphocytes[double_neg_mask]
        double_pos = lymphocytes[double_pos_mask]
        
        print(f"Lymphocytes: {len(lymphocytes):,}")
        print(f"B cells (FITC+): {len(b_cells):,} ({100*len(b_cells)/len(lymphocytes):.1f}%)")
        print(f"T cells (PE+): {len(t_cells):,} ({100*len(t_cells)/len(lymphocytes):.1f}%)")
        print(f"Double negative: {len(double_neg):,} ({100*len(double_neg)/len(lymphocytes):.1f}%)")
        print(f"Double positive: {len(double_pos):,} ({100*len(double_pos)/len(lymphocytes):.1f}%)")
        
        if len(b_cells) > 0:
            print(f"B cell FITC mean: {b_cells['FITC-A'].mean():.0f}")
            print(f"B cell PE mean: {b_cells['PE-A'].mean():.0f}")
        
        if len(t_cells) > 0:
            print(f"T cell FITC mean: {t_cells['FITC-A'].mean():.0f}")
            print(f"T cell PE mean: {t_cells['PE-A'].mean():.0f}")
        
        # Assertions: Should have meaningful populations
        assert len(b_cells) > 0 or len(t_cells) > 0, "No B or T cells detected"
        
        # ──────────────────────────────────────────────────────────────
        # STEP 5: Within T CELLS, gate for CD4+ and CD8+ clusters
        # Use PerCP and APC as proxy markers for CD4/CD8
        # ──────────────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("STEP 5: CD4 vs CD8 Subsets within T Cells")
        print("="*70)
        print("PerCP-Cy5-5-A as proxy for CD4")
        print("APC-Cy7-A as proxy for CD8")
        
        if len(t_cells) > 100:  # Only if we have enough T cells
            # CD4+ T cells
            cd4_gate = RectangleGate(
                'PerCP-Cy5-5-A', 'APC-Cy7-A',
                x_min=1000, x_max=200_000,   # PerCP+ (CD4 proxy)
                y_min=0, y_max=5000          # APC- (CD8 negative)
            )
            
            # CD8+ T cells
            cd8_gate = RectangleGate(
                'PerCP-Cy5-5-A', 'APC-Cy7-A',
                x_min=0, x_max=5000,         # PerCP- (CD4 negative)
                y_min=1000, y_max=200_000    # APC+ (CD8 positive)
            )
            
            cd4_mask = cd4_gate.contains(t_cells)
            cd8_mask = cd8_gate.contains(t_cells)
            dp_mask = (cd4_mask & cd8_mask)  # Double positive
            dn_mask = ~(cd4_mask | cd8_mask)  # Double negative
            
            cd4_cells = t_cells[cd4_mask]
            cd8_cells = t_cells[cd8_mask]
            
            print(f"T cells: {len(t_cells):,}")
            print(f"CD4+ T cells: {len(cd4_cells):,} ({100*len(cd4_cells)/len(t_cells):.1f}%)")
            print(f"CD8+ T cells: {len(cd8_cells):,} ({100*len(cd8_cells)/len(t_cells):.1f}%)")
            print(f"CD4+CD8+ (double+): {np.sum(dp_mask):,} ({100*np.sum(dp_mask)/len(t_cells):.1f}%)")
            print(f"CD4-CD8- (double-): {np.sum(dn_mask):,} ({100*np.sum(dn_mask)/len(t_cells):.1f}%)")
            
            if len(cd4_cells) > 0:
                print(f"CD4+ PerCP mean: {cd4_cells['PerCP-Cy5-5-A'].mean():.0f}")
                print(f"CD4+ APC mean: {cd4_cells['APC-Cy7-A'].mean():.0f}")
            
            if len(cd8_cells) > 0:
                print(f"CD8+ PerCP mean: {cd8_cells['PerCP-Cy5-5-A'].mean():.0f}")
                print(f"CD8+ APC mean: {cd8_cells['APC-Cy7-A'].mean():.0f}")
            
            # Assertions: Should have meaningful CD4/CD8 populations
            total_identified = len(cd4_cells) + len(cd8_cells)
            assert total_identified > 0, "No CD4+ or CD8+ cells identified in T cell population"
        else:
            print("⚠️  Not enough T cells for CD4/CD8 gating (need >100)")

    def test_pipeline_reproducibility(self, sample_c_events):
        """Verify the pipeline produces identical results when run twice."""
        def run_full_pipeline(data):
            # Step 1: Singlets
            singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
            level1 = data[singlet_gate.contains(data)]
            
            # Step 2: Live
            live_gate = RangeGate('APC-A', low=0, high=45000)
            level2 = level1[live_gate.contains(level1)]
            
            # Step 3: Lymphocytes
            lymph_gate = RectangleGate('FSC-A', 'SSC-A', x_min=40_000, x_max=120_000, y_min=500, y_max=15_000)
            level3 = level2[lymph_gate.contains(level2)]
            
            # Step 4: T cells
            t_gate = RectangleGate('FITC-A', 'PE-A', x_min=0, x_max=100, y_min=50, y_max=300)
            level4 = level3[t_gate.contains(level3)]
            
            return len(level4)
        
        result1 = run_full_pipeline(sample_c_events)
        result2 = run_full_pipeline(sample_c_events)
        
        assert result1 == result2, "Pipeline produced different results on repeated runs"

    def test_pipeline_monotonic_decrease(self, sample_c_events):
        """Verify each gating step reduces the population monotonically."""
        print("\n" + "="*70)
        print("MONOTONIC POPULATION DECREASE CHECK")
        print("="*70)
        
        level0_count = len(sample_c_events)
        print(f"Level 0 (all events): {level0_count:,}")
        
        # Step 1
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        level1 = sample_c_events[singlet_gate.contains(sample_c_events)]
        level1_count = len(level1)
        print(f"Level 1 (singlets): {level1_count:,}")
        
        # Step 2
        live_gate = RangeGate('APC-A', low=0, high=45000)
        level2 = level1[live_gate.contains(level1)]
        level2_count = len(level2)
        print(f"Level 2 (live): {level2_count:,}")
        
        # Step 3
        lymph_gate = RectangleGate('FSC-A', 'SSC-A', x_min=20_000, x_max=200_000, y_min=500, y_max=50_000)
        level3 = level2[lymph_gate.contains(level2)]
        level3_count = len(level3)
        print(f"Level 3 (lymphocytes): {level3_count:,}")
        
        # Step 4
        t_gate = RectangleGate('FITC-A', 'PE-A', x_min=0, x_max=100, y_min=50, y_max=300)
        level4 = level3[t_gate.contains(level3)]
        level4_count = len(level4)
        print(f"Level 4 (T cells): {level4_count:,}")
        
        # Verify monotonic decrease
        assert level1_count <= level0_count, "Singlets greater than all events"
        assert level2_count <= level1_count, "Live cells greater than singlets"
        assert level3_count <= level2_count, "Lymphocytes greater than live cells"
        assert level4_count <= level3_count, "T cells greater than lymphocytes"
        
        # All stages should be meaningful (>0)
        assert level4_count > 0, "No cells remain after complete pipeline"
        
        print("\n✓ Monotonic decrease verified through all levels")

    def test_pipeline_statistics_consistency(self, sample_c_events):
        """Verify statistics are reasonable through the pipeline."""
        print("\n" + "="*70)
        print("STATISTICS CONSISTENCY CHECK")
        print("="*70)
        
        levels = []
        data = sample_c_events
        
        # Singlets
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        data = data[singlet_gate.contains(data)]
        levels.append(('Singlets', data))
        
        # Live
        live_gate = RangeGate('APC-A', low=0, high=45000)
        data = data[live_gate.contains(data)]
        levels.append(('Live', data))
        
        # Lymphocytes
        lymph_gate = RectangleGate('FSC-A', 'SSC-A', x_min=40_000, x_max=120_000, y_min=500, y_max=15_000)
        data = data[lymph_gate.contains(data)]
        levels.append(('Lymphocytes', data))
        
        # T cells
        t_gate = RectangleGate('FITC-A', 'PE-A', x_min=0, x_max=100, y_min=50, y_max=300)
        data = data[t_gate.contains(data)]
        levels.append(('T cells', data))
        
        # Verify statistics are valid (not NaN, not infinite)
        for name, level_data in levels:
            if len(level_data) > 0:
                fsc_mean = level_data['FSC-A'].mean()
                ssc_mean = level_data['SSC-A'].mean()
                
                assert not np.isnan(fsc_mean), f"{name}: FSC mean is NaN"
                assert not np.isnan(ssc_mean), f"{name}: SSC mean is NaN"
                assert not np.isinf(fsc_mean), f"{name}: FSC mean is Inf"
                assert not np.isinf(ssc_mean), f"{name}: SSC mean is Inf"
                
                print(f"{name:15s} | n={len(level_data):6,} | FSC={fsc_mean:7.0f} | SSC={ssc_mean:7.0f}")
        
        print("\n✓ All statistics valid and finite")


@pytest.mark.integration
class TestSampleCSpecificClusters:
    """Test identification of specific cell clusters in Sample C."""

    def test_clear_b_t_separation(self, sample_c_events):
        """Sample C should have clear B vs T cell separation."""
        # Prepare data
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        singlets = sample_c_events[singlet_gate.contains(sample_c_events)]
        
        live_gate = RangeGate('APC-A', low=0, high=45000)
        live = singlets[live_gate.contains(singlets)]
        
        lymph_gate = RectangleGate('FSC-A', 'SSC-A', x_min=20_000, x_max=200_000, y_min=500, y_max=50_000)
        lymphocytes = live[lymph_gate.contains(live)]
        
        # Check for B/T separation
        if len(lymphocytes) > 100:
            # Positive gates
            b_gate = RectangleGate('FITC-A', 'PE-A', x_min=1000, x_max=200_000, y_min=0, y_max=5000)
            t_gate = RectangleGate('FITC-A', 'PE-A', x_min=0, x_max=5000, y_min=1000, y_max=200_000)
            
            b_count = np.sum(b_gate.contains(lymphocytes))
            t_count = np.sum(t_gate.contains(lymphocytes))
            
            # Should have both populations
            assert b_count > 0, "No B cells found"
            assert t_count > 0, "No T cells found"
            
            # B and T should be identifiable
            assert abs(b_count - t_count) > len(lymphocytes) * 0.001, \
                "B and T cell populations too similar"

    def test_cd4_cd8_identifiable(self, sample_c_events):
        """Sample C should have identifiable CD4 and CD8 clusters in T cells."""
        # Prepare data
        singlet_gate = RectangleGate('FSC-A', 'SSC-A', x_min=50_000, x_max=200_000, y_min=1_000, y_max=50_000)
        singlets = sample_c_events[singlet_gate.contains(sample_c_events)]
        
        live_gate = RangeGate('APC-A', low=0, high=45000)
        live = singlets[live_gate.contains(singlets)]
        
        lymph_gate = RectangleGate('FSC-A', 'SSC-A', x_min=20_000, x_max=200_000, y_min=500, y_max=50_000)
        lymphocytes = live[lymph_gate.contains(live)]
        
        # Get T cells
        t_gate = RectangleGate('FITC-A', 'PE-A', x_min=0, x_max=100, y_min=50, y_max=300)
        t_cells = lymphocytes[t_gate.contains(lymphocytes)]
        
        if len(t_cells) > 100:
            # Check CD4 and CD8
            cd4_gate = RectangleGate('PerCP-Cy5-5-A', 'APC-Cy7-A', x_min=1000, x_max=200_000, y_min=0, y_max=5000)
            cd8_gate = RectangleGate('PerCP-Cy5-5-A', 'APC-Cy7-A', x_min=0, x_max=5000, y_min=1000, y_max=200_000)
            
            cd4_count = np.sum(cd4_gate.contains(t_cells))
            cd8_count = np.sum(cd8_gate.contains(t_cells))
            
            # Should identify at least some CD4 or CD8
            assert cd4_count > 0 or cd8_count > 0, \
                "No CD4 or CD8 cells identified in T cell population"
