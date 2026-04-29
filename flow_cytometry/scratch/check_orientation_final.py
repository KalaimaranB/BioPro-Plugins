import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.stats import rankdata
from scipy.ndimage import gaussian_filter, map_coordinates
from fast_histogram import histogram2d as fast_hist2d

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
    
    # TRYING [y, x] INSTEAD OF [x, y]
    densities_xy = map_coordinates(smoothed, [x_coords, y_coords], order=1, mode='nearest')
    densities_yx = map_coordinates(smoothed, [y_coords, x_coords], order=1, mode='nearest')
    
    return densities_xy[0], densities_yx[0]

def test_orientation():
    # Cluster at (0.2, 0.8)
    np.random.seed(42)
    N = 1000
    x = np.random.normal(0.2, 0.05, N)
    y = np.random.normal(0.8, 0.05, N)
    
    d_xy, d_yx = compute_pseudocolor_points(x, y, (0, 1), (0, 1))
    
    print(f"Cluster center (0.2, 0.8):")
    print(f"  Density [x, y]: {d_xy:.4f}")
    print(f"  Density [y, x]: {d_yx:.4f}")

if __name__ == "__main__":
    test_orientation()
