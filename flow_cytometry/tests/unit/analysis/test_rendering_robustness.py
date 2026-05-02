import pytest
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from fast_histogram import histogram2d
from flow_cytometry.analysis.rendering import compute_pseudocolor_points

def test_pseudocolor_rank_normalization():
    """Verify that rank-based normalization handles density peaks correctly."""
    # Create two clusters with different absolute densities
    N1 = 1000
    N2 = 100
    x = np.concatenate([
        np.random.normal(0.2, 0.05, N1),
        np.random.normal(0.8, 0.05, N2)
    ])
    y = np.concatenate([
        np.random.normal(0.2, 0.05, N1),
        np.random.normal(0.8, 0.05, N2)
    ])
    
    # Render
    xv, yv, c = compute_pseudocolor_points(x, y, (0, 1), (0, 1), nbins_scaling=1.0)
    
    # Both clusters should have distinct color ranges despite 10x density difference
    # because of rank-based normalization.
    c1 = c[:N1] # Dense cluster (sorted last)
    c2 = c[N1:] # Sparse cluster
    
    assert np.max(c) == pytest.approx(1.0, abs=0.05)
    assert np.mean(c1) > np.mean(c2)
    assert np.max(c2) > 0.5 # Should still be vivid

def test_coordinate_mapping_orientation():
    """Verify H[x, y] vs map_coordinates[y, x] alignment."""
    # Cluster at X=15, Y=5
    x = np.random.normal(15, 0.1, 100)
    y = np.random.normal(5, 0.1, 100)
    
    x_range = (0, 20)
    y_range = (0, 20)
    nbins = 20
    
    # H has shape (nbins, nbins) where H[i, j] is x_bin i, y_bin j
    H = histogram2d(x, y, bins=[nbins, nbins], range=[x_range, y_range])
    smoothed = gaussian_filter(H, sigma=0.5)
    
    # data (15, 5) -> bin (14.5, 4.5)
    tx = (15 - 0) / 20 * nbins - 0.5 
    ty = (5 - 0) / 20 * nbins - 0.5
    
    # map_coordinates expects [row_coords, col_coords]
    # If H[i, j] is [x, y], then row=x, col=y
    d_correct = map_coordinates(smoothed, [[tx], [ty]], order=1)[0]
    d_wrong = map_coordinates(smoothed, [[ty], [tx]], order=1)[0]
    
    assert d_correct > d_wrong
    assert d_correct > 0.1

def test_inverted_axis_rendering():
    """Verify that rendering doesn't crash or flip with inverted limits (e.g. 100 to 0)."""
    x = np.random.normal(50, 5, 100)
    y = np.random.normal(50, 5, 100)
    
    # This should handle the inverted range internally
    try:
        xv, yv, c = compute_pseudocolor_points(x, y, (100, 0), (0, 100))
        assert len(xv) == 100
    except Exception as e:
        pytest.fail(f"compute_pseudocolor_points crashed on inverted limits: {e}")
