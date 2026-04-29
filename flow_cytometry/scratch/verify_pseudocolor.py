import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.stats import rankdata
from scipy.ndimage import gaussian_filter, map_coordinates
from fast_histogram import histogram2d as fast_hist2d

# The actual logic from rendering.py (copied here for standalone test)
def compute_pseudocolor_points(x, y, x_range, y_range, nbins=128):
    x_lo, x_hi = x_range
    y_lo, y_hi = y_range
    x_min, x_max = min(x_lo, x_hi), max(x_lo, x_hi)
    y_min, y_max = min(y_lo, y_hi), max(y_lo, y_hi)
    
    H = fast_hist2d(x, y, bins=[nbins, nbins], range=[[x_min, x_max], [y_min, y_max]])
    smoothed = gaussian_filter(H.astype(np.float64), sigma=1.5)
    
    x_span = max(x_max - x_min, 1e-12)
    y_span = max(y_max - y_min, 1e-12)
    x_coords = np.clip((x - x_min) / x_span * nbins - 0.5, 0, nbins - 1)
    y_coords = np.clip((y - y_min) / y_span * nbins - 0.5, 0, nbins - 1)
    
    densities = map_coordinates(smoothed, [x_coords, y_coords], order=1, mode='nearest')
    
    max_d = np.max(densities)
    c_plot = np.zeros_like(densities)
    if max_d > 0:
        c_plot = rankdata(densities, method='average') / len(densities)
        threshold = max_d * 0.01 
        c_plot[densities < threshold] = 0.0
        mask = c_plot > 0
        if np.any(mask):
            c_min, c_max = np.min(c_plot[mask]), np.max(c_plot[mask])
            if c_max > c_min:
                c_plot[mask] = 0.15 + 0.85 * (c_plot[mask] - c_min) / (c_max - c_min)
            else:
                c_plot[mask] = 1.0
    return x, y, c_plot

def test_final():
    # Cluster at (0.2, 0.8) -> TOP-LEFT
    # Noise elsewhere
    np.random.seed(42)
    N = 1000
    x = np.concatenate([np.random.normal(0.2, 0.05, N), np.random.uniform(0, 1, 100)])
    y = np.concatenate([np.random.normal(0.8, 0.05, N), np.random.uniform(0, 1, 100)])
    
    # Test case 1: Standard axes
    x1, y1, c1 = compute_pseudocolor_points(x, y, (0, 1), (0, 1))
    # Point near center should be red
    center_idx = 0
    print(f"Standard axes - Color at center: {c1[center_idx]:.4f}")
    assert c1[center_idx] > 0.9, "Cluster center should be red (> 0.9)"
    
    # Test case 2: Inverted axes (1 to 0)
    x2, y2, c2 = compute_pseudocolor_points(x, y, (1, 0), (0, 1))
    print(f"Inverted X - Color at center: {c2[center_idx]:.4f}")
    assert c2[center_idx] > 0.9, "Cluster center should still be red with inverted X"
    
    # Verify background is blue
    noise_idx = -1 # Last point is uniform noise
    print(f"Noise point color: {c2[noise_idx]:.4f}")
    # It might have some density due to smoothing, but should be low
    assert c2[noise_idx] < 0.5, "Background should be relatively blue"
    
    print("ALL TESTS PASSED!")

if __name__ == "__main__":
    test_final()
