"""Flow cytometry workspace state container.

``FlowState`` is the single source of truth for the entire analysis
session.  It follows the same pattern as the Western Blot
``AnalysisState``: a plain dataclass that holds every intermediate
result, with ``to_workflow_dict`` / ``from_workflow_dict`` for
serialization.

The state is intentionally kept separate from both the UI and the
analysis engines so that:
- Undo/Redo can snapshot it cheaply via ``export_state`` / ``load_state``.
- It can be serialized to disk independently of the GUI.
- Tests can inspect it without importing PyQt.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from biopro.sdk.utils.logging import get_logger
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from biopro.sdk.core import PluginState

import numpy as np

from .compensation import CompensationMatrix
from .experiment import Experiment, Sample, SampleRole, WorkflowTemplate
from .scaling import AxisScale
from biopro.sdk.core.events import CentralEventBus
from . import events
from .config import FlowConfig, RenderConfig

if TYPE_CHECKING:
    from .axis_manager import AxisManager
    from .population_service import PopulationService

logger = get_logger(__name__, "flow_cytometry")


@dataclass
class ExperimentState:
    """Domain model state layer."""
    experiment: Experiment = field(default_factory=Experiment)
    compensation: Optional[CompensationMatrix] = None

    def to_dict(self) -> dict:
        return {
            "experiment": self.experiment.to_dict() if hasattr(self.experiment, "to_dict") else None,
            "compensation": self.compensation.to_dict() if hasattr(self.compensation, "to_dict") else None,
        }

@dataclass
class ViewState:
    """UI and presentation state layer."""
    current_sample_id: Optional[str] = None
    current_gate_id: Optional[str] = None
    active_x_param: str = field(default_factory=lambda: FlowConfig.get_last_params()[0])
    active_y_param: str = field(default_factory=lambda: FlowConfig.get_last_params()[1])
    active_transform_x: str = "linear"
    active_transform_y: str = "linear"
    active_plot_type: str = "pseudocolor"
    auto_range_on_quality: bool = field(default_factory=FlowConfig.get_auto_range)
    _render_config: RenderConfig = field(default_factory=RenderConfig)

    @property
    def render_config(self) -> RenderConfig:
        return self._render_config

    @render_config.setter
    def render_config(self, value: RenderConfig) -> None:
        self._render_config = value
        CentralEventBus.publish(events.RENDER_CONFIG_CHANGED, {"config": value})

    def to_dict(self) -> dict:
        return {
            "current_sample_id": self.current_sample_id,
            "current_gate_id": self.current_gate_id,
            "active_x_param": self.active_x_param,
            "active_y_param": self.active_y_param,
            "active_transform_x": self.active_transform_x,
            "active_transform_y": self.active_transform_y,
            "active_plot_type": self.active_plot_type,
            "auto_range_on_quality": self.auto_range_on_quality,
            "render_config": self.render_config.to_dict(),
        }

@dataclass
class FlowState(PluginState):
    """Mutable state for one flow cytometry analysis session.
    
    Now layered into 'data' (ExperimentState) and 'view' (ViewState).
    """

    # ── Layers ────────────────────────────────────────────────────────
    data: ExperimentState = field(default_factory=ExperimentState)
    view: ViewState = field(default_factory=ViewState)
    
    # ── Services ──────────────────────────────────────────────────────
    axis_manager: Optional[Any] = None
    population_service: Optional[Any] = None

    # ── Backward Compatibility Properties ───────────────────────────
    # These allow existing code to access state.experiment instead of state.data.experiment
    @property
    def experiment(self) -> Experiment: return self.data.experiment
    @experiment.setter
    def experiment(self, val: Experiment): self.data.experiment = val

    @property
    def compensation(self) -> Optional[CompensationMatrix]: return self.data.compensation
    @compensation.setter
    def compensation(self, val: Optional[CompensationMatrix]): self.data.compensation = val

    @property
    def current_sample_id(self) -> Optional[str]: return self.view.current_sample_id
    @current_sample_id.setter
    def current_sample_id(self, val: Optional[str]): self.view.current_sample_id = val

    @property
    def current_gate_id(self) -> Optional[str]: return self.view.current_gate_id
    @current_gate_id.setter
    def current_gate_id(self, val: Optional[str]): self.view.current_gate_id = val

    @property
    def active_x_param(self) -> str: return self.view.active_x_param
    @active_x_param.setter
    def active_x_param(self, val: str): self.view.active_x_param = val

    @property
    def active_y_param(self) -> str: return self.view.active_y_param
    @active_y_param.setter
    def active_y_param(self, val: str): self.view.active_y_param = val

    @property
    def active_transform_x(self) -> str: return self.view.active_transform_x
    @active_transform_x.setter
    def active_transform_x(self, val: str): self.view.active_transform_x = val

    @property
    def active_transform_y(self) -> str: return self.view.active_transform_y
    @active_transform_y.setter
    def active_transform_y(self, val: str): self.view.active_transform_y = val

    @property
    def active_plot_type(self) -> str: return self.view.active_plot_type
    @active_plot_type.setter
    def active_plot_type(self, val: str): self.view.active_plot_type = val

    @property
    def render_config(self) -> RenderConfig: return self.view.render_config
    @render_config.setter
    def render_config(self, val: RenderConfig): self.view.render_config = val

    @property
    def auto_range_on_quality(self) -> bool: return self.view.auto_range_on_quality
    @auto_range_on_quality.setter
    def auto_range_on_quality(self, val: bool): self.view.auto_range_on_quality = val

    def to_dict(self) -> dict:
        """Standard serialization for undo history snapshots."""
        return {
            "data": self.data.to_dict(),
            "view": self.view.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> FlowState:
        """Reconstruct the nested state objects properly from dict for Undo/Redo."""
        state = cls()
        if "data" in data:
            d_data = data["data"]
            if "experiment" in d_data and d_data["experiment"]:
                state.data.experiment = Experiment.from_dict(d_data["experiment"])
            if "compensation" in d_data and d_data["compensation"]:
                state.data.compensation = CompensationMatrix.from_dict(d_data["compensation"])
        if "view" in data:
            v_data = data["view"]
            state.view.current_sample_id = v_data.get("current_sample_id")
            state.view.current_gate_id = v_data.get("current_gate_id")
            state.view.active_x_param = v_data.get("active_x_param", "FSC-A")
            state.view.active_y_param = v_data.get("active_y_param", "SSC-A")
            state.view.active_transform_x = v_data.get("active_transform_x", "linear")
            state.view.active_transform_y = v_data.get("active_transform_y", "linear")
            state.view.active_plot_type = v_data.get("active_plot_type", "pseudocolor")
            state.view.auto_range_on_quality = v_data.get("auto_range_on_quality", True)
            if "render_config" in v_data:
                state.view.render_config = RenderConfig.from_dict(v_data["render_config"])
        return state

    # ── Serialization ─────────────────────────────────────────────────

    def to_workflow_dict(self) -> dict:
        """Serialize the entire state for workflow save/load.

        Returns:
            A JSON-serializable dictionary.
        """
        # Serialize sample file paths so we can reload FCS data
        sample_paths = {}
        for sid, sample in self.experiment.samples.items():
            if sample.fcs_data and sample.fcs_data.file_path:
                sample_paths[sid] = str(sample.fcs_data.file_path)

        return {
            "experiment": self.experiment.to_dict(),
            "sample_paths": sample_paths,
            "compensation": (
                self.compensation.to_dict() if self.compensation else None
            ),
            "view": {
                "current_sample_id": self.current_sample_id,
                "current_gate_id": self.current_gate_id,
                "active_x_param": self.active_x_param,
                "active_y_param": self.active_y_param,
                "active_transform_x": self.active_transform_x,
                "active_transform_y": self.active_transform_y,
                "active_plot_type": self.active_plot_type,
                "render_config": self.render_config.to_dict(),
                "auto_range_on_quality": self.auto_range_on_quality,
            }
        }

    def from_workflow_dict(self, data: dict) -> None:
        """Restore state from a serialized dictionary.

        If ``sample_paths`` are present, FCS files are reloaded from
        disk.  If a file no longer exists, the sample is kept but
        flagged without data.

        Args:
            data: Dictionary previously produced by
                  :meth:`to_workflow_dict`.
        """
        logger.info(f"Restoring FlowState from workflow dict (samples: {len(data.get('experiment', {}).get('samples', {}))})")
        
        # Compensation
        comp_data = data.get("compensation")
        if comp_data:
            self.compensation = CompensationMatrix.from_dict(comp_data)
        else:
            self.compensation = None

        # View state
        view = data.get("view", {})
        self.current_sample_id = view.get("current_sample_id")
        self.current_gate_id = view.get("current_gate_id")
        self.active_x_param = view.get("active_x_param", "FSC-A")
        self.active_y_param = view.get("active_y_param", "SSC-A")
        self.active_transform_x = view.get("active_transform_x", "linear")
        self.active_transform_y = view.get("active_transform_y", "linear")
        self.active_plot_type = view.get("active_plot_type", "pseudocolor")
        self.render_config = RenderConfig.from_dict(view.get("render_config", {}))
        self.auto_range_on_quality = view.get("auto_range_on_quality", True)

        # Experiment reconstruction: reload FCS files from saved paths
        exp_data = data.get("experiment", {})
        if exp_data:
            logger.info("Restoring experiment model...")
            self.experiment = Experiment.from_dict(exp_data)

            sample_paths = data.get("sample_paths", {})
            if sample_paths:
                logger.info(f"Reloading {len(sample_paths)} FCS files...")
                self._reload_fcs_data(sample_paths)

        logger.info("FlowState restoration complete.")

    def _reload_fcs_data(self, sample_paths: dict[str, str]) -> None:
        """Reload FCS event data from disk for saved samples.

        Args:
            sample_paths: Mapping of sample_id → file path string.
        """
        from .fcs_io import load_fcs

        for sid, path_str in sample_paths.items():
            sample = self.experiment.samples.get(sid)
            if sample is None:
                continue

            path = Path(path_str)
            if not path.exists():
                logger.warning(
                    "FCS file no longer exists: %s (sample: %s)",
                    path, sample.display_name,
                )
                continue

            try:
                fcs_data = load_fcs(path)
                
                # Re-apply compensation if it was active when saved
                if sample.is_compensated and self.compensation:
                    # Check if it was already compensated by the loader (embedded SPILL)
                    if not fcs_data.is_compensated:
                        from .compensation import apply_compensation
                        fcs_data.events = apply_compensation(fcs_data, self.compensation)
                        fcs_data.is_compensated = True
                        logger.info(f"Re-applied BioPro compensation matrix to reloaded sample '{sample.display_name}'")
                
                sample.fcs_data = fcs_data
                logger.info(
                    "Reloaded FCS data for '%s': %d events",
                    sample.display_name, fcs_data.num_events,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to reload FCS for '%s': %s",
                    sample.display_name, exc,
                )
