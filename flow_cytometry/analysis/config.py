"""Configuration management for Flow Cytometry module.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from biopro.sdk.utils.io import PluginConfig
from . import constants

class FlowConfig:
    """Manages persistent user preferences for the flow module."""
    
    _config = PluginConfig("flow_cytometry")
    
    # Keys
    AUTO_RANGE = "auto_range_on_quality"
    LAST_X_PARAM = "last_x_param"
    LAST_Y_PARAM = "last_y_param"
        
    @classmethod
    def get_auto_range(cls) -> bool:
        return cls._config.get(cls.AUTO_RANGE, True)
    
    @classmethod
    def set_auto_range(cls, value: bool):
        cls._config.set(cls.AUTO_RANGE, value)
        cls._config.save()

    @classmethod
    def get_last_params(cls) -> tuple[str, str]:
        x = cls._config.get(cls.LAST_X_PARAM, "FSC-A")
        y = cls._config.get(cls.LAST_Y_PARAM, "SSC-A")
        return x, y
    
    @classmethod
    def set_last_params(cls, x: str, y: str):
        cls._config.set(cls.LAST_X_PARAM, x)
        cls._config.set(cls.LAST_Y_PARAM, y)
        cls._config.save()

@dataclass
class RenderConfig:
    """Stores user-customizable rendering parameters for pseudocolor plots."""
    max_events: int = constants.MAIN_PLOT_MAX_EVENTS_OPTIMIZED
    nbins_scaling: float = constants.NBINS_SCALING_FACTOR
    sigma_scaling: float = constants.SIGMA_SCALING_FACTOR
    density_threshold: float = constants.DENSITY_THRESHOLD_MIN
    vibrancy_min: float = constants.VIBRANCY_MIN
    vibrancy_range: float = constants.VIBRANCY_RANGE

    def to_dict(self) -> dict:
        return {
            "max_events": self.max_events,
            "nbins_scaling": self.nbins_scaling,
            "sigma_scaling": self.sigma_scaling,
            "density_threshold": self.density_threshold,
            "vibrancy_min": self.vibrancy_min,
            "vibrancy_range": self.vibrancy_range,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RenderConfig:
        return cls(
            max_events=data.get("max_events", constants.MAIN_PLOT_MAX_EVENTS_OPTIMIZED),
            nbins_scaling=data.get("nbins_scaling", constants.NBINS_SCALING_FACTOR),
            sigma_scaling=data.get("sigma_scaling", constants.SIGMA_SCALING_FACTOR),
            density_threshold=data.get("density_threshold", constants.DENSITY_THRESHOLD_MIN),
            vibrancy_min=data.get("vibrancy_min", constants.VIBRANCY_MIN),
            vibrancy_range=data.get("vibrancy_range", constants.VIBRANCY_RANGE),
        )
