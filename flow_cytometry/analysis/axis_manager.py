"""Axis manager for coordinate transformations and range management.

Decouples UI axis logic (GraphWindow, GroupPreview) from data logic.
Ensures consistent auto-ranging and scale synchronization across components.
"""

from __future__ import annotations
from biopro.sdk.utils.logging import get_logger
import numpy as np
from typing import Optional, TYPE_CHECKING
from PyQt6.QtCore import QObject, pyqtSignal

from .scaling import AxisScale, calculate_auto_range
from .transforms import TransformType

if TYPE_CHECKING:
    from .state import FlowState
    import pandas as pd

logger = get_logger(__name__, "flow_cytometry")

class AxisManager(QObject):
    """Coordinates axis scales and auto-ranging across the module.
    
    Signals:
        axis_updated(channel, scale): 
            Emitted when a channel's scale is modified.
    """
    
    axis_updated = pyqtSignal(str, AxisScale)
    
    def __init__(self, state: FlowState, parent=None):
        super().__init__(parent)
        self._state = state
        self._fallback_scales: dict[str, AxisScale] = {}

    def get_scale(
        self,
        channel: str,
        sample_id: Optional[str] = None,
        default_transform: Optional[TransformType] = None,
    ) -> AxisScale:
        """Get the current scale for a channel from the sample's primary group."""
        if sample_id:
            sample = self._state.experiment.samples.get(sample_id)
            if sample and sample.group_ids:
                group = self._state.experiment.groups.get(sample.group_ids[0])
                if group:
                    if channel not in group.channel_scales:
                        transform = default_transform or TransformType.LINEAR
                        group.channel_scales[channel] = AxisScale(transform_type=transform)
                    return group.channel_scales[channel]
        
        if channel not in self._fallback_scales:
            transform = default_transform or TransformType.LINEAR
            self._fallback_scales[channel] = AxisScale(transform_type=transform)
        return self._fallback_scales[channel]

    def set_scale(self, channel: str, scale: AxisScale, notify: bool = True, sample_id: Optional[str] = None):
        """Update a channel's scale in the sample's primary group and notify listeners."""
        saved = False
        if sample_id:
            sample = self._state.experiment.samples.get(sample_id)
            if sample and sample.group_ids:
                group = self._state.experiment.groups.get(sample.group_ids[0])
                if group:
                    group.channel_scales[channel] = scale.copy()
                    saved = True
                    
        if not saved:
            self._fallback_scales[channel] = scale.copy()
            
        if notify:
            self.axis_updated.emit(channel, scale)

    def calculate_range(self, data: pd.Series, channel: str, sample_id: Optional[str] = None) -> tuple[float, float]:
        """Calculate the display range for a channel based on data and scale settings."""
        scale = self.get_scale(channel, sample_id)
        
        # If manual range is set, use it
        if scale.min_val is not None and scale.max_val is not None:
            return (scale.min_val, scale.max_val)
            
        # Otherwise auto-range
        data_np = data.to_numpy() if hasattr(data, "to_numpy") else np.asarray(data)
        return calculate_auto_range(
            data_np,
            scale.transform_type,
            scale.outlier_percentile
        )

    def update_auto_range(self, sample_id: str, channel: str, axis_id: str = "x") -> Optional[tuple[float, float]]:
        """Update the channel's scale with an auto-calculated range based on a sample."""
        sample = self._state.experiment.samples.get(sample_id)
        if not sample or not sample.has_data:
            return None
            
        data = sample.fcs_data.events[channel]
        new_range = self.calculate_range(data, channel, sample_id)
        
        scale = self.get_scale(channel, sample_id).copy()
        scale.min_val, scale.max_val = new_range
        self.set_scale(channel, scale, sample_id=sample_id)
        return new_range
