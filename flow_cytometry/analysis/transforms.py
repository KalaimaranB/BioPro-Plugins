"""Axis transformations for flow cytometry data visualization.

Provides linear, logarithmic, and biexponential (logicle) transforms
using ``flowkit``'s validated C-extension implementations.

The Logicle transform uses the Parks et al. (2006) algorithm via
``flowutils``, not a simplified approximation.

Reference:
    Parks, D.R., Roederer, M., Moore, W.A. (2006). A new "Logicle"
    display method avoids deceptive effects of logarithmic scaling for
    low signals and compensated data. *Cytometry Part A*, 69A:541-551.
"""

from __future__ import annotations

from biopro.sdk.utils.logging import get_logger
from enum import Enum
from typing import Optional

import numpy as np

logger = get_logger(__name__, "flow_cytometry")


class TransformType(Enum):
    """Available axis transformation types."""

    LINEAR = "linear"
    LOG = "log"
    BIEXPONENTIAL = "biexponential"


# ── Cache for FlowKit transform instances ────────────────────────────────────
_logicle_cache: dict[tuple, object] = {}


def linear_transform(
    data: np.ndarray,
    **kwargs,
) -> np.ndarray:
    """Linear (identity) transform — returns raw values unchanged.

    Matplotlib auto-ranges the axes based on the actual data extent,
    which is what scientists expect for scatter parameters like
    FSC-A and SSC-A.

    Args:
        data: Raw channel values.

    Returns:
        The same values (as float64 for consistency).
    """
    return data.astype(np.float64)


def log_transform(
    data: np.ndarray,
    decades: float = 4.5,
    min_value: float = 1.0,
) -> np.ndarray:
    """Logarithmic (base-10) scaling.

    Values below ``min_value`` are clamped to ``min_value`` to avoid
    log(0) or log(negative).

    Args:
        data:      Raw channel values.
        decades:   Number of decades to display.
        min_value: Floor value before taking the log.

    Returns:
        Log-scaled values.
    """
    clamped = np.maximum(data, min_value)
    return np.log10(clamped) / decades


def biexponential_transform(
    data: np.ndarray,
    *,
    enable_dithering: bool = False,
    top: float = 262144.0,
    width: float = 1.0,
    positive: float = 4.5,
    negative: float = 0.0,
) -> np.ndarray:
    """Biexponential (logicle) transform for compensated data.

    Uses ``flowkit.transforms.LogicleTransform`` which wraps the
    validated C implementation from ``flowutils``.  This is the **real**
    Parks 2006 algorithm, not an approximation.

    Falls back to ``flowutils.transforms.logicle`` if FlowKit's
    high-level API is unavailable, and finally to an asinh
    approximation as a last resort.

    Args:
        data:             Raw channel values.
        enable_dithering: If True, apply +/-0.5 uniform jitter to prevent barcode artifacts.
        top:              Maximum expected data value (T parameter).
        width:            Linearization width (W parameter, decades).
        positive:         Number of positive decades (M parameter).
        negative:         Additional negative decades (A parameter).

    Returns:
        Transformed values in display units.
    """
    cache_key = (top, width, positive, negative)

    # Apply continuous +/-0.5 uniform dithering to prevent integer banding
    # (barcode artifacts) which dramatically skew density calculations near 0
    data_jitter = np.asarray(data, dtype=np.float64).copy()
    if enable_dithering:
        data_jitter += np.random.uniform(-0.5, 0.5, size=data_jitter.shape)

    # ── Attempt 1: flowkit.transforms.LogicleTransform ────────────────
    # Primary method: Uses FlowKit's object-oriented LogicleTransform class.
    # We cache the instantiated transform object because Logicle calculation 
    # initialization (spline generation) is mathematically expensive. 
    # Reusing the transform significantly improves UI slider responsiveness.
    try:
        if cache_key not in _logicle_cache:
            import flowkit as fk
            xform = fk.transforms.LogicleTransform(
                param_t=top,
                param_w=width,
                param_m=positive,
                param_a=negative,
            )
            _logicle_cache[cache_key] = xform

        xform = _logicle_cache[cache_key]
        return xform.apply(data_jitter)
    except (ImportError, AttributeError):
        pass

    # ── Attempt 2: flowutils.transforms.logicle ──────────────────────
    # Secondary fallback: If the high-level FlowKit wrapper is unavailable or 
    # has a breaking API change, we drop down to the underlying `flowutils` C-extension.
    # This directly calls the Parks (2006) implementation without caching.
    try:
        from flowutils.transforms import logicle as fu_logicle
        return fu_logicle(data_jitter, t=top, w=width, m=positive, a=negative)
    except ImportError:
        pass

    # ── Attempt 3: arcsinh Approximation ─────────────────────────────
    # Ultimate fallback: If the environment lacks C-compiled dependencies (e.g. 
    # running in a pure-python or restricted CI environment), we use an analytical 
    # arcsinh approximation. This is mathematically similar to logicle around zero, 
    # ensuring the application doesn't hard-crash when rendering.
    logger.warning(
        f"Neither flowkit nor flowutils available — using parameterized asinh fallback (W={width}, M={positive}). "
        "Install flowkit for the real Logicle transform."
    )
    # Parameterized asinh to respond to W and M
    # W controls the linear width, M controls the positive decades
    # Roughly: cofactor = T / 10^M * 10^W
    cofactor = (top / (10**positive)) * (10**width)
    return np.arcsinh(data_jitter / cofactor) / positive


