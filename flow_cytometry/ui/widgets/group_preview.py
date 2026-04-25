"""Group Preview Panel — shows low-res renders of all samples in a group.

Refactored to use AxisManager, PopulationService, and RenderTask.
"""

from __future__ import annotations
import logging
from typing import Optional, Dict

import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt
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
)

logger = logging.getLogger(__name__)

class PreviewThumbnail(QFrame):
    """A single sample thumbnail in the preview grid."""

    def __init__(self, sample_id: str, state: FlowState, parent=None):
        super().__init__(parent)
        self._sample_id = sample_id
        self._state = state
        self._last_params = None
        self._setup_ui()

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
        self._img.setStyleSheet("background: black;")
        layout.addWidget(self._img)
        
        self._name = QLabel(self._sample_id[:12])
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
        w, h = PREVIEW_THUMBNAIL_SIZE
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
            plot_type=plot_type
        )
        
        worker = task_scheduler.submit(task, None)
        worker.finished.connect(self._on_render_done)

    def _on_render_done(self, results: dict) -> None:
        """Called on the UI thread when the off-thread render completes."""
        if "error" in results:
            logger.warning(f"Render error for {self._sample_id}: {results['error']}")
            return
            
        buf = results.get("image_data")
        if not buf:
            return
            
        w, h = results["width"], results["height"]
        qimg = QImage(buf, w, h, QImage.Format.Format_RGBA8888)
        self._img.setPixmap(QPixmap.fromImage(qimg))


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
        if sample.group_ids:
            gid = list(sample.group_ids)[0]
            peers = [s for s in self._state.experiment.samples.values()
                     if gid in s.group_ids and s.sample_id != self._current_sample_id]
        
        for i, p in enumerate(peers):
            thumb = PreviewThumbnail(p.sample_id, self._state)
            self._thumbnails[p.sample_id] = thumb
            self._grid.addWidget(thumb, i // 3, i % 3)
            thumb.request_render(self._current_node_id)

    def _refresh_all(self) -> None:
        for thumb in self._thumbnails.values():
            thumb.request_render(self._current_node_id)
