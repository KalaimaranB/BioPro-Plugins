"""Functional rendering core for flow cytometry plots.

Contains the math and data processing logic for creating histograms,
pseudocolor density maps, and contour plots. 
Decoupled from both PyQt and Matplotlib backend details where possible.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict, Any
from fast_histogram import histogram2d as fast_hist2d

def compute_pseudocolor_density(
    x_vis: np.ndarray, 
    y_vis: np.ndarray, 
    x_range: Tuple[float, float], 
    y_range: Tuple[float, float],
    bins: int = 256
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute 2D histogram and outlier mask for pseudocolor plots.
    
    Returns:
        H: 2D histogram (density map)
        outliers_x: X coordinates of sparse points
        outliers_y: Y coordinates of sparse points
    """
    if len(x_vis) == 0:
        return np.zeros((bins, bins)), np.array([]), np.array([])
        
    # 1. Compute high-res 2D histogram
    H = fast_hist2d(
        y_vis, x_vis, 
        bins=bins, 
        range=[[y_range[0], y_range[1]], [x_range[0], x_range[1]]]
    )
    
    # 2. Identify outliers (points in low-density bins)
    # This matches the FlowJo-style "smoothed density with outlier dots"
    # We find which bin each point falls into
    # (Simplified for now: points in bins with count <= threshold are outliers)
    # In a real implementation, we'd use the histogram to mask the original data.
    
    # For now, we return the histogram. The caller can decide how to render it.
    return H, np.array([]), np.array([]) # Outlier logic can be added later

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
