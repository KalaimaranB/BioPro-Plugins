"""Group Preview Panel — shows low-res renders of all samples in a group.

Refactored to use AxisManager, PopulationService, and RenderTask.
"""

from __future__ import annotations
import logging
from typing import Optional, Dict

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QGridLayout,
)
from PyQt6.QtGui import QImage, QPixmap

from biopro.ui.theme import Colors, Fonts
from biopro.core.task_scheduler import task_scheduler

from ...analysis.state import FlowState
from ...analysis.experiment import Sample
from ...analysis.event_bus import Event, EventType
from ...analysis.constants import (
    PREVIEW_LIMIT_DEFAULT,
    PREVIEW_THUMBNAIL_SIZE,
    MAIN_PLOT_MAX_EVENTS_OPTIMIZED,
)

logger = logging.getLogger(__name__)

class PreviewThumbnail(QFrame):
    """A single sample thumbnail in the preview grid."""

    def __init__(self, sample_id: str, state: FlowState, parent=None):
        super().__init__(parent)
        self._sample_id = sample_id
        self._state = state
        self._last_params = None
        self._current_task_id = None
        self._setup_ui()
        
        # Connect to global signals ONLY ONCE
        task_scheduler.task_finished.connect(self._on_global_task_finished)
        task_scheduler.task_error.connect(self._on_global_task_error)

    def _setup_ui(self):
        self.setFixedSize(PREVIEW_THUMBNAIL_SIZE[0] + 8, PREVIEW_THUMBNAIL_SIZE[1] + 24)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(f"background: {Colors.BG_DARK}; border: 1px solid {Colors.BORDER}; border-radius: 4px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        self._img = QLabel()
        self._img.setFixedSize(*PREVIEW_THUMBNAIL_SIZE)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setScaledContents(True) # Enable High-DPI scaling
        self._img.setStyleSheet("background: white; border: 1px solid #DDDDDD;")
        layout.addWidget(self._img)
        
        sample = self._state.experiment.samples.get(self._sample_id)
        display_name = sample.display_name if sample else self._sample_id
        self._name = QLabel(display_name[:18])
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: 9px;")
        layout.addWidget(self._name)

    def request_render(self, node_id: Optional[str] = None, temp_gate=None):
        """Submit a background render task for this thumbnail."""
        x_param = self._state.active_x_param
        y_param = self._state.active_y_param
        plot_type = self._state.active_plot_type

        # Use AxisManager to get current scales (synced with main canvas)
        x_scale = self._state.axis_manager.get_scale(x_param)
        y_scale = self._state.axis_manager.get_scale(y_param)
        
        gate_id = temp_gate.gate_id if temp_gate else None

        # Cache invalidation check
        scale_key = (x_scale.min_val, x_scale.max_val, y_scale.min_val, y_scale.max_val)
        current_params = (x_param, y_param, node_id, gate_id, scale_key, plot_type)
        if current_params == self._last_params:
            return
        self._last_params = current_params

        # Use PopulationService to get gated events
        events = self._state.population_service.get_gated_events(self._sample_id, node_id)
        if events is None or len(events) == 0:
            return

        # Calculate display ranges
        x_range = self._state.axis_manager.calculate_range(events[x_param], x_param)
        y_range = self._state.axis_manager.calculate_range(events[y_param], y_param)

        # Configure and submit RenderTask
        from ...analysis.render_task import RenderTask
        task = RenderTask()
        w, h = PREVIEW_THUMBNAIL_SIZE[0] * 2, PREVIEW_THUMBNAIL_SIZE[1] * 2
        # Collect gates to render (children of the current node + temp gate)
        gates_to_show = []
        current_node = self._state.population_service.find_node(self._sample_id, node_id)
        if current_node:
            for child in current_node.children:
                if child.gate:
                    gates_to_show.append(child.gate)
        
        if temp_gate:
            gates_to_show.append(temp_gate)

        # Pass quality settings to RenderTask
        from ...analysis.constants import MAIN_PLOT_MAX_EVENTS_OPTIMIZED
        is_full = self._state.render_quality == "transparent" # "transparent" means "Full" in the backend
        max_events = None if is_full else MAIN_PLOT_MAX_EVENTS_OPTIMIZED
        quality_mult = 2.0 if is_full else 1.0

        task.configure(
            data=events,
            x_param=x_param,
            y_param=y_param,
            x_scale=x_scale,
            y_scale=y_scale,
            x_range=x_range,
            y_range=y_range,
            width_px=w,
            height_px=h,
            plot_type=plot_type,
            max_events=max_events,
            quality_multiplier=quality_mult,
            gates=gates_to_show,
            selected_gate_id=self._state.current_gate_id
        )
        
        worker = task_scheduler.submit(task, self._state)
        self._current_task_id = worker.task_id  # submit() returns the worker; the ID is on .task_id

    def _on_global_task_finished(self, tid: str, results: dict) -> None:
        if str(tid) == str(getattr(self, "_current_task_id", None)):
            self._on_render_done(results)

    def _on_global_task_error(self, tid: str, error_msg: str) -> None:
        if str(tid) == str(getattr(self, "_current_task_id", None)):
            logger.warning(f"Render error for {self._sample_id}: {error_msg}")

    def _on_render_done(self, results: dict) -> None:
        """Called on the UI thread when the off-thread render completes."""
        if "error" in results:
            logger.warning(f"Render error for {self._sample_id}: {results['error']}")
            return
            
        buf = results.get("image_data")
        if not buf:
            return
            
        w, h = results["width"], results["height"]
        logger.debug(f"PreviewThumbnail: received buffer {len(buf)} bytes for {self._sample_id}")
        
        # Force a copy of the buffer so it doesn't get garbage collected
        # Also use ARGB32 as it's more stable on some platforms for raw buffers
        try:
            qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888).copy()
            self._img.setPixmap(QPixmap.fromImage(qimg))
            self._img.update() 
        except Exception as e:
            logger.error(f"Failed to load image buffer for {self._sample_id}: {e}")


