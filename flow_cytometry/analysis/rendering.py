"""Functional rendering core for flow cytometry plots.

Contains the math and data processing logic for creating histograms,
pseudocolor density maps, and contour plots. 
Decoupled from both PyQt and Matplotlib backend details where possible.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from biopro.sdk.utils.logging import get_logger
from typing import Tuple, Optional, Dict, Any
from fast_histogram import histogram2d as fast_hist2d
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.stats import rankdata

from .constants import (
    DEFAULT_NBINS_MIN,
    DEFAULT_NBINS_MAX,
    NBINS_SCALING_FACTOR,
    SIGMA_MIN,
    SIGMA_SCALING_FACTOR,
    DENSITY_THRESHOLD_MIN,
    DENSITY_THRESHOLD_PCT,
    VIBRANCY_MIN,
    VIBRANCY_RANGE,
)

logger = get_logger(__name__, "flow_cytometry")


def compute_pseudocolor_points(
    x: np.ndarray, 
    y: np.ndarray, 
    x_range: Tuple[float, float], 
    y_range: Tuple[float, float],
    quality_multiplier: float = 1.0,
    nbins_scaling: Optional[float] = None,
    sigma_scaling: Optional[float] = None,
    density_threshold: Optional[float] = None,
    vibrancy_min: Optional[float] = None,
    vibrancy_range: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute robust, industry-standard pseudocolor density.
    
    Uses rank-based normalization to ensure visual parity between sparse
    thumbnails and dense main plots.
    """
    valid = np.isfinite(x) & np.isfinite(y)
    x_vis, y_vis = x[valid], y[valid]

    if len(x_vis) == 0:
        return np.array([]), np.array([]), np.array([])
        
    n_points = len(x_vis)
    x_lo, x_hi = x_range
    y_lo, y_hi = y_range

    # 1. 2D Histogram Computation
    # Calculates a 2D density grid over the given data range extremely fast using C bindings.
    # High resolution for both main and subplots ensures density peaks remain sharp.
    # We cap nbins at DEFAULT_NBINS_MAX to prevent grid undersampling lumpiness ("blocky chunks").
    nbins_scaling_val = nbins_scaling if nbins_scaling is not None else NBINS_SCALING_FACTOR
    raw_nbins = max(DEFAULT_NBINS_MIN, np.sqrt(n_points) * nbins_scaling_val)
    nbins = int(min(DEFAULT_NBINS_MAX, raw_nbins * quality_multiplier))
    
    # Handle potentially inverted axis limits from Matplotlib
    x_min, x_max = (min(x_lo, x_hi), max(x_lo, x_hi))
    y_min, y_max = (min(y_lo, y_hi), max(y_lo, y_hi))
    
    # Ensure non-zero span for fast_histogram (prevents divide-by-zero errors)
    if x_min == x_max: x_max += 1e-6
    if y_min == y_max: y_max += 1e-6

    H = fast_hist2d(
        x_vis, y_vis,
        bins=[nbins, nbins],
        range=[[x_min, x_max], [y_min, y_max]]
    )

    # 2. Robust Gaussian Smoothing
    # Smoothes the raw histogram to create continuous color transitions 
    # instead of sharp rectangular bin outlines. 
    # Sigma scales proportionally with nbins to maintain a consistent visual 'glow' regardless of resolution.
    sigma_scaling_val = sigma_scaling if sigma_scaling is not None else SIGMA_SCALING_FACTOR
    sigma = max(SIGMA_MIN, sigma_scaling_val * (nbins / DEFAULT_NBINS_MIN))
    smoothed = gaussian_filter(H.astype(np.float64), sigma=sigma)
    
    # 3. Interpolated Density Lookup
    # map_coordinates extracts the exact smoothed density value for each individual event.
    # This dynamic point-lookup approach completely prevents blocky grid artifacts.
    x_span = max(x_max - x_min, 1e-12)
    y_span = max(y_max - y_min, 1e-12)
    
    # Map data coordinates to grid indices [0, nbins - 1]
    x_coords = np.clip((x_vis - x_min) / x_span * (nbins - 1), 0, nbins - 1)
    y_coords = np.clip((y_vis - y_min) / y_span * (nbins - 1), 0, nbins - 1)
    
    # We transpose the smoothed array and use [y_coords, x_coords] to ensure 
    # the standard (row, col) -> (y, x) mapping aligns correctly with matplotlib backends.
    densities = map_coordinates(smoothed.T, [y_coords, x_coords], order=1, mode='nearest')
    
    # 4. Normalization and Scaling
    max_d = np.max(densities)
    c_plot = np.zeros_like(densities)
    
    if max_d > 0:
        # 4. Rank Percentile Normalization
        # Industry-standard "secret sauce": instead of log-scaling, we use the percentile rank 
        # of each event's density. This ensures that the "blue cloud" of low-density 
        # events is robustly represented regardless of the absolute density values.
        c_plot = rankdata(densities, method='average') / n_points
        
        # 5. Thresholding & Vibrancy
        # Background Suppression: Snaps the bottom X% of events strictly to 0.0 (blue).
        # This cleans up sparse background noise.
        density_thresh_val = density_threshold if density_threshold is not None else DENSITY_THRESHOLD_MIN
        c_plot[c_plot < density_thresh_val] = 0.0
        
        # Vibrancy: Mathematically amplifies the color range for the rest of the distribution.
        vib_min_val = vibrancy_min if vibrancy_min is not None else VIBRANCY_MIN
        vib_range_val = vibrancy_range if vibrancy_range is not None else VIBRANCY_RANGE
        
        mask = c_plot > 0
        if np.any(mask):
            # Scale the ranks [threshold, 1.0] -> [vib_min, vib_min + vib_range]
            # This makes the population core "pop" with vivid colors.
            c_plot[mask] = vib_min_val + vib_range_val * (c_plot[mask] - density_thresh_val) / (1.0 - density_thresh_val)
            c_plot = np.clip(c_plot, 0, 1)

    # 6. Z-Sorting
    # Sort events so that dense events are rendered on top, preventing sparse outliers 
    # from hiding the dense core population.
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
