"""Axis scaling and range calculation utilities.

Provides data structures for persisting per-axis scale settings (e.g.,
Min/Max, Logicle T, W, M, A parameters) and utilities for calculating
robust auto-ranges that ignore extreme outliers.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .transforms import TransformType

logger = get_logger(__name__, "flow_cytometry")


@dataclass
class AxisScale:
    """Settings for how to scale and display a single axis."""
    
    transform_type: TransformType = TransformType.LINEAR
    
    # Range limits (None means auto-scale)
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    
    # Biexponential (Logicle) parameters
    # Matches standard Transform dialog defaults and naming
    logicle_t: float = 262144.0  # Top data value (determines max scale)
    logicle_w: float = 1.0       # Width Basis (linear range around 0)
    logicle_m: float = 4.5       # Positive decades
    logicle_a: float = 0.0       # Extra negative decades
    
    # Outlier bounds (percentile to ignore at each end)
    outlier_percentile: float = 0.1  # Default to 0.1% (p0.1 and p99.9)

    def __post_init__(self):
        """Validate scale parameters after initialization."""
        # Validate transform type
        valid_transforms = {t.value for t in TransformType}
        if self.transform_type.value not in valid_transforms:
            raise ValueError(
                f"Invalid transform_type: {self.transform_type}. "
                f"Must be one of: {valid_transforms}"
            )
        
        # Validate range
        if self.min_val is not None and self.max_val is not None:
            if self.min_val >= self.max_val:
                raise ValueError(
                    f"min_val ({self.min_val}) must be less than max_val ({self.max_val})"
                )
        
        # Validate Logicle parameters
        if self.transform_type == TransformType.BIEXPONENTIAL:
            if self.logicle_t <= 0:
                raise ValueError(f"logicle_t must be positive, got {self.logicle_t}")
            if self.logicle_w < 0:
                raise ValueError(f"logicle_w must be non-negative, got {self.logicle_w}")
            if self.logicle_m <= 0:
                raise ValueError(f"logicle_m must be positive, got {self.logicle_m}")
            if self.logicle_a < 0:
                raise ValueError(f"logicle_a must be non-negative, got {self.logicle_a}")
        
        # Validate outlier percentile
        if not 0 <= self.outlier_percentile <= 50:
            raise ValueError(
                f"outlier_percentile must be between 0 and 50, got {self.outlier_percentile}"
            )

    def copy(self) -> "AxisScale":
        return AxisScale(
            transform_type=self.transform_type,
            min_val=self.min_val,
            max_val=self.max_val,
            logicle_t=self.logicle_t,
            logicle_w=self.logicle_w,
            logicle_m=self.logicle_m,
            logicle_a=self.logicle_a,
            outlier_percentile=self.outlier_percentile,
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
            "outlier_percentile": self.outlier_percentile,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AxisScale":
        """Create an AxisScale instance from a dictionary."""
        return cls(
            transform_type=TransformType(data.get("transform_type", "linear")),
            min_val=data.get("min_val"),
            max_val=data.get("max_val"),
            logicle_t=data.get("logicle_t", 262144.0),
            logicle_w=data.get("logicle_w", 1.0),
            logicle_m=data.get("logicle_m", 4.5),
            logicle_a=data.get("logicle_a", 0.0),
            outlier_percentile=data.get("outlier_percentile", 0.1),
        )


def calculate_auto_range(
    data: np.ndarray, transform_type: TransformType, outlier_percentile: float = 0.1
) -> tuple[float, float]:
    """Calculate a robust display range ignoring extreme outliers."""
    if len(data) == 0:
        return (0.0, 1.0)
        
    valid = np.isfinite(data)
    valid_data = data[valid]
    
    if len(valid_data) == 0:
        return (0.0, 1.0)

    # Calculate percentiles based on outlier_percentile parameter
    p_min = float(np.percentile(valid_data, outlier_percentile))
    p_max = float(np.percentile(valid_data, 100.0 - outlier_percentile))

    if transform_type == TransformType.LINEAR:
        # Floor: anchor at 0 so scatter channels always show the origin.
        # Allow slightly negative for compensated/gated subsets.
        floor = min(0.0, p_min)

        # Ceiling: No longer hardcoded to 262144. Instead, use p_max plus 5% headroom.
        # This fixes squishing for small-range channels like Time.
        # We only snap to 262144 if the data is already approaching it (e.g. FSC/SSC).
        span = p_max - floor
        if span <= 0:
            span = 1.0
        
        ceiling = p_max + span * 0.05
        
        # Heuristic: If it looks like a standard 18-bit channel, keep the full scale.
        if p_max > 200000 and p_max < 262144:
            ceiling = 262144.0

        return (floor, ceiling)
        
    elif transform_type == TransformType.LOG:
        pos_data = valid_data[valid_data > 0]
        if len(pos_data) == 0:
            return (0.1, 10.0)
        p_min_pos = np.percentile(pos_data, outlier_percentile)
        return (p_min_pos * 0.5, p_max * 2.0)
        
    elif transform_type == TransformType.BIEXPONENTIAL:
        # p_min and p_max already calculated above using outlier_percentile
        if p_min < 0:
            # Compensated fluorescence: show the negative tail with 5% headroom.
            span = max(p_max - p_min, 1.0)
            display_min = p_min - span * 0.05
        else:
            # Positive-only data (FSC, SSC, bright fluorescence).
            # Stay positive: min = 95% of the data floor so the lowest events
            # sit just inside the left/bottom edge.
            display_min = p_min * 0.95

        span = max(p_max - p_min, 1.0)
        display_max = p_max + span * 0.05
        return (display_min, display_max)
        
    else:
        return (p_min, p_max)

def detect_logicle_top(data) -> float:
    """Return the Logicle T (Top) parameter for this channel's data.
 
    T is the INSTRUMENT CEILING, not the data maximum. Traditional software always
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
 
    # Use p99.9 so isolated saturation spikes don't inflate T.
    # Only jump to the next bucket when a meaningful fraction of events
    # genuinely exceed the current ceiling (50% headroom).
    p99 = float(np.percentile(data[valid], 99.9))

    # 18-bit standard cytometer (covers ~99% of modern instruments)
    if p99 <= 262144.0 * 1.5:
        return 262144.0

    # 20-bit / amplified channels (spectral systems, etc.)
    if p99 <= 1_048_576.0 * 1.5:
        return 1_048_576.0

    # Beyond that, round up to next power of 2
    return float(2 ** int(np.ceil(np.log2(p99))))

def estimate_logicle_params(
    data: np.ndarray,
    t: float = 262144.0,
    width: float = 1.0,
) -> tuple[float, float]:
    """Estimate Logicle W and A parameters from data.

    Standard industry defaults: W=1.0 (1 visual decade linear region), A=0.0.
    A is only set > 0 when there is measurable negative data.
    """
    valid = data[np.isfinite(data)]
    if len(valid) == 0:
        return 1.0, 0.0

    # Industry-standard linear-region width. W=1.0 = squish zone is 2 visual
    # decades wide, matching user requested default.
    w = 1.0

    # Only add negative decades when >0.5% of events are genuinely negative
    n_neg = int(np.sum(valid < -10))
    if n_neg == 0 or n_neg / len(valid) < 0.005:
        return w, 0.0

    # Estimate A from the extreme low end of the negative tail
    r = float(np.percentile(valid, 0.1))
    try:
        a = -np.log10(abs(r)) if r < -10.0 else 0.0
        a = max(0.0, min(a, 2.0))
        return w, float(a)
    except Exception:
        return w, 0.0