class GroupPreviewPanel(QWidget):
    """Panel showing previews for all samples in a group."""

    def __init__(self, state: FlowState, parent=None):
        super().__init__(parent)
        self._state = state
        self._current_sample_id: Optional[str] = None
        self._current_node_id: Optional[str] = None
        self._thumbnails: Dict[str, PreviewThumbnail] = {}
        self._setup_ui()
        self._setup_events()
        
        # Throttle timer for real-time gate previews
        from ...analysis.constants import PREVIEW_THROTTLE_MS
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_THROTTLE_MS)
        self._preview_timer.timeout.connect(self._do_throttled_refresh)
        self._pending_temp_gate = None

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        hdr = QLabel("👥 Group Preview")
        hdr.setStyleSheet(f"color: {Colors.FG_SECONDARY}; font-size: 10px; font-weight: 700;")
        layout.addWidget(hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"background: {Colors.BG_DARKEST};")

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {Colors.BG_DARKEST};")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)
        self.setMinimumHeight(200)

    def _setup_events(self) -> None:
        eb = self._state.event_bus
        eb.subscribe(EventType.AXIS_PARAMS_CHANGED, lambda _: self._refresh_all())
        eb.subscribe(EventType.AXIS_RANGE_CHANGED,  lambda _: self._refresh_all())
        eb.subscribe(EventType.TRANSFORM_CHANGED,   lambda _: self._refresh_all())
        eb.subscribe(EventType.GATE_CREATED,        lambda _: self._refresh_all())
        eb.subscribe(EventType.GATE_MODIFIED,       lambda _: self._refresh_all())
        eb.subscribe(EventType.GATE_DELETED,        lambda _: self._refresh_all())
        eb.subscribe(EventType.DISPLAY_MODE_CHANGED, lambda _: self._refresh_all())
        eb.subscribe(EventType.GATE_PREVIEW,        self._on_gate_preview)

    def _on_gate_preview(self, event: Event) -> None:
        """Handle real-time gate drawing preview."""
        self._pending_temp_gate = event.data.get("gate")
        if not self._preview_timer.isActive():
            self._preview_timer.start()

    def _do_throttled_refresh(self) -> None:
        """Execute the refresh with the latest pending preview gate."""
        self._refresh_all(temp_gate=self._pending_temp_gate)
        self._pending_temp_gate = None

    def update_context(self, sample_id: str, node_id: Optional[str]) -> None:
        if sample_id == self._current_sample_id and node_id == self._current_node_id:
            self._refresh_all()
            return
        self._current_sample_id = sample_id
        self._current_node_id = node_id
        self._rebuild()

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._thumbnails.clear()

        if not self._current_sample_id:
            return

        sample = self._state.experiment.samples.get(self._current_sample_id)
        if not sample:
            return

        peers = []
        gid = None
        if sample.group_ids:
            gid = list(sample.group_ids)[0]
            peers = [s for s in self._state.experiment.samples.values()
                     if gid in s.group_ids and s.sample_id != self._current_sample_id]
        
        # Fallback: if no group peers, show all other samples in experiment
        if not peers:
            logger.info("GroupPreviewPanel._rebuild: no group peers found, falling back to all samples.")
            peers = [s for s in self._state.experiment.samples.values() 
                     if s.sample_id != self._current_sample_id]
        
        logger.info(f"GroupPreviewPanel._rebuild: found {len(peers)} samples to preview (group={gid})")
        for i, p in enumerate(peers):
            thumb = PreviewThumbnail(p.sample_id, self._state)
            self._thumbnails[p.sample_id] = thumb
            self._grid.addWidget(thumb, i // 3, i % 3)
            thumb.request_render(self._current_node_id)

    def _refresh_all(self, temp_gate=None) -> None:
        for thumb in self._thumbnails.values():
            thumb.request_render(self._current_node_id, temp_gate=temp_gate)
