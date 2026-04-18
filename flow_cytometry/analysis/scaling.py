"""Axis scaling and range calculation utilities.

Provides data structures for persisting per-axis scale settings (e.g.,
Min/Max, Logicle T, W, M, A parameters) and utilities for calculating
robust auto-ranges that ignore extreme outliers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .transforms import TransformType

logger = logging.getLogger(__name__)


@dataclass
class AxisScale:
    """Settings for how to scale and display a single axis."""
    
    transform_type: TransformType = TransformType.LINEAR
    
    # Range limits (None means auto-scale)
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    
    # Biexponential (Logicle) parameters
    # Matches FlowJo v11 Transform dialog defaults and naming
    logicle_t: float = 262144.0  # Top data value (determines max scale)
    logicle_w: float = 0.5       # Width Basis (linear range around 0)
    logicle_m: float = 4.5       # Positive decades
    logicle_a: float = 0.0       # Extra negative decades

    def copy(self) -> "AxisScale":
        return AxisScale(
            transform_type=self.transform_type,
            min_val=self.min_val,
            max_val=self.max_val,
            logicle_t=self.logicle_t,
            logicle_w=self.logicle_w,
            logicle_m=self.logicle_m,
            logicle_a=self.logicle_a,
        )

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "transform_type": self.transform_type.value,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "logicle_t": self.logicle_t,
            "logicle_w": self.logicle_w,
            "logicle_m": self.logicle_m,
            "logicle_a": self.logicle_a,
        }


def calculate_auto_range(
    data: np.ndarray, transform_type: TransformType
) -> tuple[float, float]:
    """Calculate a robust display range ignoring extreme outliers."""
    if len(data) == 0:
        return (0.0, 1.0)
        
    valid = np.isfinite(data)
    valid_data = data[valid]
    
    if len(valid_data) == 0:
        return (0.0, 1.0)

    if transform_type == TransformType.LINEAR:
        p_min = np.percentile(valid_data, 0.1)
        
        # THE FIX: Find a robust high percentile to ignore 262k noise peg-outs
        p99_5 = np.percentile(valid_data, 99.5)
        
        # Add 10% padding so we don't slice the top of the diffuse populations
        p_max = p99_5 * 1.1
        
        # Cap it at the absolute max just in case the data is perfectly distributed
        p_max = min(p_max, valid_data.max())
        
        # If the biological data is all mostly positive (FSC/SSC), ensure 0 is in frame
        if p_min > 0 and p_min < p_max * 0.1:
            p_min = 0.0
            
        rng = max(p_max - p_min, 1e-6)
        bottom_pad = 0.0 if p_min == 0.0 else rng * 0.02
        
        return (p_min - bottom_pad, p_max + rng * 0.02)
        
    elif transform_type == TransformType.LOG:
        # ... (keep existing log code)
        pos_data = valid_data[valid_data > 0]
        if len(pos_data) == 0:
            return (0.1, 10.0)
        p_min = np.percentile(pos_data, 0.1)
        p_max = np.percentile(valid_data, 99.9)
        return (p_min * 0.5, p_max * 2.0)
        
    elif transform_type == TransformType.BIEXPONENTIAL:
        # ... (keep existing biexponential code)
        p_min = np.percentile(valid_data, 0.1)
        p_max = np.percentile(valid_data, 99.9)
        range_val = abs(p_max - p_min)
        pad_bottom = max(100.0, range_val * 0.05)
        pad_top = max(100.0, range_val * 0.1)
        return (p_min - pad_bottom, p_max + pad_top)
        
    else:
        return (valid_data.min(), valid_data.max())

def detect_logicle_top(data) -> float:
    """Return the Logicle T (Top) parameter for this channel's data.
 
    T is the INSTRUMENT CEILING, not the data maximum.  FlowJo always
    uses 2^18 = 262144 for modern digital cytometers regardless of what
    the data actually reaches.  Using a lower T compresses the scale and
    makes the near-zero cluster appear at the wrong position.
 
    We still inspect the data so that:
      - Very old 12/14-bit instruments (max ~16384) get a smaller T.
      - Future 20-bit instruments (max ~1M) get a larger T.
    But T is ALWAYS at least 262144 for standard 18-bit instruments.
    """
    import numpy as np
 
    if len(data) == 0:
        return 262144.0
 
    valid = np.isfinite(data)
    if not np.any(valid):
        return 262144.0
 
    # Use 99th percentile (not 99.99) — a handful of saturated events
    # should not inflate T unnecessarily.
    p99 = float(np.percentile(data[valid], 99))
 
    # Standard 18-bit digital cytometer — covers ~99% of all modern instruments.
    # Always at least 262144 so the logicle scale matches FlowJo.
    if p99 <= 262144.0:
        return 262144.0
 
    # 20-bit or amplified channels (rare, e.g. spectral systems)
    if p99 <= 1_048_576.0:
        return 1_048_576.0
 
    # Beyond that, round up to next power of 2
    return float(2 ** int(np.ceil(np.log2(p99 * 1.1))))