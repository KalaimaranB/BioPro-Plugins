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

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from biopro.sdk.core import PluginState

import numpy as np

from .compensation import CompensationMatrix
from .experiment import Experiment, Sample, SampleRole, WorkflowTemplate
from .scaling import AxisScale
from .event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)


@dataclass
class FlowState(PluginState):
    """Mutable state for one flow cytometry analysis session.

    Attributes:
        experiment:         The full experiment model (samples, groups,
                            marker mappings, workflow template).
        compensation:       The computed or imported compensation matrix.
        current_sample_id:  The sample currently displayed in the main
                            graph window.
        current_gate_id:    The gate currently selected in the tree.
        active_x_param:     X-axis parameter for the current graph.
        active_y_param:     Y-axis parameter for the current graph.
        active_transform_x: Transform type string for X axis.
        active_transform_y: Transform type string for Y axis.
        active_plot_type:   Current plot display mode.
    """

    # ── Core data ─────────────────────────────────────────────────────
    experiment: Experiment = field(default_factory=Experiment)
    compensation: Optional[CompensationMatrix] = None

    # ── View state ────────────────────────────────────────────────────
    current_sample_id: Optional[str] = None
    current_gate_id: Optional[str] = None
    active_x_param: str = "FSC-A"
    active_y_param: str = "SSC-A"
    active_transform_x: str = "linear"
    active_transform_y: str = "linear"
    active_plot_type: str = "pseudocolor"
    
    # ── Transformation State ──────────────────────────────────────────
    channel_scales: dict[str, AxisScale] = field(default_factory=dict)
    
    # ── Event System ──────────────────────────────────────────────────
    # All state changes are published as events via this bus
    event_bus: EventBus = field(default_factory=EventBus)
    
    # ── Rendering preferences ─────────────────────────────────────────
    auto_range_on_quality: bool = True  # Auto-update axes when render mode changes
    _render_quality: str = field(default="optimized")

    @property
    def render_quality(self) -> str:
        return self._render_quality

    @render_quality.setter
    def render_quality(self, value: str) -> None:
        if self._render_quality != value:
            self._render_quality = value
            self.event_bus.publish(Event(
                type=EventType.RENDER_MODE_CHANGED,
                data={"mode": value},
                source="FlowState"
            ))

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
            },
            "channel_scales": {
                ch: {
                    "transform_type": sc.transform_type.value,
                    "min_val": sc.min_val,
                    "max_val": sc.max_val,
                    "logicle_t": sc.logicle_t,
                    "logicle_w": sc.logicle_w,
                    "logicle_m": sc.logicle_m,
                    "logicle_a": sc.logicle_a,
                }
                for ch, sc in self.channel_scales.items()
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

        # Experiment reconstruction: reload FCS files from saved paths
        exp_data = data.get("experiment", {})
        if exp_data:
            logger.info("Restoring experiment model...")
            self.experiment = Experiment.from_dict(exp_data)

            sample_paths = data.get("sample_paths", {})
            if sample_paths:
                logger.info(f"Reloading {len(sample_paths)} FCS files...")
                self._reload_fcs_data(sample_paths)

        # Scale parameters
        scales_data = data.get("channel_scales", {})
        from .transforms import TransformType
        for ch, sc in scales_data.items():
            self.channel_scales[ch] = AxisScale(
                transform_type=TransformType(sc.get("transform_type", "linear")),
                min_val=sc.get("min_val"),
                max_val=sc.get("max_val"),
                logicle_t=sc.get("logicle_t", 262144.0),
                logicle_w=sc.get("logicle_w", 0.5),
                logicle_m=sc.get("logicle_m", 4.5),
                logicle_a=sc.get("logicle_a", 0.0),
            )

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