def apply_transform(
    data: np.ndarray,
    transform_type: TransformType,
    **kwargs,
) -> np.ndarray:
    """Apply a named transform to data.

    Args:
        data:           Raw channel values.
        transform_type: Which transform to apply.
        **kwargs:       Additional arguments passed to the transform.

    Returns:
        Transformed values.
    """
    if transform_type == TransformType.LINEAR:
        return linear_transform(data, **kwargs)
    elif transform_type == TransformType.LOG:
        return log_transform(data, **kwargs)
    elif transform_type == TransformType.BIEXPONENTIAL:
        return biexponential_transform(data, **kwargs)
    else:
        raise ValueError(f"Unknown transform: {transform_type}")


def invert_linear_transform(
    data: np.ndarray,
    **kwargs,
) -> np.ndarray:
    """Inverse of linear (identity) transform."""
    return data.astype(np.float64)


def invert_log_transform(
    data: np.ndarray,
    decades: float = 4.5,
    min_value: float = 1.0,
) -> np.ndarray:
    """Inverse of logarithmic scaling.
    
    Args:
        data:      Transformed channel values.
        decades:   Number of decades displayed.
        min_value: Floor value that was originally used.

    Returns:
        Raw channel values.
    """
    return 10.0 ** (data * decades)


def invert_biexponential_transform(
    data: np.ndarray,
    *,
    top: float = 262144.0,
    width: float = 1.0,
    positive: float = 4.5,
    negative: float = 0.0,
) -> np.ndarray:
    """Inverse of biexponential (logicle) transform.

    Args:
        data:     Transformed channel values in display units.
        top:      Maximum expected data value (T parameter).
        width:    Linearization width (W parameter, decades).
        positive: Number of positive decades (M parameter).
        negative: Additional negative decades (A parameter).

    Returns:
        Raw channel values.
    """
    cache_key = (top, width, positive, negative)

    # ── Attempt 1: flowkit.transforms.LogicleTransform ────────────────
    try:
        if cache_key not in _logicle_cache:
            import flowkit as fk
            xform = fk.transforms.LogicleTransform(
                param_t=top,
                param_w=width,
                param_m=positive,
                param_a=negative,
            )
            _logicle_cache[cache_key] = xform

        xform = _logicle_cache[cache_key]
        return xform.inverse(data)
    except (ImportError, AttributeError):
        pass

    # ── Attempt 2: flowutils.transforms.logicle_inverse ───────────────
    try:
        from flowutils.transforms import logicle_inverse as fu_logicle_inverse
        return fu_logicle_inverse(data, t=top, w=width, m=positive, a=negative)
    except ImportError:
        pass

    # ── Attempt 3: asinh fallback (parameterized) ────────────────────
    cofactor = (top / (10**positive)) * (10**width)
    return np.sinh(data * positive) * cofactor


def invert_transform(
    data: np.ndarray,
    transform_type: TransformType,
    **kwargs,
) -> np.ndarray:
    """Apply the inverse of a named transform to mapped data.

    Args:
        data:           Transformed display values.
        transform_type: Which transform was applied.
        **kwargs:       Additional arguments passed to the transform.

    Returns:
        Raw data values.
    """
    if transform_type == TransformType.LINEAR:
        return invert_linear_transform(data, **kwargs)
    elif transform_type == TransformType.LOG:
        return invert_log_transform(data, **kwargs)
    elif transform_type == TransformType.BIEXPONENTIAL:
        return invert_biexponential_transform(data, **kwargs)
    else:
        raise ValueError(f"Unknown transform: {transform_type}")
