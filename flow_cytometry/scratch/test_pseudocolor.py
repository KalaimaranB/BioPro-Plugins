import numpy as np
import sys
import os
from scipy.stats import rankdata
from scipy.ndimage import gaussian_filter, map_coordinates

# Import the actual rendering functions if possible
# We'll mock fast_histogram since we already know its behavior from test_orientation.py
# But we'll use the logic from rendering.py to verify it.

def mock_histogram2d(x, y, bins, range):
    from fast_histogram import histogram2d
    return histogram2d(x, y, bins=bins, range=range)

def run_test(x_vis, y_vis, x_range, y_range, nbins=128):
    x_lo, x_hi = x_range
    y_lo, y_hi = y_range
    
    # 1. Histogram
    try:
        # Handling the inverted axes bug
        x_lims = [min(x_lo, x_hi), max(x_lo, x_hi)]
        y_lims = [min(y_lo, y_hi), max(y_lo, y_hi)]
        H = mock_histogram2d(x_vis, y_vis, bins=[nbins, nbins], range=[x_lims, y_lims])
    except Exception as e:
        return f"CRASH: {e}"
        
    # 2. Smoothing
    smoothed = gaussian_filter(H.astype(np.float64), sigma=1.5)
    
    # 3. Lookup
    x_span = max(abs(x_hi - x_lo), 1e-12)
    y_span = max(abs(y_hi - y_lo), 1e-12)
    
    # Use the same min logic for coordinates
    x_coords = np.clip((x_vis - min(x_lo, x_hi)) / x_span * nbins - 0.5, 0, nbins - 1)
    y_coords = np.clip((y_vis - min(y_lo, y_hi)) / y_span * nbins - 0.5, 0, nbins - 1)
    
    # Check orientation [x, y] vs [y, x]
    # We want to know which one puts high density at the cluster center
    densities_xy = map_coordinates(smoothed, [x_coords, y_coords], order=1, mode='nearest')
    densities_yx = map_coordinates(smoothed, [y_coords, x_coords], order=1, mode='nearest')
    
    return {
        "densities_xy": densities_xy,
        "densities_yx": densities_yx,
        "H": H
    }

def main():
    # Test 1: Standard orientation
    # Cluster at (0.2, 0.8)
    N = 1000
    x = np.random.normal(0.2, 0.05, N)
    y = np.random.normal(0.8, 0.05, N)
    
    res = run_test(x, y, (0, 1), (0, 1))
    if isinstance(res, str):
        print(res)
        return

    # Cluster center is roughly point 0
    idx = 0
    d_xy = res["densities_xy"][idx]
    d_yx = res["densities_yx"][idx]
    
    print(f"Cluster center (0.2, 0.8):")
    print(f"  Density [x, y]: {d_xy:.4f}")
    print(f"  Density [y, x]: {d_yx:.4f}")
    
    if d_xy > d_yx:
        print("RESULT: [x, y] is correct for standard axes.")
    else:
        print("RESULT: [y, x] is correct for standard axes.")

    # Test 2: Inverted X axis (1 to 0)
    res_inv = run_test(x, y, (1, 0), (0, 1))
    if isinstance(res_inv, str):
        print(f"Inverted X test: {res_inv}")
    else:
        print("Inverted X test: PASSED (no crash)")
        d_xy_inv = res_inv["densities_xy"][idx]
        print(f"  Density [x, y] with inverted X: {d_xy_inv:.4f}")

if __name__ == "__main__":
    main()
