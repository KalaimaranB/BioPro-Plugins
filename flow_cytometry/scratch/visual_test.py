import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.stats import rankdata
from scipy.ndimage import gaussian_filter, map_coordinates
from fast_histogram import histogram2d as fast_hist2d
import os

def compute_pseudocolor_points_fixed(x, y, x_range, y_range, quality_multiplier=1.0):
    valid = np.isfinite(x) & np.isfinite(y)
    x_vis, y_vis = x[valid], y[valid]
    n_points = len(x_vis)
    x_lo, x_hi = x_range
    y_lo, y_hi = y_range
    nbins = int(min(1024, max(128, np.sqrt(n_points) * 2.0)) * quality_multiplier)
    
    H = fast_hist2d(x_vis, y_vis, bins=[nbins, nbins], range=[[x_lo, x_hi], [y_lo, y_hi]])
    sigma = max(1.2, 1.8 * (nbins / 512))
    smoothed = gaussian_filter(H.astype(np.float64), sigma=sigma)
    
    x_span = max(x_hi - x_lo, 1e-12)
    y_span = max(y_hi - y_lo, 1e-12)
    
    x_coords = np.clip((x_vis - x_lo) / x_span * nbins - 0.5, 0, nbins - 1)
    y_coords = np.clip((y_vis - y_lo) / y_span * nbins - 0.5, 0, nbins - 1)
    
    # Current "fixed" state
    densities = map_coordinates(smoothed, [x_coords, y_coords], order=1, mode='nearest')
    
    c_plot = np.zeros_like(densities)
    mask = densities > 1e-12
    if np.any(mask):
        c_plot[mask] = rankdata(densities[mask], method='ordinal') / np.sum(mask)
        
    sort_idx = np.argsort(c_plot)
    return x_vis[sort_idx], y_vis[sort_idx], c_plot[sort_idx]

def run_visual_test():
    # 1. Create a cluster at (0.2, 0.8)
    # Note: Cluster is TOP-LEFT
    np.random.seed(42)
    N = 5000
    x_cluster = np.random.normal(0.2, 0.05, N)
    y_cluster = np.random.normal(0.8, 0.05, N)
    
    # Background noise
    x_noise = np.random.uniform(0, 1, 1000)
    y_noise = np.random.uniform(0, 1, 1000)
    
    x = np.concatenate([x_cluster, x_noise])
    y = np.concatenate([y_cluster, y_noise])
    
    x_range = (0, 1)
    y_range = (0, 1)
    
    x_p, y_p, c_p = compute_pseudocolor_points_fixed(x, y, x_range, y_range)
    
    fig = plt.figure(figsize=(4, 4), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    
    sc = ax.scatter(x_p, y_p, c=c_p, cmap='jet', s=5, vmin=0, vmax=1, edgecolors='none')
    
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    
    rgba = np.array(canvas.buffer_rgba())
    # Inspect pixels
    # (0.2, 0.8) is roughly at (x_px = 0.2*width, y_px = (1-0.8)*height)
    # Matplotlib y-axis is bottom-to-top, but image pixels are top-to-bottom.
    
    # Just save the image for now
    out_path = "/Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/scratch/visual_test.png"
    plt.savefig(out_path)
    print(f"Saved test image to {out_path}")
    
    # Check max color
    print(f"Max c_p: {np.max(c_p)}")
    print(f"Mean c_p: {np.mean(c_p)}")
    print(f"Points with density > 0: {np.sum(c_p > 0)}")

if __name__ == "__main__":
    run_visual_test()
