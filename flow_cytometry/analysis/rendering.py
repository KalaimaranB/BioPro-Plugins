"""Functional rendering core for flow cytometry plots.

Contains the math and data processing logic for creating histograms,
pseudocolor density maps, and contour plots. 
Decoupled from both PyQt and Matplotlib backend details where possible.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import logging
from typing import Tuple, Optional, Dict, Any
from fast_histogram import histogram2d as fast_hist2d
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.stats import rankdata

logger = logging.getLogger(__name__)

def compute_pseudocolor_points(
    x: np.ndarray, 
    y: np.ndarray, 
    x_range: Tuple[float, float], 
    y_range: Tuple[float, float],
    quality_multiplier: float = 1.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute FlowJo-style pseudocolor density percentiles for each point.
    
    Args:
        x, y: Transformed coordinates.
        x_range, y_range: Transformed display limits.
        quality_multiplier: Scale factor for bin density.
        
    Returns:
        x_sorted, y_sorted, c_sorted: Points sorted by density (Z-order) with 0-1 percentiles.
    """
    valid = np.isfinite(x) & np.isfinite(y)
    x_vis, y_vis = x[valid], y[valid]

    if len(x_vis) == 0:
        return np.array([]), np.array([]), np.array([])
        
    if len(x_vis) < 10:
        return x_vis, y_vis, np.zeros_like(x_vis)

    # 1. Density estimation using fast 2D histogram
    n_points = len(x_vis)
    # Increased max bins to 1024 for high-res monitors and large datasets.
    # Base resolution scales with sqrt of points for statistical robustness.
    N_BINS = int(min(1024, max(128, np.sqrt(n_points) * 2.0)) * quality_multiplier)
    
    # Sigma controls the "blur" of the density map. 
    # Increased slightly to eliminate quantization artifacts (blocks).
    sigma = max(1.2, 2.5 * (N_BINS / 1024))

    H = fast_hist2d(
        y_vis, x_vis,
        range=[[y_range[0], y_range[1]], [x_range[0], x_range[1]]],
        bins=N_BINS,
    )
    H_smooth = gaussian_filter(H.astype(np.float64), sigma=sigma)

    # 2. Per-event density lookup (bilinear interpolation)
    x_span = max(x_range[1] - x_range[0], 1e-12)
    y_span = max(y_range[1] - y_range[0], 1e-12)
    x_frac = np.clip((x_vis - x_range[0]) / x_span * N_BINS - 0.5, 0, N_BINS - 1)
    y_frac = np.clip((y_vis - y_range[0]) / y_span * N_BINS - 0.5, 0, N_BINS - 1)
    
    densities = map_coordinates(H_smooth, [y_frac, x_frac], order=1, mode='nearest')

    # 3. Equal Probability (Percentile) Normalization
    c_plot = rankdata(densities) / len(densities)

    # 4. Z-sort: dense events render on top
    sort_idx = np.argsort(c_plot)
    return x_vis[sort_idx], y_vis[sort_idx], c_plot[sort_idx]

def compute_1d_histogram(
    x_vis: np.ndarray,
    x_range: Tuple[float, float],
    bins: int = 256
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute 1D histogram counts and bin edges."""
    if len(x_vis) == 0:
        return np.zeros(bins), np.linspace(x_range[0], x_range[1], bins + 1)
        
    counts, edges = np.histogram(x_vis, bins=bins, range=x_range)
    return counts, edges
