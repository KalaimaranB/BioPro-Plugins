"""Shared utilities for flow cytometry gate and transform operations.

This module provides reusable, testable functions extracted from gate
implementations to reduce code duplication and improve maintainability.

Key utilities:
- Scale parsing and deserialization
- Transform type resolution
- Parameter extraction for biexponential transforms
- Statistics dictionary construction
- Gate data serialization
"""

from typing import Dict, Any, Optional, Union
import numpy as np
from .transforms import TransformType
from .scaling import AxisScale


class ScaleFactory:
    """Factory for creating and parsing AxisScale objects.
    
    Centralizes scale deserialization logic to ensure consistency
    across all gate types and avoid code duplication.
    """
    
    @staticmethod
    def parse(s: Any) -> AxisScale:
        """Deserialize an AxisScale from dict, object, or None.
        
        Handles multiple input formats gracefully, defaulting to LINEAR
        if parsing fails. This ensures robust deserialization even with
        partially populated or corrupted scale data.
        
        Args:
            s: AxisScale instance, dict representation, or None.
            
        Returns:
            AxisScale object. Defaults to LINEAR if input is invalid.
        """
        if s is None:
            return AxisScale(TransformType.LINEAR)
        
        if isinstance(s, AxisScale):
            return s
        
        if isinstance(s, dict):
            sc = dict(s)  # Shallow copy to avoid mutation
            tt = sc.get("transform_type")
            
            if isinstance(tt, str):
                sc["transform_type"] = TransformTypeResolver.resolve(tt)
            
            try:
                return AxisScale(**sc)
            except Exception:
                # Corrupted or incompatible dict — fall back to LINEAR
                pass
        
        return AxisScale(TransformType.LINEAR)


class TransformTypeResolver:
    """Resolves transform type from various representations.
    
    Handles normalization of transform type identifiers from:
    - TransformType enum instances
    - String values (case-insensitive)
    - String names (case-insensitive)
    
    This eliminates repeated enum resolution logic scattered across gates.
    """
    
    @staticmethod
    def resolve(t_val: Any) -> TransformType:
        """Resolve a transform type identifier to TransformType enum.
        
        Args:
            t_val: TransformType enum, string name, or string value.
            
        Returns:
            TransformType enum instance. Defaults to LINEAR if unrecognized.
        """
        if isinstance(t_val, TransformType):
            return t_val
        
        if isinstance(t_val, str):
            t_lower = t_val.lower()
            for enum_member in TransformType:
                # Match both enum value and enum name case-insensitively
                if (enum_member.value.lower() == t_lower or 
                    enum_member.name.lower() == t_lower):
                    return enum_member
        
        # Unrecognized — default to LINEAR
        return TransformType.LINEAR


class BiexponentialParameters:
    """Encapsulates biexponential (logicle) transform parameters.
    
    Replaces repeated dictionary construction across gates and canvas
    with a single, testable class that extracts parameters consistently
    from AxisScale objects.
    
    Attributes:
        top: Maximum value (default 262144 ≈ 2^18).
        width: Linear region width (default 0.5).
        positive_decades: Positive decade range (default 4.5).
        negative_decades: Negative decade range (default 0.0).
    """
    
    # Defaults match Logicle spec and BiExponentialTransform expectations
    _DEFAULTS = {
        "top": 262144,        # Typical for 18-bit data
        "width": 1.0,         # Standard linear region (increased from 0.5)
        "positive": 4.5,      # Positive decades
        "negative": 0.0,      # Negative decades (typically off)
    }
    
    def __init__(
        self,
        scale: AxisScale,
    ):
        """Extract biexponential parameters from an AxisScale.
        
        Args:
            scale: AxisScale instance to extract parameters from.
                   Parameters accessed via getattr with defaults.
        """
        self.top = getattr(scale, "logicle_t", self._DEFAULTS["top"])
        self.width = getattr(scale, "logicle_w", self._DEFAULTS["width"])
        self.positive = getattr(scale, "logicle_m", self._DEFAULTS["positive"])
        self.negative = getattr(scale, "logicle_a", self._DEFAULTS["negative"])
    
    def to_dict(self) -> Dict[str, float]:
        """Return parameters as a dictionary for transform functions.
        
        Returns:
            Dict with keys: 'top', 'width', 'positive', 'negative'.
                   Suitable for **kwargs expansion into transform calls.
        """
        return {
            "top": self.top,
            "width": self.width,
            "positive": self.positive,
            "negative": self.negative,
        }


class ScaleSerializer:
    """Serializes and deserializes AxisScale objects.
    
    Centralizes the logic for converting AxisScale objects to/from
    dictionaries, ensuring consistent enum handling across all gates.
    """
    
    @staticmethod
    def to_dict(scale: AxisScale) -> Dict[str, Any]:
        """Convert an AxisScale to a serializable dictionary.
        
        Handles enum conversion so results can be JSON-serialized.
        
        Args:
            scale: AxisScale instance to serialize.
            
        Returns:
            Dictionary with all scale attributes. TransformType enums
            are converted to their string values.
        """
        if hasattr(scale, "to_dict"):
            sd = scale.to_dict()
        else:
            sd = dict(getattr(scale, "__dict__", {}))
        
        # Ensure transform_type is serializable
        if "transform_type" in sd and hasattr(sd["transform_type"], "value"):
            sd["transform_type"] = sd["transform_type"].value
        
        return sd


class StatisticsBuilder:
    """Builds statistics dictionaries with consistent structure.
    
    Encapsulates the statistics dictionary format used throughout
    GateController to ensure consistency and enable future evolution.
    """
    
    @staticmethod
    def build(
        count: int,
        pct_parent: float,
        pct_total: float,
    ) -> Dict[str, Union[int, float]]:
        """Build a statistics dictionary for a gate node.
        
        Args:
            count: Number of events in this gate.
            pct_parent: Percentage of parent population.
            pct_total: Percentage of root population.
            
        Returns:
            Dictionary with keys: 'count', 'pct_parent', 'pct_total'.
                   Percentages are rounded to 2 decimal places.
        """
        return {
            "count": count,
            "pct_parent": round(pct_parent, 2),
            "pct_total": round(pct_total, 2),
        }
