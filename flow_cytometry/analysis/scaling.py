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
        # p99.9 is deliberate: for 300k events, p99.95 picks up ~150 saturation
        # spike events that inflate the ceiling and squish all data to the bottom.
        # p99.9 drops those spikes while still capturing the biological range.
        p_min = float(np.percentile(valid_data, 0.1))
        p_max = float(np.percentile(valid_data, 99.9))

        # Floor: anchor at 0 so scatter channels always show the origin.
        # Allow slightly negative for compensated/gated subsets.
        floor = min(0.0, p_min)

        # Ceiling: never less than the standard 18-bit instrument range so
        # FSC/SSC always fills the axis at full scale even with sparse data.
        ceiling = max(p_max, 262144.0)

        return (floor, ceiling)
        
    elif transform_type == TransformType.LOG:
        pos_data = valid_data[valid_data > 0]
        if len(pos_data) == 0:
            return (0.1, 10.0)
        p_min = np.percentile(pos_data, 0.1)
        p_max = np.percentile(valid_data, 99.9)
        return (p_min * 0.5, p_max * 2.0)
        
    elif transform_type == TransformType.BIEXPONENTIAL:
        # Use actual data percentiles as FlowJo does — no arbitrary hardcoded
        # floor/ceiling.  This makes the default view data-driven.
        p_lo = float(np.percentile(valid_data, 0.5))
        p_hi = float(np.percentile(valid_data, 99.5))

        if p_lo < 0:
            # Compensated fluorescence: show the negative tail with 5% headroom.
            span = max(p_hi - p_lo, 1.0)
            display_min = p_lo - span * 0.05
        else:
            # Positive-only data (FSC, SSC, bright fluorescence).
            # Stay positive: min = 95% of the data floor so the lowest events
            # sit just inside the left/bottom edge.  Do NOT use span-based
            # padding here — it would subtract a huge number and push min
            # far into negative territory.
            display_min = p_lo * 0.95

        span = max(p_hi - p_lo, 1.0)
        display_max = p_hi + span * 0.05
        return (display_min, display_max)
        
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
    m: float = 4.5
) -> tuple[float, float]:
    """Estimate Logicle W and A parameters from data.

    FlowJo defaults: W=0.5 (1 visual decade linear region), A=0.0.
    A is only set > 0 when there is measurable negative data.
    """
    valid = data[np.isfinite(data)]
    if len(valid) == 0:
        return 0.5, 0.0

    # FlowJo-standard linear-region width. W=0.5 = squish zone is 1 visual
    # decade wide, matching FlowJo defaults exactly.
    w = 0.5

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