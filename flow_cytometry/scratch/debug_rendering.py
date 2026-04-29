import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.stats import rankdata

# Mocking fast_histogram.histogram2d since it might not be in the environment
# But we know it returns H[x, y]
def mock_hist2d(x, y, bins, range):
    # Standard numpy histogram2d also returns H[x, y]
    H, _, _ = np.histogram2d(x, y, bins=bins, range=range)
    return H

def compute_pseudocolor_points_debug(x, y, x_range, y_range, swap=True):
    n_points = len(x)
    nbins = 100
    x_lo, x_hi = x_range
    y_lo, y_hi = y_range
    
    H = mock_hist2d(x, y, bins=[nbins, nbins], range=[[x_lo, x_hi], [y_lo, y_hi]])
    smoothed = gaussian_filter(H.astype(np.float64), sigma=1.5)
    
    x_span = max(x_hi - x_lo, 1e-12)
    y_span = max(y_hi - y_lo, 1e-12)
    
    x_coords = np.clip((x - x_lo) / x_span * nbins - 0.5, 0, nbins - 1)
    y_coords = np.clip((y - y_lo) / y_span * nbins - 0.5, 0, nbins - 1)
    
    if swap:
        # THE BUG: y and x swapped in coordinates
        densities = map_coordinates(smoothed, [y_coords, x_coords], order=1, mode='nearest')
    else:
        # THE FIX
        densities = map_coordinates(smoothed, [x_coords, y_coords], order=1, mode='nearest')
        
    return densities

# Test case: Cluster at (0.8, 0.2)
N = 1000
x = np.random.normal(0.8, 0.05, N)
y = np.random.normal(0.2, 0.05, N)

# Add some noise
x = np.concatenate([x, np.random.uniform(0, 1, 100)])
y = np.concatenate([y, np.random.uniform(0, 1, 100)])

x_range = (0, 1)
y_range = (0, 1)

densities_bug = compute_pseudocolor_points_debug(x, y, x_range, y_range, swap=True)
densities_fix = compute_pseudocolor_points_debug(x, y, x_range, y_range, swap=False)

print(f"Max density (Bug): {np.max(densities_bug):.4f}")
print(f"Max density (Fix): {np.max(densities_fix):.4f}")

# Check points near the cluster center (0.8, 0.2)
cluster_mask = (x > 0.75) & (x < 0.85) & (y > 0.15) & (y < 0.25)
print(f"Avg cluster density (Bug): {np.mean(densities_bug[cluster_mask]):.4f}")
print(f"Avg cluster density (Fix): {np.mean(densities_fix[cluster_mask]):.4f}")

# Check points near the mirrored center (0.2, 0.8)
mirror_mask = (x > 0.15) & (x < 0.25) & (y > 0.75) & (y < 0.85)
if np.any(mirror_mask):
    print(f"Avg mirrored density (Bug): {np.mean(densities_bug[mirror_mask]):.4f}")
    print(f"Avg mirrored density (Fix): {np.mean(densities_fix[mirror_mask]):.4f}")
else:
    print("No points near mirrored center to check.")
